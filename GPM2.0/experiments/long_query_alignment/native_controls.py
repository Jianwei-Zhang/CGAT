"""Deterministic native-DP controls; data generated only by an explicit caller.

Keep the original eight controls; add a real large candidate/split-pool control.
These are fixtures, NOT passing validation receipts or a recovery certificate.
"""
from __future__ import annotations

import random

import audit_post_dp as audit
import windowed_alignment as wa

CASE_NAMES = (
    "identity","split_decoy","chain_score_not_alignment_score",
    "cancelled_indels","cancelled_indels_reverse","three_split_decoy",
    "three_split_reverse","three_split_without_exact_parent","many_equal_split_targets",
)


def fixtures():
    result = audit.fixtures()
    rng = random.Random(2311303)
    dna = bytes(rng.choices(b"ACGT",k=200000))
    decoy = bytearray(dna)
    decoy[60000:61000] = bytes(rng.choices(b"ACGT",k=1000))
    decoy[130000:131000] = bytes(rng.choices(b"ACGT",k=1000))
    cancelled = dna[:60000]+bytes(rng.choices(b"ACGT",k=2000))+dna[60000:130000]+dna[132000:]
    changed = bytes(decoy)
    result.extend([
        ("cancelled_indels",{"target":cancelled},dna),
        ("cancelled_indels_reverse",{"target":cancelled},dna.translate(wa.RC)[::-1]),
        ("three_split_decoy",{"exact":dna,"decoy":changed},dna),
        ("three_split_reverse",{"exact":dna,"decoy":changed},dna.translate(wa.RC)[::-1]),
        ("three_split_without_exact_parent",{"decoy":changed},dna),
        # 70 original target copies exercise actual pre/post-DP competition and
        # split pools, not only an in-memory sort replay or primary-only output.
        ("many_equal_split_targets",{f"decoy{i:03d}":changed for i in range(70)},dna),
    ])
    return result
