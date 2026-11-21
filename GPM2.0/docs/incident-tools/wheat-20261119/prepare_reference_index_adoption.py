"""Prepare the existing sealed reference DB for normal cache reuse, off workspace.

Only emits a ready artifact. Installation requires a later owning handoff; the
normal builder still verifies its exact catalog bindings and original PAF bytes.
"""
import argparse
import csv
import json
from pathlib import Path
import shutil
import sys
from probe_global_seed_controls import sha,signature


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package-dir','lookup-dir','index-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();work=a.workspace.resolve(strict=True)
    sys.path[:0]=[str(a.package_dir),str(work/'.prepare_lib/tools')]
    from lgz_core.common import stable_id
    from lgz_core.q0_sources import SourceKey,SourceSegment,Interval
    from lgz_core.q0_reference_index import ReferenceIndex
    from lgz_core.q0_preparation import atomic_write_json
    lookup_path=a.lookup_dir/'source-part-lookup.json';proof=json.loads((a.lookup_dir/'receipt.json').read_text())
    if sha(lookup_path)!=proof['lookup_sha256']:raise ValueError('source metadata changed')
    parts={}
    for key,row in json.loads(lookup_path.read_text()).items():
        source=SourceKey(row['dataset'],row['contig']);length=row['length'];sequence_sha=row['sequence_sha256']
        if stable_id('q0-source-part',[source.dataset,source.contig,0,length,sequence_sha])!=key:
            raise ValueError('only canonical full-source lookup is supported')
        parts[key]=SourceSegment(key,source,Interval(0,length),sequence_sha,0,'record_start','record_end')
    reference=list(csv.DictReader((work/'metadata/reference.tsv').read_text().splitlines(),delimiter='\t'))
    refs={f[0]:int(f[1]) for f in (line.split('\t') for line in (work/reference[0]['fai_relpath']).read_text().splitlines())}
    source=a.index_dir/'reference.sqlite';before=signature(source);built=json.loads((a.index_dir/'index-built.json').read_text())
    expected='18677df675e1a3c5fe9071d3edcd908215c8a20d2fbba4d5effd39411c0909a3'
    if built['index_sha256']!=expected:raise ValueError('not the previously verified sealed DB')
    inputs=sorted([{'path':path,**row} for path,row in built['reference_inputs'].items()],key=lambda row:row['path'])
    key=stable_id('reference-index',{'binding':ReferenceIndex.bindings(parts,refs),'inputs':inputs})
    relative='grt/evidence/q0_prepare/indexes/'+key
    ready=Path('artifacts').resolve()/relative
    if ready.is_relative_to(work):raise ValueError('index preparation must not write the live workspace')
    ready.mkdir(parents=True,exist_ok=False);db=ready/'reference.sqlite'
    shutil.copyfile(source,db)
    if sha(db)!=expected or signature(source)!=before:raise ValueError('sealed DB changed during copy')
    index=ReferenceIndex.open(db,work,parts,refs)
    try:
        index.verify_inputs()
        if index.build_report()['reference_inputs']!=built['reference_inputs']:
            raise ValueError('sealed DB and original input report differ')
    finally:index.close()
    atomic_write_json(ready/'success.json',{'status':'success','key':key,'inputs':inputs,'sha256':expected,'size':db.stat().st_size})
    report={'status':'complete_reference_cache_ready_for_owned_adoption','relative':relative,'source':str(ready),
            'source_index':str(source),'files':[{'name':p.name,'sha256':sha(p),'size':p.stat().st_size} for p in (db,ready/'success.json')],
            'workspace_modified':False,'reference_mapping_rerun':False,'index_rebuilt':False}
    atomic_write_json(Path('ready.json'),report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
