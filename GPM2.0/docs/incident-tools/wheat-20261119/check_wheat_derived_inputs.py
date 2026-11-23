"""Hash-replay one frozen wheat parent input family; never opens a PAF or writes a workspace."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys

SNAP = '2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d'
UNIT, DATASET = 'q0_chr:Un', 'JM19_hifiasm'
BASE = 'runs/chr_Un/' + DATASET + '_vs_self'
PART = 'runs/chr_Un/datasets/' + DATASET + '.fa'


def require(value, message):
    if not value:
        raise ValueError(message)


def member(root, rel):
    p = Path(rel)
    require(p.parts and rel == p.as_posix() and not p.is_absolute() and '..' not in p.parts and '\\' not in rel, 'foreign member')
    path = root / p
    require(path.resolve(strict=True) == path and path.is_file(), 'linked or missing input')
    return path


def signature(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def bound(path, digest, limit=8 << 20):
    before = signature(path.stat())
    require(before[2] <= limit, 'oversized metadata')
    raw = path.read_bytes()
    require(len(raw) == before[2] and signature(path.stat()) == before and hashlib.sha256(raw).hexdigest() == digest,
            'metadata differs from frozen parent')
    return raw


def rows(raw):
    return csv.DictReader(io.StringIO(raw.decode('utf-8')), delimiter='\t')


def record_bytes(stream, entry):
    length, offset, line_bases, line_width = entry
    require(0 < length <= 32 << 20 and offset >= 0 and 0 < line_bases and line_bases <= line_width <= line_bases + 2,
            'invalid FASTA index row')
    extent = length + ((length - 1) // line_bases) * (line_width - line_bases)
    stream.seek(offset)
    raw = stream.read(extent)
    seq = raw.replace(b'\n', b'').replace(b'\r', b'')
    require(len(raw) == extent and len(seq) == length, 'invalid indexed FASTA geometry')
    return seq, extent


def replay(stream, ordered, batches, expected):
    hashes = {p: hashlib.sha256() for p in expected}
    sizes = dict.fromkeys(expected, 0)

    def emit(p, *chunks):
        for chunk in chunks:
            hashes[p].update(chunk)
            sizes[p] += len(chunk)

    by_name = {name: i for i, name in enumerate(sorted(n for n, _ in ordered), 1)}
    require(len(by_name) == len(ordered) > 1 and sum(v[0] for _, v in ordered) <= 32 << 20, 'pilot cap or duplicate source')
    entries = [(index, row['name'], row['length']) for index, batch in enumerate(batches) for row in batch['entries']]
    require(len(entries) == len(ordered) and batches and all(b['entries'] for b in batches), 'incomplete batch plan')
    width = max(9, len(str(len(by_name))))
    read_bytes = 0
    for (name, entry), (batch, alias, length) in zip(ordered, entries):
        prefix = ('gpm_pair_%0*d' % (width, by_name[name])).encode()
        q, t = prefix + b'b', prefix + b'a'
        require(q == alias.encode() and length == entry[0], 'batch inventory disagrees with original source')
        seq, count = record_bytes(stream, entry)
        read_bytes += count
        emit(PART, b'>', name, b'\n', seq, b'\n')
        emit(BASE + '/self_name_map.tsv', t, b'\t', name, b'\n', q, b'\t', name, b'\n')
        emit(BASE + '/self_target.fa', b'>', t, b'\n', seq, b'\n')
        emit(BASE + '/self_query.fa', b'>', q, b'\n', seq, b'\n')
        emit(BASE + '/batches/batch-%05d/query.fa' % batch, b'>', q, b'\n', seq, b'\n')
    for p, row in expected.items():
        require((sizes[p], hashes[p].hexdigest()) == (row['size'], row['sha256']), 'derived bytes disagree: ' + p)
    return read_bytes


def main(ctrl):
    s = json.loads(bound(member(ctrl, 'snapshot.json'), SNAP)); root = Path(s['source'])
    initial = {r['path']: r for r in s['files']}; pin, = [r for r in s['producer_checkpoints'] if r['unit'] == UNIT]
    receipt = json.loads(bound(member(ctrl, 'producer/' + Path(pin['checkpoint']).name), pin['sha256']))
    require(receipt['status'] == 'success' and receipt['unit_id'] == UNIT, 'wrong parent')
    inputs = {r['path']: r for r in receipt['input_payload']['inputs']}
    def metadata(rel, inventory):
        return bound(member(root, rel), inventory[rel]['sha256'])
    ds, = [r for r in rows(metadata('metadata/datasets.tsv', initial)) if r['dataset_name'] == DATASET]
    selected = {}
    for r in rows(metadata('metadata/chr_assignments.tsv', initial)):
        if r['dataset_name'] == DATASET and r['assigned_chr_name'] == 'Un':
            key = r['seq_name'].encode(); length = int(r['seq_length_bp'])
            require(key not in selected, 'duplicate assignment'); selected[key] = length
    ordered = []
    for line in metadata(ds['fai_relpath'], initial).splitlines():
        name, *cols = line.split(b'\t')
        if name in selected:
            entry = tuple(map(int, cols)); require(len(entry) == 4 and entry[0] == selected[name], 'FAI length mismatch'); ordered.append((name, entry))
    require({n for n, _ in ordered} == set(selected), 'unresolved source')
    batches = json.loads(metadata(BASE + '/self_batch_manifest.json', inputs))['batches']
    roles = {p: r for p, r in inputs.items() if p == PART or (p.startswith(BASE + '/') and (p.endswith('.fa') or p == BASE + '/self_name_map.tsv'))}
    names = {PART, BASE + '/self_name_map.tsv', BASE + '/self_target.fa', BASE + '/self_query.fa'}
    for i, batch in enumerate(batches):
        p = BASE + '/batches/batch-%05d/query.fa' % i
        require(Path(batch['query']) == root / p and inputs[p]['sha256'] == batch['query_sha256'], 'misdirected batch')
        names.add(p)
    require(set(roles) == names, 'incomplete or unexpected roles')
    source = member(root, ds['fasta_relpath']); before = signature(source.stat())
    require(before[2] == initial[ds['fasta_relpath']]['size'], 'source size changed')
    with source.open('rb') as stream:
        require(signature(os.fstat(stream.fileno())) == before, 'source replaced'); n = replay(stream, ordered, batches, roles)
    require(signature(source.stat()) == before, 'source changed during probe')
    return {'schema': 'wheat_parent_derived_input_probe_v1', 'snapshot_sha256': SNAP, 'unit': UNIT, 'dataset': DATASET,
            'parent_sha256': pin['sha256'], 'source_records': len(ordered), 'source_extent_bytes': n,
            'verified_derived_inputs': [roles[p] for p in sorted(roles)], 'verified_derived_bytes': sum(r['size'] for r in roles.values()),
            'mapper_calls': 0, 'limits': 'Digest-only replay from indexed source extents; no whole-source rehash, output materialization, checkpoint import or Q0 count.'}


if __name__ == '__main__':
    print(json.dumps(main(Path(sys.argv[1]).resolve(strict=True)), sort_keys=True, indent=2))
