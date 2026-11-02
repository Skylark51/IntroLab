$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
py -3 -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw "Python installation failed" }
py -3 -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller installation failed" }
py -3 -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
py -3 -m PyInstaller --noconfirm --clean --onefile --name IntroLab tools/launcher.py
if ($LASTEXITCODE -ne 0) { throw "Executable build failed" }
& .\dist\IntroLab.exe --help
if ($LASTEXITCODE -ne 0) { throw "Executable smoke test failed" }
Write-Host "Built: dist\IntroLab.exe"
