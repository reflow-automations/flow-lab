"""Deterministic aliases, protected snippets and whitespace-only paragraph layout."""
import re, secrets
import storage

def alias_pattern(alias):
    tokens=storage.alias_key(alias).split()
    letters={'e':'[eéèêë]','a':'[aáàâä]','i':'[iíìîï]','o':'[oóòôö]','u':'[uúùûü]'}
    def word(s):return ''.join(letters.get(c,re.escape(c)) for c in s)
    if tokens and tokens[0]=='slash' and len(tokens)>1:
        pattern=r'(?:/\s*|slash[\s_-]+)'+r'[\s_-]+'.join(word(w) for w in tokens[1:])
    else:pattern=r'[\s_-]+'.join(word(w) for w in tokens)
    return re.compile(r'(?<![\w/])'+pattern+r'(?!\w)',re.I)

def matches(text,items,include_canonical=False):
    found=[]
    for item in items:
        if not item['enabled']:continue
        if include_canonical and item.get('source')=='wispr-hint':continue
        aliases=item['aliases']+([item['value']] if include_canonical else [])
        for alias in aliases:
            for m in alias_pattern(alias).finditer(text):found.append((m.start(),m.end(),item))
    found.sort(key=lambda x:(x[0],-(x[1]-x[0])))
    selected=[];end=-1
    for m in found:
        if m[0]>=end:selected.append(m);end=m[1]
    return selected

def dictionary_replace(text):
    parts=[];pos=0
    for start,end,item in matches(text,storage.entries('dictionary'),True):
        parts.extend([text[pos:start],item['value']]);pos=end
    return ''.join(parts)+text[pos:]

def protect_snippets(text):
    parts=[];protected={};pos=0
    prefix='FLOWLAB_'+secrets.token_hex(6).upper()+'_'
    for start,end,item in matches(text,storage.entries('snippet')):
        token=prefix+str(len(protected))+'_END'
        protected[token]={'text':item['value'],'name':item['name'],'id':item['id']}
        parts.extend([text[pos:start],token]);pos=end
    return ''.join(parts)+text[pos:],protected

def restore_snippets(text,protected):
    if any(text.count(token)!=1 for token in protected):raise ValueError('Een beschermde snippetmarkering is gewijzigd.')
    for token,item in protected.items():text=text.replace(token,item['text'])
    return text

def snippet_preview(text):
    masked,protected=protect_snippets(text)
    if len(protected)==1 and masked.strip(' \t\r\n.!?,;:') in protected:
        result=next(iter(protected.values()))['text']
    else:result=restore_snippets(dictionary_replace(masked),protected)
    return {'text':result,'snippets':[x['name'] for x in protected.values()]}

def paragraph_layout(text,mode='normaal'):
    """Only alter whitespace at sentence boundaries; do not rewrite words or punctuation."""
    if mode=='compact':return text
    if mode not in ('normaal','ruim'):raise ValueError('Onbekende alinea-indeling.')
    blocks=re.split(r'\n\s*\n',text.strip());out=[]
    target=55 if mode=='normaal' else 35
    for block in blocks:
        # Preserve list lines, addresses, code and already deliberate short line breaks.
        lines=block.splitlines()
        if re.search(r'^\s*(?:[-*]|\d+[.)])\s|https?://|`',block,re.M) or (len(lines)>1 and all(len(line)<70 for line in lines)):
            out.append(block);continue
        block=' '.join(lines)
        sentences=re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-Ÿ0-9])',block)
        if len(sentences)<2:out.append(block);continue
        chunks=[];current=[];words=0
        for index,sentence in enumerate(sentences):
            count=len(sentence.split());transition=bool(re.match(r'(?:We hebben dus|Daarnaast|Verder|Tot slot|Ten slotte|Een ander punt|Vervolgens|Daarna|Overigens)\b',sentence,re.I))
            remaining=sum(len(s.split()) for s in sentences[index:])
            if current and ((transition and words>=12) or (remaining>=12 and ((words+count>target and words>=20) or (len(current)>=3 and words>=35)))):
                chunks.append(' '.join(current));current=[];words=0
            current.append(sentence);words+=count
        if current:chunks.append(' '.join(current))
        # A medium-sized block can still feel dense even below the hard word target.
        # Balance complete sentences instead of leaving a tiny final paragraph.
        minimum=30 if mode=='ruim' else 40
        counts=[len(s.split()) for s in sentences]
        if len(chunks)==1 and len(sentences)>=(2 if mode=='ruim' else 3) and sum(counts)>=minimum:
            candidates=[i for i in range(1,len(sentences)) if sum(counts[:i])>=12 and sum(counts[i:])>=12]
            if candidates:
                boundary=min(candidates,key=lambda i:abs(sum(counts[:i])-sum(counts)/2))
                chunks=[' '.join(sentences[:boundary]),' '.join(sentences[boundary:])]
        out.append('\n\n'.join(chunks))
    return '\n\n'.join(out)
