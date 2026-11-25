"""Question-driven native scope sizing. No mapper, no evidence acceptance, no change to the original matrix."""
from collections import Counter
from hashlib import sha256
import gzip
import json
from pathlib import Path
import sys

PARENT='14bbc01fad3743cdfdfb3ff4c6009d92caeb928c4b9291e156bac9aa827961d9'
MISSING, SCOPED, EXACT, SELF=range(4)


def src_id(ds,name):
    return sha256(json.dumps([ds,name],separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()


def checked(p,pin):
    data=p.read_bytes()
    if sha256(data).hexdigest()!=pin:raise ValueError('content changed: '+str(p))
    return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)


def mask(base,geom,out):
    from wheat_dispatch_native_scope import main as native
    from lgz_core.q0_regional_candidates import CompletedNativeScopes
    from wheat_dispatch_scope import put
    out.mkdir()
    def capture(pin,pool,parents,requested,lookup,order):
        if pin!=PARENT:raise ValueError('native scope replay differs')
        tested={p:(CompletedNativeScopes.remaining_targets(pool,p,requested),CompletedNativeScopes.remaining_targets(pool,p,requested,include_approximate=False)) for p in parents}
        if any(missing & ~without_profile for missing,without_profile in tested.values()):raise ValueError('invalid native profile containment')
        lengths={}; codes={p:{} for p in parents};parent_keys={}
        for part,(rank,n,_) in lookup.items():
            s=order[rank];key=src_id(s.dataset,s.contig);bit=1<<rank
            if key in lengths:raise ValueError('source is not a unique whole native part')
            lengths[key]=n
            for p,(missing,without_profile) in tested.items():
                code=SELF if p==part else MISSING if missing&bit else SCOPED if without_profile&bit else EXACT
                if p==part:parent_keys[p]=key
                if code!=MISSING:codes[p][key]=code
        if len(lengths)!=38267 or sum(lengths.values())!=31706122489 or len(parent_keys)!=2:raise ValueError('wrong native inventory')
        doc=dict(schema='wheat_original_matrix_pair_scope_v1',binding=pin,lengths=lengths,parents={parent_keys[p]:codes[p] for p in parents},parent_parts={parent_keys[p]:p for p in parents},mapper_calls=0)
        print('PAIR_MASK_READY',put(out/'pair-mask.json.gz',doc),flush=True)
    native(base,geom,out/'native.json',on_verified_scope=capture)


def evaluate(m,detail):
    lengths=m['lengths']; parents=m['parents'];issues=detail['issues']
    if detail['source_intervals'] is None or not detail['has_path']:
        return dict(bounded_request=False,native_rule='no_bounded_draft',mapper_calls=0)
    demand={src_id(s['dataset'],s['contig']):spans for s,spans in detail['source_intervals']}; operands=[];bounds={}
    for v in issues:
        keys=set()
        for ds,s,lo,hi in v['spans']:
            k=src_id(ds,s)
            if k not in lengths or not 0<=lo<hi<=lengths[k]:raise ValueError('question outside original source')
            keys.add(k);bounds.setdefault(k,[]).append((lo,hi))
        operands.append(keys)
    def merged(spans):
        out=[]
        for a,b in sorted(spans):
            if out and a<=out[-1][1]:out[-1][1]=max(b,out[-1][1])
            else:out.append([a,b])
        return out
    if len(demand)!=len(detail['source_intervals']) or demand!={k:merged(v) for k,v in bounds.items()}:raise ValueError('question union disagrees with source intervals')
    demand=demand.keys()
    metrics={};retained=set();roles={}; counts=Counter()
    for p,tested in parents.items():
        direct=p in demand;targets=(lengths.keys() if direct else demand)-{p}; bins=Counter(tested.get(t,MISSING) for t in targets); absent={t for t in targets if tested.get(t,MISSING)==MISSING};retained.update(absent);hit_query=Counter();direct_join=Counter();open_q=set();exact_only=set()
        if tested.get(p)!=SELF:raise ValueError('self exclusion missing')
        for i,(v,parts) in enumerate(zip(issues,operands)):
            qside=p in parts
            if qside:hit_query[v['kind']]+=1
            # A query-side request can receive new evidence with any untested original target, not merely a target on the current path.
            if (qside and bool(absent)) or any(k in absent for k in parts):open_q.add(i)
            elif not qside and all(tested.get(k,MISSING)==EXACT for k in parts):exact_only.add(i)
            if v['kind']=='unproven_join' and qside:
                other=parts-{p}; name=('untested_endpoint_pair' if any(tested.get(k,MISSING)==MISSING for k in other) else 'previously_scoped_endpoint_pair' if other else 'same_source');direct_join[name]+=1
        metrics[m['parent_parts'][p]]=dict(query_has_demand=direct,whole_targets_examined_by_axis=len(targets),exact_pair_scope=bins[EXACT],limited_pair_scope=bins[SCOPED],untested_pair_scope=len(absent),untested_target_bases=sum(lengths[t] for t in absent),query_role_questions=hit_query,direct_join_role=direct_join)
        roles[p]=open_q,exact_only
    for i,v in enumerate(issues):
        classification='some_untested_relationship' if any(i in a for a,_ in roles.values()) else 'all_relevant_pairs_exact_scope' if all(i in b for _,b in roles.values()) else 'previously_scoped_or_self'
        counts[classification+':'+v['kind']]+=1
    return dict(bounded_request=True,remaining_sources=len(demand),remaining_source_bases=sum(lengths[s] for s in demand),distinct_remaining_questions=len(issues),whole_native_target_count=len(lengths),whole_native_target_bases=sum(lengths.values()),parents=metrics,distinct_untested_target_count=len(retained),distinct_untested_target_bases=sum(lengths[t] for t in retained),question_classes=counts,mapper_calls=0,limits='Pair scope follows the original planner, including reciprocal coverage and its declared long-part approximate profile. It is not a proof of identical PAFs with a smaller target collection. Self exclusion is not negative sequence evidence. Non-endpoint queries can still indirectly change placement or routing.')


if __name__=='__main__':
    if sys.argv[1]=='mask':mask(*map(Path,sys.argv[2:]))
    elif sys.argv[1]=='evaluate':
        m=checked(Path(sys.argv[2]),sys.argv[3]); detail=checked(Path(sys.argv[4]),sys.argv[5]);result=evaluate(m,detail)
        with Path(sys.argv[6]).open('x') as f:json.dump(dict(mask_sha256=sys.argv[3],questions_sha256=sys.argv[5],**result),f,sort_keys=True,indent=2);f.write('\n')
    else:raise SystemExit('expected mask or evaluate')
