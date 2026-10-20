from concurrent.futures import Future
import json
import queue
import threading
import time
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient
import storage
from app import app
from correction_learning import Repository,candidates,basis_for_placement,own_region,WINDOW_SECONDS,QUIET_SECONDS
from correction_watch import Session,Watcher

def name():
    return storage.save_entry('dictionary',{'value':'Lunaro','aliases':['loenaro']})

def change(before='Ik spreek Lunaaro morgen.',after='Ik spreek Lunaro morgen.'):
    return candidates(before,after,storage.entries('dictionary'))

def test_known_name_learns_alias_and_keeps_manual_rule():
    identifier=name();repo=Repository();items=change()
    assert items and items[0]['mode']=='auto'
    repo.observe('dictation-one',items)
    entry=next(row for row in storage.entries('dictionary') if row['id']==identifier)
    assert entry['aliases']==['loenaro','Lunaaro'] and entry['source']=='user'
    case=repo.list()[0];assert case['state']=='learned'
    repo.observe('dictation-one',items)
    assert repo.list()[0]['observations']==1
    from personalization import dictionary_replace
    assert dictionary_replace('Lunaaro komt morgen.')=='Lunaro komt morgen.'

def test_new_name_needs_two_independent_dictations():
    repo=Repository();items=candidates('Ik spreek Alppana morgen.','Ik spreek Alpana morgen.',[])
    assert items[0]['mode']=='repeat'
    repo.observe('one',items);repo.observe('one',items)
    assert repo.list()[0]['state']=='pending'
    repo.observe('two',items)
    assert repo.list()[0]['state']=='learned' and repo.list()[0]['observations']==2

def test_lowercase_name_part_is_learned_with_unchanged_name_context():
    repo=Repository()
    items=candidates('Ik bel Merona pakket morgen.','Ik bel Merona parket morgen.',[])
    assert len(items)==1 and items[0]['wrong']=='Merona pakket' and items[0]['right']=='Merona parket'
    assert items[0]['mode']=='repeat'
    repo.observe('one',items)
    assert repo.list()[0]['state']=='pending'
    repo.observe('two',items)
    assert repo.list()[0]['state']=='learned'
    from personalization import dictionary_replace
    assert dictionary_replace('Een pakket voor Merona pakket.')=='Een pakket voor Merona parket.'

def test_standalone_unknown_name_context_is_visible_as_a_proposal():
    items=candidates('Merona pakket.','Merona parket.',[])
    assert len(items)==1 and items[0]['mode']=='confirm'
    assert items[0]['right']=='Merona parket'

def test_existing_compound_name_learns_only_the_whole_name_alias():
    identifier=storage.save_entry('dictionary',{'value':'Merona Parket','aliases':['merona parket']})
    items=candidates('Ik bel Merona pakket morgen.','Ik bel Merona parket morgen.',storage.entries('dictionary'))
    assert len(items)==1 and items[0]['mode']=='auto' and items[0]['known_id']==identifier
    Repository().observe('one',items)
    from personalization import dictionary_replace
    assert dictionary_replace('Een pakket voor Merona pakket.')=='Een pakket voor Merona Parket.'

@pytest.mark.parametrize(('before','after'),[
    ('Mijn pakket is weg.','Mijn parket is weg.'),
    ('Dit pakket is weg.','Dit parket is weg.'),
    ('Een pakket is weg.','Een parket is weg.'),
    ('Ik bel "Merona pakket".','Ik bel "Merona parket".'),
    ('Ik bel Merona. pakket morgen.','Ik bel Merona. parket morgen.'),
    ('Ik bel Merona niet morgen.','Ik bel Merona wel morgen.'),
])
def test_name_context_does_not_learn_ordinary_words_quotes_or_sentence_boundaries(before,after):
    assert candidates(before,after,[])==[]

def test_acronym_is_a_proposal_and_can_be_accepted():
    name();repo=Repository();items=change('Ik spreek XYZ morgen.','Ik spreek Lunaro morgen.')
    assert items[0]['mode']=='confirm'
    repo.observe('one',items);repo.observe('two',items)
    case=repo.list()[0];assert case['state']=='pending'
    assert repo.review(case['id'],'accept')['state']=='learned'

@pytest.mark.parametrize(('before','after'),[
 ('Het is morgen klaar.','Het is vrijdag klaar.'),
 ('Het kost 15 euro.','Het kost 50 euro.'),
 ('Het is misschien goed.','Het is zeker goed.'),
 ('Ik spreek Lunaaro morgen.','Een volledig andere tekst met een nieuw verhaal.'),
 ('Ik spreek morgen.','Ik spreek morgen. Lunaro komt ook.'),
 ('Ik gebruik "Lunaaro" hier.','Ik gebruik "Lunaro" hier.'),
 ('Ik gebruik `Lunaaro` hier.','Ik gebruik `Lunaro` hier.'),
 ('Mail Lunaaro@example.test.','Mail Lunaro@example.test.'),
 ('Open /tmp/Lunaaro.txt.','Open /tmp/Lunaro.txt.'),
 ('Gebruik config.Lunaaro.','Gebruik config.Lunaro.'),
 ('Gebruik sk-privatekey.','Gebruik sk-otherprivatekey.'),
 ('Gebruik AABBCCDDEEFFAABB.','Gebruik AABBCCDDEEFFAABC.'),
 ('Wis deze woorden.',''),
])
def test_non_word_corrections_and_protected_content_are_not_learned(before,after):
    name();assert candidates(before,after,storage.entries('dictionary'))==[]

def test_undo_removes_only_own_alias_and_preserves_later_manual_aliases():
    identifier=name();repo=Repository();repo.observe('one',change());case=repo.list()[0]
    entry=next(row for row in storage.entries('dictionary') if row['id']==identifier)
    storage.save_entry('dictionary',{**entry,'aliases':entry['aliases']+['handmatige variant']})
    assert repo.review(case['id'],'undo')['state']=='undone'
    entry=next(row for row in storage.entries('dictionary') if row['id']==identifier)
    assert entry['aliases']==['loenaro','handmatige variant']
    repo.observe('two',change())
    assert 'Lunaaro' not in next(row for row in storage.entries('dictionary') if row['id']==identifier)['aliases']

def test_editing_back_within_same_dictation_retracts_automatic_alias():
    identifier=name();repo=Repository();repo.observe('one',change());repo.observe('one',[])
    entry=next(row for row in storage.entries('dictionary') if row['id']==identifier)
    assert entry['aliases']==['loenaro'] and repo.list()[0]['state']=='withdrawn'

def test_automatic_retraction_does_not_overwrite_manual_changes():
    identifier=name();repo=Repository();repo.observe('one',change())
    entry=next(row for row in storage.entries('dictionary') if row['id']==identifier)
    storage.save_entry('dictionary',{**entry,'aliases':entry['aliases']+['manual']})
    repo.observe('one',[])
    assert repo.list()[0]['state']=='conflict'
    assert next(row for row in storage.entries('dictionary') if row['id']==identifier)['aliases']==['loenaro','Lunaaro','manual']

def test_disabled_deleted_and_removed_aliases_are_not_silently_restored():
    identifier=name();repo=Repository();items=change()
    entry=next(row for row in storage.entries('dictionary') if row['id']==identifier)
    storage.save_entry('dictionary',{**entry,'enabled':False})
    assert change()==[];repo.observe('one',items)
    assert repo.list()==[]
    storage.save_entry('dictionary',{**entry,'enabled':True})
    repo.observe('two',items)
    entry=next(row for row in storage.entries('dictionary') if row['id']==identifier)
    storage.save_entry('dictionary',{**entry,'aliases':['loenaro']})
    repo.observe('three',items)
    assert next(row for row in storage.entries('dictionary') if row['id']==identifier)['aliases']==['loenaro']
    storage.delete_entry('dictionary',identifier);repo.observe('four',items)
    assert not any(row['value']=='Lunaro' for row in storage.entries('dictionary'))

def test_existing_alias_conflict_keeps_both_manual_rules():
    name();storage.save_entry('dictionary',{'value':'DifferentName','aliases':['Lunaaro']})
    repo=Repository();repo.observe('one',change())
    assert repo.list()[0]['state']=='conflict'
    assert next(row for row in storage.entries('dictionary') if row['value']=='DifferentName')['aliases']==['Lunaaro']

def test_field_basis_owns_only_inserted_text_and_rejects_uncertain_fields():
    basis=basis_for_placement('Prefix Lunaaro einde','Lunaaro','Prefix ',' einde')
    assert own_region(basis,'Prefix Lunaro einde')=='Lunaro'
    assert own_region(basis,'Ander prefix Lunaro einde') is None
    assert basis_for_placement('Wrong','Expected','','') is None
    assert basis_for_placement('Lunaaro','Lunaaro','Fake placeholder','')['prefix']==''

def test_quiet_period_timeout_and_composition():
    basis={'original':'Ik spreek Lunaaro.','prefix':'','suffix':''};session=Session(basis,0)
    assert session.sample({'text':'Ik spreek Luna'},.5)[0]=='wait'
    assert session.sample({'text':'Ik spreek Lunaro.','composing':True},1)[0]=='wait'
    assert session.sample({'text':'Ik spreek Lunaro.'},2)[0]=='wait'
    assert session.sample({'text':'Ik spreek Lunaro.'},2.6)==('stable','Ik spreek Lunaro.')
    assert session.sample({'text':'Ik spreek Lunaro.'},3)[0]=='wait'
    assert session.sample({'text':'anything'},WINDOW_SECONDS)[0]=='stop'
    assert Session(basis,0).sample(None,.5)[0]=='stop'

def test_turned_off_learning_creates_no_worker_or_observation():
    calls=[];watch=Watcher(lambda:calls.append('worker'),lambda *_:None,NS(),lambda:False,lambda *_:None)
    watch.begin(1,(1,),{'original':'x','prefix':'','suffix':''},'one')
    assert calls==[]

def test_provider_timeout_disables_only_learning_and_does_not_spawn_more_workers():
    calls=[]
    class Pending:
        def result(self,timeout):raise TimeoutError()
        def cancel(self):calls.append('cancel')
    factory=lambda:calls.append('worker') or NS(submit=lambda *_:Pending())
    watch=Watcher(factory,lambda *_:None,NS(),lambda:True,lambda status:calls.append(status))
    watch.begin(1,(1,),{'original':'x','prefix':'','suffix':''},'one')
    for _ in range(100):
        if watch.stalled:break
        time.sleep(.005)
    watch.begin(1,(1,),{'original':'x','prefix':'','suffix':''},'two')
    assert watch.stalled and calls.count('worker')==1 and 'stalled' in calls

def test_learning_api_respects_origin_and_accept_ignore_undo():
    name();repo=Repository();repo.observe('one',change('Ik spreek XYZ.','Ik spreek Lunaro.'))
    identifier=repo.list()[0]['id'];client=TestClient(app)
    path='/api/learning/'+identifier
    assert client.post(path+'/accept',headers={'Origin':'https://example.com'}).status_code==403
    origin={'Origin':'http://127.0.0.1:17865'}
    assert client.post(path+'/accept',headers=origin).json()['item']['state']=='learned'
    assert client.post(path+'/undo',headers=origin).json()['item']['state']=='undone'
    assert client.post(path+'/ignore',headers=origin).json()['item']['state']=='ignored'

def test_manual_canonical_rename_between_detection_and_commit_wins():
    identifier=name();items=change();entry=storage.entries('dictionary')[0]
    entry=next(row for row in storage.entries('dictionary') if row['id']==identifier)
    storage.save_entry('dictionary',{**entry,'value':'Lunara'})
    repo=Repository();repo.observe('one',items)
    assert repo.list()[0]['state']=='conflict'
    assert not any(row['value']=='Lunaro' for row in storage.entries('dictionary'))

def test_correcting_final_known_name_then_continuing_to_type():
    name()
    items=change('Ik spreek Lunaaro.','Ik spreek Lunaro. Dat wilde ik nog toevoegen.')
    assert len(items)==1 and items[0]['wrong']=='Lunaaro' and items[0]['right']=='Lunaro'

def test_two_aliases_can_be_undone_independently():
    identifier=name();repo=Repository()
    repo.observe('one',change())
    repo.observe('two',change('Ik spreek Lunnaro morgen.','Ik spreek Lunaro morgen.'))
    cases=repo.list();assert len(cases)==2 and all(row['state']=='learned' for row in cases)
    first=next(row for row in cases if row['wrong']=='Lunaaro')
    repo.review(first['id'],'undo')
    entry=next(row for row in storage.entries('dictionary') if row['id']==identifier)
    assert entry['aliases']==['loenaro','Lunnaro']

def test_learning_snapshot_checks_same_field_password_and_composition(monkeypatch):
    import desktop_windows as w
    element=NS(GetRuntimeId=lambda:(1,2),CurrentIsPassword=False,CurrentIsEnabled=True)
    uia=NS(GetFocusedElement=lambda:element);reads=[]
    monkeypatch.setattr(w,'foreground',lambda:10)
    monkeypatch.setattr(w,'field_text',lambda *_:reads.append(1) or 'Ik spreek Lunaro.')
    monkeypatch.setattr(w,'pattern',lambda *args:None)
    assert w.learning_snapshot(uia,None,10,(1,2))=={'text':'Ik spreek Lunaro.','composing':False}
    reads.clear();assert w.learning_snapshot(uia,None,10,(9,9)) is None and not reads
    element.CurrentIsPassword=True
    assert w.learning_snapshot(uia,None,10,(1,2)) is None and not reads
    element.CurrentIsPassword=False
    monkeypatch.setattr(w,'pattern',lambda *args:NS(GetActiveComposition=lambda:NS(GetText=lambda _: 'x')) if args[2]=='UIA_TextEditPatternId' else None)
    assert w.learning_snapshot(uia,None,10,(1,2))['composing']

def test_stopping_watcher_cancels_pending_observation():
    future=Future();submitted=threading.Event();calls=[]
    worker=NS(submit=lambda *_:submitted.set() or future)
    watch=Watcher(lambda:worker,lambda *_:None,NS(catalog=lambda:calls.append('catalog')),lambda:True,lambda *_:None)
    watch.begin(1,(1,),{'original':'Lunaaro','prefix':'','suffix':''},'one')
    assert submitted.wait(.2)
    watch.stop();future.set_result({'text':'Lunaro'})
    time.sleep(.02)
    assert calls==[]
