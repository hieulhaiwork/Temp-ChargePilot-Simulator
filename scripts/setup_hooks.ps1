# Install git pre-push hook for AI log submission (Windows PowerShell).
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir

# Support git worktrees by querying git for the hooks directory
$GitHookDir = git -C $RepoRoot rev-parse --git-path hooks 2>$null
if ($GitHookDir -and $LASTEXITCODE -eq 0) {
    if ([System.IO.Path]::IsPathRooted($GitHookDir)) {
        $HookDir = $GitHookDir
    } else {
        $HookDir = Join-Path $RepoRoot $GitHookDir
    }
} else {
    $HookDir = Join-Path $RepoRoot '.git\hooks'
}
$HookFile = Join-Path $HookDir 'pre-push'

if (-not (Test-Path $HookDir) -and -not (Test-Path (Join-Path $RepoRoot '.git'))) {
    Write-Error "[ai-log] Error: No .git or hooks directory found at $RepoRoot"
    exit 1
}

if (-not (Test-Path $HookDir)) {
    New-Item -ItemType Directory -Path $HookDir -Force | Out-Null
}

# Git on Windows runs hooks via Git Bash, so the hook body must be bash without BOM and with LF endings.
$HookBody = "#!/usr/bin/env bash`n# Pre-push: sweep recent Antigravity / Gemini prompts, then submit AI logs.`nREPO_ROOT=`"`$(git rev-parse --show-toplevel 2>/dev/null || pwd)`"`nbash `"`$REPO_ROOT/scripts/_pyrun.sh`" `"`$REPO_ROOT/scripts/log_antigravity.py`" --auto || true`nbash `"`$REPO_ROOT/scripts/_pyrun.sh`" `"`$REPO_ROOT/scripts/submit_log.py`" || true`nexit 0`n"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllBytes($HookFile, $Utf8NoBom.GetBytes($HookBody))
Write-Host "[ai-log] Git pre-push hook installed at $HookFile (LF, no BOM)."

$AiLogDir = Join-Path $RepoRoot '.ai-log'
if (-not (Test-Path $AiLogDir)) { New-Item -ItemType Directory -Path $AiLogDir | Out-Null }
if (-not (Test-Path (Join-Path $AiLogDir '.gitkeep'))) { New-Item -ItemType File -Path (Join-Path $AiLogDir '.gitkeep') | Out-Null }

Write-Host "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
