"""Versioned Q0 acceptance: support a usable path, not uniqueness of unsearched alternatives."""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass
from pathlib import Path

from .common import sha256_file, stable_id
from .q0_frontier_scope import UnsearchedQ0Context, _unsearched_axes
from .q0_sources import Interval, Q0EvidenceError, SourceKey, merged_intervals, subtract_intervals

SCOPE = 'positive_threshold'
SEMANTICS = 'supported_backbone_not_exhaustive_alternatives_v2'
MAX_REPAIRS = 1


def contract():
    here = Path(__file__)
    return {'semantics': SEMANTICS, 'minimum_anchor_bp': 100, 'join_reach_bp': 2000,
            'maximum_repairs': MAX_REPAIRS, 'readless_only': True,
            'rule_sha256': sha256_file(here.with_name('q0_threshold_questions.py')),
            'junction_review_sha256': sha256_file(here.with_name('q0_junction_review.py')),
            'paf_chunks_sha256': sha256_file(here.with_name('q0_paf_chunks.py')),
            'retained_hit_sha256': sha256_file(here.with_name('q0_retained_hits.py')),
            'native_frontier_sha256': sha256_file(here.with_name('q0_native_frontier.py')),
            'acceptance_sha256': sha256_file(here), 'preparer_sha256': sha256_file(here.with_name('q0_threshold_prepare.py'))}


def record(frontier):
    return None if frontier is None else [[asdict(s), [[i.start, i.end] for i in spans]] for s,spans in sorted(frontier.items())]


def decode(raw, lengths):
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise Q0EvidenceError('invalid threshold request inventory')
    result = {}
    for row in raw:
        if not isinstance(row,list) or len(row)!=2 or not isinstance(row[0],dict) or set(row[0])!={'dataset','contig'} or not isinstance(row[1],list) or not row[1]:
            raise Q0EvidenceError('invalid threshold source request')
        s = SourceKey(**row[0]); spans = []
        for bounds in row[1]:
            if not isinstance(bounds,list) or len(bounds)!=2 or any(type(n) is not int for n in bounds):
                raise Q0EvidenceError('invalid threshold request bounds')
            spans.append(Interval(*bounds))
        if s not in lengths or s in result or tuple(spans)!=merged_intervals(spans) or spans[-1].end>lengths[s]:
            raise Q0EvidenceError('unbound or noncanonical threshold request')
        result[s]=tuple(spans)
    if record(result)!=raw:
        raise Q0EvidenceError('noncanonical threshold request order')
    return result


@dataclass(frozen=True)
class VerifiedScope:
    """Assigned from the verified manifest and its bound assignment table, not a catalog flag."""
    ready_identity: str
    assignments: tuple
    report_identity: str


class ThresholdRepairRequired(UnsearchedQ0Context):
    """Private handoff of this selection's exact demand (None means full search)."""
    def __init__(self, reason, demand, native_ids=()):
        super().__init__(reason)
        self.demand = demand
        self.native_ids = tuple(native_ids)

    def __reduce__(self):
        return type(self), (self.args[0], self.demand, self.native_ids)


def complete_window_accounting(catalog):
    """Both planners finished. Each skipped *whole* context recorded both axes before dispatch.

    If no omitted context intersects a new shoulder, widening to it cannot add a task: the
    partial-stage inputs/results stay unchanged, so the candidate-stage inputs stay unchanged
    too. This is coverage of the existing planner, not a claim that every locus was mapped.
    """
    n = 0
    for phase in ('regional_partial_discovery', 'regional_candidate_discovery'):
        row = catalog.get(phase)
        if not isinstance(row, dict) or row.get('frontier_scope') is not True:
            return False
        done = row.get('completed_regional_tasks'); skipped = row.get('frontier_omitted_windows')
        if type(done) is not int or done < 0 or type(skipped) is not int or skipped < 0:
            raise Q0EvidenceError('invalid threshold regional phase counts')
        n += done
    from .q0_junction_review import extra_count
    if n + extra_count(catalog) != sum(t['kind'] == 'regional_discovery' for t in catalog['supplementary_alignments']):
        raise Q0EvidenceError('threshold regional phase completion differs from tasks')
    return True


def audit(data, selection, *, admission_policy=None, path_policy=None, quality_pass=None):
    from .q0_admission import AdmissionPolicy, FirstRequestSelection
    from .q0_paths import PathPolicy
    from .q0_threshold_questions import questions
    if isinstance(selection, FirstRequestSelection):
        raise Q0EvidenceError('a planning-only Q0 selection cannot certify a prepared generation')
    binding = data.threshold_scope
    if not isinstance(binding, VerifiedScope) or not binding.ready_identity or binding.ready_identity!=data.ready_manifest_identity:
        raise Q0EvidenceError('threshold acceptance needs a verified scope and assignment inventory')
    if quality_pass is not None or (admission_policy is not None and admission_policy!=AdmissionPolicy()) or (path_policy is not None and path_policy!=PathPolicy()):
        raise Q0EvidenceError('threshold acceptance does not cover modified policies or reads QC')
    report=data.catalog.get('supplement_scope')
    if not isinstance(report, dict) or stable_id('threshold-search', report)!=binding.report_identity:
        raise Q0EvidenceError('threshold search report changed after verification')
    mode=report['effective']
    if report.get('requested')!=SCOPE or report.get('acceptance')!=SEMANTICS:
        raise Q0EvidenceError('threshold acceptance contract differs from catalog')
    frontier=decode(report['threshold_request'],{s:len(seq) for s,seq in data.sources.items()})
    axes=_unsearched_axes(report,data.parts)
    from .q0_native_frontier import CACHE_ONLY, omitted, touches
    pending = omitted(report,data.parts)
    if mode=='full':
        if axes or frontier is not None: raise Q0EvidenceError('full threshold fallback contains omissions or a scoped request')
        return {'full_discovery': True}
    if mode not in ('base_only','decision_frontier') or frontier is None or (mode=='base_only' and (frontier or axes)):
        raise Q0EvidenceError('invalid threshold search mode')
    assignments=({'dataset_name':d,'seq_name':s,'assigned_chr_name':c} for d,s,c in binding.assignments)
    # Only unresolved gaps/weak placements may abstain from a global search. A
    # missing required chromosome never becomes accepted through this rule.
    bounded_cold = bool(pending) and report.get('native_fallback_policy') == CACHE_ONLY
    issues = [] if bounded_cold else None
    need,counts=questions(data,selection,assignments,issue_sink=issues.append if bounded_cold else None)
    if need is None: raise ThresholdRepairRequired('threshold selector needs full supplemental evidence', need)
    affected = [row['id'] for row in pending if touches(row,data.parts,need)]
    if affected:
        if not bounded_cold:
            raise Q0EvidenceError('unbound deferred native fallback policy; cannot certify the selected path')
        missing = {}
        for issue in issues:
            if issue['kind'] not in ('weak_placement','unproven_join'):
                for d,s,a,b in issue['spans']:
                    missing.setdefault(SourceKey(d,s),[]).append(Interval(a,b))
        if any(touches(row,data.parts,missing) for row in pending):
            raise Q0EvidenceError('required Q0 chromosome remains unproven; automatic whole-source fallback is disabled')
        counts['unsearched_whole_source_matrices'] = len(affected)

    enumerated = mode=='decision_frontier' and complete_window_accounting(data.catalog) and (not pending or bounded_cold)
    covered_without_repair = 0
    for s,spans in need.items():
        for span in spans:
            if subtract_intervals(span,frontier.get(s,())):
                if not enumerated:
                    raise ThresholdRepairRequired('threshold decision was not requested on this source interval', need)
                covered_without_repair += 1
            if s in axes:
                starts,omitted=axes[s]; j=bisect_right(starts,span.end-1)-1
                if j>=0 and omitted[j].end>span.start:
                    raise ThresholdRepairRequired('threshold decision overlaps an unsearched source interval', need)
    if covered_without_repair:
        counts['expanded_intervals_already_covered_by_planner'] = covered_without_repair
    return counts


def validate_catalog(root, manifest, catalog):
    from . import q0_preparation as prep
    prep._readless_package(root)
    paths={i['path'] for i in manifest['inputs']}
    if not {'metadata/package.tsv','metadata/chr_assignments.tsv'} <= paths:
        raise Q0EvidenceError('threshold evidence lacks bound package/assignments')
    scope=catalog['supplement_scope']; mode=scope['effective']
    if scope.get('acceptance')!=SEMANTICS or 'threshold_request' not in scope:
        raise Q0EvidenceError('missing threshold evidence contract')
    lengths={SourceKey(**r['source']):r['length'] for r in catalog['sources']}
    q=decode(scope['threshold_request'],lengths)
    from .q0_native_frontier import validate_inventory
    from .q0_junction_review import extra_count
    extra_count(catalog)
    from .q0_native_frontier import CACHE_ONLY
    if scope.get('deferred_native_matrices') and scope.get('native_fallback_policy') != CACHE_ONLY:
        raise Q0EvidenceError('unbound deferred native fallback policy')
    if 'native_fallback_policy' in scope and (scope['native_fallback_policy'] != CACHE_ONLY or mode != 'decision_frontier'):
        raise Q0EvidenceError('unknown or misplaced native fallback policy')
    validate_inventory(catalog)
    if mode=='base_only':
        if q!={} or scope['unsearched_part_intervals'] or catalog['supplementary_alignments'] or any(k in catalog for k in ('regional_partial_discovery','regional_candidate_discovery')):
            raise Q0EvidenceError('base-only threshold evidence claims supplemental discovery')
    elif (mode=='full' and q is not None) or (mode=='decision_frontier' and not q):
        raise Q0EvidenceError('threshold scope differs from requested work')
