param([switch]$DesktopOnly)
$ErrorActionPreference = 'Stop'
$env:FLOW_LAB_PORT = '17865'
$flowRoot = $PSScriptRoot
$flowReady = $false
try {
    $flowStatus = Invoke-RestMethod 'http://127.0.0.1:17865/api/status' -TimeoutSec 2
    if ($flowStatus.app -ne 'flow-lab') { throw 'Poort 17865 wordt gebruikt door een ander programma.' }
    $flowReady = $true
} catch { }
if (-not $flowReady) {
    New-Item -ItemType Directory -Path (Join-Path $flowRoot 'logs') -Force | Out-Null
    $flowPython = Join-Path $flowRoot '.venv/Scripts/python.exe'
    $flowProcess = Start-Process -FilePath $flowPython -ArgumentList '-m uvicorn app:app --host 127.0.0.1 --port 17865 --no-access-log' -WorkingDirectory $flowRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $flowRoot 'logs/app-17865.stdout.log') -RedirectStandardError (Join-Path $flowRoot 'logs/app-17865.stderr.log')
    $flowProcess.Id | Set-Content -LiteralPath (Join-Path $flowRoot 'logs/app-17865.pid') -Encoding ascii
    for ($flowAttempt = 0; $flowAttempt -lt 30; $flowAttempt++) {
        try { $flowStatus = Invoke-RestMethod 'http://127.0.0.1:17865/api/status' -TimeoutSec 1; if ($flowStatus.app -eq 'flow-lab') { $flowReady = $true; break } } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $flowReady) { throw 'Flow Lab startte niet. Bekijk logs/app-17865.stderr.log.' }
}
$flowDesktopScript = Join-Path $flowRoot 'desktop_helper.py'
$flowPython = Join-Path $flowRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $flowDesktopScript) {
    $flowDesktopState = & $flowPython $flowDesktopScript --status
    if ($flowDesktopState -eq 'not_running' -or -not $flowDesktopState) {
        $flowDesktop = Start-Process -FilePath $flowPython -ArgumentList ('"' + $flowDesktopScript + '"') -WorkingDirectory $flowRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $flowRoot 'logs/desktop.stdout.log') -RedirectStandardError (Join-Path $flowRoot 'logs/desktop.stderr.log')
        $flowDesktop.Id | Set-Content -LiteralPath (Join-Path $flowRoot 'logs/desktop.pid') -Encoding ascii
    }
}
if (-not $DesktopOnly) {
    for ($flowWait=0; $flowWait -lt 20; $flowWait++) {
        $flowDesktopState = & $flowPython $flowDesktopScript --status
        if ($flowDesktopState -and $flowDesktopState -ne 'not_running') { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $flowDesktopState -or $flowDesktopState -eq 'not_running') { throw 'Flow Lab-venster kon niet starten. Bekijk logs/desktop.stderr.log.' }
    & $flowPython $flowDesktopScript --open
}
New-Item -ItemType Directory -Path (Join-Path $flowRoot 'logs') -Force | Out-Null
$flowLaunchReadback = @{
    launched_at_utc = [DateTime]::UtcNow.ToString('o')
    server_ready = $flowReady
    browser_requested = $false
    native_window_requested = -not [bool]$DesktopOnly
}
[System.IO.File]::WriteAllText((Join-Path $flowRoot 'logs/launcher-last-run.json'),($flowLaunchReadback | ConvertTo-Json),[System.Text.UTF8Encoding]::new($false))
