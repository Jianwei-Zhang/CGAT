"""Isolated full 4D experiment. No ready manifest, production writes or subsetting by winners."""
from collections import Counter, defaultdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
import sys
from time import monotonic
from unittest.mock import patch

from lgz_core import q0_admission as adm, q0_preparation as prep, q0_threshold_prepare as threshold
from lgz_core.common import reverse_complement
from lgz_core.q0_threshold_questions import questions
from lgz_core.q0_threshold_acceptance import record

GROUP = '4D'
REV = '44e274a715308e3d15598832947b83aa32b88450'
REFERENCE = '2916252571014e63f9fbfd47e898d82027ab651df7eec8af5edd52e0be73c442'
LOOKUP = '2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sealed(p, expected):
    raw = p.read_bytes()
    need(sha256(raw).hexdigest() == expected, 'input changed: '+str(p))
    return json.loads(raw)


def write(p, value):
    with p.open('x') as f:
        json.dump(value, f, sort_keys=True, allow_nan=False); f.write('\n')


def load(work, lookup):
    class Loaded(Exception):
        pass
    def intercept(data, **options):
        raise Loaded(data)
    meta = json.loads((work/'group.json').read_bytes())
    seqs = prep._dataset_sequences(work, meta['ds'])
    inventory = {(v['dataset'], v['contig']): v for v in sealed(lookup, LOOKUP).values()}
    for s, seq in seqs.items():
        v = inventory[s.dataset,s.contig]
        need(sha256(seq.encode()).hexdigest() == v['sequence_sha256'] and len(seq) == v['length'], 'source content drift')
    need(len(seqs) == meta['n'] == 766 and sum(map(len, seqs.values())) == meta['bp'] == 1074672025, 'not the complete frozen 4D input')
    try:
        with patch.object(adm, 'select_request_paths', intercept):
            threshold.initial_questions(work, seqs, meta['refs'], meta['assign'], meta['matrices'], threads=8)
    except Loaded as result:
        data, = result.args
        need(len(data.pair_links) == 1212752 and len(data.parts) == 766, 'wrong frozen matrix inputs')
        return data, meta
    raise ValueError('input capture never reached selector')


def save_layout(out, label, paths, data):
    """Write reconstructable source geometry and actual FASTA, checking occupancy across records."""
    occupied = defaultdict(list); kinds = Counter(); records = []; total = ns = gap_bp = 0
    with gzip.open(out/(label+'.fa.gz'), 'xb', compresslevel=1) as fa:
        for n, path in enumerate(paths, 1):
            need(path.chromosome == GROUP and len(path.slices)==len(path.joins)+1, 'invalid scaffold')
            digest=sha256(); bases=0; slices=[]; joins=[]; fa.write(f'>{GROUP}_{n}\n'.encode())
            def emit(seq):
                nonlocal total, ns, bases
                raw=seq.encode(); fa.write(raw+b'\n'); digest.update(raw); total+=len(raw); bases+=len(raw); ns+=seq.upper().count('N')
            def occupy(s, interval):
                need(interval.end<=len(data.sources[s]) and not any(interval.intersection(o) for o in occupied[s]), 'source reused or out of range')
                occupied[s].append(interval)
            for i,item in enumerate(path.slices):
                s=item.source; span=item.interval; occupy(s,span); need(item.orientation in ('+','-'), 'invalid strand')
                piece=data.sources[s][span.start:span.end]; emit(piece if item.orientation=='+' else reverse_complement(piece))
                slices.append([s.dataset,s.contig,span.start,span.end,item.orientation])
                if i<len(path.joins):
                    j=path.joins[i]; need((j.left_id,j.right_id)==(item.placement_id,path.slices[i+1].placement_id) and j.evidence_ids,'unbound junction')
                    if j.kind=='input_assembly_gap':
                        a=j.gap_interval; occupy(j.gap_source,a); need(set(data.sources[j.gap_source][a.start:a.end].upper())=={'N'} and a.length==j.n_bp,'invalid original gap')
                    kinds[j.kind]+=1; gap_bp+=j.n_bp
                    if j.n_bp: emit('N'*j.n_bp)
                    joins.append([j.kind,j.left_end,j.right_start,j.n_bp,list(j.evidence_ids)])
            records.append(dict(sha256=digest.hexdigest(),bp=bases,slices=slices,joins=joins))
    used=sum(v.length for spans in occupied.values() for v in spans)
    write(out/(label+'.layout.json'),records)
    return dict(scaffolds=len(records),slices=sum(len(r['slices']) for r in records),sequence_bp=total,sequence_n_bp=ns,
                join_gap_bp=gap_bp,join_kinds=dict(kinds),source_bp_used=used,group_source_bp_not_used_on_4D=sum(map(len,data.sources.values()))-used,
                record_hashes=[r['sha256'] for r in records])


def main(mode, work, base, out):
    out.mkdir(exist_ok=False); start=monotonic()
    data, meta=load(work,base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json'); loaded=monotonic()
    common=dict(group=GROUP,members=meta['n'],source_bp=meta['bp'],pair_rows=len(data.pair_links),load_s=loaded-start,
                input_runtime=REV,formal_q0=False)
    if mode=='A':
        selection=adm.select_request_paths(data, screen_threads=8,progress=lambda m: print(m,flush=True)); req,_=questions(data,selection,meta['assign'])
        current=selection.paths[GROUP].path; need(current is not None,'unusable frozen group control')
        result=save_layout(out,'A',[current],data); end=monotonic()
        archive=base/('q0-request-ready.'+REV[:8])/'qualification'; ref=sealed(archive/'candidate.json',REFERENCE)
        need(result['record_hashes']==[ref['scientific']['sequences'][GROUP]] and record(req)==json.loads((archive/'4d-first-request.json').read_bytes()), 'A does not reproduce frozen 4D sequence/request')
        write(out/'A.json',dict(common,arm='current initial-evidence selection; not post-supplement truth',metrics=result,from_input_s=end-start,mapper_calls=0))
    elif mode=='BC':
        from pilot_fast_group_selector import trial
        trial(data, out, common, start)
    else: raise ValueError('unknown arm')

if __name__=='__main__':
    main(sys.argv[1], *map(Path,sys.argv[2:]))
