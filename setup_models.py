"""Download pinned public runtime/model artifacts, verify digests, never run installers."""
import argparse, concurrent.futures, hashlib, json, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as r: return json.load(r)

def fetch(url, target, expected=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    def digest(p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(4*1024*1024), b''): h.update(b)
        return h.hexdigest()
    if target.exists() and expected and digest(target)==expected: return expected
    temp=target.with_suffix(target.suffix+'.part')
    with urllib.request.urlopen(url,timeout=120) as resp, temp.open('wb') as out:
        while chunk:=resp.read(4*1024*1024): out.write(chunk)
    actual=digest(temp)
    if expected and actual!=expected: raise ValueError('Hash mismatch: '+target.name)
    temp.replace(target)
    return actual

def runtime(repo, tag, suffix, destination):
    d=get_json(f'https://api.github.com/repos/{repo}/releases/tags/{tag}')
    a=next(x for x in d['assets'] if x['name'].endswith(suffix))
    expected=(a.get('digest') or '').removeprefix('sha256:')
    if not expected:
        c=next(x for x in d['assets'] if x['name']==a['name']+'.sha256')
        with urllib.request.urlopen(c['browser_download_url'],timeout=30) as r: expected=r.read().decode().split()[0]
    archive=ROOT/'runtime/downloads'/a['name']
    h=fetch(a['browser_download_url'],archive,expected)
    dest=(ROOT/'runtime'/destination).resolve(); dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            if not (dest/item.filename).resolve().is_relative_to(dest): raise ValueError('Unsafe archive path')
        z.extractall(dest)
    print('Ready runtime:', destination, flush=True)
    return {'kind':'runtime','repo':repo,'revision':tag,'file':a['name'],'sha256':h,'path':str(dest)}

def model(repo, rev, filename):
    d=get_json(f'https://huggingface.co/api/models/{repo}/revision/{rev}?blobs=true')
    a=next(x for x in d['siblings'] if x['rfilename']==filename)
    expected=a.get('lfs',{}).get('sha256')
    if not expected: raise ValueError('Missing upstream LFS digest: '+filename)
    p=ROOT/'models'/filename
    h=fetch(f'https://huggingface.co/{repo}/resolve/{rev}/{filename}',p,expected)
    print('Ready model:', filename, flush=True)
    return {'kind':'model','repo':repo,'revision':rev,'file':filename,'sha256':h,'path':str(p)}

def download_jobs(legacy=False):
    qwen=(model,('bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF','ae44f08e1392f39c0e474af10c3ff8355c8b6688','Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf'))
    if not legacy:return [qwen]
    return [
        (runtime,('NVIDIA/NeMo-Speech.cpp','v0.2.0','windows-x86_64-cuda.zip','nemo')),
        (runtime,('ggml-org/llama.cpp','b11658','bin-win-vulkan-x64.zip','llama')),
        (runtime,('ggml-org/whisper.cpp','b5454','win-cuda-12.4.0-x64.zip','whisper')),
        (model,('nvidia/parakeet-tdt-0.6b-v3','541d1f99c6b0c3cd0b11a95167540bb8edefd82b','parakeet-tdt-0.6b-v3.q8_0.gguf')),
        (model,('ggerganov/whisper.cpp','5359861c739e955e79d9a303bcbc70fb988958b1','ggml-large-v3-turbo-q5_0.bin')),
        qwen,
    ]

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--legacy-runtimes',action='store_true');args=parser.parse_args()
    jobs=download_jobs(args.legacy_runtimes)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(f,*args):args for f,args in jobs}
        for fut in concurrent.futures.as_completed(futures):
            try: results.append(fut.result())
            except Exception as e: results.append({'error':str(e),'job':futures[fut]}); print('Download failed:',str(e),flush=True)
            (ROOT/'model-manifest.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
    if any('error' in row for row in results):raise SystemExit(1)
