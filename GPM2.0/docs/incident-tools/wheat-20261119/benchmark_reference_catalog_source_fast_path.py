"""Replay real bounded reference PAF slices in baseline/candidate catalog code.

The control uses original complete source records addressed through their FAI,
not invented raw alignment geometry. Build a sealed index for the isolated
sample, then re-open it in both versions. Never consumes/publishes main state.
"""
import argparse
import csv
import gc
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time

from benchmark_regional_mapper_dispatch import digest, window_bytes, within

MIB = 1024**2
SLICE_BYTES = 2*MIB
SLICES = 8
DNA_PER_DATASET = 128*MIB
MAX_SOURCE = 100_000_000


def metadata(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f,delimiter='\t'))


def load_fai(path):
    entries={}
    with path.open(encoding='utf-8') as f:
        for line in f:
            name,*raw=line.rstrip('\r\n').split('\t')
            values=tuple(map(int,raw))
            if name in entries or len(values)!=4: raise ValueError('invalid FAI row')
            length,offset,columns,width=values
            if not name or length<1 or offset<0 or not 0<columns<=width: raise ValueError('invalid FAI geometry')
            entries[name]=values
    return entries


def signature(path):
    s=path.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def bounded_rows(path):
    size=path.stat().st_size
    ranges=[(left,min(size,left+SLICE_BYTES)) for left in range(0,size,SLICE_BYTES)] if size<=SLICES*SLICE_BYTES else [
        (left,left+SLICE_BYTES) for left in [(size-SLICE_BYTES)*i//(SLICES-1) for i in range(SLICES)]]
    with path.open('rb') as f:
        for low,high in ranges:
            if low:
                f.seek(low-1);skip=f.read(1)!=b'\n'
            else: skip=False
            raw=f.read(high-low)
            if skip: raw=raw[raw.find(b'\n')+1:] if b'\n' in raw else b''
            if high!=size and not raw.endswith(b'\n'): raw=raw[:raw.rfind(b'\n')+1]
            yield from (row for row in raw.splitlines(keepends=True) if row.strip() and not row.startswith(b'#'))


def make_sample(work, sample, source_key):
    datasets=metadata(work/'metadata/datasets.tsv'); references=metadata(work/'metadata/reference.tsv')
    if len(references)!=1 or not 1<=len(datasets)<=4: raise ValueError('unexpected source table')
    ref_fai=within(work,references[0]['fai_relpath']);refs={k:v[0] for k,v in load_fai(ref_fai).items()}
    assignments=metadata(work/'metadata/chr_assignments.tsv');sources={};samples=[]
    for row in sorted(datasets,key=lambda r:r['dataset_name']):
        ds=row['dataset_name'];fa=within(work,row['fasta_relpath']);fai=within(work,row['fai_relpath'])
        relative=f'runs/{ds}_vs_ref/result.paf';paf=within(work,relative);bound={p:signature(p) for p in (fa,fai,paf)}
        lengths=load_fai(fai);out=sample/relative;out.parent.mkdir(parents=True,exist_ok=False)
        selected={};bases=seen=accepted=0
        with out.open('xb') as dest:
            for hit in bounded_rows(paf):
                seen+=1;q,qlen,*_=hit.split(b'\t',2);q=q.decode('utf-8');qlen=int(qlen)
                if qlen!=lengths[q][0]: raise ValueError('PAF/FAI source length differs')
                if q not in selected:
                    if qlen>MAX_SOURCE or qlen>DNA_PER_DATASET-bases:continue
                    selected[q]=lengths[q];bases+=qlen
                dest.write(hit if hit.endswith(b'\n') else hit+b'\n');accepted+=1
        if not accepted:raise ValueError(f'no representative bounded reference hits for {ds}')
        for q,idx in selected.items(): sources[source_key(ds,q)]=window_bytes(fa,idx,0,idx[0])
        if any(signature(p)!=stamp for p,stamp in bound.items()):raise ValueError('main input changed during sampling')
        samples.append({'dataset':ds,'original_size':bound[paf][2],'paf_records_inspected':seen,'records':accepted,
                        'source_bases':bases,'sources':len(selected),'paf_bytes':out.stat().st_size,'paf_sha256':digest(out)})
    return sources,refs,assignments,samples


def load_baseline(path):
    name='lgz_core.q0_catalog_frozen_baseline'
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package-dir','baseline','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();work=a.workspace.resolve(strict=True);out=a.output.resolve();package=a.package_dir.resolve(strict=True)
    if any(x.is_relative_to(work) or work.is_relative_to(x) for x in (out,package)):
        raise ValueError('must isolate probe package and outputs from main')
    sys.path.insert(0,str(package));out.mkdir(exist_ok=False);sample=out/'sample';sample.mkdir()
    from lgz_core import q0_catalog as candidate
    from lgz_core.common import canonical_json,sha256_bytes
    from lgz_core.q0_reference_index import ReferenceIndex
    from lgz_core.q0_sources import SourceKey
    a_old=load_baseline(a.baseline.resolve(strict=True))
    sources,refs,assignments,samples=make_sample(work,sample,SourceKey)
    print(json.dumps({'phase':'sample','datasets':samples}),flush=True)
    db=out/'reference.sqlite'
    def build(mod, factory):
        t=time.monotonic();result=mod.build_catalog(sample,sources,refs,assignments,regional_factory=factory)
        duration=time.monotonic()-t
        # Compare payload, every proof reference, and exact routing footprints;
        # this is not a count-only acceptance gate.
        content={'payload':result.payload,'routable_parts':sorted(result.reference_routable_parts),
            'footprints':[[*key,[[x.start,x.end] for x in values]] for key,values in sorted(result.reference_routable_footprints.items())],
            'routing_report':result.regional_index_report}
        return duration,sha256_bytes(canonical_json(content).encode('utf-8')),len(result.payload['evidence'])
    index_seconds,expected,indexed_evidence=build(a_old,lambda parts,rr:ReferenceIndex.create(db,sample,parts,rr))
    print(json.dumps({'phase':'sealed_sample_index','seconds':index_seconds,'evidence':indexed_evidence}),flush=True)
    phases=[]
    for mode in ('baseline','candidate','candidate','baseline'):
        gc.collect();mod=a_old if mode=='baseline' else candidate
        seconds,identity,records=build(mod,lambda parts,rr:ReferenceIndex.open(db,sample,parts,rr))
        if identity!=expected or records!=indexed_evidence:raise ValueError('catalog or routing evidence differs from baseline')
        result={'mode':mode,'seconds':seconds,'combined_content_sha256':identity,'evidence':records}
        phases.append(result);print(json.dumps(result),flush=True)
    ratio=sum(x['seconds'] for x in phases if x['mode']=='baseline')/sum(x['seconds'] for x in phases if x['mode']=='candidate')
    report={'status':'exact_bounded_reference_catalog_replay_NOT_production_acceptance','hostname':socket.gethostname(),
        'samples':samples,'phases':phases,'seconds_for_initial_index_excluded_from_ratio':index_seconds,
        'baseline_over_candidate_wall':ratio,'catalog_routing_content_equal':True,'main_workspace_modified':False,
        'mapper_executed':False,'whole_dataset_replayed':False,'old_module_sha256':digest(a.baseline),'new_module_sha256':digest(Path(candidate.__file__))}
    (out/'summary.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')


if __name__=='__main__':main()
