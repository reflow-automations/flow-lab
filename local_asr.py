"""Offline Parakeet ONNX backend. No downloads or cloud fallback at runtime."""
import hashlib
import importlib.metadata
import json
import sys
import threading
from pathlib import Path

import numpy as np

def onnx_enabled(root):
    path=Path(root)/'data/local-asr-runtime.json'
    if not path.exists():return True
    try:config=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):raise RuntimeError('Lokale ASR-configuratie is niet leesbaar.') from None
    if config.get('backend')!='onnx-parakeet':raise RuntimeError('Onbekende lokale ASR-runtime.')
    return True

def checked_files(folder,files):
    folder=Path(folder).resolve()
    for name,digest in files.items():
        path=folder/name
        if Path(name).name!=name or path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(folder):
            raise RuntimeError('Een lokaal model- of runtimebestand ontbreekt: '+name)
        with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=digest:raise RuntimeError('Lokaal bestand gewijzigd: '+name)

def model_folder(root,lock):
    base=Path(root)/'models';name=lock['model_directory'];folder=base/name
    if Path(name).name!=name or folder.is_symlink() or not folder.resolve().is_relative_to(base.resolve()):
        raise RuntimeError('Ongeldig lokaal modelpad.')
    return folder

def model_present(root):
    try:
        lock=json.loads((Path(root)/'asr-onnx-lock.json').read_text(encoding='utf-8'))
        folder=model_folder(root,lock)
        return all((folder/name).is_file() for name in lock['files'])
    except (OSError,ValueError,KeyError,RuntimeError):return False

def audio_spans(audio,rate=16000):
    """All samples exactly once, max 24 s. Prefer quiet boundaries from 16-24 s."""
    start=0;maximum=24*rate;minimum=16*rate;window=rate//10
    while len(audio)-start>maximum:
        candidates=range(start+minimum,start+maximum-window+1,window)
        cut=min(candidates,key=lambda p:float(np.mean(np.square(audio[p:p+window]))))+window//2
        yield start,cut;start=cut
    if start<len(audio):yield start,len(audio)

class OnnxParakeet:
    def __init__(self,root):
        self.root=Path(root);self.model=None;self.lock=threading.RLock()

    def ensure(self):
        with self.lock:
            if self.model is not None:return
            lock=json.loads((self.root/'asr-onnx-lock.json').read_text(encoding='utf-8'))
            for package,version in lock['packages'].items():
                try:installed=importlib.metadata.version(package)
                except importlib.metadata.PackageNotFoundError:raise RuntimeError('Spraakruntime ontbreekt. Voer Setup-FlowLab.ps1 -DownloadModels uit volgens README.') from None
                if installed!=version:raise RuntimeError('Onverwachte versie van '+package+'. Controleer de ONNX-installatie.')
            if sys.platform=='win32':
                native=Path(sys.prefix)/'Lib/site-packages/onnxruntime/capi'
                checked_files(native,lock['windows_native'])
            folder=model_folder(self.root,lock)
            checked_files(folder,lock['files'])
            # Native hashes are checked before importing the signed Microsoft runtime.
            import onnxruntime as ort
            import onnx_asr
            options=ort.SessionOptions();options.intra_op_num_threads=6;options.inter_op_num_threads=1
            self.model=onnx_asr.load_model('nemo-parakeet-tdt-0.6b-v3',path=folder,quantization='int8',
                                         providers=['CPUExecutionProvider'],sess_options=options)

    def recognize(self,pcm16):
        with self.lock:
            self.ensure()
            audio=np.frombuffer(pcm16,dtype='<i2').astype(np.float32)/32768
            if len(audio)>300*16000:raise ValueError('Maximaal vijf minuten audio.')
            return ' '.join(text for start,end in audio_spans(audio)
                            if (text:=self.model.recognize(audio[start:end],sample_rate=16000).strip()))

    def close(self):
        with self.lock:self.model=None
