"""Verify a separate, authentic buffered initial proof; never fabricate validation.json."""
import hashlib
import json
from pathlib import Path
import re

from q0_science_context import checked, digest


def _member(row, expected):
    if checked(row) != expected.resolve(strict=True) or Path(row['path']) != expected:
        raise ValueError('buffered proof artifact is not at its declared path: ' + str(expected))
    return expected


def _json(row, expected):
    return json.loads(_member(row,expected).read_text())


def verify_buffered_proof(stage_root, transition_record, proof_record, scheduler_record):
    """Complete proof plus real scheduler success, launch identity and original 25 rows."""
    stage_root = Path(stage_root).resolve(strict=True)
    tpath = _member(transition_record,stage_root/'transition.json')
    transition = json.loads(tpath.read_text())
    work = Path(transition['workspace']).resolve(strict=True)
    proof_path = checked(proof_record)
    root = proof_path.parent
    if (proof_path.name != 'buffered-proof.json' or root.parent != stage_root.parent or root == stage_root
            or root.is_relative_to(work) or stage_root.is_relative_to(work)):
        raise ValueError('buffered proof is not a separate incident packet')
    proof = json.loads(proof_path.read_text())
    if (proof['status'] != 'buffered_preflight_probe_only_no_handoff_authority'
            or any(proof.get(k) is not False for k in ('workspace_modified','main_task_submitted','q0_runtime_installed'))):
        raise ValueError('wrong or incomplete buffered proof type')
    bound = proof['bindings']
    stage = _json(bound['candidate_prepared'],stage_root/'candidate-prepared.json')
    if (bound['original_staged_transition'] != transition_record or stage['transition'] != transition_record
            or bound['previous_transition'] != stage['previous_transition']
            or stage.get('status') != 'q0_candidate_prepared_not_installed'):
        raise ValueError('buffered proof does not bind this runtime transition')
    origin = _json(bound['origin_probe'],root/'origin-probe.json')
    if (origin['workspace'] != str(work) or origin['native_origin'] != transition['native_origin']
            or origin['phase'] != 'origin_probe' or origin['scientific_builder_modified'] is not False
            or origin['dependencies']['context'] != transition['dependencies']['context']):
        raise ValueError('buffered probe is not bound to the authentic original context')
    _member(origin['dependencies']['probe'],root/'probe_q0_buffered_preflight.py')
    _member(bound['candidate_reader'],root/'buffered_reader.py')
    previous = checked(stage['previous_transition'])
    prior = _json(bound['previous_report'],previous.with_name('validation.json'))
    rows = proof['initial_checkpoints']
    if (prior['status'] != 'q0_transition_all_initial_checkpoints_verified_only'
            or prior['transition_sha256'] != stage['previous_transition']['sha256']
            or any(prior.get(k) is not False for k in ('workspace_modified','main_task_submitted','q0_runtime_installed'))
            or rows != prior['initial_checkpoints'] or len(rows) != 25):
        raise ValueError('buffered proof differs from real original checkpoint identities')
    ids = [r['unit_id'] for r in rows]
    if (len(set(ids)) != 25 or ids[2] != 'assign' or any(not k.startswith('ref:') for k in ids[:2])
            or any(not k.startswith('q0_chr:') for k in ids[3:])
            or any(not re.fullmatch('[a-f0-9]{64}',r[k]) for r in rows for k in ('input_fingerprint','checkpoint_sha256'))):
        raise ValueError('buffered proof has malformed or incomplete initial identities')
    match = re.fullmatch(r'\s*Submit job <([1-9][0-9]*)> successfully\.\s*',(root/'submit.txt').read_text())
    if match is None:
        raise ValueError('no unambiguous Donau submission receipt for buffered probe')
    job_id = match[1]
    scheduler = _json(scheduler_record,root/f'terminal-{job_id}.json')['data']['successData']
    if len(scheduler) != 1:
        raise ValueError('ambiguous Donau terminal packet')
    job = scheduler[0]
    if (str(job['jobId']) != job_id or job['state'] != 'SUCCEEDED' or job['jobExitCode'] != 0
            or job.get('queue') != 'x86' or job.get('taskExecNodesCount') != 1
            or Path(job['execPath']) != root or Path(job['cmd']) != root/'run.dsub'):
        raise ValueError('buffered proof job did not complete on the verified path')
    intent = json.loads((root/'submission.intent').read_text())
    launcher = json.loads((root/'retry-launcher.json').read_text())
    watched_path = Path(launcher['existing_watch'])
    _member({'path':str(watched_path),'sha256':launcher['existing_watch_sha256']},stage_root/'loader-watcher-3h-config.json')
    watched = json.loads(watched_path.read_text())
    if (intent['operation'] != 'once_read_only_after_timeout' or intent['prior']['state'] != 'FAILED'
            or intent['prior']['jobExitCode'] != 124 or str(intent['prior']['jobId']) != str(watched['preflight_job'])
            or watched['transition'] != transition_record or str(intent['main_job']) != str(stage['previous_job'])
            or str(intent['protected_baseline']) != str(stage['protected_baseline'])):
        raise ValueError('buffered probe was not launched for this exact old diagnostic and main job')
    for name in ('config.sha256','job.sha256'):
        if digest(root/name) != launcher[name]:
            raise ValueError('buffered manifest changed')
    manifest = {}
    for line in (root/'job.sha256').read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  ([a-z0-9_.]+)',line)
        if match is None or match[2] in manifest:
            raise ValueError('invalid buffered probe manifest')
        manifest[match[2]] = match[1]
    if set(manifest) != {'probe_q0_buffered_preflight.py','test_probe_q0_buffered_preflight.py','buffered_reader.py','run.dsub'}:
        raise ValueError('buffered probe manifest has wrong scope')
    for name, sha in manifest.items():
        _member({'path':str(root/name),'sha256':sha},root/name)
    if json.loads((root/'config.json').read_text()) != bound:
        raise ValueError('actual buffered proof binding does not match launch configuration')
    # Refuse an old proof if the committed small receipt documents have drifted.
    # The ordinary owner still fully revalidates bound contents after locking.
    for row in rows:
        unit = row['unit_id']
        label = ''.join(c if c.isalnum() else '-' for c in unit)[:48]
        name = hashlib.sha256(json.dumps(unit,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()[:16]
        path = work/'.run_all/checkpoints'/f'{label}.{name}.json'
        if path.is_symlink() or digest(path) != row['checkpoint_sha256']:
            raise ValueError('initial checkpoint receipt changed since buffered verification: '+unit)
    return rows
