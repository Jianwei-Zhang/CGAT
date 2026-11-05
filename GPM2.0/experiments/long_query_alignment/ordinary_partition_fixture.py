#!/usr/bin/env python3
"""Private balanced multipart control, not a customer dataset or production input.

The 8 GB N padding is remote-only; it exercises the ORIGINAL default -I policy.
Smaller local controls must explicitly label their forced index partitioning.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random


def generate(root, *, seed_bases=51_000_000, padding_records=80, padding_bases=100_000_000,
             query_records=16, query_bases=10_000_000):
    if not (seed_bases > query_bases > 1000 and padding_records >= 0 and
            padding_bases > 0 and query_records >= 4):
        raise ValueError('positive bounded complete-record fixture required')
    root.mkdir(parents=True, exist_ok=False)
    rng = random.Random(2311302)
    seed = rng.randbytes(seed_bases).translate(bytes.maketrans(bytes(range(256)), b'ACGT' * 64))
    target, query = root/'target.fa', root/'queries.fa'
    digest = hashlib.sha256()
    def emit(out, data):
        out.write(data);digest.update(data)
    with target.open('xb') as out:
        emit(out,b'>left\n');emit(out,seed);emit(out,b'\n')
        block=b'N'*1_000_000
        for i in range(padding_records):
            emit(out,f'>padding_{i}\n'.encode())
            left=padding_bases
            while left:
                n=min(len(block),left);emit(out,block[:n]);left-=n
            emit(out,b'\n')
        emit(out,b'>right\n')
        emit(out,seed.translate(bytes.maketrans(b'ACGT',b'TGCA'))[::-1]);emit(out,b'\n')
    manifest={'synthetic_control_only':True,'customer_wheat_data':False,
              'target_sha256':digest.hexdigest(),'seed':2311302,'seed_bases':seed_bases,
              'padding_records':padding_records,'padding_bases':padding_bases,
              'original_default_index_policy_expected':padding_records*padding_bases>=8_000_000_000,
              'query_records':query_records,'query_bases_before_indels':query_bases,
              'N_only_queries':1,'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    digest=hashlib.sha256()
    with query.open('xb') as out:
        for i in range(query_records):
            offset=i*7919 % (len(seed)-query_bases+1)
            body=bytearray(seed[offset:offset+query_bases])
            for j in range(101+i,len(body),997):
                body[j]=b'ACGT'[(b'ACGT'.index(body[j])+1)%4]
            if i%5==0:
                j=len(body)//2;body=body[:j]+b'ACGTACG'+body[j+3:]
            if i%3==0:
                body=body.translate(bytes.maketrans(b'ACGT',b'TGCA'))[::-1]
            if i==query_records-1:
                body=bytearray(b'N')*len(body)
            emit(out,f'>q{i:03d}\n'.encode());emit(out,body);emit(out,b'\n')
    manifest['query_sha256']=digest.hexdigest()
    (root/'fixture.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seed-bases',type=int,default=51_000_000)
    p.add_argument('--padding-records',type=int,default=80)
    p.add_argument('--padding-bases',type=int,default=100_000_000)
    p.add_argument('--query-records',type=int,default=16)
    p.add_argument('--query-bases',type=int,default=10_000_000)
    p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if a.execute:
        if (not 1000<a.query_bases<a.seed_bases<=100_000_000 or not 0<=a.padding_records<=100
                or not 0<a.padding_bases<=100_000_000 or not 4<=a.query_records<=64):
            p.error('bounded fixture resources required')
        result=generate(a.out,seed_bases=a.seed_bases,padding_records=a.padding_records,
            padding_bases=a.padding_bases,query_records=a.query_records,query_bases=a.query_bases)
    else:
        result={'execute':False,'files_created':False,'note':'Use --execute to write a private synthetic fixture.'}
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
