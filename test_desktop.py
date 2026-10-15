import array
from concurrent.futures import Future
from types import SimpleNamespace as NS
import threading
import queue
import ctypes
import desktop_windows as w
from desktop_helper import amplitude, Desktop

def test_audio_levels_and_native_layout():
    assert amplitude(bytes(1920)) == 0
    assert amplitude(array.array('h', [4000, -4000]*480).tobytes()) > .8
    assert ctypes.sizeof(w.INPUT) == 40
    assert ctypes.sizeof(w.WAVEFORMAT) == 18
    assert ctypes.sizeof(w.WAVEHDR) == 48

def test_native_selection_counts_utf16():
    assert w.utf16_slice('A\U0001f600B', 1, 3) == '\U0001f600'
    assert w.utf16_slice('A\U0001f600B', 3) == 'B'

def target_fixture(monkeypatch):
    element=NS(CurrentIsPassword=False, GetRuntimeId=lambda:(1,2))
    uia=NS(GetFocusedElement=lambda:element)
    target=w.Target(10,editable=True,element=element,runtime=(1,2),before_hash=w.digest('Begin SELECTIE einde'),native_edit=20,native_selection=(6,14))
    monkeypatch.setattr(w,'foreground',lambda:10)
    monkeypatch.setattr(w,'field_text',lambda *_:'Begin SELECTIE einde')
    monkeypatch.setattr(w,'edit_selection',lambda *_:(6,14))
    return uia,target,element

def test_caret_change_blocks_insertion(monkeypatch):
    uia,target,_=target_fixture(monkeypatch)
    assert w.same_target(uia,None,target)[0]
    monkeypatch.setattr(w,'edit_selection',lambda *_:(14,14))
    assert not w.same_target(uia,None,target)[0]

def test_focus_change_blocks_insertion(monkeypatch):
    uia,target,element=target_fixture(monkeypatch)
    element.GetRuntimeId=lambda:(9,9)
    assert not w.same_target(uia,None,target)[0]
    monkeypatch.setattr(w,'foreground',lambda:99)
    assert not w.same_target(uia,None,target)[0]

def test_edits_and_password_block_insertion(monkeypatch):
    uia,target,element=target_fixture(monkeypatch)
    monkeypatch.setattr(w,'field_text',lambda *_:'Changed')
    assert not w.same_target(uia,None,target)[0]
    element.CurrentIsPassword=True
    assert not w.same_target(uia,None,target)[0]

def test_late_cancel_never_pastes(monkeypatch):
    app=NS(events=queue.Queue(),hwnd=1,test=False)
    session=NS(cancel=threading.Event(),ident=1)
    session.cancel.set()
    monkeypatch.setattr(w,'paste_once',lambda: (_ for _ in ()).throw(AssertionError('Must not paste')))
    Desktop.insert(app,session,{'text':'Late result'})
    assert app.events.get()[0]=='inserted'

def test_warning_never_pastes(monkeypatch):
    app=NS(events=queue.Queue(),hwnd=1,test=False)
    session=NS(cancel=threading.Event(),ident=1)
    monkeypatch.setattr(w,'paste_once',lambda: (_ for _ in ()).throw(AssertionError('Must not paste')))
    Desktop.insert(app,session,{'text':'Text','warning':'Formatter rejected'})
    assert app.events.get()[2] is False

def test_clipboard_change_prevents_restore(monkeypatch):
    backup=object.__new__(w.ClipboardBackup)
    monkeypatch.setattr(w,'clipboard_sequence',lambda:8)
    monkeypatch.setattr(w,'open_clipboard',lambda *_: (_ for _ in ()).throw(AssertionError('Must not open')))
    assert backup.restore(7) is False

def test_copy_sequence_is_read_after_close(monkeypatch):
    state={'sequence':1}
    monkeypatch.setattr(w,'open_clipboard',lambda *_:None)
    monkeypatch.setattr(w,'_empty',lambda:None)
    monkeypatch.setattr(w,'put_memory',lambda *_:None)
    monkeypatch.setattr(w,'_close',lambda:state.update(sequence=2))
    monkeypatch.setattr(w,'clipboard_sequence',lambda:state['sequence'])
    assert w.copy_text(1,'Hello')==2

def test_paste_never_sends_enter(monkeypatch):
    sent=[]
    monkeypatch.setattr(w,'keys',lambda seq:sent.extend(seq) or True)
    assert w.paste_once()
    assert sent==[(0x11,False),(0x56,False),(0x56,True),(0x11,True)]

def ancestry_fixture(depth,matching=True):
    nodes=[NS(CurrentNativeWindowHandle=0,GetRuntimeId=lambda i=i:(i,)) for i in range(depth)]
    window=nodes[-1] if matching else NS()
    parents={id(node):nodes[i+1] if i+1<len(nodes) else None for i,node in enumerate(nodes)}
    uia=NS(ElementFromHandle=lambda _:window,CompareElements=lambda a,b:a is b,
           RawViewWalker=NS(GetParentElement=lambda e:parents[id(e)]))
    return uia,nodes,parents

def test_deep_browser_editor_proves_ancestry_without_native_handles():
    uia,nodes,_=ancestry_fixture(48)
    details={}
    assert w.belongs_to_window(uia,nodes[0],10,details)
    assert details=={'ancestry_depth':47,'ancestry_result':'window_element'}

def test_different_window_and_cyclic_provider_are_rejected():
    uia,nodes,parents=ancestry_fixture(48,False)
    details={}
    assert not w.belongs_to_window(uia,nodes[0],10,details)
    assert details['ancestry_result']=='root_reached'
    parents[id(nodes[-1])]=nodes[0]
    assert not w.belongs_to_window(uia,nodes[0],10,details)
    assert details['ancestry_result']=='cycle'

def test_ancestry_search_is_bounded():
    uia,nodes,_=ancestry_fixture(150)
    details={}
    assert not w.belongs_to_window(uia,nodes[0],10,details)
    assert details['ancestry_result']=='depth_limit'

def test_settings_only_pause_hotkeys_in_own_foreground(monkeypatch):
    root=NS(state=lambda:'normal',winfo_id=lambda:20)
    window=NS(exists=lambda:True,root=root,tabs={'settings':'settings','openrouter':'openrouter'},
              notebook=NS(select=lambda:'settings'))
    app=NS(shortcut_dialog=None,control_window=window)
    monkeypatch.setattr(w,'ancestor',lambda *_:20)
    monkeypatch.setattr(w,'foreground',lambda:30)
    assert not Desktop.settings_are_open(app)
    monkeypatch.setattr(w,'foreground',lambda:20)
    assert Desktop.settings_are_open(app)

def test_failed_insertion_has_outcome_timing_but_no_placement_claim(monkeypatch,tmp_path):
    import desktop_helper as d
    monkeypatch.setattr(d,'ROOT',tmp_path)
    app=NS(events=queue.Queue(),hwnd=1,test=False)
    app.record_insertion=lambda *args:Desktop.record_insertion(app,*args)
    session=NS(cancel=threading.Event(),ident=1,target=w.Target(10),timings={},released_at=d.time.monotonic())
    Desktop.insert(app,session,{'text':'Example','warning':'Rejected'})
    report=d.json.loads((tmp_path/'logs/desktop-last-insertion.json').read_text(encoding='utf-8'))
    assert report['status']=='blocked'
    assert report['timings']['release_to_outcome_ms']>=0
    assert 'release_to_verified_ms' not in report['timings']
    assert 'Example' not in d.json.dumps(report)

def test_failure_status_is_retained_and_error_hide_is_longer(monkeypatch,tmp_path):
    import desktop_helper as d
    monkeypatch.setattr(d,'ROOT',tmp_path)
    (tmp_path/'data').mkdir()
    calls=[]
    app=NS(control_window=None,root=NS(after=lambda delay,fn:calls.append(delay)),ident=1,current=None)
    Desktop.remember_status(app,'Plaatsen mislukt. Je tekst blijft bewaard.')
    assert d.json.loads((tmp_path/'data/desktop-last-status.json').read_text(encoding='utf-8'))['message']==app.last_insertion_message
    Desktop.hide_later(app,15000)
    assert calls==[15000]

def test_success_measures_release_to_verified_insertion(monkeypatch):
    import desktop_helper as d
    class Worker:
        def submit(self,fn,*args):
            future=Future();future.set_result((True,'') if fn is w.same_target else True);return future
    backup=NS(sequence=1,restore=lambda _:True,dispose=lambda:None)
    monkeypatch.setattr(w,'ClipboardBackup',lambda _:backup)
    monkeypatch.setattr(w,'modifiers_held',lambda:False)
    monkeypatch.setattr(w,'clipboard_sequence',lambda:1)
    monkeypatch.setattr(w,'copy_text',lambda *_:2)
    monkeypatch.setattr(w,'foreground',lambda:10)
    monkeypatch.setattr(w,'paste_once',lambda:True)
    app=NS(events=queue.Queue(),hwnd=1,test=False,uia=Worker())
    session=NS(ident=1,target=w.Target(10,editable=True),cancel=threading.Event(),
               timings={},released_at=d.time.monotonic()-.3)
    Desktop.insert(app,session,{'text':'Synthetic insertion'})
    assert app.events.get()==('inserted',1,True,'Ingevoegd')
    assert session.timings['release_to_verified_ms']>=300
    assert session.timings['insertion_ms']<session.timings['release_to_verified_ms']

def test_rich_editor_verification_accepts_exact_value_not_partial_match(monkeypatch):
    element=NS(GetRuntimeId=lambda:(1,2))
    uia=NS(GetFocusedElement=lambda:element)
    target=w.Target(10,can_verify=True,runtime=(1,2),element=element,prefix='Before ',suffix=' after')
    monkeypatch.setattr(w,'field_text',lambda *_:'Stale provider value')
    value=NS(CurrentValue='Before inserted after\r\n')
    monkeypatch.setattr(w,'pattern',lambda *_:value)
    assert w.verify_target(uia,None,target,'inserted')
    assert target.details['verification']=='value_pattern'
    value.CurrentValue='inserted'
    assert not w.verify_target(uia,None,target,'inserted')
    assert target.details['verification']=='text_mismatch'

def test_clipboard_image_preserves_dib_without_invalid_bitmap_handle(monkeypatch):
    formats=iter([2,8,0]);data=ctypes.create_string_buffer(bytes([40])+bytes(79))
    monkeypatch.setattr(w,'open_clipboard',lambda _:None)
    monkeypatch.setattr(w,'_close',lambda:None)
    monkeypatch.setattr(w,'_enum',lambda _:next(formats))
    monkeypatch.setattr(w,'_get',lambda fmt:123 if fmt==8 else (_ for _ in ()).throw(AssertionError('Do not request synthesized bitmap')))
    monkeypatch.setattr(w,'_size',lambda _:80)
    monkeypatch.setattr(w,'_lock',lambda _:ctypes.addressof(data))
    monkeypatch.setattr(w,'_unlock',lambda _:None)
    monkeypatch.setattr(w,'clipboard_sequence',lambda:5)
    backup=w.ClipboardBackup(1)
    assert backup.items==[[8,'bytes',data.raw[:80]]]
    restored=[]
    monkeypatch.setattr(w,'_empty',lambda:None)
    monkeypatch.setattr(w,'put_memory',lambda fmt,payload:restored.append((fmt,payload)))
    assert backup.restore(5)
    assert restored==[(8,data.raw[:80])]
