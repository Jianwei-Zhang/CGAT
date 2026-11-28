"""Independent readback of the 15 real projections, not another mapper or a claim of Q0 closure."""
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
import gzip,json,sys
from lgz_core.common import sha256_file
from lgz_core.q0_alignments import read_paf_observations
from lgz_core.q0_regional_mapping import verify_regional_task
from lgz_core.q0_sources import Interval

PLAN='aa84f79c0d5faa4d253850c5bf8635be308145f8efa47f4d3de934b34290a28e'
QUESTIONS='9c0a2e5569e4161e7ef59f7332b232f1d2d2ea4480c4a1c8445490c61ee62d97'
LINKS='5518b461e67e9f45adab0ea7e9cc28bf4561547bfc495f4c1f822ed14b5ff9b9'
LOOK='2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'

def need(ok,msg):
    if not ok:raise ValueError(msg)

def checked(path,pin):
    raw=path.read_bytes();need(sha256(raw).hexdigest()==pin,'input differs: '+path.name)
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)

def local_contacts(hit,spans):
    """Require 100 contiguous M/= bp inside one actual shoulder, never a DP hull or deletion."""
    if hit.matches/hit.block_length<.95:return set()
    possible=[(i,j,v) for i,j,v in spans if min(hit.target.end,v.end)-max(hit.target.start,v.start)>=100]
    if not possible:return set()
    seen=set()
    for b in hit.aligned_blocks():
        if b.operation not in ('M','=') or b.target.length<100:continue
        for i,j,v in possible:
            if min(b.target.end,v.end)-max(b.target.start,v.start)>=100:seen.add((i,j))
    return seen

def counts(issues,support):
    by_kind=Counter();both_parent=set();both_window=set()
    for i,sides in support.items():
        by_kind[issues[i]['kind']]+=1
        if issues[i]['kind']!='unproven_join' or 0 not in sides or 1 not in sides:continue
        a,b=sides[0],sides[1]
        if {q for q,w in a} & {q for q,w in b}:both_parent.add(i)
        if a & b:both_window.add(i)
    return dict(issues_with_any_100bp_shoulder=dict(by_kind),joins_hit_on_both_ends_by_same_parent=len(both_parent),joins_hit_on_both_ends_in_same_query_window=len(both_window))

def run(base,owner,*,on_support=None):
    result=owner/'result.json';pin=sha256_file(result); logs=list(owner.glob('regionals_*.out'))
    need(any(pin+'  result.json' in p.read_text().splitlines() for p in logs),'result not in completed job output')
    report=checked(result,pin);need(report['plan']==PLAN and report['updated_questions']==QUESTIONS and report['batches']==len(report['receipts'])==15 and report['windows']==13 and report['native_mapper_starts']==0,'incomplete execution')
    baseline=base/'q0-whole-updated.We9jf3UC';issues=checked(baseline/'result/updated-questions.json.gz',QUESTIONS)['issues'];links=checked(baseline/'compare/result/regional-question-links.json',LINKS);expected={v['index'] for v in links}
    need(len(issues)==4076 and len(expected)==98 and all((issues[v['index']]['id'],issues[v['index']]['kind'])==(v['id'],v['kind']) for v in links),'not the original residual issue set')
    lookup=checked(base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json',LOOK); ids={(v['dataset'],v['contig']):k for k,v in lookup.items()};members={k:(v['length'],v['sequence_sha256']) for k,v in lookup.items()};spans=defaultdict(list)
    for i,row in enumerate(issues):
        if row['kind']=='unproven_join':need(len(row['spans'])==2,'unknown join endpoints')
        for j,(d,s,a,b) in enumerate(row['spans']):spans[ids[d,s]].append((i,j,Interval(a,b)))
    windows={}; tasks=set();root=owner/'workspace';pairs=set(); stats=Counter(); support=defaultdict(lambda:defaultdict(set)); cross=defaultdict(lambda:defaultdict(set)); rows=0; cases=Counter()
    for ordinal,ds in enumerate(report['receipts'],1):
        batch=checked(owner/f'batch-{ordinal:02d}.json',ds); t=batch['task'];need(batch['index']==ordinal and t['task_id'] not in tasks,'duplicate or shuffled batch');tasks.add(t['task_id']);q,=t['query_ids'];need(lookup[q]['contig'] in ('JM19flyeA_contig_4549','ptg000010l') and q not in spans,'unexpected directly requested or foreign query');w=batch['query']; windows.setdefault(w,q);need(windows[w]==q,'query parent changed')
        need(sha256_file(root/t['receipt'])==batch['receipt_sha256'],'changed projected receipt'); verify_regional_task(root,t,members=members);file=root/t['paf']; fingerprint=sha256_file(file);need(fingerprint==batch['projected_sha256'] and file.stat().st_size==batch['projected_bytes'],'changed PAF');n=0
        for hit in read_paf_observations(file,query_lengths={q:members[q][0]},target_lengths={k:members[k][0] for k in t['target_ids']},artifact=t['paf']):
            n+=1; qid=hit.query_name; target=hit.target_name; relation='cross' if lookup[qid]['dataset']!=lookup[target]['dataset'] else 'intra';stats[relation]+=1;pairs.add((qid,target,hit.strand))
            touched=local_contacts(hit,spans.get(target,()));
            if touched:cases[relation]+=1
            for i,j in touched:
                need(i in expected,'positive outside the sealed frame contact set');support[i][j].add((qid,w))
                if relation=='cross':cross[i][j].add((qid,w))
        need(n==batch['projected_rows'] and sha256_file(file)==fingerprint,'PAF changed during analysis');rows+=n
        print('REGIONAL_EVIDENCE_READ',ordinal,'rows',n,'issues_so_far',len(support),flush=True)
    need(len(windows)==13 and rows==report['projected_rows'] and sha256_file(result)==pin,'incomplete panel readback')
    if on_support is not None:
        on_support([(issues[i],sorted(sides)) for i,sides in sorted(support.items())])
    return dict(mapping=pin,questions=QUESTIONS,geometric_contacts_before=98,projected_rows=rows,projected_by_relation=dict(stats),distinct_query_target_strand=len(pairs),paf_rows_supporting_any_shoulder=dict(cases),any_relationship=counts(issues,support),cross_assembly_only=counts(issues,cross),native_mapper_starts=0,scope='Fixed old question shoulders and real paired CIGAR runs; contacts are candidate evidence, not orientation-compatible bridging, gap closure, placement acceptance or the next Q0 path.')

if __name__=='__main__':
    owner=Path(sys.argv[1]); value=run(owner.parent,owner)
    with Path('assessment.json').open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
