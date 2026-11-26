"""Cache-only regional fallback. Unsearched matrices never produce mapping receipts."""
from .common import stable_id
from .q0_sources import Q0EvidenceError

PHASES = ('regional_partial_discovery', 'regional_candidate_discovery')


def descriptor(phase, queries, targets):
    # Bind the complete original matrix. Do not trim targets to the regional windows.
    q, t = sorted(set(queries)), sorted(set(targets))
    return {'id': stable_id('q0-native-fallback-scope',[phase,q,t]), 'phase':phase, 'query_ids':q, 'target_ids':t}


def first_contact(row, parts, demand):
    if not demand: return None
    for side in ('query_ids','target_ids'):
        for key in row[side]:
            part = parts[key]
            for span in demand.get(part.source, ()):
                overlap = part.interval.intersection(span)
                if overlap is not None:
                    return f"{side}:{key}:{overlap.start}-{overlap.end}"
    return None


def touches(row, parts, demand):
    return demand is None or first_contact(row,parts,demand) is not None


CACHE_ONLY = 'cache_only_leave_unresolved_v1'


class RegionalFallbackCache:
    def __init__(self, *, bounded):
        self.bounded = bounded
        self.omissions = []
        self.planned = {}

    def dispatch(self, phase, requests, probe):
        matrices = [descriptor(phase, r['query_ids'], r['target_ids']) for r in requests]
        self.planned[phase] = [row['id'] for row in matrices]
        completed = []
        for request, row in zip(requests, matrices):
            hit = probe(request)
            if hit is not None:
                completed.append(hit)
                continue
            print(f"LGZ q0 native fallback: phase={phase} matrix={row['id']} "
                  f"query_parts={len(row['query_ids'])} target_parts={len(row['target_ids'])} "
                  "decision=not_searched reason=whole_source_fallback_disabled", flush=True)
            if not self.bounded:
                raise Q0EvidenceError('full Q0 evidence unavailable: automatic whole-source regional fallback is disabled; '
                                      'use a bounded positive_threshold run or provide existing complete evidence')
            self.omissions.append(row)
        return completed


def prefer_cached_whole(regional, whole, report):
    """Do not ingest a local sibling twice when its entire native matrix was already cached."""
    if not whole: return regional
    coverage = {}
    for task in whole:
        targets = set(task['target_ids'])
        for q in task['query_ids']: coverage.setdefault(q, []).append(targets)
    kept = [t for t in regional if not (len(t['query_ids']) == 1 and
            any(scope.issuperset(t['target_ids']) for scope in coverage.get(t['query_ids'][0], ())))]
    report['regional_tasks_superseded_by_cache'] = len(regional)-len(kept)
    report['completed_regional_tasks'] = len(kept)
    return [*kept,*whole]


def omitted(report, parts):
    rows = report.get('deferred_native_matrices', [])
    if not isinstance(rows,list) or (rows and report.get('effective')!='decision_frontier'):
        raise Q0EvidenceError('invalid threshold native omission mode')
    seen = set()
    for row in rows:
        if not isinstance(row,dict) or row.get('phase') not in PHASES:
            raise Q0EvidenceError('invalid threshold native omission phase')
        q,t = row.get('query_ids'),row.get('target_ids')
        if any(not isinstance(v,list) or not v or any(not isinstance(k,str) or k not in parts for k in v) for v in (q,t)):
            raise Q0EvidenceError('invalid threshold native omission members')
        if row != descriptor(row['phase'],q,t) or row['id'] in seen:
            raise Q0EvidenceError('unbound or duplicate threshold native omission')
        seen.add(row['id'])
    return rows


def validate_inventory(catalog):
    """Every scoped native fallback is either a real task or an explicitly unsearched whole matrix."""
    report = catalog['supplement_scope']
    plans = {p:catalog.get(p,{}).get('native_fallback_matrix_ids',[]) for p in PHASES}
    if not any(plans.values()) and 'deferred_native_matrices' not in report:
        if report['effective']=='decision_frontier' and (catalog.get(PHASES[0],{}).get('fallback_sources') or
                catalog.get(PHASES[1],{}).get('fallback_parents')):
            raise Q0EvidenceError('unaccounted threshold native fallback')
        return
    if report['effective']!='decision_frontier': raise Q0EvidenceError('unexpected threshold native plan')
    pending = omitted(report,{s['segment_id'] for s in catalog['segments']})
    accounted = {phase:{} for phase in PHASES}
    for row in pending:
        accounted[row['phase']][row['id']] = row['query_ids']
    for task in catalog['supplementary_alignments']:
        kind = task['kind']
        if kind=='partial_source_discovery' and plans[PHASES[0]]: phase=PHASES[0]
        elif kind=='candidate_chr' and task['request'].get('regional_fallback'): phase=PHASES[1]
        else: continue
        row = descriptor(phase,task['query_ids'],task['target_ids'])
        if row['id'] in accounted[phase]: raise Q0EvidenceError('threshold native matrix counted twice')
        accounted[phase][row['id']] = row['query_ids']
    for phase,ids in plans.items():
        rows = accounted[phase]
        if not isinstance(ids,list) or len(ids)!=len(rows) or set(ids)!=rows.keys():
            raise Q0EvidenceError('threshold native plan differs from completed and deferred matrices')
        if phase not in catalog: continue
        parents = sorted(k for members in rows.values() for k in members)
        if phase == PHASES[0]:
            if parents!=sorted(r['segment_id'] for r in catalog[phase].get('fallback_sources',[])) or len(ids)>1:
                raise Q0EvidenceError('threshold partial native matrix differs from fallback parents')
        elif len(parents)!=len(set(parents)) or len(parents)!=catalog[phase].get('fallback_parents',0):
            raise Q0EvidenceError('threshold native candidate parent count differs')
