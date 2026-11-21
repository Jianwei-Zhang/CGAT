"""Metadata-only inversion of canonical whole-source part IDs for diagnostics.

Length is only a search hint: every source name/dataset/interval/content digest
must recompute the exact existing part ID. Splits or mismatches fail closed.
This is NOT a source FASTA content revalidation or a placement-confidence proof.
"""
from pathlib import Path
from collections import defaultdict
import argparse
import csv
import hashlib
import json
import sys


def invert(members, hints, sources, stable_id, *, maximum_trials=200000):
    by_length=defaultdict(list)
    for dataset,name,length in sources:
        if not dataset or not name or type(length) is not int or length<1:raise ValueError('invalid source metadata')
        by_length[length].append((dataset,name))
    if len({(d,n) for d,n,_ in sources})!=len(sources):raise ValueError('duplicate source identity')
    if set(members)!=set(hints):raise ValueError('part length-hint inventory differs')
    trials=sum(len(by_length.get(hints[key],[])) for key in members)
    if trials>maximum_trials:raise ValueError('metadata inversion exceeds login-node budget; schedule it')
    result={};used=set()
    for key,digest in sorted(members.items()):
        length=hints[key]
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('invalid member digest')
        matches=[(d,n) for d,n in by_length.get(length,[])
                 if stable_id('q0-source-part',[d,n,0,length,digest])==key]
        if len(matches)!=1:raise ValueError('not an exact whole-source part; do not guess from its length')
        source=matches[0]
        if source in used:raise ValueError('source mapped more than once')
        used.add(source);result[key]={'dataset':source[0],'contig':source[1],'length':length,'sequence_sha256':digest}
    if used!={(d,n) for d,n,_ in sources}:raise ValueError('whole-source inventory is incomplete')
    return result,trials


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True);p.add_argument('--complete-task',required=True)
    p.add_argument('--length-hints',type=Path,required=True)
    a=p.parse_args();work=a.workspace.resolve(strict=True);out=Path.cwd().resolve()
    if out==work or work in out.parents or Path(a.complete_task).name!=a.complete_task:raise ValueError('isolated output directory required')
    sys.path.insert(0,str(work/'.prepare_lib/tools'));from lgz_core.common import stable_id
    inputs={}
    def read(path):
        path=Path(path);before=path.stat();raw=path.read_bytes();after=path.stat()
        signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if signature(before)!=signature(after):raise ValueError('metadata changed during reading')
        inputs[str(path)]={'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw),'stat':signature(after)}
        return raw.decode('utf-8')
    task=work/'grt/evidence/q0_prepare/tasks'/a.complete_task
    receipt=json.loads(read(task/'success.json'));command=json.loads(read(task/'command.json'))
    if receipt.get('status')!='success' or receipt['spec']!=command['spec']:raise ValueError('completed native specification differs')
    members=dict(command['spec']['members'])
    if len(members)!=len(command['spec']['members']):raise ValueError('duplicate member identity')
    datasets=list(csv.DictReader(read(work/'metadata/datasets.tsv').splitlines(),delimiter='\t'))
    sources=[]
    for dataset in datasets:
        rel=Path(dataset['fai_relpath'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('FAI escapes workspace')
        for line in read(work/rel).splitlines():
            fields=line.split('\t');sources.append((dataset['dataset_name'],fields[0],int(fields[1])))
    hints={}
    for line in read(a.length_hints).splitlines():
        fields=line.split('\t')
        if fields[0] in hints:raise ValueError('duplicate part length hint')
        hints[fields[0]]=int(fields[1])
    result,trials=invert(members,hints,sources,stable_id)
    assignments=defaultdict(set)
    for row in csv.DictReader(read(work/'metadata/chr_assignments.tsv').splitlines(),delimiter='\t'):
        assignments[(row['dataset_name'],row['seq_name'])].add(row['assigned_chr_name'])
    for row in result.values():row['original_assigned_chromosomes']=sorted(assignments[(row['dataset'],row['contig'])])
    for path,expected in inputs.items():
        s=Path(path).stat()
        if tuple(expected['stat'])!=(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns):raise ValueError('metadata changed before publication')
    output=out/'source-part-lookup.json';output.write_text(json.dumps(result,sort_keys=True)+'\n')
    receipt={'status':'canonical_whole_source_ids_verified_metadata_only','records':len(result),'hash_trials':trials,
             'inputs':inputs,'lookup_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
             'source_fasta_contents_revalidated':False,'assignment_is_placement_confidence':False,
             'policy':'only diagnostic source/dataset/group labels; not a production cache acceptance proof'}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='inputs'}))


if __name__=='__main__':main()
