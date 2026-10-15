import threading
from types import SimpleNamespace as NS
import pytest
from dictation_gesture import DictationGesture
from shortcut_config import ShortcutEdges

def test_hold_starts_on_down_stops_on_release_without_delay():
    g=DictationGesture()
    assert g.feed('down',1)==['start']
    assert g.feed('down',2)==[]
    assert g.tick(3)==[]
    assert g.feed('up',4)==['stop']
    assert g.tick(9)==[]

def test_double_tap_locks_same_recording_then_third_press_stops():
    g=DictationGesture()
    assert g.feed('down',1)==['start']
    assert g.feed('up',1.1)==[]
    assert g.feed('down',1.25)==['lock']
    assert g.feed('up',1.35)==[]
    assert g.tick(20)==[]
    assert g.mode=='locked'
    assert g.feed('down',21)==['stop']
    assert g.feed('up',21.1)==[]

def test_single_short_tap_finishes_after_double_tap_window():
    g=DictationGesture();g.feed('down',1);g.feed('up',1.1)
    assert not g.tick(1.3)
    assert g.tick(1.43)==['stop']
    assert g.feed('down',1.5)==[]

@pytest.mark.parametrize('key,mask,extra',[(0,10,0xA4),(0x20,6,0xA4)])
def test_extra_alt_cancels_without_final_text(key,mask,extra):
    edge=ShortcutEdges(mask,key);g=DictationGesture();actions=[]
    keys=[0xA2,0x5B] if not key else [0xA2,0xA0,key]
    for vk in keys:
        event=edge.feed(vk,True)
        if event:actions+=g.feed(event,1)
    event=edge.feed(extra,True);assert event=='cancel'
    actions+=g.feed(event,1.05)
    for vk in reversed(keys+[extra]):assert edge.feed(vk,False) is None
    assert actions==['start','cancel'] and g.mode=='idle'

@pytest.mark.parametrize('keys',[[0xA2,0x5B],[0x5C,0xA3],[0x5B,0xA2]])
def test_edges_are_immediate_and_not_repeated(keys):
    edge=ShortcutEdges(10)
    assert edge.feed(keys[0],True) is None
    assert edge.feed(keys[1],True)=='down'
    assert edge.feed(keys[1],True) is None
    assert edge.feed(keys[0],False)=='up'
    assert edge.feed(keys[1],False) is None

def test_regular_shortcut_release_can_be_repeated_while_modifier_held():
    edge=ShortcutEdges(2,0x44)
    assert edge.feed(0xA2,True) is None
    assert edge.feed(0x44,True)=='down'
    assert edge.feed(0x44,False)=='up'
    assert edge.feed(0x44,True)=='down'
    assert edge.feed(0x44,False)=='up'

def test_injected_edges_ignored():
    edge=ShortcutEdges(10)
    assert all(edge.feed(k,d,True) is None for k,d in [(0xA2,True),(0x5B,True),(0xA2,False)])

def test_release_before_target_capture_cannot_leave_microphone_running(monkeypatch):
    import desktop_helper as d
    mic=NS(stop=threading.Event())
    monkeypatch.setattr(d,'Recording',lambda *args:mic)
    app=NS(state='starting',current=None,gesture=DictationGesture(),display=lambda _:None,
           ident=1,test=False,stop_requested=False)
    d.Desktop.stop(app)
    assert app.stop_requested and app.state=='processing'
    d.Desktop.begin_recording(app,NS(password=False))
    assert mic.stop.is_set() and app.state=='processing'

def test_compact_overlay_size_and_controls(tk_window):
    import tkinter as tk
    from compact_overlay import CompactOverlay
    root=tk_window;calls=[]
    try:
        overlay=CompactOverlay(root,lambda:calls.append('cancel'),lambda:calls.append('stop'),lambda:calls.append('copy'))
        overlay.configure(text='Ik luister. Laat los om te verwerken.')
        overlay.render('recording',[.4]*13,True)
        assert (overlay.width,overlay.height)==(156,36)
        overlay.click(NS(x=18,y=18));overlay.click(NS(x=138,y=18))
        assert calls==['cancel','stop']
        overlay.set_hover(True)
        assert overlay.height==64
        overlay.click(NS(x=(350-156)/2+138,y=46))
        assert calls[-1]=='stop'
        overlay.set_hover(False)
        assert overlay.height==36
    finally:root.destroy()
