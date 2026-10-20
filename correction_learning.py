"""Local correction decisions and reversible dictionary updates. No network or UI."""
from difflib import SequenceMatcher
import json
import re
import time
import uuid
import storage

WINDOW_SECONDS=60
QUIET_SECONDS=1.5
WORD=re.compile(r'[^\W_]+(?:[\x27’\-][^\W_]+)*',re.UNICODE)
QUOTES=re.compile(r'"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’|(?<!\w)\x27[^\x27\n]+\x27(?!\w)|`[^`\n]*`')
COMMON=set('ik jij je hij zij ze wij we jullie u het de een en of maar want dus dat dit die deze is was zijn waren heb heeft hebben kan kunnen wil willen moet moeten niet wel geen misschien zeker morgen gisteren vandaag maandag dinsdag woensdag donderdag vrijdag zaterdag zondag ja nee betaald betalen werkt werken dag tijd naam woord term you me my your he she we they it the a an and or but because this that is was are were have has can could would should will not yes no maybe tomorrow today yesterday higher lower right wrong'.split())
COMMON.update('mijn jouw uw haar hun ons onze iedere elk welke your our their its'.split())

def basis_for_placement(actual,dictated,prefix,suffix):
    actual=actual.replace('\r\n','\n').replace('\r','\n').rstrip('\n')
    dictated=dictated.replace('\r\n','\n').replace('\r','\n').rstrip('\n')
    if not dictated or len(actual)>40000:return None
    expected=(prefix+dictated+suffix).rstrip('\n')
    if actual==expected and actual[len(prefix):len(prefix)+len(dictated)]==dictated:start=len(prefix)
    elif actual==dictated:start=0
    elif actual.count(dictated)==1 and actual.split()==expected.split():start=actual.index(dictated)
    else:return None
    return {'original':dictated,'prefix':actual[:start],'suffix':actual[start+len(dictated):]}

def own_region(basis,current):
    prefix=basis['prefix'];suffix=basis['suffix']
    if not current.startswith(prefix) or (suffix and not current.endswith(suffix)):return None
    end=len(current)-len(suffix) if suffix else len(current)
    if end<len(prefix):return None
    return current[len(prefix):end]

def safe_phrase(value):
    if value.casefold().startswith(('sk-','ghp-','eyj')):return False
    if any(len(word)>32 or len(word)>=16 and all(c in '0123456789abcdefABCDEF' for c in word) for word in value.split()):return False
    return 2<=len(value)<=80 and bool(re.fullmatch(r'[^\W_]+(?:[\x27’\- ][^\W_]+){0,2}',value,re.UNICODE)) and any(c.isalpha() for c in value) and not value.isnumeric()

def name_span(before,after,left,right,i,j,k,l,catalog):
    """Keep a corrected word scoped to a name; never turn a name part into a global alias."""
    options=[]
    for prefix in range(min(i,k,2)+1):
        for suffix in range(min(len(left)-j,len(right)-l,2)+1):
            if not prefix+suffix or l-k+prefix+suffix>3:continue
            a,b=i-prefix,j+suffix;c,d=k-prefix,l+suffix
            if [m[0] for m in left[a:i]]!=[m[0] for m in right[c:k]]:continue
            if [m[0] for m in left[j:b]]!=[m[0] for m in right[l:d]]:continue
            old=before[left[a].start():left[b-1].end()];new=after[right[c].start():right[d-1].end()]
            if not safe_phrase(old) or not safe_phrase(new):continue
            known=next((row for row in catalog if storage.alias_key(row['value'])==storage.alias_key(new)),None)
            if known:options.append((d-c,a,b,c,d))
    if options:
        _,a,b,c,d=max(options)
        return a,b,c,d
    # A lowercase second name part is still a useful proposal when its unchanged
    # first part looks like a name. Ordinary determiners are excluded.
    if j-i==l-k==1 and i>0 and k>0 and right[k][0][0].islower():
        prefix=right[k-1][0]
        if (left[i-1][0]==prefix and prefix[0].isupper() and len(prefix)>=3
                and storage.alias_key(prefix) not in COMMON
                and re.fullmatch(r'[ \t]+',before[left[i-1].end():left[i].start()])
                and re.fullmatch(r'[ \t]+',after[right[k-1].end():right[k].start()])):
            return i-1,j,k-1,l
    return i,j,k,l

def candidates(before,after,catalog):
    """Only small replacements in the owned passage; additions alone never teach."""
    if len(before)>24000 or len(after)>26000 or not after.strip():return []
    left=list(WORD.finditer(before));right=list(WORD.finditer(after))
    if not left or not right:return []
    ops=SequenceMatcher(None,[m[0] for m in left],[m[0] for m in right],autojunk=False).get_opcodes()
    changed=[op for op in ops if op[0]!='equal']
    if len(changed)>3:return []
    if any(tag=='delete' or (tag=='insert' and i<len(left)) for tag,i,j,k,l in changed):return []
    quotes_left=[m.span() for m in QUOTES.finditer(before)];quotes_right=[m.span() for m in QUOTES.finditer(after)]
    results=[]
    for tag,i,j,k,l in changed:
        # Correcting the final name and then continuing to type is one diff block.
        # Only a known canonical spelling can bound that correction reliably.
        if tag=='replace' and j==len(left) and 1<=j-i<=2 and l-k>2:
            for length in (2,1):
                proposed=after[right[k].start():right[k+length-1].end()]
                if any(row['enabled'] and storage.alias_key(row['value'])==storage.alias_key(proposed) for row in catalog):
                    l=k+length;break
        if tag!='replace' or not 1<=j-i<=2 or not 1<=l-k<=2:continue
        changed_wrong=before[left[i].start():left[j-1].end()]
        changed_right=after[right[k].start():right[l-1].end()]
        if not safe_phrase(changed_wrong) or not safe_phrase(changed_right):continue
        if storage.alias_key(changed_wrong) in COMMON or storage.alias_key(changed_right) in COMMON:continue
        a,b,c,d=name_span(before,after,left,right,i,j,k,l,catalog)
        contextual=(a,b,c,d)!=(i,j,k,l)
        i,j,k,l=a,b,c,d
        start,end=left[i].start(),left[j-1].end();new_start,new_end=right[k].start(),right[l-1].end()
        def unsafe_context(text,a,b):
            first=max(text.rfind(' ',0,a),text.rfind('\n',0,a))+1
            stops=[position for mark in ' \n' if (position:=text.find(mark,b))>=0]
            token=text[first:min(stops) if stops else len(text)]
            return any(symbol in token for symbol in '@/\\_`#$=<>{}[]') or bool(re.search(r'\w\.\w',token))
        if unsafe_context(before,start,end) or unsafe_context(after,new_start,new_end):continue
        if any(start<b and end>a for a,b in quotes_left) or any(new_start<b and new_end>a for a,b in quotes_right):continue
        wrong=before[start:end];correct=after[new_start:new_end]
        if not safe_phrase(wrong) or not safe_phrase(correct):continue
        wk=storage.alias_key(wrong);rk=storage.alias_key(correct)
        if wk==rk or wk in COMMON or rk in COMMON:continue
        if any(c.isdigit() for c in wrong+correct):continue
        known=next((row for row in catalog if storage.alias_key(row['value'])==rk),None)
        if known and (not known['enabled'] or known.get('source')=='wispr-hint'):continue
        changed_wk=storage.alias_key(changed_wrong);changed_rk=storage.alias_key(changed_right)
        ratio=SequenceMatcher(None,changed_wk.replace(' ',''),changed_rk.replace(' ','')).ratio()
        ambiguous=changed_wrong.isupper() and len(changed_wrong)<=5 or len(changed_wk)<4 or ratio<.55
        if known:mode='confirm' if ambiguous else 'auto'
        elif correct[0].isupper() and len(rk)>=4:
            preceding=after[:new_start].rstrip()
            sentence_initial=not preceding or preceding[-1] in '.!?'
            mode='confirm' if ambiguous or sentence_initial else 'repeat'
        else:continue
        results.append({'wrong':wrong,'right':known['value'] if known else correct,'mode':mode,'known_id':known['id'] if known else None,
                        'reason':'Dubbelzinnige of korte variant' if ambiguous else 'Bekende schrijfwijze' if known else 'Nieuwe naam met woordcontext' if contextual else 'Nieuwe naam of term'})
    return results

class Repository:
    def catalog(self):return storage.entries('dictionary')

    def list(self):
        with storage.connect() as c:
            c.execute("DELETE FROM learning_cases WHERE state IN ('pending','withdrawn') AND updated_at<?",(time.time()-30*86400,))
            c.execute('DELETE FROM learning_evidence WHERE case_id NOT IN (SELECT id FROM learning_cases)')
            rows=c.execute('SELECT l.*, (SELECT count(*) FROM learning_evidence e WHERE e.case_id=l.id AND e.active=1) AS observations FROM learning_cases l ORDER BY updated_at DESC LIMIT 100').fetchall()
        return [dict(row) for row in rows]

    def _undo(self,c,row,state='undone',explicit=False):
        now=time.time();entry=c.execute('SELECT * FROM entries WHERE id=?',(row['entry_id'],)).fetchone()
        if entry:
            if entry['value']!=row['right'] or (not explicit and entry['updated_at']!=row['entry_revision']):
                c.execute("UPDATE learning_cases SET state='conflict',reason=?,updated_at=? WHERE id=?",('Woordenboek intussen gewijzigd; controleer de variant daar.',now,row['id']));return
            aliases=json.loads(entry['aliases']);remaining=[a for a in aliases if a!=row['wrong']]
            if row['created_entry'] and not remaining and entry['source']=='auto-learn':c.execute('DELETE FROM entries WHERE id=?',(entry['id'],))
            else:
                c.execute('UPDATE entries SET aliases=?,updated_at=? WHERE id=?',(json.dumps(remaining or [entry['value']],ensure_ascii=False),now,entry['id']))
                c.execute("UPDATE learning_cases SET entry_revision=? WHERE entry_id=? AND entry_revision=? AND state='learned'",(now,entry['id'],entry['updated_at']))
        c.execute('UPDATE learning_cases SET state=?,updated_at=? WHERE id=?',(state,now,row['id']))

    def _apply(self,c,row):
        now=time.time();all_entries=[dict(r,aliases=json.loads(r['aliases'])) for r in c.execute("SELECT * FROM entries WHERE kind='dictionary'")]
        blocked={r[0] for r in c.execute('SELECT word_key FROM learning_blocks')}
        if row['wrong_key'] in blocked or row['right_key'] in blocked:
            c.execute("UPDATE learning_cases SET state='conflict',reason=?,updated_at=? WHERE id=?",('Deze schrijfwijze is handmatig uitgezet of verwijderd. Beheer haar in het woordenboek.',now,row['id']));return
        entry=next((r for r in all_entries if storage.alias_key(r['value'])==row['right_key']),None)
        if row['target_id'] and (not entry or entry['id']!=row['target_id']):
            c.execute("UPDATE learning_cases SET state='conflict',reason=?,updated_at=? WHERE id=?",('Doelwoord is intussen gewijzigd. Controleer het woordenboek.',now,row['id']));return
        if entry and (not entry['enabled'] or entry['source']=='wispr-hint'):return
        if any(row['wrong_key'] in [storage.alias_key(a) for a in item['aliases']] and (not entry or item['id']!=entry['id']) for item in all_entries):
            c.execute("UPDATE learning_cases SET state='conflict',reason=?,updated_at=? WHERE id=?",('Variant hoort al bij een andere woordenboekregel.',now,row['id']));return
        created=not bool(entry)
        if entry:
            if row['wrong_key'] in [storage.alias_key(a) for a in entry['aliases']]:
                c.execute("UPDATE learning_cases SET state='covered',updated_at=? WHERE id=?",(now,row['id']));return
            if len(entry['aliases'])>=60:return
            aliases=[*entry['aliases'],row['wrong']]
            c.execute('UPDATE entries SET aliases=?,updated_at=? WHERE id=?',(json.dumps(aliases,ensure_ascii=False),now,entry['id']))
            c.execute("UPDATE learning_cases SET entry_revision=? WHERE entry_id=? AND entry_revision=? AND state='learned'",(now,entry['id'],entry['updated_at']))
            entry_id=entry['id']
        else:
            entry_id=str(uuid.uuid4())
            c.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,?,?)',(entry_id,'dictionary',row['right'],json.dumps([row['wrong']],ensure_ascii=False),row['right'],1,'auto-learn',now))
        c.execute("UPDATE learning_cases SET state='learned',entry_id=?,entry_revision=?,created_entry=?,updated_at=? WHERE id=?",(entry_id,now,int(created),now,row['id']))

    def observe(self,dictation_id,items,active=lambda:True):
        if not dictation_id or not active():return []
        changed=[];now=time.time()
        with storage.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not active():return []
            present={(storage.alias_key(item['wrong']),storage.alias_key(item['right'])) for item in items}
            previous=c.execute('SELECT l.* FROM learning_cases l JOIN learning_evidence e ON e.case_id=l.id WHERE e.dictation_id=? AND e.active=1',(dictation_id,)).fetchall()
            for row in previous:
                if (row['wrong_key'],row['right_key']) in present:continue
                c.execute('UPDATE learning_evidence SET active=0 WHERE case_id=? AND dictation_id=?',(row['id'],dictation_id))
                count=c.execute('SELECT count(*) FROM learning_evidence WHERE case_id=? AND active=1',(row['id'],)).fetchone()[0]
                if row['state']=='learned' and count<(2 if row['mode']=='repeat' else 1):self._undo(c,row,'withdrawn');changed.append(row['id'])
                elif row['state']=='pending' and count==0:c.execute("UPDATE learning_cases SET state='withdrawn',updated_at=? WHERE id=?",(now,row['id']))
            for item in items:
                wrong=item['wrong'];right=item['right'];wk=storage.alias_key(wrong);rk=storage.alias_key(right)
                if not safe_phrase(wrong) or not safe_phrase(right) or wk==rk:continue
                if c.execute('SELECT 1 FROM learning_blocks WHERE word_key IN (?,?)',(wk,rk)).fetchone():continue
                row=c.execute('SELECT * FROM learning_cases WHERE wrong_key=? AND right_key=?',(wk,rk)).fetchone()
                if row and row['state'] in ('ignored','undone','conflict','covered'):continue
                case_id=row['id'] if row else str(uuid.uuid4())
                if not row:
                    c.execute('INSERT INTO learning_cases(id,wrong,right,wrong_key,right_key,mode,state,reason,target_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(case_id,wrong,right,wk,rk,item['mode'],'pending',item['reason'],item.get('known_id'),now,now))
                c.execute('INSERT INTO learning_evidence VALUES(?,?,1) ON CONFLICT(case_id,dictation_id) DO UPDATE SET active=1',(case_id,dictation_id))
                if row and row['state']=='learned':continue
                count=c.execute('SELECT count(*) FROM learning_evidence WHERE case_id=? AND active=1',(case_id,)).fetchone()[0]
                c.execute("UPDATE learning_cases SET state='pending',updated_at=? WHERE id=?",(now,case_id))
                row=c.execute('SELECT * FROM learning_cases WHERE id=?',(case_id,)).fetchone()
                if row['mode']=='auto' or row['mode']=='repeat' and count>=2:self._apply(c,row)
                changed.append(case_id)
            if not active():
                c.rollback();return []
        return changed

    def review(self,case_id,action):
        if action not in ('accept','ignore','undo'):raise ValueError('Onbekende leeractie.')
        with storage.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM learning_cases WHERE id=?',(case_id,)).fetchone()
            if not row:raise ValueError('Voorstel niet gevonden.')
            if action=='undo' and row['state']=='learned':self._undo(c,row,explicit=True)
            elif action=='ignore':
                if row['state']=='learned':self._undo(c,row,'ignored',explicit=True)
                else:c.execute("UPDATE learning_cases SET state='ignored',updated_at=? WHERE id=?",(time.time(),case_id))
            elif action=='accept' and row['state']!='learned':self._apply(c,row)
        return next((item for item in self.list() if item['id']==case_id),None)
