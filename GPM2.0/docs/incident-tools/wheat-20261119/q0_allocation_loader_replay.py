"""Bound archive parity on the actual x86 allocation before any handoff.

The prior smoke still proves the staged production writer/reader. This replay
adds fresh, guarded native parity when only the inherited search string drifted;
changing a selected executable or any resolved library is not eligible.
"""
import os
from pathlib import Path

from benchmark_regional_thread_split import GUARD_SHA, digest, load_cases, run_phase, stamp

ARCHIVE = 'q0-native-dispatch-control-20261122-110235'


def replay_archive(root, work, env):
    from lgz_core import q0_regional_mapping as mapping

    # Tools use the same ownership, guard and two threads as the original
    # commands. Run only one frozen complete pair on the assigned node.
    root = root.resolve(strict=True)
    work = work.resolve(strict=True)
    archive = root.parent / ARCHIVE
    candidate_guard = Path(mapping.__file__).with_name('q0_mapper_guard.py')
    expected_env = dict(os.environ)
    removed = expected_env.pop('LD_LIBRARY_PATH', None)
    if not removed or env != expected_env:
        raise ValueError('same-node archive replay requires the verified child-only environment')
    if (archive.is_symlink() or not archive.is_dir() or archive.resolve() != archive
            or root.is_relative_to(work) or archive.is_relative_to(work)
            or candidate_guard.is_symlink() or digest(candidate_guard) != GUARD_SHA):
        raise ValueError('allocation replay inputs differ from the guarded archive')
    cases, signatures, source_bytes = load_cases(work, archive, 1)
    if len(cases) != 1 or not 0 < source_bytes <= 128 * 1024**2:
        raise ValueError('unexpected or unbounded allocation replay archive')
    expected = {s.kind: s.expected_sha256 for s in cases[0].stages}
    if len(cases[0].stages) != 2 or set(expected) != {'chaining', 'precise'}:
        raise ValueError('same-node proof needs both original phases')
    signatures[candidate_guard] = stamp(candidate_guard)
    out = root / 'allocation-loader-archive-replay'
    out.mkdir(mode=0o700)
    observed = run_phase(out / 'verified_child', cases, candidate_guard, 2, 1, child_env=env)
    rows = observed['rows']
    got = {row['stage']: row['sha256'] for row in rows[0][1]} if len(rows) == 1 and rows[0][0] == 0 else {}
    if got != expected or len(rows[0][1]) != 2:
        raise ValueError('allocation-native full stdout failed archive parity')
    if any(stamp(path) != before for path, before in signatures.items()) or digest(candidate_guard) != GUARD_SHA:
        raise ValueError('allocation replay inputs changed during execution')
    return {'archived_raw_receipt': cases[0].receipt, 'archive_input_bytes': source_bytes,
            'paf_sha256': got, 'seconds': observed['seconds']}
