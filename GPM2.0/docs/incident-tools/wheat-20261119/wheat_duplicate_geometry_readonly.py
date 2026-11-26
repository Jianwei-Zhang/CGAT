"""Project frozen duplicate units back to actual skipped source coordinates."""
import argparse,gzip,json,subprocess
from pathlib import Path
from unittest.mock import patch
from lgz_core.q0_sources import Interval,merged_intervals
from wheat_continuity_gap_rescue_readonly import dp_nodes,append_options,candidate_slices,need,adm
from wheat_local_chain_selection_readonly import checked_pickle
from wheat_indexed_anchor_support_readonly import AnchorSupportIndex,indexed_native
from wheat_reference_funnel_readonly import digest,write
from wheat_selected_path_risk_audit import minus
from wheat_continuous_dominant_admission_readonly import legacy


def duplicate_intervals(model,prefix,source,interval):
    covered,duplicate,_=model._project_selected(prefix)
    need(not duplicate,'prefix itself duplicates')
    out=[]
    for i in model._overlapping_atoms(source,interval):
        atom=model.atoms[i][1];root,flip=model.units[i]
        overlap=atom.intersection(interval)
        local=Interval(atom.end-overlap.end,atom.end-overlap.start) if flip else Interval(overlap.start-atom.start,overlap.end-atom.start)
        for previous in covered.get(root,()):
            hit=local.intersection(previous)
            if hit:
                out.append(Interval(atom.end-hit.end,atom.end-hit.start) if flip else Interval(atom.start+hit.start,atom.start+hit.end))
    return merged_intervals(out)


def run(source,out):
    seal=json.loads((source/'continuous-graph.json').read_text())
    graph=checked_pickle(source/'continuous-graph.pickle',seal['sha256'])
    nodes,_=dp_nodes(graph);current=None;rows=[]
    for node in nodes:
        options=append_options(graph,current,node)
        if options:current=min(options,key=graph.rank);continue
        p=graph.placements[node];hull=adm._hull(a.source for a in p.reference_blocks)
        joins=graph.joins(current.nodes[-1],node)
        need(len(joins)==1 and joins[0].kind=='reference_unknown','different failed-node join geometry')
        proposed=candidate_slices(graph,current.nodes+(node,),current.joins+joins)
        duplicate=duplicate_intervals(graph.coverage,proposed[:-1],*proposed[-1])
        need(bool(duplicate),'exact reject not explained by projected duplicates')
        safe=minus((p.interval,),duplicate)
        conflicts=[]
        for sl,(src,iv) in zip(current.slices,proposed[:-1]):
            spans=duplicate_intervals(graph.coverage,((src,iv),),*proposed[-1])
            if not spans:continue
            other=graph.placements[sl.placement_id]
            blocks=graph.homologous_blocks(p,other)
            direct=[p.source_interval(b.left) for b,e in blocks
                    if other.source_interval(b.right).intersection(iv)]
            conflicts.append({'node':sl.placement_id,'source':[src.dataset,src.contig],
                              'source_bp':iv.length,'duplicate_bp':adm._size(spans),
                              'direct_block_duplicate_bp':legacy.overlap_bp(spans,direct)})
        rows.append({'node':node,'source':[p.source.dataset,p.source.contig],'source_bp':p.interval.length,
                     'overhang_bp':p.interval.length-hull.length,'duplicate_source_bp':adm._size(duplicate),
                     'duplicate_inside_anchor_hull_bp':legacy.overlap_bp(duplicate,(hull,)),
                     'duplicate_overlapping_actual_reference_anchor_bp':legacy.overlap_bp(duplicate,(a.source for a in p.reference_blocks)),
                     'duplicate_regions':len(duplicate),'safe_contiguous_regions':len(safe),
                     'longest_duplicate_free_region_bp':max((v.length for v in safe),default=0),
                     'terminal_only_duplicates':len(safe)==1,'conflicts':conflicts,
                     'duplicate_intervals':[[i.start,i.end] for i in duplicate]})
    need(len(rows)==22,'different frozen skip count')
    result={'schema':'wheat_skipped_duplicate_geometry_v1','graph_sha256':seal['sha256'],
            'rows':rows,'summary':{'skipped_nodes':len(rows),'source_bp':sum(r['source_bp'] for r in rows),
                'overhang_bp':sum(r['overhang_bp'] for r in rows),'duplicate_source_bp_sum':sum(r['duplicate_source_bp'] for r in rows),
                'duplicate_inside_anchor_hull_bp_sum':sum(r['duplicate_inside_anchor_hull_bp'] for r in rows),
                'duplicate_overlapping_actual_reference_anchor_bp_sum':sum(r['duplicate_overlapping_actual_reference_anchor_bp'] for r in rows),
                'terminal_only_nodes':sum(r['terminal_only_duplicates'] for r in rows)},
            'mapper_calls':0,'formal_workspace_modified':False,'native_gate_unchanged':True,
            'limitations':['Source sums are not reference coverage unions.','Coverage units include transitive equivalences; direct paired-block overlap is reported separately.','A unit shared by two sources is an engine equivalence, not independent proof of biological duplication.']}
    write(out/'skipped-duplicate-geometry.json',result)
    print('DUPLICATE_GEOMETRY_DONE',json.dumps(result['summary']),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('owner',type=Path);a=p.parse_args()
    need(a.owner.resolve().parent==a.source.resolve().parent and a.owner.stat().st_mode&0o077==0,'private sibling owner required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external program forbidden')),indexed_native(AnchorSupportIndex()):run(a.source,a.owner)
