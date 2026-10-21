import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
import setup_models
import setup_ollama
import setup_asr_onnx

def cache_fixture(root,ready=True):
    model=root/'models'/setup_ollama.QWEN;model.parent.mkdir();model.write_bytes(b'synthetic-weights')
    digest=hashlib.sha256(model.read_bytes()).hexdigest()
    (root/'model-lock.json').write_text(json.dumps([{'file':setup_ollama.QWEN,'sha256':digest}]),encoding='utf-8')
    def import_cache():
        manifest=root/'models/ollama/manifests/registry.ollama.ai/library/flow-lab-qwen/4b';manifest.parent.mkdir(parents=True,exist_ok=True)
        manifest.write_text(json.dumps({'layers':[{'mediaType':'application/vnd.ollama.image.model','digest':'sha256:'+digest}]}),encoding='utf-8')
        blob=root/'models/ollama/blobs'/('sha256-'+digest);blob.parent.mkdir(parents=True,exist_ok=True);blob.write_bytes(model.read_bytes())
    if ready:import_cache()
    return digest,import_cache

def test_default_downloads_do_not_fetch_unsigned_native_runtimes():
    jobs=setup_models.download_jobs()
    assert len(jobs)==1 and jobs[0][0] is setup_models.model
    assert jobs[0][1][-1]==setup_ollama.QWEN

def test_ollama_fails_closed_when_publisher_is_not_confirmed(tmp_path,monkeypatch):
    exe=tmp_path/'ollama.exe';exe.write_bytes(b'fixture')
    def reject(*_):raise RuntimeError('publisher rejected')
    monkeypatch.setattr(setup_ollama,'verify_publisher',reject)
    with pytest.raises(RuntimeError,match='publisher'):setup_ollama.find_ollama(tmp_path,str(exe))
    assert not (tmp_path/'data/local-runtime.json').exists()

def test_model_manifest_and_blob_must_both_match(tmp_path):
    digest,_=cache_fixture(tmp_path)
    assert setup_ollama.model_ready(tmp_path,digest)
    blob=tmp_path/'models/ollama/blobs'/('sha256-'+digest);blob.write_bytes(b'modified')
    assert not setup_ollama.model_ready(tmp_path,digest)

def test_existing_valid_setup_is_reused_without_launch_or_config_overwrite(tmp_path,monkeypatch):
    cache_fixture(tmp_path);exe=tmp_path/'ollama.exe';exe.write_bytes(b'fixture')
    monkeypatch.setattr(setup_ollama,'find_ollama',lambda *_:exe)
    monkeypatch.setattr(setup_ollama.subprocess,'Popen',lambda *_a,**_k:(_ for _ in ()).throw(AssertionError('No restart')))
    setup_ollama.setup(tmp_path);path=tmp_path/'data/local-runtime.json';before=path.read_bytes()
    setup_ollama.setup(tmp_path)
    assert path.read_bytes()==before and json.loads(before)['sha256']==hashlib.sha256(b'fixture').hexdigest()

@pytest.mark.parametrize('success',[True,False])
def test_import_uses_only_own_local_server_and_writes_config_after_success(tmp_path,monkeypatch,success):
    _,create_cache=cache_fixture(tmp_path,ready=False);exe=tmp_path/'ollama.exe';exe.write_bytes(b'fixture')
    monkeypatch.setattr(setup_ollama,'find_ollama',lambda *_:exe)
    calls=[]
    proc=NS(poll=lambda:None,terminate=lambda:calls.append('stop-own'),wait=lambda **_:calls.append('wait-own'))
    monkeypatch.setattr(setup_ollama.subprocess,'Popen',lambda *_a,**_k:proc)
    class Client:
        def __init__(self,**kw):assert not kw['trust_env']
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def get(self,url):assert url.startswith('http://127.0.0.1:');return NS(status_code=200)
    monkeypatch.setattr(setup_ollama.httpx,'Client',Client)
    def create(args,**kwargs):
        assert args[1:3]==['create','flow-lab-qwen:4b']
        assert kwargs['env']['OLLAMA_NO_CLOUD']=='1' and kwargs['env']['OLLAMA_MODELS']==str(tmp_path/'models/ollama')
        assert not (tmp_path/'data/local-runtime.json').exists()
        if success:create_cache()
        return NS(returncode=0 if success else 1)
    monkeypatch.setattr(setup_ollama.subprocess,'run',create)
    if success:setup_ollama.setup(tmp_path)
    else:
        with pytest.raises(RuntimeError,match='import mislukt'):setup_ollama.setup(tmp_path)
    assert calls==['stop-own','wait-own']
    assert (tmp_path/'data/local-runtime.json').exists()==success

def test_onnx_failed_signature_keeps_prior_configuration(tmp_path,monkeypatch):
    root=tmp_path;folder=root/'models/fixture';folder.mkdir(parents=True)
    (root/'asr-onnx-lock.json').write_text(json.dumps({'model_directory':'fixture','files':{},'windows_native':{}}),encoding='utf-8')
    (root/'data').mkdir();config=root/'data/local-asr-runtime.json';config.write_text('{"backend":"existing"}',encoding='utf-8');before=config.read_bytes()
    monkeypatch.setattr(setup_asr_onnx,'ROOT',root)
    def reject(*_):raise RuntimeError('signature rejected')
    monkeypatch.setattr(setup_asr_onnx,'verify_publisher',reject)
    with pytest.raises(RuntimeError,match='signature'):setup_asr_onnx.setup(True)
    assert config.read_bytes()==before
