"""Read Windows publisher signatures; never change trust or execution policy."""
import base64
from pathlib import Path
import shutil
import subprocess
import sys

def verify_publisher(path,publisher):
    if sys.platform!='win32':raise RuntimeError('Deze installatiecontrole vereist Windows.')
    path=Path(path)
    literal=str(path).replace("'","''");subject=publisher.replace("'","''")
    select="Get-ChildItem -LiteralPath '"+literal+"' -File | Where-Object { $_.Extension -in '.dll','.pyd' }" if path.is_dir() else "Get-Item -LiteralPath '"+literal+"'"
    command=("$ErrorActionPreference='Stop'; $files=@("+select+"); if ($files.Count -eq 0) { throw 'Geen bestanden' }; "
             "$files | ForEach-Object { $s=Get-AuthenticodeSignature -LiteralPath $_.FullName; "
             "if ($s.Status -ne 'Valid' -or -not $s.SignerCertificate.Subject.StartsWith('"+subject+"')) { throw 'Uitgeversignatuur niet geldig' } }")
    encoded=base64.b64encode(command.encode('utf-16le')).decode('ascii')
    shell=shutil.which('pwsh') or 'powershell.exe'
    result=subprocess.run([shell,'-NoProfile','-NonInteractive','-EncodedCommand',encoded],capture_output=True,timeout=60)
    if result.returncode:raise RuntimeError('Geldige handtekening van '+publisher+' kon niet worden bevestigd. Installatie gestopt.')
