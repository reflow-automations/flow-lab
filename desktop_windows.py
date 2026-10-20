"""Windows primitives using the installed Python runtime and Windows DLLs only."""
import ctypes as C
from ctypes import wintypes as W
import hashlib,queue,threading,time
from concurrent.futures import Future
from dataclasses import dataclass,field
from shortcut_config import shortcut,ShortcutEdges

user=C.WinDLL('user32',use_last_error=True);kernel=C.WinDLL('kernel32',use_last_error=True);gdi=C.WinDLL('gdi32',use_last_error=True);winmm=C.WinDLL('winmm')
PTR=C.c_void_p;SIZE=C.c_size_t;LRESULT=C.c_ssize_t
def api(lib,name,args,result):
    fn=getattr(lib,name);fn.argtypes=args;fn.restype=result;return fn
foreground=api(user,'GetForegroundWindow',[],W.HWND)
window_pid=api(user,'GetWindowThreadProcessId',[W.HWND,C.POINTER(W.DWORD)],W.DWORD)
ancestor=api(user,'GetAncestor',[W.HWND,W.UINT],W.HWND)
is_window=api(user,'IsWindow',[W.HWND],W.BOOL)
show=api(user,'ShowWindow',[W.HWND,C.c_int],W.BOOL)
get_style=api(user,'GetWindowLongPtrW',[W.HWND,C.c_int],LRESULT)
set_style=api(user,'SetWindowLongPtrW',[W.HWND,C.c_int,LRESULT],LRESULT)
set_position=api(user,'SetWindowPos',[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT],W.BOOL)
post=api(user,'PostMessageW',[W.HWND,W.UINT,W.WPARAM,W.LPARAM],W.BOOL)
post_thread=api(user,'PostThreadMessageW',[W.DWORD,W.UINT,W.WPARAM,W.LPARAM],W.BOOL)
register=api(user,'RegisterHotKey',[W.HWND,C.c_int,W.UINT,W.UINT],W.BOOL)
unregister=api(user,'UnregisterHotKey',[W.HWND,C.c_int],W.BOOL)
key_state=api(user,'GetAsyncKeyState',[C.c_int],C.c_short)
clipboard_sequence=api(user,'GetClipboardSequenceNumber',[],W.DWORD)
create_window=api(user,'CreateWindowExW',[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,PTR],W.HWND)
send_message=api(user,'SendMessageW',[W.HWND,W.UINT,W.WPARAM,W.LPARAM],LRESULT)
set_text=api(user,'SetWindowTextW',[W.HWND,W.LPCWSTR],W.BOOL)
get_text=api(user,'GetWindowTextW',[W.HWND,W.LPWSTR,C.c_int],C.c_int)
destroy=api(user,'DestroyWindow',[W.HWND],W.BOOL)
set_focus=api(user,'SetFocus',[W.HWND],W.HWND)

def text_of(hwnd):
    b=C.create_unicode_buffer(50000);get_text(hwnd,b,len(b));return b.value
def pid_of(hwnd):
    p=W.DWORD();window_pid(hwnd,C.byref(p));return p.value
def modifiers_held():return any(key_state(k)&0x8000 for k in (0x10,0x11,0x12,0x5B,0x5C,0x20))

class KEYBD(C.Structure):_fields_=[('key',W.WORD),('scan',W.WORD),('flags',W.DWORD),('time',W.DWORD),('extra',SIZE)]
class MOUSE(C.Structure):_fields_=[('x',W.LONG),('y',W.LONG),('data',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',SIZE)]
class UNION(C.Union):_fields_=[('keyboard',KEYBD),('mouse',MOUSE)]
class INPUT(C.Structure):_fields_=[('type',W.DWORD),('data',UNION)]
_send_input=api(user,'SendInput',[W.UINT,C.POINTER(INPUT),C.c_int],W.UINT)
def keys(sequence):
    entries=(INPUT*len(sequence))(*[INPUT(1,UNION(keyboard=KEYBD(k,0,2 if up else 0,0,0))) for k,up in sequence])
    return _send_input(len(entries),entries,C.sizeof(INPUT))==len(entries)
def paste_once():
    ok=keys([(0x11,False),(0x56,False),(0x56,True),(0x11,True)])
    if not ok:keys([(0x11,True)])
    return ok
HOTKEYS={'ctrl-win':(10,0,'Ctrl+Windows'),'ctrl-alt-space':(3,0x20,'Ctrl+Alt+Spatie'),'win-alt-d':(9,0x44,'Win+Alt+D'),'ctrl-shift-space':(6,0x20,'Ctrl+Shift+Spatie')}
REPLAY_KEYS={'alt-shift-z':(5,0x5A,'Alt+Shift+Z'),'ctrl-alt-shift-z':(7,0x5A,'Ctrl+Alt+Shift+Z')}
def test_hotkey(hwnd,key):
    import os
    if foreground()!=hwnd or pid_of(hwnd)!=os.getpid():return False
    _,modifiers,vk,_=shortcut(key);codes=[k for flag,k in [(2,0x11),(1,0x12),(4,0x10),(8,0x5B)] if modifiers&flag]+([vk] if vk else [])
    return keys([(k,False) for k in codes]+[(k,True) for k in reversed(codes)])

class KBDLL(C.Structure):
    _fields_=[('vk',W.DWORD),('scan',W.DWORD),('flags',W.DWORD),('time',W.DWORD),('extra',SIZE)]
HOOKPROC=C.WINFUNCTYPE(LRESULT,C.c_int,W.WPARAM,W.LPARAM)
_set_hook=api(user,'SetWindowsHookExW',[C.c_int,HOOKPROC,W.HINSTANCE,W.DWORD],W.HANDLE)
_next_hook=api(user,'CallNextHookEx',[W.HANDLE,C.c_int,W.WPARAM,W.LPARAM],LRESULT)
_unhook=api(user,'UnhookWindowsHookEx',[W.HANDLE],W.BOOL)
_module=api(kernel,'GetModuleHandleW',[W.LPCWSTR],W.HMODULE)

class Hotkeys:
    def __init__(self,events,key):
        self.events=events;self.key=key;self.thread_id=0;self.commands=queue.Queue();self.registered=False
        self.hook=None;self.hook_callback=None;self.main_id=1
        threading.Thread(target=self.run,daemon=True).start()

    def activate(self,value):
        """Prepare replacement first, release previous shortcut only after success."""
        value,mask,vk,_=shortcut(value)
        old_hook=getattr(self,'hook',None)
        old_id=getattr(self,'main_id',1)
        if self.registered and value==self.key:return True
        new_hook=None;callback=None
        new_id=3 if old_id==1 else 1
        if vk and not register(None,new_id,mask|0x4000,vk):return False
        chord=ShortcutEdges(mask,vk)
        chord.down={k for k in range(8,256) if k not in (0x10,0x11,0x12) and key_state(k)&0x8000}
        chord.blocked=bool(chord.down)
        def receive(code,message,data):
            if code==0 and message in (0x100,0x101,0x104,0x105):
                item=C.cast(data,C.POINTER(KBDLL)).contents
                edge=chord.feed(item.vk,message in (0x100,0x104),bool(item.flags&0x10))
                if edge:self.events.put(('gesture',edge,time.monotonic()))
            return _next_hook(None,code,message,data)
        callback=HOOKPROC(receive)
        new_hook=_set_hook(13,callback,_module(None),0)
        if not new_hook:
            if vk:unregister(None,new_id)
            return False
        if old_hook:_unhook(old_hook)
        if self.registered and old_id:unregister(None,old_id)
        self.hook=new_hook;self.hook_callback=callback;self.main_id=new_id if vk else None
        self.key=value;self.registered=True
        return True

    def run(self):
        self.thread_id=kernel.GetCurrentThreadId();msg=W.MSG()
        user.PeekMessageW(C.byref(msg),None,0,0,0)
        for candidate in dict.fromkeys([self.key,'ctrl-shift-space','ctrl-alt-space','win-alt-d']):
            if self.activate(candidate):break
        self.events.put(('hotkey_ready',self.key,self.registered))
        for replay_key,(modifiers,vk,_) in REPLAY_KEYS.items():
            if register(None,4,modifiers|0x4000,vk):
                self.events.put(('replay_ready',replay_key,True));break
        else:self.events.put(('replay_ready',None,False))
        while user.GetMessageW(C.byref(msg),None,0,0)>0:
            # The hook reports press/release. WM_HOTKEY for dictation is only a reservation.
            if msg.message==0x312 and msg.wParam in (2,4):self.events.put(('hotkey',msg.wParam))
            elif msg.message==0x8001:
                while not self.commands.empty():
                    action,value=self.commands.get()
                    if action=='escape':
                        if value:register(None,2,0x4000,0x1B)
                        else:unregister(None,2)
                    elif action=='change':
                        try:success=self.activate(value)
                        except ValueError:success=False
                        if success:self.events.put(('hotkey_ready',self.key,self.registered))
                        else:self.events.put(('hotkey_error','Deze combinatie is bezet of niet beschikbaar. De vorige blijft actief.'))
        if getattr(self,'hook',None):_unhook(self.hook)
        unregister(None,1);unregister(None,3);unregister(None,2);unregister(None,4)
    def command(self,action,value):
        self.commands.put((action,value))
        if self.thread_id:post_thread(self.thread_id,0x8001,0,0)
    def close(self):
        if self.thread_id:post_thread(self.thread_id,0x12,0,0)

def norm(s):return s.replace('\r\n','\n').replace('\r','\n')
def digest(s):return hashlib.sha256(norm(s).encode('utf-8')).hexdigest()

class UiaWorker:
    """A hung accessibility provider can never hang the overlay or process shutdown."""
    def __init__(self):
        self.tasks=queue.Queue();threading.Thread(target=self.run,daemon=True).start()
    def run(self):
        import sys
        sys.coinit_flags=0
        import comtypes,comtypes.client
        comtypes.CoInitializeEx(0);comtypes.client.GetModule('UIAutomationCore.dll')
        from comtypes.gen import UIAutomationClient as U
        uia=comtypes.client.CreateObject(U.CUIAutomation8,interface=U.IUIAutomation2)
        uia.AutoSetFocus=False
        uia.ConnectionTimeout=300;uia.TransactionTimeout=300
        while True:
            fn,args,future=self.tasks.get()
            if future.cancelled():continue
            try:
                result=fn(uia,U,*args)
                if not future.cancelled():future.set_result(result)
            except Exception as e:
                if not future.cancelled():future.set_exception(e)
    def submit(self,fn,*args):
        f=Future();self.tasks.put((fn,args,f));return f

def pattern(e,U,name,interface):
    try:return e.GetCurrentPattern(getattr(U,name)).QueryInterface(getattr(U,interface))
    except Exception:return None
def field_text(e,U):
    v=pattern(e,U,'UIA_ValuePatternId','IUIAutomationValuePattern')
    if v:return v.CurrentValue
    p=pattern(e,U,'UIA_TextPatternId','IUIAutomationTextPattern')
    if p:return p.DocumentRange.GetText(40001)
    return ''

@dataclass
class Target:
    hwnd:int
    editable:bool=False
    password:bool=False
    reason:str='Geen controleerbaar tekstvak'
    element:object=None
    selected:object=None
    runtime:tuple=()
    before_hash:str=''
    prefix:str=''
    suffix:str=''
    can_verify:bool=False
    native_edit:int=0
    native_selection:tuple=()
    details:dict=field(default_factory=dict)
    learning_requested:bool=False
    learning_basis:dict|None=None

def edit_selection(hwnd):
    start=W.DWORD();end=W.DWORD();result=SIZE()
    fn=api(user,'SendMessageTimeoutW',[W.HWND,W.UINT,W.WPARAM,W.LPARAM,W.UINT,W.UINT,C.POINTER(SIZE)],LRESULT)
    if not fn(hwnd,0xB0,C.addressof(start),C.addressof(end),2,300,C.byref(result)):
        raise OSError('Tekstvak reageert niet op selectiecontrole')
    return start.value,end.value

def utf16_slice(text,start,end=None):
    # Native EDIT offsets count UTF-16 code units, including surrogate pairs.
    data=text.encode('utf-16le')
    return data[start*2:None if end is None else end*2].decode('utf-16le')

def belongs_to_window(uia,element,hwnd,details):
    """Prove ancestry, including deeply nested browser editors without HWNDs."""
    window=uia.ElementFromHandle(hwnd)
    parent=element;seen=set()
    for depth in range(128):
        if not parent:
            details['ancestry_result']='root_reached';return False
        details['ancestry_depth']=depth
        if uia.CompareElements(parent,window):
            details['ancestry_result']='window_element';return True
        handle=parent.CurrentNativeWindowHandle
        if handle and ancestor(handle,2)==hwnd:
            details['ancestry_result']='native_window';return True
        runtime=tuple(parent.GetRuntimeId())
        if runtime:
            if runtime in seen:
                details['ancestry_result']='cycle';return False
            seen.add(runtime)
        parent=uia.RawViewWalker.GetParentElement(parent)
    details['ancestry_result']='depth_limit'
    return False

def focused_writable_editor(e,U):
    """No field text: verify keyboard focus and an editable role or writable text pattern."""
    if not e.CurrentHasKeyboardFocus or not e.CurrentIsEnabled:return False
    if e.CurrentIsPassword or e.CurrentControlType==U.UIA_EditControlTypeId:return True
    value=pattern(e,U,'UIA_ValuePatternId','IUIAutomationValuePattern')
    if value and not value.CurrentIsReadOnly:return True
    text=pattern(e,U,'UIA_TextPatternId','IUIAutomationTextPattern')
    if text:
        readonly=text.DocumentRange.GetAttributeValue(U.UIA_IsReadOnlyAttributeId)
        return readonly is False or type(readonly) is int and readonly==0
    return False

def focused_editor(uia,U,hwnd,details=None):
    """Resolve hosted editors by Windows roles and focus, never by app name or location."""
    details={} if details is None else details
    details['focus_stage']='get_focused'
    e=uia.GetFocusedElement()
    if not e:return e
    details['focus_resolution']='focused_element'
    # Custom, Group, Document, Window and Pane can host an embedded editor.
    if getattr(e,'CurrentControlType',None) not in {50025,50026,50030,50032,50033}:return e
    if e.CurrentIsPassword or 'terminal' in (e.CurrentName or '').casefold():return e
    if getattr(e,'CurrentHasKeyboardFocus',False) and focused_writable_editor(e,U):return e
    if foreground()!=hwnd or not belongs_to_window(uia,e,hwnd,{}):return e
    details['focus_host_class']=e.CurrentClassName
    editable=uia.CreateOrCondition(uia.CreatePropertyCondition(U.UIA_ControlTypePropertyId,U.UIA_EditControlTypeId),
        uia.CreateOrCondition(uia.CreatePropertyCondition(U.UIA_IsValuePatternAvailablePropertyId,True),
                              uia.CreatePropertyCondition(U.UIA_IsTextPatternAvailablePropertyId,True)))
    condition=uia.CreateAndCondition(uia.CreatePropertyCondition(U.UIA_HasKeyboardFocusPropertyId,True),editable)
    details['focus_stage']='host_find_first'
    first=uia.ElementFromHandle(hwnd).FindFirst(U.TreeScope_Descendants,condition)
    if not first:
        details['focus_lookup_result']='no_focused_editor'
        return e
    if not focused_writable_editor(first,U):return e
    parent=uia.RawViewWalker.GetParentElement(first)
    if not parent:return e
    # A full descendant enumeration can walk the complete chat history and exceed
    # the capture deadline. Check only this focused editor's immediate siblings.
    details['focus_stage']='host_focused_siblings'
    # WinUI fragment parents can return no children through FindAll even while
    # RawViewWalker exposes the actual focused edit. Walk only direct siblings.
    candidates={};candidate=uia.RawViewWalker.GetFirstChildElement(parent);seen=0
    while candidate and seen<16:
        seen+=1
        if focused_writable_editor(candidate,U) and belongs_to_window(uia,candidate,hwnd,{}):
            runtime=tuple(candidate.GetRuntimeId())
            if runtime:candidates[runtime]=candidate
        candidate=uia.RawViewWalker.GetNextSiblingElement(candidate)
    details['focused_siblings_examined']=seen;details['focused_edit_candidates']=len(candidates)
    if candidate:return e
    if len(candidates)==1 and tuple(first.GetRuntimeId()) in candidates and foreground()==hwnd:
        details['focus_resolution']='hosted_focused_edit'
        details['focus_stage']='resolved'
        return next(iter(candidates.values()))
    return e

def capture_with_focus_retry(uia,U,hwnd,details=None):
    """Briefly tolerate an editor's focus publication lag before recording starts."""
    details={} if details is None else details
    attempts=[]
    for attempt,delay in enumerate((0,.08,.12),1):
        if delay:
            if foreground()!=hwnd:break
            time.sleep(delay)
            if foreground()!=hwnd:break
        details.clear();details.update(capture_attempts=attempt,capture_attempt_stages=list(attempts))
        target=capture_target(uia,U,hwnd,details)
        current=dict(details)
        attempts.append({key:current[key] for key in ('focus_stage','focus_lookup_result','capture_stage') if key in current})
        details['capture_attempt_stages']=list(attempts)
        target.details=details
        # Do not retry a known field, password, readonly field, ambiguity, provider
        # error or changed selection. Only the absence of a focused child qualifies.
        if target.editable or target.password or current.get('focus_lookup_result')!='no_focused_editor':return target
    if foreground()!=hwnd:
        return Target(hwnd,reason='Het actieve venster is gewijzigd',details=details)
    return target


def capture_target(uia,U,hwnd,details=None):
    t=Target(hwnd)
    if details is not None:t.details=details
    t.details['capture_stage']='focus'
    if foreground()!=hwnd:t.reason='Het actieve venster is gewijzigd';return t
    e=focused_editor(uia,U,hwnd,t.details)
    if not e:return t
    t.details.update(control_type=e.CurrentControlType,class_name=e.CurrentClassName or '',enabled=bool(e.CurrentIsEnabled))
    t.details['capture_stage']='ancestry'
    # Hosted browser controls may use another PID. Prove ancestry, not just PID equality.
    if not belongs_to_window(uia,e,hwnd,t.details):
        t.reason='Kan het invoerveld niet aan het actieve venster koppelen. Tekst blijft bewaard.';return t
    if e.CurrentIsPassword:t.password=True;t.reason='Wachtwoordveld: opname niet gestart';return t
    name=(e.CurrentName or '').casefold()
    if 'terminal' in name:t.reason='Terminal: tekst straks zelf kopiëren';return t
    t.details['capture_stage']='patterns'
    tp=pattern(e,U,'UIA_TextPatternId','IUIAutomationTextPattern');vp=pattern(e,U,'UIA_ValuePatternId','IUIAutomationValuePattern')
    t.details.update(text_pattern=bool(tp),value_pattern=bool(vp))
    writable=bool(vp and not vp.CurrentIsReadOnly)
    if vp and vp.CurrentIsReadOnly:
        t.reason='Dit tekstvak is alleen-lezen.';return t
    if tp:
        readonly=tp.DocumentRange.GetAttributeValue(U.UIA_IsReadOnlyAttributeId)
        if readonly is True or type(readonly) is int and readonly==1:
            t.reason='Dit tekstvak is alleen-lezen.';return t
        writable=writable or readonly is False or type(readonly) is int and readonly==0
    if not e.CurrentIsEnabled or not (writable or e.CurrentControlType==U.UIA_EditControlTypeId):
        t.reason='Klik eerst in het tekstvak waar je wilt dicteren.';return t
    if not tp:
        native=e.CurrentNativeWindowHandle
        if not native or (e.CurrentClassName or '').casefold()!='edit' or not vp:
            t.reason='Dit tekstvak geeft de cursor nog niet door aan Windows.';return t
        t.details['capture_stage']='native_selection'
        start,end=edit_selection(native);text=vp.CurrentValue
        t.native_edit=native;t.native_selection=(start,end)
        t.prefix=norm(utf16_slice(text,0,start));t.suffix=norm(utf16_slice(text,end));t.can_verify=True
        t.editable=True;t.reason='Cursor vastgelegd';t.element=e;t.runtime=tuple(e.GetRuntimeId());t.before_hash=digest(text)
        t.details['capture_stage']='ready';return t
    t.details['capture_stage']='selection'
    selections=tp.GetSelection()
    t.details['selection_count']=selections.Length
    if selections.Length!=1:
        t.reason='De cursor of selectie in dit tekstvak is niet uitleesbaar.';return t
    selected=selections.GetElement(0);t.details['capture_stage']='surrounding_text'
    before=tp.DocumentRange.Clone();before.MoveEndpointByRange(1,selected,0)
    after=tp.DocumentRange.Clone();after.MoveEndpointByRange(0,selected,1)
    t.prefix=norm(before.GetText(20001));t.suffix=norm(after.GetText(20001));t.can_verify=len(t.prefix)<=20000 and len(t.suffix)<=20000
    text=field_text(e,U)
    # Empty rich editors may expose hint/placeholder text through TextPattern
    # ranges while their actual ValuePattern is empty. It is not existing content.
    if vp and vp.CurrentValue=='':t.prefix='';t.suffix='';t.can_verify=True
    t.details.update(before_length=len(text),prefix_length=len(t.prefix),suffix_length=len(t.suffix))
    t.editable=True;t.reason='Cursor vastgelegd';t.element=e;t.runtime=tuple(e.GetRuntimeId());t.selected=selected.Clone();t.before_hash=digest(text)
    t.details['capture_stage']='ready';return t

def same_target(uia,U,t):
    if not t.editable:return False,t.reason
    if foreground()!=t.hwnd:return False,'Je bent naar een ander venster gegaan'
    try:
        e=focused_editor(uia,U,t.hwnd)
        if not e or e.CurrentIsPassword or tuple(e.GetRuntimeId())!=t.runtime:return False,'Je bent naar een ander tekstvak gegaan'
        if digest(field_text(e,U))!=t.before_hash:return False,'De tekst is intussen veranderd'
        if t.native_edit:
            if edit_selection(t.native_edit)!=t.native_selection:return False,'De cursor of selectie is verplaatst'
            return True,''
        p=pattern(e,U,'UIA_TextPatternId','IUIAutomationTextPattern')
        if not p:return False,'De cursor is niet meer controleerbaar'
        selections=p.GetSelection()
        if selections.Length!=1:return False,'De selectie is gewijzigd'
        selected=selections.GetElement(0)
        if selected.CompareEndpoints(0,t.selected,0)!=0 or selected.CompareEndpoints(1,t.selected,1)!=0:return False,'De cursor of selectie is verplaatst'
        return True,''
    except Exception:return False,'Het tekstvak reageert niet meer'

def verify_target(uia,U,t,text):
    if not t.can_verify:return False
    expected=norm(t.prefix+text+t.suffix).rstrip('\n')
    try:
        # Rich editors can replace their accessibility object after a paste.
        # Resolve the same runtime ID again; never verify an unrelated field.
        e=t.element
        focused=focused_editor(uia,U,t.hwnd)
        if focused and tuple(focused.GetRuntimeId())==t.runtime:e=focused
        actual=norm(field_text(e,U)).rstrip('\n')
        if getattr(t,'learning_requested',False):
            from correction_learning import basis_for_placement
            t.learning_basis=basis_for_placement(actual,text,t.prefix,t.suffix)
        t.details.update(expected_length=len(expected),actual_length=len(actual))
        dictated=norm(text).rstrip('\n')
        t.details.update(whole_field_equals_dictation=actual==dictated,
                         complete_dictation_present=bool(dictated and dictated in actual))
        if actual==expected:
            t.details['verification']='text_pattern';return True
        # Chromium editors may expose a fresher ValuePattern than TextPattern.
        # Both must match the complete expected field, not just a substring.
        value=pattern(e,U,'UIA_ValuePatternId','IUIAutomationValuePattern')
        if value:
            actual_value=norm(value.CurrentValue).rstrip('\n')
            if getattr(t,'learning_requested',False) and not t.learning_basis:
                from correction_learning import basis_for_placement
                t.learning_basis=basis_for_placement(actual_value,text,t.prefix,t.suffix)
            t.details['value_length']=len(actual_value)
            if actual_value==expected:
                t.details['verification']='value_pattern';return True
        t.details['verification']='text_mismatch'
        return False
    except Exception:
        t.details['verification']='provider_error';return False

def learning_snapshot(uia,U,hwnd,runtime):
    """Read only the original focused edit. Never inspect a newly focused field."""
    if foreground()!=hwnd:return None
    element=focused_editor(uia,U,hwnd)
    if not element or tuple(element.GetRuntimeId())!=tuple(runtime):return None
    if element.CurrentIsPassword or not element.CurrentIsEnabled:return None
    value=pattern(element,U,'UIA_ValuePatternId','IUIAutomationValuePattern')
    if value and value.CurrentIsReadOnly:return None
    editing=pattern(element,U,'UIA_TextEditPatternId','IUIAutomationTextEditPattern')
    composing=False
    if editing:
        composition=editing.GetActiveComposition()
        composing=bool(composition and composition.GetText(1))
    text=norm(field_text(element,U)).rstrip('\n')
    if len(text)>40000 or foreground()!=hwnd:return None
    return {'text':text,'composing':composing}

_open=api(user,'OpenClipboard',[W.HWND],W.BOOL);_close=api(user,'CloseClipboard',[],W.BOOL)
_empty=api(user,'EmptyClipboard',[],W.BOOL);_enum=api(user,'EnumClipboardFormats',[W.UINT],W.UINT)
_get=api(user,'GetClipboardData',[W.UINT],W.HANDLE);_set=api(user,'SetClipboardData',[W.UINT,W.HANDLE],W.HANDLE)
_size=api(kernel,'GlobalSize',[W.HGLOBAL],SIZE);_lock=api(kernel,'GlobalLock',[W.HGLOBAL],PTR);_unlock=api(kernel,'GlobalUnlock',[W.HGLOBAL],W.BOOL)
_alloc=api(kernel,'GlobalAlloc',[W.UINT,SIZE],W.HGLOBAL);_free=api(kernel,'GlobalFree',[W.HGLOBAL],W.HGLOBAL)
_copy_image=api(user,'CopyImage',[W.HANDLE,W.UINT,C.c_int,C.c_int,W.UINT],W.HANDLE)
_delete_object=api(gdi,'DeleteObject',[W.HANDLE],W.BOOL)
_copy_emf=api(gdi,'CopyEnhMetaFileW',[W.HANDLE,W.LPCWSTR],W.HANDLE);_delete_emf=api(gdi,'DeleteEnhMetaFile',[W.HANDLE],W.BOOL)
def open_clipboard(hwnd):
    for _ in range(20):
        if _open(hwnd):return
        time.sleep(.025)
    raise OSError('Klembord is bezet')

class ClipboardBackupError(OSError):
    def __init__(self,message,formats,failed_format):
        super().__init__(message)
        self.formats=formats;self.failed_format=failed_format
def put_memory(fmt,data):
    h=_alloc(2,max(1,len(data)))
    if not h:raise OSError('Klembordgeheugen ontbreekt')
    p=_lock(h)
    if not p:_free(h);raise OSError('Klembordgeheugen niet beschikbaar')
    C.memmove(p,data,len(data));_unlock(h)
    if not _set(fmt,h):_free(h);raise OSError('Klembordtekst kon niet worden geplaatst')
class ClipboardBackup:
    def __init__(self,hwnd):
        self.items=[];self.hwnd=hwnd
        open_clipboard(hwnd)
        try:
            f=0;formats=[]
            while f:=_enum(f):formats.append(f)
            # Preserve portable DIB bytes first. Windows synthesizes CF_BITMAP
            # from these; some clipboard providers expose an unusable HBITMAP.
            for f in sorted(formats,key=lambda fmt:fmt==2):
                dib_saved=any(item[0] in (8,17) and item[1]=='bytes' and len(item[2])>=40 for item in self.items)
                if f==2 and dib_saved:continue
                h=_get(f)
                if not h:raise OSError('Klembordformaat niet uitleesbaar')
                if f==2:
                    dup=_copy_image(h,0,0,0,0x2000)
                    if not dup:raise OSError('Afbeelding niet te bewaren')
                    self.items.append([f,'bitmap',dup]);continue
                if f==14:
                    dup=_copy_emf(h,None)
                    if not dup:raise OSError('Afbeelding niet te bewaren')
                    self.items.append([f,'emf',dup]);continue
                if f in (3,9):raise OSError('Dit klembordformaat kan niet veilig worden bewaard')
                n=_size(h)
                if not n or n>32*1024*1024:raise OSError('Klembordformaat niet veilig te kopiëren')
                p=_lock(h)
                if not p:raise OSError('Klembordformaat niet uitleesbaar')
                self.items.append([f,'bytes',C.string_at(p,n)]);_unlock(h)
            self.sequence=clipboard_sequence()
        except Exception as exc:
            self.dispose()
            raise ClipboardBackupError(str(exc),formats,f) from exc
        finally:_close()
    def restore(self,expected):
        if clipboard_sequence()!=expected:return False
        open_clipboard(self.hwnd)
        try:
            if clipboard_sequence()!=expected:return False
            _empty()
            for item in self.items:
                f,kind,data=item
                if kind=='bytes':put_memory(f,data)
                elif data:
                    if not _set(f,data):raise OSError('Klembordherstel mislukt')
                    item[2]=None
            return True
        finally:_close();self.dispose()
    def dispose(self):
        for item in self.items:
            if item[1]=='bitmap' and item[2]:_delete_object(item[2]);item[2]=None
            if item[1]=='emf' and item[2]:_delete_emf(item[2]);item[2]=None
def copy_text(hwnd,text):
    open_clipboard(hwnd)
    try:_empty();put_memory(13,(text+'\0').encode('utf-16le'))
    finally:_close()
    return clipboard_sequence()
def read_clipboard_text(hwnd):
    open_clipboard(hwnd)
    try:
        h=_get(13)
        if not h:return ''
        p=_lock(h)
        if not p:return ''
        s=C.wstring_at(p);_unlock(h);return s
    finally:_close()

class WAVEFORMAT(C.Structure):
    _pack_=2
    _fields_=[('tag',W.WORD),('channels',W.WORD),('rate',W.DWORD),('average',W.DWORD),('align',W.WORD),('bits',W.WORD),('extra',W.WORD)]
class WAVEHDR(C.Structure):
    _fields_=[('data',PTR),('length',W.DWORD),('recorded',W.DWORD),('user',SIZE),('flags',W.DWORD),('loops',W.DWORD),('next',PTR),('reserved',SIZE)]
WAVECALLBACK=C.WINFUNCTYPE(None,W.HANDLE,W.UINT,SIZE,SIZE,SIZE)
_wave_open=api(winmm,'waveInOpen',[C.POINTER(W.HANDLE),W.UINT,C.POINTER(WAVEFORMAT),WAVECALLBACK,SIZE,W.DWORD],W.UINT)
for name in ['waveInPrepareHeader','waveInUnprepareHeader','waveInAddBuffer']:api(winmm,name,[W.HANDLE,C.POINTER(WAVEHDR),W.UINT],W.UINT)
for name in ['waveInStart','waveInStop','waveInReset','waveInClose']:api(winmm,name,[W.HANDLE],W.UINT)
class Microphone:
    def __init__(self,push):
        self.push=push;self.handle=W.HANDLE();self.running=False;self.guard=threading.RLock();self.inflight=0;self.returned=threading.Event()
        # 10 x 40 ms in flight: a short Python/GIL pause can no longer starve the device and drop words.
        self.buffers=[C.create_string_buffer(1920) for _ in range(10)];self.headers=[WAVEHDR(C.cast(b,PTR),1920,0,0,0,0,None,0) for b in self.buffers]
        self.callback=WAVECALLBACK(self.on_data)
    def start(self):
        fmt=WAVEFORMAT(1,1,24000,48000,2,16,0)
        result=_wave_open(C.byref(self.handle),0xffffffff,C.byref(fmt),self.callback,0,0x30000)
        if result:raise OSError('Microfoon kon niet openen (Windows-code '+str(result)+').')
        self.running=True
        for h in self.headers:
            if winmm.waveInPrepareHeader(self.handle,C.byref(h),C.sizeof(h)) or winmm.waveInAddBuffer(self.handle,C.byref(h),C.sizeof(h)):raise OSError('Microfoonbuffer kon niet starten')
            self.inflight+=1
        if winmm.waveInStart(self.handle):raise OSError('Microfoon kon niet starten')
    def on_data(self,handle,message,instance,p1,p2):
        if message!=0x3c0:return
        h=C.cast(p1,C.POINTER(WAVEHDR))
        with self.guard:
            if h.contents.recorded:self.push(C.string_at(h.contents.data,h.contents.recorded))
            self.inflight-=1
            if self.running:
                if not winmm.waveInAddBuffer(handle,h,C.sizeof(WAVEHDR)):self.inflight+=1
            if self.inflight<=0:self.returned.set()
    def stop(self):
        with self.guard:self.running=False
        if self.handle:
            winmm.waveInStop(self.handle);winmm.waveInReset(self.handle)
            if not self.returned.wait(2):raise OSError('Laatste audioblok kwam niet terug; opname afgebroken')
    def close(self):
        if self.handle:
            try:self.stop()
            except Exception:pass
            for h in self.headers:winmm.waveInUnprepareHeader(self.handle,C.byref(h),C.sizeof(h))
            winmm.waveInClose(self.handle);self.handle=W.HANDLE()
