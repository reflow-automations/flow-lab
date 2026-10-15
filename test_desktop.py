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
