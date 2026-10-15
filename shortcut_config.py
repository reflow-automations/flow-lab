"""Shortcut validation and modifier-only chord recognition, without input logging."""
MODIFIERS={'ctrl':2,'alt':1,'shift':4,'win':8}
LABELS={'ctrl':'Ctrl','alt':'Alt','shift':'Shift','win':'Windows'}
KEYS={'space':(0x20,'Spatie'),'enter':(0x0D,'Enter'),'tab':(0x09,'Tab'),
      **{chr(n).lower():(n,chr(n)) for n in range(65,91)},
      **{str(n):(48+n,str(n)) for n in range(10)},
      **{f'f{n}':(111+n,f'F{n}') for n in range(1,25) if n!=12}}

def shortcut(value):
    parts=value.lower().split('-')
    mods=[p for p in parts if p in MODIFIERS]
    extra=[p for p in parts if p not in MODIFIERS]
    if len(mods)!=len(set(mods)) or len(extra)>1 or any(p not in KEYS for p in extra):
        raise ValueError('Kies een geldige toetscombinatie.')
    mask=sum(MODIFIERS[p] for p in mods)
    if not extra and len(mods)<2:
        raise ValueError('Kies minstens twee hulptoetsen, of voeg een toets toe.')
    if extra and not mask&11:
        raise ValueError('Gebruik Ctrl, Alt of Windows bij een extra toets.')
    ordered=[p for p in MODIFIERS if p in mods]
    canonical='-'.join(ordered+extra)
    label='+'.join([LABELS[p] for p in ordered]+([KEYS[extra[0]][1]] if extra else []))
    return canonical,mask,KEYS[extra[0]][0] if extra else 0,label

def shortcut_label(value):return shortcut(value)[3]

VK_MOD={0x10:4,0xA0:4,0xA1:4,0x11:2,0xA2:2,0xA3:2,0x12:1,0xA4:1,0xA5:1,0x5B:8,0x5C:8}

class ShortcutEdges:
    """Report physical chord down/up/cancel; never store text or repeat events."""
    def __init__(self,mask,key=0):
        self.mask=mask;self.key=key;self.down=set();self.active=False;self.blocked=False

    def feed(self,vk,is_down,injected=False):
        if injected:return None
        was_active=self.active
        if is_down:self.down.add(vk)
        else:self.down.discard(vk)
        present=0
        for k in self.down:present|=VK_MOD.get(k,0)
        extra=bool(present&~self.mask) or any(k not in VK_MOD and k!=self.key for k in self.down)
        if extra:self.blocked=True
        exact=present==self.mask and (not self.key or self.key in self.down) and not self.blocked
        event=None
        if exact and not was_active:self.active=True;event='down'
        elif was_active and not exact:
            self.active=False;event='cancel' if self.blocked else 'up'
        if not self.down:self.blocked=False
        return event

class ModifierChord:
    """Fire once on release, only if the whole gesture contained exactly this chord.

    Waiting for release prevents Ctrl+Windows+Alt or Ctrl+Windows+D from
    briefly starting dictation while the third key is being pressed.
    """
    def __init__(self,mask):
        self.mask=mask;self.down=set();self.armed=False;self.blocked=False;self.fired=False

    def feed(self,vk,is_down,injected=False):
        if injected:return False
        trigger=False
        if is_down:
            self.down.add(vk)
            present=0
            for key in self.down:present|=VK_MOD.get(key,0)
            if vk not in VK_MOD or present&~self.mask:self.blocked=True
            if present==self.mask and not self.blocked:self.armed=True
        else:
            if vk in self.down and VK_MOD.get(vk,0)&self.mask and self.armed and not self.blocked and not self.fired:
                trigger=True;self.fired=True
            self.down.discard(vk)
        if not self.down:self.armed=False;self.blocked=False;self.fired=False
        return trigger
