"""Explicit local runtime selection. Never downloads models or changes Windows policy."""
import hashlib
import json
import os
from pathlib import Path

MODEL='flow-lab-qwen:4b'

def ollama_spec(root,port):
    path=root/'data/local-runtime.json'
    if not path.exists():return None
    cfg=json.loads(path.read_text(encoding='utf-8'))
    if cfg.get('backend')!='ollama':raise RuntimeError('Onbekende lokale modelruntime.')
    exe=Path(cfg['executable'])
    if not exe.is_absolute() or not exe.is_file():raise RuntimeError('De ingestelde Ollama-installatie ontbreekt.')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=cfg.get('sha256'):
        raise RuntimeError('De lokale Ollama-installatie is gewijzigd. Controleer de installatie voor gebruik.')
    env=os.environ.copy()
    env.update(OLLAMA_HOST=f'127.0.0.1:{port}',OLLAMA_MODELS=str(root/'models/ollama'),
               OLLAMA_NO_CLOUD='1',OLLAMA_KEEP_ALIVE='30m',OLLAMA_NUM_PARALLEL='1',
               OLLAMA_ORIGINS=f'http://127.0.0.1:{port-2}')
    env.pop('OLLAMA_API_KEY',None)
    return {'exe':exe,'args':[str(exe),'serve'],'env':env,'model':MODEL,'health':'/api/version'}
