"""Replay the 13 former whole-source windows through the production planner. No DNA extraction or mapping."""
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from census_wheat_q0_fork import bind, bounded, require
from check_wheat_inverse_targets import reference
from lgz_core.q0_query_windows import QueryWindow
from lgz_core.q0_regional_discovery import plan_parent
from lgz_core.q0_regional_mapping import target_batches
from lgz_core.q0_native_frontier import RegionalFallbackCache, PHASES
from lgz_core.q0_sources import Interval

COMPARISON='d03288f586c6ac4c6dccfb86a39c78f4e371c2ef232f776e6aac53a8f5a7fa0a'

def run(base):
    old=json.loads(bounded(base/'q0-whole-updated.We9jf3UC/compare/result/comparison.json',1<<20,COMPARISON))
    snap,root,lookup,order,lens=bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json')
    known={'JM19flyeA_contig_4549':('JM19_flye_ABD',422383),'ptg000010l':('JM19_hifiasm',99097964)}
    summary=[];former=[]; calls=[]
    with TemporaryDirectory(dir='/tmp',prefix='wheat-regional-replay-') as tmp, reference(snap,root,lookup,order,lens,Path(tmp)) as index:
        for parent in old['parents']:
            name=parent['parent']; ds,length=known[name]
            key,=(k for k,(rank,n,_) in lookup.items() if n==length and order[rank].contig==name and order[rank].dataset==ds);former.append(key)
            windows=[];out=[]
            for frame in parent['windows']:
                a,b=frame['source_interval'];q=QueryWindow(key,length,a,b,((a,b),));require(q.window_id==frame['query'],'old window identity differs');windows.append(q)
            plans,reason=plan_parent(SimpleNamespace(parts=index.parts),index,windows)
            require(reason is None and [q for q,_ in plans]==windows,'unexpected native fallback or lost siblings')
            for (q,targets),raw in zip(plans,parent['windows']):
                total=sum(t.length for t in targets); require(total==raw['target_bases'] and len({t.segment_id for t in targets})==raw['target_parts'],'target axes differ from historical frames')
                partitions=list(target_batches(targets)); expected=Counter(t.window_id for t in targets); delivered=Counter(t.window_id for part in partitions for t in part)
                require(expected==delivered and max(delivered.values())==1,'local target loss or duplication')
                out.append(dict(query=q.window_id,target_bp=total,targets=len(targets),batches=[sum(t.length for t in part) for part in partitions]))
            summary.append(dict(parent=name,rows=out,whole_native_fallback=False))
    gate=RegionalFallbackCache(bounded=True)
    require(not (root/'grt/evidence/q0_prepare/tasks/q0-map-bbb71092f55e5db234479331/success.json').exists(),'retired native task has an unexpected success receipt')
    def cold_probe(r):calls.append(len(r['target_ids']));return None
    synthetic_miss=gate.dispatch(PHASES[0],[dict(query_ids=former,target_ids=list(lookup))],cold_probe)
    require(calls==[38267] and not synthetic_miss and len(gate.omissions)==1,'a cold library-wide request must remain explicitly unsearched')
    return dict(schema='wheat_13_native_fallback_windows_production_planning_v1',historical_comparison=COMPARISON,
                parents=summary,windows=sum(len(p['rows']) for p in summary),regional_batches=sum(len(w['batches']) for p in summary for w in p['rows']),native_mapper_starts=0,regional_mapper_starts=0,
                cold_gate_control='cache_only_unsearched',scope='Real sealed reference index and actual 13 query/target frames; no alignment, PAF equivalence or final Q0 claim. Cold-miss gate is a separate control.')

if __name__=='__main__':
    with Path('result.json').open('x') as out:json.dump(run(Path(sys.argv[1])),out,sort_keys=True,indent=2);out.write('\n')
