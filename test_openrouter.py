import asyncio
import json
from pathlib import Path
import pytest
import httpx
from fastapi.testclient import TestClient
import openrouter_provider as provider
import storage,engines
from app import app

MODEL={'id':'example/editor:free','name':'Example','context_length':16384,'pricing':{'prompt':'0','completion':'0'},'architecture':{'input_modalities':['text'],'output_modalities':['text']},'supported_parameters':[]}

@pytest.fixture(autouse=True)
def isolated_provider(tmp_path,monkeypatch):
    monkeypatch.setattr(provider,'ROOT',tmp_path)
    monkeypatch.setattr(provider,'SECRET_FILE',tmp_path/'data/openrouter-key.dpapi')
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    monkeypatch.setattr(provider,'_catalog',[]);monkeypatch.setattr(provider,'_catalog_at',0.)
    monkeypatch.setattr(provider,'_lock',asyncio.Lock())

def test_only_free_text_models_pass():
    assert provider.free_text_model(MODEL)
    assert not provider.free_text_model(dict(MODEL,id='example/content-safety:free'))
    for model in [dict(MODEL,id='example/editor'),dict(MODEL,pricing={'prompt':'0.01','completion':'0'}),dict(MODEL,pricing={'prompt':'0','completion':'0','request':'1'}),dict(MODEL,pricing={}),dict(MODEL,context_length=1000),dict(MODEL,architecture={'input_modalities':['audio'],'output_modalities':['text']})]:
        assert not provider.free_text_model(model)

def test_cost_and_privacy_controls_and_no_paid_fallback():
    payload={'messages':[],'model':'paid','models':['paid/fallback'],'tools':[{}],'temperature':0}
    result=provider.request_body(payload,MODEL)
    assert result['model'].endswith(':free') and 'models' not in result and 'tools' not in result
    assert result['provider']['max_price']=={'prompt':0,'completion':0,'request':0}
    assert result['provider']['data_collection']=='deny' and not result['provider']['allow_fallbacks']
    assert result['plugins']==[]

def test_privacy_only_changes_by_explicit_setting_and_keeps_zero_price():
    assert provider.status()['data_collection']=='deny'
    with TestClient(app) as client:
        h={'Origin':f'http://127.0.0.1:{engines.APP_PORT}'}
        assert client.post('/api/openrouter/privacy',headers=h,json={'data_collection':'allow'}).status_code==200
    assert provider.status()['data_collection']=='allow'
    body=provider.request_body({},MODEL,'allow')
    assert body['provider']['max_price']['completion']==0
    assert body['provider']['data_collection']=='allow'

def test_key_encrypted_and_never_returned():
    key='sk-or-'+('x'*40)
    with TestClient(app) as client:
        r=client.post('/api/openrouter/key',headers={'Origin':f'http://127.0.0.1:{engines.APP_PORT}'},json={'key':key})
        assert r.status_code==200 and key not in r.text
        assert key not in client.get('/api/openrouter/status').text
    assert key.encode() not in provider.SECRET_FILE.read_bytes()
    assert provider.key_value()==key

def test_invalid_or_cross_origin_secret_not_echoed_or_written():
    value='wrong-provider-sensitive-value'
    with TestClient(app) as client:
        r=client.post('/api/openrouter/key',headers={'Origin':f'http://127.0.0.1:{engines.APP_PORT}'},json={'key':value})
        assert r.status_code==400 and value not in r.text
        assert client.post('/api/openrouter/key',json={'key':value}).status_code==403
    assert not provider.SECRET_FILE.exists()

def test_missing_key_never_sends_text(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('Must not request anything')
    monkeypatch.setattr(provider.httpx,'AsyncClient',forbidden)
    with pytest.raises(RuntimeError,match='sleutel'):asyncio.run(provider.complete({'messages':[]}))

def test_openrouter_request_uses_separate_key_and_fixed_url(monkeypatch):
    seen=[]
    monkeypatch.setattr(provider,'key_value',lambda:'sk-or-'+('x'*40))
    storage.set_setting('openrouter_model',MODEL['id'])
    async def catalogue(*a,**kw):return [MODEL]
    monkeypatch.setattr(provider,'catalogue',catalogue)
    class Client:
        def __init__(self,*a,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,headers,json):
            seen.append((url,headers,json))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'Dit is een test.'}}]})
    monkeypatch.setattr(provider.httpx,'AsyncClient',Client)
    monkeypatch.setattr(engines,'api_key',lambda:(_ for _ in ()).throw(AssertionError('No OpenAI key')))
    result=asyncio.run(engines.format_text('dit is een test','openrouter-free'))
    assert result['text']=='Dit is een test.'
    assert len(seen)==1 and seen[0][0]=='https://openrouter.ai/api/v1/chat/completions'
    assert seen[0][2]['model']==MODEL['id']

def test_paid_or_removed_model_is_not_called(monkeypatch):
    monkeypatch.setattr(provider,'key_value',lambda:'sk-or-'+('x'*40))
    storage.set_setting('openrouter_model','example/paid')
    async def catalogue(*a,**kw):return [MODEL]
    monkeypatch.setattr(provider,'catalogue',catalogue)
    with pytest.raises(RuntimeError,match='gratis'):asyncio.run(provider.complete({'messages':[]}))

def test_rate_limit_has_no_retry_and_no_raw_provider_error(monkeypatch):
    monkeypatch.setattr(provider,'key_value',lambda:'sk-or-'+('x'*40));storage.set_setting('openrouter_model',MODEL['id'])
    async def catalogue(*a,**kw):return [MODEL]
    monkeypatch.setattr(provider,'catalogue',catalogue);calls=[]
    class Client:
        def __init__(self,*a,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,*a,**kw):calls.append(1);return httpx.Response(429,json={'error':{'message':'do not echo this provider body'}})
    monkeypatch.setattr(provider.httpx,'AsyncClient',Client)
    with pytest.raises(RuntimeError,match='limiet') as exc:asyncio.run(provider.complete({'messages':[]}))
    assert len(calls)==1 and 'do not echo' not in str(exc.value)

def test_offline_mode_still_rejects_cloud_formatter():
    from app import validate
    with pytest.raises(ValueError):validate('parakeet','openrouter-free')
    validate('hybrid-parakeet','openrouter-free')
