import queue
import pytest
from pathlib import Path
from types import SimpleNamespace as NS
import tkinter as tk
from fastapi.testclient import TestClient
import storage
from app import app as api
from engines import APP_PORT
from native_app import NativeApp,entry_payload,phone_library

def test_native_payload_preserves_snippet_exactly():
    text='Eerste regel.\n\n  Tweede regel.  '
    payload=entry_payload('snippet',None,'Test',text,'  testzin\nvariant\n',True)
    assert payload['value']==text and payload['aliases']==['testzin','variant']

@pytest.mark.parametrize('formatter',['local','verbatim'])
def test_native_window_library_history_roundtrip(monkeypatch,tk_window,formatter):
    root=tk_window
    client=TestClient(api)
    fake=NS(root=root,root_path=Path(__file__).resolve().parent,service_url=f'http://127.0.0.1:{APP_PORT}',events=queue.Queue(),config={'hotkey':'ctrl-shift-space','formatter':formatter},replay_key='alt-shift-z',write_state=lambda:None,shortcut_settings=lambda:None,quit_all=lambda:None)
    def request(self,path,callback,method='GET',data=None):
        r=client.request(method,path,json=data,headers={'Origin':fake.service_url})
        callback(r.json() if r.status_code<400 else None,None if r.status_code<400 else str(r.json()))
    monkeypatch.setattr(NativeApp,'request',request)
    try:
        window=NativeApp(fake);window.root.withdraw()
        fake.recovery_store=NS(entries=lambda:[{'id':'synthetic-id','created_at':1,'duration_s':120,'config':{'formatter':'local'},'persistent':True}])
        window.refresh_home()
        assert str(window.retry_button['state'])=='normal'
        window.retry_button.invoke()
        assert fake.events.get_nowait()==('retry_recording','synthetic-id')
        fake.recovery_store=NS(entries=lambda:[]);window.refresh_home()
        assert str(window.retry_button['state'])=='disabled'
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
        assert len(window.notebook.tabs())==7
        from correction_learning import Repository,candidates
        repo=Repository()
        storage.save_entry('dictionary',{'value':'Lunaro','aliases':['loenaro']})
        repo.observe('native-test',candidates('Ik spreek XYZ.','Ik spreek Lunaro.',repo.catalog()))
        window.load_learning();case=repo.list()[0]
        window.learning_tree.selection_set(case['id']);window.learning_selection()
        assert str(window.learning_buttons['accept']['state'])=='normal'
        window.learning_buttons['accept'].invoke()
        assert repo.list()[0]['state']=='learned'
        window.learning_tree.selection_set(case['id']);window.learning_selection()
        window.learning_buttons['undo'].invoke()
        assert repo.list()[0]['state']=='undone'
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        buttons={str(w.cget('text')):w for w in descendants(window.tabs['settings']) if w.winfo_class()=='TButton'}
        checks={str(w.cget('text')):w for w in descendants(window.tabs['settings']) if w.winfo_class()=='TCheckbutton'}
        checks['Automatisch leren van mijn woordcorrecties'].invoke()
        assert fake.events.get()==('learning_toggle',True)
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

def test_phone_library_export_matches_android_format():
    data={'dictionary':[{'id':'1','kind':'dictionary','name':'Supabase','value':'Supabase','aliases':['superbase'],'enabled':True,'source':'user','updated_at':1},
                        {'id':'2','kind':'dictionary','name':'Wispr','value':'Wispr','aliases':['whisper'],'enabled':True,'source':'wispr-hint','updated_at':1}],
          'snippets':[{'id':'3','kind':'snippet','name':'Adres','value':'Straat 1\n\nStad','aliases':['mijn adres'],'enabled':False,'source':'user','updated_at':1}]}
    out=phone_library(data)
    assert out=={'dictionary':[{'name':'Supabase','value':'Supabase','aliases':['superbase'],'enabled':True,'source':'user'}],
                 'snippets':[{'name':'Adres','value':'Straat 1\n\nStad','aliases':['mijn adres'],'enabled':False,'source':'user'}]}

def test_openrouter_key_shortlist_and_saved_model_probe(monkeypatch,tk_window):
    import app as app_module
    import openrouter_provider as provider
    from openrouter_guide import SUGGESTIONS
    first,second=list(SUGGESTIONS)[:2]
    available=[{'id':first,'name':'First model'},{'id':second,'name':'Second model'}]
    available += [{'id':f'example/other-{i}:free','name':f'Other {i}'} for i in range(6)]
    storage.set_setting('openrouter_model',first)
    key_saves=[];probes=[];requests=[]
    monkeypatch.setattr(provider,'status',lambda:{'configured':True,'key_present':True,'model':storage.setting('openrouter_model',''),'data_collection':'deny'})
    monkeypatch.setattr(provider,'save_key',lambda key:key_saves.append(key))
    async def catalogue(*_,**__):return available
    async def fake_format(text,formatter):
        probes.append((text,formatter,storage.setting('openrouter_model','')))
        return {'text':'Hallo Alex. De voorbeeldplanning is klaar.','ms':750,'warning':None}
    monkeypatch.setattr(provider,'catalogue',catalogue)
    monkeypatch.setattr(app_module,'format_text',fake_format)
    client=TestClient(api);root=tk_window
    fake=NS(root=root,root_path=Path(__file__).resolve().parent,service_url=f'http://127.0.0.1:{APP_PORT}',events=queue.Queue(),config={'hotkey':'ctrl-win','formatter':'local'},replay_key='alt-shift-z',write_state=lambda:None,shortcut_settings=lambda:None,quit_all=lambda:None)
    def request(self,path,callback,method='GET',data=None):
        requests.append(path)
        response=client.request(method,path,json=data,headers={'Origin':fake.service_url})
        callback(response.json() if response.status_code<400 else None,None if response.status_code<400 else 'Fictieve providerfout')
    monkeypatch.setattr(NativeApp,'request',request)
    window=NativeApp(fake)
    try:
        window.show('openrouter');window.root.withdraw()
        assert 'Sleutel toegevoegd' in window.router_key_notice.get()
        assert str(window.router_key_input['state'])=='disabled'
        assert str(window.router_key_save['state'])=='disabled'
        window.router_key.set('onbedoelde tweede waarde');window.save_router_key()
        assert key_saves==[]
        window.edit_router_key();window.router_key.set('sk-or-'+('x'*40));window.save_router_key()
        assert len(key_saves)==1 and window.router_key.get()==''
        assert str(window.router_key_save['state'])=='disabled'
        assert key_saves[0] not in window.router_key_notice.get()+window.router_status.get()
        window.fetch_router_models()
        assert len(window.router_combo['values'])==2
        label=next(k for k,v in window.router_choice_map.items() if v['id']==second)
        window.router_choice.set(label);window.router_choice_selected()
        assert str(window.router_test_button['state'])=='disabled'
        window.test_router_model();assert probes==[]
        assert storage.setting('openrouter_model','')==first
        window.save_router_model();window.test_router_model()
        assert len(probes)==1 and probes[0][1:] == ('openrouter-free',second)
        assert 'hallo Alex' in probes[0][0]  # The fixed API example, never microphone/history input.
        assert second in window.router_result.get('1.0','end-1c')
        assert fake.config['formatter']=='local' and fake.events.empty()
        window.router_all.set(True);window.populate_router_choices()
        assert len(window.router_combo['values'])==8 and window.router_model.get()==second
        window.activate_router();assert fake.events.get()[1]['formatter']=='openrouter-free'
        async def fail_format(*_):raise RuntimeError('Fictieve providerfout')
        monkeypatch.setattr(app_module,'format_text',fail_format)
        window.test_router_model()
        assert 'Sleutel toegevoegd' in window.router_key_notice.get()
        assert str(window.router_key_save['state'])=='disabled'
        assert 'Fictieve providerfout' in window.router_status.get()
    finally:window.root.destroy()
