"""Bounded, user-owned recovery audio. No provider calls or automatic replay."""
import io
import json
import threading
import time
import uuid
import wave
from pathlib import Path
from limits import MAX_PCM_BYTES

RETENTION_SECONDS=24*60*60
MAX_STORAGE_BYTES=500*1024*1024

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
        self.path=Path(path);self.memory={};self.lock=threading.RLock();self.active=set()

    def write_metadata(self,metadata):
        key=identifier(metadata['id'])
        if key in self.memory:self.memory[key]=(dict(metadata),self.memory[key][1])
        if not metadata.get('persistent',True):return
        self.path.mkdir(parents=True,exist_ok=True)
        temp=self.path/(key+'.json.tmp');temp.write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf-8')
        temp.replace(self.path/(key+'.json'))

    def metadata(self,key):
        key=identifier(key)
        if key in self.memory:return dict(self.memory[key][0])
        try:
            metadata=json.loads((self.path/(key+'.json')).read_text(encoding='utf-8'))
            if metadata['id']!=key or not isinstance(metadata['created_at'],(int,float)):raise ValueError('Invalid index')
            return metadata
        except (OSError,ValueError,KeyError):
            metadata,_=self.load(key);self.write_metadata(metadata);return metadata

    def prune(self,now=None):
        now=time.time() if now is None else now
        with self.lock:
            for key in self.ids():
                if key in self.active:continue
                try:expired=self.metadata(key)['created_at']<=now-RETENTION_SECONDS
                except Exception:continue # Unknown/corrupt files require explicit deletion.
                if expired:self.discard(key)

    def used_bytes(self):
        return sum(len(pcm)+65536 for _,pcm in self.memory.values())+sum(p.stat().st_size for p in self.path.glob('*.dpapi'))

    def can_record(self):
        self.prune()
        return self.used_bytes()+MAX_PCM_BYTES+65536<=MAX_STORAGE_BYTES

    def mark_completed(self,key):
        with self.lock:
            if key not in self.ids():return
            metadata=self.metadata(key);metadata['completed']=True;metadata.pop('retry_id',None)
            self.write_metadata(metadata)

    def retry_id(self,key):
        with self.lock:
            metadata=self.metadata(key)
            if metadata.get('retry_id'):return metadata['retry_id']
            request_id=str(uuid.uuid4()) if metadata.get('completed') else key
            metadata['retry_id']=request_id;self.write_metadata(metadata)
            return request_id

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
            self.prune()
            if key not in self.ids() and self.used_bytes()+len(pcm)+65536>MAX_STORAGE_BYTES:
                raise RuntimeError('Audio-opslag is vol. Verwijder eerst een bewaarde opname.')
            metadata={'id':key,'created_at':time.time(),'duration_s':len(pcm)/48000,
                      'config':{k:config[k] for k in ('engine','formatter','style','paragraphs') if k in config},
                      'partial':bool(partial),'persistent':True,'completed':False}
            # Keep the exact samples even if disk protection/storage fails.
            self.memory[key]=(metadata,bytes(pcm))
            try:
                header=json.dumps(metadata,ensure_ascii=False).encode('utf-8')
                encrypted=protect(len(header).to_bytes(4,'little')+header+pcm)
                self.path.mkdir(parents=True,exist_ok=True)
                temp=self.path/(key+'.tmp');temp.write_bytes(encrypted);temp.replace(self.path/(key+'.dpapi'))
                self.write_metadata(metadata)
                self.memory.pop(key,None)
            except Exception:
                metadata['persistent']=False
                self.memory[key]=(dict(metadata),bytes(pcm))

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
        self.prune()
        result=[]
        for key in self.ids():
            try:result.append(self.metadata(key))
            except Exception:result.append({'id':key,'created_at':0,'duration_s':0,'unreadable':True,'persistent':True})
        return sorted(result,key=lambda entry:entry['created_at'])

    def discard(self,recording_id):
        key=identifier(recording_id)
        with self.lock:
            (self.path/(key+'.dpapi')).unlink(missing_ok=True)
            (self.path/(key+'.tmp')).unlink(missing_ok=True)
            (self.path/(key+'.json')).unlink(missing_ok=True)
            (self.path/(key+'.json.tmp')).unlink(missing_ok=True)
            self.memory.pop(key,None)
