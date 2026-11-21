"""Metadata-only upper-bound candidate-window probe; never execute a mapper.

All source parts are allowed candidate targets and initial observed pairs are
intentionally empty. This overestimates required work, not a production plan.
Only the complete native first-supplement receipt is reused as a recorded prior
proof; its large FASTAs/PAF are not rehashed by this diagnostic.
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


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package-dir','lookup-dir','index-dir','first-supplement'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();started=time.monotonic();faulthandler.dump_traceback_later(120,repeat=True)
    sys.path[:0]=[str(a.package_dir),str(a.workspace/'.prepare_lib/tools')]
    from lgz_core.common import stable_id,executable_identity
    from lgz_core.q0_sources import SourceKey,SourceSegment,Interval
    from lgz_core.q0_catalog import CandidateCatalog,_IntervalUnion
    from lgz_core.q0_reference_index import ReferenceIndex
    from lgz_core.q0_regional_candidates import CandidatePlan,candidate_window_targets
    # Load the whole module closure before any genomic I/O.
    from lgz_core import q0_preparation
    lookup=json.loads((a.lookup_dir/'source-part-lookup.json').read_text())
    if sha(a.lookup_dir/'source-part-lookup.json')!=json.loads((a.lookup_dir/'receipt.json').read_text())['lookup_sha256']:raise ValueError('lookup changed')
    parts={};source_ids={}
    for key,row in lookup.items():
        source=SourceKey(row['dataset'],row['contig']);length=row['length'];digest=row['sequence_sha256']
        if stable_id('q0-source-part',[source.dataset,source.contig,0,length,digest])!=key:raise ValueError('not a whole-source part')
        parts[key]=SourceSegment(key,source,Interval(0,length),digest,0,'record_start','record_end');source_ids[source]=key
    reference=list(csv.DictReader((a.workspace/'metadata/reference.tsv').read_text().splitlines(),delimiter='\t'))
    refs={f[0]:int(f[1]) for f in (line.split('\t') for line in (a.workspace/reference[0]['fai_relpath']).read_text().splitlines())}
    receipt=json.loads(a.first_supplement.read_text())
    if sha(a.first_supplement)!='994bfaa20bd68d035bedb7d8abacf616d826ebbb0bdc9c2cdc0b1e13b561245e':raise ValueError('first native receipt differs')
    tool=executable_identity('minimap2')
    if tool!=receipt['spec']['tool']:raise ValueError('original mapper identity differs')
    task={'task_id':a.first_supplement.parent.name,'kind':'unplaced_discovery','query_ids':receipt['spec']['query_ids'],'target_ids':receipt['spec']['target_ids'],
          'paf':str((a.first_supplement.parent/'result.paf').relative_to(a.workspace)),'receipt':str(a.first_supplement.relative_to(a.workspace))}
    built=json.loads((a.index_dir/'index-built.json').read_text())
    reports=[]
    with tempfile.TemporaryDirectory(prefix='cgat-candidate-scope-',dir='/tmp') as tmp:
        scratch=Path(tmp);db=scratch/'reference.sqlite';shutil.copyfile(a.index_dir/'reference.sqlite',db)
        if sha(db)!=built['index_sha256']:raise ValueError('sealed reference index changed')
        mirrors=scratch/'pafs';mirrors.mkdir()
        index=ReferenceIndex.open(db,a.workspace,parts,refs,local_paf_directory=mirrors)
        try:
            routed_sources={row[0] for row in index.connection.execute('SELECT DISTINCT source FROM records')}
            routable=frozenset(source_ids[index.sources[i]] for i in routed_sources)
            unroutable=set(parts)-routable
            unplaced=set(task['query_ids'])
            inventory=dict(total_parts=len(parts),total_source_bases=sum(part.interval.length for part in parts.values()),routable_parts=len(routable),
                           unroutable_parts=len(unroutable),unroutable_bases=sum(parts[k].interval.length for k in unroutable),
                           unroutable_outside_completed_unplaced=len(unroutable-unplaced),
                           largest_unroutable=[dict(segment_id=k,dataset=parts[k].source.dataset,contig=parts[k].source.contig,bases=parts[k].interval.length) for k in sorted(unroutable,key=lambda k:-parts[k].interval.length)[:10]])
            print(json.dumps(dict(phase='routing_inventory',**inventory)),flush=True)
            selected=[]
            for ds in sorted({part.source.dataset for part in parts.values()}):
                keys=sorted((k for k in routable if parts[k].source.dataset==ds),key=lambda k:(-parts[k].interval.length,k))
                selected+=keys[:4]+[keys[int((len(keys)-1)*i/4)] for i in range(5)]
            selected=list(dict.fromkeys(selected));footprints={}
            for key in selected:
                part=parts[key]
                for hit in index._source_hits(part.source,part.interval):
                    for block in hit.aligned_blocks():
                        if block.operation!='X':footprints.setdefault((key,hit.target_name),_IntervalUnion()).append(block.query)
            footprints={key:tuple(value) for key,value in footprints.items()}
            requests=[dict(kind='candidate_chr',chromosome=chr,query_ids=sorted(k for k in selected if (k,chr) in footprints),target_ids=sorted(parts)) for chr in refs]
            requests=[r for r in requests if r['query_ids']]
            catalog=CandidateCatalog({'candidates':[]},{},parts,reference_routable_parts=routable,reference_routable_footprints=footprints)
            planner=CandidatePlan(a.workspace,catalog,index,requests,set(),[task],tool,'asm10')
            for key in selected:
                requested,eligible=planner.eligible(key);windows=planner.windows(key);selection=index.target_selection(eligible & planner.routable)
                subset=sorted({0,len(windows)//2,len(windows)-1}) if windows else [];samples=[]
                for i in subset:
                    begin=time.monotonic();targets,reason=candidate_window_targets(index,key,windows[i],planner.query_chromosomes[key],selection)
                    samples.append(dict(window_number=i,query=windows[i].record(),target_bases=sum(t.length for t in targets),target_windows=len(targets),reason=reason,seconds=time.monotonic()-begin,
                                        target_scope_identity=stable_id('candidate-window-targets',[t.record() for t in targets])))
                row=dict(segment_id=key,dataset=parts[key].source.dataset,contig=parts[key].source.contig,bases=parts[key].interval.length,
                         qualified_source_core_bases=sum(interval.length for interval in planner.cores.get(key,())),full_candidate_windows=len(windows),
                         requested_target_parts=requested.bit_count(),eligible_target_parts=eligible.bit_count(),unroutable_target_parts=(eligible & ~planner.routable).bit_count(),samples=samples)
                reports.append(row);print(json.dumps(row),flush=True)
            index.verify_inputs()
        finally:index.close()
    report=dict(status='candidate_regional_upper_bound_scope_complete',inventory=inventory,parents=reports,seconds=time.monotonic()-started,
                original_source_DNA_revalidated=False,first_native_content_revalidated=False,prior_native_receipt_sha256=sha(a.first_supplement),initial_observed_pairs_omitted=True,
                all_parts_allowed_as_targets=True,mapper_executed=False,production_modified=False,code_sha256={p.name:sha(p) for p in (a.package_dir/'lgz_core').glob('*.py')})
    Path('summary.json').write_text(json.dumps(report,indent=2)+'\n');faulthandler.cancel_dump_traceback_later()
    print(json.dumps({k:v for k,v in report.items() if k not in ('parents','code_sha256')}),flush=True)


if __name__=='__main__':main()
