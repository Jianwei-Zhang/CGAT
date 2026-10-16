#!/usr/bin/env python3
"""Check NEW production refill batches against retained real PAFs; no old run."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--old',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--threads',type=int,default=8)
a=p.parse_args()
sys.path.insert(0,str(a.source/'tools'))
from grt_core.common import read_fasta, read_tsv, executable_identity
from grt_core.refill_batch import RefillBatchAlignment
from grt_core.stage_cache import fasta_bytes

server=a.output;server.mkdir(parents=True,exist_ok=False)
(server/'grt/donors').mkdir(parents=True)
donor=next(r for r in read_tsv(a.old/'metadata/grt_donor_sets.tsv') if r['donor_kind']=='ordinary')
os.link(a.old/donor['fasta_relpath'],server/donor['fasta_relpath'])
lengths={};name=None
with (server/donor['fasta_relpath']).open('rb') as handle:
 for line in handle:
  if line.startswith(b'>'):
   name=line[1:].split()[0].decode();lengths[name]=0
  else:lengths[name]+=len(line.strip())
report={'status':'RUNNING','checks':[],'rounds':[],
        'boundary':'New production batching only; retained real customer refill PAFs are the reference. No old minimap2 baseline invocation.'}
def save():(server/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
save()
minimap=executable_identity('minimap2')
for round_name in ('round1','round2'):
 root=a.old/'grt/evidence/step3/refill'/round_name/'by_chr'
 records=[];query_map={};groups={}
 for path in sorted(root.glob('*/flanks.fa')):
  key=path.parent.name;groups[key]=list(read_fasta(path))
  records.extend(groups[key])
  for name,_seq in groups[key]:query_map[name]=({'chr':key,'object_id':name},name.rsplit('__',1)[-1])
 batch=RefillBatchAlignment(server,'step3_refill_'+round_name,donor,minimap,a.threads,
                            records,query_map,lengths,server/'artifacts'/round_name/'batch')
 started=time.monotonic()
 for key,queries in groups.items():
  out=server/'artifacts'/round_name/key;out.mkdir(parents=True)
  (out/'flanks.fa').write_bytes(fasta_bytes(queries))
  batch(out/'flanks.fa',out/'result.paf',out)
  same=(out/'result.paf').read_bytes()==(root/key/'result.paf').read_bytes()
  report['checks'].append({'round':round_name,'chromosome':key,'status':'PASS' if same else 'FAIL'})
 report['rounds'].append({'round':round_name,'seconds':time.monotonic()-started,'provenance':batch.provenance})
 save()
report['checks'].append({'label':'same target index actually reused in round2','status':'PASS' if report['rounds'][1]['provenance']['index_cache_hit'] else 'FAIL'})
report['status']='PASS' if all(c['status']=='PASS' for c in report['checks']) else 'FAIL';save()
print('PRODUCTION_REFILL',report['status'],len(report['checks']),flush=True)
if report['status']!='PASS':raise SystemExit('New production refill differs from retained PAF')
