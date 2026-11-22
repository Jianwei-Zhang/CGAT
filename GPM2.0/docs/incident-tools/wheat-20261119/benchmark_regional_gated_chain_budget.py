"""Native ABBA of bounded exact work plus per-core/per-dataset full recovery.

An isolated experiment only. Exact candidates use -p0.5/-N50 without -P. If
validated candidate evidence fails 98% cross or 90% intra coverage in ANY core
of ANY target dataset, rerun original full exact work (not coarse work). Native
recovery must match historical full PAF bytes. All interim outputs are retained.
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
from regional_chain_recovery_gate import validated_core_coverage, recovery_decision


def candidate_argv(argv, target, query, candidate):
    result = input_argv(argv, target, query)
    if candidate:
        if result.count('-P') != 1 or any(k in result for k in ('-X','-N','-p','--secondary=no')):
            raise ValueError('require exactly one explicit all-chains flag and no conflicting secondary policy')
        result.remove('-P')
        result[-2:-2] = ['-p','0.5','-N','50']
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
    for phase,mode in enumerate(('legacy','gated_chain_budget','gated_chain_budget','legacy')):
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
                     candidate_argv(case['argv'],target,qpath,mode=='gated_chain_budget'),case['tool'],4*GIB)
            path=exact/'result.paf.tmp';sha=digest(path)
            if mode=='legacy' and sha!=case['rawsha']:raise ValueError('legacy exact output differs from historical')
            decision=None;candidate_sha=None;recovery_seconds=0
            if mode=='gated_chain_budget':
                coverage=validated_core_coverage(path,case,read_paf)
                decision=recovery_decision(query.cores,case['qd'],set(case['td'].values()),coverage)
                candidate_sha=sha
                path.rename(exact/'result.paf');path=exact/'result.paf'
                if decision['native_recovery_required']:
                    recovery=dest/'native-recovery';recovery.mkdir();rt=time.monotonic()
                    _execute(inputs,recovery,case['context'],case['rel'],None,query,targets,
                             candidate_argv(case['argv'],target,qpath,False),case['tool'],4*GIB)
                    path=recovery/'result.paf.tmp';sha=digest(path)
                    if sha!=case['rawsha']:raise ValueError('native recovery differs from historical complete raw PAF')
                    path.rename(recovery/'result.paf');path=recovery/'result.paf';recovery_seconds=time.monotonic()-rt
            else:
                path.rename(exact/'result.paf');path=exact/'result.paf'
            quality=interval_quality(path,case,read_paf)
            with path.open() as handle: paf_rows=sum(bool(line.strip()) and not line.startswith('#') for line in handle)
            return {'ordinal':ordinal,'raw_receipt':case['raw_receipt'],'seconds':time.monotonic()-t,'coarse_seconds':coarse_seconds,
                    'sha256':sha,'quality':quality,'paf_rows':paf_rows,'recovery_decision':decision,'candidate_sha256':candidate_sha,'native_recovery_seconds':recovery_seconds}
        results,order=dispatch(cases,run,7,'completed');elapsed=time.monotonic()-begin
        phases.append({'phase':phase,'mode':mode,'seconds':elapsed,'results':results,'completion_order':order})
        print(json.dumps({'phase':phase,'mode':mode,'seconds':elapsed}),flush=True)
    for left,right in [(0,3),(1,2)]:
        if [r['sha256'] for r in phases[left]['results']]!=[r['sha256'] for r in phases[right]['results']]:raise ValueError('within-mode output differs')
    if [(r['candidate_sha256'],r['recovery_decision']) for r in phases[1]['results']] != [(r['candidate_sha256'],r['recovery_decision']) for r in phases[2]['results']]:
        raise ValueError('candidate raw or recovery decisions differ between repetitions')
    comparisons=[]
    for old,new in zip(phases[0]['results'],phases[1]['results']):
        a=old['quality'];b=new['quality']
        comparisons.append({'ordinal':old['ordinal'],'old':a['bases'],'candidate':b['bases'],
            'lost':{k:difference_bases(a['intervals'][k],b['intervals'][k]) for k in ('intra','cross')},
            'gained':{k:difference_bases(b['intervals'][k],a['intervals'][k]) for k in ('intra','cross')}})
    report={'status':'native_gated_chain_budget_completed_NOT_production_acceptance','hostname':socket.gethostname(),'cases':len(cases),'threads':16,'mappers':7,'mapper_AS_bytes':4*GIB,
        'exact_removed_flags':['-P'],'exact_additional_flags':['-p','0.5','-N','50'],'gate_is_per_dataset_and_per_core':True,'coarse_flags_changed':False,'target_context_changed':False,'input_bytes_verified':input_bytes,'phases':phases,'comparisons':comparisons,
        'legacy_over_candidate_pipeline_time':sum(p['seconds'] for p in phases if p['mode']=='legacy')/sum(p['seconds'] for p in phases if p['mode']=='gated_chain_budget'),
        'native_recovery_cases':sum(r['recovery_decision']['native_recovery_required'] for r in phases[1]['results']),'quality':{'old_paired_core_bases':{k:sum(r['old'][k] for r in comparisons) for k in ('intra','cross')},'lost_old_paired_core_bases':{k:sum(r['lost'][k] for r in comparisons) for k in ('intra','cross')}},
        'historical_full_exact_stdout_all_equal':True,'main_workspace_modified':False,'production_strategy_enabled':False,'seconds':time.monotonic()-started,
        'limitations':['64 bounded completed anchors, not held-out/long-tail/whole-wheat acceptance.',
            'Secondary-chain admission changes scientific output; it is NOT a resource-only transition.',
            'Same exhaustive coarse/profile choices and full targets; original exact raw is rerun when a dataset/core fails the gate.',
            'High-quality core coverage is not proof of orthology or preservation of all alternative relationships.',
            'Common input validation excluded; no planning/catalog/final assembly/large-owner-heap measured.']}
    (out/'summary.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'phase':'completed','seconds':report['seconds'],'speedup':report['legacy_over_candidate_pipeline_time'],'quality':report['quality']}),flush=True)


if __name__=='__main__':main()
