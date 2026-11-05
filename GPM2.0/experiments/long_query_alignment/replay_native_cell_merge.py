#!/usr/bin/env python3
"""Maintainer-only completed native-PAF assembly replay; never launches a mapper."""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import resource
import shutil
import sys
import time


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>64*1024**2:
        raise ValueError('invalid completed JSON evidence')
    return json.loads(path.read_text())


def require(value,message):
    if not value:raise ValueError(message)


def write(path,data):
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')


def execute(args):
    runtime=args.runtime_root.resolve();files=read(runtime/'branch-runtime.json')['files_sha256']
    profile=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(profile==args.profile,'unexpected runtime source profile')
    for name,wanted in files.items():
        require(Path(name).name==name and not (runtime/name).is_symlink()
            and sha(runtime/name)==wanted,'runtime source bytes changed')
    require('native_first' not in sys.modules,'foreign native assembly module already loaded')
    sys.path.insert(0,str(runtime));nf=importlib.import_module('native_first')
    root=args.case_root.resolve();report=read(root/'benchmark.json')
    require(report['status']=='complete_equal','input comparison is still running or failed; no replay')
    trial_path=root/'r00-native-mmi/trial.json';trial=read(trial_path)
    require(trial in report['runs'] and trial['mode']=='native-mmi' and trial['status']=='complete',
        'input trial was not completed by the frozen comparison')
    native_path=trial_path.parent/'native/native-attempt.json';native=read(native_path)
    source=Path(native['path']);source_sha=native['paf_sha256']
    require(source.is_file() and not source.is_symlink() and native==trial['native'] and native['status']=='native_success' and native['paf_usable'] is True
        and native['execution']['returncode']==0 and source_sha==trial['paf_sha256']
        and sha(source)==source_sha,'completed native source/receipt changed')
    guards={p:(p.stat().st_size,p.stat().st_mtime_ns,sha(p)) for p in (trial_path,native_path,source)}
    out=args.out.resolve()
    require(not args.out.is_symlink() and not out.exists() and out.parent.is_dir(),'fresh private output required')
    require(shutil.disk_usage(out.parent).free>=4*1024**3,'insufficient private scratch; no replay')
    for key,requested in ((resource.RLIMIT_AS,8*1024**3),(resource.RLIMIT_FSIZE,2*1024**3)):
        soft,hard=resource.getrlimit(key)
        cap=min([requested,*[v for v in (soft,hard) if v!=resource.RLIM_INFINITY]])
        resource.setrlimit(key,(cap,hard))
    out.mkdir();write(out/'input-native-receipt.json',native)
    queries={r['name']:r for r in report['sources']['query']['records']}
    targets={r['name']:r for r in report['sources']['reference']['records']}
    started=time.monotonic();before=resource.getrusage(resource.RUSAGE_SELF)
    merger=nf.CellMerger(out/'cells',queries,targets,report['index']['parts'])
    rows=merger.add_native(native,list(queries));combined=merger.finish(out/'complete.paf')
    seconds=time.monotonic()-started;after=resource.getrusage(resource.RUSAGE_SELF)
    require(sha(out/'complete.paf')==source_sha and rows==trial['paf_rows']
        and combined['all_cells_completed'] is True,'raw bytes/order or original completion matrix changed')
    for p,wanted in guards.items():
        require((p.stat().st_size,p.stat().st_mtime_ns,sha(p))==wanted,'immutable completed evidence changed during replay')
    for name,wanted in files.items():require(sha(runtime/name)==wanted,'runtime changed during replay')
    result={'schema':1,'status':'complete_equal','runtime_profile':profile,'host':__import__('os').uname().nodename,
        'merge_seconds':seconds,'self_cpu_seconds':after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
        'paf_sha256':source_sha,'paf_rows':rows,'paf_bytes':source.stat().st_size,'combination':combined,
        'mapping_started':False,'original_evidence_modified':False,'automatic_retry':False,
        'timing_scope':'CellMerger_init_add_native_finish_including_internal_validation_not_full_CGAT',
        'input_native_receipt_path':str(native_path),'runtime_files_sha256':files,
        'original_source_data_and_MMI_not_reprocessed':True}
    write(out/'replay.json',result);print(json.dumps(result,sort_keys=True))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--profile',required=True)
    p.add_argument('--case-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--execute',action='store_true');args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps({'plan_only':True,'mapping_started':False,'files_created':False}));return 0
    execute(args);return 0


if __name__=='__main__':raise SystemExit(main())
