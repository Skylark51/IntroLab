param([switch]$BuildExe)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path .git)) { throw "Run this script from a git-cloned IntroLab repository." }
$status = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw "git status failed" }
if ($status) { throw "Uncommitted changes detected: commit or stash them before updating." }
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw "git pull failed" }
py -3 -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw "Python installation failed" }
if ($BuildExe) { & "$PSScriptRoot\build.ps1" }
Write-Host "IntroLab updated. Local .introlab database is preserved."
