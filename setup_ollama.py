"""Configure a signed installed Ollama for local Qwen, isolated from its global service."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import httpx
from local_runtime import MODEL,ollama_launch
from runtime_trust import verify_publisher

ROOT=Path(__file__).resolve().parent
QWEN='Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf'

def find_ollama(root,explicit=None):
    candidates=[]
    cfg=Path(root)/'data/local-runtime.json'
    if explicit:candidates.append(explicit)
    elif cfg.exists():candidates.append(json.loads(cfg.read_text(encoding='utf-8')).get('executable',''))
    candidates.extend([shutil.which('ollama') or '',str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Ollama/ollama.exe'),
                       str(Path(os.environ.get('ProgramFiles',''))/'Ollama/ollama.exe')])
    for value in candidates:
        path=Path(value)
        if path.is_file():
            verify_publisher(path,'CN=Ollama Inc.,');return path.resolve()
        if explicit:break
    raise RuntimeError('Installeer eerst de ondertekende Windows-versie van Ollama via https://ollama.com/download/windows. Voer daarna Setup-FlowLab.ps1 -DownloadModels opnieuw uit.')

def model_digest(root):
    lock=json.loads((Path(root)/'model-lock.json').read_text(encoding='utf-8'))
    return next(item['sha256'] for item in lock if item['file']==QWEN)

def model_ready(root,digest):
    root=Path(root);manifest=root/'models/ollama/manifests/registry.ollama.ai/library/flow-lab-qwen/4b'
    try:layers=json.loads(manifest.read_text(encoding='utf-8'))['layers']
    except (OSError,ValueError,KeyError):return False
    if not any(layer.get('mediaType')=='application/vnd.ollama.image.model' and layer.get('digest')=='sha256:'+digest for layer in layers):return False
    blob=root/'models/ollama/blobs'/('sha256-'+digest)
    if not blob.is_file():return False
    with blob.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()==digest

def setup(root=ROOT,explicit=None,check=False):
    root=Path(root);exe=find_ollama(root,explicit)
    if check:print('Ondertekende Ollama-installatie gevonden.');return
    digest=model_digest(root)
    if not model_ready(root,digest):
        model=root/'models'/QWEN
        if not model.is_file():raise RuntimeError('Qwen-model ontbreekt. Voer Setup-FlowLab.ps1 -DownloadModels uit.')
        with model.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=digest:raise RuntimeError('Qwen-modelhash klopt niet.')
        (root/'data').mkdir(exist_ok=True);(root/'logs').mkdir(exist_ok=True)
        modelfile=root/'data/ollama-install.Modelfile'
        modelfile.write_text('FROM '+json.dumps(model.resolve().as_posix(),ensure_ascii=False)+'\nPARAMETER num_ctx 8192\nPARAMETER temperature 0\n',encoding='utf-8')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        spec=ollama_launch(root,port,exe)
        with (root/'logs/ollama-install.log').open('ab') as log:
            proc=subprocess.Popen(spec['args'],env=spec['env'],stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                with httpx.Client(trust_env=False,timeout=1) as client:
                    end=time.monotonic()+30
                    while True:
                        if proc.poll() is not None:raise RuntimeError('Ollama-installatieserver stopte. Zie logs/ollama-install.log.')
                        try:
                            if client.get('http://127.0.0.1:'+str(port)+'/api/version').status_code==200:break
                        except httpx.HTTPError:pass
                        if time.monotonic()>end:raise RuntimeError('Ollama-installatieserver startte niet op tijd.')
                        time.sleep(.1)
                result=subprocess.run([str(exe),'create',MODEL,'-f',str(modelfile)],env=spec['env'],stdout=log,stderr=log,timeout=300,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode:raise RuntimeError('Qwen-import mislukt. Zie logs/ollama-install.log.')
            finally:
                proc.terminate();proc.wait(timeout=15)
        if not model_ready(root,digest):raise RuntimeError('Qwen-import kon niet worden bevestigd.')
    config={'backend':'ollama','executable':str(exe),'sha256':hashlib.sha256(exe.read_bytes()).hexdigest()}
    path=root/'data/local-runtime.json';path.parent.mkdir(exist_ok=True)
    if not path.exists() or json.loads(path.read_text(encoding='utf-8'))!=config:path.write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    print('Lokale Qwen via ondertekende Ollama geconfigureerd.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--ollama');parser.add_argument('--check',action='store_true');args=parser.parse_args();setup(explicit=args.ollama,check=args.check)
