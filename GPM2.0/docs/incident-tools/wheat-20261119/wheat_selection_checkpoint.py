"""Private, same-revision wheat first-request checkpoints; never an accepted Q0.

Re-stage and verify frozen PAFs/metadata on each attempt. Only deterministic
placement and ranked chromosome prefixes are reused, in original order.
"""
from contextlib import contextmanager
from dataclasses import fields
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from lgz_core.q0_admission import RequestAdmission
from lgz_core.q0_paths import Join, Placement, ReferenceAnchor, RequestPathResult, Slice, _ScoredPath
from lgz_core.q0_sources import Interval, SourceKey

TYPES = {t.__name__: t for t in (Placement, ReferenceAnchor, RequestPathResult, _ScoredPath, Join, Slice, Interval, SourceKey)}


def need(ok, text):
    if not ok:
        raise ValueError('selection checkpoint: ' + text)


def encode(v):
    t = type(v)
    if TYPES.get(t.__name__) is t:
        return {t.__name__: [encode(getattr(v, f.name)) for f in fields(v)]}
    if t is tuple:
        return [encode(x) for x in v]
    need(v is None or t in (str, int, bool), 'unexpected field')
    return v


def decode(v):
    if type(v) is list:
        return tuple(map(decode, v))
    if type(v) is dict:
        (key, args), = v.items()
        t = TYPES[key]
        need(type(args) is list and len(args) == len(fields(t)), 'invalid field count')
        return t(*map(decode, args))
    need(v is None or type(v) in (str, int, bool), 'unexpected scalar')
    return v


def line(v):
    return (json.dumps(v, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


class PlacementSaved(Exception):
    """End of the explicitly placement-only phase, not a first-request result."""


class Store:
    def __init__(self, folder, binding, placement_only):
        self.folder, self.binding, self.placement_only = folder, binding, placement_only
        self.previous = ''

    def _header(self, name, chromosome):
        return ['wheat_first_request_checkpoint_v1', self.binding, name, chromosome, self.previous]

    def save(self, name, chromosome, rows):
        header = self._header(name, chromosome)
        with NamedTemporaryFile(dir=self.folder, prefix='.partial-') as out:
            digest = sha256(); n = 0
            def put(value):
                raw = line(value); digest.update(raw); out.write(raw)
            put(header)
            for r in rows:
                put(encode(r)); n += 1
            value = digest.hexdigest()
            out.write(line(['end', n, value])); out.flush(); os.fsync(out.fileno())
            os.link(out.name, self.folder / name)  # atomic no-overwrite publication
            d = os.open(self.folder, os.O_DIRECTORY)
            try:
                os.fsync(d)
            finally:
                os.close(d)
        self.previous = value
        print('SELECTION_CHECKPOINT_SAVED', name, chromosome, n, value, flush=True)

    def load(self, name, chromosome, cls):
        path = self.folder / name
        if not os.path.lexists(path):
            return None
        need(path.resolve() == path and path.is_file(), 'linked or non-file checkpoint')
        with path.open('rb') as f:
            head = f.readline(); need(json.loads(head) == self._header(name, chromosome), 'wrong input, prefix or role')
            digest = sha256(head); rows = []
            for raw in f:
                value = json.loads(raw)
                if isinstance(value, list) and value[:1] == ['end']:
                    need(value == ['end', len(rows), digest.hexdigest()] and not f.read(1), 'invalid content digest or trailer')
                    self.previous = digest.hexdigest()
                    print('SELECTION_CHECKPOINT_RESTORED', name, chromosome, len(rows), self.previous, flush=True)
                    return rows
                digest.update(raw); obj = decode(value)
                need(type(obj) is cls, 'wrong record class'); rows.append(obj)
        raise ValueError('incomplete selection checkpoint: ' + name)

    def load_admission(self):
        rows = self.load('admission.jsonl', None, Placement)
        return None if rows is None else RequestAdmission(tuple(rows))

    def save_admission(self, a):
        need(isinstance(a, RequestAdmission), 'not a first-request admission')
        self.save('admission.jsonl', None, a.placements)

    def after_admission(self):
        if self.placement_only:
            raise PlacementSaved(self.previous)

    def load_group(self, index, chromosome):
        rows = self.load(f'group-{index:03}.jsonl', chromosome, RequestPathResult)
        if rows is None:
            return None
        row, = rows
        need(row.path is None or row.path.chromosome == chromosome, 'wrong chromosome winner')
        return row

    def save_group(self, index, chromosome, search):
        self.save(f'group-{index:03}.jsonl', chromosome, (search,))


@contextmanager
def opened(folder, ctrl, snapshot, revision, threads, placement_only):
    base = Path.home()/'cgat-reads-debug/jm19-compare-614589f-20261118'
    stage = base / ('q0-request-ready.' + revision[:8]); folder = Path(folder)
    need(re.fullmatch('[0-9a-f]{40}', revision) and folder == stage/'selection' and folder.resolve() == folder
         and ctrl.resolve() == ctrl and stage in ctrl.parents and (stage/'latest.rev').read_text().strip() == revision,
         'wrong incident scope')
    folder.mkdir(mode=0o700, exist_ok=True)
    need(folder.is_dir() and folder.stat().st_uid == os.getuid() and not folder.stat().st_mode & 0o077, 'not private')
    binding = [snapshot, revision, threads] + [sha256(p.read_bytes()).hexdigest() for p in
               (stage/'latest.tgz', Path(__file__), stage/'fork_wheat_q0.py')]
    with (folder/'writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield Store(folder, binding, placement_only)
