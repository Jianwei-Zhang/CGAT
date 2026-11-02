import test from "node:test";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { beginAssemblyViewRequest } from "../assembly-view-request.js";
import { afterAssemblyPaint, hydrateAssemblyCtgDetail, retryAssemblyCtgDetail, restoreAssemblyLocalEvidence, resumeAssemblyReadyStages } from "../assembly-ready-stages.js";
import { renderAssemblyDetailStatus, renderAssemblyLocalRestoreStatus, bindAssemblyDetailRetry } from "../assembly-detail-status.js";
import { getMessages } from "../../../i18n/index.js";

function deferred() { let resolve, reject; const promise = new Promise((a,b) => { resolve=a;reject=b; });return { promise, resolve, reject }; }
function fixture() {
  const summary = { mode: "composition", members: [] };
  const store = createStore({ locale: "en", activeRoute: "assembly", session: { workspacePath: "D:/fixture", projectId: 1 },
    assembly: { loading: false, selectedChrName: "chr1", selectedCtgId: 1, selectedMemberSeqId: null,
      ctgDetailLoading: true, ctgDetail: null, ctgDetailError: "", subview: { summary },
      subviewRestoring: true, subviewRestoringSummary: summary, subviewRestoreError: "" } });
  const requests = [], patches = [];
  const deps = {
    loadSideDataForCtg: (_root,_project,id) => { const pending = deferred();requests.push({ id, ...pending });return pending.promise; },
    patchSelection: () => patches.push("detail"), patchSubview: () => patches.push("local"),
    rerender: () => assert.fail("details/evidence must not rebuild Main DOM"),
    mapAssemblyError: ({error}) => ({ userMessage: error.message }),
  };
  return { store, deps, requests, patches, assembly(patch) { store.setState({ assembly: { ...store.getState().assembly, ...patch } }); } };
}

test("detail hydration preserves concurrent user edits and member choice without changing Main readiness", async () => {
  const f=fixture(), paint=deferred();f.deps.afterMainPaint=()=>paint.promise;
  const loading=hydrateAssemblyCtgDetail({},f.store,f.deps,{afterPaint:true});assert.equal(f.requests.length,0);
  const paths={chr1:{segments:[{type:"gap",gapSizeBp:123}]}};f.assembly({finalPathByChr:paths,selectedMemberSeqId:12});
  paint.resolve();await new Promise(setImmediate);f.requests[0].resolve({detail:{members:[{assemblySeqId:11},{assemblySeqId:12}]}});await loading;
  assert.equal(f.store.getState().assembly.finalPathByChr,paths);assert.equal(f.store.getState().assembly.selectedMemberSeqId,12);
  assert.equal(f.store.getState().assembly.loading,false);assert.equal(f.store.getState().assembly.ctgDetailLoading,false);
  assert.deepEqual(f.patches,["detail"]);
});

for(const type of ["workspace","project","chromosome","route","generation","selected-contig"]) for(const failure of [false,true]) {
  test(`stale ${failure?"detail error":"detail success"} cannot publish after ${type} change`,async()=>{
    const f=fixture();const pending=hydrateAssemblyCtgDetail({},f.store,f.deps);
    if(type==="workspace")f.store.setState({session:{workspacePath:"D:/other",projectId:1}});
    if(type==="project")f.store.setState({session:{workspacePath:"D:/fixture",projectId:2}});
    if(type==="chromosome")f.assembly({selectedChrName:"chr2"});
    if(type==="route")f.store.setState({activeRoute:"importer"});
    if(type==="generation")beginAssemblyViewRequest(f.store);
    if(type==="selected-contig")f.assembly({selectedCtgId:2});
    if(failure)f.requests[0].reject(Error("old-error"));else f.requests[0].resolve({detail:{name:"old",members:[]}});
    await pending;assert.equal(f.store.getState().assembly.ctgDetail,null);assert.equal(f.store.getState().assembly.ctgDetailError,"");assert.deepEqual(f.patches,[]);
  });
}

test("same-contig ABA and retry supersede pending details using independent generations",async()=>{
  const f=fixture();const old=hydrateAssemblyCtgDetail({},f.store,f.deps);
  f.assembly({selectedCtgId:2});const middle=hydrateAssemblyCtgDetail({},f.store,f.deps);
  f.assembly({selectedCtgId:1});const latest=hydrateAssemblyCtgDetail({},f.store,f.deps);
  f.requests[2].resolve({detail:{version:"latest",members:[{assemblySeqId:10}]}});await latest;
  f.requests[0].resolve({detail:{version:"old",members:[]}});f.requests[1].reject(Error("old-error"));await Promise.all([old,middle]);
  assert.equal(f.store.getState().assembly.ctgDetail.version,"latest");assert.deepEqual(f.patches,["detail"]);
  const retry=retryAssemblyCtgDetail({},f.store,f.deps);await new Promise(setImmediate);
  assert.equal(f.store.getState().assembly.ctgDetail,null);assert.equal(f.store.getState().assembly.ctgDetailLoading,true);
  f.requests.at(-1).resolve({detail:{version:"retried",members:[]}});await retry;
  assert.equal(f.store.getState().assembly.ctgDetail.version,"retried");
});

test("detail error is independent, escaped, retryable, and never shows the previous contig",async()=>{
  const f=fixture();const pending=hydrateAssemblyCtgDetail({},f.store,f.deps);f.requests[0].reject(Error("<failure>"));await pending;
  const assembly=f.store.getState().assembly;assert.equal(assembly.loading,false);assert.equal(assembly.error,undefined);
  const output=renderAssemblyDetailStatus(f.store.getState());assert.match(output,/role="alert"/);assert.match(output,/&lt;failure&gt;/);assert.match(output,/data-assembly-detail-retry/);
  f.store.setState({activeRoute:"importer"});assert.equal(retryAssemblyCtgDetail({},f.store,f.deps),undefined);
});

test("local restore has a separate stage, suppresses internal renders and patches only Local on completion",async()=>{
  const f=fixture(), paint=deferred(), evidence=deferred();let calls=0;
  f.deps.afterMainPaint=()=>paint.promise;f.deps.refreshSubviewPairwiseEvidence=async(_h,_s,options)=>{
    calls++;assert.deepEqual(options,{rerenderLoading:false,rerenderLoaded:false});await evidence.promise;
  };
  const task=restoreAssemblyLocalEvidence({},f.store,f.deps,{afterPaint:true});assert.equal(calls,0);
  const labels=getMessages(f.store.getState(),"assembly");
  assert.match(renderAssemblyLocalRestoreStatus(f.store.getState().assembly,labels),/aria-busy="true"/);
  paint.resolve();await new Promise(setImmediate);assert.equal(calls,1);assert.deepEqual(f.patches,[]);
  evidence.resolve();await task;assert.equal(f.store.getState().assembly.subviewRestoring,false);assert.deepEqual(f.patches,["local"]);
});

test("local failures never fail Main and a new Local selection does not display the old loading/error placeholder",async()=>{
  const f=fixture(), pending=deferred();f.deps.refreshSubviewPairwiseEvidence=()=>pending.promise;
  const task=restoreAssemblyLocalEvidence({},f.store,f.deps);pending.reject(Error("evidence-failed"));await task;
  assert.equal(f.store.getState().assembly.loading,false);assert.equal(f.store.getState().assembly.subviewRestoreError,"evidence-failed");
  const labels=getMessages(f.store.getState(),"assembly");assert.match(renderAssemblyLocalRestoreStatus(f.store.getState().assembly,labels),/data-assembly-subview-retry/);
  f.assembly({subview:{summary:{mode:"2-contig"}}});assert.equal(renderAssemblyLocalRestoreStatus(f.store.getState().assembly,labels),"");
});

test("stale Local restore cannot clear a new view's loading state",async()=>{
  const f=fixture(), pending=deferred();f.deps.refreshSubviewPairwiseEvidence=()=>pending.promise;
  const task=restoreAssemblyLocalEvidence({},f.store,f.deps);beginAssemblyViewRequest(f.store);
  pending.resolve();await task;assert.equal(f.store.getState().assembly.subviewRestoring,true);assert.deepEqual(f.patches,[]);
});

test("paint opportunity cancels its bounded fallback and does not require browser globals for headless tests",async()=>{
  await afterAssemblyPaint({});let callback,cancelled=0;
  const task=afterAssemblyPaint({ownerDocument:{defaultView:{requestAnimationFrame(fn){callback=fn;return 42;},cancelAnimationFrame(id){assert.equal(id,42);cancelled++;}}}});
  callback();await task;assert.equal(cancelled,1);
});

test("retry event binding is delegated once and follows the latest callbacks",()=>{
  const listeners=[];const host={addEventListener:(name,fn)=>listeners.push(fn),contains:()=>true};const calls=[];
  bindAssemblyDetailRetry(host,()=>calls.push("old"),()=>{});
  bindAssemblyDetailRetry(host,()=>calls.push("detail"),()=>calls.push("local"));assert.equal(listeners.length,1);
  listeners[0]({target:{closest:selector=>selector==="[data-assembly-detail-retry]"?{}:null}});
  listeners[0]({target:{closest:selector=>selector==="[data-assembly-subview-retry]"?{}:null}});
  assert.deepEqual(calls,["detail","local"]);
});

for (const change of ["workspace", "project", "route", "generation"]) for (const failed of [false, true]) {
  test(`pairwise evidence ignores stale ${failed ? "failure" : "success"} after ${change} change`, async () => {
    const { createSubviewPairwiseController } = await import("../subview-pairwise-controller.js");
    const f = fixture(), request = deferred();
    f.assembly({ subview: { summary: { mode: "2-contig", top: { role: "support", contigId: 2 }, bottom: { role: "primary", contigId: 1 } } } });
    const controller = createSubviewPairwiseController({
      session: { subviewPairwiseEvidenceRequestSeq: 0 },
      rerenderSubviewPanel: () => assert.fail("silent restoration must not render"),
      scheduleDeferredSubviewPanelRerender: () => assert.fail("stale restoration must not render"),
      getJunctionInspection: () => request.promise,
    });
    const task = controller.refreshSubviewPairwiseEvidence({}, f.store, { rerenderLoading: false, rerenderLoaded: false });
    const evidence = f.store.getState().assembly.subview.pairwiseEvidence;
    assert.equal(evidence.status, "loading");
    if (change === "workspace") f.store.setState({ session: { workspacePath: "D:/other", projectId: 1 } });
    if (change === "project") f.store.setState({ session: { workspacePath: "D:/fixture", projectId: 2 } });
    if (change === "route") f.store.setState({ activeRoute: "project" });
    if (change === "generation") beginAssemblyViewRequest(f.store);
    if (failed) request.reject(Error("stale evidence failure")); else request.resolve({ hits: [{ hitKey: "stale" }] });
    await task;
    assert.equal(f.store.getState().assembly.subview.pairwiseEvidence, evidence);
  });
}

test("route return resumes discarded details without duplicating a still-active request", async () => {
  const f = fixture();
  f.assembly({ subviewRestoring: false });
  const old = hydrateAssemblyCtgDetail({}, f.store, f.deps);
  await resumeAssemblyReadyStages({}, f.store, f.deps);
  assert.equal(f.requests.length, 1);
  f.store.setState({ activeRoute: "projectExport" });
  f.requests[0].resolve({ detail: { version: "off-route", members: [] } });
  await old;
  assert.equal(f.store.getState().assembly.ctgDetail, null);
  f.store.setState({ activeRoute: "assembly" });
  const returning = resumeAssemblyReadyStages({}, f.store, f.deps);
  await new Promise(setImmediate);
  assert.equal(f.requests.length, 2);
  f.requests[1].resolve({ detail: { version: "returned", members: [] } });
  await returning;
  assert.equal(f.store.getState().assembly.ctgDetail.version, "returned");
  assert.equal(f.store.getState().assembly.ctgDetailLoading, false);
});

test("route return restarts abandoned Local evidence rather than keeping a cached loading request forever", async () => {
  const { createSubviewPairwiseController } = await import("../subview-pairwise-controller.js");
  const f = fixture(), requests = [];
  const summary = { mode: "2-contig", top: { role: "support", contigId: 2 }, bottom: { role: "primary", contigId: 1 } };
  f.assembly({ ctgDetailLoading: false, subview: { summary }, subviewRestoringSummary: summary });
  const controller = createSubviewPairwiseController({
    session: { subviewPairwiseEvidenceRequestSeq: 0 },
    rerenderSubviewPanel: () => assert.fail("silent stage"),
    scheduleDeferredSubviewPanelRerender: () => assert.fail("silent stage"),
    getJunctionInspection: () => { const request = deferred(); requests.push(request); return request.promise; },
  });
  f.deps.refreshSubviewPairwiseEvidence = controller.refreshSubviewPairwiseEvidence;
  const old = restoreAssemblyLocalEvidence({}, f.store, f.deps);
  await resumeAssemblyReadyStages({}, f.store, f.deps);
  assert.equal(requests.length, 1);
  f.store.setState({ activeRoute: "projectExport" });
  requests[0].resolve({ hits: [{ hitKey: "discarded" }] }); await old;
  assert.equal(f.store.getState().assembly.subviewRestoring, true);
  f.store.setState({ activeRoute: "assembly" });
  const returning = resumeAssemblyReadyStages({}, f.store, f.deps);
  await new Promise(setImmediate);
  assert.equal(requests.length, 2);
  requests[1].resolve({ hits: [{ hitKey: "current" }] }); await returning;
  assert.equal(f.store.getState().assembly.subviewRestoring, false);
  assert.equal(f.store.getState().assembly.subview.pairwiseEvidence.hits[0].hitKey, "current");
});

test("independent detail notice stays out of flow and fully hides when ready", () => {
  const css = readFileSync(new URL("../../../../styles/assembly.css", import.meta.url), "utf8");
  assert.match(css, /\.assembly-detail-status\s*\{[^}]*position:\s*fixed/s);
  assert.match(css, /\.assembly-detail-status\[hidden\]\s*\{\s*display:\s*none/s);
  const f = fixture();
  assert.match(renderAssemblyDetailStatus(f.store.getState()), /class="assembly-detail-status"/);
  f.assembly({ ctgDetailLoading: false });
  assert.match(renderAssemblyDetailStatus(f.store.getState()), / hidden>/);
});

test("controller-reported Local failure stays independent and exposes a working retry stage", async () => {
  const { createSubviewPairwiseController } = await import("../subview-pairwise-controller.js");
  const f = fixture();
  const summary = { mode: "2-contig", top: { role: "support", contigId: 2 }, bottom: { role: "primary", contigId: 1 } };
  f.assembly({ ctgDetailLoading: false, subview: { summary }, subviewRestoringSummary: summary });
  let requests = 0;
  const controller = createSubviewPairwiseController({
    session: { subviewPairwiseEvidenceRequestSeq: 0 },
    rerenderSubviewPanel: () => assert.fail("silent stage"),
    scheduleDeferredSubviewPanelRerender: () => assert.fail("silent stage"),
    getJunctionInspection: async () => {
      if (++requests === 1) throw Error("controlled Local failure");
      return { hits: [{ hitKey: "retried-evidence" }] };
    },
  });
  f.deps.refreshSubviewPairwiseEvidence = controller.refreshSubviewPairwiseEvidence;
  await restoreAssemblyLocalEvidence({}, f.store, f.deps);
  assert.equal(f.store.getState().assembly.loading, false);
  assert.ok(f.store.getState().assembly.subviewRestoreError);
  const output = renderAssemblyLocalRestoreStatus(f.store.getState().assembly, getMessages(f.store.getState(), "assembly"));
  assert.match(output, /data-assembly-subview-retry/);
  assert.doesNotMatch(output, /\[object Object\]/);
  f.assembly({ subviewRestoring: true, subviewRestoreError: "" });
  await restoreAssemblyLocalEvidence({}, f.store, f.deps);
  assert.equal(requests, 2);
  assert.equal(f.store.getState().assembly.subviewRestoreError, "");
  assert.equal(f.store.getState().assembly.subview.pairwiseEvidence.hits[0].hitKey, "retried-evidence");
});
