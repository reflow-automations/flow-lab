param([switch]$DownloadModels, [string]$PythonExe, [string]$OllamaPath)
$ErrorActionPreference = 'Stop'
$flowRoot = $PSScriptRoot
$flowPython = Join-Path $flowRoot '.venv/Scripts/python.exe'
Push-Location -LiteralPath $flowRoot
try {
    if (-not (Test-Path -LiteralPath $flowPython)) {
        if ($PythonExe) { & $PythonExe -m venv .venv } else { & py -3.12 -m venv .venv }
        if ($LASTEXITCODE -ne 0) { throw 'Installeer eerst CPython 3.12 (64-bit), inclusief Python Launcher en Tcl/Tk.' }
    }
    & $flowPython -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('pip') else 1)"
    if ($LASTEXITCODE -ne 0) {
        & $flowPython -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw 'pip ontbreekt. Herstel de project-Python voordat je verdergaat.' }
    }
    & $flowPython -m pip install -r (Join-Path $flowRoot 'requirements.lock.txt') -r (Join-Path $flowRoot 'requirements.asr-onnx.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Installatie van Python-pakketten is mislukt.' }
    & $flowPython -c 'import tkinter,comtypes,pystray,fastapi'
    if ($LASTEXITCODE -ne 0) { throw 'Een Python-onderdeel ontbreekt. Bekijk de foutmelding hierboven.' }
    Write-Host 'Python-onderdelen beschikbaar.'
    foreach ($folder in @('data','logs','results','recordings')) {
        New-Item -ItemType Directory -Path (Join-Path $flowRoot $folder) -Force | Out-Null
    }
    if ($DownloadModels) {
        $flowOllamaArgs = @()
        if ($OllamaPath) { $flowOllamaArgs = @('--ollama', $OllamaPath) }
        & $flowPython (Join-Path $flowRoot 'setup_ollama.py') --check @flowOllamaArgs
        if ($LASTEXITCODE -ne 0) { throw 'Ollama ontbreekt of de uitgeverscontrole faalde. Zie de melding hierboven.' }
        & $flowPython (Join-Path $flowRoot 'setup_models.py')
        if ($LASTEXITCODE -ne 0) { throw 'Niet alle modeldownloads zijn voltooid. Bekijk model-manifest.json.' }
        & $flowPython (Join-Path $flowRoot 'setup_asr_onnx.py') --enable
        if ($LASTEXITCODE -ne 0) { throw 'De gecontroleerde ONNX-spraakruntime is niet klaar.' }
        & $flowPython (Join-Path $flowRoot 'setup_ollama.py') @flowOllamaArgs
        if ($LASTEXITCODE -ne 0) { throw 'Lokale Qwen-opmaak is niet klaar. Bekijk de melding hierboven.' }
    }
    Write-Host 'Flow Lab-broncode voorbereid. Start met Start-FlowLab.cmd.'
    if (-not $DownloadModels) { Write-Host 'Voor lokale spraakherkenning: voer Setup-FlowLab.ps1 -DownloadModels uit.' }
} finally { Pop-Location }
