# Install shortcuts for this prepared local checkout. No admin rights required.
$ErrorActionPreference = 'Stop'
$flowRoot = $PSScriptRoot
$flowLauncher = Join-Path $flowRoot 'Start-FlowLab.ps1'
$flowPython = Join-Path $flowRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $flowPython)) { throw 'Voer eerst Setup-FlowLab.ps1 uit.' }
if (-not (Test-Path -LiteralPath $flowLauncher)) { throw 'Start-FlowLab.ps1 ontbreekt.' }
$flowPowerShell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$flowShell = New-Object -ComObject WScript.Shell
$flowArguments = '-NoProfile -WindowStyle Hidden -File "' + $flowLauncher + '"'
$flowLinks = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Flow Lab.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'Flow Lab.lnk')
)
foreach ($flowPath in $flowLinks) {
    if (Test-Path -LiteralPath $flowPath) {
        $flowPrior = $flowShell.CreateShortcut($flowPath)
        if ($flowPrior.TargetPath -ne $flowPowerShell -or $flowPrior.Arguments -ne $flowArguments) {
            throw ('Er bestaat al een andere snelkoppeling: ' + $flowPath)
        }
    }
}
foreach ($flowPath in $flowLinks) {
    $flowLink = $flowShell.CreateShortcut($flowPath)
    $flowLink.TargetPath = $flowPowerShell
    $flowLink.Arguments = $flowArguments
    $flowLink.WorkingDirectory = $flowRoot
    $flowLink.Description = 'Flow Lab - dicteren, snippets en woordenboek'
    $flowLink.WindowStyle = 7
    $flowLink.IconLocation = (Join-Path $flowRoot 'assets/flow-lab.ico') + ',0'
    $flowLink.Save()
    $flowCheck = $flowShell.CreateShortcut($flowPath)
    if ($flowCheck.TargetPath -ne $flowPowerShell -or $flowCheck.Arguments -ne $flowArguments) {
        throw ('Snelkoppeling kon niet worden gecontroleerd: ' + $flowPath)
    }
}
Write-Host 'Flow Lab staat nu op je bureaublad en in het Startmenu.'
Write-Host 'De app gebruikt deze projectmap. Verplaats of verwijder die map niet.'
