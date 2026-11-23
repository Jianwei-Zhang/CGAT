"""Measure exact shared vs node-local FASTA reads, including copying and checking.

Read only pre-existing archived inputs and committed receipts. Both arms keep
the tool, guard, flags, worker count and shared output placement the same. The
two original guarded commands must each reproduce complete historical stdout.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

from benchmark_regional_thread_split import GIB, GUARD_SHA, digest, load_cases, stamp, within

WINDOWS = 8
WORKERS = 2
THREADS = 2
CPU_BUDGET = 6


def _signature(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def _inputs(case):
    names = tuple(Path(p) for p in case.stages[0].argv[THREADS-1][-2:])
    if (tuple(p.name for p in names) != ('target.fa', 'query.fa')
            or not all(s.argv[THREADS-1][-2:] == tuple(map(str, names)) for s in case.stages)):
        raise ValueError('coarse and precise must share the exact bound inputs')
    return names


def stage_inputs(inputs, directory, signatures, digests):
    """Copy a bounded complete pair; never accept a changed archive source."""
    copies = tuple(directory/p.name for p in inputs)
    for source, dest in zip(inputs, copies):
        expected = signatures[source]
        if expected[2] > 110*1024**2 or stamp(source) != expected:
            raise ValueError('original archived input changed or exceeds budget')
        checksum = hashlib.sha256()
        with source.open('rb') as incoming, dest.open('xb') as outgoing:
            if _signature(os.fstat(incoming.fileno())) != expected:
                raise ValueError('archive identity changed before local staging')
            for chunk in iter(lambda: incoming.read(1024*1024), b''):
                checksum.update(chunk)
                outgoing.write(chunk)
            if _signature(os.fstat(incoming.fileno())) != expected:
                raise ValueError('archive identity changed during local staging')
        if (stamp(source) != expected or dest.stat().st_size != expected[2]
                or checksum.hexdigest() != digests[source] or digest(dest) != digests[source]):
            raise ValueError('archived input changed or local copy differs from original receipt')
    return copies


def _mount_type(path):
    return subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE', '-T', str(path)], text=True).strip()


def run_arm(out, cases, signatures, digests, guard, scratch=None):
    out.mkdir()

    def run(index, case):
        dest = out/str(index)
        dest.mkdir()
        initial = _inputs(case)
        local = (tempfile.TemporaryDirectory(prefix='window-', dir=scratch)
                 if scratch is not None else nullcontext())
        with local as directory:
            start = time.monotonic()
            inputs = stage_inputs(initial, Path(directory), signatures, digests) if directory else initial
            copy_seconds = time.monotonic() - start if directory else 0.0
            frames = {path:stamp(path) for path in inputs} if directory else {p:signatures[p] for p in inputs}
            rows = []
            for stage in case.stages:
                argv = [sys.executable, str(guard), '--address-space-bytes', str(4*GIB), '--',
                        *stage.argv[THREADS-1][:-2], *map(str, inputs)]
                began = time.monotonic()
                output = dest/(stage.kind+'.paf')
                with output.open('xb') as stdout, (dest/(stage.kind+'.err')).open('xb') as stderr:
                    subprocess.run(argv, cwd=dest, stdout=stdout, stderr=stderr, check=True)
                native = time.monotonic() - began
                if digest(output) != stage.expected_sha256:
                    raise ValueError(f'{stage.kind} {index}: full PAF differs from original')
                if any(stamp(path) != signature for path, signature in frames.items()):
                    raise ValueError('mapper inputs changed during execution')
                rows.append({'stage':stage.kind, 'process_seconds':native,
                             'verification_seconds':time.monotonic()-began-native,
                             'sha256':stage.expected_sha256})
            return {'input_bytes':sum(signatures[p][2] for p in initial), 'copy_seconds':copy_seconds,
                    'window_seconds':time.monotonic()-start, 'stages':rows}

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        jobs = [pool.submit(run,i,c) for i,c in enumerate(cases)]
        rows = [f.result() for f in jobs]
    return {'mode':'staged_local' if scratch else 'shared', 'seconds':time.monotonic()-start,
            'copy_seconds_sum':sum(r['copy_seconds'] for r in rows), 'cases':rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'archive', 'package', 'output', 'scratch'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    work, archive, package, out = (p.resolve() for p in (args.workspace,args.archive,args.package,args.output))
    if any(out.is_relative_to(p) or p.is_relative_to(out) for p in (work,archive,package)):
        raise ValueError('diagnostic output must be isolated from inputs and live workspace')
    scratch_parent = args.scratch.resolve(strict=True)
    if not scratch_parent.is_relative_to(Path('/tmp').resolve(strict=True)) or scratch_parent.stat().st_uid != os.getuid():
        raise ValueError('scratch must be a private job-owned directory under /tmp')
    if scratch_parent.stat().st_mode & 0o077:
        raise ValueError('scratch directory permissions are not private')
    guard = within(package, 'lgz_core/q0_mapper_guard.py')
    if digest(guard) != GUARD_SHA:
        raise ValueError('guard not identical to historical commands')
    if len(os.sched_getaffinity(0)) < CPU_BUDGET:
        raise ValueError('requires at least six allocated cores')
    digests = {}
    cases, signatures, nbytes = load_cases(work,archive,WINDOWS, input_digests=digests)
    signatures[guard] = stamp(guard)
    out.mkdir()
    with tempfile.TemporaryDirectory(prefix='cgat-regional-local-io-', dir=scratch_parent) as staging:
        scratch = Path(staging)
        fstype = _mount_type(scratch)
        if (fstype not in {'xfs','ext4','ext3','btrfs','tmpfs'} or scratch.stat().st_dev == out.stat().st_dev):
            raise ValueError('scratch is not a recognised, separate node-local filesystem')
        cap = os.statvfs(scratch)
        if cap.f_bavail*cap.f_frsize < WORKERS*220*1024**2:
            raise ValueError('node-local scratch free space too low for guarded experiment')
        print(json.dumps({'phase':'inputs_verified', 'windows':len(cases),'input_bytes':nbytes,
                          'scratch_fstype':fstype,'archive_fstype':_mount_type(archive),
                          'shared_output_fstype':_mount_type(out)}), flush=True)
        result = []
        for i,storage in enumerate((None,scratch,scratch,None)):
            arm = run_arm(out/f'phase-{i}', cases, signatures, digests, guard, scratch=storage)
            if any(stamp(p) != s for p,s in signatures.items()):
                raise ValueError('a frozen artifact changed after a phase')
            print(json.dumps({k:v for k,v in arm.items() if k!='cases'}), flush=True)
            result.append(arm)
        if any(digest(p) != h or stamp(p) != signatures[p] for p,h in digests.items()):
            raise ValueError('original archived FASTA does not match the bound source bytes after the experiment')
    with (out/'report.json').open('x') as f:
        json.dump({'status':'exact_regional_local_input_abba', 'node':socket.gethostname(),
                   'stdout_matches_both_original_commands':True, 'scratch_fstype':fstype,
                   'workspace_modified':False, 'windows':len(cases), 'input_bytes':nbytes,
                   'workers':WORKERS, 'threads_per_mapper':THREADS, 'phases':result,
                   'isolates':'coarse/precise input placement, including staging; not producer/preflight/pipeline'},
                  f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
