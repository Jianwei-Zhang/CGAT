"""Resolve whole-parent matrix coverage without resurrecting the retired native mapping.

The historical native fallback reused the original partial request's unmodified
*target IDs*. Reconstruct that task ID from all bound source parts as a content
proof of the exact requested target set (a matching count alone is insufficient).
"""
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
import json
import sys

from bound_regional_scope_from_native_receipts import EXPECTED
from census_wheat_q0_fork import SNAP, bounded, require
from lgz_core import q0_regional_mapping as mapping
from lgz_core.common import stable_id
from lgz_core.q0_cigar_policy import WEAK_GLOBAL_SEED_POLICY
from lgz_core.q0_regional_candidates import CompletedNativeScopes
from wheat_dispatch_scope import inputs, original_queries, put, QUERIES

GEOMETRY='b209c9be61fe9ac2ed773b4c7e216fa151ec3c2f8419c300f886ca2e10f7db61'
RETIRED='2f6d5d8a1a5a3d775ffe3e59c555288720f4825a965ae19599410e3183db7252'
ADOPTED='8ae9a628bcaf403bb26ccf6bf55ad192072f7bc576108951e455092dac344f40'
REPLAY='9b7e12988d8fabe2fd360910d517a3e112e99da4b03578fe1ed9fdcff4d2a682'


def checked(path,pin):
    return json.loads(bounded(path,64<<20,pin))


def main(base,geometry,out):
    snap,root,lookup,order,_=inputs(base); ranks={p:v[0] for p,v in lookup.items()}; ids=sorted(lookup)
    queries=original_queries(base,lookup,order); plan=checked(base/'q0-fork-partial-queries-20261123-1556/plan/replay.json',REPLAY)
    observed=checked(geometry,GEOMETRY);retired=checked(base.parent/'logs/retire-43017096-20261124/retired.json',RETIRED)
    require(observed['native_task']==retired['task'] and observed['job']==retired['job'] and retired['task_absent'] and observed['source_run']==snap['source_run'] and observed['snapshot']==SNAP,'unbound retired task')
    require(observed['input_sha256']['queries.tsv.gz']==QUERIES and observed['input_sha256']['replay.json']==REPLAY and observed['replayed_plan_queries']==len(queries)==61000,'foreign historical plan')
    tool=mapping._ops().executable_identity('minimap2'); original=[row['part'] for row in observed['native_queries']]
    spec=dict(schema='lgz_q0_mapping_v1',query_ids=sorted(original),target_ids=ids,members=[[p,lookup[p][2]] for p in ids],tool=tool,preset='asm10',alignment_flags=mapping.BASE_FLAGS)
    require(len(ids)==observed['native_targets'] and sum(lookup[p][1] for p in ids)==observed['native_target_bp'] and stable_id('q0-map',spec)==retired['task'], 'cannot prove complete historical required-target inventory')
    for row in observed['native_queries']:
        rank,n,_=lookup[row['part']];require(order[rank].contig==row['source'] and n==row['whole_parent_bp'] and sum(r==rank for r,_,_ in queries.values())==row['planned_query_windows'],'native parent mismatch')
    seeded=checked(base/'q0-cache-adoption-fast-20261122/ready.json',ADOPTED)
    require(seeded['normal_cache_validation_completed'] and seeded['scoped_approximate_matrix'] and not seeded['mapper_executed'] and seeded['task_id'] in EXPECTED and any(f['name']=='success.json' and f['sha256']==EXPECTED[seeded['task_id']] for f in seeded['files']),'foreign weak-profile acceptance')
    pool=SimpleNamespace(ranks=ranks,scopes=[],scope_task_ids=[],approximate_scope_task_ids=[])
    mask=lambda keys:CompletedNativeScopes.mask(pool,keys)
    require({p.parent.name for p in (root/'grt/evidence/q0_prepare/tasks').glob('*/success.json')}==EXPECTED.keys()==plan['native_matrices'].keys(),'native cohort has changed')
    for tid,sha in sorted(EXPECTED.items()):
        row=checked(root/'grt/evidence/q0_prepare/tasks'/tid/'success.json',sha);s=row['spec'];q=s['query_ids'];t=s['target_ids'];flags=s['alignment_flags'];leaf=plan['native_matrices'][tid]
        require(row['status']=='success' and stable_id('q0-map',s)==tid and s['tool']==tool and s['preset']=='asm10' and s['members']==[[p,lookup[p][2]] for p in sorted(set(q+t))] and leaf['receipt_sha256']==sha and leaf['alignment_flags']==flags and any(o['path'].endswith('/result.paf') and o['sha256']==leaf['paf_sha256'] for o in row['outputs']), 'unbound completed matrix')
        if flags!=mapping.BASE_FLAGS:
            require(tid==seeded['task_id'] and flags==seeded['alignment_flags']==[*mapping.BASE_FLAGS,'-m',str(WEAK_GLOBAL_SEED_POLICY['minimum_chain_score'])],'unexpected approximate profile')
            # Original stock cache acceptance already established cohort-level
            # eligibility; the stock policy's only per-part filter is length.
            floor=WEAK_GLOBAL_SEED_POLICY['minimum_part_bases'];q=[p for p in q if lookup[p][1]>=floor];t=[p for p in t if lookup[p][1]>=floor]
            require((len(q),len(t))==(seeded['effective_scope_query_count'],seeded['effective_scope_target_count']),'scoped effective set differs');pool.approximate_scope_task_ids.append(tid)
        pool.scopes.append((mask(q),mask(t)));pool.scope_task_ids.append(tid)
    targets=mask(ids);groups=defaultdict(list)
    for qid,(rank,a,b) in queries.items():groups[rank].append(qid)
    skipped={};counts=Counter()
    for rank,windows in sorted(groups.items()):
        p=ids[rank];require(ranks[p]==rank,'rank drift')
        if CompletedNativeScopes.remaining_targets(pool,p,targets):continue
        kind='declared_long_part_scope' if CompletedNativeScopes.remaining_targets(pool,p,targets,include_approximate=False) else 'exact_complete_matrices'
        skipped[rank]=dict(part=p,kind=kind,windows=sorted(windows));counts[kind]+=len(windows)
    result=dict(schema='wheat_frozen_partial_native_parent_coverage_v1',snapshot=SNAP,query_inventory=QUERIES,native_adoption=ADOPTED,native_matrices=EXPECTED,retired_target_set_witness=retired['task'],required_targets=len(ids),parents_in_plan=len(groups),parent_windows=skipped,pre_frontier_skip_counts=counts,retired_fallback_parents=sorted(ranks[p] for p in original),mapper_starts=0)
    print('NATIVE_PARENT_COVERAGE',len(skipped),'parents',dict(counts),'receipt',put(out,result),flush=True)


if __name__=='__main__':main(*map(Path,sys.argv[1:]))
