"""Check original native seed reuse across the wheat fork without starting a mapper.

Separate metadata transfer bounds (four matrices) from a cold physical copy and
production cache-only/PAF check (one small native matrix). No published Q0.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

from bound_regional_scope_from_native_receipts import EXPECTED
from census_wheat_q0_fork import SNAP, bind, bounded, require, write
from fork_wheat_q0 import copy_bound, member
from lgz_core import q0_preparation as prep
from lgz_core.common import stable_id
from lgz_core.q0_sources import Interval

SMALL = 'q0-map-b30137a13323db8a99874448'


def transfer_budget(rows):
    """Read each distinct sealed payload from shared storage once, never link to live files."""
    blobs = {}; logical = 0
    for item in rows:
        n = item['size']; sha = item['sha256']
        require(type(n) is int and n>=0 and len(sha)==64 and blobs.setdefault(sha,n)==n,'inconsistent content identity')
        logical += n
    unique=sum(blobs.values()); return {'logical_output_bytes':logical,'unique_payload_bytes':unique,'repeated_bytes':logical-unique}


def main(snapshot,lookup,dest):
    frozen,root,parts,ordered,_=bind(snapshot,lookup); require(not dest.exists() and not dest.is_relative_to(root),'unsafe report path')
    tool=prep.executable_identity('minimap2'); all_rows=[]; receipts={}; base='grt/evidence/q0_prepare/tasks/'; names=set(prep.MAPPING_OUTPUT_FILES)
    for key,pin in sorted(EXPECTED.items()):
        directory=base+key+'/'; rel=directory+'success.json'; raw=bounded(member(root,rel),24<<20,pin); doc=json.loads(raw); spec=doc['spec']; rows=doc['outputs']
        require(doc['status']=='success' and spec['schema']=='lgz_q0_mapping_v1' and stable_id('q0-map',spec)==key and spec['tool']==tool and spec['preset']=='asm10','wrong producer task/tool')
        require(len(rows)==len(names) and {r['path'] for r in rows}=={directory+k for k in names},'native output closure is incomplete')
        keys=set(spec['query_ids']+spec['target_ids']); require(spec['members']==[[k,parts[k][2]] for k in sorted(keys)],'part binding differs from fork source inventory')
        all_rows.extend(rows); receipts[key]=(spec,rows,rel,raw)
    spec,rows,rel,receipt=receipts[SMALL]; require(spec['alignment_flags']==prep.POLICY['supplement_flags'],'do not relabel a weak matrix as native')
    plan=transfer_budget(all_rows); stats={'rows':0}; relevant={k for k,_ in spec['members']}; catalog=SimpleNamespace(parts={k:SimpleNamespace(sequence_sha256=parts[k][2],interval=Interval(0,parts[k][1]),source=ordered[parts[k][0]]) for k in relevant})
    def consume(task, hits):
        require(task['task_id']==SMALL,'wrong cache output'); stats['rows']=sum(1 for _ in hits)
    with tempfile.TemporaryDirectory(prefix='q0-fork-native-check-',dir='/tmp') as tmp:
        child=Path(tmp).resolve(); require(not child.is_relative_to(root),'not isolated')
        for row in rows:
            src=member(root,row['path']); dst=member(child,row['path']); copy_bound(src,dst,row)
            require(not src.samefile(dst),'child shares live inode')
        member(child,rel).write_bytes(receipt)
        request={'kind':'fork_cache_probe_only','query_ids':spec['query_ids'],'target_ids':spec['target_ids']}
        task=prep._supplement(child,catalog,request,tool,spec['preset'],1,cache_only=True,on_cache_hit=consume)
        require(task is not None and stats['rows']>0 and bounded(member(root,rel),24<<20,EXPECTED[SMALL])==receipt,'latest cache consumer did not accept the complete private copy')
    result={'schema':'whole_wheat_native_seed_transfer_probe_v1','snapshot':SNAP,'revision':frozen['revision'],'historical_receipts':EXPECTED,'four_matrix_output_transfer_bound':plan,'native_probe':{'id':SMALL,'receipt_sha256':hashlib.sha256(receipt).hexdigest(),'verified_outputs':len(rows),'copied_bytes':sum(r['size'] for r in rows),'paf_rows_consumed':stats['rows'],'query_parts':len(spec['query_ids']),'target_parts':len(spec['target_ids']),'mapper_calls':0},'production_modified':False,'limits':'Transfer numbers apply if all four outputs are requested; they are not real shared I/O or space savings of this probe. Only the named matrix was copied/validated. The -m 2000 matrix still needs its original weak-scoped admission. No chromosome checkpoint import, complete Q0, or scientific equivalence claimed.'}; write(dest,result); print(json.dumps(result),flush=True)


if __name__=='__main__': main(*(Path(v).absolute() for v in sys.argv[1:]))
