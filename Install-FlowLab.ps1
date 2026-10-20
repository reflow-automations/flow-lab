# Install shortcuts for this prepared local checkout. No admin rights required.
$ErrorActionPreference = 'Stop'
$flowRoot = $PSScriptRoot
$flowLauncher = Join-Path $flowRoot 'launcher.py'
$flowPython = Join-Path $flowRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $flowPython)) { throw 'Voer eerst Setup-FlowLab.ps1 uit.' }
if (-not (Test-Path -LiteralPath $flowLauncher)) { throw 'launcher.py ontbreekt.' }
$flowPowerShell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$flowPythonWindow = Join-Path $flowRoot '.venv/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $flowPythonWindow)) { throw 'De Python-windowlauncher ontbreekt. Voer Setup-FlowLab.ps1 uit.' }
$flowShell = New-Object -ComObject WScript.Shell
$flowArguments = '"' + $flowLauncher + '"'
$flowOldArguments = '-NoProfile -WindowStyle Hidden -File "' + (Join-Path $flowRoot 'Start-FlowLab.ps1') + '"'
$flowLinks = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Flow Lab.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'Flow Lab.lnk')
)
foreach ($flowPath in $flowLinks) {
    if (Test-Path -LiteralPath $flowPath) {
        $flowPrior = $flowShell.CreateShortcut($flowPath)
        $flowKnownOld = $flowPrior.TargetPath -eq $flowPowerShell -and $flowPrior.Arguments -eq $flowOldArguments
        $flowKnownNew = $flowPrior.TargetPath -eq $flowPythonWindow -and $flowPrior.Arguments -eq $flowArguments
        if (-not ($flowKnownOld -or $flowKnownNew)) {
            throw ('Er bestaat al een andere snelkoppeling: ' + $flowPath)
        }
    }
}
foreach ($flowPath in $flowLinks) {
    $flowLink = $flowShell.CreateShortcut($flowPath)
    $flowLink.TargetPath = $flowPythonWindow
    $flowLink.Arguments = $flowArguments
    $flowLink.WorkingDirectory = $flowRoot
    $flowLink.Description = 'Flow Lab - dicteren, snippets en woordenboek'
    $flowLink.WindowStyle = 7
    $flowLink.IconLocation = (Join-Path $flowRoot 'assets/brand/flow-lab.ico') + ',0'
    $flowLink.Save()
    $flowCheck = $flowShell.CreateShortcut($flowPath)
    if ($flowCheck.TargetPath -ne $flowPythonWindow -or $flowCheck.Arguments -ne $flowArguments) {
        throw ('Snelkoppeling kon niet worden gecontroleerd: ' + $flowPath)
    }
}
Write-Host 'Flow Lab staat nu op je bureaublad en in het Startmenu.'
Write-Host 'De app gebruikt deze projectmap. Verplaats of verwijder die map niet.'
