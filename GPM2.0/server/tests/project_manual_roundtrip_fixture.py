"""Real publication and re-import bridge; only the two native tool responses are controlled."""
import hashlib
import json
from pathlib import Path
import sys

from project_auto_patch_fixture import publish_baseline, publish_batch, build_tool_report, create, WorkspaceLock
from job_final_catalog import publish_catalog
from project_delivery_publish import publish_current
from refine import prepare_batch, read_tasks
from refine_run import publish_results
from run_orchestration import sha256_file
from workspace_layout import WorkspaceLayout


def generate(root):
    result, _, _ = create(root, job_outputs=True, project_delivery=True, with_source_evidence=True)
    layout = WorkspaceLayout.detect(root)
    report = layout.path('report'); report.mkdir(parents=True, exist_ok=True)
    for name, value in [('manifest.json', '{}'), ('report.html', '<html></html>'), ('render_report.py', '# fixture')]:
        (report / name).write_text(value)
    lock = WorkspaceLock(root, 'manual-roundtrip-setup'); lock.acquire()
    try:
        publish_baseline(root, lock)
        batch = {'batch_id':'2'*32, 'status':'staged', 'exit_code':0, 'tools':{'degap':{
            'status':'staged', 'run_id':result['run_id'], 'report':build_tool_report(root, result)}}}
        result = publish_batch(root, lock, {'batch':batch, 'staged_results':{'degap':result}, 'exit_code':0})
        if result['exit_code']: raise ValueError(batch)
        publish_catalog(root, lock, batch['batch_id'], batch['tools']); publish_current(root, lock)
    finally:
        lock.release()


def manual(root, archive):
    layout = WorkspaceLayout.detect(root)
    def public_pair():
        return {f.name:sha256_file(f) for f in layout.path('07_delivery').iterdir() if f.is_file()}
    before = public_pair(); batch, task = read_tasks(archive)
    assert task['tool_parameters']['lrgapcloser']['iterations'] == 5 and 'snapshot_sha256' in task
    prepared = prepare_batch(root, archive)
    assert all(r['status']=='prepared' for r in prepared['loci']), prepared
    directory = layout.path('04_refinement/manual/'+batch)
    rows, patches = [], {}
    lock = WorkspaceLock(root, 'manual-roundtrip-admission'); lock.acquire()
    try:
        for locus in task['loci']:
            for tool in locus['tools']:
                data = {'degap':b'GATTACA', 'lrgapcloser':b'CCC'}[tool]
                name = f"patches/{locus['id']}.{tool}.seq"
                source = directory / (tool+'.seq'); source.write_bytes(data); patches[name] = source
                n = locus['gap_bp']
                rows.append({'locus_id':locus['id'], 'tool':tool, 'status':'closed', 'reason':None,
                             'version':'controlled', 'revision':'controlled', 'attempt_id':tool+'-fixture',
                             'patch':{'operation':'replace_gap', 'original_length':n, 'original_sha256':hashlib.sha256(b'N'*n).hexdigest(),
                                      'path':name, 'length':len(data), 'sha256':hashlib.sha256(data).hexdigest()}})
        out = publish_results(layout, directory, batch, rows, patches, manifest=task, reads={})
        assert Path(out['delivery']) == layout.path(f'07_delivery/manual/job.manual-{batch[:16]}.patch.zip')
        assert before == public_pair() and len(before)==3
        assert f'job.manual-{batch[:16]}.fa' in layout.path('05_final/results.tsv').read_text()
    finally:
        lock.release()


if __name__ == '__main__':
    root = Path(sys.argv[1]) / 'job'
    if len(sys.argv) == 2: generate(root)
    else: manual(root, Path(sys.argv[2]))
