import json
import threading
import os
from types import SimpleNamespace as NS
import pytest
import launcher

def test_reused_pid_with_other_executable_is_not_a_running_backend(tmp_path):
    assert not launcher.process_alive(os.getpid(),tmp_path/'not-our-python.exe')

def test_native_start_lock_prevents_concurrent_launch(tmp_path):
    first=launcher.LaunchLock(tmp_path);observed=[]
    def second():
        lock=launcher.LaunchLock(tmp_path);observed.append(lock.acquired);lock.close()
    worker=threading.Thread(target=second);worker.start();worker.join(2)
    first.close()
    assert observed==[False]
    last=launcher.LaunchLock(tmp_path)
    try:assert last.acquired
    finally:last.close()

def test_warm_open_does_not_spawn_or_overwrite_server_pid(monkeypatch,tmp_path):
    (tmp_path/'logs').mkdir();(tmp_path/'logs/app-17865.pid').write_text('123')
    calls=[]
    monkeypatch.setattr(launcher,'service_status',lambda:{'app':'flow-lab'})
    monkeypatch.setattr(launcher,'helper_command',lambda root,action:calls.append(action) or {'pid':7})
    monkeypatch.setattr(launcher,'start_child',lambda *_:(_ for _ in ()).throw(AssertionError('No duplicate processes')))
    result=launcher.launch(tmp_path)
    assert result['ok'] and calls==['--status','--open']
    assert (tmp_path/'logs/app-17865.pid').read_text()=='123'
    assert json.loads((tmp_path/'logs/launcher-last-run.json').read_text())['elapsed_ms']>=0

def test_port_is_busy_without_ready_response_does_not_start_second_server(monkeypatch,tmp_path):
    statuses=iter([None,{'app':'flow-lab'}])
    monkeypatch.setattr(launcher,'service_status',lambda:next(statuses))
    monkeypatch.setattr(launcher,'port_open',lambda:True)
    monkeypatch.setattr(launcher,'helper_command',lambda *_:{'pid':7})
    monkeypatch.setattr(launcher,'start_child',lambda *_:(_ for _ in ()).throw(AssertionError('Do not overwrite listener')))
    monkeypatch.setattr(launcher.time,'sleep',lambda _:None)
    assert launcher.launch(tmp_path,True)['ok']

def test_start_timeout_is_bounded_and_leaves_failure_trace(monkeypatch,tmp_path):
    clock=[0]
    monkeypatch.setattr(launcher.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(launcher.time,'sleep',lambda amount:clock.__setitem__(0,clock[0]+amount))
    monkeypatch.setattr(launcher,'service_status',lambda:None)
    monkeypatch.setattr(launcher,'port_open',lambda:True)
    monkeypatch.setattr(launcher,'start_child',lambda *_:(_ for _ in ()).throw(AssertionError('Do not start another server')))
    with pytest.raises(TimeoutError):launcher.launch(tmp_path,True)
    result=json.loads((tmp_path/'logs/launcher-last-run.json').read_text())
    assert not result['ok'] and 45000<=result['elapsed_ms']<46000
    assert result['phases'][-1]['name']=='failed'

def test_second_click_does_not_replace_first_launch_trace(monkeypatch,tmp_path):
    (tmp_path/'logs').mkdir();prior=tmp_path/'logs/launcher-last-run.json';prior.write_text('first run')
    monkeypatch.setattr(launcher,'LaunchLock',lambda _:NS(acquired=False,close=lambda:None))
    result=launcher.launch(tmp_path,True)
    assert result['phases'][-1]['name']=='existing_launch_in_progress'
    assert prior.read_text()=='first run'
