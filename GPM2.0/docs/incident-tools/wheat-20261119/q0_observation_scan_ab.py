"""Bounded same-process A/B for the initial PAF work-selection scan only."""
import hashlib
import json
from pathlib import Path
import resource
import socket
import sys
import tempfile
import time

from lgz_core.q0_alignments import read_paf, read_paf_observations
from lgz_core.q0_catalog import ObservedSourcePairs
from lgz_core.q0_sources import SourceKey

CAP = 8 * 1024**2
FLYE, HIFI = 'JM19_flye_ABD', 'JM19_hifiasm'
CASES = [('1B', FLYE, FLYE), ('2A', HIFI, HIFI), ('6B', FLYE, HIFI)]


def stamp(path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def scan(reader, path, qlen, tlen, query, target, compact):
    qkeys = {name: SourceKey(query, name) for name in qlen}
    tkeys = {name: SourceKey(target, name) for name in tlen}
    known = ObservedSourcePairs({**{key: qlen[name] for name,key in qkeys.items()},
                                **{key: tlen[name] for name,key in tkeys.items()}})
    before, cpu = time.monotonic(), time.process_time()
    rows = 0
    for hit in reader(path, query_lengths=qlen, target_lengths=tlen):
        if compact:
            a,b = qkeys[hit.query_name],tkeys[hit.target_name]
        else:
            a,b = SourceKey(query,hit.query_name), SourceKey(target,hit.target_name)
        known.observe_alignment(hit,a,b)
        rows += 1
    elapsed, used = time.monotonic()-before, time.process_time()-cpu
    payload = [sorted(((a.dataset,a.contig),(b.dataset,b.contig)) for a,b in known),
               sorted((key.dataset,key.contig,[(i.start,i.end) for i in spans]) for key,spans in known.cross_coverage.items())]
    return {'records': rows, 'pair_count': len(known), 'covered_source_count': len(payload[1]),
            'observation_sha256': hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest(),
            'wall_seconds': elapsed, 'cpu_seconds': used}


def main(root, out):
    root, out = root.resolve(strict=True), out.resolve()
    if out.is_relative_to(root) or Path.cwd().resolve().is_relative_to(root):
        raise ValueError('diagnostic must not write within the run workspace')
    result = []
    with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
        for chrom, target, query in CASES:
            stem = target+'_vs_'+('self' if query == target else query)
            rel = f'runs/chr_{chrom}/{stem}/result.paf'
            path = root/rel
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
                raise ValueError('linked external PAF')
            before = stamp(path)
            with path.open('rb') as f:
                raw = f.read(CAP+1)
            if len(raw) > CAP:
                raw = raw[:CAP].rsplit(b'\n',1)[0]+b'\n'
                if len(raw) > CAP:
                    raise ValueError('no complete line in bounded slice')
            if before != stamp(path):
                raise ValueError('underlying sample changed')
            sample = Path(tmp)/'sample.paf'
            sample.write_bytes(raw)
            qlen,tlen={},{}
            # The slice is a timing fixture: infer internally consistent lengths
            # from its headers, not from the full production FASTAs.
            for line in raw.decode('utf-8').splitlines():
                if not line.strip() or line.startswith('#'):
                    continue
                fields = line.split('\t')
                for lengths, idx in ((qlen,0), (tlen,5)):
                    name,n=fields[idx],int(fields[idx+1])
                    if lengths.setdefault(name,n) != n:
                        raise ValueError('inconsistent source length within timing slice')
            trials=[]
            for mode in 'ABBA':
                arm=scan(read_paf if mode=='A' else read_paf_observations,sample,qlen,tlen,query,target,mode=='B')
                trials.append({'mode':mode,**arm})
            if len({tuple(arm[key] for key in ('records','pair_count','covered_source_count','observation_sha256')) for arm in trials}) != 1:
                raise ValueError('observations differ')
            if query != target and trials[0]['covered_source_count'] == 0:
                raise ValueError('cross sample lacks qualifying coverage')
            result.append({'path':rel,'original_size':before[2],'sample_bytes':len(raw),
                           'sample_sha256':hashlib.sha256(raw).hexdigest(),'trials':trials})
    with out.open('x') as f:
        json.dump({'schema':'q0_initial_observation_scan_ab_v1','host':socket.gethostname(), 'python':sys.version,
                   'whole_cache_validated':False,'workspace_modified':False,'ran_mapper':False,
                   'measured':'isolated initial planning reads from local bounded slices; source lengths inferred from each slice',
                   'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, 'cases':result}, f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main(*map(Path,sys.argv[1:]))
