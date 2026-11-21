"""Read-only comparison on an existing SMALL complete native mapping cache.

The baseline is the bfc6d7a1 _supplement function (AST extracted, same shared
libraries), followed by ordinary evidence consumption. The candidate fuses that
consumption into validation. This measures duplicate parsing, not mapper speed
or the whole wheat workflow. Generated FASTA inputs are byte-hashed, not loaded
as a whole DNA heap. No primary-workspace file is written.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import resource
import statistics
import sys
import time
from types import SimpleNamespace

LOOKUP_SHA='2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def stamp(path):
    s=path.stat();return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package-dir','lookup','baseline-source'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--baseline-catalog',type=Path,required=True)
    parser.add_argument('--baseline-alignments',type=Path,required=True)
    parser.add_argument('--task-id',default='q0-map-b30137a13323db8a99874448')
    parser.add_argument('--rounds',type=int,default=5)
    a=parser.parse_args()
    if not 3<=a.rounds<=7:raise ValueError('bounded comparison requires 3-7 alternating rounds')
    sys.path.insert(0,str(a.package_dir))
    from lgz_core import q0_preparation as candidate
    from lgz_core import q0_catalog
    from lgz_core.q0_sources import SourceKey,SourceSegment,Interval
    from lgz_core.common import stable_id
    root=a.workspace.resolve(strict=True)
    relative='grt/evidence/q0_prepare/tasks/'+a.task_id;directory=root/relative
    marker=directory/'success.json';receipt=json.loads(marker.read_text());spec=receipt['spec']
    if (receipt.get('status')!='success' or stable_id('q0-map',spec)!=a.task_id
            or spec['alignment_flags']!=candidate.POLICY['supplement_flags']
            or (directory/'result.paf').stat().st_size>16*1024**2):
        raise ValueError('only the bounded existing native cache is eligible')
    if digest(a.lookup)!=LOOKUP_SHA:raise ValueError('source-part lookup changed')
    lookup=json.loads(a.lookup.read_text());parts={}
    for key in set(spec['query_ids']+spec['target_ids']):
        row=lookup[key];source=SourceKey(row['dataset'],row['contig']);n=row['length'];sha=row['sequence_sha256']
        if stable_id('q0-source-part',[source.dataset,source.contig,0,n,sha])!=key:
            raise ValueError('cache member is not a canonical whole-source part')
        parts[key]=SourceSegment(key,source,Interval(0,n),sha,0,'record_start','record_end')
    catalog=SimpleNamespace(parts=parts)
    request={'kind':'candidate_unroutable_seed','query_ids':spec['query_ids'],'target_ids':spec['target_ids'],
             'native_short_targets_as_queries':True}
    tree=ast.parse(a.baseline_source.read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_supplement')
    namespace=dict(candidate.__dict__)
    exec(compile(ast.Module(body=[function],type_ignores=[]),str(a.baseline_source),'exec'),namespace)
    baseline=namespace['_supplement']
    old_tree=ast.parse(a.baseline_catalog.read_text())
    old_class=next(n for n in old_tree.body if isinstance(n,ast.ClassDef) and n.name=='ObservedSourcePairs')
    scope=dict(q0_catalog.__dict__)
    exec(compile(ast.Module(body=[old_class],type_ignores=[]),str(a.baseline_catalog),'exec'),scope)
    old_observed=scope['ObservedSourcePairs']
    current_tree=ast.parse(Path(q0_catalog.__file__).read_text())
    select=lambda tree,name:next(n for n in tree.body if getattr(n,'name',None)==name)
    if ast.dump(select(old_tree,'_IntervalUnion'),include_attributes=False)!=ast.dump(select(current_tree,'_IntervalUnion'),include_attributes=False):
        raise ValueError('baseline interval union is not the same shared implementation')
    old_alignment_tree=ast.parse(a.baseline_alignments.read_text())
    import lgz_core.q0_alignments as alignments
    current_alignment_tree=ast.parse(Path(alignments.__file__).read_text())
    cls=select(current_alignment_tree,'PafAlignment')
    cls.body=[n for n in cls.body if getattr(n,'name',None)!='paired_query_intervals']
    if ast.dump(old_alignment_tree,include_attributes=False)!=ast.dump(current_alignment_tree,include_attributes=False):
        raise ValueError('shared parser or legacy aligned_blocks differs from the baseline')
    source_lengths={p.source:p.interval.length for p in parts.values()}
    real_read=candidate.read_paf;calls=0
    def counted(*args,**kwargs):
        nonlocal calls
        calls+=1;return real_read(*args,**kwargs)
    candidate.read_paf=counted;baseline.__globals__['read_paf']=counted
    paths=[directory/name for name in candidate.MAPPING_OUTPUT_FILES]+[marker]
    before={str(p):stamp(p) for p in paths}
    def run(mode):
        nonlocal calls
        calls=0;rows=0;h=hashlib.sha256();beg=time.monotonic()
        observed=(old_observed if mode=='baseline_two_pass' else q0_catalog.ObservedSourcePairs)(source_lengths)
        def consume(task,hits):
            nonlocal rows
            for hit in hits:
                query,target=parts[hit.query_name],parts[hit.target_name]
                observed.observe_alignment(hit,query.source,target.source)
                intervals=(tuple(b.query for b in hit.aligned_blocks()) if mode=='baseline_two_pass'
                           else tuple(hit.paired_query_intervals()))
                value=[hit.evidence_id,hit.record_sha256,hit.artifact,hit.line_number,
                       hit.query_name,hit.query_length,hit.query.start,hit.query.end,hit.strand,
                       hit.target_name,hit.target_length,hit.target.start,hit.target.end,
                       hit.matches,hit.block_length,hit.mapping_quality,hit.cigar,[(i.start,i.end) for i in intervals]]
                h.update(json.dumps(value,separators=(',',':')).encode());h.update(b'\n');rows+=1
        args=(root,catalog,request,spec['tool'],spec['preset'],8)
        if mode=='baseline_two_pass':
            task=baseline(*args,cache_only=True)
            if task is None:raise ValueError('existing native cache was rejected; never run a mapper')
            consume(task,counted(root/task['paf'],query_lengths={key:parts[key].interval.length for key in task['query_ids']},
                                 target_lengths={key:parts[key].interval.length for key in task['target_ids']},artifact=task['paf']))
        else:
            task=candidate._supplement(*args,cache_only=True,on_cache_hit=consume)
            if task is None:raise ValueError('candidate native cache was rejected; never run a mapper')
        if rows<1 or calls!=(2 if mode=='baseline_two_pass' else 1):
            raise ValueError('cache records were not completely consumed with the expected parse count')
        relations=stable_id('observed-pairs',[[[s.dataset,s.contig] for s in pair] for pair in sorted(observed)])
        coverage=stable_id('cross-coverage',[[s.dataset,s.contig,[[i.start,i.end] for i in values]]
                    for s,values in sorted(observed.cross_coverage.items())])
        return {'seconds':time.monotonic()-beg,'relations':relations,'coverage':coverage,'rows':rows,'record_digest':h.hexdigest(),'parse_passes':calls,'task':task}
    warm=run('baseline_two_pass');results=[]
    for i in range(a.rounds):
        modes=('baseline_two_pass','fused_one_pass') if i%2==0 else ('fused_one_pass','baseline_two_pass')
        for mode in modes:
            row=run(mode)
            if any(row[k]!=warm[k] for k in ('task','rows','record_digest','relations','coverage')):
                raise ValueError('ordered complete PAF records/geometry/evidence IDs differ')
            results.append({'mode':mode,**{k:v for k,v in row.items() if k!='task'}})
    if before!={str(p):stamp(p) for p in paths}:raise ValueError('native cache changed during comparison')
    medians={mode:statistics.median(r['seconds'] for r in results if r['mode']==mode)
             for mode in ('baseline_two_pass','fused_one_pass')}
    report={'status':'identical_native_cache_records_single_parse','task_id':a.task_id,'rounds':a.rounds,
        'paf_bytes':(directory/'result.paf').stat().st_size,'records':warm['rows'],'record_digest':warm['record_digest'],'relations_digest':warm['relations'],'cross_coverage_digest':warm['coverage'],
        'medians_seconds':medians,'baseline_over_fused':medians['baseline_two_pass']/medians['fused_one_pass'],
        'results':results,'python':sys.version,'hostname':__import__('socket').gethostname(),
        'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'baseline_revision':'bfc6d7a1','baseline_scope':'AST function with identical shared libraries, not entire runtime',
        'baseline_source_sha256':digest(a.baseline_source),'baseline_catalog_sha256':digest(a.baseline_catalog),'baseline_alignments_sha256':digest(a.baseline_alignments),'shared_baseline_ast_checks_passed':True,'lookup_sha256':LOOKUP_SHA,
        'candidate_core_sha256':{p.name:digest(p) for p in (a.package_dir/'lgz_core').glob('*.py')},
        'generated_fasta_content_hashed':True,'whole_dna_heap_loaded':False,'mapper_executed':False,
        'primary_workspace_mutated_by_benchmark':False,'whole_wheat_speedup_claimed':False}
    Path('summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('results','candidate_core_sha256')}),flush=True)


if __name__=='__main__':main()
