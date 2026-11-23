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
import re
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
    automatic_sha = hashlib.sha256(_encode(rows)).hexdigest()
    data = _encode(rows + _manual_rows(layout))
    digest = hashlib.sha256(data).hexdigest()
    # Do not advance any public name if another entry (including the TSV) is
    # already known to be unowned or modified. Recheck at each replace as well.
    for name, sha, source in entries:
        _inspect_entry(layout, name, sha, source)
    _inspect_entry(layout, 'results.tsv', digest, None)
    for name, sha, source in entries:
        _owned_entry(layout, name, sha, source=source)
    _owned_entry(layout, 'results.tsv', digest, contents=data)
    return automatic_sha


def _encode(rows):
    buf = io.StringIO(newline='')
    writer = csv.writer(buf, delimiter='\t', lineterminator='\n')
    writer.writerow(COLUMNS); writer.writerows(rows)
    return buf.getvalue().encode('utf-8')


def _manual_rows(layout):
    if not layout.project_delivery:
        return []
    from manual_genome import SCHEMA, names
    directory = layout.path('04_refinement/manual')
    if directory.is_symlink(): raise PublicationError('linked manual jobs directory')
    rows=[]
    for pointer in sorted(directory.glob('*/manual-delivery.json')):
        batch=pointer.parent.name
        if not re.fullmatch(r'[0-9a-f]{64}',batch) or pointer.parent.is_symlink(): raise PublicationError('invalid manual delivery location')
        receipt=read_json(pointer)
        if receipt.get('schema') != SCHEMA: continue  # earlier, local-only task; never infer a genome
        if receipt.get('batch')!=batch: raise PublicationError('mismatched manual genome batch')
        result=names(layout,batch)
        for k,p in result.items():
            if sha256_file(_regular(p))!=receipt['files'][k]: raise PublicationError('manual result changed: '+str(p))
        accepted=receipt['accepted']; tag='manual-'+batch[:16]
        rows.append([tag,batch,'published','accepted' if accepted else 'unchanged_from_export',str(accepted),result['fasta'].name,receipt['files']['fasta'],batch])
    return rows


def _read_catalog(layout,*,recover=False):
    path=_regular(layout.path('05_final/results.tsv'))
    owner=read_json(layout.path(OWNERS+'/results.tsv.json'))
    acceptable={owner.get('next')}
    if recover: acceptable.add(owner.get('previous'))
    if sha256_file(path) not in acceptable: raise PublicationError('job results.tsv differs from its ownership receipt')
    with path.open(encoding='utf-8',newline='') as stream:
        reader=csv.reader(stream,delimiter='\t')
        if next(reader,None)!=list(COLUMNS): raise PublicationError('unexpected job catalog columns')
        rows=list(reader)
    if any(len(r)!=len(COLUMNS) for r in rows): raise PublicationError('malformed job result row')
    automatic=[r for r in rows if not r[0].startswith('manual-')]
    if any(r[0] not in ('lgz',*TOOL_DIRECTORIES) for r in automatic): raise PublicationError('unknown automatic result')
    return automatic, [r for r in rows if r[0].startswith('manual-')]


def refresh_manual_catalog(layout):
    automatic,_=_read_catalog(layout,recover=True)
    data=_encode(automatic+_manual_rows(layout))
    _owned_entry(layout,'results.tsv',hashlib.sha256(data).hexdigest(),contents=data)


def validate_catalog(layout, expected):
    automatic,manual=_read_catalog(layout)
    if not expected or hashlib.sha256(_encode(automatic)).hexdigest()!=expected or manual!=_manual_rows(layout):
        raise PublicationError('job result catalog changed after publication')
    for version,_,_,_,_,file,sha,_ in automatic:
        if not file: continue
        if file!=f'{layout.result_prefix}.{version}.fa' or sha256_file(_regular(layout.path('05_final/'+file)))!=sha:
            raise PublicationError('invalid or changed direct genome: '+file)


def record_early_failure(root, lock, attempt, exit_code):
    # Never relabel a successful or recoverable publication because a later phase failed.
    if exit_code:
        layout = WorkspaceLayout.detect(root)
        baseline = layout.path('.runtime/refinement/lgz_baseline.json')
        if layout.result_prefix and not (baseline.exists() or baseline.is_symlink()):
            publish_catalog(root, lock, attempt, {}, baseline_status='failed_before_publication')
    return exit_code
