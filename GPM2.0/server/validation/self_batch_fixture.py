#!/usr/bin/env python3
"""Bounded functional/adversarial synthetic fixture; not a customer-speed claim."""
import argparse,hashlib,json,os,random,shutil,subprocess,sys,time
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--restore',type=Path,required=True);a=p.parse_args()
    a.root.mkdir(parents=True,exist_ok=False);rng=random.Random(2665)
    def dna(n):return ''.join(rng.choices('ACGT',k=n))
    def mutate(seq):
        bases=list(seq)
        for i in range(13,len(bases),211):bases[i]={'A':'C','C':'G','G':'T','T':'A'}[bases[i]]
        return ''.join(bases)
    motif=dna(5000);unique=dna(160000)
    # Skewed long-record fixture + many-record fixture with imperfect repeats,
    # unique flanks, inverted pieces, zero-overlap candidates and long gaps.
    core=unique[:60000]+(motif*24)+unique[60000:]
    inv=core[40000:80000].translate(str.maketrans('ACGT','TGCA'))[::-1]
    cases={
      'chr_BSWB01000001.1/hifiasm_vs_self':[core,mutate(core[:220000])+inv,core[:50000]+dna(8000)+core[50000:]],
      'chr_BSWB01000003.1/flye_vs_self':[mutate(core[i*3000:i*3000+30000]) for i in range(18)]+[dna(20000),motif*7,inv+dna(5000)]}
    report={'status':'RUNNING','seed':2665,'boundary':'Small synthetic adversarial functional suite, not yet a calibrated reproduction of customer multi-hour hotspots. Baseline and batches same binary/flags. No biological quality claim.','cases':{},'stages':[]}
    def save():(a.root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    mm=shutil.which('minimap2');assert mm
    from self_query_batches import FLAGS,sha
    report['tool']={'path':mm,'sha256':sha(mm)};save()
    for name,seqs in cases.items():
        dest=a.root/'workspace/runs'/name;dest.mkdir(parents=True)
        mapping=[]
        for suffix,filename in [('a','self_target.fa'),('b','self_query.fa')]:
            with (dest/filename).open('w') as f:
                for i,seq in enumerate(seqs,1):
                    alias=f'gpm_pair_{i:09d}{suffix}';mapping.append(f'{alias}\tcontig{i}\n')
                    f.write('>'+alias+'\n')
                    for j in range(0,len(seq),80):f.write(seq[j:j+80]+'\n')
        (dest/'self_name_map.tsv').write_text(''.join(mapping));shutil.copyfile(a.restore,dest/'restore_self_paf.py')
        start=time.monotonic()
        with (dest/'raw.paf').open('wb') as f,(dest/'baseline.stderr').open('wb') as err:
            subprocess.run([mm,*FLAGS,'-t','4',str(dest/'self_target.fa'),str(dest/'self_query.fa')],stdout=f,stderr=err,check=True,timeout=120)
        with (dest/'raw.paf').open('rb') as f,(dest/'result.paf').open('wb') as out:
            subprocess.run([sys.executable,str(dest/'restore_self_paf.py'),str(dest/'self_name_map.tsv')],stdin=f,stdout=out,check=True,timeout=30)
        report['cases'][name]={'lengths':list(map(len,seqs)),'baseline_seconds':time.monotonic()-start,'paf_sha256':sha(dest/'result.paf')};save()
    script=Path(__file__).with_name('self_query_batches.py')
    cmd=[sys.executable,str(script),'--root',str(a.root/'batched'),'--workspace',str(a.root/'workspace'),'--tools',str(Path(__file__).parent/'tools'),'--threads','4','--memory-gb','24','--batch-bases','100000']
    for stage in ('cold','resume','corrupt-one-rebuild'):
        if stage=='corrupt-one-rebuild':
            one=next((a.root/'batched').glob('*/batch-*/result.paf'));one.write_bytes(b'corrupted-test-output\n')
        with (a.root/(stage+'.log')).open('wb') as log:
            subprocess.run(cmd+([] if stage=='cold' else ['--resume']),stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        result=json.loads((a.root/'batched/report.json').read_text());total=len(result['batches']);hits=result['cache_hits']
        assert result['status']=='PASS'
        if stage=='resume':assert hits==total and not result['completed']
        if stage=='corrupt-one-rebuild':assert hits==total-1 and len(result['completed'])==1
        report['stages'].append({'stage':stage,'status':result['status'],'batches':total,'cache_hits':hits,'seconds':result['total_seconds']});save()
    report['status']='PASS';save();print(json.dumps(report,indent=2))

if __name__=='__main__':main()
