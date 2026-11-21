"""Produce one reusable native q0 task for the 61 weak-reference wheat sources.

This is useful missing work, not a full-data benchmark or a ready main manifest.
It writes only the isolated artifact root; the original workspace is read-only.
Target input bytes are copied from the complete first native supplement, while
all selected query sources are freshly content-verified from the original FAI.
An explicit experimental score option produces a distinct, non-admitted raw key;
it must never be relabelled as the normal native seed or auto-installed.
"""
import argparse
import csv
import fcntl
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sys
import tempfile
import time


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def experiment_policy(policy,minimum):
    if minimum is None:return policy
    expected=['-D','-P','--dual=yes','--no-long-join']
    if type(minimum) is not int or minimum!=2000 or policy.get('supplement_flags')!=expected:
        raise ValueError('unsupported experimental seed profile')
    return {**policy,'supplement_flags':[*expected,'-m',str(minimum)]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package-dir','lookup-dir','index-dir','first-supplement','candidate-scope'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--threads',type=int,default=32)
    p.add_argument('--experimental-minimum-chain-score',type=int,choices=(2000,),default=None)
    a=p.parse_args();started=time.monotonic();work=a.workspace.resolve(strict=True)
    if a.threads!=32:raise ValueError('this productive plan is bound to 32 threads')
    limit=112*1024**3
    if resource.getrlimit(resource.RLIMIT_AS)!=(limit,limit):raise ValueError('fresh-process 112GiB address-space guard is absent')
    if (work/'grt/evidence/q0_prepare/tasks/q0-map-a6056c2d8fcb81f6ca19d1a7/success.json').exists():
        report={'status':'deferred_main_partial_marker_requires_validation','mapper_executed':False,'main_workspace_modified':False}
        Path('summary.json').write_text(json.dumps(report)+'\n');print(json.dumps(report),flush=True);return
    root=Path('artifacts').resolve();root.mkdir(exist_ok=True)
    with (root/'.producer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        sys.path[:0]=[str(a.package_dir.resolve(strict=True)),str(work/'.prepare_lib/tools')]
        from lgz_core import q0_preparation as prep
        # Isolated experiment only: the explicit flags are part of the raw
        # mapping key and actual command. This does not install a main policy,
        # and the unmodified complete-native-scope reader rejects this profile.
        prep.POLICY=experiment_policy(prep.POLICY,a.experimental_minimum_chain_score)
        from lgz_core.common import stable_id,executable_identity
        from lgz_core.q0_catalog import CandidateCatalog
        from lgz_core.q0_sources import SourceKey,SourceSegment,Interval,split_source
        from lgz_core.q0_reference_index import ReferenceIndex
        inputs={str(path):digest(path) for path in (a.package_dir/'lgz_core').glob('*.py')}
        inputs[str(Path(__file__).resolve())]=digest(Path(__file__).resolve())
        runtime=Path(sys.modules['run_orchestration'].__file__).resolve()
        if runtime!=(work/'.prepare_lib/tools/run_orchestration.py').resolve():raise ValueError('unexpected orchestration helper')
        inputs[str(runtime)]=digest(runtime)
        lookup=json.loads((a.lookup_dir/'source-part-lookup.json').read_text())
        proof=json.loads((a.lookup_dir/'receipt.json').read_text())
        if digest(a.lookup_dir/'source-part-lookup.json')!=proof['lookup_sha256']:raise ValueError('source-part lookup changed')
        parts={};by_source={}
        for key,row in lookup.items():
            source=SourceKey(row['dataset'],row['contig']);length=row['length'];sha=row['sequence_sha256']
            if stable_id('q0-source-part',[source.dataset,source.contig,0,length,sha])!=key:raise ValueError('not a canonical full-source part')
            parts[key]=SourceSegment(key,source,Interval(0,length),sha,0,'record_start','record_end');by_source[source]=key
        receipt_identity=prep.identity(work,str(a.first_supplement.relative_to(work)))
        if receipt_identity['sha256']!='994bfaa20bd68d035bedb7d8abacf616d826ebbb0bdc9c2cdc0b1e13b561245e':raise ValueError('complete native first receipt changed')
        receipt=json.loads(a.first_supplement.read_text());tool=executable_identity('minimap2')
        if tool!=receipt['spec']['tool']:raise ValueError('native mapper identity differs')
        targets=receipt['spec']['target_ids'];prior_queries=set(receipt['spec']['query_ids'])
        built=json.loads((a.index_dir/'index-built.json').read_text())
        scope=json.loads(a.candidate_scope.read_text())
        if scope['lookup_sha256']!=proof['lookup_sha256'] or not all(r['all_reference_candidates_count']>r['original_count'] for r in scope['chromosomes']):
            raise ValueError('every original reference candidate group must require expansion')
        for ds,sha in scope['reference_sha256'].items():
            if built['reference_inputs'][f'runs/{ds}_vs_ref/result.paf']['sha256']!=sha:raise ValueError('scope and index reference inputs differ')
        reference=list(csv.DictReader((work/'metadata/reference.tsv').read_text().splitlines(),delimiter='\t'))
        refs={f[0]:int(f[1]) for f in (line.split('\t') for line in (work/reference[0]['fai_relpath']).read_text().splitlines())}
        with tempfile.TemporaryDirectory(prefix='cgat-native-seed-index-',dir='/tmp') as tmp:
            db=Path(tmp)/'reference.sqlite';shutil.copyfile(a.index_dir/'reference.sqlite',db)
            if digest(db)!=built['index_sha256']:raise ValueError('sealed reference index changed')
            index=ReferenceIndex.open(db,work,parts,refs)
            try:routable={by_source[index.sources[row[0]]] for row in index.connection.execute('SELECT DISTINCT source FROM records')}
            finally:index.close()
        queries=sorted(set(parts)-routable-prior_queries)
        if (len(queries)!=61 or sum(parts[k].interval.length for k in queries)!=3953796 or len(targets)!=38117
                or not set(queries)<=set(targets) or max(parts[k].interval.length for k in queries)>1000000):
            raise ValueError('native seed is outside the verified short-query wheat scope')
        datasets=list(csv.DictReader((work/'metadata/datasets.tsv').read_text().splitlines(),delimiter='\t'))
        paths={r['dataset_name']:prep.artifact_path(work,r['fasta_relpath']) for r in datasets}
        indices={r['dataset_name']:{f[0]:tuple(map(int,f[1:5])) for f in (line.split('\t') for line in prep.artifact_path(work,r['fai_relpath']).read_text().splitlines())} for r in datasets}
        sources={}
        for key in queries:
            part=parts[key];length,offset,bases,width=indices[part.source.dataset][part.source.contig]
            if length!=part.interval.length:raise ValueError('original source length changed')
            with paths[part.source.dataset].open('rb') as stream:
                stream.seek(offset);raw=stream.read((length-1)//bases*width+(length-1)%bases+1)
            sequence=raw.replace(b'\n',b'').replace(b'\r',b'').decode('ascii').upper()
            verified=split_source(part.source,sequence)
            if len(verified.segments)!=1 or verified.segments[0].segment_id!=key or verified.segments[0].interval!=part.interval or verified.segments[0].sequence_sha256!=part.sequence_sha256:raise ValueError('query source content or geometry changed')
            parts[key]=verified.segments[0]
            sources[part.source]=sequence
        request={'kind':'candidate_unroutable_seed','query_ids':queries,'target_ids':targets,
                 'reason':'complete_unroutable_relationships_once_before_regional_candidates'}
        native_spec={'schema':'lgz_q0_mapping_v1','query_ids':queries,'target_ids':targets,
                     'members':[[key,parts[key].sequence_sha256] for key in sorted(set(queries+targets))],
                     'tool':tool,'preset':'asm10','alignment_flags':prep.POLICY['supplement_flags']}
        expected_task_id=stable_id('q0-map',native_spec)
        plan={'status':('experimental_profiled_seed_prepared' if a.experimental_minimum_chain_score else 'productive_native_seed_prepared'),'request':request,'expected_task_id':expected_task_id,'query_bases':3953796,'target_parts':len(targets),
              'target_input_reuse_receipt':receipt_identity,'reference_index_sha256':built['index_sha256'],
              'threads':a.threads,'address_space_bytes':limit,'wall_clock_timeout':None,
              'query_sources_freshly_content_verified':True,'target_input_verified_from_complete_receipt':True,
              'main_workspace_modified':False,'experimental_minimum_chain_score':a.experimental_minimum_chain_score,
              'alignment_flags':prep.POLICY['supplement_flags'],'production_profile_admitted':False,'code_sha256':inputs}
        prep.atomic_write_json(Path('producer-plan.json'),plan)
        print(json.dumps({k:v for k,v in plan.items() if k not in ('request','code_sha256')}),flush=True)
        catalog=CandidateCatalog({'candidates':[]},sources,parts)
        template={'root':str(work),'receipt':receipt_identity}
        directory=root/'grt/evidence/q0_prepare/tasks'/expected_task_id;directory.mkdir(parents=True,exist_ok=True)
        prep._copy_prepared_target(root,catalog,targets,directory/'target.fa',template)
        print(json.dumps({'phase':'verified_target_input_ready','task_id':expected_task_id,'seconds':time.monotonic()-started}),flush=True)
        if (work/'grt/evidence/q0_prepare/tasks/q0-map-a6056c2d8fcb81f6ca19d1a7/success.json').exists():
            report={'status':'input_ready_deferred_main_partial_marker_requires_validation','task_id':expected_task_id,'mapper_executed':False,'main_workspace_modified':False}
            prep.atomic_write_json(Path('summary.json'),report);print(json.dumps(report),flush=True);return
        task=prep._supplement(root,catalog,request,tool,'asm10',a.threads,prepared_target=template)
        if task['task_id']!=expected_task_id:raise ValueError('actual native key differs from the frozen producer plan')
        # A no-mapper cache-only pass checks the normal adoption contract.
        if prep._supplement(root,catalog,request,tool,'asm10',a.threads,cache_only=True)!=task:
            raise ValueError('complete native task cannot be reused by the ordinary API')
        for path,sha in inputs.items():
            if digest(Path(path))!=sha:raise ValueError('productive producer code changed')
        report={'status':('complete_experimental_profiled_seed_not_adopted' if a.experimental_minimum_chain_score else 'complete_isolated_native_seed'),'task':task,'artifact_root':str(root),'seconds':time.monotonic()-started,
                'query_sources':len(queries),'query_bases':3953796,'target_parts':len(targets),'tool':tool,'code_sha256':inputs,
                'normal_native_cache_contract_verified':a.experimental_minimum_chain_score is None,
                'same_profile_raw_cache_contract_verified':True,'experimental_minimum_chain_score':a.experimental_minimum_chain_score,
                'alignment_flags':prep.POLICY['supplement_flags'],'production_profile_admitted':False,'main_workspace_modified':False,'ready_main_manifest_published':False,
                'producer_plan_sha256':digest(Path('producer-plan.json'))}
        prep.atomic_write_json(Path('summary.json'),report)
        print(json.dumps({k:v for k,v in report.items() if k!='code_sha256'}),flush=True)


if __name__=='__main__':main()
