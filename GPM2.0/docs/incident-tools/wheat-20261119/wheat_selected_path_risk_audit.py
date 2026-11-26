"""Audit downloaded diagnostic selected slices against existing old-Q0 metadata.

No mapper. Old route and source-name labels are comparators, not biological
truth. Reference overlap and source-interval conflict are reported separately.
"""
import argparse,csv,gzip,json,re
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from lgz_core import q0_admission as adm
from lgz_core.q0_sources import Interval,merged_intervals
from wheat_selection_checkpoint import decode
from wheat_local_chain_primitives import clipped


def need(ok,text):
    if not ok:raise ValueError(text)


def footprint(path,placements):
    refs=[]
    for sl in path.slices:
        p=placements[sl.placement_id]
        refs.extend(a.reference for a in clipped(p.reference_blocks,sl.interval,p.orientation))
    return {'source_bp':sum(s.interval.length for s in path.slices),'reference_union_bp':size(refs),'slices':len(path.slices),'gap_count':sum(j.n_bp>0 for j in path.joins),'gap_placeholder_bp':sum(j.n_bp for j in path.joins),'score':path.score}


def size(rows):return sum(i.length for i in merged_intervals(rows))


def minus(rows,mask):
    mask=merged_intervals(mask);out=[];j=0
    for iv in merged_intervals(rows):
        while j<len(mask) and mask[j].end<=iv.start:j+=1
        k=j;cursor=iv.start
        while k<len(mask) and mask[k].start<iv.end:
            block=mask[k]
            if cursor<block.start:out.append(Interval(cursor,min(iv.end,block.start)))
            cursor=max(cursor,block.end)
            if cursor>=iv.end:break
            k+=1
        if cursor<iv.end:out.append(Interval(cursor,iv.end))
    return out


def run(root,mode):
    receipt=json.loads((root/('candidate-selection-'+mode+'.json')).read_text());records=receipt['results'][mode]['searches'];paths={}
    for key,row in records.items():
        raw=(root/row['path_file']).read_bytes();need(sha256(raw).hexdigest()==row['path_sha256'],'selected path changed');paths[key]=decode(json.loads(gzip.decompress(raw)))
    wanted={s.placement_id for path in paths.values() for s in path.slices};placements={};admission=json.loads((root/'local-admission.json').read_text())
    for name in ('frozen-placements.jsonl.gz',mode+'-placements.jsonl.gz'):
        need(sha256((root/name).read_bytes()).hexdigest()==admission['outputs'][name]['sha256'],'admission artifact changed')
        with gzip.open(root/name,'rt') as f:
            for line in f:
                row=json.loads(line)
                if row['Placement'][0] in wanted:
                    p=decode(row);need(p.placement_id not in placements,'duplicate selected ID');placements[p.placement_id]=p
    need(set(placements)==wanted,'missing selected placements');old=defaultdict(list);bp=0
    with (root/'old-grt-q-segments.tsv').open() as f:
        for r in csv.DictReader(f,delimiter='\t'):
            if r['q_version']!='q0' or r['segment_kind']!='source':continue
            iv=Interval(int(r['source_start'])-1,int(r['source_end']));need(iv.length==int(r['q_end'])-int(r['q_start'])+1,'old coordinate convention differs');old[r['dataset_name'],r['contig_name']].append((iv,r['chr'],r['orientation']));bp+=iv.length
    need(bp==14097144889-100300,'old q0 source extent differs');results={}
    for key,path in paths.items():
        observed=json.loads(json.dumps(footprint(path,placements)));need(all(records[key]['metrics'][k]==v for k,v in observed.items()),'selected metrics differ');refs=defaultdict(list);labels=defaultdict(list);source_conflicts=defaultdict(lambda:defaultdict(list));examples=[]
        for sl in path.slices:
            p=placements[sl.placement_id];need(sl.source==p.source and sl.orientation==p.orientation and p.interval.contains(sl.interval),'slice escapes placement');anchors=clipped(p.reference_blocks,sl.interval,p.orientation);m=re.match(r'JM19flye([ABD])_',p.source.contig);label=m.group(1) if m else 'unlabelled';labels[label].extend(a.reference for a in anchors)
            for iv,group,strand in old.get((p.source.dataset,p.source.contig),()):
                ov=iv.intersection(sl.interval)
                if ov is None:continue
                category='same_1A_same_orientation' if group=='1A' and strand==p.orientation else ('same_1A_opposite_orientation' if group=='1A' else 'other_chromosome');projected=[a.reference for a in clipped(anchors,ov,p.orientation)];refs[category].extend(projected)
                if group!='1A' and group[-1] in 'BD':refs['other_subgenome'].extend(projected);source_conflicts['other_subgenome'][p.source].append(ov)
                if category!='same_1A_same_orientation':
                    source_conflicts[category][p.source].append(ov);examples.append({'placement_id':p.placement_id,'source':[p.source.dataset,p.source.contig],'selected_source_interval':[sl.interval.start,sl.interval.end],'old_group':group,'old_orientation':strand,'new_orientation':sl.orientation,'source_overlap_bp':ov.length,'reference_overlap_bp':size(projected)})
        bd=labels['B']+labels['D'];results[key]={'metrics_verified':observed,'reference_overlap_with_old_q0_bp':{k:size(v) for k,v in refs.items()},'source_overlap_conflict_bp':{k:sum(size(v) for v in by.values()) for k,by in source_conflicts.items()},'reference_bp_by_name_label':{k:size(v) for k,v in labels.items()},'B_D_only_reference_bp_without_A_or_unlabelled':size(minus(bd,labels['A']+labels['unlabelled'])),'largest_old_route_conflict_examples':sorted(examples,key=lambda r:(-r['reference_overlap_bp'],-r['source_overlap_bp']))[:12]}
    report={'schema':'wheat_1A_selected_path_risk_audit_v1','mode':mode,'selection_report_sha256':sha256((root/('candidate-selection-'+mode+'.json')).read_bytes()).hexdigest(),'old_metadata_sha256':sha256((root/'old-grt-q-segments.tsv').read_bytes()).hexdigest(),'results':results,'mapper_calls':0,'formal_workspace_modified':False,'limitations':['Old Q0 and source-name labels are not independent biological truth.','Conflict means a source interval was placed on a different chromosome/orientation by the old route; it is a review flag, not proof which route is wrong.','Reference category unions may overlap and must not be added as disjoint losses.','Only actual selected slice intersections are audited, not all admitted candidate hulls.']}
    (root/('selected-path-risk-'+mode+'.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:{n:v for n,v in row.items() if n!='largest_old_route_conflict_examples'} for k,row in results.items()},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--mode',choices=('dominant90','regional'),required=True);a=p.parse_args();run(a.root.resolve(),a.mode)
