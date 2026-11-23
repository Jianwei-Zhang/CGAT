"""Produce genuine Server archives over the controlled (non-native) admission test fixture."""
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from lgz_app_package import build
from lgz_final import publish_baseline
from project_auto_patch import publish_auto_patch
from refinement_batch import publish_batch
from refinement_bundle_fixture import create
from refinement_reports import build_tool_report
from run_all_runner import WorkspaceLock


def generate(dest):
    root = dest/'job'
    first, _, _ = create(root, with_source_evidence=True, job_outputs=True)
    build(root,dest/'baseline',True)
    lock = WorkspaceLock(root,'controlled-project-auto-patch')
    lock.acquire()
    try:
        publish_baseline(root,lock)
        for tool in ('degap','tgsgapcloser'):
            result = first if tool=='degap' else create(root,with_source_evidence=True,tool=tool,reuse_workspace=True)[0]
            batch={'batch_id':('1' if tool=='degap' else '2')*32,'status':'staged','exit_code':0,
                   'tools':{tool:{'status':'staged','run_id':result['run_id'],'report':build_tool_report(root,result)}}}
            completed=publish_batch(root,lock,{'batch':batch,'staged_results':{tool:result},'exit_code':0})
            if completed['exit_code']: raise ValueError(completed)
            publish_auto_patch(root,lock)
            shutil.copyfile(root/'07_delivery/job.auto.patch.zip', dest/(tool+'.zip'))
    finally:
        lock.release()


if __name__=='__main__':
    generate(Path(sys.argv[1]))
