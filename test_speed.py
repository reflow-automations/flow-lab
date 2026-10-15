import asyncio,queue,threading,time
from concurrent.futures import Future
from types import SimpleNamespace as NS
from fastapi.testclient import TestClient
import app as routes
import engines
import desktop_windows as w
from desktop_helper import Desktop

ORIGIN={'Origin':f'http://127.0.0.1:{engines.APP_PORT}'}

def test_local_formatter_uses_lossless_ngram_speculation():
    # Greedy decoding (temperature 0) keeps speculative output identical to normal output.
    assert engines.SPECULATIVE_ARGS[:2]==['--spec-type','ngram-simple']

def test_concurrent_prepare_warms_each_model_once(monkeypatch):
    calls=[]
    async def ensure(name):return 'http://127.0.0.1'
    async def transcribe(pcm,engine):calls.append(engine);await asyncio.sleep(.01);return ''
    async def fmt(text,engine,*a,**kw):calls.append(engine);await asyncio.sleep(.01);return {'text':text}
    monkeypatch.setattr(engines,'workers',engines.LocalWorkers())
    monkeypatch.setattr(engines.workers,'ensure',ensure)
    monkeypatch.setattr(engines,'local_transcribe',transcribe);monkeypatch.setattr(engines,'format_text',fmt)
    async def both():await asyncio.gather(engines.prepare_local('parakeet','local'),engines.prepare_local('parakeet','local'))
    asyncio.run(both())
    assert sorted(calls)==['local','parakeet']

def test_wake_only_touches_idle_warm_models(monkeypatch):
    calls=[]
    async def transcribe(pcm,engine):calls.append(engine);return ''
    async def fmt(text,engine,*a,**kw):calls.append(engine);return {'text':text}
    workers=engines.LocalWorkers();monkeypatch.setattr(engines,'workers',workers)
    monkeypatch.setattr(engines,'local_transcribe',transcribe);monkeypatch.setattr(engines,'format_text',fmt)
    asyncio.run(engines.wake_local('parakeet','local'))
    assert calls==[] # never loads a model that was not warmed
    workers.warmed.update({'parakeet','local'})
    asyncio.run(engines.wake_local('parakeet','local'))
    assert sorted(calls)==['local','parakeet']
    calls.clear();workers.used('parakeet');workers.used('local')
    asyncio.run(engines.wake_local('parakeet','local'))
    assert calls==[] # recently used models stay untouched
    asyncio.run(engines.wake_local('parakeet','cloud-mini'))
    assert calls==[] # cloud formatting never wakes the local formatter

def test_prewarm_runs_in_background_without_blocking_dictation(monkeypatch):
    started=[]
    async def prepare(engine,formatter):started.append((engine,formatter));await asyncio.sleep(.05)
    monkeypatch.setattr(routes,'prepare_local',prepare);monkeypatch.setattr(routes,'prewarm_task',None)
    with TestClient(routes.app) as client:
        assert client.post('/api/prewarm',json={'engine':'parakeet','formatter':'local'}).status_code==403
        r=client.post('/api/prewarm',json={'engine':'hybrid-parakeet','formatter':'cloud-mini'},headers=ORIGIN)
        assert r.json()=={'started':True} and not routes.gate.locked()
        assert client.post('/api/prewarm',json={'engine':'parakeet','formatter':'cloud-mini'},headers=ORIGIN).status_code==400
        time.sleep(.1)
    assert started==[('parakeet','cloud-mini')]

def test_microphone_has_headroom_for_python_pauses():
    assert len(w.Microphone(lambda _:None).buffers)>=8

def test_empty_field_with_hint_text_is_reported_as_inserted(monkeypatch,tmp_path):
    import desktop_helper as d
    monkeypatch.setattr(d,'ROOT',tmp_path)
    class Worker:
        def submit(self,fn,*args):
            future=Future()
            if fn is w.same_target:future.set_result((True,''))
            else:args[0].details['whole_field_equals_dictation']=True;future.set_result(False)
            return future
    backup=NS(sequence=1,restore=lambda _:True,dispose=lambda:None)
    monkeypatch.setattr(w,'ClipboardBackup',lambda _:backup)
    monkeypatch.setattr(w,'modifiers_held',lambda:False)
    monkeypatch.setattr(w,'clipboard_sequence',lambda:1)
    monkeypatch.setattr(w,'copy_text',lambda *_:2)
    monkeypatch.setattr(w,'foreground',lambda:10)
    monkeypatch.setattr(w,'paste_once',lambda:True)
    app=NS(events=queue.Queue(),hwnd=1,test=False,uia=Worker())
    app.record_insertion=lambda *args:Desktop.record_insertion(app,*args)
    session=NS(ident=1,target=w.Target(10,editable=True),cancel=threading.Event(),timings={},released_at=d.time.monotonic())
    Desktop.insert(app,session,{'text':'All sentences.'})
    kind,ident,ok,reason=app.events.get_nowait()
    assert kind=='inserted' and ok and reason=='Ingevoegd in leeg tekstvak'
    report=d.json.loads((tmp_path/'logs/desktop-last-insertion.json').read_text(encoding='utf-8'))
    assert report['status']=='complete_dictation_context_unverified' # diagnostics stay precise
