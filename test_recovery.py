import asyncio
import json
import queue
import threading
import time
import uuid
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
import app as routes
import storage
from recovery import RecoveryStore,RETENTION_SECONDS,wav_bytes
from engines import APP_PORT

def config():return dict(engine='parakeet',formatter='local',style='bericht',paragraphs='normaal')

def test_encrypted_audio_survives_restart_and_preserves_exact_samples(tmp_path):
    pcm=b'PRIVATE_SYNTHETIC_AUDIO_ONLY_'*20
    store=RecoveryStore(tmp_path);key=str(uuid.uuid4());store.save(key,pcm,config())
    saved=(tmp_path/(key+'.dpapi')).read_bytes()
    assert pcm not in saved and b'parakeet' not in saved
    metadata,restored=RecoveryStore(tmp_path).load(key)
    assert restored==pcm and metadata['persistent'] and metadata['config']==config()
    store.discard(key)
    assert RecoveryStore(tmp_path).entries()==[]

def test_recovery_capacity_never_evicts_unexpired_audio(monkeypatch,tmp_path):
    import recovery
    store=RecoveryStore(tmp_path)
    key=str(uuid.uuid4());store.save(key,b'\0\1'*20,config())
    monkeypatch.setattr(recovery,'MAX_STORAGE_BYTES',store.used_bytes()+65536+39)
    with pytest.raises(RuntimeError):store.save(str(uuid.uuid4()),b'\0\1'*20,config())
    assert store.ids()==[key]
    with pytest.raises(ValueError):store.discard('../outside')

def test_successful_audio_remains_for_24_hours_and_can_really_run_again(tmp_path):
    store=RecoveryStore(tmp_path);key=str(uuid.uuid4());pcm=b'\0\1'*20
    store.save(key,pcm,config());original_time=store.metadata(key)['created_at']
    assert store.retry_id(key)==key
    store.mark_completed(key)
    assert RecoveryStore(tmp_path).load(key)[1]==pcm
    retry=store.retry_id(key)
    assert retry!=key and store.retry_id(key)==retry
    store.mark_completed(key)
    assert store.metadata(key)['created_at']==original_time
    assert store.retry_id(key)!=retry
    store.prune(now=original_time+RETENTION_SECONDS-1)
    assert key in store.ids()
    store.prune(now=original_time+RETENTION_SECONDS)
    assert store.ids()==[] and not list(tmp_path.glob(key+'.*'))

def test_expiry_protects_active_retry_and_never_removes_new_recording(tmp_path):
    store=RecoveryStore(tmp_path);key=str(uuid.uuid4());store.save(key,b'\0\1'*20,config())
    created=store.metadata(key)['created_at'];store.active.add(key)
    store.prune(now=created+RETENTION_SECONDS+1)
    assert key in store.ids()
    store.active.discard(key);store.prune(now=created+RETENTION_SECONDS+1)
    assert key not in store.ids()

def test_metadata_listing_does_not_decrypt_all_audio(monkeypatch,tmp_path):
    store=RecoveryStore(tmp_path);key=str(uuid.uuid4());store.save(key,b'\0\1'*20,config())
    monkeypatch.setattr(store,'load',lambda *_:(_ for _ in ()).throw(AssertionError('Listing should use small metadata index')))
    assert store.entries()[0]['id']==key

def test_disk_failure_keeps_in_memory_recovery(monkeypatch,tmp_path):
    import recovery
    monkeypatch.setattr(recovery,'protect',lambda *_:(_ for _ in ()).throw(OSError('disk failed')))
    store=RecoveryStore(tmp_path);key=str(uuid.uuid4());store.save(key,b'\0\1'*20,config())
    metadata,pcm=store.load(key)
    assert not metadata['persistent'] and pcm==b'\0\1'*20

def test_retry_is_idempotent_after_lost_result_response(monkeypatch):
    calls=[]
    async def run(pcm,*args,**kwargs):
        calls.append(pcm);return {'raw':'Synthetic example.','text':'Synthetic example.','warning':None,'asr_ms':1,'format_ms':2,'after_stop_ms':3}
    monkeypatch.setattr(routes,'run_clip',run)
    key=str(uuid.uuid4());params={**config(),'recording_id':key}
    with TestClient(routes.app) as client:
        for _ in range(2):
            result=client.post('/api/clip',params=params,content=wav_bytes(b'\0\1'*2400),headers={'Origin':f'http://127.0.0.1:{APP_PORT}'})
            assert result.status_code==200 and result.json()['history_id']==key
        assert client.post('/api/clip',params={**params,'recording_id':'../bad'},content=b'').status_code in (403,422)
    assert len(calls)==1 and storage.history()['total']==1

def test_transport_failure_keeps_recording_until_user_stops(monkeypatch,tmp_path):
    import desktop_helper as d
    events=queue.Queue();store=RecoveryStore(tmp_path)
    app=NS(config=config(),events=events,recovery_store=store)
    started=threading.Event();finished=threading.Event()
    def source(self):
        self.push(b'\0\1'*100);started.set()
        self.stop.wait(3)
        self.push(b'\0\2'*100)
        if not self.cancel.is_set():store.save(self.recording_id,self.pcm,self.config)
        self.audio.put(None);finished.set()
    async def network(self):raise RuntimeError('Connection failed')
    monkeypatch.setattr(d.Recording,'source',source);monkeypatch.setattr(d.Recording,'network',network)
    recorder=d.Recording(app,7,None)
    assert started.wait(2)
    time.sleep(.03)
    assert not finished.is_set() and not recorder.stop.is_set()
    recorder.stop.set();assert finished.wait(2)
    deadline=time.monotonic()+2;received=[]
    while time.monotonic()<deadline:
        try:
            event=events.get(timeout=.1);received.append(event)
            if event[0]=='error':break
        except queue.Empty:pass
    assert any(e[0]=='error' for e in received)
    assert store.load(recorder.recording_id)[1]==b'\0\1'*100+b'\0\2'*100

def test_retry_busy_keeps_audio_and_never_starts_microphone(monkeypatch,tmp_path):
    import httpx
    import desktop_helper as d
    store=RecoveryStore(tmp_path);key=str(uuid.uuid4());store.save(key,b'\0\1'*20,config())
    monkeypatch.setattr(httpx,'post',lambda *a,**k:NS(status_code=409))
    monkeypatch.setattr(d.w,'Microphone',lambda *_:(_ for _ in ()).throw(AssertionError('No microphone on retry')))
    app=NS(state='idle',ident=1,current=None,recovery_store=store,events=queue.Queue(),
           hotkeys=NS(command=lambda *_:None),remember_status=lambda _:None)
    d.Desktop.retry_recording(app,key)
    event=app.events.get(timeout=3)
    assert event[0]=='recovery_error' and 'bewaard' in event[2]
    assert key in store.ids()

def test_retry_rejects_unconfirmed_response_without_dropping_audio(monkeypatch,tmp_path):
    import httpx
    import desktop_helper as d
    store=RecoveryStore(tmp_path);key=str(uuid.uuid4());store.save(key,b'\0\1'*20,config())
    monkeypatch.setattr(httpx,'post',lambda *a,**k:NS(status_code=200,is_success=True,json=lambda:{'text':'Example','raw':'Example'}))
    app=NS(state='idle',ident=1,current=None,recovery_store=store,events=queue.Queue(),
           hotkeys=NS(command=lambda *_:None),remember_status=lambda _:None)
    d.Desktop.retry_recording(app,key)
    assert app.events.get(timeout=3)[0]=='recovery_error'
    assert key in store.ids()

def test_cancelled_recording_does_not_keep_audio(monkeypatch,tmp_path):
    import desktop_helper as d
    store=RecoveryStore(tmp_path);key=str(uuid.uuid4());store.save(key,b'\0\1'*20,config())
    recorder=object.__new__(d.Recording)
    recorder.recording_id=key;recorder.app=NS(recovery_store=store)
    recorder.cancel=threading.Event();recorder.cancel.set();recorder.stop=threading.Event()
    recorder.source=lambda:None
    async def network():return
    recorder.network=network
    recorder.run()
    assert store.ids()==[]

def test_ws_history_uses_same_recovery_id(monkeypatch):
    async def prepare(*args):pass
    async def transcribe(*args):return 'Synthetic whole recording.'
    async def format_text(*args,**kwargs):return {'text':'Synthetic whole recording.','ms':2,'warning':None}
    monkeypatch.setattr(routes,'prepare_local',prepare);monkeypatch.setattr(routes,'wake_local',prepare)
    monkeypatch.setattr(routes,'local_transcribe',transcribe);monkeypatch.setattr(routes,'format_text',format_text)
    key=str(uuid.uuid4())
    with TestClient(routes.app) as client:
        with client.websocket_connect('/api/record',headers={'Origin':f'http://127.0.0.1:{APP_PORT}'}) as ws:
            ws.send_json({**config(),'recording_id':key});assert ws.receive_json()['type']=='ready'
            ws.send_bytes(b'\0\x10'*2400);ws.send_json({'type':'stop'})
            assert ws.receive_json()['type']=='recognized'
            assert ws.receive_json()['history_id']==key
    assert storage.history_result(key)['text']=='Synthetic whole recording.'
