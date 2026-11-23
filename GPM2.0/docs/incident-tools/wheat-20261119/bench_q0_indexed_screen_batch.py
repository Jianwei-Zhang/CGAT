"""Diagnostic strong-scaling trial on a predeclared bounded slice of the existing wheat reference index.

Same in-memory data for each arm. No derived FASTA, mapper, ready or production checkpoint.
"""
from contextlib import ExitStack, closing
from pathlib import Path
import json
import sqlite3
import sys

from bench_q0_source_screen_pool import adm, measure
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_retained_hits import RetainedHit
from lgz_core.q0_sources import SourceKey, split_source

DATASETS = ('JM19_flye_ABD', 'JM19_hifiasm')
CACHE = 'reference-index-fdad41a395b84a35a2176f31'


def require(value, message):
    if not value:
        raise ValueError(message)


def checked_path(root, rel):
    path = Path(rel)
    require(not path.is_absolute() and path.parts and '..' not in path.parts, 'invalid sample path')
    p = root/path
    require(p.resolve(strict=True) == p and p.is_file(), 'linked or missing sample input')
    return p


def signature(path):
    s = path.stat(); return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def choose(index):
    # No timing, results, annotation, or PAF hit count is consulted when choosing sources.
    names = sorted(k for k,v in index.items() if 1_000_000 <= v[0] <= 2_400_000)
    require(len(names) >= 16, 'insufficient length-stratum population')
    return [names[(2*i+1)*len(names)//32] for i in range(16)]


def fetch_dna(handle, row):
    n, offset, width, stride = row
    require(0 < n <= 2_400_000 and offset >= 0 and 0 < width <= stride <= width+2, 'invalid FAI')
    size = n+(n-1)//width*(stride-width)
    require(size <= 3*n, 'unbounded FAI extent')
    handle.seek(offset); raw=handle.read(size); dna=raw.replace(b'\n',b'').replace(b'\r',b'').decode('ascii')
    require(len(raw)==size and len(dna)==n, 'incomplete original FASTA extent')
    return dna, size


def load(root):
    paths = {}
    def source(rel):
        p=checked_path(root,rel); stamp=signature(p)
        require(paths.setdefault(p,stamp)==stamp, 'scientific input changed'); return p
    idx='grt/evidence/q0_prepare/indexes/'+CACHE+'/'
    receipt=json.loads(source(idx+'success.json').read_text()); db=source(idx+'reference.sqlite')
    require(receipt['status']=='success' and receipt['key']==CACHE and receipt['size']==db.stat().st_size,'not sealed index')
    require(not any(Path(str(db)+s).exists() for s in ('-wal','-shm','-journal')), 'live database journal')
    seqs, parts, hits, edges, access = {}, {}, {}, [], {'fasta_bytes':0, 'paf_bytes':0, 'records':0}
    with ExitStack() as resources:
        conn=resources.enter_context(closing(sqlite3.connect(db.as_uri()+'?mode=ro&immutable=1',uri=True)))
        meta=dict(conn.execute('select name,value from metadata'))
        binding=json.loads(meta['bindings']); report=json.loads(meta['build_report'])
        require(meta['sealed']=='true' and report['reference_inputs']=={r['path']:{k:r[k] for k in ('size','sha256')} for r in receipt['inputs']},'wrong index input set')
        require(binding['minimum_reference_identity']==adm.AdmissionPolicy().minimum_reference_identity,'index identity gate differs')
        names=sorted({(row[1],row[2]) for row in binding['sources']}); ranks={v:i for i,v in enumerate(names)}
        lengths=dict(binding['references']); chromosomes=sorted(lengths)
        pafs=dict(conn.execute('select id,path from files')); handles={}
        require(set(pafs.values())=={f'runs/{d}_vs_ref/result.paf' for d in DATASETS},'unrecognized PAF set')
        for fid, rel in pafs.items():
            p=source(rel); require(p.stat().st_size==report['reference_inputs'][rel]['size'],'unexpected PAF size')
            handles[fid]=resources.enter_context(p.open('rb'))
        for dataset in DATASETS:
            fa=source('data/datasets/'+dataset+'.fa'); index={}
            for line in source('data/datasets/'+dataset+'.fa.fai').read_text().splitlines():
                name,*fields=line.split('\t');require(name not in index and len(fields)==4,'ambiguous index');index[name]=tuple(map(int,fields))
            fasta=resources.enter_context(fa.open('rb'))
            for name in choose(index):
                key=SourceKey(dataset,name); sid=ranks[dataset,name]; dna,extent=fetch_dna(fasta,index[name]);access['fasta_bytes']+=extent
                seqs[key]=dna; info=split_source(key,dna);parts.update((p.segment_id,p) for p in info.segments);edges.extend(info.adjacencies)
                records=[]
                sql='SELECT r.* FROM boxes b JOIN records r ON r.id=b.id WHERE b.slo<=? AND b.shi>=? AND r.source=? ORDER BY r.id LIMIT 65537'
                for _,src,ref,qs,qe,ts,te,fid,offset,size,line,digest in conn.execute(sql,(sid,sid,sid)):
                    require(src==sid and pafs[fid]==f'runs/{dataset}_vs_ref/result.paf' and 0<size<=4<<20 and 0<=offset<=report['reference_inputs'][pafs[fid]]['size']-size,'foreign or oversized PAF extent')
                    access['paf_bytes']+=size; access['records']+=1
                    require(access['paf_bytes']<=64<<20 and len(records)<65536,'bounded record budget exceeded')
                    infile=handles[fid]; infile.seek(offset); raw=infile.read(size);require(len(raw)==size,'short PAF extent')
                    h=parse_paf_line(raw.decode(),artifact=pafs[fid],line_number=line)
                    require(h.query_name==name and h.query_length==len(dna) and h.target_name==chromosomes[ref] and h.target_length==lengths[h.target_name] and (h.query.start,h.query.end,h.target.start,h.target.end)==(qs,qe,ts,te) and bytes.fromhex(h.record_sha256)==digest,'indexed record does not match original')
                    records.append(RetainedHit.from_validated(h,name,h.target_name))
                hits[key]=records
    require(all(signature(p)==sig for p,sig in paths.items()),'input changed during the read')
    return adm.EvidenceInput(seqs,parts,lengths,hits,(),tuple(edges),{},'bounded-reference-only-experiment'), access


def main(root):
    data,access=load(root); expected=None; trials=[]
    for cores in (1,2,4,8,8,4,2,1):
        out,row=measure(data,[],cores)
        if expected is None: expected=out
        else: require(out==expected,'decision changed under parallel reference screening')
        trials.append(row); print(f'completed {cores} cores in {row["seconds"]:.3f}s',file=sys.stderr,flush=True);del out
    return {'scope':'bounded reference-only workload; no assembly pair links or assignment demand, no mapper or whole-wheat Q0 conclusion',
            'selector':'16 names per dataset at sorted mid-quantiles among 1.0–2.4 Mb sources, chosen before reading hits', 'sources':len(data.sources),'parts':len(data.parts),'sequence_bp':sum(map(len,data.sources.values())), 'access':access,'trials':trials,'all_decisions_equal':True}


if __name__=='__main__': print(json.dumps(main(Path(sys.argv[1]).resolve(strict=True)),indent=2))
