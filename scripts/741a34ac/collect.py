#!/usr/bin/env python3
"""Independent official lobby/Valve check; retain prior observation on access/schema failure."""
import base64
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/741a34ac'
spec=importlib.util.spec_from_file_location('coverage_audit_741a34ac', Path(__file__).with_name('audit.py'))
audit=importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
spec=importlib.util.spec_from_file_location('coverage_source_parser_741a34ac', ROOT/'scripts/f7279a54/core.py')
parser=importlib.util.module_from_spec(spec); sys.modules[spec.name]=parser; spec.loader.exec_module(parser)


def now(): return audit.iso(datetime.now(timezone.utc))


def get(url):
    request=Request(url,headers={'User-Agent':'MaltaProj2-evidence-audit/1.0','Accept':'application/json, text/html;q=0.9'})
    with urlopen(request,timeout=30) as response:
        body=response.read(8_000_001)
        if len(body)>8_000_000: raise ValueError('Response exceeds audit capture budget')
        return body, dict(url=url,status=response.status,error=None,at_utc=now(),
                          age_header=response.headers.get('Age'),sha256=hashlib.sha256(body).hexdigest())


def main():
    DATA.mkdir(parents=True,exist_ok=True)
    log={}
    try:
        raw,meta=get(audit.LOBBY)
        state=parser.lobby_state(raw.decode('utf-8'))
        fixtures=[]
        raw_cs2=[r for r in state.get('fixtures') or [] if str(r.get('sport_alias','')).casefold()=='cs2']
        for row in raw_cs2:
            fx=parser.fixture_from_hotspawn(row)
            if not fx: raise ValueError('A CS2 listing could not be parsed; refuse partial coverage')
            fixtures.append({**fx,'seen_in':['lobby_page']})
        meta['fixtures_in_transfer_state']=len(raw_cs2)
        snap={'collected_to_utc':now(),'hotspawn':{'fixtures':fixtures,'permalinks':state.get('permalinks',{}),'week':state.get('week')},'access_log':{'hotspawn_lobby_page':meta}}
        audit.rows_from_snapshot(snap)
        (DATA/'lobby_snapshot.json').write_text(json.dumps(snap,indent=2)+'\n')
        log['lobby']={**meta,'result':'successful retained observation'}
    except Exception as e:
        log['lobby']={'url':audit.LOBBY,'attempted_utc':now(),'error':str(e)[:300], 'result':'failed; previous source timestamp NOT reset'}
    try:
        url='https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/2026'
        raw,meta=get(url); entries=json.loads(raw)
        candidates=[r for r in entries if r['name'].startswith('standings_global_') and r['name'].endswith('.md')]
        selected=max(candidates,key=lambda r:r['name'])
        raw,_=get(selected['url']); file=json.loads(raw)
        text=base64.b64decode(file['content']).decode('utf-8')
        sha=hashlib.sha1(f'blob {len(text.encode())}\0'.encode()+text.encode()).hexdigest()
        if sha!=file['sha'] or not audit.rating_index(text): raise ValueError('Official file hash/schema mismatch')
        (DATA/'valve-standings.md').write_text(text)
        (DATA/'valve-file.json').write_text(json.dumps({k:file[k] for k in ('name','path','sha','html_url')},indent=2)+'\n')
        log['valve']={**meta,'file':selected['html_url'],'sha':sha,'result':'official file hash checked'}
    except Exception as e:
        log['valve']={'url':'https://github.com/ValveSoftware/counter-strike_regional_standings/tree/main/live/2026','attempted_utc':now(),'error':str(e)[:300],'result':'failed; pinned prior file retained'}
    (DATA/'collection.json').write_text(json.dumps(log,indent=2)+'\n')
    print(json.dumps(log,indent=2))

if __name__=='__main__': main()
