"""Validate an isolated completed seed with the real new cache API, read-only.

This does not move anything or accept temporary PAFs. Actual flags determine the
raw key; weak-global matrix coverage excludes short queries AND short targets.
"""
import argparse
import csv
import fcntl
import json
from pathlib import Path
import shutil
import sys
import tempfile
from probe_global_seed_controls import sha,signature


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package-dir','producer-dir','lookup-dir','index-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();work=a.workspace.resolve(strict=True);producer=a.producer_dir.resolve(strict=True)
    summary_path=producer/'summary.json';summary_sha=sha(summary_path);summary=json.loads(summary_path.read_text())
    if (summary.get('status') not in {'complete_isolated_native_seed','complete_experimental_profiled_seed_not_adopted'}
            or summary.get('main_workspace_modified') is not False
            or not (summary.get('same_profile_raw_cache_contract_verified') is True
                    or summary.get('normal_native_cache_contract_verified') is True)):
        raise ValueError('producer has not completed a verified raw cache')
    root=Path(summary['artifact_root']).resolve(strict=True)
    if root!=producer/'artifacts' or root.is_relative_to(work):raise ValueError('producer cache is not isolated')
    with (root/'.producer.lock').open('r') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        sys.path[:0]=[str(a.package_dir),str(work/'.prepare_lib/tools')]
        from lgz_core import q0_preparation as prep
        from lgz_core.common import stable_id,executable_identity
        from lgz_core.q0_sources import SourceKey,SourceSegment,Interval
        from lgz_core.q0_catalog import CandidateCatalog
        from lgz_core.q0_reference_index import ReferenceIndex
        from lgz_core.q0_regional_mapping import BASE_FLAGS
        from lgz_core.q0_cigar_policy import weak_global_seed_scope
        lookup_path=a.lookup_dir/'source-part-lookup.json'
        if sha(lookup_path)!=json.loads((a.lookup_dir/'receipt.json').read_text())['lookup_sha256']:raise ValueError('source lookup changed')
        parts={};by_source={}
        for key,row in json.loads(lookup_path.read_text()).items():
            source=SourceKey(row['dataset'],row['contig']);length=row['length'];digest=row['sequence_sha256']
            if stable_id('q0-source-part',[source.dataset,source.contig,0,length,digest])!=key:raise ValueError('source lookup is not canonical')
            parts[key]=SourceSegment(key,source,Interval(0,length),digest,0,'record_start','record_end');by_source[source]=key
        reference=list(csv.DictReader((work/'metadata/reference.tsv').read_text().splitlines(),delimiter='\t'))
        refs={f[0]:int(f[1]) for f in (line.split('\t') for line in (work/reference[0]['fai_relpath']).read_text().splitlines())}
        catalog=CandidateCatalog({'candidates':[]},{},parts)
        with tempfile.TemporaryDirectory(prefix='cgat-adopt-index-',dir='/tmp') as tmp:
            db=Path(tmp)/'reference.sqlite';shutil.copyfile(a.index_dir/'reference.sqlite',db)
            if sha(db)!='18677df675e1a3c5fe9071d3edcd908215c8a20d2fbba4d5effd39411c0909a3':raise ValueError('sealed source index changed')
            index=ReferenceIndex.open(db,work,parts,refs)
            try:catalog.reference_routable_parts={by_source[index.sources[row[0]]] for row in index.connection.execute('SELECT DISTINCT source FROM records')}
            finally:index.close()
        task=summary['task'];request=task['request'];receipt=json.loads(prep.artifact_path(root,task['receipt']).read_text());spec=receipt['spec']
        tool=executable_identity('minimap2');fast=spec['alignment_flags']==[*BASE_FLAGS,'-m','2000']
        if spec['alignment_flags'] not in (BASE_FLAGS,[*BASE_FLAGS,'-m','2000']):raise ValueError('unadmitted raw mapping flags')
        if tool!=spec['tool']:raise ValueError('raw mapper identity changed')
        # Forbid any mapper launch even if a broken cache unexpectedly misses.
        def forbidden(*args,**kwargs):raise AssertionError('adoption verification must not launch a mapper')
        original_run=prep.subprocess.run
        try:
            prep.subprocess.run=forbidden
            accepted=prep._supplement(root,catalog,request,tool,'asm10',32,cache_only=True,
                                      weak_seed_fast=fast,reference_bases=sum(refs.values()))
        finally:prep.subprocess.run=original_run
        if accepted!=task:raise ValueError('actual new cache API did not accept the exact raw task')
        relative='grt/evidence/q0_prepare/tasks/'+task['task_id'];directory=root/relative
        names={p.name for p in directory.iterdir()}
        required=set(prep.MAPPING_OUTPUT_FILES)|{'success.json'}
        if not required<=names<=required|{'stdout.log','stderr.log'}:
            raise ValueError('producer directory contains partial or unexpected artifacts')
        files=[]
        for path in sorted(directory.iterdir()):
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1:raise ValueError('linked producer artifact')
            # Reuse hashes already computed by the real cache API in this process.
            row=prep.identity(root,str(path.relative_to(root)))
            files.append({'name':path.name,'sha256':row['sha256'],'size':row['size']})
        if sha(summary_path)!=summary_sha:raise ValueError('producer proof changed while validating')
        effective=(weak_global_seed_scope(parts,catalog.reference_routable_parts,task['query_ids'],task['target_ids'],
                    reference_bases=sum(refs.values()),preset='asm10') if fast else (task['query_ids'],task['target_ids']))
        report={'status':'complete_mapping_cache_ready_for_owned_adoption','source':str(directory),'relative':relative,
            'task_id':task['task_id'],'files':files,'alignment_flags':spec['alignment_flags'],
            'normal_cache_validation_completed':True,'scoped_approximate_matrix':fast,
            'effective_scope_query_count':len(effective[0]),'effective_scope_target_count':len(effective[1]),
            'source_producer_summary':{'path':str(summary_path),'sha256':summary_sha},
            'validated_builder':prep.builder_identity(),'workspace_modified':False,'mapper_executed':False}
        prep.atomic_write_json(Path('ready.json'),report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
