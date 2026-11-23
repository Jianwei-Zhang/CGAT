"""Compare one vs two strict matrix reads on frozen Q0 inputs; never run an aligner."""
import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from time import monotonic
from unittest.mock import patch

from lgz_core import q0_alignments as paf, q0_preparation as prep, q0_retained_hits as packed, q0_threshold_prepare as draft
from lgz_core.q0_catalog import ObservedSourcePairs
from lgz_core.q0_sources import SourceKey
from lgz_core.q0_threshold_acceptance import record
from compare_fused_draft_panels import digest
from probe_q0_threshold_heap import catalog, stamp


def check(ok, message):
    if not ok: raise ValueError(message)


def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()


def coverage(known):
    pairs = [[a.dataset,a.contig,b.dataset,b.contig] for a,b in sorted(known)]
    intervals = [[k.dataset,k.contig,[(v.start,v.end) for v in vals]] for k,vals in sorted(known.cross_coverage.items())]
    return hashlib.sha256(encoded([pairs,intervals])).hexdigest()


def compare(root, seq_lengths, descriptors, *, panel=None):
    sources = {SourceKey(d,k):n for d,dct in seq_lengths.items() for k,n in dct.items()}; results=[]
    for shared in ((False,True,True,False) if panel is None else (False,True)):
        counts=Counter(); original=paf.open_paf_text; matrix_names={row['paf'] for row in descriptors}
        def opened(path,**kw):
            rel=path.relative_to(root).as_posix()
            if rel in matrix_names: counts[rel]+=1
            return original(path,**kw)
        known=ObservedSourcePairs(sources); cache=draft._DraftMatrices(root) if shared else None
        names={d:packed.retained_names(v) for d,v in seq_lengths.items()}; rows=0; rowhash=hashlib.sha256()
        with ExitStack() as stack:
            stack.enter_context(patch.object(paf,'open_paf_text',opened)); stack.enter_context(patch.object(packed,'open_paf_text',opened)); start=monotonic()
            for row in descriptors:
                q,t,rel=row['query_dataset'],row['target_dataset'],row['paf']; args=dict(artifact=rel,query_lengths=seq_lengths[q],target_lengths=seq_lengths[t]); path=root/rel
                hits=(cache.observe(path,query_dataset=q,target_dataset=t,**args) if shared else paf.read_paf_observations(path,**args))
                for hit in hits:known.observe_alignment(hit,SourceKey(q,hit.query_name),SourceKey(t,hit.target_name))
            if panel is None:
                short=packed.retained_geometry_cache()
                if shared:cache.check_inventory(descriptors)
                for row in descriptors:
                    rel=row['paf'];hits=(cache.take(row) if shared else packed.read_retained_paf(root/rel,artifact=rel,query_names=names[row['query_dataset']],target_names=names[row['target_dataset']],short_geometry=short))
                    for hit in hits:rowhash.update(hit.evidence_id.encode());rows+=1
                demand=None
            else:
                seqs,refs,assignments=panel; req,has_path=draft.initial_questions(root,seqs,refs,assignments,descriptors,matrices=cache);demand={'request':record(req),'has_path':has_path}
            elapsed=monotonic()-start
        check(set(counts)==matrix_names and set(counts.values())==({1} if shared else {2}),'unexpected number of matrix parses')
        results.append({'shared':shared,'semantic_opens':sum(counts.values()),'seconds':elapsed,'coverage_sha256':coverage(known),'retained_rows':rows,'ordered_ids_sha256':rowhash.hexdigest() if panel is None else None,'first_request':demand})
    for r in results[1:]:
        check(all(r[k]==results[0][k] for k in ('coverage_sha256','retained_rows','ordered_ids_sha256','first_request')),'observations, identities, or request differ')
    return results


def real_panel(root,pin):
    check(digest(root/'panel.json')==pin,'wrong frozen panel'); result=json.loads((root/'panel.json').read_bytes());artifacts=result['artifacts']
    def verify():
        for rel,h in artifacts.items():
            p=root/rel;check(p.resolve()==p and p.is_relative_to(root) and digest(p)==h,'unbound panel file')
    verify();ds=prep.table(root,'metadata/datasets.tsv',('dataset_name','fasta_relpath'));seq=prep._dataset_sequences(root,ds);refs=json.loads((root/'reference-lengths.json').read_bytes());desc=json.loads((root/'base-alignments.json').read_bytes());assign=prep.table(root,'metadata/chr_assignments.tsv',('dataset_name','seq_name','assigned_chr_name'))
    used={'metadata/datasets.tsv','reference-lengths.json','base-alignments.json','metadata/chr_assignments.tsv'}|{d['fasta_relpath'] for d in ds}|{d['paf'] for d in desc}|{f"runs/{d['dataset_name']}_vs_ref/result.paf" for d in ds};check(used<=artifacts.keys(),'incomplete frozen artifacts')
    lens={d['dataset_name']:{s.contig:len(v) for s,v in seq.items() if s.dataset==d['dataset_name']} for d in ds}
    out=compare(root,lens,desc,panel=(seq,refs,assign));verify();return {'panel':root.name,'sha256':pin,'arms':out}


def sample(root,snapshot):
    check(digest(snapshot)=='2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d','wrong producer');s=json.loads(snapshot.read_bytes());check(s['source']==str(root),'wrong source workspace'); pin={r['path']:r for r in s['files']}; lens,_,meta,_=catalog(root);lens.pop(None);check(all(pin[k]['sha256']==h for k,h in meta.items()),'metadata drift')
    limit=512*1024; size=0; h=hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix='q0-shared-matrix-',dir='/tmp') as tmp:
        scratch=Path(tmp)
        for row in s['alignments']:
            rel=row['paf'];p=root/rel;check(p==p.resolve() and p.is_relative_to(root),'invalid PAF path');before=stamp(p);check(before[2]==pin[rel]['size'],'matrix size drift');n=0;to=scratch/rel;to.parent.mkdir(parents=True,exist_ok=True)
            with p.open('rb') as src, to.open('xb') as out:
                while n<limit:
                    line=src.readline(limit-n+1)
                    if not line or n+len(line)>limit:break
                    out.write(line);n+=len(line);h.update(line)
            check(stamp(p)==before,'matrix changed');size+=n
        a=compare(scratch,lens,s['alignments']);return {'files':len(s['alignments']),'bytes':size,'sample_sha256':h.hexdigest(),'arms':a,'limits':'Up to 512 KiB per matrix: local warm file reads, coverage consumer and ordered row ID summary. Not whole-wheat runtime.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='kind',required=True);x=sub.add_parser('panel');x.add_argument('root',type=Path);x.add_argument('pin');x=sub.add_parser('sample');x.add_argument('root',type=Path);x.add_argument('snapshot',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args(); root=a.root.resolve(strict=True);check(not a.out.exists() and not a.out.resolve().is_relative_to(root),'unsafe output');r=real_panel(root,a.pin) if a.kind=='panel' else sample(root,a.snapshot)
    with a.out.open('x') as f:json.dump(r,f,sort_keys=True,indent=2);f.write('\n')
    print('VERIFIED',a.kind,a.root.name,[(x['semantic_opens'],round(x['seconds'],3)) for x in r['arms']],flush=True)
