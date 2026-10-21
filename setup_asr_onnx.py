"""Download pinned model data and opt in to the separate ONNX runtime."""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from local_asr import checked_files,model_folder
from runtime_trust import verify_publisher

ROOT=Path(__file__).resolve().parent

def setup(enable=False):
    lock=json.loads((ROOT/'asr-onnx-lock.json').read_text(encoding='utf-8'))
    folder=model_folder(ROOT,lock);folder.mkdir(parents=True,exist_ok=True)
    for name,digest in lock['files'].items():
        path=folder/name
        if path.exists():
            try:checked_files(folder,{name:digest});continue
            except RuntimeError:pass
        url='https://huggingface.co/'+lock['model_repo']+'/resolve/'+lock['model_revision']+'/'+name
        temporary=path.with_suffix(path.suffix+'.download')
        print('Download '+name,flush=True);urllib.request.urlretrieve(url,temporary)
        with temporary.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=digest:raise RuntimeError('Downloadhash wijkt af: '+name)
        temporary.replace(path)
    checked_files(folder,lock['files'])
    if enable:
        import sys
        if sys.platform=='win32':
            native=Path(sys.prefix)/'Lib/site-packages/onnxruntime/capi';checked_files(native,lock['windows_native'])
            verify_publisher(native,'CN=Microsoft Corporation,')
        config=ROOT/'data/local-asr-runtime.json';config.parent.mkdir(exist_ok=True)
        config.write_text(json.dumps({'backend':'onnx-parakeet','providers':['CPUExecutionProvider']},indent=2)+'\n',encoding='utf-8')
    print('ONNX-model gecontroleerd. '+('Lokale ONNX-herkenning geactiveerd.' if enable else 'Nog niet geactiveerd.'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--enable',action='store_true');args=parser.parse_args();setup(args.enable)
