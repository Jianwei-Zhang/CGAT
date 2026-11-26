"""Isolated cached trial: reference orientation must not break a source contig.

Only cross-chromosome chains can make barriers. Existing Top10 and single-group
support thresholds are retained, including the conservative opposite-strand
competition test. This is not an instruction to straighten internal inversions.
"""
from collections import defaultdict
from unittest.mock import patch
from wheat_continuous_dominant_admission_readonly import continuous_candidates
import wheat_continuous_dominant_admission_readonly as continuous
import wheat_top_chain_admission_readonly as top
from wheat_local_chain_primitives import chain
from wheat_split_first_indexed_readonly import indexed_barriers

_NATIVE_BARRIERS = indexed_barriers()[0]


def foreign_barriers(groups, high, main_key, main_chain, length, policy=continuous.POLICY):
    # Filtering is confined to the split decision, NOT reference screening,
    # dominance evidence, or the actual DNA carried by a placement.
    cross_chr = {k: rows for k, rows in groups.items()
                 if k == main_key or k[0] != main_key[0]}
    return _NATIVE_BARRIERS(cross_chr, high, main_key, main_chain, length, policy)


def candidates(part, groups, high, chromosome):
    keys = [k for k, rows in groups.items() if k[0] == chromosome
            and continuous.adm._size(a.source for a in rows) >= 100_000]
    if not keys:
        return [], {"reason": "no_main_chain"}
    lengths = {k: continuous.adm._size(a.source for a in chain(groups[k], k[1])) for k in keys}
    primary = min(keys, key=lambda k: (-lengths[k], k))
    with patch.object(continuous, "foreign_barriers", foreign_barriers):
        old, old_audit = continuous_candidates(part, groups, high, target=chromosome)
    with patch.object(top, "FOREIGN_BARRIERS", foreign_barriers):
        new, audit = top.top_chain(part, groups, high, primary, ratios=(10,))
    # Never rescue a secondary strand by independently peeling its own source
    # region out of an otherwise continuous, primary-oriented contig.
    values = [p for p in old["75"] if p.orientation == primary[1]] + new["10"]
    unique = {}
    for p in values:
        unique.setdefault((p.source, p.interval, p.orientation, p.reference_blocks), p)
    return list(unique.values()), {"primary": list(primary), "chain_support": [[list(k), v] for k,v in sorted(lengths.items())],
                                 "continuous75": old_audit, "top10": audit}


def merge_frozen(frozen, new):
    """Keep valid legacy candidates, except opposite orientation inside a carrier.

    This guard concerns physical source coordinates and chromosome, not IDs,
    reference overlap, or a list of wheat contig names.
    """
    by_source = defaultdict(list)
    for p in new:
        by_source[(p.source, p.chromosome)].append(p)
    kept = []; removed = []
    for p in frozen:
        owners = by_source[(p.source, p.chromosome)]
        if any(q.orientation != p.orientation and q.interval.intersection(p.interval) is not None for q in owners):
            removed.append(p.placement_id)
        else:
            kept.append(p)
    unique = {}
    for p in kept + new:
        unique.setdefault((p.source, p.interval, p.orientation, p.reference_blocks), p)
    return list(unique.values()), removed
