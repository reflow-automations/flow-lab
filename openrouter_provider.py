"""Opt-in free-only OpenRouter text formatting. Never handles microphone audio."""
import asyncio
import ctypes as C
from ctypes import wintypes as W
from decimal import Decimal,InvalidOperation
import os
from pathlib import Path
import re
import time
import httpx
import storage

ROOT=Path(__file__).resolve().parent
SECRET_FILE=ROOT/'data/openrouter-key.dpapi'
BASE='https://openrouter.ai/api/v1'
_catalog=[];_catalog_at=0.;_lock=asyncio.Lock()

class Blob(C.Structure):_fields_=[('size',W.DWORD),('data',C.POINTER(C.c_ubyte))]

def crypt(data,decrypt=False):
    """Windows DPAPI binds encrypted material to the current Windows user."""
    crypt32=C.WinDLL('crypt32',use_last_error=True);kernel=C.WinDLL('kernel32',use_last_error=True)
    raw=C.create_string_buffer(data);source=Blob(len(data),C.cast(raw,C.POINTER(C.c_ubyte)));target=Blob()
    fn=crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    fn.argtypes=[C.POINTER(Blob),C.c_void_p,C.POINTER(Blob),C.c_void_p,C.c_void_p,W.DWORD,C.POINTER(Blob)]
    fn.restype=W.BOOL
    if not fn(C.byref(source),None,None,None,None,1,C.byref(target)):raise RuntimeError('Windows kon de OpenRouter-sleutel niet veilig lezen of opslaan.')
    kernel.LocalFree.argtypes=[C.c_void_p];kernel.LocalFree.restype=C.c_void_p
    try:return C.string_at(target.data,target.size)
    finally:kernel.LocalFree(target.data)

def save_key(key):
    if not isinstance(key,str) or not key.startswith('sk-or-') or not 24<=len(key)<=512 or re.search(r'\s',key):
        raise ValueError('Gebruik een OpenRouter-API-sleutel (sk-or-...), geen OpenAI-sleutel.')
    encrypted=crypt(key.encode('utf-8'));SECRET_FILE.parent.mkdir(exist_ok=True)
    temporary=SECRET_FILE.with_suffix('.tmp');temporary.write_bytes(encrypted);temporary.replace(SECRET_FILE)

def key_value():
    if SECRET_FILE.exists():return crypt(SECRET_FILE.read_bytes(),True).decode('utf-8')
    key=os.environ.get('OPENROUTER_API_KEY','').strip()
    if key:return key
    env=ROOT/'.env.local'
    if env.exists():
        for line in env.read_text(encoding='utf-8').splitlines():
            if line.startswith('OPENROUTER_API_KEY='):return line.split('=',1)[1].strip().strip('"').strip("'")
    return ''

def status():
    try:key=key_value()
    except (OSError,RuntimeError,UnicodeError):key=''
    return {'configured':key.startswith('sk-or-'),'key_present':bool(key),'model':storage.setting('openrouter_model',''),'free_only':True,'data_collection':storage.setting('openrouter_data_collection','deny')}

def free_text_model(item):
    if not isinstance(item.get('id'),str) or not item['id'].endswith(':free'):return False
    if any(tag in item['id'].lower() for tag in ('content-safety','safeguard','moderation')):return False
    pricing=item.get('pricing') or {}
    try:
        if not all(Decimal(str(pricing[k])).is_finite() and Decimal(str(pricing[k]))==0 for k in ('prompt','completion')):return False
        for key in ('request','image','web_search','internal_reasoning','input_cache_read','input_cache_write'):
            if key in pricing and pricing[key] is not None and Decimal(str(pricing[key]))!=0:return False
    except (KeyError,InvalidOperation,ValueError):return False
    if not isinstance(item.get('context_length'),int) or item['context_length']<8192:return False
    architecture=item.get('architecture') or {}
    return 'text' in architecture.get('input_modalities',[]) and 'text' in architecture.get('output_modalities',[])

async def catalogue(refresh=False):
    global _catalog,_catalog_at
    async with _lock:
        if not refresh and _catalog and time.monotonic()-_catalog_at<300:return list(_catalog)
        try:
            async with httpx.AsyncClient(timeout=12,trust_env=False) as client:
                response=await client.get(BASE+'/models');response.raise_for_status();data=response.json()['data']
        except Exception:raise RuntimeError('Gratis OpenRouter-modellen konden niet worden opgehaald.') from None
        _catalog=[{'id':m['id'],'name':m.get('name',m['id']),'context_length':m.get('context_length'),'supported_parameters':m.get('supported_parameters',[])} for m in data if free_text_model(m)]
        _catalog.sort(key=lambda m:m['name'].casefold());_catalog_at=time.monotonic()
        return list(_catalog)

async def select_model(identifier):
    if identifier not in {m['id'] for m in await catalogue(refresh=True)}:raise ValueError('Kies een momenteel beschikbaar gratis tekstmodel uit de lijst.')
    storage.set_setting('openrouter_model',identifier)

def request_body(payload,model,data_collection='deny'):
    if data_collection not in ('deny','allow'):raise ValueError('Onbekende privacykeuze.')
    body=dict(payload);body['model']=model['id'];body.pop('temperature',None)
    body['provider']={'allow_fallbacks':False,'data_collection':data_collection,'sort':'latency','max_price':{'prompt':0,'completion':0,'request':0}}
    # No random router, tools, paid fallback list or automatic retries.
    body.pop('models',None);body.pop('tools',None);body['plugins']=[]
    if 'reasoning' in model.get('supported_parameters',[]):body['reasoning']={'enabled':False,'exclude':True}
    return body

async def complete(payload):
    key=key_value()
    if not key:raise RuntimeError('Voeg eerst je OpenRouter-sleutel toe in Instellingen > OpenRouter.')
    if not key.startswith('sk-or-'):raise RuntimeError('De ingestelde sleutel is geen OpenRouter-sleutel.')
    selected=storage.setting('openrouter_model','')
    if not selected:raise RuntimeError('Kies eerst een gratis OpenRouter-model in Instellingen.')
    # Recheck before sending text. Provider price ceilings also protect changes after this fetch.
    model=next((m for m in await catalogue() if m['id']==selected),None)
    if not model:raise RuntimeError('Het gekozen model is niet meer als gratis beschikbaar. Kies een ander model.')
    body=request_body(payload,model,storage.setting('openrouter_data_collection','deny'))
    try:
        async with httpx.AsyncClient(timeout=30,trust_env=False) as client:
            response=await client.post(BASE+'/chat/completions',headers={'Authorization':'Bearer '+key,'X-OpenRouter-Title':'Flow Lab'},json=body)
    except httpx.HTTPError:raise RuntimeError('OpenRouter reageert niet op tijd. Je transcriptie blijft behouden.') from None
    errors={401:'OpenRouter accepteert de sleutel niet.',402:'OpenRouter blokkeert dit verzoek door een account- of kredietlimiet.',403:'OpenRouter weigert dit verzoek. Controleer je account en privacybeleid.',404:'Geen geschikte gratis provider gevonden onder de gekozen prijs- en privacyvoorwaarden. Ook je OpenRouter-accountbeleid blijft gelden.',429:'Het gratis model is druk of de OpenRouter-limiet is bereikt. Probeer later opnieuw of gebruik lokaal.'}
    if response.status_code!=200:raise RuntimeError(errors.get(response.status_code,'OpenRouter kon de tekst niet opmaken (HTTP '+str(response.status_code)+').'))
    try:
        result=response.json()
        if result.get('error') or not result.get('choices'):raise ValueError()
        choice=result['choices'][0];content=choice.get('message',{}).get('content')
        if not isinstance(content,str) or not content.strip() or choice.get('finish_reason') in ('length','error','content_filter','tool_calls'):raise ValueError()
        return result
    except (ValueError,TypeError,KeyError,IndexError):raise RuntimeError('OpenRouter gaf geen volledig bruikbaar opmaakresultaat terug; je transcriptie blijft behouden.') from None

async def check_key():
    key=key_value()
    if not key:raise RuntimeError('Er is nog geen OpenRouter-sleutel opgeslagen.')
    if not key.startswith('sk-or-'):raise RuntimeError('De ingestelde sleutel is geen OpenRouter-sleutel.')
    try:
        async with httpx.AsyncClient(timeout=12,trust_env=False) as client:
            r=await client.get(BASE+'/key',headers={'Authorization':'Bearer '+key})
        if r.status_code!=200:raise RuntimeError()
        data=r.json()['data'];quota=data.get('free_model_daily_requests') or {}
        return {'valid':True,'free_requests':{k:quota.get(k) for k in ('used','limit','remaining')}}
    except Exception:raise RuntimeError('Sleutel of quotum kon niet worden gecontroleerd.') from None
