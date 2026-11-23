"""Same-node DP-cap ladder on one source-independent and two archived tails.

Only add a per-extension DP cap. Retain the underlying score profile,
complete targets, all-chain flags, resource guard and sequence bytes.
Reports are never accepted as production evidence.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import time

from benchmark_regional_mapper_dispatch import GIB, LOOKUP_SHA, digest, read_json
from probe_regional_dp_budget import command_for, load_case, observed_timing, paired_quality, summarize_quality

QUALITY_SHA='b2b8b2b06cd25aa9c511b198e406c308d00736923dce615f584471d00060a438'
# Indices in the 128-case frozen cohort, NOT the old DP bench indices.
CASES=((1,'archived','slow_independent_density_positive'),
       (72,'heldout','slow_density_positive_seen_in_prior_cap_test'),
       (77,'heldout','slow_density_negative_seen_in_prior_cap_test'))
PROFILES=('original','30m','10m')


def argv_for(c,profile):
    argv=command_for(c['argv'],c['paths']['target.fa'],c['paths']['query.fa'],False)
    if profile not in PROFILES or argv[-4:-2]!=['-t','2'] or argv[1]!='-c':
        raise ValueError('unknown profile or noncanonical resource command')
    return argv if profile=='original' else [*argv[:-2],'--cap-sw-mem',profile,*argv[-2:]]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('workspace','archived','heldout','quality','lookup','output'):
        p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();work=a.workspace.resolve(strict=True);out=a.output.resolve()
    inputs={name:getattr(a,name).resolve(strict=True) for name in ('archived','heldout')}
    if out.is_relative_to(work) or any(x.is_relative_to(work) or x.is_relative_to(out) or out.is_relative_to(x) for x in inputs.values()):
        raise ValueError('overlapping diagnostic paths')
    if digest(a.quality)!=QUALITY_SHA or digest(a.lookup)!=LOOKUP_SHA:
        raise ValueError('frozen cohort identity differs')
    from lgz_core.q0_alignments import read_paf
    from lgz_core.q0_regional_mapping import _execute
    rows=read_json(a.quality)['rows']; lookup=read_json(a.lookup); cases=[]
    if len(rows)!=128:
        raise ValueError('frozen cohort size differs')
    total=0
    for ordinal,source,reason in CASES:
        r=rows[ordinal]
        if r['ordinal']!=ordinal or r['anchor_case']!=(source=='archived'):
            raise ValueError('wrong cohort index')
        c=load_case(work,inputs[source],r,ordinal,lookup);total+=c['bytes']
        cases.append((source,reason,c))
    if total>512*1024**2 or len({c['query'].segment_id for _,_,c in cases})!=3:
        raise ValueError('invalid pilot source diversity or admission size')
    out.mkdir(exist_ok=False)
    begin=time.monotonic()
    def run(case):
        source,reason,c=case; ordinal=c['ordinal']; path=out/str(ordinal); path.mkdir()
        old=paired_quality(c['raw'],c,read_paf); results=[]
        for profile in PROFILES:
            dest=path/profile; dest.mkdir()
            argv=argv_for(c,profile); t=time.monotonic()
            _execute(inputs[source],dest,c['context'],c['rel'],None,c['query'],c['targets'],argv,c['tool'],4*GIB)
            paf=dest/'result.paf.tmp'; digest_value=digest(paf)
            if profile=='original' and digest_value!=c['raw_sha']:
                raise ValueError('same-node original no longer exactly reproduces historical output')
            quality=paired_quality(paf,c,read_paf)
            result={'ordinal':ordinal,'profile':profile,'total_seconds':time.monotonic()-t,
                'native_timing':observed_timing(dest/'stderr.log'),'output_sha256':digest_value,
                'same_as_original':digest_value==c['raw_sha'],'paf_rows':quality['rows'],
                'coverage':summarize_quality(old,quality,c)}
            print(json.dumps(result),flush=True); results.append(result); paf.rename(dest/'result.paf')
        if digest(c['raw'])!=c['raw_sha']:
            raise ValueError('archived raw PAF changed')
        return {'ordinal':ordinal,'source_part':c['query'].segment_id,'reason':reason,
                'query_bases':c['query'].length,'query_dataset':c['qd'],'target_dataset_counts':dict(Counter(c['td'].values())),
                'results':results}
    with ThreadPoolExecutor(max_workers=3) as pool:
        result=list(pool.map(run,cases))
    summary={'status':'same_node_dp_cap_ladder_NOT_production_admission','node':socket.gethostname(),
          'input_fasta_bytes_verified':total,'cases':result,'elapsed_seconds':time.monotonic()-begin,
          'main_workspace_modified':False,'chaining_recomputed':False,'guard_as_bytes':4*GIB,
          'limits':['Fixed three-case native comparison. Only one case is independent of earlier cap trials.',
                    'Complete original targets kept; high-quality core and oriented target comparison, not final Q0/Q1 equivalence.']}
    with (out/'report.json').open('x') as f:
        json.dump(summary,f,indent=2,sort_keys=True); f.write('\n')


if __name__=='__main__':
    main()
