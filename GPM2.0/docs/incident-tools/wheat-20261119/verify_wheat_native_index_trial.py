"""Independent readback: native index statistics/thresholds, flags and byte equality, not a production receipt."""
from hashlib import sha256
import json
from pathlib import Path
import re
import shlex
import sys

from trial_wheat_native_index_parts import CALIBRATION, MAPPING, metadata
from run_wheat_shortlist_panel import TOOL, need, digest


def native_log(path, threads, n):
    text=path.read_text(); commands=re.findall(r'^\[M::main\] CMD: (.+)$',text,re.M)
    need(len(commands)==1 and re.findall(r'^\[M::main\] Version: (.+)$',text,re.M)==['2.31-r1302'],'incomplete or wrong native log')
    command=shlex.split(commands[0]); flags=command[1:-2]
    need(flags==['-c','-x','asm10','-D','-P','--dual=yes','--no-long-join','-t',str(threads)],'different mapping parameters')
    cutoff=re.findall(r'^\[M::mm_mapopt_update::[^\]]+\] mid_occ = (\d+)$',text,re.M)
    index=re.findall(r'^\[M::mm_idx_stat\] (kmer size:.+)$',text,re.M)
    details=re.findall(r'^\[M::mm_idx_stat::[^\]]+\] (distinct minimizers:.+)$',text,re.M)
    need(len(cutoff)==len(index)==len(details)==n,'unbound partition statistics')
    return [dict(mid_occ=int(t),seed_index=s,distribution=d) for t,s,d in zip(cutoff,index,details)]


def verify(folder, olderr, calibration, receipt):
    c=metadata(calibration,CALIBRATION); r=json.loads(receipt.read_bytes()); phases=json.loads((folder/'native-phases.json').read_bytes())
    need(r['calibration']==CALIBRATION and r['mapping']==c['mapping']==MAPPING and r['tool_sha256']==TOOL,'unexpected result lineage')
    need(phases['mapping']==MAPPING and digest(folder/'native-phases.json')==c['phases'] and digest(olderr)==phases['stderr']['full'],'foreign original log')
    old=native_log(olderr,32,4); rows=r['parts']; need(len(rows)==4 and r['threads_per_mapper']==8 and r['total_mapper_threads']==32,'wrong experiment')
    all_hash=sha256();n=0;measures=[]
    for i,(ref,row,st) in enumerate(zip(c['parts'],rows,old),1):
        paf=folder/f'part-{i}.paf'; err=folder/f'part-{i}.stderr'; new,=native_log(err,8,1); part=sha256()
        with paf.open('rb') as f:
            for b in iter(lambda:f.read(1<<20),b''):part.update(b);all_hash.update(b);n+=len(b)
        need(row['part']==i and part.hexdigest()==row['paf_sha256'] and paf.stat().st_size==row['bytes'],'shard receipt differs from native output')
        same=part.hexdigest()==ref['paf_sha256'];need(same==row['matches_original'],'shard comparison does not reproduce')
        measures.append(dict(part=i,paf_identical=same,observed_seed_index_identical=st==new,original_mid_occ=st['mid_occ'],candidate_mid_occ=new['mid_occ'],native_stderr=digest(err)))
    same=all_hash.hexdigest()==c['full']['paf_sha256'];need(all_hash.hexdigest()==r['combined_sha256'] and same==r['whole_paf_identical'] and n==r['combined_bytes'],'combined comparison does not reproduce')
    return dict(receipt=digest(receipt),calibration=CALIBRATION,whole_paf_identical=same,index_observations_identical=all(x['observed_seed_index_identical'] for x in measures),parts=measures,scope='Independent readback of the saved native outputs for these three queries; not an assertion of equivalence for long queries.')


if __name__=='__main__':print(json.dumps(verify(*map(Path,sys.argv[1:])),sort_keys=True,indent=2))
