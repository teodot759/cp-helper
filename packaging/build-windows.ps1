# Build C++ Helper on Windows.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build-windows.ps1
#
# Produces dist\CppHelper\CppHelper.exe. Run installer.iss with Inno Setup 6
# afterwards to get a per-user installer.

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    .venv\Scripts\pip install -e .
}

.venv\Scripts\python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    .venv\Scripts\pip install pyinstaller
}

.venv\Scripts\pyinstaller packaging\cpp-helper.spec --noconfirm --clean
Write-Host "Built: $PWD\dist\CppHelper\CppHelper.exe"

$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    & $iscc "packaging\installer.iss"
    Write-Host "Installer: $PWD\dist\installer\CppHelper-Setup.exe"
} else {
    Write-Host "Inno Setup not found; skipping installer."
}
