param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryPath,

    [string]$HandoffRoot = 'D:\Youtube\_AI_HANDOFFS\Story Audio',
    [string]$Status = 'IN_PROGRESS',
    [string]$UpdatedBy,
    [string]$TechLeadModel,
    [string]$CurrentTask,
    [string]$CurrentPhase,
    [ValidateSet('VERIFIED', 'UNVERIFIED', 'NOT USED')]
    [string]$WorkerIdentity,
    [string]$WorkerProvider,
    [string]$WorkerModel,
    [string]$NextAction,
    [string]$ExpectedHead,
    [string]$LastTestCommand,
    [string]$LastTestStatus,
    [string]$LastTestSummary,
    [string]$LastTestDuration,
    [string]$TemplatePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Utf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Content
    )
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Read-Utf8File {
    param([Parameter(Mandatory = $true)][string]$Path)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    return [System.IO.File]::ReadAllText($Path, $encoding)
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string]$Repo,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [int[]]$AllowedExitCodes = @(0)
    )
    function Quote-ProcessArgument {
        param([AllowEmptyString()][string]$Value)
        if ($Value -notmatch '[\s"]') {
            return $Value
        }
        return '"' + ($Value -replace '"', '\"') + '"'
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'git'
    $allArguments = @('-C', $Repo) + $Arguments
    $psi.Arguments = (($allArguments | ForEach-Object { Quote-ProcessArgument -Value $_ }) -join ' ')
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $psi
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    $exitCode = $process.ExitCode
    if ($AllowedExitCodes -notcontains $exitCode) {
        $detail = ($stdout + "`n" + $stderr).Trim()
        throw "git $($Arguments -join ' ') failed with exit code $exitCode. $detail"
    }
    return $stdout
}

function New-UniqueDirectory {
    param([Parameter(Mandatory = $true)][string]$Parent)
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
    for ($i = 0; $i -lt 1000; $i++) {
        $name = if ($i -eq 0) { $stamp } else { '{0}_{1:000}' -f $stamp, $i }
        $candidate = Join-Path $Parent $name
        if (-not (Test-Path -LiteralPath $candidate)) {
            New-Item -ItemType Directory -Path $candidate | Out-Null
            return $candidate
        }
    }
    throw "Unable to create unique history directory under $Parent"
}

function Format-ListBlock {
    param(
        [AllowEmptyString()][string]$Text,
        [string]$Empty = 'none'
    )
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return "- $Empty"
    }
    $items = @($Text -split "`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($items.Count -eq 0) {
        return "- $Empty"
    }
    return (($items | ForEach-Object { "- $_" }) -join "`n")
}

function Get-WorktreeSummary {
    param([AllowEmptyString()][string]$Porcelain)
    if ([string]::IsNullOrWhiteSpace($Porcelain)) {
        return 'clean'
    }
    $lines = @($Porcelain -split "`n" | Where-Object { $_ -ne '' })
    return "dirty ($($lines.Count) porcelain entr$(if ($lines.Count -eq 1) { 'y' } else { 'ies' }))"
}

function Test-SuspiciousPatch {
    param([AllowEmptyString()][string]$Patch)
    $categories = New-Object System.Collections.Generic.List[string]
    if ([string]::IsNullOrEmpty($Patch)) {
        return $categories
    }

    $checks = @(
        @{ Name = 'API_KEY'; Pattern = '(?im)^\+.*\b(api[_-]?key|apikey)\b\s*[:=]\s*["'']?[^"'',\s]{8,}' },
        @{ Name = 'AUTHORIZATION_HEADER'; Pattern = '(?im)^\+.*\bauthorization\b\s*:\s*[^,\s].+' },
        @{ Name = 'BEARER_TOKEN'; Pattern = '(?im)^\+.*\bbearer\s+[A-Za-z0-9._~+/-]{16,}' },
        @{ Name = 'ACCESS_OR_REFRESH_TOKEN'; Pattern = '(?im)^\+.*\b(access|refresh)[_-]?token\b\s*[:=]\s*["'']?[^"'',\s]{12,}' },
        @{ Name = 'CLIENT_SECRET'; Pattern = '(?im)^\+.*\bclient[_-]?secret\b\s*[:=]\s*["'']?[^"'',\s]{8,}' },
        @{ Name = 'PASSWORD'; Pattern = '(?im)^\+.*\b(password|passwd|pwd)\b\s*[:=]\s*["'']?[^"'',\s]{6,}' },
        @{ Name = 'AWS_ACCESS_KEY_ID'; Pattern = '(?m)^\+.*\b(AKIA|ASIA)[A-Z0-9]{16}\b' },
        @{ Name = 'AWS_SECRET_KEY'; Pattern = '(?im)^\+.*\baws(.{0,20})?(secret|private)(.{0,20})?key\b\s*[:=]\s*["'']?[A-Za-z0-9/+=]{30,}' },
        @{ Name = 'OPENAI_KEY'; Pattern = '(?m)^\+.*\bsk-[A-Za-z0-9_-]{20,}\b' },
        @{ Name = 'GITHUB_TOKEN'; Pattern = '(?m)^\+.*\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b' },
        @{ Name = 'SLACK_TOKEN'; Pattern = '(?m)^\+.*\bxox[baprs]-[A-Za-z0-9-]{10,}\b' },
        @{ Name = 'JWT'; Pattern = '(?m)^\+.*\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b' },
        @{ Name = 'COOKIE'; Pattern = '(?im)^\+.*\bcookie\b\s*[:=]\s*[^,\s].+' },
        @{ Name = 'GENERIC_SECRET'; Pattern = '(?im)^\+.*\b(secret|token)\b\s*[:=]\s*["'']?[^"'',\s]{12,}' }
    )

    foreach ($check in $checks) {
        if ($Patch -match $check.Pattern) {
            $categories.Add($check.Name)
        }
    }
    return $categories
}

function Copy-IfExists {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        Copy-Item -LiteralPath $Source -Destination $Destination
    }
}

function Remove-ActiveFiles {
    param([Parameter(Mandatory = $true)][string]$Root)
    $names = @(
        'ACTIVE_TASK.md',
        'GIT_STATE.txt',
        'LAST_TEST_RESULT.txt',
        'ACTIVE_WORKTREE.patch',
        'ACTIVE_WORKTREE.patch.status'
    )
    foreach ($name in $names) {
        $path = Join-Path $Root $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Remove-Item -LiteralPath $path
        }
    }
}

function Publish-ActiveFiles {
    param(
        [Parameter(Mandatory = $true)][string]$TempDir,
        [Parameter(Mandatory = $true)][string]$Root
    )
    Remove-ActiveFiles -Root $Root
    foreach ($item in Get-ChildItem -LiteralPath $TempDir -File) {
        Move-Item -LiteralPath $item.FullName -Destination (Join-Path $Root $item.Name)
    }
}

$tempDir = $null
$historySnapshot = 'none'
$createdFiles = New-Object System.Collections.Generic.List[string]

try {
    $repoFullPath = [System.IO.Path]::GetFullPath($RepositoryPath)
    if (-not (Test-Path -LiteralPath $repoFullPath -PathType Container)) {
        throw "RepositoryPath does not exist or is not a directory: $repoFullPath"
    }

    $handoffFullPath = [System.IO.Path]::GetFullPath($HandoffRoot)
    if ($handoffFullPath.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar).Equals($repoFullPath.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar), [System.StringComparison]::OrdinalIgnoreCase) -or
        $handoffFullPath.StartsWith($repoFullPath.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'HandoffRoot must be outside RepositoryPath.'
    }

    if ([string]::IsNullOrWhiteSpace($TemplatePath)) {
        $TemplatePath = Join-Path $repoFullPath 'docs\AI_ACTIVE_TASK_TEMPLATE.md'
    }
    $templateFullPath = [System.IO.Path]::GetFullPath($TemplatePath)
    if (-not (Test-Path -LiteralPath $templateFullPath -PathType Leaf)) {
        throw "TemplatePath does not exist: $templateFullPath"
    }

    Invoke-Git -Repo $repoFullPath -Arguments @('rev-parse', '--is-inside-work-tree') | Out-Null
    $branch = (Invoke-Git -Repo $repoFullPath -Arguments @('branch', '--show-current')).Trim()
    if ([string]::IsNullOrWhiteSpace($branch)) {
        $branch = '(detached)'
    }
    $head = (Invoke-Git -Repo $repoFullPath -Arguments @('rev-parse', 'HEAD')).Trim()
    $subject = (Invoke-Git -Repo $repoFullPath -Arguments @('log', '-1', '--pretty=%s')).Trim()

    if (-not [string]::IsNullOrWhiteSpace($ExpectedHead) -and $ExpectedHead.Trim() -ne $head) {
        throw "ExpectedHead mismatch. expected=$($ExpectedHead.Trim()) actual=$head"
    }

    $porcelain = Invoke-Git -Repo $repoFullPath -Arguments @('status', '--porcelain=v1')
    $trackedModified = Invoke-Git -Repo $repoFullPath -Arguments @('diff', '--name-only', 'HEAD', '--')
    $stagedTracked = Invoke-Git -Repo $repoFullPath -Arguments @('diff', '--name-only', '--cached', 'HEAD', '--')
    $trackedAll = @()
    foreach ($line in (($trackedModified + "`n" + $stagedTracked) -split "`n")) {
        if (-not [string]::IsNullOrWhiteSpace($line) -and $trackedAll -notcontains $line) {
            $trackedAll += $line
        }
    }
    $trackedAllText = $trackedAll -join "`n"
    $untracked = Invoke-Git -Repo $repoFullPath -Arguments @('ls-files', '--others', '--exclude-standard')
    $diffStat = Invoke-Git -Repo $repoFullPath -Arguments @('diff', '--stat', 'HEAD', '--')
    $diffNumstat = Invoke-Git -Repo $repoFullPath -Arguments @('diff', '--numstat', 'HEAD', '--')
    $cachedPatch = Invoke-Git -Repo $repoFullPath -Arguments @('diff', '--binary', '--cached', 'HEAD', '--')
    $unstagedPatch = Invoke-Git -Repo $repoFullPath -Arguments @('diff', '--binary', '--')
    $patch = $cachedPatch
    if (-not [string]::IsNullOrEmpty($patch) -and -not [string]::IsNullOrEmpty($unstagedPatch)) {
        $patch += "`n"
    }
    $patch += $unstagedPatch

    $secretCategories = @(Test-SuspiciousPatch -Patch $patch)
    $patchStatus = if ($secretCategories.Count -gt 0) {
        'WITHHELD_SUSPECTED_SECRET: ' + (($secretCategories | Sort-Object -Unique) -join ', ')
    } elseif ([string]::IsNullOrEmpty($patch)) {
        'SAFE_EMPTY'
    } else {
        'SAFE_CAPTURED'
    }

    New-Item -ItemType Directory -Path $handoffFullPath -Force | Out-Null
    $historyRoot = Join-Path $handoffFullPath 'HISTORY'
    New-Item -ItemType Directory -Path $historyRoot -Force | Out-Null
    $tempDir = Join-Path $handoffFullPath ('.tmp_capture_' + [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempDir | Out-Null

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'
    $worktreeSummary = Get-WorktreeSummary -Porcelain $porcelain
    $untrackedCount = if ([string]::IsNullOrWhiteSpace($untracked)) { 0 } else { @($untracked -split "`n" | Where-Object { $_ -ne '' }).Count }
    $safeUpdatedBy = if ([string]::IsNullOrWhiteSpace($UpdatedBy)) { 'UNSPECIFIED' } else { $UpdatedBy }
    $safeTechLeadModel = if ([string]::IsNullOrWhiteSpace($TechLeadModel)) { 'UNSPECIFIED' } else { $TechLeadModel }
    $safeTask = if ([string]::IsNullOrWhiteSpace($CurrentTask)) { 'UNSPECIFIED' } else { $CurrentTask }
    $safePhase = if ([string]::IsNullOrWhiteSpace($CurrentPhase)) { 'UNSPECIFIED' } else { $CurrentPhase }
    $safeWorkerIdentity = if ([string]::IsNullOrWhiteSpace($WorkerIdentity)) { 'UNSPECIFIED' } else { $WorkerIdentity }
    $safeWorkerProvider = if ([string]::IsNullOrWhiteSpace($WorkerProvider)) { 'UNSPECIFIED' } else { $WorkerProvider }
    $safeWorkerModel = if ([string]::IsNullOrWhiteSpace($WorkerModel)) { 'UNSPECIFIED' } else { $WorkerModel }
    $safeNextAction = if ([string]::IsNullOrWhiteSpace($NextAction)) { 'UNSPECIFIED' } else { $NextAction }
    $safeLastTestStatus = if ([string]::IsNullOrWhiteSpace($LastTestStatus)) { 'UNSPECIFIED' } else { $LastTestStatus }
    $safeLastTestSummary = if ([string]::IsNullOrWhiteSpace($LastTestSummary)) { 'UNSPECIFIED' } else { $LastTestSummary }
    $bt = [char]96
    $fence = '```'

    $managedBlock = @"
<!-- AI-HANDOFF-AUTO-START -->
## Managed Handoff Snapshot

- Timestamp: $bt$timestamp$bt
- Status: $bt$Status$bt
- Updated by: $bt$safeUpdatedBy$bt
- Tech Lead model: $bt$safeTechLeadModel$bt
- Repository path: $bt$repoFullPath$bt
- Current task: $bt$safeTask$bt
- Current phase: $bt$safePhase$bt
- Worker identity: $bt$safeWorkerIdentity$bt
- Worker provider: $bt$safeWorkerProvider$bt
- Worker model: $bt$safeWorkerModel$bt
- Branch: $bt$branch$bt
- HEAD: $bt$head$bt
- Subject: $bt$subject$bt
- Worktree summary: $bt$worktreeSummary$bt
- Modified tracked files:
$(Format-ListBlock -Text $trackedAllText)
- Untracked filename count: $bt$untrackedCount$bt
- Diff stat:

$($fence)text
$diffStat
$fence

- Patch status: $bt$patchStatus$bt
- Last test status: $bt$safeLastTestStatus$bt
- Last test summary: $bt$safeLastTestSummary$bt
- Next action: $bt$safeNextAction$bt
<!-- AI-HANDOFF-AUTO-END -->
"@

    $activeTaskPath = Join-Path $handoffFullPath 'ACTIVE_TASK.md'
    $template = Read-Utf8File -Path $templateFullPath
    if (Test-Path -LiteralPath $activeTaskPath -PathType Leaf) {
        $existing = Read-Utf8File -Path $activeTaskPath
        $pattern = '(?s)<!-- AI-HANDOFF-AUTO-START -->.*?<!-- AI-HANDOFF-AUTO-END -->'
        if ($existing -match $pattern) {
            $activeTask = [regex]::Replace($existing, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $managedBlock }, 1)
        } else {
            $activeTask = $managedBlock + "`n`n" + $existing
        }
    } else {
        $activeTask = $managedBlock + "`n`n" + $template
    }

    $gitState = @"
Timestamp: $timestamp
Repository: $repoFullPath
Branch: $branch
HEAD: $head
Subject: $subject
ExpectedHead check: $(if ([string]::IsNullOrWhiteSpace($ExpectedHead)) { 'not supplied' } else { 'matched' })
Worktree summary: $worktreeSummary

Porcelain status:
```text
$porcelain
```

Tracked modified filenames:
```text
$trackedAllText
```

Untracked filenames:
```text
$untracked
```

Diff stat:
```text
$diffStat
```

Diff numstat:
```text
$diffNumstat
```

Patch status: $patchStatus
"@

    $lastTest = @"
Timestamp: $timestamp
Command: $(if ([string]::IsNullOrWhiteSpace($LastTestCommand)) { 'UNSPECIFIED' } else { $LastTestCommand })
Status: $(if ([string]::IsNullOrWhiteSpace($LastTestStatus)) { 'UNSPECIFIED' } else { $LastTestStatus })
Summary: $(if ([string]::IsNullOrWhiteSpace($LastTestSummary)) { 'UNSPECIFIED' } else { $LastTestSummary })
Duration: $(if ([string]::IsNullOrWhiteSpace($LastTestDuration)) { 'UNSPECIFIED' } else { $LastTestDuration })
"@

    Write-Utf8File -Path (Join-Path $tempDir 'ACTIVE_TASK.md') -Content $activeTask
    Write-Utf8File -Path (Join-Path $tempDir 'GIT_STATE.txt') -Content $gitState
    Write-Utf8File -Path (Join-Path $tempDir 'LAST_TEST_RESULT.txt') -Content $lastTest
    if ($patchStatus -like 'WITHHELD_SUSPECTED_SECRET*') {
        Write-Utf8File -Path (Join-Path $tempDir 'ACTIVE_WORKTREE.patch.status') -Content "Patch status: $patchStatus`nPatch withheld because suspicious secret categories were detected. Values are intentionally omitted.`n"
    } else {
        Write-Utf8File -Path (Join-Path $tempDir 'ACTIVE_WORKTREE.patch') -Content $patch
    }

    $activeNames = @('ACTIVE_TASK.md', 'GIT_STATE.txt', 'LAST_TEST_RESULT.txt', 'ACTIVE_WORKTREE.patch', 'ACTIVE_WORKTREE.patch.status')
    $previousExists = $false
    foreach ($name in $activeNames) {
        if (Test-Path -LiteralPath (Join-Path $handoffFullPath $name) -PathType Leaf) {
            $previousExists = $true
        }
    }
    if ($previousExists) {
        $historySnapshot = New-UniqueDirectory -Parent $historyRoot
        foreach ($name in $activeNames) {
            Copy-IfExists -Source (Join-Path $handoffFullPath $name) -Destination (Join-Path $historySnapshot $name)
        }
    }

    Publish-ActiveFiles -TempDir $tempDir -Root $handoffFullPath
    Remove-Item -LiteralPath $tempDir -Recurse -Force
    $tempDir = $null

    foreach ($name in $activeNames) {
        if (Test-Path -LiteralPath (Join-Path $handoffFullPath $name) -PathType Leaf) {
            $createdFiles.Add($name)
        }
    }

    Write-Host "SUCCESS capture complete"
    Write-Host "Repository: $repoFullPath"
    Write-Host "HEAD: $head"
    Write-Host "HandoffRoot: $handoffFullPath"
    Write-Host "PatchStatus: $patchStatus"
    Write-Host "HistorySnapshot: $historySnapshot"
    Write-Host "ActiveFiles: $($createdFiles -join ', ')"
    exit 0
} catch {
    if ($null -ne $tempDir -and (Test-Path -LiteralPath $tempDir)) {
        Remove-Item -LiteralPath $tempDir -Recurse -Force
    }
    Write-Error "FAILED capture_ai_handoff: $($_.Exception.Message)"
    exit 1
}
