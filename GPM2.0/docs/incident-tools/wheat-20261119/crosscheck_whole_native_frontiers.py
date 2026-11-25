"""Join the full refreshed question list to the two native fallback parents and the actual 13 old frames."""
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
import gzip,json,sys
from census_wheat_q0_fork import bind,bounded,require,write
from crosscheck_native_4d_frontiers import relate_frames
from lgz_core.q0_sources import Interval,SourceKey,merged_intervals
from lgz_core.q0_threshold_acceptance import decode,record


def main(base,owner,out):
    result=owner/'result';sraw=bounded(result/'summary.json',1<<20);pin=sha256(sraw).hexdigest();report=json.loads(sraw)
    require(any(pin+'  result/summary.json' in f.read_text().splitlines() for f in owner.glob('whole_*.out')),'unsealed full result')
    require(report['regional']==59278 and report['native']==4 and report['mapper_starts']==0 and not report['published_q0'],'not the complete cached staging run')
    snap,root,lookup,order,lens=bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json');details=json.loads(gzip.decompress(bounded(result/'updated-questions.json.gz',64<<20,report['questions'])));issues=details['issues'];by_src=defaultdict(list);union=defaultdict(list);after=decode(details['source_intervals'],lens);before_sha='1a7d9f53498e6376ef93d800b2b8346dd3e593e04f2825cc2e2022673d3f83a5';prior=json.loads(gzip.decompress(bounded(base/'q0-whole-dispatch-20261125.9Icl9fR7/result/issues.json.gz',8<<20,before_sha)))['issues'];require(details['evidence_inventory']==report['evidence_digest'] and details['counts']==report['counts'],'foreign residual')
    for i,q in enumerate(issues):
        for ds,seq,a,b in q['spans']:
            s=SourceKey(ds,seq);iv=Interval(a,b);union[s].append(iv);by_src[s].append((iv,i))
    require(after is None or record({s:merged_intervals(v) for s,v in union.items()})==details['source_intervals'],'issue list does not match request')
    geo,parents,all_counts,target_counts,touched=relate_frames(base,snap,root,lookup,order,lens,issues,by_src);current={(g,r['kind'],r['id']) for r in issues for g in r['groups']};old={(r['group'],r['kind'],r['id']) for r in prior};groups=defaultdict(Counter)
    for key in old|current:groups[key[0]][('retained_id_' if key in old and key in current else 'new_id_' if key in current else 'absent_id_')+key[1]]+=1
    contacts=[dict(index=i,kind=issues[i]['kind'],groups=issues[i]['groups'],id=issues[i]['id']) for i in sorted(touched)];write(out/'regional-question-links.json',contacts)
    write(out/'comparison.json',dict(summary_sha256=pin,updated_questions=report['questions'],has_path=details['has_path'],first_request=report['first_request'],counts=all_counts,after=report['after'],actions=report['actions'],old_state_ids=len(old),new_state_ids=len(current),by_group=groups,old_window_target_contact=target_counts,parents=parents,geometric_links_sha256=sha256((out/'regional-question-links.json').read_bytes()).hexdigest(),mapper_starts=0,scope='Updated whole-wheat planning-only selection against the unchanged original target matrix and historical frames. A missing stable question ID can reflect a different selected path, not necessarily closure. Geometric contact is not proof a mapper would resolve it.'))
    print('FULL_FALLBACK_COMPARISON',report['actions'],all_counts,target_counts,flush=True)


if __name__=='__main__':main(*map(Path,sys.argv[1:]))
