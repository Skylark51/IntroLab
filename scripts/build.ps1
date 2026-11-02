$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
py -3 -m pip install -e .
py -3 -m pip install pyinstaller
py -3 -m PyInstaller --noconfirm --clean --onefile --name IntroLab tools/launcher.py
Write-Host "Built: dist\IntroLab.exe"
