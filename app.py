import asyncio, json, time, uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from engines import ROOT, APP_PORT, ASR_MODELS, FORMAT_MODELS, MAX_SECONDS, CloudStream, workers, format_text, local_transcribe, run_clip, read_wav, silent,prepare_local
import storage
from personalization import snippet_preview
from limits import MAX_WAV_BYTES,MAX_TEXT_CHARS,LIMIT_MESSAGE

ORIGINS={f'http://127.0.0.1:{APP_PORT}',f'http://localhost:{APP_PORT}'}
gate=asyncio.Lock()

@asynccontextmanager
async def lifespan(app):
    storage.prune()
    async def retention():
        while True:
            await asyncio.sleep(3600);storage.prune()
    task=asyncio.create_task(retention())
    try:yield
    finally:
        task.cancel();workers.close()

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])

@app.middleware('http')
async def protect(request:Request,call_next):
    if request.method not in ('GET','HEAD') and request.headers.get('origin') not in ORIGINS:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Open deze proef via localhost.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Content-Security-Policy']=f"default-src 'self'; connect-src 'self' ws://127.0.0.1:{APP_PORT} ws://localhost:{APP_PORT}; media-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
    response.headers['Cache-Control']='no-store'
    return response

@app.get('/')
async def index():return FileResponse(ROOT/'web/index.html')

@app.get('/api/status')
async def status():
    return {'app':'flow-lab','cloud_configured':(ROOT/'.env.local').is_file(),'local_installed':all((ROOT/'models'/n).exists() for n in ['parakeet-tdt-0.6b-v3.q8_0.gguf','ggml-large-v3-turbo-q5_0.bin','Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf']),'busy':gate.locked(),'version':'0.2.0','max_seconds':MAX_SECONDS,'history_days':storage.RETENTION_DAYS}

class TextInput(BaseModel):
    text:str=Field(max_length=MAX_TEXT_CHARS)
    formatter:str='cloud-mini'
    style:str='bericht'
    paragraphs:str='normaal'

def remember(result,raw,source,engine,formatter,style,paragraphs,duration=None):
    metadata={k:result.get(k) for k in ('asr_ms','format_ms','after_stop_ms','warning','snippets')}
    metadata.update({'source':source,'engine':engine,'formatter':formatter,'style':style,'paragraphs':paragraphs,'duration_s':duration})
    result['history_id']=storage.add_history(raw,result['text'],metadata)
    return result

@app.get('/api/library')
async def library():
    return {'dictionary':storage.entries('dictionary'),'snippets':storage.entries('snippet')}

class EntryInput(BaseModel):
    id:str|None=None
    name:str=Field(default='',max_length=160)
    aliases:list[str]=Field(max_length=60)
    value:str=Field(max_length=20000)
    enabled:bool=True

@app.post('/api/library/{kind}')
async def save_library(kind:str,data:EntryInput):
    try:return {'id':storage.save_entry(kind,data.model_dump())}
    except ValueError as e:raise HTTPException(400,str(e))

@app.delete('/api/library/{kind}/{identifier}')
async def delete_library(kind:str,identifier:str):
    if kind not in ('dictionary','snippet'):raise HTTPException(400,'Onbekend type.')
    storage.delete_entry(kind,identifier);return {'ok':True}

@app.get('/api/history')
async def list_history(q:str=Query(default='',max_length=200),limit:int=Query(default=50,ge=1,le=100),offset:int=Query(default=0,ge=0)):
    return storage.history(q,limit,offset)

@app.delete('/api/history/{identifier}')
async def remove_history(identifier:str):
    storage.delete_history(identifier);return {'ok':True}

@app.post('/api/expand')
async def expand(data:TextInput):return snippet_preview(data.text)

def validate(engine,formatter):
    if engine not in (*ASR_MODELS,'parakeet','whisper','hybrid-parakeet'):raise ValueError('Onbekende herkenner.')
    if formatter not in (*FORMAT_MODELS,'local','verbatim'):raise ValueError('Onbekende opmaakmotor.')
    if engine in ('parakeet','whisper') and formatter not in ('local','verbatim'):raise ValueError('Offline gebruikt uitsluitend lokale opmaak.')

@app.post('/api/format')
async def format_route(data:TextInput,request:Request):
    if gate.locked():raise HTTPException(409,'Er loopt al een proef.')
    async with gate:
        try:
            result=await format_text(data.text,data.formatter,data.style,paragraphs=data.paragraphs)
            if await request.is_disconnected():return result
            return remember(result,data.text,'opmaak',None,data.formatter,data.style,data.paragraphs)
        except (ValueError,RuntimeError) as e:raise HTTPException(400,str(e))

@app.post('/api/warm')
async def warm(request:Request):
    data=await request.json();engine=data.get('engine'); formatter=data.get('formatter')
    try:validate(engine,formatter)
    except ValueError as e:raise HTTPException(400,str(e))
    if gate.locked():raise HTTPException(409,'Er loopt al een proef.')
    async with gate:
        try:
            await prepare_local('parakeet' if engine=='hybrid-parakeet' else engine,formatter)
            return {'ready':True}
        except RuntimeError as e:raise HTTPException(400,str(e))

@app.post('/api/clip')
async def clip(request:Request):
    engine=request.query_params.get('engine','parakeet');formatter=request.query_params.get('formatter','local');style=request.query_params.get('style','bericht');paragraphs=request.query_params.get('paragraphs','normaal')
    try:validate(engine,formatter)
    except ValueError as e:raise HTTPException(400,str(e))
    if gate.locked():raise HTTPException(409,'Er loopt al een proef.')
    audio=bytearray()
    async for chunk in request.stream():
        audio.extend(chunk)
        if len(audio)>MAX_WAV_BYTES:raise HTTPException(413,'Maximaal 128 MB.')
    async with gate:
        try:
            pcm=read_wav(bytes(audio));result=await run_clip(pcm,engine,formatter,style,paragraphs=paragraphs)
            if await request.is_disconnected():return result
            return remember(result,result['raw'],'bestand',engine,formatter,style,paragraphs,len(pcm)/48000)
        except Exception as e:raise HTTPException(400,str(e) if isinstance(e,(ValueError,RuntimeError)) else 'Het WAV-bestand kon niet worden verwerkt.')

@app.websocket('/api/record')
async def record(ws:WebSocket):
    if ws.headers.get('origin') not in ORIGINS:
        await ws.close(code=1008);return
    await ws.accept()
    if gate.locked():await ws.send_json({'type':'error','message':'Er loopt al een proef.'});await ws.close();return
    stream=None
    async with gate:
        try:
            cfg=await asyncio.wait_for(ws.receive_json(),10)
            engine=cfg.get('engine','cloud-live');original_engine=engine;formatter=cfg.get('formatter','cloud-mini');style=cfg.get('style','bericht');paragraphs=cfg.get('paragraphs','normaal')
            validate(engine,formatter)
            if engine=='hybrid-parakeet':engine='parakeet'
            async def partial(text):await ws.send_json({'type':'partial','text':text})
            if engine in ASR_MODELS:
                stream=CloudStream(engine,partial);await stream.start()
            await prepare_local(engine,formatter)
            await ws.send_json({'type':'ready','max_seconds':MAX_SECONDS})
            audio=bytearray(); began=time.perf_counter()
            while True:
                msg=await asyncio.wait_for(ws.receive(),MAX_SECONDS+15)
                if msg['type']=='websocket.disconnect':return
                if time.perf_counter()-began>MAX_SECONDS+10:raise ValueError(LIMIT_MESSAGE)
                if msg.get('bytes') is not None:
                    chunk=msg['bytes']
                    if len(chunk)%2 or len(chunk)>48000:raise ValueError('Ongeldig audioblok.')
                    audio.extend(chunk)
                    if len(audio)>MAX_SECONDS*48000:raise ValueError(LIMIT_MESSAGE)
                    if stream:await stream.append(chunk)
                elif msg.get('text'):
                    event=json.loads(msg['text'])
                    if event.get('type')=='cancel':return
                    if event.get('type')=='stop':break
            stopped=time.perf_counter()
            if silent(bytes(audio)):
                await ws.send_json({'type':'done','raw':'','text':'','asr_ms':0,'format_ms':0,'after_stop_ms':0,'warning':'Geen hoorbare spraak gevonden.'});return
            async def finalize():
                raw=await stream.finish() if stream else await local_transcribe(bytes(audio),engine)
                asr_ms=(time.perf_counter()-stopped)*1000
                await ws.send_json({'type':'recognized','text':raw})
                try:formatted=await format_text(raw,formatter,style,paragraphs=paragraphs)
                except Exception:
                    formatted={'text':raw,'ms':0,'warning':'Opmaak mislukt. De herkende tekst is behouden; controleer en kopieer deze zelf.'}
                return {'type':'done','raw':raw,'text':formatted['text'],'asr_ms':round(asr_ms,1),'format_ms':formatted['ms'],'after_stop_ms':round((time.perf_counter()-stopped)*1000,1),'warning':formatted['warning'],'snippets':formatted.get('snippets',[])}
            async def cancelled():
                while True:
                    event=await ws.receive()
                    if event['type']=='websocket.disconnect':return
                    if event.get('text') and json.loads(event['text']).get('type')=='cancel':return
            processing=asyncio.create_task(finalize());cancellation=asyncio.create_task(cancelled())
            try:
                finished,_=await asyncio.wait([processing,cancellation],return_when=asyncio.FIRST_COMPLETED)
                if cancellation in finished:return
                result=await processing
                remember(result,result['raw'],'microfoon',original_engine,formatter,style,paragraphs,len(audio)/48000)
                await ws.send_json(result)
            finally:
                for task in (processing,cancellation):
                    if not task.done():task.cancel()
                await asyncio.gather(processing,cancellation,return_exceptions=True)
        except WebSocketDisconnect:pass
        except Exception as e:
            try:await ws.send_json({'type':'error','message':str(e) if isinstance(e,(ValueError,RuntimeError)) else 'De proef stopte door een verbindings- of opnamefout.'})
            except Exception:pass
        finally:
            if stream:await stream.close()
            try:await ws.close()
            except Exception:pass

app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')
