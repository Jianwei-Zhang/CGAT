"""Read-only user-gate audit: distinguish inherited unselected candidates.

This never changes paths or erases the original all-candidate-zero gate. Source
names below identify the four incident checks only; they do not drive admission.
"""
import argparse,gzip,json,subprocess
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch
from compare_wheat_local_only_paths import load_arm
from wheat_selection_checkpoint import decode
from wheat_reference_funnel_readonly import digest,write
from wheat_continuity_gap_rescue_readonly import need,load_rows
from wheat_continuous_dominant_admission_readonly import old_routes,risk
from wheat_top_chain_cross_readonly import cross_source_overlaps


def audit(base,owner):
    file=owner/'inversion-validation.json'
    need(digest(file)=='0a56fd27fb04995b5da723ced002d08f0edb87fa6c2e425024c6eef32eb92e57','different trial result')
    report=json.loads(file.read_text())
    _,_,frozen,_,_=load_arm(base/'q0-whole-local-maps.soHq9Z6J','d23a49af479b6c9b81916518e8034d4044ea31b5c97229c5d0ce1624138fc9d4','whole-wheat-local-supplement-v1')
    oldfile=base/'q0-continuity-20261126.RAbGvNba/old-grt-q-segments.tsv'
    need(digest(oldfile)=='cd9069e54e64cce94ba7d4790afd2c575d85ffc227722b04eca56bf6e04ea847','old comparator changed')
    old=old_routes(oldfile);new_conflicts={};inherited={};paths={};cases={}
    incident={'3B':{'ptg000449l','ptg000508l','ptg000447l'},'3D':{'ptg000664l'}}
    for group,row in report['results'].items():
        meta=report['admission'][group];pfile=owner/(group+'-placements.jsonl.gz')
        need(digest(pfile)==meta['placements_sha256'],'new placement file changed')
        new=load_rows(pfile);ids={p.placement_id for p in new};flags=[]
        for p in new:
            _,ss=risk(p,old)
            for kind,spans in ss.items():
                if kind!='same_group_same_orientation' and spans:
                    flags.append({'placement_id':p.placement_id,'category':kind})
        new_conflicts[group]=flags
        inherited[group]=[]
        for flag in report['admission_conflicts'][group]:
            pid=flag['placement_id']
            need(pid in frozen[group] and pid not in ids,'conflict is not an unchanged frozen candidate')
            inherited[group].append({**flag,'frozen_placement_record_sha256':frozen[group][pid]})
        pathfile=owner/row['path_file'];need(digest(pathfile)==row['path_sha256'],'selected path changed')
        with gzip.open(pathfile,'rt') as f:paths[group]=decode(json.load(f))
        selected={s.placement_id for s in paths[group].slices}
        need(not selected & {v['placement_id'] for v in inherited[group]},'inherited warning reached output')
        for name in sorted(incident.get(group,())):
            admitted=[p for p in new if p.source.contig==name]
            slices=[s for s in paths[group].slices if s.source.contig==name]
            flipped=[]
            for s in slices:
                for iv,chr_,orientation in old.get(s.source,()):
                    if iv.intersection(s.interval) is not None and (chr_!=group or orientation!=s.orientation):flipped.append(s.placement_id)
            need(not flipped,'incident source is still locally flipped')
            cases[name]={'group':group,'new_admission':[{'interval':[p.interval.start,p.interval.end],'orientation':p.orientation} for p in admitted],
                         'selected':[{'interval':[s.interval.start,s.interval.end],'orientation':s.orientation} for s in slices],
                         'not_selected':not slices,'local_flip_remaining':False}
        need(row['native_score_and_duplicate_gate_passed'] and row['incumbent_lower_bounds_passed'],'exact path or frozen lower bound failed')
        need(not row['risk']['conflict_flags'] and not row['reference_order_flags'],'selected conflict/order failure')
        need(row['guard']['union_audit']['rejected_large_map_unions']==0,'long-map rejection requires investigation')
    conflicts=cross_source_overlaps(paths)
    need(not conflicts and not any(new_conflicts.values()),'new candidate or source-occupancy conflict')
    final={'schema':'wheat_inversion_preservation_user_gate_v1','trial_report_sha256':digest(file),
           'original_all_candidate_zero_gate':report['three_group_policy_checks_passed'],
           'user_gate':'no_new_admission_conflicts_and_no_selected_conflicts_and_no_cross_group_source_reuse',
           'user_requested_checks_passed':True,'new_admission_conflicts':new_conflicts,
           'unchanged_unselected_frozen_candidate_warnings':inherited,'incident_sources':cases,
           'cross_group_source_conflicts':conflicts,'production_integration_eligible':True,
           'formal_q0_lgz':'HOLD','whole_wheat_22_group_acceptance':False,'mapper_calls':0,
           'scope':'Reopened sealed paths/new candidates and verified all original 22-group checkpoint records. Does not change the original result or equate old-Q0 direction with biological truth.'}
    write(owner/'inversion-user-gate-audit.json',final)
    print('INVERSION_USER_GATE_DONE',json.dumps(final),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('owner',type=Path);a=p.parse_args()
    need(a.owner.resolve().parent==a.base.resolve() and a.owner.stat().st_mode&0o077==0,'private sibling owner required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external programs forbidden')):audit(a.base,a.owner)
