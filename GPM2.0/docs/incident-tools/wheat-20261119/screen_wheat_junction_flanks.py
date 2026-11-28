"""One-sided impossibility proof. A survivor must go back to the complete chromosome graph."""
from collections import defaultdict
from lgz_core.q0_paths import PathPolicy,pair_blocks,reference_consistent
from lgz_core.q0_threshold_questions import facing_evidence


def maybe_old_cut(l,r,links,old,policy):
    # Production _side immediately rejects the same source. An original assembly-gap edge
    # cannot join two different sources; neither can an overlap preserve its adjacency ID.
    if l.source==r.source or old.kind=='input_assembly_gap':return False
    for z in links:
        if z.hit.matches/z.hit.block_length<policy.minimum_pair_identity:continue
        blocks=pair_blocks(z,l,r)
        # Necessary for the SAME evidence id in PathGraph.joins. Ignore ambiguity and
        # cut/support tests, so this can overcount but can never approve a replacement.
        if (any(b.left.end==l.interval.length for b in blocks) and any(b.right.start==0 for b in blocks)
                and all(reference_consistent(b,l,r) for b in blocks)):return True
    return False


def screen_all(cases,links,groups):
    required={tuple(sorted((l.source,r.source))) for _,_,_,sides in cases for l,r,_,_ in sides};pool=defaultdict(list);policy=PathPolicy()
    for z in links:
        k=tuple(sorted((z.query_source,z.target_source)))
        if k in required and z.hit.matches/z.hit.block_length>=policy.minimum_pair_identity:pool[k].append(z)
    rows={g:dict(candidates=0,geometry_windows=set(),not_feasible=0,already_witnessed=0,survivors=0,possible_windows=set()) for g in groups}
    for chrom,_,alt,sides in cases:
        row=rows[chrom];row['candidates']+=1;opts=[];probes=[]
        for l,r,j,w in sides:
            pair=pool[tuple(sorted((l.source,r.source)))]; can=w is not None and not facing_evidence(l,r,pair,policy)
            if w is not None:row['geometry_windows'].add(w)
            opts.append(can or maybe_old_cut(l,r,pair,j,policy))
            if can:probes.append(w)
        if not all(opts):row['not_feasible']+=1
        elif not probes:row['already_witnessed']+=1
        else:row['survivors']+=1;row['possible_windows'].update(probes)
    union=set().union(*(v['possible_windows'] for v in rows.values()));before=set().union(*(v['geometry_windows'] for v in rows.values()))
    return dict(schema='wheat_all_junction_old_evidence_screen_v1',groups={k:{c:len(n) if isinstance(n,set) else n for c,n in d.items()} for k,d in rows.items()},geometry_windows=len(before),eligible_upper=len(union),needs_graph=[k for k,v in rows.items() if v['survivors']],old_pairs_requested=len(required),old_pairs_with_qualifying_rows=sum(bool(pool[k]) for k in required),mapper_starts=0,scope='Zero rules out a local search for this frozen cohort; nonzero is an upper bound, not a mapper dispatch or a join.')
