"""Compare draft and full Q0 consumer-visible geometry. Diagnostic only; never publish a draft."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from lgz_core import q0_admission as admission, q0_preparation as prep
from lgz_core.q0_publication import available_intervals, source_occupancy
from lgz_core.q0_sources import Q0EvidenceError
from probe_q0_decision_frontier import subset_input
from replay_q0_reverse_parents import load_panel


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def span(i):
    return i.start, i.end


def source(s):
    return s.dataset, s.contig


def geometry(path):
    if path is None:
        return None
    slices = [(source(s.source), span(s.interval), s.orientation) for s in path.slices]
    joins = [(j.kind, j.left_end, j.right_start, j.n_bp, source(j.gap_source) if j.gap_source else None,
              span(j.gap_interval) if j.gap_interval else None) for j in path.joins]
    return slices, joins


def footprint(result, seqs):
    d = result.decisions
    occupied = source_occupancy(result)
    available = available_intervals(seqs, occupied)  # Publication code; excludes long N gaps.
    chrs = {r['chromosome']: r for r in d['chromosomes']}

    def key(pair):
        return json.dumps(pair, separators=(',', ':'))

    def by_src(rows):
        return {key(k): [span(i) for i in v] for k, v in rows.items()}

    return {
        'sequence': {c: sha256(v.encode('ascii')).hexdigest() for c, v in result.records.items()},
        'ordered_path': {c: geometry(r.path) for c, r in result.paths.items()},
        'reference_gaps': {c: (r['status'], r.get('reference_unrepresented')) for c, r in chrs.items()},
        'occupied': by_src({source(s): v for s, v in occupied.items() if v}),
        'available_donor_intervals': by_src(available),
        'unplaced_parts': {i: True for i in d['unplaced_segment_ids']},
        'known_placement_geometry': {key([p.segment_id, p.chromosome, p.orientation, span(p.interval),
                                         p.localization_kind, [span(i) for i in p.reference_intervals]]): True
                                     for p in result.admission.placements},
        'alternative_paths': {c: sorted({digest(geometry(p)) for p in r.alternatives}) for c, r in result.paths.items()},
        'known_ambiguous_intervals': by_src({source(s): v for s, v in result.admission.ambiguous_intervals.items() if v}),
    }


def differences(draft, full):
    if draft.keys() != full.keys():
        raise ValueError('different comparison schema')
    result = {}
    for kind, old in draft.items():
        new = full[kind]
        changed = sorted(k for k in old.keys() & new.keys() if old[k] != new[k])
        lost, gained = sorted(old.keys() - new.keys()), sorted(new.keys() - old.keys())
        result[kind] = {'draft_sha256': digest(old), 'full_sha256': digest(new), 'draft_keys': len(old),
                        'full_keys': len(new), 'draft_only_keys': len(lost), 'full_only_keys': len(gained),
                        'changed_common_keys': len(changed), 'different_key_digest': digest([lost, gained, changed])}
    return result


def draft_facts(arm, seqs):
    try:
        result = admission.construct_q0(arm)
    except Q0EvidenceError as exc:
        if str(exc) != 'no chromosome has a trustworthy q0 path':
            raise
        return None
    return footprint(result, seqs)


def run(root, panel, expected_ready):
    ready = prep.load_verified_evidence(root)
    data = load_panel(root, panel, ready)
    if data.ready_manifest_identity != expected_ready:
        raise ValueError('wrong full archive')
    tasks = data.catalog['supplementary_alignments']
    native = {t['paf'] for t in tasks if t['kind'] != 'regional_discovery'}
    if len(tasks) != len({t['paf'] for t in tasks}):
        raise ValueError('duplicate supplemental tasks')
    seqs = {source(s): v for s, v in data.sources.items()}
    base = draft_facts(subset_input(data, set()), seqs)
    native_draft = draft_facts(subset_input(data, native), seqs) if native else base
    full = footprint(admission.construct_q0(data), seqs)
    if prep.load_verified_evidence(root) != ready:
        raise ValueError('archive changed')

    def compare(arm):
        return {'status': 'no_trustworthy_path'} if arm is None else {'status': 'draft_only', 'fields': differences(arm, full)}

    return {'schema': 'q0_draft_consumer_comparison_v1', 'panel': panel['panel'], 'ready': expected_ready,
            'regional_windows': len(tasks) - len(native), 'native_tasks': len(native), 'base_only': compare(base),
            'native_plus_base': compare(native_draft), 'full_sequences': len(full['sequence']), 'new_mapper_executions': 0}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'panel', 'output'):
        p.add_argument(name, type=Path)
    p.add_argument('--ready', required=True); p.add_argument('--panel-sha', required=True)
    a = p.parse_args(); root = a.root.resolve(strict=True); raw = a.panel.read_bytes()
    if sha256(raw).hexdigest() != a.panel_sha or a.output.resolve().is_relative_to(root) or a.output.exists():
        raise ValueError('invalid isolated output or panel binding')
    result = run(root, json.loads(raw), a.ready)
    with a.output.open('x') as f:
        json.dump(result, f, indent=2, sort_keys=True); f.write('\n')
