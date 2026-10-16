import asyncio,re,time
import pytest
from fastapi.testclient import TestClient
import storage,engines
from personalization import snippet_preview,paragraph_layout,dictionary_replace
from app import app

ORIGIN={'Origin':f'http://127.0.0.1:{engines.APP_PORT}'}
def snippet(aliases=None,value='Regel één.\n\nRegel twee.  '):
    return storage.save_entry('snippet',{'name':'Compact voorbereiding','aliases':aliases or ['compact voorbereiding','compact voorbereiden'],'value':value})

@pytest.mark.parametrize('phrase',['Compact voorbereiding','compact-voorbereiding.','COMPACT voorbereiden!'])
def test_full_snippet_exact_and_no_model(monkeypatch,phrase):
    snippet();calls=[]
    async def forbidden(*args,**kwargs):calls.append(args);raise AssertionError('No model should receive a full snippet')
    monkeypatch.setattr(engines,'_format_text_base',forbidden)
    result=asyncio.run(engines.format_text(phrase,'cloud-mini'))
    assert result['text']=='Regel één.\n\nRegel twee.  ' and not calls

def test_inline_snippet_body_never_sent_to_formatter(monkeypatch):
    body='Gebruik deze exacte tekst.\n\n/compact\n  spaties blijven staan'
    snippet(['mijn tekst'],body);received=[]
    async def mock(text,*args,**kwargs):
        received.append(text);return {'text':text,'ms':1,'warning':None}
    monkeypatch.setattr(engines,'_format_text_base',mock)
    r=asyncio.run(engines.format_text('Begin: mijn tekst Daarna klaar.','cloud-mini'))
    assert r['text']=='Begin: '+body+' Daarna klaar.'
    assert body not in received[0] and 'FLOWLAB_' in received[0]

def test_damaged_snippet_marker_falls_back_without_losing_snippet(monkeypatch):
    snippet(['mijn tekst'],'EXACT\n\nBEHOUDEN')
    async def mock(*args,**kwargs):return {'text':'Een model liet iets weg.','ms':1,'warning':None}
    monkeypatch.setattr(engines,'_format_text_base',mock)
    r=asyncio.run(engines.format_text('Begin mijn tekst klaar.','local'))
    assert 'EXACT\n\nBEHOUDEN' in r['text'] and r['warning']

def test_slash_boundaries_repeats_and_alias_collisions():
    snippet(['/compact','slash compact.'],'/compact zorgvuldig samenvatten')
    assert snippet_preview('/compact')['text']=='/compact zorgvuldig samenvatten'
    assert snippet_preview('slash compact.')['text']=='/compact zorgvuldig samenvatten'
    assert snippet_preview('compact is een gewoon woord')['text']=='compact is een gewoon woord'
    assert snippet_preview('slash compact en slash compact')['text'].count('/compact zorgvuldig')==2
    with pytest.raises(ValueError):snippet(['slash-compact'],'andere tekst')

def test_dictionary_longest_match_and_no_cascade():
    storage.save_entry('dictionary',{'value':'Supabase','aliases':['super base','super-base','soeper base']})
    assert dictionary_replace('super-base, soeper base en SUPER BASE gebruiken webhoek.')=='Supabase, Supabase en Supabase gebruiken webhook.'
    assert dictionary_replace('super-basement')=='super-basement'

def test_spoken_participle_repair_preserves_meaning_and_unrelated_words():
    from personalization import repair_spoken_words
    assert repair_spoken_words('Ik heb al gebetaald voor het kaartje.')=='Ik heb al betaald voor het kaartje.'
    assert repair_spoken_words('Heb je nog niet gebetaald?')=='Heb je nog niet betaald?'
    assert repair_spoken_words('De gasten hebben gisteren allemaal gebetaald.')=='De gasten hebben gisteren allemaal betaald.'
    assert repair_spoken_words('Ik heb geprobeerd en daarna gebeld.')=='Ik heb geprobeerd en daarna gebeld.'

def test_spelling_discussion_and_quotes_are_not_repaired():
    from personalization import repair_spoken_words
    examples=['Het woord gebetaald is onjuist.', 'Ik heb "gebetaald" gezegd.', "Ik heb 'gebetaald' gezegd.",
              'Ik heb gebetaald op het bord geschreven.', 'Ik heb `gebetaald` gebruikt.', 'Hier staat gebetaald.']
    for example in examples:assert repair_spoken_words(example)==example

def test_imported_hint_does_not_capitalize_common_words():
    identifier=storage.save_entry('dictionary',{'value':'Ook','aliases':['Ook']},source='wispr-hint')
    assert dictionary_replace('het is ook lokaal')=='het is ook lokaal'
    storage.save_entry('dictionary',{'id':identifier,'value':'OOK','aliases':['ook']})
    assert dictionary_replace('het is ook lokaal')=='het is OOK lokaal'

def test_unrequested_internal_marker_is_rejected():
    assert engines.content_guard('Ik druk op stoppen.','Ik druk op stoppen.\nFLOWLAB_stoppen_END')=='invented_marker'

def test_paragraphs_at_topic_change_without_content_changes():
    text='Deze fictieve voorbeeldtekst beschrijft een eenvoudige planning voor een gezamenlijke wandeling door het park. Daarnaast bespreken we welke route prettig is voor de groep en waar we onderweg kunnen pauzeren. Iedereen neemt zelf wat drinken mee. Dat is handig.'
    result=paragraph_layout(text)
    assert 'park.\n\nDaarnaast' in result
    assert 'mee.\n\nDat' not in result
    assert re.sub(r'\s+',' ',result)==re.sub(r'\s+',' ',text)
    assert paragraph_layout(text,'compact')==text
    assert paragraph_layout('1. Eerste punt\n2. Tweede punt')=='1. Eerste punt\n2. Tweede punt'


def test_dense_block_without_transition_gets_balanced_paragraphs():
    text='Een fictieve groep bezoekers komt op zaterdag samen voor een rondleiding in het museum. De gids bespreekt eerst de geschiedenis van het gebouw en geeft daarna uitleg over de tentoonstelling. De bezoekers kunnen vragen stellen bij de verschillende schilderijen in iedere zaal. Het programma eindigt met een korte pauze in de centrale hal.'
    result=paragraph_layout(text)
    assert len(result.split('\n\n'))==2
    assert result.replace('\n\n',' ')==text


def test_history_retention_search_and_idempotency(monkeypatch):
    now=time.time()
    with storage.connect() as c:
        c.executemany('INSERT INTO history VALUES(?,?,?,?,?)', [('old',now-31*86400,'oud','oud','{}'),('keep',now-29*86400,'raw','bewaar 100%','{}')])
    storage.prune(now)
    assert storage.history()['total']==1
    assert storage.history('%')['total']==1
    assert storage.history("' OR 1=1 --")['total']==0
    storage.add_history('a','b',{},identifier='same');storage.add_history('a','b',{},identifier='same')
    assert storage.history()['total']==2

def test_library_roundtrip_and_history_api(monkeypatch):
    client=TestClient(app)
    entry={'name':'Testsnippet','aliases':['test variant'],'value':'Hoi\n\nExacte regels.','enabled':True}
    saved=client.post('/api/library/snippet',headers=ORIGIN,json=entry);assert saved.status_code==200
    assert client.get('/api/library').json()['snippets'][0]['value']==entry['value']
    expanded=client.post('/api/expand',headers=ORIGIN,json={'text':'test variant'}).json();assert expanded['text']==entry['value']
    assert client.get('/api/history').json()['total']==0
    made=client.post('/api/format',headers=ORIGIN,json={'text':'test variant','formatter':'verbatim'}).json()
    rows=client.get('/api/history').json()['items'];assert len(rows)==1 and rows[0]['id']==made['history_id']
    assert rows[0]['text']==entry['value'] and rows[0]['metadata']['source']=='opmaak'
    assert client.post('/api/library/snippet',headers={'Origin':'https://example.com'},json=entry).status_code==403

def test_cancel_during_format_does_not_create_history(monkeypatch):
    async def prepare(*args):pass
    async def transcribe(*args):return 'Dit is een test.'
    async def slow(*args,**kwargs):await asyncio.sleep(2);return {'text':'Dit is een test.','ms':2000,'warning':None}
    import app as routes
    monkeypatch.setattr(routes,'prepare_local',prepare);monkeypatch.setattr(routes,'local_transcribe',transcribe);monkeypatch.setattr(routes,'format_text',slow)
    with TestClient(app) as client:
        with client.websocket_connect('/api/record',headers=ORIGIN) as ws:
            ws.send_json({'engine':'parakeet','formatter':'local'});assert ws.receive_json()['type']=='ready'
            ws.send_bytes(b'\x00\x10'*24000);ws.send_json({'type':'stop'})
            assert ws.receive_json()['type']=='recognized';ws.send_json({'type':'cancel'})
            from starlette.websockets import WebSocketDisconnect
            with pytest.raises(WebSocketDisconnect):ws.receive_json()
        assert client.get('/api/history').json()['total']==0
