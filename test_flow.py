import asyncio,io,wave
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app import app,validate
from engines import clean_layout,number_guard,pcm_wav,read_wav,silent,run_clip,conservative_layout,content_guard,dictionary_replace

def test_blank_lines_and_decimal_survive():
    assert clean_layout(' Hoi Jan ,\r\n\r\n\r\nHet is 0,5 procent.  \r\n')=='Hoi Jan,\n\nHet is 0,5 procent.'

def test_invented_letter_envelope_removed_but_real_recipient_retained():
    assert conservative_layout('ik kan vrijdag','Hoi Jan,\n\nik kan vrijdag.\n\nEinde.')=='Ik kan vrijdag.'
    assert conservative_layout('hoi Sem ik kan vrijdag','Hoi Sem,\nik kan vrijdag.')=='Hoi Sem,\n\nIk kan vrijdag.'
    assert content_guard('misschien niet','Dat is zeker.')

def test_streaming_wav_header_uses_actual_data_length():
    data=bytearray(pcm_wav(bytes(48000)))
    data[4:8]=(0xffffffff).to_bytes(4,'little');data[40:44]=(0xffffffff).to_bytes(4,'little')
    assert len(read_wav(bytes(data)))==48000

def test_person_names_not_silently_changed_and_paragraph_command():
    assert dictionary_replace('Sam koppelt Superbase aan de webhoek')=='Sam koppelt Supabase aan de webhook'
    assert conservative_layout('eerste zin nieuwe alinea morgen verder','Eerste zin.\nmorgen verder.')=='Eerste zin.\n\nMorgen verder.'

def test_offline_cannot_silently_use_cloud_formatter():
    with pytest.raises(ValueError):validate('parakeet','cloud-mini')
    validate('whisper','local')

def test_digit_change_is_detected():
    assert number_guard('Het is 1500 euro.','Het is 15000 euro.')=={'15000'}
    assert not number_guard('Het is 1500 euro.','Het is 1.500 euro.')
    assert not number_guard('eerste punt test de koppeling','1. Test de koppeling.')

def test_question_cannot_disappear_during_editing():
    assert content_guard('Is de bestelling betaald?', 'De bestelling is betaald.')=='question_removed'
    assert content_guard('Kun je nagaan wat de voorwaarden zijn?', 'Kun je nagaan wat de voorwaarden zijn?') is None

def test_audio_duration_and_resampling():
    pcm=(np.sin(np.arange(48000)*.1)*1000).astype('<i2').tobytes()
    converted=read_wav(pcm_wav(pcm,48000))
    assert len(converted)==48000
    assert not silent(converted)
    assert silent(bytes(48000))

def test_long_audio_rejected():
    with pytest.raises(ValueError):read_wav(pcm_wav(bytes(48000*301)))

def test_silence_does_not_call_cloud():
    result=asyncio.run(run_clip(bytes(48000),'cloud-live','cloud-mini'))
    assert result['text']=='' and result['after_stop_ms']==0

def test_cross_site_post_and_unknown_host_rejected():
    client=TestClient(app)
    assert client.post('/api/format',headers={'Origin':'https://example.com'},json={'text':'Hallo'}).status_code==403
    assert client.get('/',headers={'Host':'evil.example'}).status_code==400
    assert client.get('/.env.local').status_code==404

def test_page_and_security_headers():
    r=TestClient(app).get('/')
    assert r.status_code==200 and 'Klaar om te gebruiken' in r.text
    assert "frame-ancestors 'none'" in r.headers['Content-Security-Policy']
