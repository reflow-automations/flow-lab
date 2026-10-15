"""Read the most recent retained result without altering history or calling a model."""
from pathlib import Path
import sqlite3
import time

def latest_text(path=None, now=None):
    path=Path(path) if path else Path(__file__).resolve().parent/'data/flow-lab.sqlite'
    if not path.exists(): return ''
    cutoff=(time.time() if now is None else now)-30*86400
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1) as c:
        c.execute('PRAGMA query_only=ON')
        row=c.execute("SELECT text FROM history WHERE created_at>=? AND trim(text)<>'' ORDER BY created_at DESC,rowid DESC LIMIT 1",(cutoff,)).fetchone()
    return row[0] if row else ''
