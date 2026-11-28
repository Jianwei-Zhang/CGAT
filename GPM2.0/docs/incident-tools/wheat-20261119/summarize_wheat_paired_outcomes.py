"""Summarize completed real wheat controls without exporting source names or coordinates.

Keep offered cuts, selected local paths, and independently re-admitted paths separate.
Initial-draft overlap of a changed request is descriptive, not permission to accept the original matrix.
"""
from hashlib import sha256
import json
from pathlib import Path
import sys

from plan_wheat_panel_neighborhoods import PANEL, pinned_panel
from probe_wheat_native_pair_scope import checked
from readmit_wheat_panel import HOODS
from wheat_selection_checkpoint import need


def footprint(rows):
    if rows is None:
        return None  # unbounded request is not an empty set
    out = {}
    for source, spans in rows:
        k = (source['dataset'], source['contig'])
        need(k not in out and all(0 <= a < b for a,b in spans) and
             all(first[1] < second[0] for first, second in zip(spans, spans[1:])), 'bad request geometry')
        out[k] = spans
    return out


def intersection(left, right):
    i = j = 0
    while i < len(left) and j < len(right):
        a,b = left[i]; c,d = right[j]
        if max(a,c) < min(b,d): yield max(a,c), min(b,d)
        i += b <= d; j += d <= b


def request_delta(full, reduced, original):
    a,b = footprint(full),footprint(reduced)
    if a is None or b is None:
        return dict(full_unbounded=a is None, reduced_unbounded=b is None, same=a==b)
    mass=lambda s: sum(y-x for x,y in s)
    fo=ro=fi=ri=0
    for k in a.keys() | b.keys():
        f,r,o=a.get(k,[]),b.get(k,[]),original.get(k,[]); both=list(intersection(f,r))
        fo+=mass(f)-mass(both); ro+=mass(r)-mass(both)
        common=mass(intersection(both,o)); fi+=mass(intersection(f,o))-common; ri+=mass(intersection(r,o))-common
    return dict(full_only_bp=fo,reduced_only_bp=ro,full_only_in_frozen_demand_bp=fi,
                reduced_only_in_frozen_demand_bp=ri,same=fo==ro==0)


def load(path):
    data=path.read_bytes(); return json.loads(data),sha256(data).hexdigest()


def summary(panel_path, questions_path, mapping_path, fixed_path, fresh_path):
    panel,pin=pinned_panel(panel_path);demand=footprint(checked(questions_path,panel['questions'])['source_intervals'])
    mapping,ms=load(mapping_path);fixed,cs=load(fixed_path);fresh,rs=load(fresh_path)
    need(fixed['schema']=='wheat_shortlist_paired_geometry_v1' and fresh['schema']=='wheat_paired_local_fresh_admission_v1'
         and fixed['mapping']==mapping and fresh['mapping_sha256']==ms and fresh['neighborhoods']==HOODS[pin]
         and fixed['panel']==fresh['panel']==mapping['panel']==pin, 'mixed trial receipts')
    need(fresh['published_q0'] is False and fixed['formal_q0'] is False and mapping['formal_q0'] is False, 'wrong output role')
    strata=[x['stratum'] for x in panel['cases']];keys=[x['join'] for x in panel['cases']]
    need(len(keys)==len(set(keys))==len(set(strata))==(8 if pin==PANEL else 4) and all([r['join'] for r in v['cases']]==keys for v in (fixed,fresh)), 'incomplete or reordered controls')
    fg=fixed['retained_geometry_shared'];fa=fixed['retained_geometry_only_full'];ra=fixed['retained_geometry_only_reduced']
    need(fg+fa==fixed['full_rows'].get('retained',0) and fg+ra==fixed['reduced_rows'].get('retained',0)
         and fixed['reduced_rows'].get('excluded',0)==0,'incomplete geometry accounting')
    cases=[]
    for pre,fx,fr in zip(panel['cases'],fixed['cases'],fresh['cases']):
        need(pre['stratum']==fx['stratum']==fr['stratum'] and pre['chromosome']==fx['chromosome']==fr['group'],'changed controls')
        expect=[pre['kind'],pre['left_cut'],pre['right_cut']];need(fx['old']==expect,'wrong expected cut')
        offered=[expect in fx[k]['cuts'] for k in ('full','reduced')]; f,r=[fr['arms'][k] for k in ('full','reduced')]
        d=request_delta(f['request'],r['request'],demand);selected=f['selected']==r['selected'];placed=f['placed']==r['placed']
        need((selected,placed,d['same'])==(fr['same_selected'],fr['same_placements'],fr['same_request']),'inconsistent neighborhood results')
        samecuts=sorted(fx['full']['cuts'])==sorted(fx['reduced']['cuts']); need(samecuts==fx['same_cuts'],'inconsistent fixed cuts')
        calibration=fr['arms']['original_background']['frozen_junction_reproduced']; rep=[v['frozen_junction_reproduced'] for v in (f,r)]
        cases.append(dict(stratum=pre['stratum'],chromosome=pre['chromosome'],partner_retained=pre['partner_retained'],
                          query_has_direct_demand=pre['q'] in panel['retained'],
                          frozen_kind=pre['kind'],fixed_same_available_cuts=samecuts,fixed_offers_old_full=offered[0],
                          fixed_offers_old_reduced=offered[1],original_background_selects_old=calibration,
                          fresh_selects_old_full=rep[0],fresh_selects_old_reduced=rep[1],fresh_same_paths=selected,
                          fresh_same_placements=placed,fresh_request_delta=d))
    full=mapping['mapper']['full']['seconds'];reduced=mapping['mapper']['reduced']['seconds'];need(min(full,reduced)>0,'bad mapper timing')
    decision=('no_unconditional_replacement_observed_local_decision_changed' if any(not c['fresh_same_paths'] or not c['fresh_request_delta']['same'] for c in cases)
              else 'no_mapper_speedup_in_pilot_retain_original' if reduced>=full
              else 'withhold_replacement_bounded_panel_only')
    return dict(schema='wheat_paired_native_control_summary_v1', panel=pin,questions=panel['questions'],
                evidence=dict(mapping=ms,fixed_readout=cs,fresh_readmission=rs,common=fresh['common_sha256'],neighborhoods=HOODS[pin]),
                mapper_s=dict(full=full,reduced=reduced),shared_prepare_verify_extract_s=mapping['setup_verify_extract_s'],
                included_target_selection_s=mapping.get('included_target_selection_s'),
                full_over_reduced_mapper_time=round(full/reduced,3),geometry=dict(retained_shared=fg,retained_only_full=fa,
                retained_only_reduced=ra,full_rows_to_excluded=fixed['full_rows'].get('excluded',0)),
                heldout_old_pair_rows=fresh['excluded_old_pair_rows'],cases=cases,decision=decision,
                limits='Preregistered short queries, not the retired parents. Timings are single serial-arm measurements on one node, not whole-workflow speedup. Request deltas are per local cohort and must not be summed as whole-wheat totals. A missing frozen junction in both arms is not a successful positive control.')


if __name__=='__main__':
    print(json.dumps(summary(*map(Path,sys.argv[1:])),indent=2,sort_keys=True))
