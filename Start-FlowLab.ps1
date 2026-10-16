param([switch]$DesktopOnly)
$ErrorActionPreference = 'Stop'
$flowPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$flowArguments = @((Join-Path $PSScriptRoot 'launcher.py'))
if ($DesktopOnly) { $flowArguments += '--desktop-only' }
& $flowPython @flowArguments
if ($LASTEXITCODE -ne 0) { throw 'Flow Lab kon niet starten. Bekijk logs/launcher-last-run.json.' }