"""Read-only sizing of reference-derived chromosome candidate scopes.

Qualifying hits only size a possible planning gate, never certify placements.
Original assignment groups are kept separately; no genomic sequence is read.
"""
from pathlib import Path
from collections import defaultdict
import argparse
import hashlib
import json
import re
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--lookup-dir',type=Path,required=True)
    p.add_argument('--reference-summary',type=Path,required=True)
    a=p.parse_args();work=a.workspace.resolve(strict=True);started=time.monotonic()
    raw=(a.lookup_dir/'source-part-lookup.json').read_bytes();proof=json.loads((a.lookup_dir/'receipt.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=proof['lookup_sha256']:raise ValueError('part lookup changed')
    parts=json.loads(raw);names={(v['dataset'],v['contig']):key for key,v in parts.items()}
    lengths={key:v['length'] for key,v in parts.items()}
    original=defaultdict(set);all_refs=defaultdict(set);qualified=defaultdict(set)
    for key,row in parts.items():
        for chromosome in row['original_assigned_chromosomes']:
            if chromosome:original[chromosome].add(key)
    sources=json.loads(a.reference_summary.read_text())['datasets'];identities={};count=0
    for source in sources:
        dataset=source['dataset'];path=work/f'runs/{dataset}_vs_ref/result.paf';before=path.stat();digest=hashlib.sha256()
        with path.open('rb') as f:
            for raw in f:
                digest.update(raw)
                if not raw.strip() or raw.startswith(b'#'):continue
                fields=raw.decode('ascii').rstrip('\r\n').split('\t');count+=1
                key=names[(dataset,fields[0])]
                if int(fields[1])!=lengths[key]:raise ValueError('source length drift')
                cigars=[tag[5:] for tag in fields[12:] if tag.startswith('cg:Z:')]
                if len(cigars)!=1:raise ValueError('missing CIGAR')
                if re.search('[M=X]',cigars[0]):all_refs[fields[5]].add(key)
                matches,span,mapq=map(int,fields[9:12])
                if matches/span>=.90 and 20<=mapq<255:
                    # A single qualifying hit is a sufficient (not exhaustive)
                    # >=100bp source-support condition for this sizing probe.
                    paired=sum(int(n) for n,op in re.findall(r'([1-9][0-9]*)([MIDN=X])',cigars[0]) if op in 'M=')
                    if paired>=100:qualified[fields[5]].add(key)
        after=path.stat()
        if ((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
                !=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                or digest.hexdigest()!=source['reference_paf_sha256']):raise ValueError('reference evidence changed')
        identities[dataset]=digest.hexdigest()
    rows=[]
    for chromosome in sorted(set(original)|set(all_refs)):
        row={'chromosome':chromosome}
        for label,ids in [('original',original[chromosome]),('all_reference_candidates',all_refs[chromosome]),
                          ('original_plus_qualifying',original[chromosome]|qualified[chromosome])]:
            row[label+'_count']=len(ids);row[label+'_bases']=sum(lengths[key] for key in ids)
        rows.append(row)
    report={'status':'read_only_scope_sizing','lookup_sha256':proof['lookup_sha256'],'reference_sha256':identities,
            'reference_rows':count,'seconds':time.monotonic()-started,'chromosomes':rows,
            'excludes_pairwise_discovery_expansion':True,'scientific_acceptance':False,
            'qualifying_definition':'a >=0.90 identity hit with known MAPQ>=20 and >=100 paired M/= bp; not union across several small hits, not admission',
            'production_policy_changed':False}
    Path('summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
