#!/usr/bin/env python3
"""PLAN ONLY by default: final installed ordinary-part engine, existing-MMI phase.

Baseline and candidate share one already-built original-layout MMI and exact
serialized parts, as in the mixed Server path. The measured execution phase
includes real mapping, production CellMerger, receipts and independent output
checks. Common input derivation/index preparation are reported separately, NOT
credited as speedup. This is NOT raw-FASTA preprocessing or full CGAT timing.
No minimap2 patch, query splitting, sensitivity change or failed-work retry.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import statistics
import sys
import time

import benchmark_ordinary_existing as existing
import benchmark_ordinary_partitions as audit
import ordinary_batch_performance as perf

MODES = ('native-mmi', 'server-original-parts')
GIB = 1024**3


def digest(path):
    return perf.sha256(path)


def runtime(root, expected):
    manifest = json.loads((root/'branch-runtime.json').read_text())
    files = manifest['files_sha256']
    profile = hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if profile != expected:
        raise ValueError('installed-runtime source profile differs from frozen expected revision')
    for name, wanted in files.items():
        path = root/name
        if path.parent != root or path.is_symlink() or digest(path) != wanted:
            raise ValueError('installed runtime source changed: '+name)
    # Never silently execute a preloaded experimental module in place of the
    # installed source whose bytes were just checked.
    if list((root/'__pycache__').glob('*.pyc')):
        raise ValueError('fresh source-only runtime without cached bytecode required')
    sys.path.insert(0,str(root))
    result = {}
    for name in ('windowed_alignment','minimap_index_context','native_first','ordinary_partition_alignment','proactive_reference_plan'):
        module = importlib.import_module(name)
        if Path(module.__file__).resolve() != root/(name+'.py'):
            raise ValueError('foreign preloaded runtime module: '+name)
        result[name] = module
    return result, files


def copied_queries(original, destination, copies):
    if copies == 1:
        return original, {'copies':1,'derived':False,'whole_records_preserved':True}
    with destination.open('xb') as out:
        for number in range(copies):
            checksum = hashlib.sha256();line_start=True;ended=True
            if number and not previous_ended:
                out.write(b'\n')
            with Path(original['source']).open('rb') as stream:
                while raw := stream.readline(1024**2):
                    checksum.update(raw)
                    if line_start and raw.startswith(b'>'):
                        out.write(b'>copy%04d|'%number+raw[1:])
                    else:
                        out.write(raw)
                    line_start=ended=raw.endswith(b'\n')
            if checksum.hexdigest() != original['sha256']:
                raise ValueError('read-only original query changed during whole-record copying')
            previous_ended=ended
    result=existing.catalog(destination,ordinary_query=True)
    expected=[{'name':f'copy{i:04d}|'+r['name'],'length':r['length']}
              for i in range(copies) for r in original['records']]
    if result['records']!=expected or result['total_bases']!=copies*original['total_bases']:
        raise ValueError('derived whole-record group lost names, order, bases or membership')
    return result, {'copies':copies,'derived':True,'whole_records_preserved':True,
                    'only_headers_prefixed':True,'boundary_newline_added_if_needed':True,
                    'original_query_sha256':original['sha256']}


def unchanged(sources, artifacts):
    for value in sources:
        if existing.identity(Path(value['source'])) != {k:value[k] for k in ('size','mtime_ns','ctime_ns','inode')}:
            raise ValueError('original or derived input changed during comparison')
    for path,identity,wanted in artifacts:
        if existing.identity(path)!=identity:
            raise ValueError('frozen runtime/tool/index artifact changed: '+str(path))


def cpu_usage(who):
    value=resource.getrusage(who)
    return value.ru_utime+value.ru_stime


def trial(mode, number, root, args, modules, mm, index, parts, reference, query):
    wa,nf,opa=(modules[k] for k in ('windowed_alignment','native_first','ordinary_partition_alignment'))
    root.mkdir()
    # Each production call starts a fresh Python interpreter. Reset ONLY this
    # private test memo between trials, not OS page caches or on-disk checkpoints.
    wa._VERIFIED_DIGESTS.clear()
    options=argparse.Namespace(threads=args.threads,timeout=args.timeout,memory_gib=0,
        minimap_batch=str(args.batch_bases),minimap_filter=args.minimap_filter,
        ordinary_group_memory_bytes=args.memory_mib*1024**2)
    rows=query['records'];names=[r['name'] for r in rows]
    started=time.monotonic();child_before=cpu_usage(resource.RUSAGE_CHILDREN);self_before=cpu_usage(resource.RUSAGE_SELF)
    if mode=='native-mmi':
        reserve=max(GIB,opa.tm.current_virtual_bytes()+64*1024**2)
        caps=[args.memory_mib*1024**2-reserve]+[n for n in resource.getrlimit(resource.RLIMIT_AS) if n!=resource.RLIM_INFINITY]
        options.memory_gib=min(caps)//GIB
        if options.memory_gib<1:raise ValueError('baseline has insufficient current address-space allowance')
        native=nf.attempt(mm,index,Path(query['source']),root/'native',options)
        if native['status']!='native_success':
            raise ValueError('baseline native failure; no retry')
        leaves=[(None,native,root/'native/native.stderr')]
    else:
        admission=opa.plan(options,parts,rows)
        if not admission['enabled']:
            raise ValueError('final production admission declined this control: '+admission['reason'])
        native=opa.attempt(mm,parts,Path(query['source']),root/'native',options,rows,admission)
        leaves=[(p['part_index'],p['native'],root/f"native/part-{p['part_index']:04d}/native.stderr") for p in native['parts']]
    mapping_done=time.monotonic()
    merger=nf.CellMerger(root/'cells',{r['name']:r for r in rows},{r['name']:r for r in reference['records']},parts)
    for i,receipt,log in leaves:
        merger.add_native(receipt,names,part_index=i)
    output=root/'complete.paf';combination=merger.finish(output)
    merged=time.monotonic()
    summaries=[]
    for i,receipt,log in leaves:
        summaries.append(audit.check_native_log(log,parts if i is None else [parts[i]],rows,args.batch_bases))
    count=audit.validate_paf(output,rows,reference['records'])
    checksum=digest(output)
    # CellMerger may only preserve native bytes/order, never silently normalize.
    raw_digests=hashlib.sha256()
    for _,receipt,_ in leaves:
        with Path(receipt['path']).open('rb') as stream:
            while block:=stream.read(1024**2):raw_digests.update(block)
    if checksum!=raw_digests.hexdigest() or not combination['all_cells_completed']:
        raise ValueError('production merger changed native bytes/order or omitted original cells')
    finished=time.monotonic();child_cpu=cpu_usage(resource.RUSAGE_CHILDREN)-child_before;parent_cpu=cpu_usage(resource.RUSAGE_SELF)-self_before
    result={'mode':mode,'repeat':number,'status':'complete','execution_stage_seconds':finished-started,
        'mapping_with_production_receipts_seconds':mapping_done-started,'merge_seconds':merged-mapping_done,
        'independent_output_audit_seconds':finished-merged,'child_cpu_seconds':child_cpu,'parent_cpu_seconds':parent_cpu,
        'execution_average_cpu_core_equivalents':(child_cpu+parent_cpu)/(finished-started),
        'native_cpu_seconds':sum(v['cpu_seconds'] for v in summaries),
        'sum_individual_native_peak_rss_gb_not_group_highwater':sum(v['peak_rss_gb'] for v in summaries),
        'native_resource_summaries':summaries,'paf_sha256':checksum,'paf_rows':count,'paf_bytes':output.stat().st_size,
        'output_path':str(output),'combination':combination,'native':native,
        'private_digest_memo_reset':True,'OS_page_cache_flushed':False,'automatic_retry':False,
        'baseline_address_space_bytes':options.memory_gib*GIB if mode=='native-mmi' else None,
        'baseline_controller_reserve_bytes':reserve if mode=='native-mmi' else None}
    perf.write_json(root/'trial.json',result)
    return result


def execute(args):
    if args.out.is_symlink():raise ValueError('linked output directory refused')
    root=args.out.resolve();modules,files=runtime(args.runtime_root.resolve(),args.expected_runtime_profile)
    modules['proactive_reference_plan'].check_prepared_scope(root,None)
    wa,mic=(modules[k] for k in ('windowed_alignment','minimap_index_context'))
    if root.exists() or root.is_symlink() or not root.parent.is_dir():
        raise ValueError('fresh output directory below an existing parent required')
    if shutil.disk_usage(root.parent).free < args.min_free_gib*GIB:
        raise ValueError('insufficient scratch space; no analysis started')
    mm=Path(shutil.which(args.minimap2) or args.minimap2).resolve()
    if subprocess_version(mm)!=perf.VERSION or args.expected_mapper_sha256 and digest(mm)!=args.expected_mapper_sha256:
        raise ValueError('pinned minimap2 version/content differs')
    soft,hard=resource.getrlimit(resource.RLIMIT_FSIZE)
    cap=min([args.max_file_gib*GIB,*[n for n in (soft,hard) if n!=resource.RLIM_INFINITY]])
    resource.setrlimit(resource.RLIMIT_FSIZE,(cap,hard))
    root.mkdir()
    report={'schema':1,'status':'running','runs':[],'threads':args.threads,'memory_mib':args.memory_mib,
        'file_size_limit_bytes':cap,'batch_bases':args.batch_bases,'minimap_filter':args.minimap_filter,'query_copies':args.query_copies,
        'timing_scope':'existing_original_MMI_ordinary_execution_including_production_merge_and_audit',
        'common_preparation_not_credited_as_speedup':True,'full_CGAT_workflow':False,'pure_ordinary_preprocessing':False,
        'automatic_memory_discovery_tested':False,'explicit_maintainer_memory_allowance':True,
        'customer_wheat_data':False,'source_profile_sha256':args.expected_runtime_profile,'runtime_files_sha256':files,
        'original_default_index_policy':args.control_index_bases is None,'TEST_ONLY_index_bases':args.control_index_bases,
        'resource_snapshot':existing.resource_snapshot(),'tool':{'path':str(mm),'sha256':digest(mm),'version':perf.VERSION},
        'host':os.uname().nodename,'architecture':os.uname().machine,'automatic_retry':False}
    perf.write_json(root/'benchmark.json',report)
    try:
        prepared=time.monotonic()
        original=existing.catalog(args.query,ordinary_query=True);reference=existing.catalog(args.target)
        for role,value in (('query',original),('reference',reference)):
            expected=getattr(args,'expected_'+role+'_sha256')
            if expected and value['sha256']!=expected:raise ValueError('frozen original '+role+' content differs')
        query,derivation=copied_queries(original,root/'whole-copies.fa',args.query_copies)
        index=root/'target.original.mmi'
        flags=[] if args.control_index_bases is None else ['-I',str(args.control_index_bases)]
        build=wa.run_command([str(mm),'-x','asm10',*flags,'-t',str(args.threads),'-d',str(index),reference['source']],root,'index',args.timeout,(args.memory_mib-1024)//1024)
        catalog=mic.copy_parts(index,root/'index-parts',{r['name']:r for r in reference['records']})
        if len(catalog['parts'])!=args.expected_parts:
            raise ValueError('unexpected original index layout; no forced repartition or retry')
        parts=catalog['parts'];perf.write_json(root/'index-context.json',catalog)
        sources=[reference,original,query]
        code=[args.runtime_root.resolve()/name for name in files]+[Path(mm),Path(__file__).resolve(),Path(existing.__file__),Path(audit.__file__),Path(perf.__file__)]
        artifacts=[(p,existing.identity(p),digest(p)) for p in code]+[(index,existing.identity(index),catalog['sha256'])]
        artifacts += [(Path(p['path']),existing.identity(Path(p['path'])),p['sha256']) for p in parts]
        report.update(sources={'reference':reference,'original_query':original,'query':query},derivation=derivation,
            common_index_build=build,index=catalog,common_preparation_seconds=time.monotonic()-prepared,
            frozen_artifacts=[{'path':str(p),'identity':identity,'sha256':wanted} for p,identity,wanted in artifacts])
        perf.write_json(root/'benchmark.json',report)
        answer=None
        for number in range(args.repeats):
            for mode in MODES if number%2==0 else reversed(MODES):
                unchanged(sources,artifacts)
                result=trial(mode,number,root/f'r{number:02d}-{mode}',args,modules,str(mm),index,parts,reference,query)
                unchanged(sources,artifacts)
                if answer is None:answer=result['paf_sha256']
                if result['paf_sha256']!=answer:raise ValueError('complete native/production outputs differ; no further trial')
                report['runs'].append(result);perf.write_json(root/'benchmark.json',report)
        before=time.monotonic()
        for p,identity,wanted in artifacts:
            if digest(p)!=wanted:raise ValueError('frozen artifact content changed: '+str(p))
        unchanged(sources,artifacts)
        medians={mode:statistics.median(r['execution_stage_seconds'] for r in report['runs'] if r['mode']==mode) for mode in MODES}
        report.update(status='complete_equal',exact_ordered_paf_equal=True,
            common_postflight_seconds=time.monotonic()-before,summary={'execution_stage_median_seconds':medians,
                'speedup':medians[MODES[0]]/medians[MODES[1]],
                'wall_reduction_percent':100*(1-medians[MODES[1]]/medians[MODES[0]])})
    except BaseException as error:
        report.update(status='failed_no_retry',error=f'{type(error).__name__}: {error}')
        raise
    finally:perf.write_json(root/'benchmark.json',report)
    return report


def subprocess_version(mm):
    import subprocess
    return subprocess.check_output([str(mm),'--version'],text=True).strip()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',type=Path,required=True);p.add_argument('--query',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--runtime-root',type=Path,required=True)
    p.add_argument('--minimap2',default='minimap2');p.add_argument('--threads',type=int,default=64)
    p.add_argument('--memory-mib',type=int,default=196608);p.add_argument('--batch-bases',type=int,default=1000000000)
    p.add_argument('--minimap-filter');p.add_argument('--query-copies',type=int,default=1)
    p.add_argument('--repeats',type=int,default=2);p.add_argument('--timeout',type=int,default=7200)
    p.add_argument('--max-file-gib',type=int,default=8);p.add_argument('--min-free-gib',type=int,default=32);p.add_argument('--control-index-bases',type=int)
    p.add_argument('--expected-parts',type=int,default=2);p.add_argument('--expected-runtime-profile',required=True)
    for role in ('mapper','reference','query'):p.add_argument('--expected-'+role+'-sha256')
    p.add_argument('--execute',action='store_true');args=p.parse_args(argv)
    try:
        if not (2<=args.threads<=128 and 4096<=args.memory_mib<=262144 and 1<=args.batch_bases<=5000000000
                and 1<=args.query_copies<=32 and 1<=args.repeats<=3 and 1<=args.timeout<=21600
                and 2<=args.expected_parts<=128 and args.min_free_gib>=0 and 1<=args.max_file_gib<=16
                and (args.control_index_bases is None or args.control_index_bases>0)):
            raise ValueError('invalid bounded comparison resources')
        import re
        for value in (args.expected_runtime_profile,args.expected_mapper_sha256,args.expected_reference_sha256,args.expected_query_sha256):
            if value is not None and not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('invalid frozen SHA-256')
        if args.minimap_filter is not None:
            if not re.fullmatch('0\\.[0-9]+',args.minimap_filter) or not 0<float(args.minimap_filter)<1:raise ValueError('invalid explicit seed fraction')
        if not args.execute:
            print(json.dumps({'execute':False,'plan_only':True,'output_created':False,'mapping_started':False,
                'timing_scope':'existing_MMI_ordinary_execution_with_production_merge_and_audit',
                'TEST_ONLY_index_bases':args.control_index_bases,'query_copies':args.query_copies},sort_keys=True));return 0
        def stop(sig,frame):raise KeyboardInterrupt('benchmark cancelled')
        signal.signal(signal.SIGTERM,stop)
        result=execute(args);print(json.dumps({'status':result['status'],'summary':result['summary']},sort_keys=True));return 0
    except (OSError,ValueError) as error:
        print(str(error),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
