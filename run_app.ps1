$ErrorActionPreference = "Stop"
$Python = "D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Khong tim thay moi truong VieNeu tai $Python"
}

$ConfigPath = Join-Path $PSScriptRoot "secrets\production-runtime.env"
$AllowedKeys = @(
    "PREPARE_RUNTIME_MODE",
    "PREPARE_FEATURE_AVAILABLE",
    "PREPARE_MUTATION_ENABLED",
    "PREPARE_OPERATOR_WINDOW_OPEN",
    "PREPARE_CANONICAL_SCHEMA_READY",
    "PREPARE_KILL_SWITCH_ACTIVE",
    "PREPARE_OPERATOR_AUTH_ENABLED",
    "PREPARE_OPERATOR_ID",
    "PREPARE_OPERATOR_TOKEN_VERSION",
    "PREPARE_OPERATOR_AUTH_LOCAL_TEST_MODE",
    "PREPARE_RENDER_ENABLED"
)
$PreviousEnvironment = @{}

try {
    if (Test-Path -LiteralPath $ConfigPath) {
        $Values = @{}
        foreach ($Line in Get-Content -LiteralPath $ConfigPath -Encoding UTF8) {
            $Trimmed = $Line.Trim()
            if (-not $Trimmed -or $Trimmed.StartsWith("#")) {
                continue
            }
            $Parts = $Trimmed.Split("=", 2)
            if ($Parts.Count -ne 2) {
                throw "Invalid production runtime configuration line."
            }
            $Name = $Parts[0].Trim()
            $Value = $Parts[1].Trim()
            if ($Name -eq "PREPARE_OPERATOR_TOKEN") {
                if (-not $Value) {
                    throw "PREPARE_OPERATOR_TOKEN must not be empty."
                }
            } elseif ($AllowedKeys -notcontains $Name) {
                throw "Unsupported production runtime configuration key: $Name"
            }
            if ($Values.ContainsKey($Name)) {
                throw "Duplicate production runtime configuration key: $Name"
            }
            $Values[$Name] = $Value
        }
        if ($Values.ContainsKey("PREPARE_OPERATOR_TOKEN")) {
            $TokenBytes = [Text.Encoding]::UTF8.GetBytes($Values["PREPARE_OPERATOR_TOKEN"])
            $Hasher = [Security.Cryptography.SHA256]::Create()
            try {
                $TokenHash = $Hasher.ComputeHash($TokenBytes)
                $Values["PREPARE_OPERATOR_TOKEN_SHA256"] = (
                    [BitConverter]::ToString($TokenHash).Replace("-", "").ToLowerInvariant()
                )
            } finally {
                $Hasher.Dispose()
                [Array]::Clear($TokenBytes, 0, $TokenBytes.Length)
            }
            # The child consumes this bootstrap value before serving requests.
            # It is never returned by an API or copied into browser state.
            $Values["STORY_AUDIO_OPERATOR_TOKEN_BOOTSTRAP"] = $Values["PREPARE_OPERATOR_TOKEN"]
            $Values.Remove("PREPARE_OPERATOR_TOKEN")
        }
        foreach ($Entry in $Values.GetEnumerator()) {
            $PreviousEnvironment[$Entry.Key] = [Environment]::GetEnvironmentVariable(
                $Entry.Key,
                [EnvironmentVariableTarget]::Process
            )
            [Environment]::SetEnvironmentVariable(
                $Entry.Key,
                $Entry.Value,
                [EnvironmentVariableTarget]::Process
            )
        }
    }

    $PreviousEnvironment["STORY_AUDIO_ALLOW_LIVE_DB"] = $env:STORY_AUDIO_ALLOW_LIVE_DB
    $PreviousEnvironment["STORY_AUDIO_SUPERVISED"] = $env:STORY_AUDIO_SUPERVISED
    $PreviousEnvironment["STORY_AUDIO_RESTART_SIGNAL"] = $env:STORY_AUDIO_RESTART_SIGNAL
    $env:STORY_AUDIO_ALLOW_LIVE_DB = "1"
    $env:STORY_AUDIO_SUPERVISED = "1"
    $DataRoot = if ($env:STORY_AUDIO_DATA_DIR) {
        [IO.Path]::GetFullPath($env:STORY_AUDIO_DATA_DIR)
    } else {
        Join-Path $PSScriptRoot "data"
    }
    $env:STORY_AUDIO_RESTART_SIGNAL = Join-Path $DataRoot "runtime\restart.request"
    $LaunchArgs = @($args)
    if ($LaunchArgs.Count -eq 0) {
        $LaunchArgs = @("--host", "127.0.0.1", "--port", "8772")
    }
    if (Test-Path -LiteralPath $env:STORY_AUDIO_RESTART_SIGNAL) {
        Remove-Item -LiteralPath $env:STORY_AUDIO_RESTART_SIGNAL -Force
    }
    $ListenHost = "127.0.0.1"
    $ListenPort = 8772
    for ($Index = 0; $Index -lt $LaunchArgs.Count; $Index++) {
        if ($LaunchArgs[$Index] -eq "--host" -and ($Index + 1) -lt $LaunchArgs.Count) {
            $ListenHost = $LaunchArgs[$Index + 1]
        }
        if ($LaunchArgs[$Index] -eq "--port" -and ($Index + 1) -lt $LaunchArgs.Count) {
            $ListenPort = [int]$LaunchArgs[$Index + 1]
        }
    }

    function Test-StoryAudioPortOpen([string]$HostName, [int]$Port) {
        $Client = [System.Net.Sockets.TcpClient]::new()
        try {
            $Connect = $Client.ConnectAsync($HostName, $Port)
            if (-not $Connect.Wait(500)) { return $false }
            return $Client.Connected
        } catch {
            return $false
        } finally {
            $Client.Dispose()
        }
    }

    function Wait-StoryAudioReadiness([Diagnostics.Process]$Process, [string]$HostName, [int]$Port) {
        $Deadline = [DateTime]::UtcNow.AddSeconds(30)
        do {
            if ($Process.HasExited) {
                throw "Story Audio exited before production readiness was available."
            }
            try {
                $Readiness = Invoke-RestMethod -Uri "http://$HostName`:$Port/api/production/prepare-readiness" -TimeoutSec 2
                if ($Readiness.runtime_mode -eq "PRODUCTION" -and $Readiness.operator_authentication_verified) {
                    return
                }
            } catch {
                # The server may still be importing modules; retry until the bounded deadline.
            }
            Start-Sleep -Milliseconds 250
        } while ([DateTime]::UtcNow -lt $Deadline)
        throw "Story Audio did not reach verified production readiness within 30 seconds."
    }

    $ChildProcess = $null
    $InitialLaunch = $true
    while ($true) {
        if ($InitialLaunch -and (Test-StoryAudioPortOpen $ListenHost $ListenPort)) {
            throw "Port $ListenHost`:$ListenPort is already in use. Stop the stale runtime before using the production launcher."
        }
        $ChildProcess = Start-Process -FilePath $Python -ArgumentList (@("-m", "story_audio.main") + $LaunchArgs) -PassThru -WindowStyle Hidden
        Wait-StoryAudioReadiness $ChildProcess $ListenHost $ListenPort
        $ChildProcess.WaitForExit()
        $ChildProcess = $null
        $InitialLaunch = $false
        if (-not (Test-Path -LiteralPath $env:STORY_AUDIO_RESTART_SIGNAL)) {
            break
        }
        Remove-Item -LiteralPath $env:STORY_AUDIO_RESTART_SIGNAL -Force
        Start-Sleep -Milliseconds 500
    }
} finally {
    if ($ChildProcess -and -not $ChildProcess.HasExited) {
        Stop-Process -Id $ChildProcess.Id -Force
    }
    foreach ($Entry in $PreviousEnvironment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable(
            $Entry.Key,
            $Entry.Value,
            [EnvironmentVariableTarget]::Process
        )
    }
}
