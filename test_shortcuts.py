import queue
import pytest
import desktop_windows as w
from shortcut_config import ModifierChord,shortcut

def gesture(chord,keys):
    return sum(chord.feed(vk,down) for vk,down in keys)

@pytest.mark.parametrize('ctrl,win',[(0xA2,0x5B),(0xA3,0x5C)])
@pytest.mark.parametrize('reverse',[False,True])
def test_modifier_only_fires_once_on_release(ctrl,win,reverse):
    first,second=(win,ctrl) if reverse else (ctrl,win)
    chord=ModifierChord(10)
    assert not chord.feed(first,True)
    assert not chord.feed(second,True)
    assert not chord.feed(second,True) # Windows key repeat
    assert chord.feed(first,False)
    assert not chord.feed(second,False)
    assert gesture(chord,[(first,True),(second,True),(second,False),(first,False)])==1

@pytest.mark.parametrize('extra',[0xA4,0xA0,0x44])
def test_superset_never_starts_dictation(extra):
    chord=ModifierChord(10)
    assert gesture(chord,[(0xA2,True),(0x5B,True),(extra,True),(extra,False),(0x5B,False),(0xA2,False)])==0
    assert gesture(chord,[(extra,True),(0xA2,True),(0x5B,True),(extra,False),(0xA2,False),(0x5B,False)])==0

def test_injected_keys_never_start_modifier_recording():
    chord=ModifierChord(10)
    assert not any(chord.feed(vk,down,injected=True) for vk,down in [(0xA2,True),(0x5B,True),(0x5B,False),(0xA2,False)])

def test_custom_shortcut_normalization():
    assert shortcut('win-ctrl')==('ctrl-win',10,0,'Ctrl+Windows')
    assert shortcut('ctrl-alt-f9')==('ctrl-alt-f9',3,120,'Ctrl+Alt+F9')
    assert shortcut('alt-7')==('alt-7',1,55,'Alt+7')

@pytest.mark.parametrize('value',['ctrl','shift-a','a','ctrl-f12','ctrl-ctrl-a','ctrl-a-b','unknown'])
def test_invalid_shortcuts_rejected(value):
    with pytest.raises(ValueError):shortcut(value)

def test_failed_registration_preserves_old_binding(monkeypatch):
    manager=object.__new__(w.Hotkeys)
    manager.key='ctrl-shift-space';manager.registered=True;manager.main_id=1;manager.hook=None
    released=[]
    monkeypatch.setattr(w,'register',lambda *args:False)
    monkeypatch.setattr(w,'unregister',lambda *args:released.append(args))
    assert manager.activate('ctrl-alt-f9') is False
    assert manager.key=='ctrl-shift-space' and manager.registered
    assert not released

def test_switch_to_hook_and_back_releases_old_resources(monkeypatch):
    manager=object.__new__(w.Hotkeys)
    manager.events=queue.Queue();manager.key='ctrl-shift-space';manager.registered=True;manager.main_id=1;manager.hook=None
    released=[];unhooked=[]
    monkeypatch.setattr(w,'register',lambda *args:True)
    monkeypatch.setattr(w,'unregister',lambda *args:released.append(args))
    monkeypatch.setattr(w,'_unhook',lambda h:unhooked.append(h))
    monkeypatch.setattr(w,'key_state',lambda k:0)
    monkeypatch.setattr(w,'_module',lambda _:1)
    monkeypatch.setattr(w,'_set_hook',lambda *args:123)
    assert manager.activate('ctrl-win')
    assert manager.hook==123 and manager.key=='ctrl-win' and released==[(None,1)]
    assert manager.activate('ctrl-alt-f9')
    assert unhooked==[123] and manager.hook==123 and manager.main_id is not None

def test_settings_open_inside_native_app():
    import desktop_helper as d
    from types import SimpleNamespace as NS
    calls=[]
    fake=NS(state='idle',open_app=lambda panel:calls.append(panel))
    d.Desktop.shortcut_settings(fake)
    assert calls==['settings']
