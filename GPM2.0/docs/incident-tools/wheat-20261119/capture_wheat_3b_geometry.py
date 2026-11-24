"""Optional incident recorder. Its file is input for replay, never a Q0 checkpoint or a request."""
from contextlib import contextmanager
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import socket
from tempfile import NamedTemporaryFile
from unittest.mock import patch

REV = 'd08efdffd93decce7ec8761907c8cc54f4b215f8'
SNAP = '2552917a975e345d03095bc7d25a14353802e547fa84c5d41eac05cf0d73019c'
LIMIT = 64 << 20


def require(ok, why):
    if not ok:
        raise ValueError(why)


def small(p):
    require(p.resolve() == p and p.is_file() and p.stat().st_size <= 1 << 20, str(p))
    with p.open('rb') as f:
        raw = f.read((1 << 20) + 1)
    require(len(raw) <= 1 << 20, str(p))
    return raw


def provenance(ctrl, expected, runner, modules):
    home = Path.home()/'cgat-reads-debug/jm19-compare-614589f-20261118/q0-request-ready.d08efdff'
    require(ctrl == home/'control' and expected == SNAP and Path.cwd() == home, 'wrong recording workspace')
    snapshot, started, staged, allocation = (small(p) for p in
        (ctrl/'snapshot.json', ctrl/'started.json', ctrl/'staged.json', home/'allocation.json'))
    s, owner, copied = map(json.loads, (snapshot, started, staged))
    require(sha256(snapshot).hexdigest() == SNAP and s['revision'] == owner['revision'] == REV and
            owner['pid'] == os.getpid() and owner['source_run'] == s['source_run'] and
            owner['snapshot_sha256'] == copied['snapshot_sha256'] == SNAP and owner['workspace'] == copied['workspace'] and
            copied['complete_for'] == 'first_request_only', 'unexpected producer/staging identity')
    j, = json.loads(allocation)['data']['successData']; jid = small(home/'whole.jobid').decode().strip()
    require(re.fullmatch(r'[0-9]+', jid) and j['jobId'] == jid and j['state'] == 'RUNNING' and j['user'] == 'xbzhang26' and
            j['queue'] == 'x86' and j['execPath'] == str(home) and j['taskExecNodes'] == owner['hostname'] == copied['hostname'] == socket.gethostname() and
            re.search(r'(?<![0-9])'+jid+r'(?![0-9])', Path('/proc/self/cgroup').read_text()), 'unexpected allocation')
    code = {m.__name__.split('.')[-1]: sha256(small(Path(m.__file__))).hexdigest() for m in modules}
    require(code == {'q0_admission':'f59d90b2657850fa058d17c80bc561e26cb967f58f1779eb0cde9f95bdec2456',
                     'q0_paths':'82d887830c1ff292b7d991ff19244e2d39981f07850e2a811acf22b1b36f46cd',
                     'q0_coverage':'9f83b2d52c985e8101a5865493371b1383d188896662953cc6ff422e3afbaee0'}, 'different live graph code')
    return dict(revision=REV, snapshot_sha256=SNAP, job=jid, source_run=s['source_run'], graph_modules=code,
                started_sha256=sha256(started).hexdigest(), staged_sha256=sha256(staged).hexdigest(),
                allocation_sha256=sha256(allocation).hexdigest(), runner_sha256=sha256(small(runner)).hexdigest(),
                recorder_sha256=sha256(small(Path(__file__))).hexdigest())


def save(ctrl, header, required, relations):
    dest = ctrl/'3B-preliminary-geometry.jsonl.gz'
    require(not os.path.lexists(dest), 'geometry file already present; not replacing it')
    digest = sha256(); written = 0
    with NamedTemporaryFile(dir=ctrl, prefix='.3B-geometry-', suffix='.partial') as tmp:
        with gzip.GzipFile(filename='', mode='wb', fileobj=tmp, compresslevel=1, mtime=0) as out:
            def put(row, *, hashed=True):
                nonlocal written
                raw = (json.dumps(row, separators=(',', ':'), sort_keys=True)+'\n').encode(); written += len(raw)
                require(written <= LIMIT, 'geometry exceeds recorder limit')
                if hashed:
                    digest.update(raw)
                out.write(raw)
            put(dict(header, schema='wheat_preliminary_coverage_geometry_v1', chromosome='3B',
                     coordinates='0-based half-open, original source axes', compact_first=True, maximum_boundaries=200000,
                     sources=len(required), relations=len(relations)))
            for source, spans in required.items():
                put(['source', source.dataset, source.contig, len(spans)])
                for s in spans:
                    put(['required', s.start, s.end])
            for r in relations:  # pre-compaction order, including duplicates and original evidence IDs
                put(['map', r.left_source.dataset, r.left_source.contig, r.left.start, r.left.end,
                     r.right_source.dataset, r.right_source.contig, r.right.start, r.right.end, r.reverse, r.evidence_id])
            put(['end', digest.hexdigest()], hashed=False)
        tmp.flush(); os.fsync(tmp.fileno()); require(tmp.tell() <= LIMIT, 'compressed geometry exceeds limit')
        os.link(tmp.name, dest)  # publish once, only after the complete gzip stream is closed
    return digest.hexdigest()


@contextmanager
def observe(ctrl, expected, runner):
    from lgz_core import q0_admission as adm, q0_paths as paths, q0_coverage as cov
    original_graph, original_model = adm.PathGraph, paths.CoverageModel
    attempted = False

    def graph(placements, *args, **kw):
        if not kw.get('first_request') or not isinstance(placements, (list, tuple)) or not placements or placements[0].chromosome != '3B':
            return original_graph(placements, *args, **kw)

        def model(required, relations, **options):
            nonlocal attempted
            if not attempted:
                attempted = True  # record the initial global geometry, never its filtered rebuild
                try:
                    require(isinstance(relations, list) and options.get('compact_first') is True and
                            options.get('maximum_boundaries') == 200000, 'unexpected preliminary model')
                    digest = save(ctrl, provenance(ctrl, expected, runner, (adm, paths, cov)), required, relations)
                    print('CAPTURED_3B_GEOMETRY', digest, flush=True)
                except (OSError, ValueError, KeyError, TypeError, MemoryError) as exc:
                    print('3B_GEOMETRY_NOT_CAPTURED', str(exc), flush=True)
            return original_model(required, relations, **options)  # scientific errors must propagate unchanged

        with patch.object(paths, 'CoverageModel', model):
            return original_graph(placements, *args, **kw)

    with patch.object(adm, 'PathGraph', graph):
        yield
