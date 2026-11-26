"""One isolated 3-query control; compare four real native searches with a completed 31.71 Gb PAF."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from hashlib import sha256
import json
import mmap
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

from calibrate_wheat_index_parts import MAPPING, metadata, target_groups
from run_wheat_shortlist_panel import INDIRECT, LOOK, TOOL, digest, need, signature

CALIBRATION = 'e6e03e3850fd47d10bc6cd263a2ceb1be70a04fe3c99d721f7b7ec293f1ffbd8'


def stage(full, shards, queryfile, groups, queries, lookup):
    """Copy original FASTA bytes once; verify ordered headers and sequence content, including excluded query IDs."""
    with ExitStack() as stack:
        src = stack.enter_context(full.open('rb')); mm = stack.enter_context(mmap.mmap(src.fileno(),0,access=mmap.ACCESS_READ))
        outputs=[stack.enter_context(p.open('xb')) for p in shards]; query=stack.enter_context(queryfile.open('xb')); pos=0
        for chunk,out in zip(groups,outputs):
            for key in chunk:
                h=mm.find(b'\n',pos,pos+256)
                need(h>pos and mm[pos:h]==b'>'+key.encode(),'target name or order changed')
                end=mm.find(b'\n>',h+1); end=len(mm) if end<0 else end+1
                header=mm[pos:h+1]; out.write(header)
                if key in queries:query.write(header)
                length=0; signature_hash=sha256()
                for i in range(h+1,end,4<<20):
                    raw=mm[i:min(end,i+(4<<20))]; dna=raw.replace(b'\n',b''); signature_hash.update(dna); length+=len(dna); out.write(raw)
                    if key in queries:query.write(raw)
                need((length,signature_hash.hexdigest())==(lookup[key]['length'],lookup[key]['sequence_sha256']), 'target DNA content differs')
                pos=end
        need(pos==len(mm),'unexpected trailing target sequences')


def native_part(tool, target, query, owner, i, expected, qcount):
    name='part-'+str(i+1); tick=monotonic(); print('NATIVE_PART_START',name,flush=True)
    paf=owner/(name+'.paf'); err=owner/(name+'.stderr')
    with paf.open('xb') as out, err.open('xb') as log:
        argv=[str(tool),'-c','-x','asm10','-D','-P','--dual=yes','--no-long-join','-t','8',str(target),str(query)]
        subprocess.run(argv,stdout=out,stderr=log,check=True)
    elapsed=monotonic()-tick; log=err.read_text()
    need(re.findall(r'loaded/built the index for (\d+) target',log)==[str(expected['targets'])] and re.findall(r'; total length: (\d+)',log)==[str(expected['bases'])] and re.findall(r'\] mapped (\d+) sequences',log)==[str(qcount)],'not the original index partition or query cohort')
    native,peak=re.findall(r'Real time: ([\d.]+) sec; CPU: [\d.]+ sec; Peak RSS: ([\d.]+) GB',log)[0]
    d=digest(paf); size=paf.stat().st_size; equal=(d,size)==(expected['paf_sha256'],expected['bytes'])
    print('NATIVE_PART_DONE',name,round(elapsed,2),'equal',equal,flush=True)
    return dict(part=i+1,native_s=float(native),peak_rss_gb=float(peak),subprocess_s=round(elapsed,3),records_checked_by_digest=expected['records'] if equal else None,bytes=size,paf_sha256=d,matches_original=equal)


def run(owner,base):
    start=monotonic(); c=metadata(owner/'calibration.json',CALIBRATION); panel=metadata(owner/'panel.json',INDIRECT)
    source=base/'q0-indirect-panel-20261126.GWoN0Il5'; m=metadata(source/'mapping.json',MAPPING)
    lookup=metadata(base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json',LOOK)
    full=base/'gpm_server/grt/evidence/q0_prepare/tasks/q0-map-a6056c2d8fcb81f6ca19d1a7/target.fa'; sig=signature(full)
    tool=Path(shutil.which('minimap2')).resolve(); qs=set(panel['queries']); groups=target_groups(lookup,c['parts'])
    need(len(qs)==3 and sorted(lookup[q]['length'] for q in qs)==[18531,27076,38629] and len(groups)==4,'controls only; never use the retired queries')
    need(digest(tool)==TOOL==m['tool_sha256'] and c['mapping']==MAPPING and c['full']==m['mapper']['full'] and c['query_fasta']==m['query_fasta'],'unbound calibration')
    need(not list(owner.glob('part-*.paf')) and not (owner/'comparison.json').exists(),'refuse to overwrite results')
    need(shutil.disk_usage('/tmp').free>full.stat().st_size+(8<<30),'insufficient node scratch before staging')
    with TemporaryDirectory(dir='/tmp',prefix='wheat-four-native-indices-') as folder:
        root=Path(folder); targets=[root/('part-'+str(i+1)+'.fa') for i in range(4)]; query=root/'query.fa'
        stage(full,targets,query,groups,qs,lookup);need(signature(full)==sig and digest(query)==m['query_fasta'],'FASTA changed')
        setup=monotonic()-start;print('FOUR_ORIGINAL_TARGET_PARTS_STAGED',round(setup,2),flush=True); tick=monotonic()
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows=list(pool.map(lambda i:native_part(tool,targets[i],query,owner,i,c['parts'][i],len(qs)),range(4)))
        pool_s=monotonic()-tick; need(digest(tool)==TOOL and signature(full)==sig and digest(query)==m['query_fasta'],'input changed during search')
    combined=sha256(); n=0
    for row in rows:
        with (owner/('part-'+str(row['part'])+'.paf')).open('rb') as f:
            for block in iter(lambda:f.read(4<<20),b''):combined.update(block);n+=len(block)
    same=combined.hexdigest()==c['full']['paf_sha256'] and n==c['full']['bytes'];need(same==all(row['matches_original'] for row in rows),'inconsistent equality claims')
    out=dict(calibration=CALIBRATION,mapping=MAPPING,panel=INDIRECT,tool_sha256=TOOL,combined_sha256=combined.hexdigest(),combined_bytes=n,whole_paf_identical=same,parts=rows,threads_per_mapper=8,total_mapper_threads=32,stage_and_verify_s=round(setup,3),parallel_mapper_and_part_hash_s=round(pool_s,3),total_wall_s=round(monotonic()-start,3),original_staging_s=m['setup_verify_extract_s'],original_full_mapper_s=m['mapper']['full']['seconds'],original_full_sha256=c['full']['paf_sha256'],scope='Paired three short control queries, same native target partitions and parameters apart from threads. Staging differs and cache warmth is not controlled. Not the two long parents or a production receipt.')
    with (owner/'comparison.json').open('x') as f:json.dump(out,f,indent=2,sort_keys=True);f.write('\n')
    print('NATIVE_PART_TRIAL_DONE',same,'seconds',out['total_wall_s'],flush=True)


if __name__=='__main__':run(Path.cwd(),Path(sys.argv[1]))
