# Instala dependencias y crea un acceso directo en el Escritorio.
# Uso: clic derecho > Ejecutar con PowerShell
#   o: powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "main.py"))) {
    $Root = Split-Path -Parent $MyInvocation.MyCommand.Path
    $Root = Split-Path -Parent $Root
}

Set-Location $Root
Write-Host "Carpeta del programa: $Root"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "No se encontro Python. Instálalo desde https://www.python.org/downloads/"
    Write-Host "Marca 'Add python.exe to PATH' en el instalador."
    exit 1
}

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$venvPythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creando entorno virtual..."
    python -m venv .venv
}

Write-Host "Instalando librerias..."
& $venvPython -m pip install -r (Join-Path $Root "requirements.txt")

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "PDF a EPUB para Kobo.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $venvPythonw
$shortcut.Arguments = "`"$(Join-Path $Root 'main.py')`""
$shortcut.WorkingDirectory = $Root
$shortcut.WindowStyle = 1
$shortcut.Description = "Convierte PDF a EPUB para Kobo"
$shortcut.Save()

Write-Host ""
Write-Host "Listo. En el Escritorio tienes: PDF a EPUB para Kobo"
Write-Host "Doble click para abrir el programa."
