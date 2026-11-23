"""Produce genuine Server archives over the controlled (non-native) admission test fixture."""
from pathlib import Path
import json
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


def generate(dest, *, project_packages=False, close_deg=False, close_tgs=False):
    root = dest/'job'
    first, _, _ = create(root, with_source_evidence=True, job_outputs=True, sequence="GTTTAC" if close_deg else "GTNNAC")
    build(root,dest/'baseline',True)
    lock = WorkspaceLock(root,'controlled-project-auto-patch')
    lock.acquire()
    try:
        publish_baseline(root,lock)
        for tool in ('degap','tgsgapcloser'):
            result = first if tool=='degap' else create(root,with_source_evidence=True,tool=tool,reuse_workspace=True,sequence="GTCCAC" if close_tgs else "GTNNAC")[0]
            batch={'batch_id':('1' if tool=='degap' else '2')*32,'status':'staged','exit_code':0,
                   'tools':{tool:{'status':'staged','run_id':result['run_id'],'report':build_tool_report(root,result)}}}
            completed=publish_batch(root,lock,{'batch':batch,'staged_results':{tool:result},'exit_code':0})
            if completed['exit_code']: raise ValueError(completed)
            publish_auto_patch(root,lock)
            shutil.copyfile(root/'07_delivery/job.auto.patch.zip', dest/(tool+'.zip'))
        if project_packages:
            from delivery_archive import create_archive
            from project_auto_patch import INDEX
            from project_delivery import project_payload
            from run_orchestration import sha256_file
            import zipfile
            patch = dest / 'tgsgapcloser.zip'
            with zipfile.ZipFile(patch) as archive:
                baseline = json.loads(archive.read(INDEX))['baseline']
            for full in (True, False):
                mode = 'full' if full else 'light'
                staged = dest / mode / 'job'
                build(root, staged, full)
                project_payload(staged, mode, baseline, patch, patch_sha=sha256_file(patch))
                fmt = 'zip' if full else 'tar.gz'
                create_archive(staged, dest / f'job.{mode}.{fmt}', fmt, 1)
    finally:
        lock.release()


if __name__=='__main__':
    generate(Path(sys.argv[1]), project_packages='--project-packages' in sys.argv[2:],
             close_deg='--close-degap' in sys.argv[2:], close_tgs='--close-tgs' in sys.argv[2:])
