"""Compare two sealed whole-wheat draft generations. Never map, dispatch, rank, or publish Q0."""
from collections import Counter, defaultdict
from dataclasses import fields
from hashlib import sha256
import gzip,json,sys
from pathlib import Path

from assess_wheat_local_only_batches import run as independently_read_15
from wheat_selection_checkpoint import decode,need
from lgz_core.q0_paths import Placement, RequestPathResult
from lgz_core.common import sha256_file

BASE='ef67a79f96a87adb9cd13d86c652b0fe4c6b769a717d5ddadda9196414eabffa'
MAPPING='ffc6e0f5cd45948e5d5ff5140c1b6a15e977e6b8bcdf5c7477c699ed34c16f8e'
READBACK='5b14bed1c71c7aec13c3496a15262e4f1b3cdd138fce228f46dd3d4881cf5a9a'
KIT='6e0de78d51a3b2b6b2b7f2d65bafd99dd2f1fcbc6b9b4d4f0be0ce61525bb286'
GROUPS=tuple([f'{n}{g}' for n in range(1,8) for g in 'ABD']+['Un'])

def get(path,pin):
    raw=path.read_bytes();need(sha256(raw).hexdigest()==pin,'different input: '+path.name)
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)

def checkpoint(folder,binding,*,on_placement=None):
    prev=''; placements=defaultdict(dict); paths={}
    names=[f.name for f in fields(Placement)];pid,chrom,ev=map(names.index,('placement_id','chromosome','evidence_ids'))
    def rows(name,group):
        nonlocal prev
        p=folder/name;need(p.resolve()==p and p.is_file(),'unbound checkpoint path')
        with p.open('rb') as f:
            head=f.readline();digest=sha256(head);need(json.loads(head)==['wheat_first_request_checkpoint_v1',binding,name,group,prev],'wrong checkpoint chain or scope');n=0
            for raw in f:
                row=json.loads(raw)
                if isinstance(row,list):
                    need(row==['end',n,digest.hexdigest()] and not f.read(1),'incomplete checkpoint');prev=digest.hexdigest();return
                digest.update(raw);n+=1;yield row,sha256(raw).hexdigest()
            raise ValueError('truncated checkpoint '+name)
    for row,fingerprint in rows('admission.jsonl',None):
        v=row['Placement'];need(len(v)==len(names) and v[chrom] in GROUPS and v[pid] not in placements[v[chrom]],'duplicate or foreign admission');placements[v[chrom]][v[pid]]=fingerprint
        if on_placement is not None:on_placement(v[chrom],v[pid],v[ev])
    for i,g in enumerate(GROUPS,1):
        (row,_),=rows(f'group-{i:03d}.jsonl',g); result=decode(row);need(isinstance(result,RequestPathResult),'not a whole-draft group');p=result.path
        if p is not None:
            need(p.chromosome==g and p.slices and len(p.slices)==len(p.joins)+1 and tuple(s.placement_id for s in p.slices)==p.nodes and set(p.nodes)<=placements[g].keys(),'path does not match its admission')
            need(all((j.left_id,j.right_id)==(l.placement_id,r.placement_id) for l,j,r in zip(p.slices,p.joins,p.slices[1:])),'broken graph adjacency')
        paths[g]=p
    return prev,placements,paths

def coord(source): return (source.dataset,source.contig)
def piece(s): return (*coord(s.source),s.orientation,s.interval.start,s.interval.end)
def edges(p):
    if not p:return []
    return [(piece(l)[:3],piece(r)[:3],l.interval.end if l.orientation=='+' else l.interval.start,
             r.interval.start if r.orientation=='+' else r.interval.end,j) for l,j,r in zip(p.slices,p.joins,p.slices[1:])]

def layout(p):
    if p is None:return None
    return tuple(map(piece,p.slices)), tuple((j.kind,j.n_bp,None if j.gap_source is None else coord(j.gap_source),None if j.gap_interval is None else (j.gap_interval.start,j.gap_interval.end)) for j in p.joins)

def path_delta(old,new):
    a,b=layout(old),layout(new);both=a is not None and b is not None
    order=both and [x[:3] for x in a[0]]==[x[:3] for x in b[0]]
    return dict(old_built=a is not None,new_built=b is not None,same_path_record=old==new,same_source_cuts_joins=a==b,
                same_source_order_and_strand=order if both else None,changed_source_cuts=sum(x[3:]!=y[3:] for x,y in zip(a[0],b[0])) if order else None,
                old_join_types=dict(Counter(j.kind for j in old.joins)) if old else {},new_join_types=dict(Counter(j.kind for j in new.joins)) if new else {})

def merged(values):
    out=[]
    for a,b in sorted(values):
        need(type(a) is int and type(b) is int and 0<=a<b,'invalid request coordinates')
        if out and a<=out[-1][1]:out[-1]=(out[-1][0],max(out[-1][1],b))
        else:out.append((a,b))
    return out

def axes(issues):
    by=defaultdict(list)
    for row in issues:
        for ds,s,a,b in row['spans']:by[ds,s].append((a,b))
    return {k:merged(v) for k,v in by.items()}

def footprint_diff(a,b):
    total=lambda v:sum(y-x for blocks in v.values() for x,y in blocks)
    common=0
    for k in a.keys()&b.keys():
        left,right=a[k],b[k];i=j=0
        while i<len(left) and j<len(right):
            x,y=left[i];z,t=right[j];common+=max(0,min(y,t)-max(x,z));i+=y<=t;j+=t<=y
    return dict(old_only_bp=total(a)-common,new_only_bp=total(b)-common,both_bp=common,same=a==b)

def issue_key(r):return r['kind'],r['id']

def group_issues(rows):
    out={g:{} for g in GROUPS}
    for r in rows:
        need(r['groups'] and len(set(r['groups']))==len(r['groups']),'invalid question group')
        for g in r['groups']:
            k=issue_key(r);need(k not in out[g],'duplicate question in group');out[g][k]=r
    return out

def load_arm(owner,summary_pin,version):
    s=get(owner/'result/summary.json',summary_pin);d=get(owner/'result/updated-questions.json.gz',s['questions']);need(s['counts']==d['counts'] and s['evidence_digest']==d['evidence_inventory'] and s['inputs']==d['source_snapshot'] and s['first_request']==d['first_request'],'wrong question lineage')
    binding=[version,*(s[k] for k in ('inputs','first_request','regional_inventory','kit_sha256','evidence_digest')),32]
    chain,pl,paths=checkpoint(owner/'selection',binding);need(s['selection_chain']==chain and s['native']==4 and s['mapper_starts']==0 and not s['published_q0'],'unsealed or noncomparable run')
    ax=axes(d['issues']);reported=d['source_intervals']
    if reported is not None:
        expected={(v['dataset'],v['contig']):[tuple(iv) for iv in spans] for v,spans in reported};need(len(expected)==len(reported) and ax==expected,'questions disagree with source request')
    return s,d,pl,paths,ax

def contacted_outcome(old_row,sides,new_issues,old_path,new_path):
    k=issue_key(old_row);other=new_issues.get(k);out=dict(kind=k[0],id=k[1],groups=old_row['groups'],sides_previously_hit=sides,
        question_still_present=other is not None,same_question_spans=None if other is None else other['spans']==old_row['spans'])
    if k[0]=='unproven_join':
        (l,r,x,y,_),=(e for e in edges(old_path) if e[4].join_id==k[1]); same_pair=[e for e in edges(new_path) if (e[0],e[1])==(l,r)]
        out.update(same_directed_source_pair_count=len(same_pair),new_join_kinds_at_same_cuts=[e[4].kind for e in same_pair if (e[2],e[3])==(x,y)])
    else:
        need(k[0]=='weak_placement','unexpected supported class');old=next(s for s in old_path.slices if s.placement_id==k[1]); candidates=[s for s in new_path.slices if s.source==old.source and s.orientation==old.orientation] if new_path else []
        out.update(old_placement_id_still_selected=any(s.placement_id==k[1] for s in candidates),old_source_slice_geometry_still_selected=any(s.interval==old.interval for s in candidates))
    return out

def compare(base,old_owner,new_owner,map_owner,assess_owner):
    pin=sha256_file(new_owner/'result/summary.json');lines=(new_owner/'local_whole_43084475.out').read_text().splitlines();need(pin+'  result/summary.json' in lines and sha256_file(new_owner/'kit.sha256')==KIT,'producer has not sealed this generation')
    old,od,op,opath,oa=load_arm(old_owner,BASE,'whole-wheat-updated-supplement-v1');new,nd,np,npath,na=load_arm(new_owner,pin,'whole-wheat-local-supplement-v1')
    need(new['questions']+'  result/updated-questions.json.gz' in lines and new['kit_sha256']==KIT and new['schema']=='wheat_whole_local_supplement_readmission_v1' and new['baseline_evidence']==old['evidence_digest'] and new['local_mapping']==MAPPING and new['evidence_digest']!=old['evidence_digest'],'different evidence experiment')
    need(new['regional']==old['regional']+15==59293 and all(new[k]==old[k] for k in ('inputs','first_request','regional_inventory','base_pair_rows')),'not the frozen baseline plus 15')
    need(sha256_file(new_owner/'tools.tgz')==sha256_file(old_owner/'tools.tgz')=='19cebdc7667d912f6d3ace4a59783d3e49fbb02e668ff5f5efbb50c618c27ad2','selection engines differ')
    focal=[]; check=independently_read_15(base,map_owner,on_support=focal.extend);need(check==get(assess_owner/'assessment.json',READBACK) and check['mapping']==MAPPING and len(focal)==6,'cannot reproduce original local hits')
    oi,ni=group_issues(od['issues']),group_issues(nd['issues']);groups={}
    for g in GROUPS:
        a,b=op[g],np[g]; orig,updated=oi[g],ni[g];groups[g]=dict(**path_delta(opath[g],npath[g]),
            old_placements=len(a),new_placements=len(b),old_only_placement_ids=len(a.keys()-b.keys()),new_only_placement_ids=len(b.keys()-a.keys()),same_ids_different_placement_records=sum(a[k]!=b[k] for k in a.keys()&b.keys()),
            old_questions=dict(Counter(x[0] for x in orig)),new_questions=dict(Counter(x[0] for x in updated)),old_only_question_ids=len(orig.keys()-updated.keys()),new_only_question_ids=len(updated.keys()-orig.keys()),request=footprint_diff(axes(orig.values()),axes(updated.values())))
    details=[]
    for row,sides in focal:
        g,=row['groups'];need(oi[g].get(issue_key(row))==row,'wrong original supported question');details.append(contacted_outcome(row,sides,ni[g],opath[g],npath[g]))
    return dict(schema='wheat_before_after_15_local_projections_v1',old_summary=BASE,new_summary=pin,local_mapping=MAPPING,local_readback=READBACK,
                groups=groups,changed_geometry_groups=[g for g,v in groups.items() if not v['same_source_cuts_joins']],changed_evidence_or_score_only_groups=[g for g,v in groups.items() if v['same_source_cuts_joins'] and not v['same_path_record']],
                old_counts=old['counts'],new_counts=new['counts'],whole_request=footprint_diff(oa,na) if od['source_intervals'] is not None and nd['source_intervals'] is not None else dict(old_unbounded=od['source_intervals'] is None,new_unbounded=nd['source_intervals'] is None),old_pair_rows=old['pair_rows'],new_pair_rows=new['pair_rows'],six_previous_contacts=details,
                scope='Same frozen engine; fresh whole-input admissions and 22 draft winners, not a formal Q0 or biological ground truth. Retired/added question IDs alone do not prove closure; inspect actual directed joins and cuts. Group interval differences can overlap; use the separate whole-wheat union.')

if __name__=='__main__':
    new,maps,assess=map(Path,sys.argv[1:4]);base=new.parent;need(maps.parent==assess.parent==base,'different source workspace');doc=compare(base,base/'q0-whole-updated.We9jf3UC',new,maps,assess)
    with Path('comparison.json').open('x') as out:json.dump(doc,out,indent=2,sort_keys=True);out.write('\n')
    print('COMPARED_22_GROUPS',doc['changed_geometry_groups'],doc['whole_request'],flush=True)
