"""Bounded metadata/index-only audit of actual large partial-discovery routing.

No DNA is read and no mapper runs. This is NOT evidence publication or full
source revalidation. The sampled parent policy is the production coordinator's.
"""
import argparse
import csv
import faulthandler
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--local-paf-cache',action='store_true')
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--package-dir',type=Path,required=True)
    p.add_argument('--lookup-dir',type=Path,required=True);p.add_argument('--index-dir',type=Path,required=True)
    p.add_argument('--residual',type=Path,required=True);a=p.parse_args()
    faulthandler.dump_traceback_later(120,repeat=True);started=time.monotonic()
    sys.path[:0]=[str(a.package_dir),str(a.workspace/'.prepare_lib/tools')]
    from lgz_core.common import stable_id
    from lgz_core.q0_sources import SourceKey,SourceSegment,Interval
    from lgz_core.q0_catalog import CandidateCatalog
    from lgz_core.q0_reference_index import ReferenceIndex
    from lgz_core.q0_query_windows import WindowPolicy,plan_query_windows
    from lgz_core.q0_regional_discovery import plan_parent,REGIONAL_POLICY
    inventory=json.loads((a.lookup_dir/'source-part-lookup.json').read_text())
    if digest(a.lookup_dir/'source-part-lookup.json')!=json.loads((a.lookup_dir/'receipt.json').read_text())['lookup_sha256']:raise ValueError('lookup changed')
    if digest(a.residual)!='03b79fc96cc80ccfa8a6560be2141efd4126afd73d21ad1021c944508a04d171':raise ValueError('completed residual snapshot changed')
    parts={};by_name={}
    for pid,row in inventory.items():
        key=SourceKey(row['dataset'],row['contig']);n=row['length'];sha=row['sequence_sha256']
        if stable_id('q0-source-part',[key.dataset,key.contig,0,n,sha])!=pid:raise ValueError('not a full original source')
        parts[pid]=SourceSegment(pid,key,Interval(0,n),sha,0,'record_start','record_end');by_name[key]=pid
    refs_table=list(csv.DictReader((a.workspace/'metadata/reference.tsv').read_text().splitlines(),delimiter='\t'))
    refs={f[0]:int(f[1]) for f in (line.split('\t') for line in (a.workspace/refs_table[0]['fai_relpath']).read_text().splitlines())}
    holes={by_name[SourceKey(row['dataset'],row['contig'])]:tuple(Interval(*i) for i in row['uncovered']) for row in json.loads(a.residual.read_text()) if row['uncovered']}
    lengths={key:p.interval.length for key,p in parts.items()}
    policy=WindowPolicy(core_bases=100000,context_bases=10000,trigger_query_bases=1,trigger_longest_bases=1)
    all_windows=plan_query_windows(lengths,holes,policy=policy) or ();groups={}
    for w in all_windows:groups.setdefault(w.segment_id,[]).append(w)
    candidates=[]
    for ds in sorted({p.source.dataset for p in parts.values()}):
        ids=sorted((k for k in groups if parts[k].source.dataset==ds),key=lambda k:(-lengths[k],k))
        candidates+=ids[:8]+[ids[min(len(ids)-1,int((len(ids)-1)*i/15))] for i in range(16)]
    selected=[];window_count=0
    for pid in dict.fromkeys(candidates):
        if window_count+len(groups[pid])>256:continue
        selected.append(pid);window_count+=len(groups[pid])
    print(json.dumps(dict(phase='selection',total_residual_parents=len(groups),total_windows=len(all_windows),sample_parents=len(selected),sample_windows=window_count)),flush=True)
    built=json.loads((a.index_dir/'index-built.json').read_text());reports=[]
    with tempfile.TemporaryDirectory(prefix='cgat-q0-scope-',dir='/tmp') as tmp:
        db=Path(tmp)/'reference.sqlite';shutil.copyfile(a.index_dir/'reference.sqlite',db)
        if digest(db)!=built['index_sha256']:raise ValueError('sealed index differs')
        mirrors=Path(tmp)/'pafs';mirrors.mkdir()
        index=ReferenceIndex.open(db,a.workspace,parts,refs,local_paf_directory=mirrors if a.local_paf_cache else None);catalog=CandidateCatalog({'candidates':[]},{},parts)
        try:
            for pid in selected:
                begin=time.monotonic();planned,reason=plan_parent(catalog,index,groups[pid])
                row=dict(segment_id=pid,dataset=parts[pid].source.dataset,contig=parts[pid].source.contig,source_bases=lengths[pid],planned_windows=len(groups[pid]),route='native_fallback' if reason else 'regional',reason=reason,seconds=time.monotonic()-begin,maximum_target_bases=max((sum(t.length for t in ts) for q,ts in planned),default=0))
                reports.append(row);print(json.dumps(row),flush=True)
            index.verify_inputs()
        finally:index.close()
    report=dict(status='regional_scope_sample_complete',policy=REGIONAL_POLICY,total_residual_parents=len(groups),total_windows=len(all_windows),sample_windows=window_count,sampled_parents=reports,seconds=time.monotonic()-started,main_workspace_modified=False,mapper_executed=False,whole_dataset_acceptance=False,index_sha256=built['index_sha256'],code_sha256={p.name:digest(p) for p in (a.package_dir/'lgz_core').glob('*.py')})
    Path('summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('sampled_parents','code_sha256')}),flush=True)
    faulthandler.cancel_dump_traceback_later()


if __name__=='__main__':main()
