#!/usr/bin/env python3
"""Explicit -f screening, never an automatic production sensitivity policy.

Full original records/order and one default MMI. Different results are reported,
not silently accepted. No downstream scientific acceptance is claimed here.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import benchmark_ordinary_existing as existing
import benchmark_ordinary_partitions as parts
import ordinary_batch_performance as perf

FRACTIONS = ('0.001', '0.005', '0.01')


def profile(path):
    # Bounded maintainer audit, not an unbounded in-memory production PAF reader.
    if path.stat().st_size > 64 * 1024**2:
        raise ValueError('filtering audit refuses PAF >64 MiB; preserve outputs, no recommendation')
    signatures, pairs, intervals = Counter(), set(), defaultdict(list)
    with path.open('rb') as stream:
        for raw in stream:
            fields = raw.decode('ascii').rstrip('\n').split('\t')
            if len(fields) < 12:
                raise ValueError('invalid PAF')
            signatures[hashlib.sha256(raw).hexdigest()] += 1
            pairs.add((fields[0], fields[5], fields[4]))
            intervals[fields[0]].append((int(fields[2]), int(fields[3])))
    coverage = {}
    for name, spans in intervals.items():
        total, end = 0, -1
        for start, stop in sorted(spans):
            total += max(0, stop - max(start, end))
            end = max(end, stop)
        coverage[name] = total
    return {'signatures': signatures, 'pairs': pairs, 'coverage': coverage}


def differences(baseline, candidate):
    before, after = baseline['coverage'], candidate['coverage']
    return {'removed_full_PAF_rows': sum((baseline['signatures'] - candidate['signatures']).values()),
            'added_full_PAF_rows': sum((candidate['signatures'] - baseline['signatures']).values()),
            'removed_query_target_strand_pairs': len(baseline['pairs'] - candidate['pairs']),
            'added_query_target_strand_pairs': len(candidate['pairs'] - baseline['pairs']),
            'previously_mapped_queries_now_unmapped': sorted(set(before) - set(after)),
            'newly_mapped_queries': sorted(set(after) - set(before)),
            'queries_with_reduced_union_coverage': sum(after.get(q, 0) < n for q, n in before.items()),
            'baseline_query_union_coverage_bases': sum(before.values()),
            'candidate_query_union_coverage_bases': sum(after.values()),
            'downstream_scientific_acceptance': False}


def execute(args):
    mm = shutil.which(args.minimap2)
    if not mm or subprocess.check_output([mm, '--version'], text=True).strip() != perf.VERSION:
        raise ValueError('pinned minimap2 ' + perf.VERSION + ' required')
    sources = {'reference': existing.catalog(args.target), 'query': existing.catalog(args.query, ordinary_query=True)}
    root = args.out.resolve(); root.mkdir(parents=True, exist_ok=False)
    guarded = {'mapper': mm, 'harness': __file__, 'runner': perf.__file__,
               'catalog_reader': existing.__file__, 'PAF_reader': parts.__file__}
    hashes = {k: perf.sha256(path) for k, path in guarded.items()}
    r = {'status': 'running', 'scope': 'explicit_filtering_parameter_screening_not_production_policy',
         'sources': sources, 'resource_snapshot': existing.resource_snapshot(), 'runs': [],
         'mapper_version': perf.VERSION, 'guarded_source_sha256': hashes,
         'production_runtime_modified': False, 'automatic_trigger_implemented': False,
         'customer_wheat_data': False, 'downstream_scientific_acceptance': False,
         'threads': args.threads, 'batch_bases': args.batch_bases}
    perf.write_json(root/'benchmark.json',r)
    try:
        index = root/'target.default.mmi'
        r['index_build'] = perf.run([mm,'-x','asm10','-t',str(args.threads),'-d',str(index),sources['reference']['source']],
                                   root,'index',args.timeout,args.memory_mib)
        index_sha = perf.sha256(index)
        baseline, expected = None, {}
        for rep in range(args.repeats):
            cases = ['default',*args.fractions]
            if rep%2: cases.reverse()
            for case in cases:
                stem = f'r{rep:02d}-f{case}'
                out = root/(stem+'.paf')
                flags = [] if case=='default' else ['-f',case]
                cmd=[mm,'-c','-x','asm10',*flags,'-t',str(args.threads),'-K',str(args.batch_bases),
                     '-o',str(out),str(index),sources['query']['source']]
                result=perf.run(cmd,root,stem,args.timeout,args.memory_mib)
                rows=parts.validate_paf(out,sources['query']['records'],sources['reference']['records'],allow_empty=case!='default')
                native=perf.parse_log((root/(stem+'.stderr')).read_text())
                counts=[len(b) for b in perf.partition(sources['query']['records'],args.batch_bases)]
                if (sum(p['target_records'] for p in native['parts'])!=len(sources['reference']['records']) or
                        any([b['records'] for b in p['batches']]!=counts for p in native['parts'])):
                    raise ValueError('native query/index batch completeness check failed')
                mid=parts.thresholds(root/(stem+'.stderr'))
                if len(mid)!=len(native['parts']) or len(set(mid))!=1:
                    raise ValueError('original threshold inheritance changed')
                digest=perf.sha256(out)
                if case in expected and digest!=expected[case]:
                    raise ValueError('same filtering condition produced different ordered PAFs')
                expected[case]=digest
                current=profile(out)
                if case=='default':
                    if args.expected_baseline_paf_sha256 and digest!=args.expected_baseline_paf_sha256:
                        raise ValueError('full default baseline differs from previously accepted complete output')
                    baseline=current
                if baseline is None:
                    raise ValueError('first original baseline is required before comparison')
                result.update(repeat=rep,fraction=case,mid_occ=mid[0],paf_sha256=digest,paf_rows=rows,
                    actual_index_parts=len(native['parts']),differences=differences(baseline,current),
                    exact_ordered_paf_equal_to_default=digest==expected['default'])
                r['runs'].append(result)
                perf.write_json(root/'benchmark.json',r)
                print(json.dumps({k:result[k] for k in ('repeat','fraction','mid_occ','wall_seconds','paf_rows','exact_ordered_paf_equal_to_default','differences')}),flush=True)
                for k,path in guarded.items():
                    if perf.sha256(path)!=hashes[k]: raise ValueError(k+' changed')
                if perf.sha256(index)!=index_sha: raise ValueError('original index changed')
                for source in sources.values():
                    if existing.identity(Path(source['source']))!={k:source[k] for k in ('size','mtime_ns','ctime_ns','inode')}:
                        raise ValueError('original FASTA metadata changed')
        for source in sources.values():
            if perf.sha256(source['source'])!=source['sha256']: raise ValueError('original FASTA content changed')
        r.update(status='completed_screening_not_scientific_acceptance',index_sha256=index_sha,
                 input_content_unchanged=True,original_default_index_policy=True,
                 filtering_parameter_changed=True,query_records_skipped=False)
    except BaseException as error:
        r.update(status='failed_no_recommendation',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        perf.write_json(root/'benchmark.json',r)
    return r


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('target','query','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--minimap2',default='minimap2')
    p.add_argument('--threads',type=int,default=64)
    p.add_argument('--memory-mib',type=int,default=196608)
    p.add_argument('--timeout',type=int,default=1800)
    p.add_argument('--batch-bases',type=int,default=500000000)
    p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--fractions',choices=FRACTIONS,nargs='+',default=['0.01'])
    p.add_argument('--expected-baseline-paf-sha256')
    p.add_argument('--execute',action='store_true')
    a=p.parse_args(argv)
    if not (1<=a.threads<=64 and 256<=a.memory_mib<=262144 and 0<a.timeout<=7200 and
            0<a.batch_bases<=5_000_000_000 and 1<=a.repeats<=5 and len(set(a.fractions))==len(a.fractions)):
        p.error('bounded resources and unique fraction cases required')
    if a.expected_baseline_paf_sha256 and not (len(a.expected_baseline_paf_sha256)==64 and
            all(c in '0123456789abcdef' for c in a.expected_baseline_paf_sha256)):
        p.error('lowercase SHA-256 required')
    result=execute(a) if a.execute else {'execute':False,'files_created':False,'mapper_started':False,
          'automatic_trigger_implemented':False,'downstream_scientific_acceptance':False}
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
