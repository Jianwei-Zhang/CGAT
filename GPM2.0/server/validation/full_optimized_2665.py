#!/usr/bin/env python3
"""NEW-only, cold complete-input end-to-end run, retaining the original parameters."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import time
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def table(path):
    with path.open() as handle:
        return list(csv.DictReader(handle, delimiter='\t'))


def final_path(path):
    document = json.loads(path.read_text())
    return [{'chr': c['chr'], 'q4_length': c['q4_length'], 'q4_sha256': c['q4_sha256'],
             'segments': [{k: s.get(k) for k in ('kind', 'length', 'orientation', 'source')}
                          for s in c['segments']]} for c in document['chromosomes']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--case', choices=('skip-self', 'self-m200-n100'), required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    old_root = Path('/share/home/xbzhang26/cgat-reads-debug/gpm2665-full-input')
    old = old_root / 'workspaces' / args.case
    golden = old_root.parent / 'grt-execution-equivalence/customer-core-080599a3/baseline'
    workspace = root / 'workspaces' / args.case
    report_file = root / 'reports' / (args.case + '.json')
    assert platform.machine() == 'x86_64', 'Same-architecture comparison required'
    assert not workspace.exists(), 'Fresh run only: never overwrite/resume an existing workspace'
    assert not report_file.exists(), 'Do not overwrite previous evidence'
    archive = root / 'gpm-full-optimized-6cc768d.tar.gz'
    assert sha(archive) == 'd7718ee3ccedc73471da27a18249d505ffa579bf2d3ef09c5a36119d4f8da49b'
    saved = json.loads((old / '.run_all/launch.json').read_text())
    original = saved['argv']
    assert original.count('--out') == 1
    argv = list(original)
    argv[argv.index('--out') + 1] = str(workspace)
    assert not any(x in argv for x in ('--grt-execution-profile', '--grt-step3-mummer-scope', '--step2-mummer-scope'))
    argv += ['--grt-execution-profile', 'optimized', '--grt-step3-mummer-scope', 'gap-screen']
    assert original[original.index('--threads') + 1] == '16'
    assert ('--skip-self' in original) == (args.case == 'skip-self')
    if args.case == 'self-m200-n100':
        assert original[original.index('--self-m') + 1] == '200'
        assert original[original.index('--self-n') + 1] == '100'
    # Exactly the previous input paths, names/order, thresholds and options.
    inputs = []
    for path, identity in saved['inputs'].items():
        p = Path(path); st = p.stat()
        assert st.st_size == identity['size'] and st.st_mtime_ns == identity['mtime_ns'], path
        inputs.append({'path': path, 'size': st.st_size, 'sha256': sha(p)})
    source = root / 'source/server'
    tools = {}
    for name in ('python3', 'minimap2', 'nucmer', 'delta-filter', 'show-coords', 'samtools', 'pigz'):
        path = shutil.which(name)
        assert path is not None, name
        tools[name] = {'resolved': str(Path(path).resolve()), 'sha256': sha(Path(path))}
    command = ['bash', str(source / 'run.sh'), *argv]
    report = {'status': 'RUNNING', 'case': args.case, 'threads': 16,
              'source_revision': '6cc768d864dc2a541964dce080f0f8d938018938',
              'source_archive_sha256': sha(archive), 'hostname': platform.node(),
              'architecture': platform.machine(), 'original_job': 40550762 if args.case == 'skip-self' else 40550763,
              'original_argv': original, 'new_command': command, 'inputs': inputs, 'tools': tools,
              'cache_mode': 'numerical-cold',
              'boundary': 'Complete data and NEW workflow from assignment/reference alignment through final Full/Light packaging. No old runtime rerun, upstream checkpoint or numerical cache borrowing. Same x86 tools and 16-CPU budget; different nodes/OS cache affect timings. Preflight hashing and postchecks excluded from workflow wall time.',
              'golden_results': str(golden), 'checks': []}
    def save():
        tmp = report_file.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        tmp.replace(report_file)
    def check(label, expected, observed):
        report['checks'].append({'label': label, 'status': 'PASS' if expected == observed else 'FAIL',
                                 'expected': expected, 'observed': observed})
    save()
    (root / 'reports' / (args.case + '-command.sh')).write_text(shlex.join(command) + '\n')
    started = time.monotonic()
    with (root / 'logs' / (args.case + '-pipeline.log')).open('x') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    report['workflow_seconds'] = time.monotonic() - started
    report['pipeline_exit'] = result.returncode
    save()
    if result.returncode:
        report['status'] = 'PIPELINE_FAILED'; save(); raise SystemExit(result.returncode)
    options = {r['key']: r['value'] for r in table(workspace / 'metadata/prepare_options.tsv')}
    for key, value in {'threads': '16', 'grt_execution_profile': 'optimized',
                       'grt_step2_mummer_scope': 'full', 'grt_step3_mummer_scope': 'gap-screen'}.items():
        check(key, value, options.get(key))
    report['stage_timings'] = table(workspace / 'logs/status.tsv')
    check('all full workflow units successful', True, bool(report['stage_timings']) and all(r['state'] == 'success' for r in report['stage_timings']))
    for stage in ('step2', 'step3'):
        cp = json.loads((workspace / f'grt/checkpoints/{stage}.json').read_text())
        check(stage + ' actual optimized execution', 'optimized', cp['fingerprint_payload']['execution_profile'])
        check(stage + ' actual scope', 'full' if stage == 'step2' else 'gap-screen', cp['fingerprint_payload']['mummer_scope'])
    for q in ('q2', 'q3', 'q4'):
        check(q + ' vs retained golden DNA file', sha(golden / 'grt/q' / (q + '.fa')), sha(workspace / 'grt/q' / (q + '.fa')))
    check('Final Path source intervals orientation order kinds and DNA', final_path(golden / 'metadata/grt_final_path.json'), final_path(workspace / 'metadata/grt_final_path.json'))
    report['refill_batches'] = [json.loads(p.read_text()) for p in (workspace / 'grt/evidence/step3/refill').glob('*/batch/provenance.json')]
    for suffix in ('.tar.gz', '.light.tar.gz'):
        p = workspace.parent / (workspace.name + suffix)
        check('delivery present ' + suffix, True, p.is_file() and p.stat().st_size > 0)
    report['status'] = 'PASS' if all(c['status'] == 'PASS' for c in report['checks']) else 'COMPARISON_FAILED'
    save()
    print('FULL_OPTIMIZED_RESULT', report['status'], report['workflow_seconds'], flush=True)
    if report['status'] != 'PASS': raise SystemExit(1)


if __name__ == '__main__':
    main()
