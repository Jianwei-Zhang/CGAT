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


def generate_scripts(source, workspace, threads, step2_scope="full"):
    text=(source/'prepare.sh').read_text()
    names=('shell_quote','make_executable_if_supported','write_grt_step2_script','write_grt_step3_script',
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
    # This is an experiment-only override. Production prepare keeps Step2 full.
    if step2_scope != 'full':
        path=workspace/'run_grt_step2.sh'
        text=path.read_text().replace('--step2-mummer-scope full', '--step2-mummer-scope '+step2_scope)
        path.write_text(text)
    for name in ('step2','step3','telomere_finalize'):
        path=workspace/f'run_grt_{name}.sh'
        words=shlex.split(path.read_text().splitlines()[-1])
        expected=str(workspace/f'.prepare_lib/tools/grt_{name}.py')
        if len(words)<4 or words[0]!='python3' or words[1]!=expected:
            raise RuntimeError('Invalid generated production command: '+str(path))
        if words[words.index('--server-dir')+1] != str(workspace):
            raise RuntimeError('Missing/wrong generated workspace argument')
        subprocess.run(['bash','-n',str(path)],check=True)
    state=workspace/'.run_all';state.mkdir(exist_ok=True)
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
    parser.add_argument('--step2-scope',choices=('full','gap-screen'),default='full')
    parser.add_argument('--resume',action='store_true',help='Resume a NEW-only launcher failure with no numerical cache')
    parser.add_argument('--paired-full',type=Path,help='Corresponding new optimized full-scope case; read-only timing/result reference')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=args.resume)
    workspace=args.output/'optimized';workspace.mkdir(exist_ok=args.resume)
    if args.resume and (args.output/'report.json').exists():
        history=args.output/'launcher-error-before-repair.json'
        if not history.exists(): shutil.copy2(args.output/'report.json',history)
    report={'status':'RUNNING','dataset':args.name,'threads':args.threads,'checks':[],
            'boundary':'Only new optimized GRT Step2(selected scope)/Step3(gap-screen)/Step4 and Final Path export on every chromosome and full donors. Upstream assignment/reads-QC/Step1 frozen inputs reused. No old engine invocation, borrowed numerical cache, leaf realignment or delivery packaging. Not whole-pipeline timing.',
            'old_results':str(args.old_results),'old_final':str(args.old_final),'step2_scope':args.step2_scope,
            'validation_script_sha256':sha(Path(__file__)),'timing_comparability':'Old timing/cache/resources may differ; no direct speedup ratio is asserted.'}
    source_record=args.source/'SOURCE.json'
    if source_record.is_file(): report['source']=json.loads(source_record.read_text())
    def save():
        p=args.output/'report.json';tmp=p.with_suffix('.tmp')
        tmp.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');tmp.replace(p)
    def check(label,expected,observed,category='core'):
        ok=expected==observed
        row={'label':label,'category':category,'status':'PASS' if ok else 'FAIL','expected_sha256':identity(expected),'observed_sha256':identity(observed)}
        if not ok:
            row['expected_preview']=repr(expected)[:2000];row['observed_preview']=repr(observed)[:2000]
        report['checks'].append(row);save();print(json.dumps(row),flush=True)
    save()
    try:
        if not args.resume:
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
        generate_scripts(args.source,workspace,args.threads,args.step2_scope)
        options=workspace/'metadata/prepare_options.tsv'
        values={row['key']:row['value'] for row in read_tsv(options)}
        values.update(threads=str(args.threads),grt_execution_profile='optimized',
                      grt_step2_mummer_scope=args.step2_scope,grt_step3_mummer_scope='gap-screen')
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
        with (args.output/'formal_run.log').open('a') as log: subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
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
            check(stage+' events',events(old['events']),events(new['events']),'audit')
            check(stage+' accepted events',events([r for r in old['events'] if r.get('status')=='accepted']),
                  events([r for r in new['events'] if r.get('status')=='accepted']))
            check(stage+' accepted intervals',selected(old['accepted_intervals'],usage_fields[1:5]),selected(new['accepted_intervals'],usage_fields[1:5]))
            check(stage+' evidence semantics',selected(old['evidence_rows'],evidence_fields),selected(new['evidence_rows'],evidence_fields),'audit')
            check(stage+' usage semantics',selected(old['usage_rows'],usage_fields),selected(new['usage_rows'],usage_fields),'audit')
            check(stage+' attempts',selected(old['attempts'],attempt_fields),selected(new['attempts'],attempt_fields),'audit')
            field='strategies' if stage=='step2' else 'classification_rows'
            keys=sorted(set().union(*(set(row) for row in old[field]+new[field]))-trace)
            check(stage+' '+field,selected(old[field],keys),selected(new[field],keys),'audit')
            check(stage+' consumed donor usage',selected([r for r in old['usage_rows'] if r.get('status')=='consumed'],usage_fields),
                  selected([r for r in new['usage_rows'] if r.get('status')=='consumed'],usage_fields))
            if stage=='step2':
                decision_fields=('chr','strategy','strategy_applied','accepted_patch_count','accepted_fallback_count','reason')
                check('step2 applied strategy',selected(old[field],decision_fields),selected(new[field],decision_fields))
            else:
                check('step3 accepted classification',selected([r for r in old[field] if r.get('outcome')=='accepted'],keys),
                      selected([r for r in new[field] if r.get('outcome')=='accepted'],keys))
            if stage=='step2':
                for name in ('candidates.tsv','rejections.tsv'):
                    left,right=read_tsv(before/name),read_tsv(after/name)
                    keys=sorted(set().union(*(set(row) for row in left+right))-trace)
                    check('step2 ordered '+name,[[row.get(k,'') for k in keys] for row in left],[[row.get(k,'') for k in keys] for row in right],'audit')
            cp=json.loads((workspace/f'grt/checkpoints/{stage}.json').read_text())
            check(stage+' optimized enabled','optimized',cp['fingerprint_payload']['execution_profile'])
            check(stage+' scope',args.step2_scope if stage=='step2' else 'gap-screen',cp['fingerprint_payload']['mummer_scope'])
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
        report['core_status']='PASS' if all(c['status']=='PASS' for c in report['checks'] if c['category']=='core') else 'FAIL'
        report['audit_status']='PASS' if all(c['status']=='PASS' for c in report['checks'] if c['category']=='audit') else 'DIFFERENT'
        final_labels=('q4 file','Final Path ordered source intervals orientations kinds and DNA','Final Path exported chromosome names order lengths DNA')
        report['final_path_status']='PASS' if all(c['status']=='PASS' for c in report['checks'] if c['label'] in final_labels) else 'FAIL'
        report['status']=('FAIL' if report['core_status']!='PASS' else 'PASS' if report['audit_status']=='PASS'
                          else 'CORE_PASS_AUDIT_DIFFERENT' if args.step2_scope=='gap-screen' else 'FAIL')
        if args.paired_full:
            report['paired_full']=str(args.paired_full)
            pair=args.paired_full/'report.json'
            if pair.is_file():
                full=json.loads(pair.read_text())
                report['paired_full_observed_status']=full['status']
                if full.get('new_suffix_seconds') and full.get('threads')==args.threads:
                    report['paired_timing']={'full_seconds':full['new_suffix_seconds'],'gap_seconds':report['new_suffix_seconds'],
                                            'wall_reduction_fraction':1-report['new_suffix_seconds']/full['new_suffix_seconds'],
                                            'boundary':'Same pinned new runtime/resources and empty numerical caches; one pass, different nodes/OS caches may affect timing.'}
        report['result_semantics']='Full audit equality is distinct from core/Final Path equality. No default scope change is authorized by this experiment.'
    except BaseException:
        report['status']='ERROR';report['exception']=traceback.format_exc();raise
    finally:
        save()
    print('FORMAL_OPTIMIZED_RESULT',report['status'],len(report['checks']),flush=True)
    if report['status'] not in {'PASS','CORE_PASS_AUDIT_DIFFERENT'}: raise SystemExit('Full-data result comparison failed; keep artifacts')


if __name__=='__main__': main()
