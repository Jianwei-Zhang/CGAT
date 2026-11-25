"""Can the 13 archived regional frames cover the actual *updated* 4D questions of the whole native matrix?"""
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import gzip,json,sys
from census_wheat_q0_fork import bind,bounded,require,write
from check_wheat_inverse_targets import reference
from lgz_core.q0_sources import Interval,SourceKey,merged_intervals
from lgz_core.q0_regional_mapping import MAX_TARGET_BASES
from lgz_core.q0_threshold_acceptance import decode,record


def main(base,first_arm,arm,out):
    ordinary=arm/'result'; stored=(ordinary/'result.json').read_bytes();pin=sha256(stored).hexdigest();log=arm/'replay_43061388.out';require(any(line==pin+'  result/result.json' for line in log.read_text().splitlines()),'ordinary result not sealed'); control=json.loads(stored)
    first=json.loads(bounded(first_arm/'result/result.json',64<<10,'7785196542b9caec592ced8b989a6712c00435cebd212e61307b1776d7b0398d'))
    require(control['selector']=='ordinary' and all(first[k]==control[k] for k in ('after','after_demand_digest','updated_counts','updated_pair_rows','inventory_digest','project_stats','matrix_actions')),'independent selectors or evidence differ')
    detail=json.loads(gzip.decompress(bounded(ordinary/'updated-questions.json.gz',2<<20,control['questions_sha256'])));snap,root,lookup,order,lens=bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json'); demand=decode(detail['source_intervals'],lens); issues=detail['issues'];union=defaultdict(list);by_src=defaultdict(list)
    for i,r in enumerate(issues):
        for ds,seq,a,b in r['spans']:
            k=SourceKey(ds,seq);iv=Interval(a,b);union[k].append(iv);by_src[k].append((iv,i))
    require(record({k:merged_intervals(v) for k,v in union.items()})==detail['source_intervals'] and detail['counts']==control['updated_counts'],'issue table does not explain the updated interval list')
    require(sha256(json.dumps(record(demand),sort_keys=True).encode()).hexdigest()==control['after_demand_digest'],'unbound updated request')
    geo=json.loads(bounded(Path.cwd()/'historical.json',1<<20,'b209c9be61fe9ac2ed773b4c7e216fa151ec3c2f8419c300f886ca2e10f7db61')); old=json.loads(bounded(Path.cwd()/'before.json',1<<20,'22b9d2a20010ad0ca55c4852252b67de9a17eef41cb4a3e63da955b7f1ef430b'));group={lookup[r['part']][0]:r for r in geo['native_queries']}; rows=defaultdict(list)
    raw=bounded(base/'q0-fork-partial-queries-20261123-1556/plan/queries.tsv.gz',8<<20,geo['input_sha256']['queries.tsv.gz'])
    for line in gzip.decompress(raw).splitlines():
        token,r,a,b=line.split();r=int(r)
        if r in group: rows[r].append((token.decode(),int(a),int(b)))
    stats=lambda ids:dict(Counter(issues[i]['kind'] for i in ids)); output=[];touched=set(); allids=set(range(len(issues)))
    with TemporaryDirectory(prefix='wheat-native-13-') as tmp,reference(snap,root,lookup,order,lens,Path(tmp)) as idx:
        for rank,part in sorted(group.items()):
            key=part['part'];direct={i for iv,i in by_src[order[rank]]};normal=set();over=set(); triggers={}; windows=[];sources=set();require(len(rows[rank])==part['planned_query_windows'],'historical query mismatch')
            for q,a,b in rows[rank]:
                refs=idx.regions(key,Interval(a,b),anchor_context=1_000_000,reference_context=10_000);targets=idx.targets(refs,context=10_000,exclude=[key]);total=sum(iv.length for ivs in targets.values() for iv in ivs);match=set()
                for p,ivs in targets.items():
                    src=order[lookup[p][0]]
                    for span,i in by_src.get(src,()):
                        if any(span.intersection(iv) is not None for iv in ivs):match.add(i);sources.add(src)
                if total>MAX_TARGET_BASES:triggers[q]='regional_target_budget';over.update(match)
                else:require(bool(targets),'unexpected empty reference target set');normal.update(match)
                windows.append(dict(query=q,source_interval=[a,b],target_parts=len(targets),target_bases=total,questions=stats(match)))
            prev,=[r for r in old['parents'] if r['source_rank']==rank];require(triggers=={t['query']:t['reason'] for t in prev['triggers']},'actual triggering scope differs'); intersect=normal|over;touched.update(intersect)
            output.append(dict(parent=part['source'],full_query_direct=stats(direct),full_matrix_target_side=stats(allids),regional_target_side=stats(intersect),trigger_only_target_side=stats(over),outside_all_regional_targets=stats(allids-intersect),regional_target_sources_with_questions=len(sources),windows=windows))
    write(out/'crosscheck.json',dict(group='4D',ordinary_result_sha256=pin,full_input_targets=geo['native_targets'],independent_decision_equal=True,updated_issues=stats(allids),any_regional_frame_contact=stats(touched),parents=output,mapper_starts=0,scope='Real 13 former whole-parent-fallback frames versus updated within-4D demand. Contact is a geometric possibility, not evidence of support. Out-of-frame demand cannot be ruled out by a local-only footprint. No whole-wheat residual or full-mapping equivalence claimed.'))
    print('CHECKED_NATIVE_ALTERNATIVE',stats(allids),stats(touched),flush=True)


if __name__=='__main__':main(*map(Path,sys.argv[1:]))
