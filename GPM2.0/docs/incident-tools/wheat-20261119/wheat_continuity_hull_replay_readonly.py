"""Compare drop vs original-style anchor-hull fallback from sealed screened anchors.

Does not read DNA, PAF or invoke mapper. Reproduces all three strict admission
sets before selecting a diagnostic downstream candidate. No production writes.
"""
import argparse, gzip, json, multiprocessing as mp, subprocess
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from time import monotonic
from unittest.mock import patch
from hashlib import sha256
import wheat_continuous_dominant_admission_readonly as original
from wheat_continuous_dominant_admission_readonly import adm, Interval, SourceKey, SourceSegment, frozen, encode, decode, risk, old_routes

PARTS = {}
GROUP = '1A'


def hull_candidates(part, groups, high, target='1A'):
    # Only remove the final whole-region support fraction veto. All main-chain,
    # dominance, high-MAPQ and substantial-foreign-chain decisions stay intact.
    policy = replace(original.POLICY, minimum_chain_fraction_of_carried_source=0.0)
    relaxed, detail = original.continuous_candidates(part, groups, high, target, policy)
    out, changed = {}, []
    seen = set()
    for fraction, placements in relaxed.items():
        out[fraction] = []
        for p in placements:
            bp = adm._size(p.anchor_intervals)
            if bp >= original.POLICY.minimum_chain_fraction_of_carried_source * p.interval.length:
                out[fraction].append(p)
                continue
            hull = adm._hull(p.anchor_intervals)
            new = adm._placement(part, p.chromosome, p.orientation, hull, p.anchor_intervals,
                                 p.reference_blocks, p.evidence_ids,
                                 kind='diagnostic_continuous_dominant_anchor_hull')
            out[fraction].append(new)
            if new.placement_id not in seen:
                changed.append({'placement_id': new.placement_id,
                                'whole_source_bp': part.interval.length,
                                'region': [p.interval.start,p.interval.end],
                                'hull': [hull.start,hull.end], 'support_bp': bp,
                                'support_fraction_in_region': bp/p.interval.length,
                                'support_fraction_in_hull': bp/hull.length,
                                'dominance_fraction': detail['dominance_fraction']})
                seen.add(new.placement_id)
    return out, detail, changed


def worker(row):
    source = SourceKey(*row['source'])
    part_id, lookup = PARTS[source]
    if row['length'] != lookup['length'] or row['sequence_sha256'] != lookup['sequence_sha256']:
        raise ValueError('screened source identity changed')
    part = SourceSegment(part_id,source,Interval(0,row['length']),row['sequence_sha256'],0,'start','end')
    groups, high = {}, {}
    for key, anchors, intervals in row['groups']:
        k=tuple(key)
        groups[k]=tuple(adm.ReferenceAnchor(Interval(a,b),Interval(c,d),e) for a,b,c,d,e in anchors)
        high[k]=tuple(Interval(a,b) for a,b in intervals)
    strict, _ = original.continuous_candidates(part,groups,high,target=GROUP)
    hull, detail, restored = hull_candidates(part,groups,high,target=GROUP)
    return {'source':row['source'],'restored':restored,
            'placements':{kind+fraction:[encode(p) for p in rows]
                          for kind, table in (('drop',strict),('hull',hull)) for fraction,rows in table.items()}}


def identities(path):
    with gzip.open(path,'rt') as f:
        result={}
        for raw in f:
            p=decode(json.loads(raw))
            if p.placement_id in result:raise ValueError('duplicate placement')
            result[p.placement_id]=encode(p)
        return result


def run(base, source_owner, owner, workers):
    began=monotonic()
    receipt=json.loads((source_owner/'continuity-admission.json').read_text())
    if receipt['group']!='1A' or receipt['mapper_calls'] or receipt['formal_workspace_modified']:
        raise ValueError('wrong successful admission receipt')
    cache=source_owner/'screened-reference-anchors.jsonl.gz'
    if frozen.digest(cache)!=receipt['outputs'][cache.name]['sha256']:
        raise ValueError('screened anchors cache changed')
    lookup=frozen.checked(base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json',frozen.LOOK)
    PARTS.update({SourceKey(v['dataset'],v['contig']):(k,v) for k,v in lookup.items()})
    old_path=source_owner/'old-grt-q-segments.tsv'
    if frozen.digest(old_path)!='cd9069e54e64cce94ba7d4790afd2c575d85ffc227722b04eca56bf6e04ea847':raise ValueError('old comparator changed')
    old=old_routes(old_path)
    frozen_path=source_owner/'frozen-placements.jsonl.gz'
    if frozen.digest(frozen_path)!=receipt['outputs'][frozen_path.name]['sha256']:raise ValueError('frozen admission changed')
    frozen_rows=[decode(p) for p in identities(frozen_path).values()]
    frozen_refs=[a.reference for p in frozen_rows for a in p.reference_blocks]
    modes=[k+str(f) for k in ('drop','hull') for f in original.FRACTIONS]
    placements={k:[] for k in modes};restored=[];done=0;last=monotonic()
    with gzip.open(cache,'rt') as f, mp.get_context('fork').Pool(workers) as pool:
        for row in pool.imap_unordered(worker,(json.loads(line) for line in f),chunksize=1):
            done+=1
            for p in row['restored']:restored.append({'source':row['source'],**p})
            for mode,encoded in row['placements'].items():placements[mode].extend(decode(p) for p in encoded)
            if monotonic()-last>=30:
                print('HULL_REPLAY_PROGRESS',done,{k:len(v) for k,v in placements.items()},round(monotonic()-began,1),flush=True);last=monotonic()
    reproduced={}
    for f in original.FRACTIONS:
        path=source_owner/('continuous'+str(f)+'-placements.jsonl.gz')
        if frozen.digest(path)!=receipt['outputs'][path.name]['sha256']:raise ValueError('strict artifact changed')
        reproduced[str(f)] = identities(path)=={p.placement_id:encode(p) for p in placements['drop'+str(f)]}
    if not all(reproduced.values()):raise ValueError('strict three-arm admission not reproduced')
    results={};files={}
    for mode, rows in placements.items():
        rows.sort(key=lambda p:(p.source,p.interval,p.orientation,p.placement_id))
        refs=[];categories=defaultdict(list);source_risks=defaultdict(lambda:defaultdict(list));conflict=0
        path=owner/(mode+'-placements.jsonl.gz')
        with gzip.open(path,'wt',compresslevel=1) as out:
            for p in rows:
                out.write(json.dumps(encode(p),separators=(',',':'))+'\n')
                refs.extend(a.reference for a in p.reference_blocks)
                rr,ss=risk(p,old)
                conflict+=any(k!='same_group_same_orientation' and vs for k,vs in ss.items())
                for k,vs in rr.items():categories[k].extend(vs)
                for k,vs in ss.items():source_risks[k][p.source].extend(vs)
        results[mode]={'placements':len(rows),'sources':len({p.source for p in rows}),
                       'source_bp_sum':sum(p.interval.length for p in rows),
                       'max_placement_bp':max((p.interval.length for p in rows),default=0),
                       'reference_bp':adm._size(refs),'combined_reference_bp':adm._size(refs+frozen_refs),
                       'old_q0_conflict_placements':conflict,
                       'old_q0_reference_bp':{k:adm._size(vs) for k,vs in categories.items()},
                       'old_q0_source_bp':{k:sum(adm._size(vs) for vs in smap.values()) for k,smap in source_risks.items()}}
        files[path.name]={'sha256':frozen.digest(path),'bytes':path.stat().st_size}
    # A comparator-only preliminary choice. Zero old-route conflicts is a
    # conservative preference, not proof of biological precision.
    eligible=[k for k,v in results.items() if v['old_q0_conflict_placements']==0]
    best=max(eligible,key=lambda k:(results[k]['combined_reference_bp'],-results[k]['placements'],results[k]['max_placement_bp'],int(k[-2:]))) if eligible else None
    report={'schema':'wheat_continuity_hull_cache_replay_v1','group':GROUP,
            'source_receipt_sha256':frozen.digest(source_owner/'continuity-admission.json'),
            'screened_cache_sha256':receipt['outputs'][cache.name]['sha256'],
            'strict_three_arms_reproduced':reproduced,'processed_sources':done,
            'variants':results,'restored_regions':sorted(restored,key=lambda r:-r['whole_source_bp']),
            'selected_mode':best,'outputs':files,'mapper_calls':0,'formal_workspace_modified':False,
            'elapsed_s':monotonic()-began,'selection_rule':'zero old-Q0 conflicts; maximize actual combined reference union, then fewer placements, longer maximum, higher dominance threshold',
            'limitations':['Low anchor density is not by itself a measurement of repeat content.',
                           'Hull fallback is allowed even if support/hull remains below 20%, matching the original extent decision.',
                           'Admission comparison is not a selected-path or biological precision acceptance.']}
    frozen.write(owner/'hull-replay.json',report)
    print('HULL_REPLAY_DONE',json.dumps({k:results[k] for k in results}), 'CHOSEN',best,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('source_owner',type=Path);p.add_argument('owner',type=Path);p.add_argument('--workers',type=int,default=4);a=p.parse_args()
    owner=a.owner.resolve();base=a.base.resolve();source=a.source_owner.resolve()
    if owner.parent!=base or source.parent!=base or not owner.name.startswith('q0-continuity-') or owner.stat().st_mode&0o077:
        raise ValueError('private owner required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external command forbidden')):
        run(base,source,owner,a.workers)
