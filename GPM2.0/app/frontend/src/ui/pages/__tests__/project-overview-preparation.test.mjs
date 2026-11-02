import test from "node:test";
import assert from "node:assert/strict";
import {createStore} from "../../../state/store.js";
import {prepareProjectOverviewSources as prepareReal,consumePreparedOverviewSources} from "../project-overview-preparation.js";
import {beginPreviewContentOperation,finishPreviewContentOperation} from "../../../services/preview-content-events.js";
import {__test as exportPage,renderProjectExportPage} from "../project-export-page.js";
import {zh,en} from "../../i18n/messages/importer.js";
let seq=0;
const cacheMetadata=async()=>({available:true,trackingVersion:3,identity:"fixture-db",revision:1,memoryValid:true});
const prepareProjectOverviewSources=(store,args,deps={},options={})=>prepareReal(store,args,{getProjectPreviewCache:cacheMetadata,...deps},options);
const tick=()=>Promise.resolve();
const sources=(id=1)=>({projectId:id,referenceGenomeId:1,chromosomes:[{chrName:"Chr1",chrOrder:1,chrLength:1000,ctgCount:2,placedBp:1400}],
 ctgs:[{assemblyCtgId:11,datasetId:2,derivedTargetDatasetId:1,name:"derived",originId:"original",assignedChrName:"Chr1",anchorStart:-10,totalLength:400,orient:"-",sourceFragment:{sourceSeqId:8,sourceStart:20,sourceEnd:419,groupKey:"manual-fragment:test",sourceLength:800}},
 {assemblyCtgId:12,datasetId:1,name:"ordinary",assignedChrName:"Chr1",anchorStart:500,totalLength:1000}],primaryCtgIds:[11,12],phasedChrTracksByChr:{}});
function fixture(){const args={workspaceRoot:`/overview-preparation-${++seq}`,projectId:1};return {args,store:createStore({locale:"en",activeRoute:"importer",session:{workspacePath:args.workspaceRoot,projectId:1},
 initializer:{datasets:[{datasetId:1,name:"primary"},{datasetId:2,name:"support"}],existingProjects:[{projectId:1,projectName:"new",primaryDatasetId:1,supportDatasetIds:[2]}]},
 assembly:{finalPathByChr:{}}})};}
test("import prewarm leaves the old project/store untouched and is consumed exactly once",async()=>{
 const f=fixture();f.store.setState({session:{workspacePath:"/old-project",projectId:99},assembly:{finalPathByChr:{Old:{segments:[{type:"gap",length:7}]}}}});const before=f.store.getState();
 let time=10;
 const result=await prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:async()=>sources(),now:()=>time+=10});
 assert.equal(result.ready,true);assert.equal(result.elapsedMs,10);assert.equal(result.sourceCount,2);assert.equal(f.store.getState(),before);
 const prepared=await consumePreparedOverviewSources(f.store,f.args);assert.equal(prepared.primaryCtgIds[0],11);assert.equal(prepared.ctgs[0].sourceFragment.sourceStart,20);
 assert.equal(await consumePreparedOverviewSources(f.store,f.args),null);
});
test("normal first Overview load reuses prepared authoritative sources and still reads fresh saved view/LGZ",async()=>{
 const f=fixture();await prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:async()=>sources()});
 f.store.setState({activeRoute:"projectExport"});let sourceCalls=0,viewCalls=0,lgzCalls=0;
 const deps={getProjectOverviewSources:async()=>{sourceCalls++;return sources();},getProjectAssemblyViewState:async()=>{viewCalls++;return {finalPathByChr:{}};},
 getGrtProjectView:async()=>{lgzCalls++;return {};},normalizeGrtProjectView:()=>({baselineFinalPathByChr:{},sourceCards:[],verification:{},recipe:{}})};
 assert.equal(await exportPage.loadProjectExportData(null,f.store,deps),true);assert.equal(sourceCalls,0);assert.equal(viewCalls,1);assert.equal(lgzCalls,1);
 assert.deepEqual(f.store.getState().projectExport.primaryCtgsByChr.Chr1.map(c=>c.assemblyCtgId),[11,12],"derived primary member must not be lost by datasetId guessing");
 assert.equal(await exportPage.loadProjectExportData(null,f.store,deps),true);assert.equal(sourceCalls,1,"the prewarm must not become an unbounded stale source cache");
});
for(const scope of ["workspace","project"])test(`prepared data cannot cross ${scope} scope`,async()=>{
 const f=fixture();await prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:async()=>sources()});
 const wrong={...f.args,...(scope==="workspace"?{workspaceRoot:"/different"}:{projectId:2})};assert.equal(await consumePreparedOverviewSources(f.store,wrong),null);assert.ok(await consumePreparedOverviewSources(f.store,f.args));
});
test("editing after preparation discards the prepared entry",async()=>{
 const f=fixture();await prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:async()=>sources()});
 const operation=beginPreviewContentOperation("run_main_view_editor_action",f.args);finishPreviewContentOperation(operation,"run_main_view_editor_action",{},true);
 assert.equal(await consumePreparedOverviewSources(f.store,f.args),null);
});
test("editing while a preparation request is in flight does not publish an older snapshot",async()=>{
 const f=fixture();let settle;const pending=prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:()=>new Promise(r=>{settle=r;})});
 await tick();beginPreviewContentOperation("undo_main_view_history",f.args);settle(sources());assert.equal((await pending).ready,false);assert.equal(await consumePreparedOverviewSources(f.store,f.args),null);
});
test("cancellation and a newer import run cannot publish a late result",async()=>{
 const f=fixture();let keep=true,settle;
 const pending=prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:()=>new Promise(r=>{settle=r;})},{shouldContinue:()=>keep});await tick();keep=false;settle(sources());
 assert.equal((await pending).ready,false);assert.equal(await consumePreparedOverviewSources(f.store,f.args),null);
 let oldSettle;const old=prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:()=>new Promise(r=>{oldSettle=r;})});await tick();
 await prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:async()=>({...sources(),marker:"new-run"})});oldSettle({...sources(),marker:"old-run"});
 assert.equal((await old).ready,false);assert.equal((await consumePreparedOverviewSources(f.store,f.args)).marker,"new-run");
});
test("failed or malformed optional preparation is not an import failure and never publishes empty stats",async()=>{
 for(const load of [async()=>{throw Error("offline");},async()=>({items:[]}),async()=>sources(99)]){
  const f=fixture();const result=await prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:load});assert.equal(result.ready,false);assert.ok(result.error);assert.equal(await consumePreparedOverviewSources(f.store,f.args),null);
 }
 const f=fixture();let calls=0;const result=await prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:async()=>{calls++;return sources();}},{shouldContinue:()=>false});assert.equal(result.ready,false);assert.equal(calls,0);
});
test("multi-project prewarm is bounded to three entries",async()=>{
 const f=fixture();for(let projectId=1;projectId<=4;projectId++)await prepareProjectOverviewSources(f.store,{...f.args,projectId},{getProjectOverviewSources:async()=>sources(projectId)});
 assert.equal(await consumePreparedOverviewSources(f.store,f.args),null);for(const projectId of [2,3,4])assert.equal((await consumePreparedOverviewSources(f.store,{...f.args,projectId})).projectId,projectId);
});
test("both languages expose separate preparation phases and elapsed time without weakening success wording",()=>{
 for(const locale of [zh,en]){
  assert.match(locale.runtime.preparePreviewDone,/\{seconds\}/);assert.match(locale.runtime.prepareOverviewDone,/\{seconds\}/);
  assert.ok(locale.runtime.prepareOverviewStage);assert.ok(locale.runtime.prepareOverviewFailed);
 }
});


for(const change of ["revision","identity","unavailable"])test(`external persisted ${change} change invalidates prewarm even without session edits`,async()=>{
 const f=fixture();let metadata={available:true,trackingVersion:3,identity:"db-a",revision:1};
 await prepareProjectOverviewSources(f.store,f.args,{getProjectPreviewCache:async()=>({...metadata}),getProjectOverviewSources:async()=>sources()});
 metadata={...metadata,...(change==="revision"?{revision:2}:change==="identity"?{identity:"db-b"}:{available:false})};
 assert.equal(await consumePreparedOverviewSources(f.store,f.args),null);
});
test("a persisted edit between the two preparation fences cannot publish mixed source data",async()=>{
 const f=fixture();let revision=1;
 const result=await prepareProjectOverviewSources(f.store,f.args,{getProjectPreviewCache:async()=>({available:true,trackingVersion:3,identity:"db",revision}),
  getProjectOverviewSources:async()=>{revision++;return sources();}});
 assert.equal(result.ready,false);assert.equal(await consumePreparedOverviewSources(f.store,f.args),null);
});
test("an unsupported validity backend does not authorize a prepared statistics hit",async()=>{
 const f=fixture();let sourceCalls=0;
 const result=await prepareProjectOverviewSources(f.store,f.args,{getProjectPreviewCache:async()=>({available:false}),getProjectOverviewSources:async()=>{sourceCalls++;return sources();}});
 assert.equal(result.ready,false);assert.equal(sourceCalls,0);assert.equal(await consumePreparedOverviewSources(f.store,f.args),null);
});


test("a persisted edit during fresh view/LGZ loading discards prepared sources and retries the normal source reader",async()=>{
 const f=fixture();let revision=1,sourceCalls=0,viewCalls=0;
 await prepareProjectOverviewSources(f.store,f.args,{getProjectPreviewCache:async()=>({available:true,trackingVersion:3,identity:"db",revision}),getProjectOverviewSources:async()=>sources()});
 f.store.setState({activeRoute:"projectExport"});
 const deps={getProjectOverviewSources:async()=>{sourceCalls++;const next=sources();next.ctgs[0].totalLength=500;return next;},
  getProjectAssemblyViewState:async()=>{viewCalls++;revision=2;return {finalPathByChr:{}};},getGrtProjectView:async()=>({}),
  normalizeGrtProjectView:()=>({baselineFinalPathByChr:{},sourceCards:[],verification:{},recipe:{}})};
 assert.equal(await exportPage.loadProjectExportData(null,f.store,deps),true);assert.equal(sourceCalls,1);assert.equal(viewCalls,2);
 assert.equal(f.store.getState().projectExport.ctgsByChr.Chr1[0].totalLength,500);
});


test("prewarming preserves complete Overview HTML with current unsaved paths and hidden-member state",async()=>{
 const f=fixture();await prepareProjectOverviewSources(f.store,f.args,{getProjectOverviewSources:async()=>sources()});
 const state=f.store.getState();f.store.setState({activeRoute:"projectExport",assembly:{...state.assembly,
  finalPathByChr:{Chr1:{mode:"segments",segments:[{type:"ctg",assemblyCtgId:12,ctgName:"ordinary",datasetName:"primary",overallLen:1000,start:101,end:800,orient:"-"}]}},
  hiddenPrimaryCtgIdsByChr:{Chr1:[12]}}});
 const cold=createStore(f.store.getState());let calls=0;
 const deps={getProjectOverviewSources:async()=>{calls++;return sources();},getProjectAssemblyViewState:async()=>({finalPathByChr:{},hiddenPrimaryCtgIdsByChr:{}}),
  getGrtProjectView:async()=>({}),normalizeGrtProjectView:()=>({baselineFinalPathByChr:{},sourceCards:[],verification:{},recipe:{}})};
 assert.equal(await exportPage.loadProjectExportData(null,f.store,deps),true);assert.equal(calls,0);
 assert.equal(await exportPage.loadProjectExportData(null,cold,deps),true);assert.equal(calls,1);
 assert.equal(renderProjectExportPage(f.store.getState()),renderProjectExportPage(cold.getState()));
});
