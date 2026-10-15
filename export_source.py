"""Create a source-only package from an explicit allowlist; never inspect secrets."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
from publication_guard import validate_public_files

ROOT=Path(__file__).resolve().parent
FILES='''README.md LICENSE THIRD_PARTY.md PUBLICATION.md .gitignore .env.example
.githooks/pre-commit .githooks/pre-push .github/workflows/checks.yml publication_guard.py test_publication.py
Setup-FlowLab.ps1 Install-FlowLab.ps1 Start-FlowLab.ps1 Start-FlowLab.cmd Start-FlowLab-Desktop.cmd Stop-FlowLab.ps1 assets/flow-lab.ico
app.py engines.py storage.py personalization.py dictionary.json
desktop_helper.py desktop_windows.py native_app.py shortcut_config.py dictation_gesture.py compact_overlay.py last_transcript.py
check_wispr_library.py setup_models.py model-lock.json requirements.lock.txt export_source.py
web/index.html web/app.js web/style.css web/recorder.js
pytest.ini conftest.py test_flow.py test_personalization.py test_desktop.py test_replay_import.py test_shortcuts.py test_gesture.py test_native_app.py test_recorder.cjs'''.split()

def build(destination=None):
    destination=Path(destination) if destination else ROOT/'releases/flow-lab-0.2.0-source.zip'
    contents={}
    for name in FILES:
        path=ROOT/name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Unsafe source path: '+name)
        data=path.read_bytes();text='' if name=='assets/flow-lab.ico' else data.decode('utf-8')
        if re.search(r'sk-(?:proj-)?[A-Za-z0-9_-]{24,}',text):raise ValueError('Credential-like text in '+name)
        if re.search(r'[A-Za-z]:[\\/](?:Users|prive coding folder)',text):raise ValueError('Personal absolute path in '+name)
        contents[name]=data
    if contents['.env.example'].decode('utf-8').splitlines()[-1]!='OPENAI_API_KEY=':
        raise ValueError('Environment example must have an empty key')
    errors=validate_public_files(contents,FILES)
    if errors:raise ValueError('\n'.join(errors))
    manifest={name:hashlib.sha256(data).hexdigest() for name,data in contents.items()}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in contents.items():z.writestr('flow-lab/'+name,data)
        z.writestr('flow-lab/SOURCE-MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(destination) as z:
        assert z.testzip() is None
        assert set(z.namelist())=={'flow-lab/'+n for n in contents}|{'flow-lab/SOURCE-MANIFEST.json'}
        for name,digest in manifest.items():assert hashlib.sha256(z.read('flow-lab/'+name)).hexdigest()==digest
    return {'archive':str(destination),'files':len(contents)+1,'bytes':destination.stat().st_size,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}

if __name__=='__main__':print(json.dumps(build(),indent=2))
