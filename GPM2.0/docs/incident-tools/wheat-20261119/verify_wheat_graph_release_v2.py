"""Two-phase release of the frozen wheat 44e274a7 first-request graph only.

Review existing immutable measurements once. At graph launch verify the sealed
review and the newly available placement checkpoint. Does not alter historical
results, publish Q0, accept arbitrary FAILED jobs, or change scientific policy.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

REV = '44e274a715308e3d15598832947b83aa32b88450'
SNAP = '1ca1582715d7b2eef8d7d007db6825d04b77d2c513ddd7ae073efff690e14d66'
AUDIT = 'cf792cf1da2caadf62936b71a785f17dbf3c370b1e0fba00acae92ec0c0310bc'
GEOMETRY = 'dcb222f0cccd82c95ddbd8bfb9b058ff7be1d530affe43d98bdcd72150ce9e16'
GEOM_TERMINAL = '8e4da64d1b10cbb13d815d5510046f6768a24f080b218b3eb287df81b56af3d7'
DELTA = {'field':'diagnostics.policy.maximum_coverage_boundaries','old':200000,'new':None}
CASES = {'forward','reverse','touching','disjoint','shared_evidence','required_endpoints',
         'consistent_cycle','inconsistent_cycle','past_200000'}


def need(ok, why):
    if not ok:
        raise ValueError('wheat graph not released: ' + why)


def regular(path):
    need(path.resolve() == path and path.is_file(), 'missing or linked: ' + str(path))
    return path


def digest(path):
    h = hashlib.sha256()
    with regular(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def document(path, expected=None):
    raw = regular(path).read_bytes()
    if expected is not None:
        need(hashlib.sha256(raw).hexdigest() == expected, str(path))
    return json.loads(raw.decode('utf-8'))


def check_4d(c, baseline, diff, projection):
    """Only omit the independently attested old/new cap from path comparison."""
    need(c['revision'] == projection['revision'] == diff['revision'] == REV and
         diff['baseline'] == baseline['revision'], '4D comparison revision')
    need(all(c[k] == baseline[k] for k in ('bp','members','chromosome','matrix_bytes','ref_records',
                                             'request_sources','request_intervals')), '4D input/request inventory')
    a, b = c['scientific'], baseline['scientific']
    need(a.keys() == b.keys() and a['has_path'] is True and c['chromosome'] in a['sequences'] and
         all(a[k] == b[k] for k in b if k != 'paths'), 'non-path scientific fields')
    need(diff['different'] == ['paths'] and diff['equal'] is False and diff['raw_request_equal'] is True,
         'not the audited raw comparison outcome')
    paths = projection['paths']; need(paths.keys() == a['paths'].keys() == b['paths'].keys() and paths,
                                      'chromosome inventory')
    for chrom, row in paths.items():
        need(row['raw'] == a['paths'][chrom] and row['with_old_diagnostic_only'] == row['reference'] == b['paths'][chrom],
             'unexplained path difference on ' + chrom)
    return len(paths)


def speed_report(candidate, baseline):
    def seconds(obj):
        s = obj.get('timing', {}).get('draft_s')
        return s if type(s) in (int,float) and math.isfinite(s) and s > 0 else None
    a,b = seconds(candidate),seconds(baseline)
    return dict(draft_s=a, baseline_s=b, status=('unavailable' if None in (a,b) else
                                                'slower' if a > b else 'not_slower'), gate=False)


def review(root, audit_path):
    q = root/'qualification'; g = q/'geometry'; base = root.parent/'q0-4d-pair-lanes.Nf85nm'
    need((root/'latest.rev').read_text().strip() == REV and digest(root/'control/snapshot.json') == SNAP, 'run identity')
    a = document(audit_path, AUDIT)
    need(a['schema'] == 'wheat_4d_metadata_delta_audit_v1' and a['revision'] == REV and a['job'] == '43058370'
         and a['original_state'] == 'FAILED' and a['changed_diagnostic'] == DELTA, 'unapproved failure or policy change')
    # The original non-releasing audit pins the producing runtime, the logger that changed only
    # the diagnostic in a COPY, the terminal receipt and the unmodified outputs. Check them once.
    json_needed = {q/'candidate.json', base/'candidate.json', q/'comparison.json', q/'cap-diagnostic-audit.json'}
    docs = {}
    for name, pin in a['evidence'].items():
        rel = Path(name); need(not rel.is_absolute() and '..' not in rel.parts, 'invalid audit member')
        path = root.parent/rel
        if path in json_needed:
            docs[path] = document(path,pin)
        else:
            need(digest(path) == pin, 'audit member drift: ' + name)
    c, b = docs[q/'candidate.json'], docs[base/'candidate.json']
    n = check_4d(c, b, docs[q/'comparison.json'], docs[q/'cap-diagnostic-audit.json'])
    need(a['verified_paths'] == n, '4D attestation inventory')
    # Fixed audit contains both raw request digests. No separate hard-coded window or member quota.
    pins = a['evidence']; key = lambda path: str(path.relative_to(root.parent))
    need(pins[key(q/'4d-first-request.json')] == pins[key(base/'4d-first-request.json')], 'different raw request')
    review_g = document(g/'review.json', GEOMETRY); term, = document(g/'terminal.json', GEOM_TERMINAL)['data']['successData']
    need(review_g['snapshot_sha256'] == SNAP and review_g['revision'] == REV and str(term['jobId']) == review_g['job']
         and term['state'] == 'SUCCEEDED' and Path(term['execPath']) == g and
         digest(g/'latest.tgz') == pins[key(root/'latest.tgz')], 'geometry job/runtime')
    rows = review_g['cases'];need(len(rows) == len(CASES) and {r['name'] for r in rows} == CASES,'geometry case inventory')
    for row in rows:
        name = row['name']
        for arm in ('candidate','reference'):
            need(digest(g/(name+'.'+arm+'.json')) == row[arm+'_sha256'], 'geometry drift: '+name)
        # The immutable prior review already checked semantic equality; do not compare JSON formatting.
    return dict(schema='wheat_first_request_science_release_v2', revision=REV, snapshot_sha256=SNAP,
                accepted=True, original_4d_job=a['job'], original_4d_state=a['original_state'],
                allowed_diagnostic=DELTA, checked_paths=n, request_intervals=c['request_intervals'],
                geometry_cases=len(rows), audit_sha256=AUDIT, geometry_review_sha256=GEOMETRY,
                performance=speed_report(c,b), scope='science_only_placement_required')


def placement_ready(root, receipt):
    need(receipt['schema'] == 'wheat_first_request_science_release_v2' and receipt['accepted'] is True and
         receipt['scope'] == 'science_only_placement_required' and receipt['revision'] == REV and
         receipt['snapshot_sha256'] == SNAP and receipt['audit_sha256'] == AUDIT and
         receipt['geometry_review_sha256'] == GEOMETRY, 'wrong sealed review')
    p = document(root/'placement/control/placement-complete.json'); expected = p['admission_sha256']
    need(p['revision'] == REV and p['snapshot_sha256'] == SNAP and p['stage'] == 'global_placement_only'
         and p['published_q0'] is False and isinstance(expected,str) and re.fullmatch('[a-f0-9]{64}', expected), 'placement receipt')
    # Bind the future full stream verification in Store.load() to this specific placement receipt;
    # no second full scan of the potentially large placement list in the launch gate.
    with regular(root/'selection/admission.jsonl').open('rb') as f:
        size = f.seek(0, 2); f.seek(max(0, size-256)); lines = f.read().splitlines()
    need(len(lines) >= 2, 'missing checkpoint trailer')
    tag,count,value = json.loads(lines[-1].decode('ascii'))
    need(tag == 'end' and type(count) is int and count >= 0 and value == expected, 'wrong checkpoint trailer')
    return count


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('phase', choices=('review','start'))
    args=ap.parse_args();root=Path.cwd();audit=Path.home()/'cgat-reads-debug/logs/4d-policy-audit-43058370-20261125/audit.json'
    if args.phase == 'review':
        print(json.dumps(review(root,audit), sort_keys=True, indent=2, allow_nan=False))
    else:
        # The submitted scheduler script verifies the digest of this receipt before entering here.
        count=placement_ready(root, document(root/'gate-v2/science-review.json'))
        print('GRAPH_RELEASE_V2_READY',REV,'restorable_placements',count,flush=True)
