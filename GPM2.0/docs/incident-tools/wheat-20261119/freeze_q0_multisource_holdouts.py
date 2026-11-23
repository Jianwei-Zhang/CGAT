"""Select post-rule holdouts from assignments only, enriched for separated anchors in both assemblies."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from freeze_q0_unseen_panels import choose
from prepare_wheat_frontier_panel import PANELS, cohorts, digest, freeze, tsv


def select(rows, datasets):
    previous = (*PANELS, *choose(rows, datasets))
    used = set().union(*(list(g) for g in cohorts(rows, datasets, previous).values()))
    chromosomes = {c for c, _ in previous}; bins = defaultdict(dict); assigned = defaultdict(set)
    for r in rows:
        key=r['dataset_name'],r['seq_name']; c=r['assigned_chr_name']; assigned[key].add(c)
        pos=r['anchor_start']; n=int(r['seq_length_bp']); support=float(r['support_percent'])
        if pos and 20_000<=n<=1_500_000 and support>=20:
            b=c,(int(pos)-1)//1_000_000
            if key in bins[b]: raise ValueError('duplicate assignment')
            bins[b][key]=int(pos), n, support
    selected=[]
    for _ in range(2):
        candidates=[]
        for b,g in bins.items():
            if (b[0] in chromosomes or b[0]=='Un' or used & g.keys() or not 6<=len(g)<=40
                    or sum(n for _,n,_ in g.values())>6_000_000): continue
            strong=[(k,p,n) for k,(p,n,s) in g.items() if s>=70 and len(assigned[k])==1]
            count=Counter(k[0] for k,_,_ in strong)
            if set(count)!=set(datasets) or min(count.values())<2: continue
            spread=max((abs(p-q)-max(n,m) for k,p,n in strong for j,q,m in strong if k[0]!=j[0]),default=0)
            if spread<=0: continue
            candidates.append((-min(count.values()), -spread, -len(strong), b))
        if not candidates: raise ValueError('no additional disjoint multisource holdout; do not relax after seeing results')
        _,_,_,b=min(candidates); selected.append(b); used.update(bins[b]); chromosomes.add(b[0])
    return tuple(selected)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('work','out','lookup','index_receipt'): p.add_argument(n,type=Path)
    p.add_argument('--assignments-sha',required=True);a=p.parse_args(); root=a.work.resolve(strict=True)
    meta=root/'metadata/chr_assignments.tsv'
    if digest(meta)!=a.assignments_sha: raise ValueError('assignment identity mismatch')
    panels=select(tsv(meta), {r['dataset_name'] for r in tsv(root/'metadata/datasets.tsv')})
    print('POST-RULE BLIND BINS',json.dumps(panels),flush=True)
    freeze(root,a.out.resolve(),a.lookup.resolve(strict=True),a.index_receipt.resolve(strict=True),panels=panels)
    if digest(meta)!=a.assignments_sha: raise ValueError('assignment drift')
