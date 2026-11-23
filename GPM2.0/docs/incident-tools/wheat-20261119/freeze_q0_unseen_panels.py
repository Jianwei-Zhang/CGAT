"""Preselect independent JM19 holdouts from assignment metadata alone, then freeze all original evidence."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from prepare_wheat_frontier_panel import PANELS, cohorts, digest, freeze, tsv


def choose(rows, datasets, previous=PANELS, sizes=(8, 16, 32)):
    seen = set().union(*(g.keys() for g in cohorts(rows, datasets, previous).values())) if previous else set()
    used_chromosomes = {c for c, _ in previous}
    bins = defaultdict(dict)
    for r in rows:
        n, anchor = int(r['seq_length_bp']), r['anchor_start']
        if not anchor or not 20_000 <= n <= 1_500_000 or float(r['support_percent']) < 20:
            continue
        key = r['dataset_name'], r['seq_name']
        b = r['assigned_chr_name'], (int(anchor)-1)//1_000_000
        if key in bins[b]:
            raise ValueError('duplicate source assignment within a bin')
        bins[b][key] = n
    selected = []
    for target in sizes:
        good = []
        for (chrom, mb), group in bins.items():
            ds = Counter(d for d, _ in group)
            if (chrom in used_chromosomes or chrom == 'Un' or group.keys() & seen or set(ds) != set(datasets)
                    or min(ds.values()) < 2 or not 5 <= len(group) <= 40 or sum(group.values()) > 6_000_000):
                continue
            good.append((abs(len(group)-target), -min(ds.values()), chrom, mb))
        if not good:
            raise ValueError('not enough disjoint test cohorts')
        _, _, c, m = min(good)
        selected.append((c, m)); used_chromosomes.add(c); seen.update(bins[c, m])
    return tuple(selected)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('work', 'out', 'lookup', 'index_receipt'):
        p.add_argument(n, type=Path)
    p.add_argument('--assignments-sha', required=True)
    a = p.parse_args(); root = a.work.resolve(strict=True); out = a.out.resolve(); meta = root/'metadata/chr_assignments.tsv'
    if digest(meta) != a.assignments_sha or out.exists() or root == out or out.is_relative_to(root) or root.is_relative_to(out):
        raise ValueError('wrong assignment snapshot or non-isolated output')
    ds = {r['dataset_name'] for r in tsv(root/'metadata/datasets.tsv')}
    panels = choose(tsv(meta), ds)
    print('BLIND HOLDOUT BINS', json.dumps(panels), flush=True)
    freeze(root, out, a.lookup.resolve(strict=True), a.index_receipt.resolve(strict=True), panels=panels)
    if digest(meta) != a.assignments_sha:
        raise ValueError('assignment metadata changed')
