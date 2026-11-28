"""Automatic Q0 supplement-scope selection.

The user-facing workflow asks for a result priority, not an implementation mode.
This module turns a small, metadata-only workload description into a bound
scope decision. It is deliberately conservative: a lossy proof-repair scope
is selected only for a large regional workload without reads-QC, and any
unknown safety input selects the complete scope.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

AUTO_SCOPE = "auto"
FULL_SCOPE = "full"
PROOF_REPAIR_SCOPE = "decision_frontier_repair"
POLICY_VERSION = 1


@dataclass(frozen=True)
class AutoScopePolicy:
    version: int = POLICY_VERSION
    minimum_paf_bytes: int = 2 * 1024**3
    minimum_source_bp: int = 1_000_000_000
    minimum_longest_source_bp: int = 20_000_000
    minimum_source_count: int = 100
    minimum_base_alignments: int = 8

    def __post_init__(self) -> None:
        if self.version != POLICY_VERSION:
            raise ValueError("unsupported automatic Q0 scope policy version")
        for name in (
            "minimum_paf_bytes", "minimum_source_bp", "minimum_longest_source_bp",
            "minimum_source_count", "minimum_base_alignments",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"invalid automatic Q0 scope threshold: {name}")


@dataclass(frozen=True)
class ScopeWorkload:
    """Facts available before the expensive Q0 evidence scan starts."""

    regional_enabled: bool
    reads_qc_enabled: bool | None
    reference_bp: int
    source_bp: int
    longest_source_bp: int
    source_count: int
    paf_bytes: int
    base_alignment_count: int

    def __post_init__(self) -> None:
        if type(self.regional_enabled) is not bool:
            raise ValueError("regional_enabled must be boolean")
        if self.reads_qc_enabled not in (True, False, None):
            raise ValueError("reads_qc_enabled must be true, false, or unknown")
        for name in (
            "reference_bp", "source_bp", "longest_source_bp", "source_count",
            "paf_bytes", "base_alignment_count",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"invalid automatic Q0 workload metric: {name}")


@dataclass(frozen=True)
class ScopeDecision:
    requested_scope: str
    effective_scope: str
    reason: str
    signals: tuple[str, ...]
    workload: ScopeWorkload
    policy: AutoScopePolicy

    def record(self) -> dict:
        return {
            "schema": "lgz_q0_scope_decision_v1",
            "requested_scope": self.requested_scope,
            "effective_scope": self.effective_scope,
            "reason": self.reason,
            "signals": list(self.signals),
            "workload": asdict(self.workload),
            "policy": asdict(self.policy),
        }


def decide_scope(workload: ScopeWorkload, *, policy: AutoScopePolicy = AutoScopePolicy()) -> ScopeDecision:
    """Choose a scope without inspecting PAF contents or changing inputs.

    The large-PAF signal is required because the optimization is intended for
    the expensive regional path, not merely for a large assembly. A second
    independent signal is required to avoid enabling the lossy mode for a
    pathological file-size-only or contig-count-only case.
    """
    signals: list[str] = []
    if not workload.regional_enabled:
        reason = "regional_route_disabled"
    elif workload.reads_qc_enabled is not False:
        reason = "reads_qc_enabled_or_unknown"
    else:
        if workload.paf_bytes >= policy.minimum_paf_bytes:
            signals.append("large_paf_inventory")
        if workload.source_bp >= policy.minimum_source_bp:
            signals.append("large_source_inventory")
        if workload.longest_source_bp >= policy.minimum_longest_source_bp:
            signals.append("long_source_contig")
        if workload.source_count >= policy.minimum_source_count:
            signals.append("many_source_contigs")
        if workload.base_alignment_count >= policy.minimum_base_alignments:
            signals.append("many_base_alignments")
        if "large_paf_inventory" not in signals:
            reason = "paf_inventory_below_complexity_gate"
        elif len(set(signals) & {
            "large_source_inventory", "long_source_contig", "many_source_contigs",
            "many_base_alignments",
        }) < 1:
            reason = "no_independent_complexity_signal"
        else:
            return ScopeDecision(AUTO_SCOPE, PROOF_REPAIR_SCOPE,
                                 "large_regional_workload", tuple(signals), workload, policy)
    return ScopeDecision(AUTO_SCOPE, FULL_SCOPE, reason, tuple(signals), workload, policy)
