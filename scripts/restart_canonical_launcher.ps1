param(
    [int]$Port = 8772,
    [int]$TimeoutSeconds = 75
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LauncherPath = Join-Path $RepositoryRoot "run_app.ps1"

function Get-ProcessRecord([int]$ProcessId) {
    Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId"
}

function Find-OwnedLauncher([int]$ChildProcessId) {
    $current = Get-ProcessRecord $ChildProcessId
    for ($depth = 0; $depth -lt 8 -and $current; $depth += 1) {
        if ($current.Name -ieq "powershell.exe" -and $current.CommandLine -like "*$LauncherPath*") {
            return $current
        }
        if (-not $current.ParentProcessId) { break }
        $current = Get-ProcessRecord ([int]$current.ParentProcessId)
    }
    return $null
}

function Wait-PortReleased([int]$ExpectedProcessId) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $listener) { return }
        if ([int]$listener.OwningProcess -ne $ExpectedProcessId) {
            throw "Port $Port changed owner during supervised restart."
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Canonical listener did not stop within $TimeoutSeconds seconds."
}

function Request-ApplicationShutdown {
    Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/runtime/restart" -Method Post -ContentType "application/json" -Body '{"confirmation":"RESTART_STORY_AUDIO"}' -TimeoutSec 5 | Out-Null
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $child = Get-ProcessRecord ([int]$listener.OwningProcess)
    if (-not $child -or $child.CommandLine -notlike "*-m story_audio.main*") {
        throw "Port $Port is not owned by a Story Audio application process."
    }
    $launcher = Find-OwnedLauncher ([int]$child.ProcessId)
    $runtime = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/runtime" -TimeoutSec 5
    if ($runtime.root -ne $RepositoryRoot -or -not $runtime.is_canonical_live_db) {
        throw "Port $Port does not expose the canonical Story Audio runtime."
    }
    if ($launcher) {
        # Target only the exact owned launcher. No broad process-name or force kill.
        Stop-Process -Id ([int]$launcher.ProcessId)
    }
    # Ask the verified application process to exit cleanly after its launcher
    # has stopped respawning it. This also recovers an orphaned supervised child.
    Request-ApplicationShutdown
    Wait-PortReleased ([int]$child.ProcessId)
}

$started = Get-Date
$launcherProcess = Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $LauncherPath,
    "--host", "127.0.0.1", "--port", "$Port"
) -PassThru -WindowStyle Hidden
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
do {
    try {
        $readiness = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/production/prepare-readiness" -TimeoutSec 3
        if ($readiness.runtime_mode -eq "PRODUCTION" -and $readiness.operator_authentication_verified) {
            [pscustomobject]@{
                launcher_pid = $launcherProcess.Id
                startup_ms = [int]((Get-Date) - $started).TotalMilliseconds
                runtime_mode = $readiness.runtime_mode
                authentication_verified = $readiness.operator_authentication_verified
                prepare_allowed = $readiness.prepare_allowed
                start_render_allowed = $readiness.start_render_allowed
                canonical_db_path_valid = $readiness.canonical_db_path_valid
                output_root_writable = $readiness.output_root_writable
            } | ConvertTo-Json -Compress
            exit 0
        }
    } catch {
        # The launcher may still be importing the app; wait within the bounded window.
    }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $deadline)

throw "Canonical launcher did not reach verified production readiness within $TimeoutSeconds seconds."
