"""Build two reviewable reports from independent controlled runs. Never use an existing output dir."""
import argparse
import json
import os
from pathlib import Path
import sys

GPM = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(GPM), str(GPM/'server/tools')]


def lgz_example(home):
    from test_grt_telomere_finalize import GrtTelomereFinalizeTests
    from server_report import ReportSession,step_record
    from server_report_collect import capture_final,collect_assignment,collect_lgz_inputs,collect_lgz_result,final_summary
    from server_report_io import write_json,SCHEMA
    from render_server_report import project_report_facts
    from report_overview_data import build_overview_view_model
    from render_overview_report import render_overview

    home.mkdir();fixture=GrtTelomereFinalizeTests();root=fixture.make_server(home)
    result=fixture.run_finalize(root,fixture.make_tools(home),dict(os.environ,FAKE_TEL_MINIMAP_LOG=str(home/'minimap.log'),FAKE_TEL_MUMMER_LOG=str(home/'mummer.log')))
    if result.returncode:raise RuntimeError(result.stderr)
    s=ReportSession(root,[],'controlled-final-path');units=[('assign',collect_assignment(root,s.input_data)),('lgz_prepare',collect_lgz_inputs(root))]
    for i,(unit,facts) in enumerate(units,1):
        path=f'steps/{i:03}.json';s.manifest['steps'].append(path);write_json(s.report/path,step_record(s.run_id,unit,status='success',facts=project_report_facts(facts)))
    for unit in ('step1','step2','step3'):
        result=json.loads((root/f'grt/evidence/{unit}/result.json').read_text());facts=collect_lgz_result(root,result)
        write_json(s.report/f'steps/grt-{unit}.json',step_record(s.run_id,unit,status='success',facts=project_report_facts(facts)))
    s.manifest['status']='success';s.save();write_json(s.report/'final_snapshot.json',dict(capture_final(root),schema_version=SCHEMA,run_id=s.run_id));write_json(s.report/'final_summary.json',final_summary(root,s.report))
    vm=build_overview_view_model(root);assert vm['final_versions'][0]['tracks'] and all(vm['lgz_summary'][k] for k in ('q0_scene','step1_scene','step2_scene','terminal_scene'))
    page=home/'lgz-only.html';page.write_text(render_overview(vm));return page


def refined_example(root):
    from project_manual_roundtrip_fixture import WorkspaceLock,publish_baseline,publish_catalog,build_tool_report,publish_batch
    from refinement_bundle_fixture import create
    from refinement_overview import render_overview
    from refinement_batch import baseline_seal
    from refine_report import automatic_overview_digest
    from test_report_manual_story import run_export
    from workspace_layout import WorkspaceLayout

    results={}
    for i,(tool,seq) in enumerate([('degap','GTTTAC'),('tgsgapcloser','ACGT')]):
        results[tool],_,_=create(root,with_source_evidence=True,project_delivery=True,job_outputs=True,sequence=seq,tool=tool,reuse_workspace=bool(i))
    layout=WorkspaceLayout.detect(root);batch=dict(batch_id='2'*32,status='staged',exit_code=0,tools={t:dict(status='staged',run_id=r['run_id'],report=build_tool_report(root,r)) for t,r in results.items()},baseline_inputs=baseline_seal(root))
    lock=WorkspaceLock(root,'controlled-review');lock.acquire()
    try:
        publish_baseline(root,lock);result=publish_batch(root,lock,dict(batch=batch,staged_results=results,exit_code=0));assert not result['exit_code']
        publish_catalog(root,lock,batch['batch_id'],batch['tools']);render_overview(root,batch,results)
    finally:lock.release()
    page=layout.path('06_report/report.html');sealed=automatic_overview_digest(page)
    run_export(root,'v1');run_export(root,'v2',all_retained=True);assert automatic_overview_digest(page)==sealed
    return page


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);home=parser.parse_args().output.resolve();home.mkdir(parents=True,exist_ok=False)
    print(lgz_example(home/'lgz'));print(refined_example(home/'project'))
