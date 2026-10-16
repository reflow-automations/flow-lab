import json
import queue
import threading
from concurrent.futures import Future
from types import SimpleNamespace as NS
import pytest
import insertion_log as journal
import desktop_windows as w
from desktop_helper import Desktop

def test_failure_survives_next_success_without_recording_text(tmp_path):
    journal.write_report(tmp_path,{'time':100,'status':'blocked','recording_id':'first','reason':'Klembord is bezet','raw':'private','text':'private','clipboard_content':'private'})
    journal.write_report(tmp_path,{'time':101,'status':'verified','recording_id':'second'})
    lines=(tmp_path/'desktop-insertions.jsonl').read_text(encoding='utf-8').splitlines()
    assert [json.loads(line)['status'] for line in lines]==['blocked','verified']
    assert json.loads((tmp_path/'desktop-last-insertion.json').read_text())['status']=='verified'
    assert 'private' not in '\n'.join(lines)

def test_retention_bounds_and_damaged_line(tmp_path,monkeypatch):
    monkeypatch.setattr(journal,'MAX_RECORDS',2)
    now=journal.RETENTION_SECONDS+100
    for timestamp in (1,100,101,102):journal.write_report(tmp_path,{'time':timestamp,'status':'verified'})
    with (tmp_path/'desktop-insertions.jsonl').open('a') as output:output.write('interrupted write\n')
    journal.prune_reports(tmp_path,now=now,force=True)
    rows=[json.loads(line) for line in (tmp_path/'desktop-insertions.jsonl').read_text().splitlines()]
    assert [row['time'] for row in rows]==[101,102]

def test_previous_last_report_is_preserved_once(tmp_path):
    (tmp_path/'desktop-last-insertion.json').write_text(json.dumps({'time':100,'status':'blocked'}))
    journal.prune_reports(tmp_path,now=101,force=True)
    journal.prune_reports(tmp_path,now=102,force=True)
    assert len((tmp_path/'desktop-insertions.jsonl').read_text().splitlines())==1

def test_clipboard_acquisition_tolerates_short_contention_without_pasting(monkeypatch):
    attempts=[];waits=[]
    monkeypatch.setattr(w,'_open',lambda _:attempts.append(1) or len(attempts)>10)
    monkeypatch.setattr(w.time,'sleep',lambda value:waits.append(value))
    monkeypatch.setattr(w,'paste_once',lambda:(_ for _ in ()).throw(AssertionError('No repeated paste')))
    w.open_clipboard(1)
    assert len(attempts)==11 and sum(waits)<.5
    monkeypatch.setattr(w,'_open',lambda _:False)
    waits.clear()
    with pytest.raises(OSError):w.open_clipboard(1)
    assert len(waits)==20 and sum(waits)<=.501

class Worker:
    def submit(self,fn,*args):
        future=Future();future.set_result((True,'') if fn is w.same_target else True);return future

def app_and_session(monkeypatch,tmp_path):
    import desktop_helper as d
    monkeypatch.setattr(d,'ROOT',tmp_path)
    app=NS(events=queue.Queue(),hwnd=1,test=False,uia=Worker())
    app.record_insertion=lambda *args:Desktop.record_insertion(app,*args)
    session=NS(cancel=threading.Event(),ident=1,target=w.Target(10,editable=True),recording_id='synthetic-recording')
    monkeypatch.setattr(w,'modifiers_held',lambda:False)
    return app,session

def test_clipboard_failure_is_tied_to_dictation_and_stage(monkeypatch,tmp_path):
    app,session=app_and_session(monkeypatch,tmp_path)
    monkeypatch.setattr(w,'ClipboardBackup',lambda _:(_ for _ in ()).throw(w.ClipboardBackupError('Formaat niet uitleesbaar',[13,50000],50000)))
    Desktop.insert(app,session,{'text':'Private sentence that must not be logged.'})
    report=json.loads((tmp_path/'logs/desktop-last-insertion.json').read_text())
    assert report['recording_id']=='synthetic-recording' and report['status']=='blocked'
    assert report['failed_stage']=='clipboard_backup' and report['failed_format']==50000
    assert 'Private sentence' not in json.dumps(report)

def test_clipboard_restore_failure_does_not_claim_paste_failed(monkeypatch,tmp_path):
    app,session=app_and_session(monkeypatch,tmp_path)
    def restore(_):raise OSError('Restore failed')
    backup=NS(sequence=1,items=[[13,'bytes',b'example']],restore=restore,dispose=lambda:None)
    monkeypatch.setattr(w,'ClipboardBackup',lambda _:backup)
    monkeypatch.setattr(w,'clipboard_sequence',lambda:1)
    monkeypatch.setattr(w,'copy_text',lambda *_:2)
    monkeypatch.setattr(w,'foreground',lambda:10)
    monkeypatch.setattr(w,'paste_once',lambda:True)
    Desktop.insert(app,session,{'text':'Synthetic text.'})
    report=json.loads((tmp_path/'logs/desktop-last-insertion.json').read_text())
    assert report['status']=='verified' and report['clipboard_restore']=='error'
    assert report['failed_stage']=='clipboard_restore' and session.paste_sent
