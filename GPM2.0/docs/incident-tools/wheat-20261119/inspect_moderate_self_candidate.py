"""Compare a complete f=.001/.002 self candidate with committed native output.

Does not run a mapper, adopt a candidate, change a native marker, or reinterpret
an incomplete result as a baseline. Follow with audit_self_fast_evidence for
identity/ambiguity strata; this report has the same verified source inventory.
"""
import argparse
import importlib
import json
from pathlib import Path
import sys

import full_self_moderate_candidate as driver
import full_self_seed_pilot as pilot
import inspect_full_self_pilot as inspection
import self_paf_comparison as comparison


def candidate_contract(report, manifest, batch):
    if (report.get('scope') != driver.SCOPE
            or report.get('status') != 'moderate_candidate_complete_not_adopted'
            or report.get('candidate_adopted') is not False
            or report.get('analysis_workspace_modified') is not False
            or report.get('whole_records_preserved') is not True
            or report.get('mapping', {}).get('returncode') != 0
            or report.get('restoration', {}).get('returncode') != 0
            or report.get('native_batch_key') != batch['key']):
        raise ValueError('complete isolated moderate candidate required')
    if driver.moderate_command(manifest, batch, report['native_command'], report.get('seed_fraction')) != report.get('command'):
        raise ValueError('actual command differs from the declared moderate fraction')
    proofs = [proof for path, proof in report['code'].items() if Path(path).name == Path(driver.__file__).name]
    if len(proofs) != 1 or proofs[0]['sha256'] != pilot.digest(Path(driver.__file__)):
        raise ValueError('use the matching frozen candidate driver')


def execute(work, manifest_path, batch_index, candidate_dir, output):
    work, manifest_path = work.resolve(strict=True), manifest_path.resolve(strict=True)
    manifest_path.relative_to(work)
    candidate_dir = candidate_dir.resolve(strict=True)
    pilot.require_isolated(work, output)
    if candidate_dir == work or candidate_dir.is_relative_to(work) or output.resolve().is_relative_to(candidate_dir):
        raise ValueError('keep comparison separate from workspace and immutable candidate')
    manifest = json.loads(manifest_path.read_text())
    if not 0 <= batch_index < len(manifest['batches']):
        raise ValueError('invalid self batch index')
    batch = manifest['batches'][batch_index]
    directory = Path(batch['directory']).resolve(strict=True); directory.relative_to(work)
    source = candidate_dir / 'candidate.json'; raw = source.read_bytes(); report = json.loads(raw)
    candidate_contract(report, manifest, batch)
    if set(report['outputs']) != {str(candidate_dir/n) for n in inspection.OUTPUT_NAMES | {'restore.stderr.log'}}:
        raise ValueError('candidate output inventory differs')
    inputs = inspection.checked_files(report['inputs']); outputs = inspection.checked_files(report['outputs'])
    inspection.checked_files(report['code'])
    if str(manifest_path) not in inputs or str(Path(batch['query'])) not in inputs:
        raise ValueError('candidate does not bind requested manifest/query')
    tools = work/'.prepare_lib/tools'; helper_path = tools/'self_alignment_batches.py'
    if str(helper_path) not in inputs:
        raise ValueError('candidate does not bind native validator')
    sys.path.insert(0,str(tools)); helper=importlib.import_module('self_alignment_batches')
    if Path(helper.__file__).resolve() != helper_path:
        raise ValueError('wrong frozen native validator')
    names = dict(line.split('\t',1) for line in Path(manifest['name_map']).read_text().splitlines() if line)
    queries = {entry['name']:entry['length'] for entry in batch['entries']}
    proof = inspection.native_commit(directory,batch['key'])
    for folder in (directory,candidate_dir):
        pilot.verify_completion(folder/'stderr.log',len(queries))
        helper.validate_raw(folder/'raw.paf',queries,manifest['target_lengths'])
        helper.validate_raw(folder/'result.paf',{names[k]:v for k,v in queries.items()},
                            {names[k]:v for k,v in manifest['target_lengths'].items()})
    result = {'scope':'one_full_self_query_diagnostic','candidate_adopted':False,
        'analysis_workspace_modified':False,'seed_fraction':report['seed_fraction'],
        'candidate_report':pilot.identities([source]),'candidate_mapping':report['mapping'],
        'candidate_inputs':inputs,'candidate_outputs':outputs,'native_commit':proof,
        'comparison_1kb':comparison.compare(directory/'result.paf',candidate_dir/'result.paf'),
        'code':pilot.identities([Path(__file__),Path(driver.__file__),Path(pilot.__file__),
            Path(inspection.__file__),Path(comparison.__file__)])}
    inspection.checked_files(inputs);inspection.checked_files(outputs);inspection.checked_files(report['code'])
    if source.read_bytes()!=raw or inspection.native_commit(directory,batch['key'])!=proof:
        raise ValueError('candidate or native source changed during comparison')
    result['status']='candidate_and_committed_native_compared_not_adopted'
    if output.exists(): raise ValueError('refusing to replace comparison report')
    helper.atomic_json(output,result)
    print(json.dumps({'status':result['status'],'seed_fraction':result['seed_fraction'],
        'mapping':result['candidate_mapping'],'position_support':result['comparison_1kb']['position_support']}),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('work','manifest','candidate-dir','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--batch-index',type=int,required=True)
    args=parser.parse_args()
    execute(args.work,args.manifest,args.batch_index,args.candidate_dir,args.output)
