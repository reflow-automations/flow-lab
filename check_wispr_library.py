"""Explicit read-only Wispr audit; optional additive repair, never overwrite local edits."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import time
import storage

def source_rows(path=None):
    path=path or Path(os.environ['APPDATA'])/'Wispr Flow/flow.sqlite'
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA query_only=ON')
        return [dict(r) for r in c.execute('SELECT id,phrase,replacement,isSnippet FROM Dictionary WHERE coalesce(isDeleted,0)=0')]

def audit(rows, local):
    report={'source_rows':len(rows),'source_types':{'snippet':0,'dictionary':0},'covered_exact':0,'dictionary_outer_whitespace_removed':0,'covered_disabled':0,'missing':[],'conflicts':[]}
    for r in rows:
        kind='snippet' if r['isSnippet'] else 'dictionary'
        report['source_types'][kind]+=1
        phrase=(r['phrase'] or '').strip(); value=r['replacement'] or phrase
        if kind=='dictionary':
            if value!=value.strip():report['dictionary_outer_whitespace_removed']+=1
            value=value.strip()
        matches=[e for e in local if e['kind']==kind and storage.alias_key(phrase) in {storage.alias_key(a) for a in e['aliases']}]
        exact=[e for e in matches if e['value']==value]
        if exact:
            report['covered_exact']+=1
            if not any(e['enabled'] for e in exact): report['covered_disabled']+=1
        else:
            report['conflicts' if matches else 'missing'].append({'source_id':r['id'],'kind':kind})
    report['local_counts']={k:sum(e['kind']==k for e in local) for k in ('snippet','dictionary')}
    return report

def reconcile(rows, apply=False):
    before=storage.entries(); report=audit(rows,before); added=[]
    if apply and report['missing']:
        # Library-only recovery snapshot. No transcript history or credentials.
        backup=storage.ROOT/'data'/('library-before-reconcile-'+str(time.time_ns())+'.json')
        backup.write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
        wanted={r['source_id'] for r in report['missing']}
        for r in rows:
            if r['id'] not in wanted: continue
            phrase=(r['phrase'] or '').strip(); value=r['replacement'] or phrase
            kind='snippet' if r['isSnippet'] else 'dictionary'
            current=storage.entries(kind)
            existing=next((e for e in current if e['value']==value),None)
            data=dict(existing) if existing else {'name':phrase if kind=='snippet' else value,'value':value,'aliases':[],'enabled':True}
            data['aliases']=list(dict.fromkeys(data['aliases']+[phrase]))
            source=existing['source'] if existing else ('wispr-import' if r['replacement'] or kind=='snippet' else 'wispr-hint')
            try:
                storage.save_entry(kind,data,source=source); added.append(r['id'])
            except ValueError:
                pass # Readback lists the unresolved row; never overwrite conflicts.
    final=audit(rows,storage.entries())
    return {'checked_at':time.time(),'added_source_rows':len(added),**final}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    result=reconcile(source_rows(),args.apply)
    (storage.ROOT/'data/wispr-library-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
