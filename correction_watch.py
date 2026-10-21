"""Bounded read-only sampling of the last dictation, isolated from insertion UIA."""
import threading
import time
from correction_learning import WINDOW_SECONDS,QUIET_SECONDS,own_region,candidates
POLL_SECONDS=.5

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
        self.proposal=None;self.review_request=None

    def is_current(self,proposal):
        return bool(proposal and self.proposal is proposal and self.token is proposal['token']
                    and not proposal['token'].is_set() and self.enabled()
                    and time.monotonic()<proposal['expires_at'])

    def clear_proposal(self):
        old=self.proposal;self.proposal=None;self.review_request=None
        if old:self.notify({'kind':'proposal_clear','proposal':old})

    def request_review(self,proposal,action):
        if action not in ('accept','ignore') or not self.is_current(proposal) or self.review_request:return False
        self.review_request=(proposal,action)
        return True

    def stop(self):
        if self.token:self.token.set()
        self.token=None
        self.clear_proposal()

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
                    current=own_region(basis,snapshot['text']) if snapshot else None
                    if self.proposal and (current!=self.proposal['region'] or snapshot.get('composing') or not self.is_current(self.proposal)):
                        self.clear_proposal()
                    state,region=session.sample(snapshot,time.monotonic())
                    if state=='stop':break
                    requested=self.review_request;self.review_request=None
                    if requested:
                        proposal,action=requested
                        if (self.is_current(proposal) and current==proposal['region'] and not snapshot.get('composing')
                                and time.monotonic()-session.changed_at>=QUIET_SECONDS):
                            try:
                                self.repository.review(proposal['case_id'],action,expected_revision=proposal['revision'],
                                                       dictation_id=dictation_id,active=lambda:active() and self.is_current(proposal))
                                self.notify('changed')
                            except ValueError:pass # A later revision or user decision wins.
                        self.clear_proposal()
                    if state=='stable':
                        items=candidates(basis['original'],region,self.repository.catalog())
                        changes=self.repository.observe(dictation_id,items,active=active)
                        if changes and active():
                            self.notify('changed')
                            rows=self.repository.list()
                            pending=next((row for row in rows if row['id'] in changes and row['state']=='pending'),None)
                            if pending:
                                self.clear_proposal()
                                proposal={'case_id':pending['id'],'revision':pending['updated_at'],'dictation_id':dictation_id,
                                          'hwnd':hwnd,'runtime':runtime,'token':token,'region':region,'wrong':pending['wrong'],
                                          'right':pending['right'],'mode':pending['mode'],
                                          'expires_at':min(session.started+WINDOW_SECONDS,time.monotonic()+10)}
                                self.proposal=proposal
                                self.notify({'kind':'proposal','proposal':proposal})
                except TimeoutError:
                    if future:future.cancel()
                    self.stalled=True
                    if active():self.notify('stalled')
                    break
                except Exception:
                    break # Incompatible provider: learning stops without touching the text.
                token.wait(POLL_SECONDS)
            token.set()
            if self.token is token:self.clear_proposal()
        threading.Thread(target=run,daemon=True).start()
