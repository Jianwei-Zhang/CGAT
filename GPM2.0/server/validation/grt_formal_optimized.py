#!/usr/bin/env python3
"""Run only the NEW formal GRT suffix on complete frozen historical inputs.

Never runs an old engine. Old result/Final Path artifacts are read-only golden
references. Upstream assignment/reads-QC/Step1 are reused; no chromosome/donor is
subsampled. Numerical/repair caches start empty. This is not whole-run_all timing.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import traceback


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def read_tsv(path):
    with path.open(newline='') as handle: return list(csv.DictReader(handle, delimiter='\t'))


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def freeze_copy(source, destination):
    # Only immutable FASTA is linked. Mutable metadata/runtime/cache/FAI never is.
    if Path(source).suffix.lower() in {'.fa', '.fasta', '.fna'}:
        os.link(Path(source).resolve(), destination)
    else: shutil.copy2(source, destination)


def paths(rows):
    return [tuple(str(row.get(k, '')) for k in ('q_version', 'chr', 'segment_kind', 'q_start', 'q_end',
             'dataset_name', 'contig_name', 'source_start', 'source_end', 'orientation')) for row in rows]


def reason(value):
    for prefix in ('corrected_then_refilled_by:', 'accepted_then_removed_by_step3:'):
        if str(value).startswith(prefix): return prefix.rstrip(':')
    return value


def events(rows):
    result=[]
    for row in rows:
        item={key: row.get(key, '') for key in ('stage','chr','object_id','action','status','error_type',
              'error_subtype','repair_mode','repair_reason','q_after_projection','strategy',
              'classification','fragment_id','donor_reuse','donor_reuse_of')}
        item['reason']=reason(row.get('reason',''))
        item['source']=row.get('source')
        item['edit']=row.get('edit')
        for name in ('q_before','q_after'):
            item[name]={k:v for k,v in (row.get(name) or {}).items() if k in ('version','start','end','sha256')}
        result.append(item)
    return sorted(result,key=lambda x: json.dumps(x,sort_keys=True))


def selected(rows, fields):
    return sorted([tuple(str(row.get(k,'')) for k in fields) for row in rows])


def final_path(document):
    return [{"chr": c['chr'], "q4_length": c['q4_length'], "q4_sha256": c['q4_sha256'],
             "segments": [{k:s.get(k) for k in ('kind','length','orientation','source')} for s in c['segments']]}
            for c in document['chromosomes']]


def fasta_dna(path):
    records=[]; name=None; h=None; length=0
    with path.open('rb') as handle:
        for line in handle:
            if line.startswith(b'>'):
                if name is not None: records.append((name,length,h.hexdigest()))
                name=line[1:].split()[0].decode();h=hashlib.sha256();length=0
            else:
                seq=line.strip();h.update(seq.upper());length+=len(seq)
    if name is not None: records.append((name,length,h.hexdigest()))
    return records


def generate_scripts(source, workspace, threads):
    text=(source/'prepare.sh').read_text()
    names=('make_executable_if_supported','write_grt_step2_script','write_grt_step3_script',
           'write_grt_telomere_finalize_script')
    definitions=[]
    for name in names:
        match=re.search(r'^'+name+r'\(\) \{\n.*?^\}\n',text,re.M|re.S)
        if match is None: raise RuntimeError('Missing production generator: '+name)
        definitions.append(match.group())
    q=shlex.quote
    script='set -euo pipefail\nsource '+q(str(source/'lib/incremental_common.sh'))+'\n'
    for key,value in {'THREADS':str(threads),'GRT_EXECUTION_PROFILE':'optimized',
        'GRT_STEP3_MUMMER_SCOPE':'gap-screen','GRT_REFILL_MAX_LENGTH':'1000000',
        'GRT_MINIMAP2':shutil.which('minimap2'),'GRT_NUCMER':shutil.which('nucmer'),
        'GRT_DELTA_FILTER':shutil.which('delta-filter'),'GRT_SHOW_COORDS':shutil.which('show-coords')}.items():
        if value is None: raise RuntimeError('Missing tool: '+key)
        script+=key+'='+q(value)+'\n'
    script+='\n'.join(definitions)
    for name in ('step2','step3','telomere_finalize'):
        script+=f'\nwrite_grt_{name}_script {q(str(workspace/f"run_grt_{name}.sh"))} {q(str(workspace))}\n'
    (workspace/'generate_formal_scripts.sh').write_text(script)
    subprocess.run(['bash',str(workspace/'generate_formal_scripts.sh')],check=True)
    state=workspace/'.run_all';state.mkdir()
    with (state/'plan.tsv').open('w') as handle:
        handle.write('unit_id\tcommand_relpath\tdetail_log_relpath\n')
        for name in ('step2','step3','telomere_finalize'):
            handle.write(f'grt_{name}\trun_grt_{name}.sh\tlogs/{name}.log\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',required=True)
    parser.add_argument('--prefix',type=Path,required=True)
    parser.add_argument('--old-results',type=Path,required=True)
    parser.add_argument('--old-final',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--threads',type=int,default=8)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    workspace=args.output/'optimized';workspace.mkdir()
    report={'status':'RUNNING','dataset':args.name,'threads':args.threads,'checks':[],
            'boundary':'Only new optimized GRT Step2(full)/Step3(gap-screen)/Step4 and Final Path export on every chromosome and full donors. Upstream assignment/reads-QC/Step1 frozen inputs reused. No old engine invocation, borrowed numerical cache, leaf realignment or delivery packaging. Not whole-pipeline timing.',
            'old_results':str(args.old_results),'old_final':str(args.old_final),'timing_comparability':'Old timing/cache/resources may differ; no direct speedup ratio is asserted.'}
    source_record=args.source/'SOURCE.json'
    if source_record.is_file(): report['source']=json.loads(source_record.read_text())
    def save():
        p=args.output/'report.json';tmp=p.with_suffix('.tmp')
        tmp.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');tmp.replace(p)
    def check(label,expected,observed):
        ok=expected==observed
        row={'label':label,'status':'PASS' if ok else 'FAIL','expected_sha256':identity(expected),'observed_sha256':identity(observed)}
        if not ok:
            row['expected_preview']=repr(expected)[:2000];row['observed_preview']=repr(observed)[:2000]
        report['checks'].append(row);save();print(json.dumps(row),flush=True)
    save()
    try:
        for name in ('data','metadata','grt/donors','grt/evidence/step1'):
            shutil.copytree(args.prefix/name,workspace/name,copy_function=freeze_copy)
        (workspace/'grt/q').mkdir()
        for name in ('q0.fa','q0r1.fa','q0f.fa','q1.fa'):
            if (args.prefix/'grt/q'/name).exists(): freeze_copy(args.prefix/'grt/q'/name,workspace/'grt/q'/name)
        (workspace/'grt/checkpoints').mkdir()
        for p in (args.prefix/'grt/checkpoints').glob('*.json'):
            if p.stem=='donor_freeze' or p.stem.startswith('step1_'): shutil.copy2(p,workspace/'grt/checkpoints'/p.name)
        for name in ('tools','lib','contracts','templates'):
            shutil.copytree(args.source/name,workspace/'.prepare_lib'/name,ignore=shutil.ignore_patterns('__pycache__'))
        if (args.prefix/'tel').exists(): shutil.copytree(args.prefix/'tel',workspace/'tel',copy_function=freeze_copy)
        generate_scripts(args.source,workspace,args.threads)
        options=workspace/'metadata/prepare_options.tsv'
        values={row['key']:row['value'] for row in read_tsv(options)}
        values.update(threads=str(args.threads),grt_execution_profile='optimized',
                      grt_step2_mummer_scope='full',grt_step3_mummer_scope='gap-screen')
        with options.open('w') as handle:
            handle.write('key\tvalue\n')
            for key,value in values.items(): handle.write(key+'\t'+value+'\n')
        prefix_stages={row['stage']:row for row in read_tsv(args.prefix/'metadata/grt_stage_status.tsv')}
        old_stages={row['stage']:row for row in read_tsv(args.old_final/'metadata/grt_stage_status.tsv')}
        check('complete frozen Q1 identity',prefix_stages['step1_round2']['q_output_sha256'],sha(workspace/'grt/q/q1.fa'))
        check('old Final Path shares frozen Q1',prefix_stages['step1_round2']['q_output_sha256'],old_stages['step1_round2']['q_output_sha256'])
        check('new numerical cache starts empty',False,(workspace/'grt/cache').exists())
        if any(c['status']=='FAIL' for c in report['checks']): raise RuntimeError('Input identity gate failed')
        command=[sys.executable,str(workspace/'.prepare_lib/tools/run_all_runner.py'),'--server-dir',str(workspace)]
        started=time.monotonic()
        with (args.output/'formal_run.log').open('w') as log: subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
        report['new_suffix_seconds']=time.monotonic()-started
        report['stage_timings']=read_tsv(workspace/'logs/status.tsv')
        evidence_fields=('stage','evidence_type','status','q_version','source_dataset','source_contig','source_start','source_end',
                         'orientation','target_chr','target_start','target_end','tool','preset','coordinate_system','projection_status')
        usage_fields=('donor_set_id','source_dataset','source_contig','source_start','source_end','stage','status','reason')
        attempt_fields=('chr','object_id','stage','status','reason','candidate_count')
        trace={'candidate_id','event_id','final_path_segment_id'}
        for stage,qversion in (('step2','q2'),('step3','q3')):
            before=args.old_results/'grt/evidence'/stage;after=workspace/'grt/evidence'/stage
            old=json.loads((before/'result.json').read_text());new=json.loads((after/'result.json').read_text())
            check(qversion+' file',old['q_output_sha256'],sha(workspace/'grt/q'/f'{qversion}.fa'))
            check(qversion+' ordered source paths',paths(old['q_rows']),paths(new['q_rows']))
            check(stage+' events',events(old['events']),events(new['events']))
            check(stage+' accepted intervals',selected(old['accepted_intervals'],usage_fields[1:5]),selected(new['accepted_intervals'],usage_fields[1:5]))
            check(stage+' evidence semantics',selected(old['evidence_rows'],evidence_fields),selected(new['evidence_rows'],evidence_fields))
            check(stage+' usage semantics',selected(old['usage_rows'],usage_fields),selected(new['usage_rows'],usage_fields))
            check(stage+' attempts',selected(old['attempts'],attempt_fields),selected(new['attempts'],attempt_fields))
            field='strategies' if stage=='step2' else 'classification_rows'
            keys=sorted(set().union(*(set(row) for row in old[field]+new[field]))-trace)
            check(stage+' '+field,selected(old[field],keys),selected(new[field],keys))
            if stage=='step2':
                for name in ('candidates.tsv','rejections.tsv'):
                    left,right=read_tsv(before/name),read_tsv(after/name)
                    keys=sorted(set().union(*(set(row) for row in left+right))-trace)
                    check('step2 ordered '+name,[[row.get(k,'') for k in keys] for row in left],[[row.get(k,'') for k in keys] for row in right])
            cp=json.loads((workspace/f'grt/checkpoints/{stage}.json').read_text())
            check(stage+' optimized enabled','optimized',cp['fingerprint_payload']['execution_profile'])
            check(stage+' scope','full' if stage=='step2' else 'gap-screen',cp['fingerprint_payload']['mummer_scope'])
        old_doc=json.loads((args.old_final/'metadata/grt_final_path.json').read_text())
        new_doc=json.loads((workspace/'metadata/grt_final_path.json').read_text())
        check('old Q4 artifact identity',old_stages['finalize']['q_output_sha256'],sha(args.old_final/'grt/q/q4.fa'))
        check('q4 file',old_stages['finalize']['q_output_sha256'],sha(workspace/'grt/q/q4.fa'))
        def final_events(path):
            return [json.loads(line) for line in (path/'metadata/grt_events.jsonl').read_text().splitlines() if line.strip()]
        check('finalized accepted repairs',events([r for r in final_events(args.old_final) if r.get('status')=='accepted']),
              events([r for r in final_events(workspace) if r.get('status')=='accepted']))
        check('Final Path ordered source intervals orientations kinds and DNA',final_path(old_doc),final_path(new_doc))
        tsv=workspace/'FinalPath.tsv'
        with tsv.open('w',newline='') as handle:
            writer=csv.writer(handle,delimiter='\t',lineterminator='\n')
            writer.writerow(('Chr','#','Ctg','Origin ID','overall_len','orient','Ctg_start','Ctg_end','Chr_start','Chr_end'))
            for chromosome in new_doc['chromosomes']:
                start=1
                for number,segment in enumerate(chromosome['segments'],1):
                    end=start+int(segment['length'])-1;src=segment.get('source')
                    values=(src['dataset']+'_'+src['contig'],src['contig'],'',src['orientation'],src['start'],src['end']) if src else ('Gap','NA','','+',1,segment['length'])
                    writer.writerow((chromosome['chr'],number,*values,start,end));start=end+1
        export=workspace/'FinalPath.fa'
        subprocess.run(['bash',str(args.source/'export_final_path_fasta.sh'),'--gpm_server',str(workspace),'--tsv',str(tsv),'-o',str(export)],check=True)
        check('Final Path exported chromosome names order lengths DNA',fasta_dna(workspace/'grt/q/q4.fa'),fasta_dna(export))
        for stage in ('step4_telomere','finalize'):
            cp=json.loads((workspace/f'grt/checkpoints/{stage}.json').read_text());check(stage+' genuine checkpoint','success',cp['status'])
        report['refill_batches']=[json.loads(p.read_text()) for p in (workspace/'grt/evidence/step3/refill').glob('*/batch/provenance.json')]
        report['status']='PASS' if all(c['status']=='PASS' for c in report['checks']) else 'FAIL'
    except BaseException:
        report['status']='ERROR';report['exception']=traceback.format_exc();raise
    finally:
        save()
    print('FORMAL_OPTIMIZED_RESULT',report['status'],len(report['checks']),flush=True)
    if report['status']!='PASS': raise SystemExit('Full-data result comparison failed; keep artifacts')


if __name__=='__main__': main()
