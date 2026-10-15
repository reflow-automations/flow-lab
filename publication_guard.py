"""Source publication checks. Inspect selected Git blobs, never private disk files."""
import argparse
import json
from pathlib import PurePosixPath
import re
import subprocess

BINARY={'assets/flow-lab.ico'}
GENERATED={'SOURCE-MANIFEST.json'}

def validate_public_files(contents,allowed):
    errors=[];allowed=set(allowed)|GENERATED
    for name,data in contents.items():
        p=PurePosixPath(name)
        if name not in allowed or p.is_absolute() or '..' in p.parts:
            errors.append(name+': not on publication allowlist');continue
        if any(part in {'data','logs','recordings','models','runtime','backups','.venv','releases'} for part in p.parts):
            errors.append(name+': private/generated directory');continue
        if p.name.startswith('.env') and name!='.env.example':errors.append(name+': environment file');continue
        if name in BINARY:
            if not data.startswith(b'\x00\x00\x01\x00'):errors.append(name+': expected ICO file')
            continue
        try:text=data.decode('utf-8')
        except UnicodeDecodeError:errors.append(name+': not UTF-8');continue
        patterns=[r'sk-(?:proj-)?[A-Za-z0-9_-]{24,}',r'gh[pousr]_[A-Za-z0-9_]{20,}',
                  r'github_pat_[A-Za-z0-9_]{20,}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                  r'[A-Za-z]:[\\/](?:Users|prive coding folder)[\\/]',
                  r'(?i)\b[A-Z0-9._%+-]+@(?:gmail\.com|outlook\.com|reflowautomations\.nl)\b']
        if any(re.search(pattern,text) for pattern in patterns):errors.append(name+': possible secret or personal data')
        if name=='.env.example':
            values=[line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
            if values!=['OPENAI_API_KEY=']:errors.append(name+': example must contain only an empty key')
        if name=='dictionary.json':
            try:
                if json.loads(text).get('replacements')!={'webhoek':'webhook','superbase':'Supabase'}:
                    errors.append(name+': starter dictionary must remain generic')
            except ValueError:errors.append(name+': invalid JSON')
    return errors

def git(*args):return subprocess.check_output(['git',*args])

def read_git_files(ref=None,staged=False):
    files={}
    records=git('ls-files','--stage','-z') if staged else git('ls-tree','-r','-z','--full-tree',ref or 'HEAD')
    for record in records.split(b'\0'):
        if not record:continue
        meta,name=record.split(b'\t',1);parts=meta.decode().split();name=name.decode('utf-8')
        if parts[0] not in ('100644','100755'):raise ValueError('Unsupported Git entry: '+name)
        if staged:
            sha=parts[1]
            if parts[2]!='0':raise ValueError('Unresolved merge: '+name)
        else:sha=parts[2]
        files[name]=git('cat-file','blob',sha)
    return files

def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group()
    group.add_argument('--git-ref',default=None);group.add_argument('--staged',action='store_true');args=parser.parse_args()
    from export_source import FILES
    contents=read_git_files(args.git_ref,args.staged)
    if not contents:raise SystemExit('No source files to check')
    errors=validate_public_files(contents,FILES)
    if errors:raise SystemExit('\n'.join(errors))
    print('Publication checks passed for '+str(len(contents))+' files. Human suitability review still required.')

if __name__=='__main__':main()
