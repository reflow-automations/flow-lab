import json
import queue
import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace as NS
import storage
import pytest
import desktop_helper as desktop
import desktop_windows as windows
from last_transcript import latest_text
from check_wispr_library import audit,reconcile

@pytest.fixture(autouse=True)
def no_native_keyboard_hook_in_unit_tests(monkeypatch):
    monkeypatch.setattr(windows,'_set_hook',lambda *args:123)
    monkeypatch.setattr(windows,'_unhook',lambda *args:True)
    monkeypatch.setattr(windows,'_module',lambda *args:1)
    monkeypatch.setattr(windows,'key_state',lambda *args:0)

def test_latest_retained_text_exact_without_duplicate_history():
    now=time.time()
    storage.add_history('raw','Oud',{},created_at=now-31*86400)
    text='Eerste alinea.\n\nTweede alinea, met btw-nummer.'
    storage.add_history('raw',text,{},created_at=now-1)
    with storage.connect() as c: before=c.execute('SELECT count(*) FROM history').fetchone()[0]
    assert latest_text(storage.DB,now)==text
    assert latest_text(storage.DB,now)==text
    with storage.connect() as c: assert c.execute('SELECT count(*) FROM history').fetchone()[0]==before
    assert latest_text(storage.DB,now+31*86400)==''

def test_replay_captures_new_target_without_recording(monkeypatch):
    future=Future();target=windows.Target(123,editable=True);future.set_result(target)
    fake=NS(state='idle',ident=2,events=queue.Queue(),uia=NS(submit=lambda fn,hwnd:future),hotkeys=NS(command=lambda *args:None),display=lambda _:None)
    monkeypatch.setattr(windows,'foreground',lambda:123)
    monkeypatch.setattr(desktop,'latest_text',lambda:'Exact\n\nresultaat')
    monkeypatch.setattr(desktop,'Recording',lambda *args: (_ for _ in ()).throw(AssertionError('No recording')))
    desktop.Desktop.replay(fake)
    assert fake.events.get(timeout=2)==('replay_captured',3,target,'Exact\n\nresultaat')

def test_replay_during_recording_ignored():
    desktop.Desktop.replay(NS(state='recording'))

def test_replay_shortcut_registration_and_release(monkeypatch):
    registrations=[];released=[]
    monkeypatch.setattr(windows.kernel,'GetCurrentThreadId',lambda:1)
    monkeypatch.setattr(windows.user,'PeekMessageW',lambda *args:0)
    monkeypatch.setattr(windows.user,'GetMessageW',lambda *args:0)
    monkeypatch.setattr(windows,'register',lambda h,i,m,k:registrations.append((i,m,k)) or True)
    monkeypatch.setattr(windows,'unregister',lambda h,i:released.append(i))
    obj=object.__new__(windows.Hotkeys);obj.key='ctrl-shift-space';obj.events=queue.Queue();obj.registered=False
    obj.run()
    assert (4,5|0x4000,90) in registrations
    assert obj.events.get()[0]=='hotkey_ready'
    assert obj.events.get()==('replay_ready','alt-shift-z',True)
    assert 4 in released

def test_replay_shortcut_fallback(monkeypatch):
    monkeypatch.setattr(windows.kernel,'GetCurrentThreadId',lambda:1)
    monkeypatch.setattr(windows.user,'PeekMessageW',lambda *args:0)
    monkeypatch.setattr(windows.user,'GetMessageW',lambda *args:0)
    monkeypatch.setattr(windows,'register',lambda h,i,m,k:not(i==4 and m==(5|0x4000)))
    monkeypatch.setattr(windows,'unregister',lambda *args:True)
    obj=object.__new__(windows.Hotkeys);obj.key='ctrl-shift-space';obj.events=queue.Queue();obj.registered=False
    obj.run();obj.events.get()
    assert obj.events.get()==('replay_ready','ctrl-alt-shift-z',True)

def test_audit_normalizes_dictionary_outer_whitespace():
    rows=[{'id':'1','phrase':'Alex Voorbeelt\u00a0','replacement':'Alex Voorbeeld\u00a0','isSnippet':0}]
    local=[dict(kind='dictionary',aliases=['Alex Voorbeelt'],value='Alex Voorbeeld',enabled=True)]
    result=audit(rows,local)
    assert result['dictionary_outer_whitespace_removed']==1 and result['covered_exact']==1
    assert not result['missing'] and not result['conflicts']

def test_reconcile_preserves_local_edits_and_adds_aliases(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'ROOT',tmp_path);(tmp_path/'data').mkdir()
    identifier=storage.save_entry('snippet',{'name':'Mijn snippet','value':'Eigen tekst','aliases':['trigger'],'enabled':True})
    rows=[{'id':'1','phrase':'trigger','replacement':'Wispr tekst','isSnippet':1},
          {'id':'2','phrase':'extra variant','replacement':'Eigen tekst','isSnippet':1}]
    result=reconcile(rows,True)
    entry=next(e for e in storage.entries() if e['id']==identifier)
    assert entry['value']=='Eigen tekst' and entry['name']=='Mijn snippet' and entry['source']=='user'
    assert entry['aliases']==['trigger','extra variant']
    assert result['added_source_rows']==1 and len(result['conflicts'])==1
    assert reconcile(rows,True)['added_source_rows']==0
