param([switch]$SkipHelper)
$ErrorActionPreference = 'Stop'
$flowRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path.TrimEnd('\') + '\'
$flowDesktopScript = Join-Path $PSScriptRoot 'desktop_helper.py'
if (-not $SkipHelper -and (Test-Path -LiteralPath $flowDesktopScript)) {
    & (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') $flowDesktopScript --quit | Out-Null
}
$flowPidFile = Join-Path $PSScriptRoot 'logs/app-17865.pid'
if (-not (Test-Path -LiteralPath $flowPidFile)) { return }
$flowPid = [int](Get-Content -LiteralPath $flowPidFile -Encoding ascii)
$flowProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $flowPid"
if (-not $flowProcess) { return }
$flowExpected = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if ($flowProcess.ExecutablePath -ne $flowExpected.Replace('/','\') -or $flowProcess.CommandLine -notmatch 'uvicorn app:app.*17865') {
    throw 'Het opgeslagen proces is niet de verwachte Flow Lab-server. Niets gestopt.'
}
$flowSnapshot = @(Get-CimInstance Win32_Process)
$flowOwned = [System.Collections.Generic.List[int]]::new()
$flowOwned.Add($flowPid)
for ($depth = 0; $depth -lt 4; $depth++) {
    foreach ($child in $flowSnapshot) {
        if ($flowOwned.Contains([int]$child.ProcessId) -or -not $flowOwned.Contains([int]$child.ParentProcessId)) { continue }
        $native = $child.ExecutablePath -and $child.ExecutablePath.StartsWith($flowRoot,[System.StringComparison]::OrdinalIgnoreCase) -and $child.Name -in @('nemo-speech.exe','llama-server.exe','whisper-server.exe')
        $interpreter = $child.Name -eq 'python.exe' -and $child.CommandLine -match 'uvicorn app:app.*17865'
        if ($native -or $interpreter) { $flowOwned.Add([int]$child.ProcessId) }
    }
}
for ($index = $flowOwned.Count - 1; $index -ge 0; $index--) { Stop-Process -Id $flowOwned[$index] -ErrorAction SilentlyContinue }
$flowStopReadback=@{stopped_at_utc=[DateTime]::UtcNow.ToString('o');owned_pids=@($flowOwned);requested_port=17865}
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'logs/stop-last-run.json'),($flowStopReadback | ConvertTo-Json),[System.Text.UTF8Encoding]::new($false))
