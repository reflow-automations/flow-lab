"""Pure hold-to-talk / double-tap state machine, independent of microphone and UI."""
class DictationGesture:
    TAP_SECONDS=.25
    DOUBLE_SECONDS=.32

    def __init__(self):self.reset()
    def reset(self):
        self.mode='idle';self.pressed=False;self.pressed_at=0.;self.deadline=0.

    def tick(self,now):
        if self.mode=='tap_wait' and now>=self.deadline:
            self.mode='processing';return ['stop']
        return []

    def feed(self,event,now):
        if event=='cancel':
            active=self.mode in ('hold','tap_wait','locked')
            self.reset();return ['cancel'] if active else []
        actions=self.tick(now)
        if event=='down':
            if self.pressed:return actions
            self.pressed=True;self.pressed_at=now
            if self.mode=='idle':self.mode='hold';actions.append('start')
            elif self.mode=='tap_wait':self.mode='locked';actions.append('lock')
            elif self.mode=='locked':self.mode='processing';actions.append('stop')
        elif event=='up':
            if not self.pressed:return actions
            self.pressed=False
            if self.mode=='hold':
                if now-self.pressed_at<=self.TAP_SECONDS:
                    self.mode='tap_wait';self.deadline=now+self.DOUBLE_SECONDS
                else:self.mode='processing';actions.append('stop')
        return actions
