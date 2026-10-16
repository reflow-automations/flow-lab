"""Bounded, user-owned recovery audio. No provider calls or automatic replay."""
import io
import json
import threading
import time
import uuid
import wave
from pathlib import Path
from limits import MAX_PCM_BYTES

MAX_PENDING=3

def identifier(value):
    return str(uuid.UUID(str(value)))

def wav_bytes(pcm):
    stream=io.BytesIO()
    with wave.open(stream,'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(24000);output.writeframes(pcm)
    return stream.getvalue()

def protect(data,decrypt=False):
    # Reuse the existing Windows DPAPI primitive; this performs no API request.
    from openrouter_provider import crypt
    try:return crypt(data,decrypt)
    except Exception as exc:raise RuntimeError('Windows kon de herstelopname niet ontsleutelen of opslaan.') from exc

class RecoveryStore:
    def __init__(self,path):
        self.path=Path(path);self.memory={};self.lock=threading.RLock()

    def ids(self):
        with self.lock:
            found=set(self.memory)
            if self.path.exists():
                for file in self.path.glob('*.dpapi'):
                    try:found.add(identifier(file.stem))
                    except ValueError:continue
            return sorted(found)

    def save(self,recording_id,pcm,config,partial=False):
        key=identifier(recording_id)
        if not pcm:return
        if len(pcm)>MAX_PCM_BYTES or len(pcm)%2:raise ValueError('Ongeldige herstelopname.')
        with self.lock:
            if key not in self.ids() and len(self.ids())>=MAX_PENDING:
                raise RuntimeError('Herstel eerst een eerdere opname of verwijder die bewust.')
            metadata={'id':key,'created_at':time.time(),'duration_s':len(pcm)/48000,
                      'config':{k:config[k] for k in ('engine','formatter','style','paragraphs') if k in config},
                      'partial':bool(partial),'persistent':True}
            # Keep the exact samples even if disk protection/storage fails.
            self.memory[key]=(metadata,bytes(pcm))
            try:
                header=json.dumps(metadata,ensure_ascii=False).encode('utf-8')
                encrypted=protect(len(header).to_bytes(4,'little')+header+pcm)
                self.path.mkdir(parents=True,exist_ok=True)
                temp=self.path/(key+'.tmp');temp.write_bytes(encrypted);temp.replace(self.path/(key+'.dpapi'))
                self.memory.pop(key,None)
            except Exception:
                metadata['persistent']=False

    def load(self,recording_id):
        key=identifier(recording_id)
        with self.lock:
            if key in self.memory:return self.memory[key]
            file=self.path/(key+'.dpapi')
            if file.stat().st_size>MAX_PCM_BYTES+65536:raise ValueError('Herstelbestand is te groot.')
            payload=protect(file.read_bytes(),True);size=int.from_bytes(payload[:4],'little')
            if not 0<size<8192 or 4+size>len(payload):raise ValueError('Herstelbestand is beschadigd.')
            metadata=json.loads(payload[4:4+size].decode('utf-8'));pcm=payload[4+size:]
            if metadata['id']!=key or not 0<len(pcm)<=MAX_PCM_BYTES or len(pcm)%2:raise ValueError('Herstelbestand is beschadigd.')
            return metadata,pcm

    def entries(self):
        result=[]
        for key in self.ids():
            try:metadata,_=self.load(key);result.append(dict(metadata))
            except Exception:result.append({'id':key,'created_at':0,'duration_s':0,'unreadable':True,'persistent':True})
        return sorted(result,key=lambda entry:entry['created_at'])

    def discard(self,recording_id):
        key=identifier(recording_id)
        with self.lock:
            (self.path/(key+'.dpapi')).unlink(missing_ok=True)
            (self.path/(key+'.tmp')).unlink(missing_ok=True)
            self.memory.pop(key,None)
