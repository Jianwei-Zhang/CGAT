"""Cumulative automatic refinement patch; immutable versions, not edits to the working path.

Reuse each committed schema-5 Light payload as its independently verifiable view.
Store identical files once. The only added sequence files are the admitted patch
sources, never a copy of the original datasets, reads, or a tool's final genome.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

from lgz_app_package import load_display_source_cards, project_final_path, validate_source_locators
from refinement_bundle import MANIFEST
from refinement_bundle_validate import validate_payload
from refinement_commit import PublicationError, current_publication, layout_and_lock, read_json, targets
from refinement_delivery import _extract
from refinement_reports import safe_file
from refinement_tools import fingerprint
from run_orchestration import sha256_file
from workspace_layout import TOOL_DIRECTORIES
from workspace_migration import durable_json, ensure_directory, sync_directories

SCHEMA = 'cgat.project-auto-refinement-patch'
INDEX = 'auto_refinement.json'
RECEIPT = '.runtime/refinement/project-delivery/auto-patch.json'


def _checked(path, expected):
    if path.is_symlink() or not path.is_file() or sha256_file(path) != expected:
        raise PublicationError(f'automatic patch input changed or is unavailable: {path}')
    return path


def _published(layout):
    rows = {}
    for tool in TOOL_DIRECTORIES:
        proof = current_publication(layout.root, tool, verify=False)
        if proof is None:
            continue
        paths = targets(layout, tool)
        files = proof['areas']['delivery']['new']['files']
        definition = read_json(_checked(paths['delivery']/'delivery.json', files['delivery.json']))
        if layout.project_delivery:
            manifest = 'light/' + MANIFEST
            if (definition.get('schema') != 'cgat.project-tool-projection' or definition['tool'] != tool
                    or definition['run_id'] != proof['run_id'] or files.get(manifest) != definition['light_manifest']):
                raise PublicationError('automatic patch got a mismatched project tool projection')
            _checked(paths['delivery']/manifest, files[manifest])
            rows[tool] = (proof, paths['delivery']/'light', files[manifest])
            continue
        light = definition['archives']['light']
        if (definition['tool'] != tool or definition['run_id'] != proof['run_id']
                or files.get(light['file']) != light['sha256']):
            raise PublicationError('automatic patch got a mismatched published Light archive')
        rows[tool] = (proof, _checked(safe_file(paths['delivery'], light['file']), light['sha256']), light['sha256'])
    return rows


def _put_object(archive, seen, path, expected):
    # The key names only bytes; no untrusted filesystem path is an archive destination.
    _checked(path, expected)
    if expected not in seen:
        archive.write(path, 'objects/' + expected)
        seen.add(expected)
    return expected


def _variant(layout, tool, row, baseline, archive, seen, temp):
    proof, light, _ = row
    final = targets(layout, tool)['final']
    files = proof['areas']['final']['new']['files']
    with _checked(final/'sources.tsv', files['sources.tsv']).open(newline='', encoding='utf-8') as handle:
        sources = list(csv.DictReader(handle, delimiter='\t'))
    payload = light if layout.project_delivery else _extract(light, temp)
    verified = validate_payload(payload, full=False)
    manifest_path = safe_file(payload, MANIFEST)
    manifest = read_json(manifest_path)
    if (verified['tool'] != tool or verified['run_id'] != proof['run_id'] or manifest['baseline'] != baseline
            or manifest['provenance_sha256'] != files['provenance.json']
            or manifest['server_final_path_sha256'] != files['final_path.json']):
        raise PublicationError(f'{tool}: automatic version does not match the LGZ baseline and committed result')
    for name, digest in manifest['files'].items():
        if name.lower().endswith(('.fa','.fasta','.fna','.fq','.fastq','.fa.gz','.fasta.gz','.fna.gz','.fq.gz','.fastq.gz')):
            raise PublicationError('sequence file in Light evidence: '+name)
        _put_object(archive, seen, safe_file(payload,name), digest)
    declared = {(r['dataset'], r['contig']): (r['fasta_sha256'], int(r['length'])) for r in manifest['sources']
                if r['origin'] == 'refinement:'+tool}
    retained = {}
    expected_path = layout.path(f"04_refinement/{TOOL_DIRECTORIES[tool]}/04_accepted/{proof['run_id']}/patches.fa")
    for source in sources:
        if source['origin'] == 'lgz':
            continue
        key = source['dataset'], source['contig']
        identity = source['fasta_sha256'], int(source['length'])
        if (source['origin'] != 'refinement:'+tool or source['path_scope'] != 'workspace'
                or layout.path(source['fasta_path']) != expected_path or key in retained or declared.get(key) != identity):
            raise PublicationError('automatic patch source is not a bound accepted sequence')
        retained[key] = identity
    if retained != declared:
        raise PublicationError('automatic patch source inventory is incomplete')
    added = sorted({digest for digest, _ in retained.values()})
    for digest in added:
        _checked(expected_path, digest)
        # Refuse an accepted-sources FASTA containing extra records. Read long
        # unwrapped patch chromosomes in bounded chunks, not one allocation per record.
        lengths, name, at_start = {}, None, True
        with expected_path.open('rb') as stream:
            while chunk := stream.readline(1024 * 1024):
                if at_start and chunk.startswith(b'>'):
                    if not chunk.endswith(b'\n'):
                        raise PublicationError('invalid accepted FASTA header')
                    name = chunk[1:].strip().decode('ascii')
                    if not name or name in lengths:
                        raise PublicationError('duplicate or empty accepted FASTA header')
                    lengths[name] = 0
                elif name is None:
                    raise PublicationError('sequence without an accepted FASTA header')
                else:
                    lengths[name] += len(chunk.rstrip(b'\r\n'))
                at_start = chunk.endswith(b'\n')
        if lengths != {contig: length for (_, contig),(sha,length) in retained.items() if sha == digest}:
            raise PublicationError('accepted FASTA contains unexpected or missing sequence')
        _put_object(archive, seen, expected_path, digest)
    return {'run_id': proof['run_id'], 'light_manifest': _put_object(archive, seen, manifest_path, sha256_file(manifest_path)),
            'accepted_sequence_objects': added}


def _build(layout, rows, baseline, source, destination, scratch):
    seen, variants = set(), {}
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, allowZip64=True, strict_timestamps=False) as archive:
        server_path = scratch/'server-base.json'
        server_path.write_bytes(json.dumps(read_json(source), sort_keys=True, separators=(',', ':')).encode())
        _put_object(archive, seen, server_path, baseline['final_path_sha256'])
        projected = scratch/'base.json'
        project_final_path(layout.root, source, projected, validate_source_locators(layout.root), load_display_source_cards(layout.root))
        app_base = _put_object(archive, seen, projected, sha256_file(projected))
        for tool, row in sorted(rows.items()):
            with tempfile.TemporaryDirectory(dir=scratch) as temp:
                variants[tool] = _variant(layout, tool, row, baseline, archive, seen, Path(temp))
        manifest = {'schema': SCHEMA, 'schema_version': 1, 'baseline': baseline,
                    'baseline_app_path': app_base, 'variants': variants}
        archive.writestr(INDEX, json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())
    # Read the actual ZIP, not only the input tree; CRC, bytes and exact inventory.
    with zipfile.ZipFile(destination) as check:
        if (len(check.infolist()) != len(seen)+1 or set(check.namelist()) != {INDEX} | {'objects/'+s for s in seen}
                or json.loads(check.read(INDEX)) != manifest):
            raise PublicationError('automatic patch archive inventory mismatch')
        for sha in seen:
            digest = hashlib.sha256()
            with check.open('objects/'+sha) as item:
                for block in iter(lambda: item.read(1024*1024), b''):
                    digest.update(block)
            if digest.hexdigest() != sha:
                raise PublicationError('automatic patch archive object changed')


def patch_path(layout):
    if layout.project_delivery:
        # First prepare privately; only the project-generation transaction may expose it.
        return layout.path('.runtime/refinement/project-delivery/prepared.auto.patch.zip')
    return layout.path(f'07_delivery/{layout.result_prefix}.auto.patch.zip')


def publish_auto_patch(root, lock):
    layout = layout_and_lock(root, lock)
    if not layout.result_prefix:
        return None
    target = patch_path(layout)
    owner = layout.path(RECEIPT)
    state = read_json(owner) if owner.exists() or owner.is_symlink() else {}
    rows = _published(layout)
    if not rows:
        if state or target.exists() or target.is_symlink():
            raise PublicationError('found an automatic patch without its tool publications')
        return None
    baseline_proof = read_json(layout.path('.runtime/refinement/lgz_baseline.json'))
    source = _checked(layout.path('metadata/grt_final_path.json'), baseline_proof['binding']['final_path_sha256'])
    if baseline_proof.get('state') != 'committed':
        raise PublicationError('automatic patch requires a committed LGZ baseline')
    # Server scientific identity hashes canonical JSON; the durable baseline receipt above hashes the file bytes.
    baseline = {'final_path_sha256': fingerprint(read_json(source)), 'assembly_sha256': baseline_proof['binding']['assembly_sha256']}
    key = fingerprint({'schema': SCHEMA, 'version': 1, 'baseline': baseline,
                       'tools': {t:[r[0]['run_id'],r[0]['areas']['final']['new']['files'],r[2]] for t,r in rows.items()}})
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise PublicationError('automatic patch is not a regular file')
    actual = sha256_file(target) if target.exists() else None
    if actual is not None and (not state or actual not in (state.get('previous'),state.get('sha256'))):
        raise PublicationError('refusing to replace an unowned or modified automatic patch')
    if actual is not None and actual == state.get('sha256') and state.get('generation') == key:
        if 'previous' in state:
            durable_json(owner, {'generation':key,'sha256':actual})
        return actual
    ensure_directory(target.parent)
    ensure_directory(owner.parent)
    with tempfile.TemporaryDirectory(dir=owner.parent) as scratch, tempfile.TemporaryDirectory(dir=target.parent, prefix='.auto-') as pending:
        staged = Path(pending)/'patch.zip'
        _build(layout, rows, baseline, source, staged, Path(scratch))
        sha = sha256_file(staged)
        with staged.open('rb') as stream:
            os.fsync(stream.fileno())
        durable_json(owner, {'generation':key, 'previous':actual, 'sha256':sha})
        if actual is None:
            os.link(staged,target)
        else:
            _checked(target,actual)
            os.replace(staged,target)
        sync_directories(target.parent)
        durable_json(owner, {'generation':key, 'sha256':sha})
        return sha


def validate_auto_patch(layout, expected):
    owner = layout.path(RECEIPT)
    target = patch_path(layout)
    if expected is None:
        if owner.exists() or owner.is_symlink() or target.exists() or target.is_symlink():
            raise PublicationError('unexpected automatic patch in a baseline-only receipt')
    else:
        proof = read_json(owner)
        if 'previous' in proof or proof.get('sha256') != expected:
            raise PublicationError('incomplete or outdated automatic patch receipt')
        _checked(target, expected)
