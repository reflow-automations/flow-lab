import queue
from pathlib import Path
from types import SimpleNamespace as NS
import tkinter as tk
from fastapi.testclient import TestClient
import storage
from app import app as api
from engines import APP_PORT
from native_app import NativeApp,entry_payload

def test_native_payload_preserves_snippet_exactly():
    text='Eerste regel.\n\n  Tweede regel.  '
    payload=entry_payload('snippet',None,'Test',text,'  testzin\nvariant\n',True)
    assert payload['value']==text and payload['aliases']==['testzin','variant']

def test_native_window_library_history_roundtrip(monkeypatch,tk_window):
    root=tk_window
    client=TestClient(api)
    fake=NS(root=root,root_path=Path(__file__).resolve().parent,service_url=f'http://127.0.0.1:{APP_PORT}',events=queue.Queue(),config={'hotkey':'ctrl-shift-space','formatter':'local'},replay_key='alt-shift-z',write_state=lambda:None,shortcut_settings=lambda:None,quit_all=lambda:None)
    def request(self,path,callback,method='GET',data=None):
        r=client.request(method,path,json=data,headers={'Origin':fake.service_url})
        callback(r.json() if r.status_code<400 else None,None if r.status_code<400 else str(r.json()))
    monkeypatch.setattr(NativeApp,'request',request)
    try:
        window=NativeApp(fake);window.root.withdraw()
        editor=window.editors['snippet']
        editor.name.set('Native test');editor.value.insert('1.0','Exact.\n\n  Witregels.  ');editor.aliases.insert('1.0','test snippet\nvariant')
        editor.save();identifier=editor.identifier
        row=next(e for e in storage.entries('snippet') if e['id']==identifier)
        assert row['value']=='Exact.\n\n  Witregels.  ' and len(row['aliases'])==2
        editor.tree.selection_set(identifier);editor.select()
        assert editor.value.get('1.0','end-1c')==row['value']
        dictionary=window.editors['dictionary']
        dictionary.value.insert('1.0','Voorbeeldnaam');dictionary.aliases.insert('1.0','voorbeeld naam');dictionary.save()
        assert any(e['value']=='Voorbeeldnaam' for e in storage.entries('dictionary'))
        history_id=storage.add_history('ruw','Twee\n\nalinea’s',{})
        window.load_history();window.history_tree.selection_set(history_id);window.select_history()
        assert window.history_text.get('1.0','end-1c')=='Twee\n\nalinea’s'
        window.hide();assert window.root.state()=='withdrawn'
        assert len(window.notebook.tabs())==5
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        buttons={str(w.cget('text')):w for w in descendants(window.tabs['settings']) if w.winfo_class()=='TButton'}
        buttons['Ctrl+Windows kiezen'].invoke();buttons['Sneltoets opslaan'].invoke()
        assert fake.events.get()==('key','ctrl-win')
        window.preference_vars['paragraphs'].set('Meer witregels')
        buttons['Verwerking opslaan'].invoke()
        event=fake.events.get();assert event[0]=='preferences' and event[1]['paragraphs']=='ruim'
        window.preference_vars['formatter'].set('Lokale audio, cloudopmaak')
        assert 'API-kosten' in window.settings_model_hint.get()
        assert 'herkende tekst' in window.settings_model_hint.get()
        assert fake.events.empty() # Merely reading the hint does not save/change a model.
        window.show_model_guide();window.guide_window.withdraw()
        assert window.guide_window.title()=='Flow Lab - Welke modellen kies ik?'
    finally:root.destroy()
