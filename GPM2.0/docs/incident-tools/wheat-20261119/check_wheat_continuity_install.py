"""Small metadata/control fences, never a replacement for output validation."""
import json,sys
from pathlib import Path
from q0_science_context import digest
root=Path(__file__).resolve().parent;work=root.parent/'gpm_server'
def snapshot():
    paths=list((work/'.run_all/checkpoints').glob('*.json'))
    paths += [work/n for n in ['.run_all/plan.tsv','.run_all/resources.json','run_all.sh',
              '.prepare_lib/tools/run_orchestration.py','.prepare_lib/tools/lgz_prepare_inputs.py',
              '.prepare_lib/tools/run_resources.py'] if (work/n).is_file()]
    return {str(p.relative_to(work)):digest(p) for p in sorted(paths)}
mode=sys.argv[1]
transition=json.loads((root/'transition.json').read_text())
if transition.get('continuous_q0_policy_change',{}).get('engine_revision') != '2064cb4cfd51b5c886f60af19f020caf0b18950f':
    raise ValueError('not the reviewed continuity transition')
if mode=='before':
    with (root/'control-before.json').open('x') as stream:json.dump(snapshot(),stream,indent=2)
else:
    before=json.loads((root/'control-before.json').read_text());after=snapshot()
    if len([n for n in before if n.startswith('.run_all/checkpoints/')]) != 25:
        raise ValueError('unexpected original parent checkpoint count')
    if before!=after:raise ValueError('original checkpoints or protected control files changed')
    receipt=json.loads((root/'install-only.json').read_text())
    declaration=json.loads((root/'installed-reader.json').read_text())
    selected=json.loads((root/'validation-selected.json').read_text())
    if receipt['main_task_started'] or declaration['q0_supplement_scope']!='positive_threshold':
        raise ValueError('unexpected runtime/startup scope')
    if [r['unit_id'] for r in selected['initial_checkpoints']]!=['q0_chr:Un']:
        raise ValueError('representative routed parent was not actually validated')
    if any((work/n).exists() for n in ['metadata/grt_q0_evidence.json','grt/q/q0.fa']):
        raise ValueError('unexpected formal Q0 output during install-only')
    report={'continuous_q0_policy_change':transition['continuous_q0_policy_change'], 'status':'continuity_engine_installed_and_one_original_parent_verified','transition_sha256':digest(root/'transition.json'),
            'source_revision':(root/'source-revision.txt').read_text().strip(),
            'checkpoint_files_unchanged':len([n for n in before if n.startswith('.run_all/checkpoints/')]),
            'protected_control_files_unchanged':True,'representative_parent':selected['initial_checkpoints'][0],
            'all_25_parent_payloads_revalidated':False,'formal_main_started':False,'mapper_calls':0,
            'validation_job_untouched':43137178,
            'reader_declaration_sha256':digest(root/'installed-reader.json'),'installation_receipt_sha256':digest(root/'installation/receipt.json')}
    with (root/'entry-repair.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps(report),flush=True)
