"""Local bounded placement diagnostics, without transcripts or clipboard data."""
import json
from pathlib import Path
import threading
import time

RETENTION_SECONDS=30*86400
MAX_RECORDS=5000
MAX_READ_BYTES=8*1024*1024
_lock=threading.RLock()
_last_prune={}
FIELDS={'time','attempt_id','recording_id','operation','status','reason','stage','failed_stage',
        'clipboard_restore','clipboard_formats','failed_format','target_hwnd','target_editable',
        'capture_reason','capabilities','timings'}

def write_report(directory,report):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    safe={key:value for key,value in report.items() if key in FIELDS}
    with _lock:
        (directory/'desktop-last-insertion.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2),encoding='utf-8')
        with (directory/'desktop-insertions.jsonl').open('a',encoding='utf-8') as output:
            output.write(json.dumps(safe,ensure_ascii=False,separators=(',',':'))+'\n')

def prune_reports(directory,now=None,force=False):
    directory=Path(directory);now=time.time() if now is None else now
    with _lock:
        if not force and now-_last_prune.get(str(directory),0)<3600:return
        path=directory/'desktop-insertions.jsonl';last=directory/'desktop-last-insertion.json'
        if not path.exists() and last.exists():
            try:write_report(directory,json.loads(last.read_text(encoding='utf-8')))
            except (OSError,ValueError):pass
        if path.exists():
            with path.open('rb') as source:
                offset=max(0,path.stat().st_size-MAX_READ_BYTES);source.seek(offset)
                if offset:source.readline()
                lines=source.readlines()
            kept=[]
            for line in lines:
                try:
                    value=json.loads(line.decode('utf-8'))
                    if isinstance(value.get('time'),(int,float)) and value['time']>=now-RETENTION_SECONDS:
                        kept.append({key:item for key,item in value.items() if key in FIELDS})
                except (ValueError,UnicodeError,AttributeError):continue
            directory.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.tmp')
            temporary.write_text(''.join(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n' for value in kept[-MAX_RECORDS:]),encoding='utf-8')
            temporary.replace(path)
        _last_prune[str(directory)]=now
