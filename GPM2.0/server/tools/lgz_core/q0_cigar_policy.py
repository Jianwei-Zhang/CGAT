"""Explicit large-regional discovery profiles selected from complete chaining.

The weak-chain span product is a cost proxy, not DP work measured in cells and
not base identity. Approximate chaining output never becomes scientific PAF
evidence. Ordinary/small/unvalidated-preset work retains native parameters.
This policy is an opt-in building block until preparation receipts integrate it.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from .q0_sources import Q0EvidenceError


@dataclass(frozen=True)
class CigarWorkPolicy:
    version: int = 1
    minimum_reference_bases: int = 5_000_000_000
    minimum_query_bases: int = 20_000
    minimum_weak_span: int = 1000
    weak_density_numerator: int = 1
    weak_density_denominator: int = 4
    weak_span_product_trigger: int = 10_000_000_000
    filtered_minimum_chain_score: int = 2000

    def __post_init__(self):
        if self.version != 1 or any(type(value) is not int or value < 1 for value in asdict(self).values()):
            raise Q0EvidenceError("invalid regional CIGAR work policy")
        if self.weak_density_numerator >= self.weak_density_denominator:
            raise Q0EvidenceError("invalid weak-chain density ratio")


@dataclass
class ChainWork:
    chains: int = 0
    weak_chains: int = 0
    weak_span_product: int = 0

    def observe(self, query_span: int, target_span: int, chain_score: int, *, policy: CigarWorkPolicy = CigarWorkPolicy()):
        if (any(type(n) is not int for n in (query_span,target_span,chain_score))
                or min(query_span,target_span) < 1 or chain_score < 0):
            raise Q0EvidenceError("invalid pre-CIGAR chain statistics")
        self.chains += 1
        if (min(query_span,target_span) >= policy.minimum_weak_span
                and chain_score*policy.weak_density_denominator
                < max(query_span,target_span)*policy.weak_density_numerator):
            self.weak_chains += 1
            self.weak_span_product += query_span*target_span


def select_cigar_profile(reference_bases: int, query_bases: int, work: ChainWork, *,
                         complete: bool, preset: str = "asm10",
                         policy: CigarWorkPolicy = CigarWorkPolicy()) -> dict:
    """Only a complete, input-bound chaining run may determine this decision.

    The caller must verify mapper exit zero, parse all output and bind raw output,
    input content, tool and policy in separate receipts. The selected -m profile
    keeps -P; it deliberately sacrifices short additional chains, not original
    sequences or already completed reference/cross/self evidence.
    """
    if complete is not True:
        raise Q0EvidenceError("incomplete chaining cannot select a scientific mapping profile")
    if (any(type(n) is not int or n < 0 for n in (reference_bases,query_bases,work.chains,work.weak_chains,work.weak_span_product))
            or work.weak_chains > work.chains or (work.weak_chains == 0 and work.weak_span_product != 0)):
        raise Q0EvidenceError("invalid completed chaining work summary")
    if preset != "asm10":reason="unvalidated_preset"
    elif reference_bases < policy.minimum_reference_bases:reason="ordinary_reference_size"
    elif query_bases < policy.minimum_query_bases:reason="small_query_context"
    elif work.weak_span_product < policy.weak_span_product_trigger:reason="ordinary_weak_chain_work"
    else:reason="large_regional_weak_chain_work"
    selected=reason=="large_regional_weak_chain_work"
    return {"schema":"lgz_q0_cigar_profile_v1","policy":asdict(policy),"reason":reason,
            "reference_bases":reference_bases,"query_bases":query_bases,"work":asdict(work),
            "additional_flags":["-m",str(policy.filtered_minimum_chain_score)] if selected else [],
            "short_additional_chain_recall_reduced":selected,
            "approximate_chaining_is_evidence":False}


# Separate from reference-local chaining: complete global mappings may prune
# alternative repeat copies. Short query AND short target relationships are not
# covered by this approximate matrix and must still receive native work.
WEAK_GLOBAL_SEED_POLICY = {
    'version': 1, 'preset': 'asm10', 'minimum_reference_bases': 5_000_000_000,
    'minimum_target_bases': 5_000_000_000, 'maximum_query_batch_bases': 8_000_000,
    'minimum_part_bases': 20_000, 'maximum_query_bases': 1_000_000,
    'minimum_chain_score': 2000, 'qualified_reference_queries_allowed': False,
    'short_query_and_target_relationships': 'native_completion_required',
    'native_short_target_completion': 'short_side_queries_when_all_queries_at_least_floor_and_all_targets_below_floor',
    'alternative_repeat_copy_recall_reduced': True, 'whole_source_equivalence': False,
}


def weak_global_seed_scope(parts, routable, queries, targets, *, reference_bases, preset):
    """Return only the long-part relationships covered by this limited profile.

    Queries shorter than the floor can be present in a completed raw cohort,
    but their absence of hits is NOT an approximate completed relationship.
    This permits reuse of an input-bound superset without losing native short
    query/target work. No geometry or negative placement is synthesized.
    """
    policy=WEAK_GLOBAL_SEED_POLICY
    queries,targets=set(queries),set(targets)
    if (preset!=policy['preset'] or reference_bases<policy['minimum_reference_bases']
            or not queries or not targets or routable is None or queries & set(routable)):
        return (),()
    if (sum(parts[key].interval.length for key in queries)>policy['maximum_query_batch_bases']
            or max(parts[key].interval.length for key in queries)>policy['maximum_query_bases']
            or sum(parts[key].interval.length for key in targets)<policy['minimum_target_bases']):
        return (),()
    return (tuple(sorted(key for key in queries if parts[key].interval.length>=policy['minimum_part_bases'])),
            tuple(sorted(key for key in targets if parts[key].interval.length>=policy['minimum_part_bases'])))
