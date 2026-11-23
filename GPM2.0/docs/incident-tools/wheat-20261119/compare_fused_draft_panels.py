"""Run one real initial_questions implementation per interpreter; compare exact request documents."""
import argparse
import hashlib
import json
from pathlib import Path
from time import monotonic


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()


def arm(panel, pin):
    from lgz_core import q0_preparation as prep, q0_threshold_prepare as threshold
    from lgz_core.q0_threshold_acceptance import record
    if digest(panel/'panel.json') != pin: raise ValueError('wrong panel')
    m = json.loads((panel/'panel.json').read_bytes()); artifacts = m['artifacts']
    if m['panel'] != panel.name: raise ValueError('panel name differs')
    def verify():
        for rel, want in artifacts.items():
            p = panel/rel
            if p.resolve() != p or not p.is_relative_to(panel) or digest(p) != want: raise ValueError('input changed: '+rel)
    verify()
    ds = prep.table(panel,'metadata/datasets.tsv',('dataset_name','fasta_relpath'))
    assignments = prep.table(panel,'metadata/chr_assignments.tsv',('dataset_name','seq_name','assigned_chr_name'))
    refs = json.loads((panel/'reference-lengths.json').read_bytes()); desc = json.loads((panel/'base-alignments.json').read_bytes())
    names = {'metadata/datasets.tsv','metadata/chr_assignments.tsv','reference-lengths.json','base-alignments.json'}
    names.update(d['fasta_relpath'] for d in ds); names.update(d['paf'] for d in desc)
    names.update(f"runs/{d['dataset_name']}_vs_ref/result.paf" for d in ds)
    if not names <= set(artifacts): raise ValueError('unbound scientific inputs')
    seq = prep._dataset_sequences(panel,ds); start = monotonic(); need,path = threshold.initial_questions(panel,seq,refs,assignments,desc); elapsed=monotonic()-start
    verify()
    return {'panel':panel.name,'panel_sha256':pin,'request':record(need),'has_path':path,'seconds':elapsed,
            'parser': 'fused' if hasattr(threshold,'read_retained_paf') else 'original'}


def compare(old, new):
    if old['parser']!='original' or new['parser']!='fused' or any(old[k]!=new[k] for k in ('panel','panel_sha256','request','has_path')):
        raise ValueError('input or exact first request differs')
    request=old['request'];return {'panel':old['panel'],'panel_sha256':old['panel_sha256'],'has_path':old['has_path'],
        'request_sha256':hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'sources':len(request) if request is not None else None,'intervals':sum(len(r[1]) for r in request) if request is not None else None,
        'original_seconds':old['seconds'],'fused_seconds':new['seconds']}


if __name__=='__main__':
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='mode',required=True);a=sub.add_parser('arm'); a.add_argument('panel',type=Path);a.add_argument('pin');a.add_argument('out',type=Path)
    c=sub.add_parser('compare');c.add_argument('old',type=Path);c.add_argument('new',type=Path);c.add_argument('out',type=Path);v=p.parse_args()
    if v.mode=='arm' and v.out.resolve().is_relative_to(v.panel.resolve()):raise ValueError('cannot write inside source panel')
    result=arm(v.panel.resolve(strict=True),v.pin) if v.mode=='arm' else compare(json.loads(v.old.read_bytes()),json.loads(v.new.read_bytes()))
    with v.out.open('x') as f: json.dump(result,f,sort_keys=True,indent=2);f.write('\n')
    print(result if v.mode=='compare' else f"{result['parser']} {result['panel']} {result['seconds']:.3f}s",flush=True)
