"""Native ABBA of a gentle exact-only seed filter in the ORIGINAL full context.

Separates seed filtering from the changed target-index context of the batching
experiment. Coarse output/profile choices stay frozen. This is an isolated
scientific approximation test, not a production transition or acceptance.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
import time

from benchmark_regional_mapper_dispatch import digest, dispatch, GIB
from benchmark_regional_candidate_screen import input_argv, difference_bases
from benchmark_regional_batched_search import load_cases, interval_quality


def candidate_argv(argv, target, query, candidate):
    result = input_argv(argv, target, query)
    if candidate:
        if '-f' in result: raise ValueError('existing filter must not be overwritten')
        result[-2:-2] = ['-f', '0.001']
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package-dir','control-artifacts','anchor-report','quality-report','trace','lookup','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();started=time.monotonic();work=a.workspace.resolve(strict=True);inputs=a.control_artifacts.resolve(strict=True);out=a.output.resolve()
    if any(x.is_relative_to(y) or y.is_relative_to(x) for x,y in [(out,work),(out,inputs),(inputs,work)]):
        raise ValueError('diagnostic/input/main directories overlap')
    out.mkdir(exist_ok=False);sys.path.insert(0,str(a.package_dir.resolve(strict=True)))
    from lgz_core.q0_alignments import read_paf
    from lgz_core.q0_regional_mapping import _execute
    cases,input_bytes=load_cases(a,work,inputs)
    print(json.dumps({'phase':'inputs_verified','cases':len(cases),'input_bytes':input_bytes,'seconds':time.monotonic()-started}),flush=True)
    phases=[]
    for phase,mode in enumerate(('legacy','exact_f001','exact_f001','legacy')):
        directory=out/f'phase-{phase}-{mode}';directory.mkdir();begin=time.monotonic()
        def run(ordinal,case):
            dest=directory/str(ordinal);dest.mkdir();t=time.monotonic();query=case['query'];targets=case['targets']
            target=inputs/case['rel']/'target.fa';qpath=inputs/case['rel']/'query.fa';coarse_seconds=0
            if case['preargv'] is not None:
                coarse=dest/'coarse';coarse.mkdir();ct=time.monotonic()
                _execute(inputs,coarse,case['context'],case['rel'],None,query,targets,
                         input_argv(case['preargv'],target,qpath,coarse=True),case['tool'],4*GIB)
                if digest(coarse/'result.paf.tmp')!=case['presha']:raise ValueError('coarse evidence differs from historical')
                (coarse/'result.paf.tmp').rename(coarse/'result.paf');coarse_seconds=time.monotonic()-ct
            exact=dest/'exact';exact.mkdir()
            _execute(inputs,exact,case['context'],case['rel'],None,query,targets,
                     candidate_argv(case['argv'],target,qpath,mode=='exact_f001'),case['tool'],4*GIB)
            path=exact/'result.paf.tmp';sha=digest(path)
            if mode=='legacy' and sha!=case['rawsha']:raise ValueError('legacy exact output differs from historical')
            quality=interval_quality(path,case,read_paf);path.rename(exact/'result.paf')
            return {'ordinal':ordinal,'raw_receipt':case['raw_receipt'],'seconds':time.monotonic()-t,'coarse_seconds':coarse_seconds,'sha256':sha,'quality':quality}
        results,order=dispatch(cases,run,7,'completed');elapsed=time.monotonic()-begin
        phases.append({'phase':phase,'mode':mode,'seconds':elapsed,'results':results,'completion_order':order})
        print(json.dumps({'phase':phase,'mode':mode,'seconds':elapsed}),flush=True)
    for left,right in [(0,3),(1,2)]:
        if [r['sha256'] for r in phases[left]['results']]!=[r['sha256'] for r in phases[right]['results']]:raise ValueError('within-mode output differs')
    comparisons=[]
    for old,new in zip(phases[0]['results'],phases[1]['results']):
        a=old['quality'];b=new['quality']
        comparisons.append({'ordinal':old['ordinal'],'old':a['bases'],'candidate':b['bases'],
            'lost':{k:difference_bases(a['intervals'][k],b['intervals'][k]) for k in ('intra','cross')},
            'gained':{k:difference_bases(b['intervals'][k],a['intervals'][k]) for k in ('intra','cross')}})
    report={'status':'native_full_target_gentle_seed_filter_completed_NOT_production_acceptance','hostname':socket.gethostname(),'cases':len(cases),'threads':16,'mappers':7,'mapper_AS_bytes':4*GIB,
        'exact_additional_flags':['-f','0.001'],'coarse_flags_changed':False,'target_context_changed':False,'input_bytes_verified':input_bytes,'phases':phases,'comparisons':comparisons,
        'legacy_over_candidate_pipeline_time':sum(p['seconds'] for p in phases if p['mode']=='legacy')/sum(p['seconds'] for p in phases if p['mode']=='exact_f001'),
        'quality':{'old_paired_core_bases':{k:sum(r['old'][k] for r in comparisons) for k in ('intra','cross')},'lost_old_paired_core_bases':{k:sum(r['lost'][k] for r in comparisons) for k in ('intra','cross')}},
        'historical_full_exact_stdout_all_equal':True,'main_workspace_modified':False,'production_strategy_enabled':False,'seconds':time.monotonic()-started,
        'limitations':['64 bounded completed anchors, not held-out/long-tail/whole-wheat acceptance.',
            'Additional seed filtering changes scientific output; it is NOT a resource-only transition.',
            'Same coarse/profile choices; original target contexts retained, no candidate pruning or batching.',
            'Common input validation excluded; no planning/catalog/final assembly/large-owner-heap measured.']}
    (out/'summary.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'phase':'completed','seconds':report['seconds'],'speedup':report['legacy_over_candidate_pipeline_time'],'quality':report['quality']}),flush=True)


if __name__=='__main__':main()
