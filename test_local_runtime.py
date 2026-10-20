import hashlib,json
import pytest
from local_runtime import ollama_spec

def test_default_keeps_existing_runtime(tmp_path):assert ollama_spec(tmp_path,17867) is None

def test_explicit_runtime_is_local_and_pinned(tmp_path,monkeypatch):
    exe=tmp_path/'ollama.exe';exe.write_bytes(b'fixture');(tmp_path/'data').mkdir()
    (tmp_path/'data/local-runtime.json').write_text(json.dumps({'backend':'ollama','executable':str(exe),'sha256':hashlib.sha256(b'fixture').hexdigest()}),encoding='utf-8')
    monkeypatch.setenv('OLLAMA_API_KEY','not-a-real-secret')
    s=ollama_spec(tmp_path,17867)
    assert s['env']['OLLAMA_HOST']=='127.0.0.1:17867' and s['env']['OLLAMA_NO_CLOUD']=='1'
    assert 'OLLAMA_API_KEY' not in s['env'] and s['model']=='flow-lab-qwen:4b'
    exe.write_bytes(b'changed')
    with pytest.raises(RuntimeError,match='gewijzigd'):ollama_spec(tmp_path,17867)
