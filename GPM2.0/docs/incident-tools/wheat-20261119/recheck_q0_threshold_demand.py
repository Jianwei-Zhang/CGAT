"""Recompute blind demand before opening the previous comparison. Re-run only changed cold draft arms."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from lgz_core import q0_admission as adm, q0_preparation as prep
from lgz_core.common import stable_id
from audit_q0_draft_consumers import digest as field_digest, footprint, source
from q0_threshold_questions import questions
from run_q0_threshold_holdout import arm, construct
from run_wheat_frontier_panel import base_input, digest, within


def demand_key(frontier):
    return None if frontier is None else stable_id('q0-threshold-request', [
        [asdict(s), [asdict(i) for i in v]] for s, v in sorted(frontier.items())])


def check(panel, panel_hash, scratch, mapper, mapper_hash, threads, old, old_hash):
    if (digest(mapper) != mapper_hash or digest(panel/'panel.json') != panel_hash or scratch.exists()
            or not scratch.is_relative_to('/tmp') or scratch.is_relative_to(panel)):
        raise ValueError('invalid isolated recheck')
    meta = json.loads((panel/'panel.json').read_text())
    if meta['panel'] != panel.name or any(digest(within(panel, k)) != v for k, v in meta['artifacts'].items()):
        raise ValueError('invalid panel inventory')
    data, assignments, desc = base_input(panel, meta)
    frontier, stats = questions(data, construct(data), assignments)
    expected = demand_key(frontier); print('BLIND_DEMAND', meta['panel'], expected, stats, flush=True)
    # The old report is only used for measurement, never passed to questions() or arm().
    if digest(old) != old_hash:
        raise ValueError('previous full comparator is unbound')
    prev = json.loads(old.read_text())
    if (prev['panel_sha256'], prev['mapper_sha256'], prev['threads'], prev['builder'], prev['selector']) != (
            panel_hash, mapper_hash, threads, prep.builder_identity(), adm.selector_identity()):
        raise ValueError('different panel, mapper, resources or selector')
    r = {'schema':'q0_blind_demand_recheck_v1', 'panel':meta['panel'], 'panel_sha256':panel_hash, 'previous_sha256':old_hash,
         'question_counts':stats, 'demand':expected, 'previous_demand':prev['draft']['request_digest']}
    if expected == r['previous_demand']:
        return {**r, 'outcome':'identical_request_previous_cold_measurement_applies', 'new_mapper_calls':0}
    scratch.mkdir(mode=0o700)
    built, record = arm(panel, meta, data, assignments, desc, scratch/'draft', mapper, threads, True)
    if record['request_digest'] != expected or digest(mapper) != mapper_hash:
        raise ValueError('blind demand or tool changed before dispatch')
    fields = None
    if built is not None and prev['fields'] is not None:
        seen = footprint(built, {source(s): seq for s, seq in data.sources.items()})
        if seen.keys() != prev['fields'].keys():
            raise ValueError('incompatible full comparator fields')
        fields = {k: field_digest(v) == prev['fields'][k]['full_sha256'] for k, v in seen.items()}
    return {**r, 'outcome':'cold_draft_measured', 'draft':record, 'full':prev['full'], 'draft_sequences':len(built.records) if built else 0,
            'matches_full_fields':fields, 'new_mapper_calls':sum(record['fresh_mapper_processes'].values())}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('panel', 'scratch', 'mapper', 'previous', 'out'):
        p.add_argument(name, type=Path)
    for name in ('panel-sha', 'mapper-sha', 'previous-sha'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--threads', type=int, choices=(2,4,6), required=True); a=p.parse_args(); out=a.out.resolve()
    if out.exists() or out.is_relative_to(a.panel.resolve()) or out.is_relative_to(a.scratch.resolve()):
        raise ValueError('output not isolated')
    r=check(a.panel.resolve(strict=True), a.panel_sha, a.scratch.resolve(), a.mapper.resolve(strict=True), a.mapper_sha,
            a.threads, a.previous.resolve(strict=True), a.previous_sha)
    with out.open('x') as f:
        json.dump(r,f,sort_keys=True,indent=2); f.write('\n')
