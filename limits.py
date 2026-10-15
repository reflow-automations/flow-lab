"""Shared bounds for five-minute dictation; no personal settings."""
MAX_SECONDS=300
PCM_RATE=24000
PCM_BYTES_PER_SECOND=PCM_RATE*2
MAX_PCM_BYTES=MAX_SECONDS*PCM_BYTES_PER_SECOND
MAX_WAV_BYTES=128*1024*1024
MAX_TEXT_CHARS=24000
FORMAT_CHUNK_CHARS=4000
SESSION_TIMEOUT_SECONDS=MAX_SECONDS+420
LIMIT_MESSAGE='Maximaal 5 minuten per opname.'

class AudioBudget:
    """Trim the final device block at a complete sample, then accept no more audio."""
    def __init__(self,limit=MAX_PCM_BYTES):self.limit=limit;self.used=0
    def take(self,data):
        remaining=max(0,self.limit-self.used)
        accepted=data[:min(len(data),remaining)//2*2]
        self.used+=len(accepted)
        return accepted
    @property
    def full(self):return self.used>=self.limit

def split_format_text(text,limit=FORMAT_CHUNK_CHARS):
    import re
    parts=[];remaining=text.strip()
    while len(remaining)>limit:
        window=remaining[:limit+1]
        boundaries=[m.end() for m in re.finditer(r'(?<=[.!?])\s+|\n\s*\n',window) if m.end()>=limit//2]
        cut=boundaries[-1] if boundaries else window.rfind(' ',0,limit+1)
        if cut<=0:raise ValueError('Een enkel woord is te lang om veilig op te maken.')
        parts.append(remaining[:cut].strip());remaining=remaining[cut:].strip()
    if remaining:parts.append(remaining)
    return parts
