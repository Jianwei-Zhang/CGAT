"""Isolated native A/B. Never execute the two retired queries; never write a production receipt."""
from hashlib import sha256
import json
import mmap
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
from time import monotonic

LOOK='2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'
TOOL='cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3'
FORBID={'q0-source-part-865ba1fbce846067c7ffff38'}

def need(ok,msg):
    if not ok: raise ValueError(msg)

def signature(f):
    st=f.stat();return st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns

def digest(f):
    h=sha256()
    with f.open('rb') as src:
        for b in iter(lambda:src.read(4<<20),b''):h.update(b)
    return h.hexdigest()

def libraries(full,small,qfile,parts,keep,queries):
    with full.open('rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm, small.open('xb') as sf, qfile.open('xb') as qf:
        start=0; total=0; smaller=0
        for part in sorted(parts):
            h=mm.find(b'\n',start,start+256);need(h>start and mm[start:h]==b'>'+part.encode(),'full target ID or order mismatch')
            stop=mm.find(b'\n>',h+1);stop=len(mm) if stop<0 else stop+1
            sinks=[v for yes,v in ((part in keep,sf),(part in queries,qf)) if yes];seen=0;seq=sha256()
            for s in sinks:s.write(mm[start:h+1])
            for i in range(h+1,stop,4<<20):
                raw=mm[i:min(stop,i+(4<<20))];dna=raw.replace(b'\n',b'');seq.update(dna);seen+=len(dna)
                for s in sinks:s.write(raw)
            need((seen,seq.hexdigest())==(parts[part]['length'],parts[part]['sequence_sha256']),'unbound DNA');start=stop;total+=seen
            if part in keep:smaller+=seen
        need(start==len(mm) and (total,smaller)==(31706122489,2302475263),'wrong libraries')

def run(base,owner,threads):
    start=monotonic(); panel=json.loads((owner/'panel.json').read_bytes()); lookup=base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json'
    need(digest(lookup)==LOOK==panel['lookup'] and panel['selection']=='5c4b0771b6a8112396adc21c710e748c3aaad44db11c0f5dc77edca8ec9aa31b','foreign panel'); parts=json.loads(lookup.read_bytes());keep=set(panel['retained']);qs=set(panel['queries'])
    retired={p for p,x in parts.items() if (x['dataset'],x['contig']) in {('JM19_hifiasm','ptg000010l'),('JM19_flye_ABD','JM19flyeA_contig_4549')}}
    need(len(retired)==2 and not qs&retired and 1<=len(qs)<=8 and max(parts[q]['length'] for q in qs)<=500000 and len(keep)==3755 and len(parts)==38267,'unsafe control queries')
    full=base/'gpm_server/grt/evidence/q0_prepare/tasks/q0-map-a6056c2d8fcb81f6ca19d1a7/target.fa'; sig=signature(full)
    tool=Path(shutil.which('minimap2')).resolve();need(digest(tool)==TOOL and 1<=threads<=32,'foreign mapper')
    need(not (owner/'mapping.json').exists() and shutil.disk_usage('/tmp').free>5<<30,'complete run or unsafe scratch')
    with tempfile.TemporaryDirectory(dir='/tmp',prefix='wheat-library-panel-') as d:
        small=Path(d)/'candidate.fa';query=Path(d)/'query.fa';libraries(full,small,query,parts,keep,qs);setup=monotonic()-start;print('LIBRARIES_BOUND',round(setup,1),len(qs),flush=True)
        rows={};qsha=digest(query); smallsha=digest(small)
        for label,target in [('reduced',small),('full',full)]:
            dest=owner/(label+'.paf');tmp=owner/(label+'.partial');need(not dest.exists() and not tmp.exists(),'refuse to overwrite mapping')
            argv=[str(tool),'-c','-x','asm10','-D','-P','--dual=yes','--no-long-join','-t',str(threads),str(target),str(query)]; tick=monotonic()
            print('MAPPER_START',label,flush=True)
            def limit():resource.setrlimit(resource.RLIMIT_AS,(112<<30,112<<30))
            with tmp.open('xb') as out,(owner/(label+'.stderr')).open('xb') as err:
                subprocess.run(argv,stdout=out,stderr=err,check=True,preexec_fn=limit)
            need(signature(full)==sig and digest(tool)==TOOL and digest(query)==qsha,'input changed during mapping');tmp.rename(dest)
            rows[label]=dict(seconds=round(monotonic()-tick,3),bytes=dest.stat().st_size,paf_sha256=digest(dest)); print('MAPPER_DONE',label,rows[label],flush=True)
        need(digest(small)==smallsha,'shortlist changed')
    with (owner/'mapping.json').open('x') as f:json.dump(dict(panel=digest(owner/'panel.json'),tool_sha256=TOOL,original_bp=31706122489,shortlist_bp=2302475263,shortlist_fasta=smallsha,query_fasta=qsha,setup_verify_extract_s=round(setup,3),mapper=rows,threads=threads,formal_q0=False),f,sort_keys=True);f.write('\n')

if __name__=='__main__':run(Path(sys.argv[1]),Path.cwd(),int(sys.argv[2]))
