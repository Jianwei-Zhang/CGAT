#!/usr/bin/env python3
"""Compare completed experimental self PAFs; missing profiles are not a pass."""
import argparse,json
from pathlib import Path


def span(intervals): return sum(b-a for a,b in intervals)


def overlap(left,right):
    i=j=total=0
    while i<len(left) and j<len(right):
        total+=max(0,min(left[i][1],right[j][1])-max(left[i][0],right[j][0]))
        if left[i][1]<right[j][1]:i+=1
        else:j+=1
    return total


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    reports={k:json.loads((a.root/('precision-'+k)/'report.json').read_text()) for k in ('baseline','rmq100','rmq0','freq100')}
    assert all(r['status']=='COMPLETED_AWAITING_PRECISION_COMPARISON' for r in reports.values())
    baseline=reports['baseline']['runs']['baseline'];out={'status':'MEASURED_NOT_APPROVED','variants':{},'boundary':'Strong means >=5kb query span and >=90% PAF identity; merged query coverage stratified by contig pair and strand. This is sensitivity relative to baseline, not ground-truth precision or Final Path equality. Different compute nodes and single-pass timings limit causal speed claims.'}
    for profile,report in reports.items():
        assert report['tool']==reports['baseline']['tool'] and report['inputs']==reports['baseline']['inputs']
        run=report['runs'][profile];rows={}
        for name,base in baseline['paf'].items():
            variant=run['paf'][name];x=base['strong_query_coverage_by_pair_strand'];y=variant['strong_query_coverage_by_pair_strand']
            before=sum(span(v) for v in x.values());retained=sum(overlap(v,y.get(k,[])) for k,v in x.items())
            rows[name]={'baseline_rows':base['rows'],'variant_rows':variant['rows'],'baseline_strong_pair_strand_query_bp':before,'retained_strong_pair_strand_query_bp':retained,'retained_fraction':retained/before if before else None,'missing_pairs_or_strands':sorted(set(x)-set(y)), 'content_equal':all(base[k]==variant[k] for k in ('rows','unordered_digest_sum','unordered_digest_square_sum'))}
        out['variants'][profile]={'seconds':run['seconds'],'speed_ratio':baseline['seconds']/run['seconds'],'tasks':rows}
    path=a.root/'precision-comparison.json'
    with path.open('x') as f:f.write(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__':main()
