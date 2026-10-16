"""Bounded read-only sampling of the last dictation, isolated from insertion UIA."""
import threading
import time
from correction_learning import WINDOW_SECONDS,QUIET_SECONDS,own_region,candidates

class Session:
    def __init__(self,basis,started):
        self.basis=basis;self.started=started;self.last_value=basis['original']
        self.changed_at=started;self.delivered=None

    def sample(self,snapshot,now):
        if now-self.started>=WINDOW_SECONDS:return 'stop',None
        if not snapshot:return 'stop',None
        region=own_region(self.basis,snapshot['text'])
        if region is None:return 'stop',None
        if snapshot.get('composing'):
            self.changed_at=now;self.last_value=region;return 'wait',None
        if region!=self.last_value:
            self.last_value=region;self.changed_at=now;return 'wait',None
        if now-self.changed_at<QUIET_SECONDS or region==self.delivered:return 'wait',None
        self.delivered=region
        return 'stable',region

class Watcher:
    def __init__(self,worker_factory,snapshot,repository,enabled,notify):
        self.worker_factory=worker_factory;self.snapshot=snapshot;self.repository=repository
        self.enabled=enabled;self.notify=notify;self.worker=None;self.token=None;self.stalled=False

    def stop(self):
        if self.token:self.token.set()
        self.token=None

    def begin(self,hwnd,runtime,basis,dictation_id):
        self.stop()
        if self.stalled or not self.enabled() or not basis or not dictation_id:return
        if self.worker is None:self.worker=self.worker_factory()
        token=threading.Event();self.token=token
        def active():return not token.is_set() and self.enabled()
        def run():
            session=Session(basis,time.monotonic())
            while active() and time.monotonic()-session.started<WINDOW_SECONDS:
                future=None
                try:
                    future=self.worker.submit(self.snapshot,hwnd,runtime)
                    snapshot=future.result(timeout=.4)
                    if not active():break
                    state,region=session.sample(snapshot,time.monotonic())
                    if state=='stop':break
                    if state=='stable':
                        items=candidates(basis['original'],region,self.repository.catalog())
                        changes=self.repository.observe(dictation_id,items,active=active)
                        if changes and active():self.notify('changed')
                except TimeoutError:
                    if future:future.cancel()
                    self.stalled=True
                    if active():self.notify('stalled')
                    break
                except Exception:
                    break # Incompatible provider: learning stops without touching the text.
                token.wait(.5)
            token.set()
        threading.Thread(target=run,daemon=True).start()
