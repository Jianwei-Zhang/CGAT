"""Conservative fast pilot, not a formal Q0 provider. No ordinary whole-window dispatcher."""
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic

from lgz_core import q0_admission as adm
from lgz_core.common import reverse_complement
from lgz_core.q0_alignments import read_paf
from lgz_core.q0_paths import PairLink, PathGraph, PathPolicy
from lgz_core.q0_source_screen import ordered_screens
from lgz_core.q0_threshold_questions import facing_evidence
from lgz_core.q0_sources import Interval, merged_intervals
from pilot_fast_group_run import GROUP, need, save_layout, write

# Fixed before B/C, independent of A's winners. All lengths are bp.
POLICY = dict(min_reference_support=1000, min_fraction_of_part=.20, min_fraction_of_hull=.50,
              core_trim=4096, max_ordered_gap=25000, max_questions=16, facing_flank=32768,
              max_nonoverlap_question_gap=2000, min_identical_cut_run=100)
TOOL_SHA='cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3'


def footprint(p):
    return p.reference_intervals[0].start,p.reference_intervals[-1].end


def seeds(data):
    """Use ordinary multi-chromosome/strand conflict and complexity screen, no pair propagation."""
    ap=adm.AdmissionPolicy(); selected=[]; rejects=Counter(); ordered=sorted(data.parts.items()); allowed=set()
    for k,p in ordered:
        if any(h.target_name==GROUP and h.mapping_quality is not None and h.mapping_quality>=ap.minimum_reference_mapq
               and h.matches/h.block_length>=ap.minimum_reference_identity for h in data.reference_hits.get(p.source,())):
            allowed.add(k)
    for key,p,result in ordered_screens(data,ordered,allowed,ap,8,adm._request_reference_screen,lambda m: print(m,flush=True)):
        if result is None: rejects['no_group_anchor']+=1; continue
        groups,high,mask,_=result
        if len(groups)!=1 or not high: rejects['ambiguous_or_weak']+=1; continue
        ((chrom,strand),anchors),=groups.items()
        if chrom!=GROUP or (chrom,strand) not in high or not adm._ordered(anchors,strand): rejects['wrong_group_or_order']+=1; continue
        support=merged_intervals(a.source for a in anchors); size=sum(i.length for i in support); hull=Interval(support[0].start,support[-1].end)
        if size<max(POLICY['min_reference_support'],p.interval.length*POLICY['min_fraction_of_part'],hull.length*POLICY['min_fraction_of_hull']):
            rejects['insufficient_span']+=1; continue
        # Do not attach an ambiguous tail or bridge a known ambiguity inside a seed.
        if any(hull.intersection(x) for x in mask): rejects['masked_inside']+=1; continue
        selected.append(adm._placement(p,chrom,strand,hull,support,anchors,(a.evidence_id for a in anchors),kind='reference'))
    return selected,dict(rejects)


def skeleton(placements):
    """Max supported bases on non-overlapping reference cores; never use a core as a cut."""
    rows=[]
    for p in placements:
        a,b=footprint(p); trim=min(POLICY['core_trim'],(b-a)//8); rows.append((b-trim,a+trim,p))
    rows.sort(key=lambda r:(r[0],r[1],r[2].source,r[2].interval,r[2].placement_id))
    ends=[r[0] for r in rows]; best=[0]; prev=[]; take=[]
    for i,(_,lo,p) in enumerate(rows):
        j=bisect_right(ends,lo,0,i); score=best[j]+sum(x.length for x in p.anchor_intervals)
        take.append(score>best[-1]); prev.append(j); best.append(max(best[-1],score))
    answer=[]; i=len(rows)
    while i:
        if take[i-1]: answer.append(rows[i-1][2]); i=prev[i-1]
        else: i-=1
    return answer[::-1]


def oriented(data,p,a,b):
    span=p.source_interval(Interval(a,b)); seq=data.sources[p.source][span.start:span.end]
    return seq if p.orientation=='+' else reverse_complement(seq)


def clean_cut(j, left,right,data):
    half=POLICY['min_identical_cut_run']//2
    if min(j.left_end,j.right_start,left.interval.length-j.left_end,right.interval.length-j.right_start)<half: return False
    a=oriented(data,left,j.left_end-half,j.left_end+half).upper(); b=oriented(data,right,j.right_start-half,j.right_start+half).upper()
    return a==b and adm._passes_complexity(a,adm.AdmissionPolicy())


def compatible_order(l,r):
    a,b=footprint(l); c,d=footprint(r); return a<c and b<d


def build(chain, links, data, extra=()):
    graph=PathGraph(chain,(*links,*extra),data.original_adjacencies,PathPolicy(),first_request=True)
    paths=[]; done=[]; stats=Counter(); prev=None; unresolved=[]
    def valid(path):
        return path is not None and graph.coverage.unique_selected_bp([*done,*((s.source,s.interval) for s in path.slices)]) is not None
    def finish():
        if paths: done.extend((s.source,s.interval) for s in paths[-1].slices)
    for p in chain:
        if prev and paths and paths[-1].nodes[-1]==prev.placement_id and compatible_order(prev,p):
            old=paths[-1]; joined=False
            for join in graph.joins(prev.placement_id,p.placement_id):
                if join.kind=='sequence_overlap' and not clean_cut(join,prev,p,data): continue
                if join.kind=='reference_unknown':
                    if footprint(p)[0]-footprint(prev)[1]>POLICY['max_ordered_gap']: continue
                    known=graph.links.get(tuple(sorted((prev.source,p.source))), ())
                    if not facing_evidence(prev,p,(x for x in known if x.hit.evidence_id not in graph.ambiguous_equivalence_ids),graph.policy): continue
                candidate=graph._score_candidate(old.nodes+(p.placement_id,),old.joins+(join,))
                if not valid(candidate): continue
                paths[-1]=candidate; joined=True
                if join.kind=='reference_unknown': unresolved.append((prev,p))
                break
            if joined: prev=p; continue
            unresolved.append((prev,p))
        if paths and len(done)<sum(len(path.slices) for path in paths): finish()
        single=graph._score_candidate((p.placement_id,),())
        if valid(single): paths.append(single); prev=p
        else: stats['duplicate_or_unusable_seed']+=1; prev=None
    observed=[(s.source,s.interval) for path in paths for s in path.slices]
    need(graph.coverage.unique_selected_bp(observed) is not None,'duplicate homologous occupancy')
    return paths,unresolved,dict(stats)


def facing(p,side):
    n=p.interval.length; width=min(n,POLICY['facing_flank']); return p.source_interval(Interval(n-width,n) if side=='left' else Interval(0,width))


def choose(unresolved, evidence):
    by_pair=defaultdict(list)
    for link in evidence: by_pair[frozenset((link.query_source,link.target_source))].append(link)
    ranked=[]
    for l,r in unresolved:
        if l.source==r.source or not compatible_order(l,r): continue
        delta=footprint(r)[0]-footprint(l)[1]
        if delta>POLICY['max_nonoverlap_question_gap']:continue
        ls,rs=facing(l,'left'),facing(r,'right'); clue=False
        for link in by_pair[frozenset((l.source,r.source))]:
            if (link.hit.strand=='+')!=(l.orientation==r.orientation):continue
            a,b=(ls,rs) if link.query_source==l.source else (rs,ls)
            h=link.hit
            if (a.start<h.query.end+link.query_offset and h.query.start+link.query_offset<a.end and
                    b.start<h.target.end+link.target_offset and h.target.start+link.target_offset<b.end): clue=True;break
        if clue or delta<=-PathPolicy().minimum_anchor_bp:
            ranked.append((not clue,abs(delta),l.placement_id,r.placement_id,l,r))
    ranked.sort(key=lambda x:x[:4]);return [(x[-2],x[-1]) for x in ranked[:POLICY['max_questions']]],len(ranked)


def map_batch(data,pairs,out,tool):
    """Exact PAF on original forward-source axes; reciprocal orientations/offsets stay in PairLink."""
    grouped=defaultdict(list); extra=[]; receipts=[]
    for l,r in pairs: grouped[r.source,facing(r,'right')].append((l,facing(l,'left'),r))
    for number,((ts,tspan),rows) in enumerate(grouped.items(),1):
        with TemporaryDirectory(prefix='4d-end-') as tmp:
            tmp=Path(tmp); target=data.sources[ts][tspan.start:tspan.end];(tmp/'t.fa').write_text('>t\n'+target+'\n'); qlens={};metadata={}; qmap={}
            with (tmp/'q.fa').open('w') as f:
                for i,(l,s,r) in enumerate(rows):
                    name=f'q{i}'; seq=data.sources[l.source][s.start:s.end]; qlens[name]=len(seq); qmap[name]=(l,s)
                    metadata[name]=[asdict(l.source),s.start,s.end,l.orientation,r.orientation,sha256(seq.encode()).hexdigest()];f.write(f'>{name}\n{seq}\n')
            paf=out/f'ends-{number:03}.paf'; cmd=[str(tool),'-x','asm10','-c','--eqx','-t','2','t.fa','q.fa']
            with paf.open('xb') as f,(out/f'ends-{number:03}.log').open('xb') as err:subprocess.run(cmd,cwd=tmp,stdout=f,stderr=err,check=True)
            count=0
            for hit in read_paf(paf,query_lengths=qlens,target_lengths={'t':len(target)},artifact='4D-pilot/'+paf.name):
                l,s=qmap[hit.query_name]; extra.append(PairLink(hit,l.source,ts,s.start,tspan.start));count+=1
            receipts.append(dict(command=cmd,queries=metadata,target=[asdict(ts),tspan.start,tspan.end,sha256(target.encode()).hexdigest()],
                                 query_bp=sum(qlens.values()),target_bp=len(target),paf_sha256=sha256(paf.read_bytes()).hexdigest(),paf_rows=count))
    return extra,receipts


def trial(data,out,common,start):
    tool=Path(shutil.which('minimap2')).resolve();need(sha256(tool.read_bytes()).hexdigest()==TOOL_SHA,'wrong mapper')
    selected,rejects=seeds(data); chain=skeleton(selected);need(chain,'no strong 4D backbone'); src={p.source for p in chain}
    links=[x for x in data.pair_links if x.query_source in src and x.target_source in src]; paths,unresolved,stats=build(chain,links,data)
    selected_at=monotonic(); base=dict(common,policy=POLICY,strong_seeds=len(selected),seed_rejections=rejects,chain=len(chain),relevant_matrix_rows=len(links))
    metrics=save_layout(out,'B',paths,data); write(out/'B.json',dict(base,metrics=metrics,unresolved_pairs=len(unresolved),build_counts=stats,mapper_calls=0,from_input_s=monotonic()-start))
    refine_at=monotonic(); pairs,eligible=choose(unresolved,links); extra,receipts=map_batch(data,pairs,out,tool)
    if extra: paths,_,stats=build(chain,links,data,extra)
    metrics=save_layout(out,'C',paths,data); end=monotonic(); write(out/'C.json',dict(base,metrics=metrics,build_counts=stats,eligible_before_budget=eligible,
        pairs_tested=len(pairs),mapper_calls=len(receipts),new_rows=len(extra),mapper_sha256=TOOL_SHA,receipts=receipts,shared_to_B_backbone_s=selected_at-start,
        refine_and_emit_s=end-refine_at,from_input_s=(selected_at-start)+(end-refine_at),sequential_BC_wall_s=end-start))
