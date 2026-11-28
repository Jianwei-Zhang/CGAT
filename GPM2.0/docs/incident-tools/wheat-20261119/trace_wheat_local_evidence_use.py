"""Read-only attribution of the 15 added projections after the whole-wheat comparison seals.

No mapper, draft selection, FASTA or baseline checkpoint reads. Output on stdout only.
"""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import json
import re
import sys

from compare_wheat_local_only_paths import BASE, GROUPS, KIT, MAPPING, READBACK, checkpoint, get, need
from lgz_core.q0_alignments import parse_paf_line


def inventory(owner):
    report=get(owner/'result.json',MAPPING); ids={}; windows=set(); batches=set(); total=0
    need(report['native_mapper_starts']==0 and len(report['receipts'])==report['batches']==15,'wrong mapping inventory')
    for i,pin in enumerate(report['receipts'],1):
        row=get(owner/f'batch-{i:02d}.json',pin);task=row['task'];tid=task['task_id'];rel=task['paf']
        need(row['index']==i and re.fullmatch(r'q0-regional-project-[0-9a-f]{24}',tid) and tid not in batches
             and rel==f'grt/evidence/q0_prepare/regional/projects/{tid}/result.paf','foreign or duplicate projection')
        batches.add(tid);windows.add(row['query']); path=owner/'workspace'/rel
        need(path==path.resolve(),'linked projection'); raw=path.read_bytes();total+=len(raw)
        need(sha256(raw).hexdigest()==row['projected_sha256'] and len(raw)==row['projected_bytes'],'projection bytes differ')
        queries=set(task['query_ids']);targets=set(task['target_ids']);count=0
        for n,line in enumerate(raw.decode('utf-8').split('\n'),1):
            if not line.strip() or line.startswith('#'):continue
            hit=parse_paf_line(line,artifact=rel,line_number=n)
            need(hit.query_name in queries and hit.target_name in targets and hit.evidence_id not in ids,'foreign or repeated evidence')
            ids[hit.evidence_id]=i;count+=1
        need(count==row['projected_rows'],'row count differs')
    need(len(ids)==report['projected_rows']==1660 and len(windows)==report['windows']==13 and total==report['projected_bytes'],'incomplete projections')
    return ids


class Trace:
    def __init__(self, ids):
        self.ids=ids;self.placements=defaultdict(dict)

    def placement(self,g,pid,evidence):
        hits=self.ids.keys() & evidence
        if hits:self.placements[g][pid]=hits

    def finish(self,paths):
        kinds=('admitted_placement','selected_placement','selected_overlap_join','selected_other_join')
        distinct={k:set() for k in kinds};groups={}
        for g,path in paths.items():
            local=self.placements[g]; counts=Counter()
            def register(kind,hits):
                if hits:distinct[kind].update(hits);counts[kind]+=1
            for hits in local.values():register('admitted_placement',hits)
            if path is not None:
                for p in set(path.nodes):register('selected_placement',local.get(p))
                for j in path.joins:
                    register('selected_overlap_join' if j.kind=='sequence_overlap' else 'selected_other_join',self.ids.keys() & j.evidence_ids)
            groups[g]={k:counts[k] for k in kinds}
        cited=set().union(*distinct.values());by_batch=Counter(self.ids[e] for e in cited);totals=Counter(self.ids.values())
        return dict(input_rows=len(self.ids),distinct_rows_by_role={k:len(v) for k,v in distinct.items()},
                    distinct_rows_cited=len(cited),rows_not_explicitly_cited=len(self.ids)-len(cited),records_by_group=groups,
                    batches=[dict(batch=i,rows=totals[i],cited=by_batch[i]) for i in range(1,16)],
                    scope='Listed evidence IDs only. Roles overlap. Placement and non-overlap join IDs may be inherited. '
                          'Not listed does not mean never evaluated or no effect on competition; a cited ID is not proof of necessity or gap closure.')


def sealed(owner,log,relative,job):
    text=(owner/log).read_text()
    need(re.findall(r'^[ \t]*JOB_ID:[ \t]*(\d+)[ \t]*$',text,re.M)==[str(job)] and
         re.findall(r'^[ \t]*EXIT_CODE:[ \t]*(-?\d+)[ \t]*$',text,re.M)==['0'],'missing successful scheduler receipt')
    pins=[line.split('  ')[0] for line in text.splitlines() if re.fullmatch('[0-9a-f]{64}  '+re.escape(relative),line)]
    need(len(pins)==1,'no unique sealed output: '+relative);return get(owner/relative,pins[0]),pins[0]


def trace(maps,new,comparison):
    doc,comparison_pin=sealed(comparison,'compare_43086929.out','comparison.json',43086929)
    s,pin=sealed(new,'local_whole_43084475.out','result/summary.json',43084475)
    need(doc['old_summary']==BASE and doc['new_summary']==pin and doc['local_mapping']==s['local_mapping']==MAPPING
         and doc['local_readback']==READBACK and set(doc['groups'])==set(GROUPS),'different or incomplete comparison')
    need(s['schema']=='wheat_whole_local_supplement_readmission_v1' and s['kit_sha256']==KIT and s['regional']==59293
         and s['native']==4 and s['mapper_starts']==0 and s['published_q0'] is False,'not the local-only draft')
    ids=inventory(maps);need(doc['new_pair_rows']==s['pair_rows']==doc['old_pair_rows']+len(ids),'unexpected admitted pair-input delta')
    use=Trace(ids);binding=['whole-wheat-local-supplement-v1',*(s[k] for k in ('inputs','first_request','regional_inventory','kit_sha256','evidence_digest')),32]
    chain,_,paths=checkpoint(new/'selection',binding,on_placement=use.placement);need(chain==s['selection_chain'],'selection not sealed')
    return dict(schema='wheat_local_projection_use_v1',comparison=comparison_pin,new_summary=pin,mapping=MAPPING,**use.finish(paths))


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--inventory':
        ids=inventory(Path(sys.argv[2]).resolve());print(json.dumps({'rows':len(ids),'id_digest':sha256('\n'.join(sorted(ids)).encode()).hexdigest()}))
    else:
        need(len(sys.argv)==4,'expected: map-owner new-owner comparison-owner');print(json.dumps(trace(*(Path(p).resolve() for p in sys.argv[1:])),indent=2,sort_keys=True))
