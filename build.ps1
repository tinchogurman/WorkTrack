# Reproducible build of WorkTrack for Windows.
# 1) runs the automated tests  2) regenerates the icon  3) builds dist\WorkTrack\WorkTrack.exe
# Usage (from the project folder):  powershell -ExecutionPolicy Bypass -File .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No se encontró .venv. Creá el entorno: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt" }

Write-Host "== Pruebas automatizadas ==" -ForegroundColor Cyan
& $python -m pytest -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { throw "Las pruebas fallaron: no se genera el ejecutable." }

Write-Host "== Ícono ==" -ForegroundColor Cyan
& $python tools\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "No se pudo generar el ícono." }

Write-Host "== PyInstaller ==" -ForegroundColor Cyan
& $python -m PyInstaller WorkTrack.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló." }

$exe = Join-Path $PSScriptRoot "dist\WorkTrack\WorkTrack.exe"
Write-Host "Listo: $exe" -ForegroundColor Green
