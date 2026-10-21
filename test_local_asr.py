import asyncio
import hashlib
import json
import numpy as np
import pytest
from types import SimpleNamespace as NS
import local_asr

def test_onnx_is_default_and_never_silently_changes_provider(tmp_path):
    assert local_asr.onnx_enabled(tmp_path)
    path=tmp_path/'data';path.mkdir();config=path/'local-asr-runtime.json'
    config.write_text('{broken',encoding='utf-8')
    with pytest.raises(RuntimeError):local_asr.onnx_enabled(tmp_path)
    config.write_text('{"backend":"cloud"}',encoding='utf-8')
    with pytest.raises(RuntimeError):local_asr.onnx_enabled(tmp_path)
    config.write_text('{"backend":"onnx-parakeet"}',encoding='utf-8')
    assert local_asr.onnx_enabled(tmp_path)

def test_model_and_native_integrity_checked_before_loading(tmp_path):
    path=tmp_path/'model.onnx';path.write_bytes(b'fixture');digest=hashlib.sha256(b'fixture').hexdigest()
    local_asr.checked_files(tmp_path,{'model.onnx':digest})
    path.write_bytes(b'changed')
    with pytest.raises(RuntimeError,match='gewijzigd'):local_asr.checked_files(tmp_path,{'model.onnx':digest})
    with pytest.raises(RuntimeError):local_asr.checked_files(tmp_path,{'../model.onnx':digest})
    with pytest.raises(RuntimeError):local_asr.model_folder(tmp_path,{'model_directory':'../elsewhere'})

@pytest.mark.parametrize('seconds',[0,.1,24,25,60,300])
def test_long_audio_preserves_every_sample_once_in_bounded_chunks(seconds):
    audio=np.ones(int(seconds*16000),dtype=np.float32)
    if len(audio)>20*16000:audio[19*16000:20*16000]=0
    spans=list(local_asr.audio_spans(audio));cursor=0
    for start,end in spans:
        assert start==cursor and start<end and end-start<=24*16000
        cursor=end
    assert cursor==len(audio)
    if seconds>24:assert spans[0][1]<=20*16000

def test_decoder_receives_all_chunks_in_order_and_offline(monkeypatch,tmp_path):
    backend=local_asr.OnnxParakeet(tmp_path);calls=[]
    def recognize(audio,sample_rate):calls.append((len(audio),sample_rate));return 'Fragment '+str(len(calls))+'.'
    backend.model=NS(recognize=recognize)
    result=backend.recognize(bytes(16000*2*60))
    assert result==' '.join('Fragment '+str(i+1)+'.' for i in range(len(calls)))
    assert sum(size for size,rate in calls)==16000*60 and all(rate==16000 for size,rate in calls)
    with pytest.raises(ValueError):backend.recognize(bytes(16000*2*301))

def test_onnx_ensure_never_starts_the_blocked_native_runtime(monkeypatch,tmp_path):
    import engines
    (tmp_path/'data').mkdir();(tmp_path/'data/local-asr-runtime.json').write_text('{"backend":"onnx-parakeet"}',encoding='utf-8')
    monkeypatch.setattr(engines,'ROOT',tmp_path);calls=[]
    monkeypatch.setattr(engines,'OnnxParakeet',lambda _:NS(ensure=lambda:calls.append('ensure'),recognize=lambda _: 'Fictieve proef.'))
    monkeypatch.setattr(engines.subprocess,'Popen',lambda *_a,**_k:(_ for _ in ()).throw(AssertionError('No blocked executable')))
    workers=engines.LocalWorkers();monkeypatch.setattr(engines,'workers',workers)
    assert asyncio.run(workers.ensure('parakeet'))=='inprocess://onnx-parakeet'
    assert asyncio.run(engines.local_transcribe(bytes(48000),'parakeet'))=='Fictieve proef.'
    assert calls==['ensure','ensure'] and workers.processes=={}

def test_failed_replacement_never_retries_old_runtime_or_cloud(monkeypatch,tmp_path):
    import engines
    monkeypatch.setattr(engines,'ROOT',tmp_path);monkeypatch.setattr(engines,'onnx_enabled',lambda _:True)
    def fail():raise RuntimeError('Model not ready')
    monkeypatch.setattr(engines,'OnnxParakeet',lambda _:NS(ensure=fail))
    monkeypatch.setattr(engines.subprocess,'Popen',lambda *_a,**_k:(_ for _ in ()).throw(AssertionError('No fallback')))
    with pytest.raises(RuntimeError,match='not ready'):asyncio.run(engines.LocalWorkers().ensure('parakeet'))
