"""User-owned local library and rolling 30-day transcript history."""
import json, sqlite3, time, uuid, re, unicodedata
from contextlib import contextmanager
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DB=ROOT/'data/flow-lab.sqlite'
RETENTION_DAYS=30

def alias_key(value):
    value=unicodedata.normalize('NFKD',value.casefold().replace('/',' slash '))
    value=''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(re.findall(r'\w+',value))

@contextmanager
def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB,timeout=5);c.row_factory=sqlite3.Row
    c.execute('PRAGMA secure_delete=ON')
    try:yield c;c.commit()
    finally:c.close()

def init():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,aliases TEXT NOT NULL,value TEXT NOT NULL,enabled INTEGER NOT NULL,source TEXT NOT NULL,updated_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY,created_at REAL NOT NULL,raw TEXT NOT NULL,text TEXT NOT NULL,metadata TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS history_time ON history(created_at DESC);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS learning_cases(id TEXT PRIMARY KEY,wrong TEXT NOT NULL,right TEXT NOT NULL,wrong_key TEXT NOT NULL,right_key TEXT NOT NULL,mode TEXT NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL,target_id TEXT,entry_id TEXT,entry_revision REAL,created_entry INTEGER NOT NULL DEFAULT 0,created_at REAL NOT NULL,updated_at REAL NOT NULL,UNIQUE(wrong_key,right_key));
        CREATE TABLE IF NOT EXISTS learning_evidence(case_id TEXT NOT NULL,dictation_id TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(case_id,dictation_id));
        CREATE TABLE IF NOT EXISTS learning_blocks(word_key TEXT PRIMARY KEY,created_at REAL NOT NULL);
        ''')
        if 'target_id' not in {row[1] for row in c.execute('PRAGMA table_info(learning_cases)')}:
            c.execute('ALTER TABLE learning_cases ADD COLUMN target_id TEXT')
        if not c.execute('SELECT 1 FROM entries LIMIT 1').fetchone():
            initial=json.loads((ROOT/'dictionary.json').read_text(encoding='utf-8')).get('replacements',{})
            for alias,value in initial.items():
                c.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),'dictionary',value,json.dumps([alias],ensure_ascii=False),value,1,'flow-lab',time.time()))
    prune()

def prune(now=None):
    with connect() as c:c.execute('DELETE FROM history WHERE created_at < ?',((time.time() if now is None else now)-RETENTION_DAYS*86400,))

def entries(kind=None):
    with connect() as c:
        rows=c.execute('SELECT * FROM entries'+(' WHERE kind=?' if kind else '')+' ORDER BY name COLLATE NOCASE',(kind,) if kind else ()).fetchall()
    return [dict(r,aliases=json.loads(r['aliases']),enabled=bool(r['enabled'])) for r in rows]

def save_entry(kind,data,source='user'):
    if kind not in ('dictionary','snippet'):raise ValueError('Onbekend type.')
    name=str(data.get('name','')).strip();value=str(data.get('value',''))
    if kind=='dictionary':value=value.strip();name=value
    aliases=data.get('aliases',[])
    if not isinstance(aliases,list) or any(not isinstance(a,str) for a in aliases):raise ValueError('Varianten moeten losse teksten zijn.')
    aliases=list(dict.fromkeys(a.strip() for a in aliases if a.strip()))
    if not name or not value.strip() or not aliases:raise ValueError('Vul een naam, tekst en minstens één herkenningsvariant in.')
    if len(name)>160 or len(value)>(20000 if kind=='snippet' else 200) or len(aliases)>60 or any(len(a)>160 for a in aliases):raise ValueError('Naam, tekst of varianten zijn te lang.')
    if any(not alias_key(a) for a in aliases):raise ValueError('Een variant moet een woord bevatten.')
    identifier=str(data.get('id') or uuid.uuid4());enabled=bool(data.get('enabled',True))
    with connect() as c:
        prior=c.execute('SELECT * FROM entries WHERE id=?',(identifier,)).fetchone()
        if prior and prior['kind']!=kind:raise ValueError('Dit item heeft een ander type.')
        wanted={alias_key(a) for a in aliases}
        if enabled:
            for row in c.execute('SELECT id,name,aliases FROM entries WHERE kind=? AND enabled=1 AND id<>?',(kind,identifier)):
                if wanted.intersection(alias_key(a) for a in json.loads(row['aliases'])):raise ValueError('Een variant wordt al gebruikt door '+row['name']+'.')
        effective_source=source if source=='user' else (prior['source'] if prior and prior['source']=='user' else source)
        if prior and prior['source']=='spelling-hint' and wanted=={alias_key(value)}:effective_source='spelling-hint'
        if kind=='dictionary' and source=='user':
            prior_keys={alias_key(a) for a in json.loads(prior['aliases'])} if prior else set()
            removed=prior_keys-wanted
            if not enabled:removed|=wanted|{alias_key(value)}
            for key in removed:c.execute('INSERT OR REPLACE INTO learning_blocks VALUES(?,?)',(key,time.time()))
            if enabled:
                for key in wanted|{alias_key(value)}:c.execute('DELETE FROM learning_blocks WHERE word_key=?',(key,))
        c.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,aliases=excluded.aliases,value=excluded.value,enabled=excluded.enabled,source=excluded.source,updated_at=excluded.updated_at',(identifier,kind,name,json.dumps(aliases,ensure_ascii=False),value,int(enabled),effective_source,time.time()))
    return identifier

def delete_entry(kind,identifier):
    with connect() as c:
        if kind=='dictionary':
            row=c.execute('SELECT value,aliases FROM entries WHERE kind=? AND id=?',(kind,identifier)).fetchone()
            if row:
                for value in [row['value'],*json.loads(row['aliases'])]:
                    c.execute('INSERT OR REPLACE INTO learning_blocks VALUES(?,?)',(alias_key(value),time.time()))
        c.execute('DELETE FROM entries WHERE kind=? AND id=?',(kind,identifier))

def add_history(raw,text,metadata,identifier=None,created_at=None):
    if not text.strip():return None
    prune();identifier=identifier or str(uuid.uuid4())
    with connect() as c:
        c.execute('INSERT OR IGNORE INTO history VALUES(?,?,?,?,?)',(identifier,time.time() if created_at is None else created_at,raw,text,json.dumps(metadata,ensure_ascii=False)))
    return identifier

def history_result(identifier):
    with connect() as c:row=c.execute('SELECT raw,text,metadata FROM history WHERE id=?',(identifier,)).fetchone()
    if not row:return None
    return {**json.loads(row['metadata']),'raw':row['raw'],'text':row['text'],'history_id':identifier}

def history(query='',limit=50,offset=0):
    prune();query=query[:200];limit=max(1,min(int(limit),100));offset=max(0,int(offset))
    escaped=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    where="WHERE text LIKE ? ESCAPE '\\' OR raw LIKE ? ESCAPE '\\'" if query else ''
    params=('%'+escaped+'%','%'+escaped+'%') if query else ()
    with connect() as c:
        total=c.execute('SELECT count(*) FROM history '+where,params).fetchone()[0]
        rows=c.execute('SELECT * FROM history '+where+' ORDER BY created_at DESC LIMIT ? OFFSET ?',(*params,limit,offset)).fetchall()
    return {'items':[dict(r,metadata=json.loads(r['metadata'])) for r in rows],'total':total,'retention_days':RETENTION_DAYS,'offset':offset}

def delete_history(identifier):
    with connect() as c:c.execute('DELETE FROM history WHERE id=?',(identifier,))

def setting(name,default=None):
    with connect() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(name,)).fetchone()
    return json.loads(r[0]) if r else default

def set_setting(name,value):
    with connect() as c:c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(name,json.dumps(value,ensure_ascii=False)))

init()
