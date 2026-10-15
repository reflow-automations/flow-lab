"""Flow Lab desktop companion. No microphone is opened until the user's hotkey."""
import asyncio
import ctypes as C
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import subprocess
import time
import tkinter as tk
from tkinter import ttk
import uuid
import wave
from collections import deque
from types import SimpleNamespace
import desktop_windows as w
from last_transcript import latest_text
from shortcut_config import shortcut,shortcut_label,KEYS,MODIFIERS,LABELS
from dictation_gesture import DictationGesture
from compact_overlay import CompactOverlay
from limits import MAX_SECONDS,SESSION_TIMEOUT_SECONDS,AudioBudget

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'data/desktop-status.json'
CONFIG = ROOT / 'data/desktop-settings.json'
URL = 'http://127.0.0.1:17865'
QUIT_MESSAGE = 0x8051
SETTINGS_MESSAGE = 0x8052
OPEN_MESSAGE = 0x8053
QUIT_ALL_MESSAGE = 0x8054
PANEL_IDS={0:'home',1:'history',2:'dictionary',3:'snippets',4:'settings',5:'openrouter'}

def stored_status():
    try:
        s = json.loads(STATE.read_text(encoding='utf-8'))
        if w.is_window(s['hwnd']) and w.pid_of(s['hwnd']) == s['pid'] and w.text_of(s['hwnd']) == s['caption']:
            return s
    except Exception:
        pass
    return None

def settings():
    defaults = dict(engine='parakeet', formatter='local', paragraphs='normaal', style='bericht',hotkey='ctrl-shift-space')
    try:
        values = {k.lower(): v for k, v in json.loads(CONFIG.read_text(encoding='utf-8')).items()}
        defaults.update({k: values[k] for k in defaults if k in values})
    except Exception:
        pass
    try:defaults['hotkey']=shortcut(defaults['hotkey'])[0]
    except (ValueError,AttributeError):defaults['hotkey']='ctrl-shift-space'
    return defaults

def amplitude(pcm):
    import array
    samples = array.array('h', pcm)
    return min(1., math.sqrt(sum(x*x for x in samples) / max(1, len(samples))) / 4500)

class Recording:
    def __init__(self, app, ident, target, fixture=None):
        self.app, self.ident, self.target = app, ident, target
        self.fixture = fixture
        self.config = dict(app.config)
        self.audio = queue.Queue()
        self.audio_budget=AudioBudget();self.limit_notified=False
        self.stop = threading.Event()
        self.cancel = threading.Event()
        self.started = time.monotonic()
        self.timings={}
        self.released_at=None
        self.last_sound = self.started
        self.mic = None
        threading.Thread(target=self.run, daemon=True).start()

    def emit(self, kind, *args): self.app.events.put((kind, self.ident, *args))

    def push(self, data):
        if self.cancel.is_set(): return
        data=self.audio_budget.take(data)
        if not data:return
        level = amplitude(data)
        if level > .025: self.last_sound = time.monotonic()
        self.emit('level', level)
        self.audio.put(data)
        if self.audio_budget.full and not self.limit_notified:
            self.limit_notified=True;self.stop.set();self.emit('source_done')

    def source(self):
        try:
            if self.fixture:
                with wave.open(str(self.fixture), 'rb') as audio:
                    if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 24000):
                        raise ValueError('Testaudio moet PCM16 mono 24 kHz zijn')
                    while not self.stop.is_set() and not self.cancel.is_set():
                        chunk = audio.readframes(960)
                        if not chunk: break
                        self.push(chunk)
                        time.sleep(.04)
                self.emit('source_done')
            else:
                self.mic = w.Microphone(self.push)
                self.mic.start()
                capture_started=time.monotonic()
                self.timings['microphone_ready_ms']=round((capture_started-self.started)*1000,1)
                self.emit('listening')
                while not self.stop.wait(.04) and not self.cancel.is_set():
                    if time.monotonic() - capture_started >= MAX_SECONDS+2:
                        self.emit('source_done')
                        break
                self.mic.stop()
        except Exception as exc:
            self.cancel.set()
            self.emit('error', str(exc))
        finally:
            if self.mic: self.mic.close()
            self.audio.put(None)

    async def network(self):
        from websockets.asyncio.client import connect
        async with connect(URL.replace('http', 'ws') + '/api/record', origin=URL, open_timeout=8, max_size=2**22) as socket:
            await socket.send(json.dumps({**self.config, 'style': self.config.get('style','bericht')}))
            ready = False
            async def send():
                nonlocal ready
                while not ready and not self.cancel.is_set(): await asyncio.sleep(.02)
                while not self.cancel.is_set():
                    try: data = self.audio.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(.015)
                        continue
                    if data is None:
                        self.timings['audio_sent_ms']=round((time.monotonic()-self.started)*1000,1)
                        await socket.send(json.dumps({'type': 'stop'}))
                        self.emit('processing')
                        return
                    await socket.send(data)
                await socket.send(json.dumps({'type': 'cancel'}))
            sender = asyncio.create_task(send())
            try:
                deadline = time.monotonic() + SESSION_TIMEOUT_SECONDS
                while time.monotonic() < deadline:
                    if self.cancel.is_set(): return
                    try: message = json.loads(await asyncio.wait_for(socket.recv(), .2))
                    except asyncio.TimeoutError:
                        if not ready and time.monotonic()-self.started>1:self.emit('preparing')
                        continue
                    kind = message.get('type')
                    if kind == 'ready':
                        ready = True
                        self.timings['backend_ready_ms']=round((time.monotonic()-self.started)*1000,1)
                    elif kind == 'done':
                        self.timings['result_ready_ms']=round((time.monotonic()-self.started)*1000,1)
                        self.timings['backend_processing_ms']=message.get('after_stop_ms')
                        if self.released_at is not None:
                            self.timings['release_to_result_ms']=round((time.monotonic()-self.released_at)*1000,1)
                        self.emit('result', message)
                        return
                    elif kind == 'error': raise RuntimeError(message.get('message') or message.get('error') or 'Verwerking mislukt')
                raise TimeoutError('Verwerking duurde te lang')
            finally:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)

    def run(self):
        producer = threading.Thread(target=self.source, daemon=True)
        producer.start()
        try: asyncio.run(self.network())
        except Exception as exc:
            if not self.cancel.is_set(): self.emit('error', str(exc))
        finally:
            self.stop.set()
            producer.join(3)

class Desktop:
    def __init__(self, test=False):
        self.events = queue.Queue()
        self.root_path=ROOT;self.service_url=URL;self.control_window=None
        self.config = settings()
        self.test = test
        self.current = None
        self.last_insertion_message='Dit is een kopie van je laatste tekst. De plaatsingsstatus verschijnt na het dicteren.'
        try:self.last_insertion_message=json.loads((ROOT/'data/desktop-last-status.json').read_text(encoding='utf-8'))['message']
        except (OSError,ValueError,KeyError):pass
        self.ident = 0
        self.last_text = ''
        self.state = 'idle'
        self.gesture = DictationGesture()
        self.stop_requested = False
        self.replay_key = None
        self.replay_registered = False
        self.main_registered = False
        self.saved_state = None
        self.shortcut_dialog = None
        self.levels = deque([0.] * 23, maxlen=23)
        self.uia = w.UiaWorker()
        try:C.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Reflow.FlowLab')
        except OSError:pass
        self.root = tk.Tk()
        self.caption = 'FlowLab.Python.' + str(uuid.uuid4())
        self.root.title(self.caption)
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.overlay=CompactOverlay(self.root,self.cancel,self.stop,self.copy)
        self.label=self.overlay
        self.root.update_idletasks()
        self.hwnd = w.ancestor(self.root.winfo_id(), 2)
        w.set_style(self.hwnd, -20, w.get_style(self.hwnd, -20) | 0x08000000 | 0x80)
        PROC = C.WINFUNCTYPE(w.LRESULT, w.W.HWND, w.W.UINT, w.W.WPARAM, w.W.LPARAM)
        call = w.api(w.user, 'CallWindowProcW', [w.PTR, w.W.HWND, w.W.UINT, w.W.WPARAM, w.W.LPARAM], w.LRESULT)
        def wndproc(hwnd, msg, wp, lp):
            if msg == 0x21: return 3 # MA_NOACTIVATE
            if msg == QUIT_MESSAGE:
                self.events.put(('quit',)); return 0
            if msg == SETTINGS_MESSAGE:
                self.events.put(('shortcut_settings',)); return 0
            if msg == OPEN_MESSAGE:
                self.events.put(('open',PANEL_IDS.get(int(wp),'home')));return 0
            if msg == QUIT_ALL_MESSAGE:
                self.events.put(('quit_all',));return 0
            return call(self.old_proc, hwnd, msg, wp, lp)
        self.proc = PROC(wndproc)
        self.old_proc = w.set_style(self.hwnd, -4, C.cast(self.proc, w.PTR).value)
        w.show(self.hwnd, 0)
        self.hotkeys = w.Hotkeys(self.events, self.config['hotkey'])
        self.tray = None
        self.scratch = None
        self.tests = {}
        self.test_started = False
        self.make_tray()
        if test: self.make_scratch()
        self.root.after(20, self.poll)

    def write_state(self, registered=None):
        if registered is not None: self.main_registered=registered
        STATE.parent.mkdir(exist_ok=True)
        control=getattr(self,'control_window',None)
        main_hwnd=int(w.ancestor(control.root.winfo_id(),2) or 0) if control and control.exists() else None
        main_visible=bool(control and control.exists() and control.root.state()!='withdrawn')
        main_panel=next((key for key,tab in control.tabs.items() if str(tab)==control.notebook.select()),None) if control and control.exists() else None
        STATE.write_text(json.dumps(dict(pid=os.getpid(), hwnd=self.hwnd, caption=self.caption, test=self.test, hotkey=self.config['hotkey'], registered=self.main_registered, replay_hotkey=self.replay_key, replay_registered=self.replay_registered, state=self.state, gesture=self.gesture.mode, controls='hold-double-tap', overlay_size=[156,36], ui='native-tk',main_window=main_hwnd,main_visible=main_visible,main_panel=main_panel), indent=2), encoding='utf-8')

    def display(self, text):
        self.overlay.render(self.state,self.levels,self.gesture.mode=='locked')
        self.label.configure(text=text)
        w.show(self.hwnd, 4) # SW_SHOWNOACTIVATE
        w.set_position(self.hwnd, -1, 0, 0, 0, 0, 0x13)

    def make_tray(self):
        import pystray
        from PIL import Image, ImageDraw
        icon = Image.new('RGB', (64,64), '#163e34')
        draw = ImageDraw.Draw(icon)
        for i,h in enumerate([14,30,44,30,14]): draw.rounded_rectangle((12+i*9,32-h//2,17+i*9,32+h//2), radius=2, fill='#d5f0dd')
        item = pystray.MenuItem
        def event(name, *args): return lambda *_: self.events.put((name, *args))
        self.tray = pystray.Icon('FlowLab', icon, 'Flow Lab: Ctrl+Shift+Spatie', pystray.Menu(
            item('Open Flow Lab', event('open'), default=True),
            item('Snippets beheren', event('open','snippets')),
            item('Woordenboek beheren', event('open','dictionary')),
            item('Geschiedenis', event('open','history')),
            item('Volledig lokaal', event('mode', 'local'), checked=lambda _: self.config['formatter']=='local'),
            item('Lokale audio, cloudopmaak', event('mode', 'cloud-mini'), checked=lambda _: self.config['formatter']=='cloud-mini'),
            item('Lokale audio, OpenRouter gratis', event('mode','openrouter-free'),checked=lambda _:self.config['formatter']=='openrouter-free'),
            item('Sneltoets instellen...', event('shortcut_settings')),
            item('Sneltoets', pystray.Menu(*[item(v[2], event('key', k), checked=lambda _, key=k: self.config['hotkey']==shortcut(key)[0]) for k,v in w.HOTKEYS.items()])),
            item('Kopieer laatste tekst', event('copy')), item('Flow Lab volledig afsluiten', event('quit_all'))))
        threading.Thread(target=self.tray.run, daemon=True).start()

    def update_tray_title(self):
        label=w.REPLAY_KEYS[self.replay_key][2] if self.replay_key else 'niet beschikbaar'
        self.tray.title='Flow Lab: '+shortcut_label(self.config['hotkey'])+' | Laatste plakken: '+label
        self.tray.update_menu()

    def open_app(self,panel='home'):
        from native_app import NativeApp
        if not self.control_window or not self.control_window.exists():self.control_window=NativeApp(self)
        self.control_window.show(panel);self.write_state()

    def quit_all(self):
        if self.state=='shutting_down':return
        self.cancel();self.state='shutting_down';self.write_state()
        if self.control_window and self.control_window.exists():self.control_window.status.set('Flow Lab en lokale modellen worden afgesloten...')
        def stop_services():
            try:
                powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
                result=subprocess.run([str(powershell),'-NoProfile','-File',str(ROOT/'Stop-FlowLab.ps1'),'-SkipHelper'],cwd=ROOT,creationflags=0x08000000,capture_output=True,timeout=25)
                if result.returncode:raise RuntimeError('Stoppen van de lokale processen is niet bevestigd.')
                import httpx
                try:
                    httpx.get(URL+'/api/status',timeout=1)
                except httpx.TransportError:pass
                else:raise RuntimeError('De lokale server is nog bereikbaar.')
                self.events.put(('quit',))
            except Exception as exc:self.events.put(('shutdown_error',str(exc)))
        threading.Thread(target=stop_services,daemon=True).start()

    def shortcut_settings(self):
        if self.state!='idle':
            self.display('Rond eerst je opname af om instellingen te wijzigen.');return
        self.open_app('settings')

    def settings_are_open(self):
        window=getattr(self,'control_window',None)
        return bool(window and window.exists() and window.root.state()!='withdrawn' and
                    w.foreground()==w.ancestor(window.root.winfo_id(),2) and
                    window.notebook.select() in (str(window.tabs['settings']),str(window.tabs['openrouter'])))

    def start(self):
        if self.current or self.state!='idle': return
        self.stop_requested=False
        self.ident += 1
        ident = self.ident
        hwnd = w.foreground()
        self.capture_started=time.monotonic()
        self.released_at=None
        self.state = 'starting'
        self.hotkeys.command('escape', True)
        self.display('Cursor controleren...')
        def capture():
            try: target = self.uia.submit(w.capture_target, hwnd).result(timeout=1.2)
            except Exception: target = w.Target(hwnd, reason='Tekstvak niet controleerbaar: straks kopiëren')
            self.events.put(('captured', ident, target))
        threading.Thread(target=capture, daemon=True).start()

    def stop(self):
        if self.state in ('recording','starting'):
            self.released_at=time.monotonic()
            self.stop_requested=True;self.gesture.mode='processing'
            self.state='processing'
            if self.current:
                self.current.released_at=self.released_at
                self.current.stop.set()
            self.display('Tekst opmaken...')

    def gesture_actions(self,actions):
        for action in actions:
            if action=='start':self.start()
            elif action=='stop':self.stop()
            elif action=='cancel':self.cancel()
            elif action=='lock':self.display('Opname vastgezet. Druk opnieuw om te stoppen.')

    def begin_recording(self,target):
        if target.password:
            self.state='idle';self.gesture.reset();self.hotkeys.command('escape',False)
            self.display(target.reason);self.hide_later();return
        fixture=ROOT/'recordings/synthetic/desktop-test-short.wav' if self.test else None
        self.current=Recording(self,self.ident,target,fixture)
        if hasattr(self.current,'timings'):
            self.current.timings['target_capture_ms']=round((time.monotonic()-getattr(self,'capture_started',time.monotonic()))*1000,1)
        self.current.released_at=getattr(self,'released_at',None)
        if self.stop_requested:
            self.current.stop.set();self.state='processing';self.display('Tekst opmaken...')
        else:
            self.state='recording';self.display('Testaudio loopt...' if self.test else 'Microfoon starten...')
        if self.test:self.tests['target_editable']=target.editable;self.tests['target_reason']=target.reason;self.tests['gesture_started']=True;self.tests['input_source']='internal gesture simulation, no OS shortcut claim'

    def replay(self):
        if self.state!='idle': return
        self.ident+=1; ident=self.ident; hwnd=w.foreground()
        self.replay_started=time.monotonic()
        self.state='starting'; self.hotkeys.command('escape',True)
        self.display('Laatste tekst ophalen...')
        def prepare():
            try:
                text=latest_text()
                if not text:
                    self.events.put(('error',ident,'Nog geen bewaarde transcriptie om te plakken')); return
                target=self.uia.submit(w.capture_target,hwnd).result(timeout=1.2)
                self.events.put(('replay_captured',ident,target,text))
            except Exception:
                self.events.put(('error',ident,'Laatste tekst niet beschikbaar of tekstvak niet controleerbaar'))
        threading.Thread(target=prepare,daemon=True).start()

    def cancel(self):
        self.gesture.reset()
        self.ident += 1
        if self.current: self.current.cancel.set(); self.current.stop.set()
        self.current = None; self.state = 'idle'
        self.hotkeys.command('escape', False)
        self.display('Geannuleerd')
        self.hide_later()

    def hide_later(self,delay_ms=3500):
        ident = self.ident
        self.root.after(delay_ms, lambda: w.show(self.hwnd, 0) if self.ident==ident and not self.current else None)

    def remember_status(self,message):
        self.last_insertion_message=message
        window=getattr(self,'control_window',None)
        if window and window.exists():window.insertion_message.set(message)
        try:
            (ROOT/'data/desktop-last-status.json').write_text(json.dumps({'message':message},ensure_ascii=False),encoding='utf-8')
        except OSError:pass

    def copy(self):
        if self.last_text:
            try: w.copy_text(self.hwnd, self.last_text); self.display('Laatste tekst gekopieerd')
            except Exception as exc: self.display(str(exc))
            self.hide_later()

    def insert(self, session, result):
        began=time.monotonic()
        text = result.get('text', '')
        backup = None; own_sequence = None
        ok = False; paste_sent=False; reason = 'Geen tekst ontvangen'
        try:
            if not text: return
            if result.get('warning'):
                reason = 'Controleer de tekst in de geschiedenis; zelf kopiëren'; return
            for _ in range(100):
                if session.cancel.is_set(): return
                if not w.modifiers_held(): break
                time.sleep(.02)
            else: reason = 'Sneltoets nog ingedrukt: zelf kopiëren'; return
            valid, reason = self.uia.submit(w.same_target, session.target).result(timeout=1)
            if not valid or session.cancel.is_set(): return
            backup = w.ClipboardBackup(self.hwnd)
            # Recheck after clipboard acquisition, and never replace a newer clipboard.
            valid, reason = self.uia.submit(w.same_target, session.target).result(timeout=1)
            if not valid or session.cancel.is_set(): return
            if w.clipboard_sequence()!=backup.sequence:
                reason='Klembord gewijzigd: zelf kopiëren'; return
            own_sequence = w.copy_text(self.hwnd, text)
            if session.cancel.is_set() or w.foreground()!=session.target.hwnd:
                reason='Invoegen geannuleerd'; return
            if not w.paste_once(): reason='Windows weigerde invoegen: zelf kopiëren'; return
            paste_sent=True
            if hasattr(session,'timings'):
                released=getattr(session,'released_at',None)
                if released is not None:session.timings['release_to_paste_sent_ms']=round((time.monotonic()-released)*1000,1)
            # Wait for the target to consume Ctrl+V before restoring the clipboard.
            for _ in range(12):
                time.sleep(.05)
                if self.uia.submit(w.verify_target, session.target, text).result(timeout=.5): ok=True; break
            reason='Ingevoegd' if ok else 'Plakken verstuurd; controleer het tekstvak'
        except Exception as exc:
            reason='Niet ingevoegd: '+str(exc)[:105]
        finally:
            if backup:
                try:
                    restored = backup.restore(own_sequence) if own_sequence is not None else False
                    if self.test and own_sequence is not None: self.tests['clipboard_restored']=restored
                except Exception: reason += ' (klembordherstel mislukt)'
                finally: backup.dispose()
            if hasattr(session,'timings'):
                session.timings['insertion_ms']=round((time.monotonic()-began)*1000,1)
                released=getattr(session,'released_at',None)
                if released is not None:
                    session.timings['release_to_outcome_ms']=round((time.monotonic()-released)*1000,1)
                    if ok:session.timings['release_to_verified_ms']=session.timings['release_to_outcome_ms']
            if hasattr(self,'record_insertion'):self.record_insertion(session,ok,reason,paste_sent)
            self.events.put(('inserted', session.ident, ok, reason))

    def record_insertion(self,session,ok,reason,paste_sent):
        target=getattr(session,'target',None)
        report={'time':time.time(),'status':'verified' if ok else 'paste_sent_unverified' if paste_sent else 'blocked',
                'reason':reason,'target_hwnd':getattr(target,'hwnd',None),'target_editable':getattr(target,'editable',False),
                'capture_reason':getattr(target,'reason',''),'capabilities':getattr(target,'details',{}),
                'timings':getattr(session,'timings',{})}
        try:
            (ROOT/'logs').mkdir(exist_ok=True)
            (ROOT/'logs/desktop-last-insertion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:pass

    def poll(self):
        try:
            for _ in range(200):
                if self.events.empty(): break
                event = self.events.get_nowait(); kind, *args = event
                if kind == 'quit': self.quit(); return
                if kind == 'quit_all':self.quit_all();continue
                if kind == 'shutdown_error':
                    self.state='idle'
                    if self.control_window and self.control_window.exists():self.control_window.status.set(args[0]+' Probeer volledig afsluiten opnieuw.')
                    else:self.display(args[0])
                    continue
                if kind == 'ui_result':
                    window,callback,result,error=args
                    window.deliver(callback,result,error);continue
                if kind == 'open': self.open_app(args[0] if args else 'home'); continue
                if kind == 'copy': self.copy(); continue
                if kind == 'shortcut_settings': self.shortcut_settings(); continue
                if kind == 'preferences':
                    data=args[0]
                    if self.state!='idle':
                        if self.control_window:self.control_window.status.set('Rond eerst je opname af om instellingen te wijzigen.')
                        continue
                    if data.get('formatter') not in ('local','cloud-mini','openrouter-free') or data.get('paragraphs') not in ('normaal','ruim','compact') or data.get('style') not in ('bericht','notitie','letterlijk'):continue
                    self.config.update(data);self.config['engine']='parakeet' if data['formatter']=='local' else 'hybrid-parakeet'
                    CONFIG.write_text(json.dumps(self.config,indent=2),encoding='utf-8')
                    if self.control_window:self.control_window.status.set('Instellingen opgeslagen. Werkt bij je volgende dictaat.')
                    continue
                if kind == 'mode':
                    if args[0] not in ('local','cloud-mini','openrouter-free'):continue
                    self.config['formatter']=args[0]; self.config['engine']='parakeet' if args[0]=='local' else 'hybrid-parakeet'
                    CONFIG.write_text(json.dumps(self.config, indent=2), encoding='utf-8'); continue
                if kind == 'key':
                    if self.state=='idle':self.hotkeys.command('change',args[0])
                    else:self.display('Rond eerst je opname af om de sneltoets te wijzigen.')
                    continue
                if kind == 'hotkey_ready':
                    self.config['hotkey']=args[0]; self.write_state(args[1])
                    CONFIG.write_text(json.dumps(self.config, indent=2), encoding='utf-8')
                    self.update_tray_title()
                    if self.control_window and self.control_window.exists():self.control_window.refresh_settings()
                    if self.shortcut_dialog and self.shortcut_dialog.winfo_exists():self.shortcut_message.set('Opgeslagen en actief: '+shortcut_label(self.config['hotkey']))
                    if not args[1]: self.display('Geen vrije sneltoets. Kies er een via het traymenu.')
                    continue
                if kind == 'hotkey_error':
                    if self.control_window and self.control_window.exists():self.control_window.settings_status.set(args[0])
                    else:self.display(args[0]);self.hide_later()
                    continue
                if kind == 'replay_ready':
                    self.replay_key,self.replay_registered=args
                    self.write_state()
                    self.update_tray_title()
                    continue
                if kind == 'hotkey':
                    if self.settings_are_open():continue
                    if args[0]==2: self.cancel()
                    elif args[0]==4: self.replay()
                    elif self.state == 'idle': self.start()
                    elif self.current: self.stop()
                    continue
                if kind == 'gesture':
                    if self.settings_are_open():self.gesture.reset();continue
                    if self.state in ('processing','inserting'):continue
                    self.gesture_actions(self.gesture.feed(args[0],args[1]));continue
                if not args or args[0] != self.ident: continue
                args = args[1:]
                if kind == 'replay_captured':
                    target,text=args
                    self.last_text=text
                    if not target.editable or target.password:
                        self.record_insertion(SimpleNamespace(target=target),False,target.reason,False)
                        self.remember_status(target.reason+' Je tekst blijft in Flow Lab beschikbaar.')
                        self.state='idle'; self.hotkeys.command('escape',False); self.display(target.reason); self.hide_later(15000); continue
                    self.current=SimpleNamespace(ident=self.ident,target=target,cancel=threading.Event(),stop=threading.Event(),
                                                 timings={},released_at=None)
                    self.state='inserting'; self.display('Laatste tekst plaatsen...')
                    threading.Thread(target=self.insert,args=(self.current,{'text':text}),daemon=True).start()
                elif kind == 'captured':
                    self.begin_recording(args[0])
                elif kind == 'listening':
                    if self.state=='recording':self.display('Opname vastgezet. Druk opnieuw om te stoppen.' if self.gesture.mode=='locked' else 'Ik luister. Laat los om te verwerken.')
                elif kind == 'level':
                    self.levels.append(args[0])
                    if self.test:
                        self.tests['audio_level_seen']=self.tests.get('audio_level_seen',False) or args[0]>.02
                        self.tests['overlay_kept_focus']=self.tests.get('overlay_kept_focus',True) and w.foreground()==self.scratch
                elif kind == 'source_done':
                    if self.test:self.gesture_actions(self.gesture.feed('up',time.monotonic()))
                    else:self.stop()
                elif kind == 'preparing':
                    if self.state=='processing':self.display('Lokale modellen laden. Je opname blijft bewaard.')
                elif kind == 'processing': self.state='processing'; self.display('Tekst opmaken...')
                elif kind == 'result':
                    self.last_text=args[0].get('text',''); self.state='inserting'; self.display('Tekst plaatsen...')
                    threading.Thread(target=self.insert,args=(self.current,args[0]),daemon=True).start()
                elif kind == 'inserted':
                    timing=getattr(self.current,'timings',{}).get('release_to_verified_ms')
                    message='Geplaatst in het gekozen tekstvak.' if args[0] else args[1]+' Je tekst blijft hieronder beschikbaar.'
                    if args[0] and timing is not None:message+=f' {timing/1000:.2f} s van loslaten tot bevestigd plaatsen.'
                    self.remember_status(message)
                    self.gesture.reset()
                    self.current=None; self.state='idle'; self.hotkeys.command('escape',False); self.display(args[1]); self.hide_later(3500 if args[0] else 15000)
                    if self.control_window and self.control_window.exists() and self.control_window.root.state()!='withdrawn':self.control_window.refresh_selected()
                    if self.test: self.tests['audio_to_insert']=args[0]; self.finish_test()
                elif kind == 'error':
                    self.remember_status('Niet geplaatst: '+args[0])
                    self.gesture.reset()
                    if self.current: self.current.cancel.set(); self.current.stop.set()
                    self.current=None; self.state='idle'; self.hotkeys.command('escape',False); self.display(args[0][:95]); self.hide_later(15000)
                    if self.test: self.tests['error']=args[0]; self.finish_test()
            self.gesture_actions(self.gesture.tick(time.monotonic()))
            self.overlay.render(self.state,self.levels,self.gesture.mode=='locked')
            if self.current and self.state=='recording' and not self.test and time.monotonic()-self.current.last_sound>5:
                self.label.configure(text='Geen geluid gemeten. Controleer je microfoon.')
            if self.test and self.scratch and not self.test_started and w.foreground()==self.scratch:
                self.test_started=True
                w.set_focus(self.edit1); w.send_message(self.edit1,0xB1,6,14)
                # Test only our own scratch window. Injected keyboard events are
                # intentionally ignored by the production shortcut hook.
                self.root.after(400, lambda: self.events.put(('gesture','down',time.monotonic())) if w.foreground()==self.scratch else None)
            if self.state!=self.saved_state:
                self.write_state(); self.saved_state=self.state
        except Exception as exc:
            print(type(exc).__name__,str(exc),file=sys.stderr,flush=True)
        self.root.after(25,self.poll)

    def make_scratch(self):
        # This window stays open until the user focuses it. No countdown can expire unseen.
        self.scratch=w.create_window(0x80,'STATIC','Flow Lab lokale invoegtest (geen microfoon)',0x10CF0000,240,200,750,300,None,None,None,None)
        w.create_window(0,'STATIC','Klik in het bovenste vak. De test start dan en gebruikt alleen testaudio.',0x50000000,20,20,700,30,self.scratch,None,None,None)
        self.edit1=w.create_window(0x200,'EDIT','Begin SELECTIE einde',0x50810004,20,65,690,75,self.scratch,None,None,None)
        self.edit2=w.create_window(0x200,'EDIT','TWEEDE VELD BLIJFT GELIJK',0x50810004,20,160,690,50,self.scratch,None,None,None)

    def finish_test(self):
        self.tests['second_field_unchanged']=w.text_of(self.edit2)=='TWEEDE VELD BLIJFT GELIJK'
        self.tests['selection_replaced']=w.norm(w.text_of(self.edit1))==w.norm('Begin '+self.last_text+' einde')
        (ROOT/'results/desktop-python-self-test.json').write_text(json.dumps(self.tests,indent=2),encoding='utf-8')
        self.root.after(2500,self.quit)

    def quit(self):
        if self.current: self.current.cancel.set(); self.current.stop.set()
        self.hotkeys.close()
        if self.tray: self.tray.stop()
        if self.scratch and w.is_window(self.scratch): w.destroy(self.scratch)
        try:
            if stored_status() and stored_status()['pid']==os.getpid(): STATE.unlink(missing_ok=True)
        except Exception: pass
        w.set_style(self.hwnd,-4,self.old_proc)
        self.root.destroy()

def main():
    current=stored_status()
    if '--status' in sys.argv:
        print(json.dumps(current) if current else 'not_running'); return
    if '--quit' in sys.argv:
        if current: w.post(current['hwnd'],QUIT_MESSAGE,0,0)
        return
    if '--settings' in sys.argv:
        if current:w.post(current['hwnd'],SETTINGS_MESSAGE,0,0)
        return
    if '--open' in sys.argv:
        if current:w.post(current['hwnd'],OPEN_MESSAGE,0,0)
        else:raise SystemExit('Start Flow Lab eerst via de launcher.')
        return
    if '--quit-all' in sys.argv:
        if current:w.post(current['hwnd'],QUIT_ALL_MESSAGE,0,0)
        return
    mutex_fn=w.api(w.kernel,'CreateMutexW',[w.PTR,w.W.BOOL,w.W.LPCWSTR],w.W.HANDLE)
    mutex=mutex_fn(None,False,'Local\\FlowLab.Desktop.Python')
    if C.get_last_error()==183: return
    try: Desktop('--self-test' in sys.argv).root.mainloop()
    finally: w.api(w.kernel,'CloseHandle',[w.W.HANDLE],w.W.BOOL)(mutex)

if __name__=='__main__': main()
