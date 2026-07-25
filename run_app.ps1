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
    $env:STORY_AUDIO_ALLOW_LIVE_DB = "1"
    $LaunchArgs = @($args)
    if ($LaunchArgs.Count -eq 0) {
        $LaunchArgs = @("--host", "127.0.0.1", "--port", "8772")
    }
    & $Python -m story_audio.main @LaunchArgs
} finally {
    foreach ($Entry in $PreviousEnvironment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable(
            $Entry.Key,
            $Entry.Value,
            [EnvironmentVariableTarget]::Process
        )
    }
}
