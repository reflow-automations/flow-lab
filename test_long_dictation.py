import asyncio
import queue
import threading
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
import app as routes
import engines
from limits import MAX_SECONDS,MAX_PCM_BYTES,MAX_WAV_BYTES,MAX_TEXT_CHARS,FORMAT_CHUNK_CHARS,SESSION_TIMEOUT_SECONDS,AudioBudget,split_format_text

def test_five_minute_bounds_and_final_device_block():
    assert MAX_SECONDS==300 and MAX_PCM_BYTES==14400000
    assert SESSION_TIMEOUT_SECONDS>MAX_SECONDS+180
    assert MAX_WAV_BYTES>300*96000*2*2+44
    budget=AudioBudget();budget.used=MAX_PCM_BYTES-100
    assert len(budget.take(bytes(1920)))==100
    assert budget.full and budget.take(bytes(1920))==b''

def test_five_minute_wav_accepted_and_one_sample_over_rejected():
    pcm=bytes(MAX_PCM_BYTES)
    assert len(engines.read_wav(engines.pcm_wav(pcm)))==len(pcm)
    with pytest.raises(ValueError):engines.read_wav(engines.pcm_wav(pcm+b'\0\0'))

def test_desktop_stop_fires_once_at_audio_limit():
    from desktop_helper import Recording
    recorder=object.__new__(Recording)
    recorder.cancel=threading.Event();recorder.stop=threading.Event();recorder.audio_budget=AudioBudget(100)
    recorder.audio=queue.Queue();recorder.limit_notified=False;events=[];recorder.emit=lambda *a:events.append(a)
    recorder.push(b'\0\x10'*96);recorder.push(b'\0\x10'*96)
    assert len(recorder.audio.get())==100 and recorder.audio.empty()
    assert recorder.stop.is_set() and sum(e[0]=='source_done' for e in events)==1

def test_five_minute_websocket_reaches_model_and_history(monkeypatch):
    seen=[]
    async def prepare(*a):pass
    async def transcribe(pcm,*a):
        seen.append(len(pcm));assert pcm[-2:]==b'\x00\x20';return 'Begin en laatste woorden.'
    async def format_text(text,*a,**kw):return {'text':text,'ms':0,'warning':None}
    monkeypatch.setattr(routes,'prepare_local',prepare);monkeypatch.setattr(routes,'local_transcribe',transcribe);monkeypatch.setattr(routes,'format_text',format_text)
    with TestClient(routes.app) as client:
        with client.websocket_connect('/api/record',headers={'Origin':f'http://127.0.0.1:{engines.APP_PORT}'}) as ws:
            ws.send_json({'engine':'parakeet','formatter':'local'})
            assert ws.receive_json()['max_seconds']==300
            for _ in range(299):ws.send_bytes(b'\0\x10'*24000)
            ws.send_bytes(b'\0\x10'*23999+b'\0\x20');ws.send_json({'type':'stop'})
            assert ws.receive_json()['type']=='recognized';result=ws.receive_json()
            assert result['text']=='Begin en laatste woorden.' and result['type']=='done'
        assert client.get('/api/history').json()['items'][0]['metadata']['duration_s']==300
    assert seen==[MAX_PCM_BYTES]

def test_format_failure_keeps_raw_transcription(monkeypatch):
    async def prepare(*a):pass
    async def transcribe(*a):return 'Bewaar deze laatste woorden.'
    async def fail(*a,**kw):raise RuntimeError('format failed')
    monkeypatch.setattr(routes,'prepare_local',prepare);monkeypatch.setattr(routes,'local_transcribe',transcribe);monkeypatch.setattr(routes,'format_text',fail)
    with TestClient(routes.app) as client:
        with client.websocket_connect('/api/record',headers={'Origin':f'http://127.0.0.1:{engines.APP_PORT}'}) as ws:
            ws.send_json({'engine':'parakeet','formatter':'local'});ws.receive_json()
            ws.send_bytes(b'\0\x10'*24000);ws.send_json({'type':'stop'});ws.receive_json();result=ws.receive_json()
            assert result['text']=='Bewaar deze laatste woorden.' and result['warning']
        assert client.get('/api/history').json()['total']==1

def test_long_text_chunks_keep_all_words_and_markers():
    text=('Dit is een fictieve notitie met een duidelijk einde. '*200)+' FLOWLAB_0123456789AB_0_END Einde.'
    parts=split_format_text(text)
    assert len(parts)>1 and all(len(p)<=FORMAT_CHUNK_CHARS for p in parts)
    assert ' '.join(parts).split()==text.split()
    assert sum('FLOWLAB_0123456789AB_0_END' in p for p in parts)==1

def test_local_formatter_cannot_silently_summarize_a_long_dictation():
    source='Een fictieve zin met herhaalde maar bewust ingesproken woorden. '*40
    assert engines.content_guard(source,'Een fictieve zin met herhaalde maar bewust ingesproken woorden.')=='contracted'

def test_long_formatting_uses_bounded_requests(monkeypatch):
    text='Dit is een fictieve notitie met een duidelijk einde. '*250
    assert 12000<len(text)<MAX_TEXT_CHARS
    calls=[]
    async def ensure(*a):return 'http://unused'
    class Client:
        def __init__(self,*a,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,url,headers,json):
            value=json['messages'][1]['content'].split('\n',1)[1].rsplit('\n',1)[0]
            calls.append(value)
            return NS(status_code=200,json=lambda:{'choices':[{'finish_reason':'stop','message':{'content':value}}]})
    monkeypatch.setattr(engines.workers,'ensure',ensure);monkeypatch.setattr(engines.httpx,'AsyncClient',Client)
    result=asyncio.run(engines.format_text(text,'local'))
    assert len(calls)>1 and max(map(len,calls))<=FORMAT_CHUNK_CHARS
    assert result['text'].split()==text.split() and not result['warning']
