"""Publish direct FASTAs from sealed publications, never from a tool's native output.

The public name and the assembly in details share data blocks. Each public entry
has a write-ahead ownership record; recovery may finish an interrupted replacement
but must not replace an unrelated file. The TSV (with sequence hashes) is last.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
from pathlib import Path
import tempfile

from refinement_commit import PublicationError, current_publication, layout_and_lock, read_json
from run_orchestration import sha256_file
from workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout
from workspace_migration import durable_json, ensure_directory, sync_directories

COLUMNS = ('version', 'attempt', 'attempt_status', 'published_status', 'accepted_edits', 'fasta', 'sha256', 'publication')
OWNERS = '.runtime/refinement/final_catalog'


def _regular(path):
    if path.is_symlink() or not path.is_file():
        raise PublicationError(f'missing or non-regular job result: {path}')
    return path


def _inspect_entry(layout, name, expected, source):
    target = layout.path('05_final/' + name)
    owner = layout.path(f'{OWNERS}/{name}.json')
    state = read_json(owner) if owner.exists() or owner.is_symlink() else {}
    exists = target.exists() or target.is_symlink()
    shared = exists and source is not None and not target.is_symlink() and target.samefile(source)
    actual = (expected if shared else sha256_file(_regular(target))) if exists else None
    if exists and (not state or actual not in (state.get('previous'), state.get('next'))):
        raise PublicationError(f'refusing to replace unowned or modified job result: {target}')
    return target, owner, state, exists, actual, shared


def _owned_entry(layout, name, expected, *, source=None, contents=None):
    target, owner, state, exists, actual, shared = _inspect_entry(layout, name, expected, source)
    ensure_directory(owner.parent)
    ensure_directory(target.parent)
    committed = {'next': expected}
    if exists and actual == expected and (source is None or shared):
        if state != committed:
            durable_json(owner, committed)
        return
    # Publish data before the index; failure is retryable with the same inputs or
    # a new attempt. A hard link is intentional: no duplicate chromosome payload.
    with tempfile.TemporaryDirectory(prefix='.publish-', dir=target.parent) as tmp:
        staged = Path(tmp) / 'entry'
        if source is not None:
            os.link(source, staged)
        else:
            with staged.open('xb') as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
        durable_json(owner, {'previous': actual, 'next': expected})
        if exists:
            os.replace(staged, target)
        else:
            os.link(staged, target)  # exclusive create; never adopt a racing unrelated file
        sync_directories(target.parent)
        durable_json(owner, committed)


def publish_catalog(root, lock, attempt, attempts, *, baseline_status='published'):
    layout = layout_and_lock(root, lock)
    if layout.result_prefix is None:
        return None
    if set(attempts) - TOOL_DIRECTORIES.keys():
        raise PublicationError('unknown automatic result in job catalog')
    rows, entries = [], []
    for tool in ('lgz', *TOOL_DIRECTORIES):
        status = baseline_status if tool == 'lgz' else attempts.get(tool, {}).get('status', 'not_requested')
        home = layout.path('05_final/' + ('00_lgz' if tool == 'lgz' else TOOL_DIRECTORIES[tool]))
        files = None
        if tool == 'lgz':
            pointer = layout.path('.runtime/refinement/lgz_baseline.json')
            if pointer.exists() or pointer.is_symlink():
                proof = read_json(pointer)
                if proof.get('state') != 'committed' or proof.get('schema') != 'cgat.lgz-baseline-publication':
                    raise PublicationError('LGZ publication is not committed')
                files, publication = proof['files']['files'], proof['binding']['final_path_sha256']
        else:
            proof = current_publication(root, tool, verify=False)
            if proof is not None:
                files, publication = proof['areas']['final']['new']['files'], proof['transaction']
                if status == 'published' and attempts[tool].get('publication_transaction') != publication:
                    raise PublicationError('job catalog tool does not match the attempted publication')
        row = [tool, attempt, status, '', '', '', '', '']
        if files is not None:
            source, provenance = _regular(home / 'assembly.fa'), _regular(home / 'provenance.json')
            if sha256_file(source) != files['assembly.fa'] or sha256_file(provenance) != files['provenance.json']:
                raise PublicationError(f'{tool} direct result does not match its publication receipt')
            prov = read_json(provenance)
            if prov['tool'] != tool:
                raise PublicationError('job catalog provenance tool mismatch')
            name = f'{layout.result_prefix}.{tool}.fa'
            entries.append((name, files['assembly.fa'], source))
            row[3:] = [prov['status'], 0 if tool == 'lgz' else prov['accepted_edit_count'], name, files['assembly.fa'], publication]
        elif status == 'published':
            raise PublicationError(f'missing committed publication for {tool}')
        elif tool != 'lgz' and tool not in attempts:
            continue
        rows.append(row)
    buf = io.StringIO(newline='')
    writer = csv.writer(buf, delimiter='\t', lineterminator='\n')
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    data = buf.getvalue().encode('utf-8')
    digest = hashlib.sha256(data).hexdigest()
    # Do not advance any public name if another entry (including the TSV) is
    # already known to be unowned or modified. Recheck at each replace as well.
    for name, sha, source in entries:
        _inspect_entry(layout, name, sha, source)
    _inspect_entry(layout, 'results.tsv', digest, None)
    for name, sha, source in entries:
        _owned_entry(layout, name, sha, source=source)
    _owned_entry(layout, 'results.tsv', digest, contents=data)
    return digest


def validate_catalog(layout, expected):
    path = _regular(layout.path('05_final/results.tsv'))
    if not expected or sha256_file(path) != expected:
        raise PublicationError('job results.tsv changed after completion')
    with path.open(encoding='utf-8', newline='') as stream:
        rows = csv.DictReader(stream, delimiter='\t')
        if rows.fieldnames != list(COLUMNS):
            raise PublicationError('unexpected job catalog columns')
        for row in rows:
            if not row['fasta']:
                continue
            if row['version'] not in ('lgz', *TOOL_DIRECTORIES) or row['fasta'] != f"{layout.result_prefix}.{row['version']}.fa":
                raise PublicationError('invalid job catalog FASTA name')
            if sha256_file(_regular(layout.path('05_final/' + row['fasta']))) != row['sha256']:
                raise PublicationError(f"job FASTA changed after completion: {row['fasta']}")


def record_early_failure(root, lock, attempt, exit_code):
    # Never relabel a successful or recoverable publication because a later phase failed.
    if exit_code:
        layout = WorkspaceLayout.detect(root)
        baseline = layout.path('.runtime/refinement/lgz_baseline.json')
        if layout.result_prefix and not (baseline.exists() or baseline.is_symlink()):
            publish_catalog(root, lock, attempt, {}, baseline_status='failed_before_publication')
    return exit_code
