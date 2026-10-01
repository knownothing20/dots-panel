"""Explicit, one-shot backend egress lookup. Normal snapshots never use network."""
import argparse
import json
import math
import os
from pathlib import Path
import stat
import time
import uuid
from urllib.request import urlopen

URL = 'https://ipwho.is/?fields=success,country,country_code,region,city'
FILE = 'exit-region.json'

def clean(value):
    if not isinstance(value, str) or len(value) > 120 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid region text')
    return value.strip()

def validate(value):
    if not isinstance(value, dict) or value.get('provider') != 'ipwho.is' or value.get('scope') != 'panel_backend_exit':
        raise ValueError('Invalid region observation')
    checked = value.get('checked_at')
    if isinstance(checked, bool) or not isinstance(checked, (int,float)) or not math.isfinite(checked) or checked <= 0 or checked > time.time()+300:
        raise ValueError('Invalid observation time')
    result = {key:clean(value.get(key,'')) for key in ('country','country_code','region','city')}
    if not result['country']: raise ValueError('Missing country')
    return {**result,'provider':'ipwho.is','scope':'panel_backend_exit','checked_at':checked}

def load(directory):
    try:
        parent = os.open(Path(directory)/'config', os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            fd = os.open(FILE, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, 'r') as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode): return None
                return validate(json.loads(handle.read(4097)))
        finally: os.close(parent)
    except (OSError, ValueError, UnicodeError): return None

def lookup(directory, opener=urlopen):
    # Only this explicit command contacts the provider; errors leave last good data intact.
    with opener(URL, timeout=8) as response:
        payload=json.loads(response.read(4097))
    if payload.get('success') is not True: raise ValueError('Region provider did not return success')
    value=validate({**payload,'provider':'ipwho.is','scope':'panel_backend_exit','checked_at':time.time()})
    directory=Path(directory)
    parent=os.open(directory/'config',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    temporary='.exit-region-'+uuid.uuid4().hex
    try:
        if os.fstat(parent).st_mode & 0o077: raise ValueError('Config directory must be private')
        try:
            if not stat.S_ISREG(os.stat(FILE,dir_fd=parent,follow_symlinks=False).st_mode): raise ValueError('Unsafe region cache')
        except FileNotFoundError: pass
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        with os.fdopen(fd,'w') as handle: json.dump(value,handle,ensure_ascii=False)
        os.replace(temporary,FILE,src_dir_fd=parent,dst_dir_fd=parent)
    finally:
        try: os.unlink(temporary,dir_fd=parent)
        except FileNotFoundError: pass
        os.close(parent)
    return value

def label(value, language='zh', now=None):
    try: value=validate(value)
    except ValueError: return '后台出口：未核验' if language != 'en' else 'Backend exit: unverified'
    parts=list(dict.fromkeys(x for x in (value['country'],value['region'],value['city']) if x))
    stale=(time.time() if now is None else now)-value['checked_at'] > 86400
    return ('后台出口（约）：' if language!='en' else 'Backend exit (approx.): ')+', '.join(parts)+((' · 旧观察' if language!='en' else ' · old observation') if stale else '')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Explicit one-time ipwho.is lookup; stores region only, no IP')
    parser.add_argument('--data-dir',required=True)
    args=parser.parse_args()
    try: print(json.dumps(lookup(args.data_dir),ensure_ascii=False))
    except (OSError,ValueError) as error: parser.exit(1,'Region lookup failed; previous cache preserved: '+str(error)+'\n')
