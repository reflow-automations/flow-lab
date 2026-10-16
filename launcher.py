"""Single-flight Windows startup with bounded waits and visible progress."""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

NO_WINDOW=0x08000000
URL='http://127.0.0.1:17865'

class LaunchLock:
    def __init__(self,root):
        self.kernel=C.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateMutexW.argtypes=[C.c_void_p,W.BOOL,W.LPCWSTR];self.kernel.CreateMutexW.restype=W.HANDLE
        self.kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];self.kernel.WaitForSingleObject.restype=W.DWORD
        self.kernel.ReleaseMutex.argtypes=[W.HANDLE];self.kernel.CloseHandle.argtypes=[W.HANDLE]
        name='Local\\FlowLab.Launch.'+hashlib.sha256(str(root).casefold().encode()).hexdigest()[:20]
        self.handle=self.kernel.CreateMutexW(None,False,name)
        if not self.handle:raise OSError('Opstartvergrendeling niet beschikbaar.')
        self.acquired=self.kernel.WaitForSingleObject(self.handle,0) in (0,0x80)
    def close(self):
        if self.acquired:self.kernel.ReleaseMutex(self.handle)
        self.kernel.CloseHandle(self.handle)

def process_alive(pid,expected_path):
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];kernel.WaitForSingleObject.restype=W.DWORD
    kernel.CloseHandle.argtypes=[W.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
    handle=kernel.OpenProcess(0x101000,False,pid)
    if not handle:return False
    try:
        size=W.DWORD(32768);buffer=C.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle,0,buffer,C.byref(size)):return False
        return Path(buffer.value).resolve()==Path(expected_path).resolve() and kernel.WaitForSingleObject(handle,0)==258
    finally:kernel.CloseHandle(handle)

def service_status():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(URL+'/api/status',timeout=.6) as response:data=json.load(response)
    except (OSError,ValueError):return None
    if data.get('app')!='flow-lab':raise RuntimeError('Poort 17865 wordt door een ander programma gebruikt.')
    return data

def port_open():
    try:
        with socket.create_connection(('127.0.0.1',17865),timeout=.3):return True
    except OSError:return False

def helper_command(root,action):
    result=subprocess.run([str(root/'.venv/Scripts/python.exe'),str(root/'desktop_helper.py'),action],
                          cwd=root,capture_output=True,timeout=3,encoding='utf-8',creationflags=NO_WINDOW)
    if result.returncode:raise RuntimeError('Flow Lab-helper reageert niet. Bekijk logs/desktop.stderr.log.')
    if action=='--status':
        try:return json.loads(result.stdout)
        except ValueError:return None

def start_child(root,args,log_prefix):
    env=dict(os.environ,FLOW_LAB_PORT='17865')
    with (root/'logs'/f'{log_prefix}.stdout.log').open('ab') as out, (root/'logs'/f'{log_prefix}.stderr.log').open('ab') as err:
        return subprocess.Popen([str(root/'.venv/Scripts/python.exe'),*args],cwd=root,env=env,
                                stdout=out,stderr=err,creationflags=NO_WINDOW)

def launch(root,desktop_only=False,notify=lambda _:None):
    root=Path(root).resolve();(root/'logs').mkdir(exist_ok=True)
    began=time.monotonic();run_id=uuid.uuid4().hex
    trace={'started_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'launcher_pid':os.getpid(),
           'phases':[],'browser_requested':False,'native_window_requested':not desktop_only}
    log=root/'logs'/f'launcher-{run_id}.json'
    def phase(name):
        trace['phases'].append({'name':name,'elapsed_ms':round((time.monotonic()-began)*1000)})
        log.write_text(json.dumps(trace,indent=2),encoding='utf-8')
    phase('launcher_entered');lock=LaunchLock(root)
    if not lock.acquired:
        phase('existing_launch_in_progress');lock.close();return trace
    try:
        notify('Flow Lab starten...');phase('checking_backend')
        ready=service_status()
        if not ready:
            prior_pid=None
            try:prior_pid=int((root/'logs/app-17865.pid').read_text(encoding='ascii').strip())
            except (OSError,ValueError):pass
            if not port_open() and not (prior_pid and process_alive(prior_pid,root/'.venv/Scripts/python.exe')):
                phase('starting_backend')
                child=start_child(root,['-m','uvicorn','app:app','--host','127.0.0.1','--port','17865','--no-access-log'],'app-17865')
                (root/'logs/app-17865.pid').write_text(str(child.pid),encoding='ascii')
            deadline=time.monotonic()+45
            while not ready:
                notify('Verwerking starten. De app wordt zo geopend...')
                if time.monotonic()>=deadline:raise TimeoutError('Flow Lab is na 45 seconden nog niet gereed. De opstartstappen staan in logs/launcher-last-run.json.')
                time.sleep(.15);ready=service_status()
        trace['server_ready']=True;phase('backend_ready')
        state=helper_command(root,'--status')
        if not state:
            phase('starting_desktop');notify('Appvenster starten...')
            child=start_child(root,[str(root/'desktop_helper.py')],'desktop')
            (root/'logs/desktop.pid').write_text(str(child.pid),encoding='ascii')
            deadline=time.monotonic()+15
            while not state:
                notify('Appvenster starten...')
                if time.monotonic()>=deadline:raise TimeoutError('Het appvenster reageert nog niet. Bekijk logs/desktop.stderr.log.')
                time.sleep(.15);state=helper_command(root,'--status')
        phase('desktop_ready');trace['desktop_pid']=state['pid']
        if not desktop_only:helper_command(root,'--open');phase('window_requested')
        trace['ok']=True;phase('complete')
        return trace
    except Exception as exc:
        trace['ok']=False;trace['error']=str(exc);phase('failed');raise
    finally:
        trace['elapsed_ms']=round((time.monotonic()-began)*1000)
        log.write_text(json.dumps(trace,indent=2),encoding='utf-8')
        (root/'logs/launcher-last-run.json').write_text(json.dumps(trace,indent=2),encoding='utf-8')
        lock.close()

def main():
    root=Path(__file__).resolve().parent;desktop_only='--desktop-only' in sys.argv
    window=None;label=None
    def notify(message):
        nonlocal window,label
        if desktop_only:return
        if window is None:
            import tkinter as tk
            from tkinter import ttk
            window=tk.Tk();window.title('Flow Lab starten');window.geometry('430x110');window.resizable(False,False)
            window.protocol('WM_DELETE_WINDOW',window.withdraw)
            label=ttk.Label(window,padding=20,wraplength=390);label.pack(fill='both',expand=True)
        label.configure(text=message);window.update()
    try:launch(root,desktop_only,notify)
    except Exception as exc:
        if not desktop_only:
            from tkinter import messagebox
            messagebox.showerror('Flow Lab starten',str(exc),parent=window)
        else:print(str(exc),file=sys.stderr)
        return 1
    finally:
        if window:window.destroy()
    return 0

if __name__=='__main__':raise SystemExit(main())
