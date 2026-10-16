#!/usr/bin/env python3
"""Review retained raw comparison failures without rerunning or changing a runtime.

Generated component IDs depend on run_id. Candidate IDs can depend on alignment
line numbers. Resolve each reference to its complete retained semantic object;
never delete arbitrary IDs, waive DNA checks, or overwrite the original report.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import re
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class References:
    def __init__(self, root, raw_events, validator):
        self.candidates = {}
        self.components = {}
        self.event_rows = {}
        events = validator.events(raw_events)
        self.resolved = {}
        self.resolving = set()
        self.event_resolving = set()
        for stage in ('step2', 'step3'):
            path = root / 'grt/evidence' / stage / 'candidates.tsv'
            if path.exists():
                with path.open() as handle:
                    for row in csv.DictReader(handle, delimiter='\t'):
                        key = row['candidate_id']
                        if key in self.candidates and self.candidates[key] != row:
                            raise ValueError('Ambiguous candidate reference: ' + key)
                        self.candidates[key] = row
        for event in events:
            if event.get('action') == 'filter_component':
                # Keep all scientific event fields, including retained/removed intervals.
                item = dict(event)
                key = item.pop('object_id')
                value = 'component-semantic-' + digest(item)
                if key in self.components and self.components[key] != value:
                    raise ValueError('Ambiguous component reference: ' + key)
                self.components[key] = value

        for event in raw_events:
            key = event.get("event_id")
            if key:
                self.event_rows[key] = validator.events([event])[0]

    def candidate(self, key):
        if key in self.resolved:
            return self.resolved[key]
        if key in self.resolving or key not in self.candidates:
            raise ValueError('Unresolved or cyclic candidate reference: ' + key)
        self.resolving.add(key)
        # Preserve source/target intervals, orientation, decisions, scores, and all
        # other candidate fields. Only generated IDs and raw alignment line indices
        # are omitted from the referenced object's semantic identity.
        trace = {'candidate_id', 'event_id', 'final_path_segment_id', 'left_line', 'right_line'}
        item = {k: self.normalize(v) for k, v in self.candidates[key].items() if k not in trace}
        self.resolved[key] = 'candidate-semantic-' + digest(item)
        self.resolving.remove(key)
        return self.resolved[key]

    def normalize(self, value):
        if isinstance(value, dict):
            return {k: self.normalize(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [self.normalize(v) for v in value]
        if isinstance(value, str):
            if value in self.components:
                return self.components[value]
            value = re.sub(r'step[23]-candidate-[0-9a-f]+', lambda m: self.candidate(m.group()), value)
            def event_reference(match):
                key = match.group()
                if key not in self.event_rows or key in self.event_resolving:
                    raise ValueError('Unresolved or cyclic event reference: ' + key)
                self.event_resolving.add(key)
                resolved = 'event-semantic-' + digest(self.normalize(self.event_rows[key]))
                self.event_resolving.remove(key)
                return resolved
            return re.sub(r'event-[0-9a-f]+', event_reference, value)
        return value


def review(case, validator):
    raw = json.loads((case / 'report.json').read_text())
    if raw['status'] in ('RUNNING', 'ERROR'):
        raise ValueError('Only completed comparisons can be reviewed')
    old_root, new_root = Path(raw['old_results']), case / 'optimized'
    stages = {}
    for stage in ('step2', 'step3'):
        stages[stage] = [json.loads((root / 'grt/evidence' / stage / 'result.json').read_text())
                         for root in (old_root, new_root)]
    refs = [References(root, [event for pair in stages.values()
                            for event in pair[index]['events']], validator)
            for index, root in enumerate((old_root, new_root))]
    checks = []
    def check(label, values, category, references=None):
        normalized = [ref.normalize(value) for ref, value in zip(references or refs, values)]
        normalized = [sorted(value, key=lambda x: json.dumps(x, sort_keys=True)) for value in normalized]
        checks.append({'label': label, 'category': category,
                       'status': 'PASS' if normalized[0] == normalized[1] else 'FAIL',
                       'expected_sha256': digest(normalized[0]), 'observed_sha256': digest(normalized[1])})
    for stage, pair in stages.items():
        for accepted in (False, True):
            check(stage + (' accepted events' if accepted else ' events'),
                  [validator.events([e for e in r['events'] if not accepted or e.get('status') == 'accepted'])
                   for r in pair], 'core' if accepted else 'audit')
        fields = ('donor_set_id', 'source_dataset', 'source_contig', 'source_start', 'source_end', 'stage', 'status', 'reason')
        check(stage + ' consumed donor usage',
              [validator.selected([r for r in result['usage_rows'] if r.get('status') == 'consumed'], fields)
               for result in pair], 'core')
        fields = ('chr', 'object_id', 'stage', 'status', 'reason', 'candidate_count')
        check(stage + ' attempts', [validator.selected(result['attempts'], fields) for result in pair], 'audit')
    old_final = Path(raw['old_final'])
    finalized = []
    final_refs = []
    for root in (old_final, new_root):
        events = [json.loads(line) for line in (root / 'metadata/grt_events.jsonl').read_text().splitlines() if line]
        final_refs.append(References(root, events, validator))
        finalized.append(validator.events([e for e in events if e.get('stage') in ('step2', 'step3') and e.get('status') == 'accepted']))
    check('finalized accepted repairs', finalized, 'core', final_refs)
    reviewed = {c['label']: c for c in checks}
    # Every unreviewed original core gate (DNA, ordered path, Final Path, export,
    # strategy, classification, etc.) must still pass. Raw failures stay retained.
    core_failures = [c['label'] for c in raw['checks'] if c['category'] == 'core'
                     and reviewed.get(c['label'], c)['status'] != 'PASS']
    remaining_audit = [c['label'] for c in raw['checks'] if c['category'] == 'audit'
                       and reviewed.get(c['label'], c)['status'] != 'PASS']
    return {'case': str(case), 'raw_status': raw['status'],
            'raw_report_sha256': hashlib.sha256((case / 'report.json').read_bytes()).hexdigest(),
            'review_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'validator_sha256': hashlib.sha256(Path(validator.__file__).read_bytes()).hexdigest(),
            'status': 'FAIL' if core_failures else 'CORE_PASS_AUDIT_DIFFERENT' if remaining_audit else 'PASS',
            'core_failures': core_failures, 'remaining_audit_differences': remaining_audit,
            'checks': checks, 'resolved_candidate_references': [len(ref.resolved) for ref in refs],
            'boundary': 'Metadata-only semantic reference resolution. Original reports unchanged; no runtime or baseline rerun. Raw alignment line numbers and generated IDs are trace fields, not scientific coordinates. Not permission to enable Step2 gap-screen.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--validator', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('validator', args.validator)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    result = review(args.case, validator)
    # Never overwrite the primary report or an existing review evidence file.
    with args.output.open('x') as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(args.case.name, result['status'], result['core_failures'], result['remaining_audit_differences'])


if __name__ == '__main__':
    main()
