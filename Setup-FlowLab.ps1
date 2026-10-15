param([switch]$DownloadModels)
$ErrorActionPreference = 'Stop'
$flowRoot = $PSScriptRoot
$flowPython = Join-Path $flowRoot '.venv/Scripts/python.exe'
Push-Location -LiteralPath $flowRoot
try {
    if (-not (Test-Path -LiteralPath $flowPython)) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Installeer eerst CPython 3.12 (64-bit), inclusief Python Launcher en Tcl/Tk.' }
    }
    & $flowPython -m pip install -r (Join-Path $flowRoot 'requirements.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Installatie van Python-pakketten is mislukt.' }
    & $flowPython -c 'import tkinter,comtypes,pystray,fastapi'
    if ($LASTEXITCODE -ne 0) { throw 'Een Python-onderdeel ontbreekt. Bekijk de foutmelding hierboven.' }
    Write-Host 'Python-onderdelen beschikbaar.'
    foreach ($folder in @('data','logs','results','recordings')) {
        New-Item -ItemType Directory -Path (Join-Path $flowRoot $folder) -Force | Out-Null
    }
    if ($DownloadModels) {
        & $flowPython (Join-Path $flowRoot 'setup_models.py')
        if ($LASTEXITCODE -ne 0) { throw 'Niet alle modeldownloads zijn voltooid. Bekijk model-manifest.json.' }
    }
    Write-Host 'Flow Lab-broncode voorbereid. Start met Start-FlowLab.cmd.'
    if (-not $DownloadModels) { Write-Host 'Voor lokale spraakherkenning: voer Setup-FlowLab.ps1 -DownloadModels uit.' }
} finally { Pop-Location }
