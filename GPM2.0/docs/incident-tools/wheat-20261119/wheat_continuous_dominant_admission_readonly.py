"""Isolated continuity-preserving dominant admission, not a production policy.

One frozen all-locus screen feeds 90/80/75 percent comparisons. Actual anchor
unions measure coverage; whole-contig carrying never invents reference support.
All screened chr/strand anchors are saved so policy trials need not rescan DNA.
"""
import argparse, csv, gzip, json, multiprocessing as mp, subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic
from unittest.mock import patch
from hashlib import sha256
import wheat_reference_funnel_readonly as frozen
import wheat_local_admission_readonly as legacy
from wheat_local_chain_primitives import chain, clipped
from lgz_core import q0_admission as adm
from lgz_core.q0_sources import SourceKey, SourceSegment, Interval, merged_intervals, subtract_intervals
from lgz_core.q0_reference_competition import reference_masks
from lgz_core.q0_retained_hits import read_retained_paf, retained_names, retained_geometry_cache
from wheat_selection_checkpoint import encode, decode
from compare_wheat_local_only_paths import load_arm

GROUP = '1A'
FRACTIONS = (90, 80, 75)
OLD = {}

@dataclass(frozen=True)
class ContinuityPolicy:
    minimum_main_chain_bp: int = 100_000
    minimum_chain_fraction_of_carried_source: float = 0.20
    foreign_cluster_gap_bp: int = 50_000
    minimum_terminal_foreign_bp: int = 10_000
    minimum_internal_foreign_bp: int = 100_000
    minimum_internal_fraction: float = 0.01
    minimum_foreign_density: float = 0.50
    maximum_main_overlap_fraction: float = 0.10

POLICY = ContinuityPolicy()

def screened(source):
    policy=frozen.POLICY;n=frozen.FAI[source][0];minimum=min(policy.minimum_anchor_bp,n);blocks=[]
    for hit in frozen.HITS.get(source,()):
        identity=hit.matches/hit.block_length
        if identity<policy.minimum_reference_identity:continue
        for b in hit.aligned_blocks():
            if b.operation!='X':blocks.append(adm._RefBlock(b.query,b.target,hit.target_name,hit.strand,hit.evidence_id,identity,hit.mapping_quality))
    masks,ambiguous=reference_masks(blocks,policy.competing_identity_margin)
    target_support=adm._size(iv for b,vs in zip(blocks,masks) if b.chromosome==GROUP for iv in vs)
    if target_support<minimum:return {}, {}, 0
    dna=frozen.sequence(source);groups=defaultdict(list);high=defaultdict(list);bounds=None
    for b,spans in zip(blocks,masks):
        if not spans:continue
        key=b.chromosome,b.strand
        if spans[0].length<minimum:
            if bounds is None:bounds=adm._possible_support_bp(blocks,masks,minimum)
            if bounds[key]<minimum:continue
        for iv in spans:
            for clean in adm._complex_intervals(dna,iv,policy):
                groups[key].append(adm.ReferenceAnchor(clean,adm._project(b.query,b.target,b.strand,clean),b.evidence_id))
                if b.mapq is not None and b.mapq>=policy.minimum_reference_mapq:high[key].append(clean)
    groups={key:tuple(sorted(set(rows),key=lambda a:(a.source,a.reference,a.evidence_id))) for key,rows in groups.items() if adm._size(a.source for a in rows)>=minimum}
    high={key:merged_intervals(rows) for key,rows in high.items() if key in groups}
    return groups, high, n


def foreign_barriers(groups, high, main_key, main_chain, length, policy=POLICY):
    """Only substantial, locally collinear independent foreign chains cut.

    Small interior islands are logged, not subtracted. A terminal chain lies
    wholly outside the main-chain hull; unsupported internal gaps are not ends.
    Cluster source-local support before finding an exact collinear chain.
    """
    main_hull = adm._hull(a.source for a in main_chain)
    barriers, audit = [], []
    for key, anchors in sorted(groups.items()):
        if key == main_key:
            continue
        rows = sorted(anchors, key=lambda a: (a.source, a.reference, a.evidence_id))
        clusters = []
        reach = -policy.foreign_cluster_gap_bp - 1
        for a in rows:
            if not clusters or a.source.start > reach + policy.foreign_cluster_gap_bp:
                clusters.append([])
            clusters[-1].append(a)
            reach = max(reach, a.source.end)
        for cluster in clusters:
            selected = chain(cluster, key[1])
            hull = adm._hull(a.source for a in selected)
            bp = adm._size(a.source for a in selected)
            terminal = hull.end <= main_hull.start or hull.start >= main_hull.end
            required = (policy.minimum_terminal_foreign_bp if terminal else
                        max(policy.minimum_internal_foreign_bp,
                            int(length * policy.minimum_internal_fraction)))
            main_overlap = legacy.overlap_bp((a.source for a in main_chain), (hull,))
            high_bp = legacy.overlap_bp((a.source for a in selected), high.get(key, ()))
            split = (bp >= required and high_bp >= required
                     and bp >= policy.minimum_foreign_density * hull.length
                     and main_overlap <= policy.maximum_main_overlap_fraction * bp)
            audit.append({'group': list(key), 'source_interval': [hull.start, hull.end],
                          'support_bp': bp, 'high_mapq_bp': high_bp,
                          'main_anchor_overlap_bp': main_overlap, 'terminal': terminal,
                          'required_bp': required, 'split': split})
            if split:
                barriers.append(hull)
    return merged_intervals(barriers), audit


def continuous_candidates(part, groups, high, target=GROUP, policy=POLICY):
    support = {key: adm._size(a.source for a in rows) for key, rows in groups.items()}
    total = adm._size(a.source for rows in groups.values() for a in rows)
    result = {str(f): [] for f in FRACTIONS}
    if not support:
        return result, {'reason': 'no_qualified_group'}
    key = min(support, key=lambda k: (-support[k], k))
    if key[0] != target:
        return result, {'reason': 'dominant_group_is_not_target', 'dominant': list(key)}
    main = chain(groups[key], key[1])
    main_bp = adm._size(a.source for a in main)
    # The numerator is actual collinear chain support, not a broad envelope.
    fraction = main_bp / max(1, total)
    detail = {'dominant': list(key), 'main_chain_bp': main_bp,
              'dominant_group_support_bp': support[key], 'all_group_support_bp': total,
              'dominance_fraction': fraction, 'regions': []}
    if main_bp < policy.minimum_main_chain_bp or fraction < min(FRACTIONS) / 100:
        detail['reason'] = 'main_chain_support_or_dominance'
        return result, detail
    barriers, foreign = foreign_barriers(groups, high, key, main, part.interval.length, policy)
    detail['foreign_chains'] = foreign
    detail['split_intervals'] = [[v.start, v.end] for v in barriers]
    foreign_anchors = [a.source for k, rows in groups.items() if k != key for a in rows]
    for region in subtract_intervals(part.interval, barriers):
        anchors = clipped(main, region, key[1])
        bp = adm._size(a.source for a in anchors)
        high_bp = legacy.overlap_bp((a.source for a in anchors), high.get(key, ()))
        row = {'interval': [region.start, region.end], 'support_bp': bp,
               'high_mapq_bp': high_bp, 'accepted': False}
        detail['regions'].append(row)
        if (bp < policy.minimum_main_chain_bp or high_bp < frozen.POLICY.minimum_anchor_bp
                or bp < policy.minimum_chain_fraction_of_carried_source * region.length):
            continue
        if not adm._ordered(anchors, key[1]):
            raise ValueError('non-collinear main chain')
        placement = adm._placement(part, *key, region, (a.source for a in anchors), anchors,
                                   (a.evidence_id for a in anchors),
                                   kind='diagnostic_continuous_dominant_chain')
        row.update(accepted=True, placement_id=placement.placement_id,
                   unsupported_carried_bp=region.length-bp,
                   foreign_qualified_source_bp=legacy.overlap_bp((region,), foreign_anchors))
        for threshold in FRACTIONS:
            if fraction >= threshold / 100:
                result[str(threshold)].append(placement)
    return result, detail


def one(source):
    groups, high, verified = screened(source)
    n = frozen.FAI[source][0]
    part = SourceSegment(legacy.PART_ID[source], source, Interval(0, n),
                         frozen.LOOKUP[source]['sequence_sha256'], 0, 'start', 'end')
    candidates, detail = continuous_candidates(part, groups, high, target=GROUP)
    # Save ALL surviving group anchors and high-MAPQ spans, not just counts.
    cache = {'source': [source.dataset, source.contig], 'length': n,
             'sequence_sha256': frozen.LOOKUP[source]['sequence_sha256'],
             'groups': [[list(k), [[a.source.start, a.source.end, a.reference.start,
                                    a.reference.end, a.evidence_id] for a in rows],
                         [[iv.start, iv.end] for iv in high.get(k, ())]]
                        for k, rows in sorted(groups.items())]}
    return {'cache': cache, 'verified_bp': verified, 'detail': detail,
            'placements': {k: [encode(p) for p in rows] for k, rows in candidates.items()},
            'qualified': [[v.start, v.end] for v in merged_intervals(
                a.reference for k, rows in groups.items() if k[0] == GROUP for a in rows)]}


def old_routes(path):
    result = defaultdict(list)
    total = 0
    with path.open() as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            if row['q_version'] != 'q0' or row['segment_kind'] != 'source':
                continue
            iv = Interval(int(row['source_start']) - 1, int(row['source_end']))
            if iv.length != int(row['q_end']) - int(row['q_start']) + 1:
                raise ValueError('old coordinate convention changed')
            result[SourceKey(row['dataset_name'], row['contig_name'])].append(
                (iv, row['chr'], row['orientation']))
            total += iv.length
    if total != 14097044589:
        raise ValueError('old q0 source extent changed')
    return result


def risk(p, old):
    refs, spans = defaultdict(list), defaultdict(list)
    for iv, group, orientation in old.get(p.source, ()):
        ov = p.interval.intersection(iv)
        if ov is None:
            continue
        category = ('same_group_same_orientation' if group == p.chromosome and orientation == p.orientation
                    else 'same_group_opposite_orientation' if group == p.chromosome else 'other_chromosome')
        categories = [category]
        if group != p.chromosome and group[-1] in 'ABD' and p.chromosome[-1] in 'ABD' and group[-1] != p.chromosome[-1]:
            categories.append('other_subgenome')
        for name in categories:
            spans[name].append(ov)
            refs[name].extend(a.reference for a in clipped(p.reference_blocks, ov, p.orientation))
    return refs, spans


def initialize(base):
    began=monotonic();snap=frozen.checked(base/'q0-latest-fork-20261123-1435/control/snapshot.json',frozen.SNAP);frozen.ROOT=Path(snap['source']);lookup=frozen.checked(base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json',frozen.LOOK);files={r['path']:r for r in snap['files']};before={}
    frozen.LOOKUP={SourceKey(v['dataset'],v['contig']):v for v in lookup.values()};legacy.PART_ID.update({SourceKey(v['dataset'],v['contig']):k for k,v in lookup.items()});frozen.FAI={}
    for ds in sorted({s.dataset for s in frozen.LOOKUP}):
        for rel in ('data/datasets/'+ds+'.fa.fai','runs/'+ds+'_vs_ref/result.paf'):
            p=frozen.ROOT/rel
            if frozen.digest(p)!=files[rel]['sha256']:raise ValueError('changed input '+rel)
            before[p]=frozen.signature(p)
        p=frozen.ROOT/('data/datasets/'+ds+'.fa');before[p]=frozen.signature(p)
        if p.stat().st_size!=files[str(p.relative_to(frozen.ROOT))]['size']:raise ValueError('source FASTA size')
        for line in (frozen.ROOT/('data/datasets/'+ds+'.fa.fai')).read_text().splitlines():
            name,n,offset,bases,width,*_=line.split('\t');frozen.FAI[SourceKey(ds,name)]=tuple(map(int,(n,offset,bases,width)))
    if {k:v[0] for k,v in frozen.FAI.items()}!={k:v['length'] for k,v in frozen.LOOKUP.items()}:raise ValueError('FAI lookup differs')
    rp=frozen.ROOT/'data/reference/IWGSC.fa.fai'
    if frozen.digest(rp)!=files[str(rp.relative_to(frozen.ROOT))]['sha256']:raise ValueError('reference FAI differs')
    lengths={r.split('\t')[0]:int(r.split('\t')[1]) for r in rp.read_text().splitlines()};frozen.HITS=defaultdict(list);geometry=retained_geometry_cache()
    for ds in sorted({s.dataset for s in frozen.FAI}):
        rel='runs/'+ds+'_vs_ref/result.paf'
        for hit in read_retained_paf(frozen.ROOT/rel,artifact=rel,query_names=retained_names({s.contig:n[0] for s,n in frozen.FAI.items() if s.dataset==ds}),target_names=retained_names(lengths),short_geometry=geometry):frozen.HITS[SourceKey(ds,hit.query_name)].append(hit)
        print('LOCAL_CHAIN_PAF_LOADED',ds,round(monotonic()-began,1),flush=True)
    return before, lengths


def run(base, owner, workers):
    began = monotonic()
    before, lengths = initialize(base)
    old_path = owner / 'old-grt-q-segments.tsv'
    if frozen.digest(old_path) != 'cd9069e54e64cce94ba7d4790afd2c575d85ffc227722b04eca56bf6e04ea847':
        raise ValueError('old comparator changed')
    old = old_routes(old_path)
    sources = sorted(s for s, hits in frozen.HITS.items() if any(h.target_name == GROUP for h in hits))
    maps = {k: frozen.Bitmap({GROUP: lengths[GROUP]}) for k in ['qualified', 'frozen'] + [str(f) for f in FRACTIONS]}
    counts, stats = Counter(), {str(f): Counter() for f in FRACTIONS}
    risk_refs = {str(f): defaultdict(list) for f in FRACTIONS}
    risk_source = {str(f): defaultdict(lambda: defaultdict(list)) for f in FRACTIONS}
    streams = {str(f): gzip.open(owner / ('continuous'+str(f)+'-placements.jsonl.gz'), 'wt', compresslevel=1) for f in FRACTIONS}
    last = monotonic()
    print('CONTINUITY_SCREEN_START', GROUP, len(sources), flush=True)
    try:
        with gzip.open(owner/'screened-reference-anchors.jsonl.gz', 'wt', compresslevel=1) as cache, \
             gzip.open(owner/'continuity-source-audit.jsonl.gz', 'wt', compresslevel=1) as audit, \
             mp.get_context('fork').Pool(workers) as pool:
            for item in pool.imap_unordered(one, sources, chunksize=1):
                counts['sources_done'] += 1
                counts['verified_sequence_bp'] += item['verified_bp']
                cache.write(json.dumps(item['cache'], separators=(',', ':'))+'\n')
                audit.write(json.dumps({'source': item['cache']['source'], **item['detail']}, separators=(',', ':'))+'\n')
                for lo, hi in item['qualified']:
                    maps['qualified'].add(GROUP, lo, hi)
                for mode, encoded in item['placements'].items():
                    stats[mode]['sources'] += bool(encoded)
                    for value in encoded:
                        p = decode(value)
                        streams[mode].write(json.dumps(value, separators=(',', ':'))+'\n')
                        stats[mode]['placements'] += 1
                        stats[mode]['source_bp_sum'] += p.interval.length
                        stats[mode]['max_placement_bp'] = max(stats[mode]['max_placement_bp'], p.interval.length)
                        for a in p.reference_blocks:
                            maps[mode].add(GROUP, a.reference.start, a.reference.end)
                        refs, spans = risk(p, old)
                        conflict = False
                        for name, rows in refs.items():
                            risk_refs[mode][name].extend(rows)
                        for name, rows in spans.items():
                            risk_source[mode][name][p.source].extend(rows)
                            conflict |= name != 'same_group_same_orientation' and bool(rows)
                        stats[mode]['old_q0_conflict_placements'] += conflict
                if monotonic() - last >= 30:
                    progress = {'group': GROUP, 'counts': dict(counts), 'total_sources': len(sources),
                                'variants': {k: dict(v) for k, v in stats.items()},
                                'elapsed_s': monotonic()-began}
                    frozen.write(owner/'continuity-progress.json', progress)
                    print('CONTINUITY_PROGRESS', json.dumps(progress), flush=True)
                    last = monotonic()
    finally:
        for stream in streams.values():
            stream.close()
    main = base/'q0-whole-local-maps.soHq9Z6J'
    _, _, records, _, _ = load_arm(main, 'd23a49af479b6c9b81916518e8034d4044ea31b5c97229c5d0ce1624138fc9d4', 'whole-wheat-local-supplement-v1')
    combined = {k: frozen.Bitmap({GROUP: lengths[GROUP]}) for k in stats}
    with (main/'selection/admission.jsonl').open('rb') as f, gzip.open(owner/'frozen-placements.jsonl.gz', 'wt', compresslevel=1) as out:
        f.readline()
        for raw in f:
            value = json.loads(raw)
            if isinstance(value, list):
                break
            p = decode(value)
            if p.chromosome != GROUP:
                continue
            if records[GROUP][p.placement_id] != sha256(raw).hexdigest():
                raise ValueError('frozen admission changed')
            out.write(raw.decode())
            counts['frozen_placements'] += 1
            for a in p.reference_blocks:
                maps['frozen'].add(GROUP, a.reference.start, a.reference.end)
                for bitmap in combined.values():
                    bitmap.add(GROUP, a.reference.start, a.reference.end)
    coverage = {k: sum(v.counts().values()) for k, v in maps.items()}
    if GROUP == '1A' and (coverage['qualified'] != 445132656 or coverage['frozen'] != 129162948):
        raise ValueError('frozen 1A screening was not reproduced: '+str(coverage))
    for mode in stats:
        with gzip.open(owner/('continuous'+mode+'-placements.jsonl.gz'), 'rt') as f:
            for line in f:
                p = decode(json.loads(line))
                for a in p.reference_blocks:
                    combined[mode].add(GROUP, a.reference.start, a.reference.end)
    for path, pin in before.items():
        if frozen.signature(path) != pin:
            raise ValueError('formal source changed during read-only check')
    outputs = {p.name: {'sha256': frozen.digest(p), 'bytes': p.stat().st_size} for p in owner.glob('*.jsonl.gz')}
    report = {'schema': 'wheat_continuous_dominant_admission_v1', 'group': GROUP,
              'policy': asdict(POLICY), 'original_reference_policy': vars(frozen.POLICY),
              'fractions': list(FRACTIONS), 'reference_coverage_bp': coverage,
              'combined_with_frozen_reference_bp': {k: sum(v.counts().values()) for k,v in combined.items()},
              'variants': {k: dict(v) for k,v in stats.items()}, 'counts': dict(counts),
              'old_q0_comparison': {mode: {
                  'reference_union_bp': {name: adm._size(rows) for name,rows in risk_refs[mode].items()},
                  'source_union_bp': {name: sum(adm._size(rows) for rows in source_map.values())
                                      for name,source_map in risk_source[mode].items()}}
                  for mode in stats},
              'outputs': outputs, 'snapshot_sha256': frozen.SNAP, 'lookup_sha256': frozen.LOOK,
              'mapper_calls': 0, 'formal_workspace_modified': False, 'elapsed_s': monotonic()-began,
              'limitations': [
                  'Experimental gates are predeclared diagnostic settings, not new production defaults.',
                  'Continuity may carry small foreign signals or unsupported sequence; source conflicts and reference conflicts are distinct.',
                  'Old Q0 is a comparator, not independent biological truth.',
                  'Admission footprints are not selected Q0 coverage; selection and actual slice risk audit remain required.',
                  'Frozen admission is retained for the downstream comparison, not rerun propagation.',
                  'No formal Q0-LGZ or 3B/3D release is authorized by this receipt alone.']}
    frozen.write(owner/'continuity-admission.json', report)
    print('CONTINUITY_ADMISSION_DONE', json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('base', type=Path)
    parser.add_argument('owner', type=Path)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--group', choices=('1A','3B','3D'), default='1A')
    args = parser.parse_args()
    GROUP = args.group
    owner, base = args.owner.resolve(), args.base.resolve()
    if owner.parent != base or not owner.name.startswith('q0-continuity-') or owner.stat().st_mode & 0o077:
        raise ValueError('private isolated continuity owner required')
    with patch.object(subprocess, 'Popen', side_effect=RuntimeError('external command forbidden in read-only admission')):
        run(base, owner, args.workers)
