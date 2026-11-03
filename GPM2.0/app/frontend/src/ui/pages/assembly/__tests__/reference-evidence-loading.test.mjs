import test from "node:test";
import assert from "node:assert/strict";
import {createStore} from "../../../../state/store.js";
import {decodeReferenceTracks} from "../../../../services/workflow/reference-transport.js";
import {readReferenceHits} from "../../../../services/workflow/reference-evidence.js";
import {ensureSubviewReferenceEvidence,missingSubviewReferenceEvidence} from "../reference-evidence-loading.js";
import {createSubviewPairwiseController} from "../subview-pairwise-controller.js";
import {renderAssemblyLocalRestoreStatus} from "../assembly-detail-status.js";
import {getAssemblyI18n} from "../i18n.js";
const metadata={referenceChrId:1,segmentOrder:1,segmentStartBp:1,segmentEndBp:100,totalLength:100,assemblyCtgId:9001,name:"ref"};
const full=()=>({items:[{...metadata,hits:[{hitId:1,mapq:0,identityPct:93.27,refStart:1,refEnd:10}]}]});
function fixture(){
 const members=decodeReferenceTracks({encoding:"reference-geometry-v1",items:[metadata]},{deferHits:true}).items;
 const summary={mode:"2-contig",top:{role:"ref",contigId:9001},bottom:{role:"ref",contigId:9002}};
 const store=createStore({locale:"zh",activeRoute:"assembly",session:{workspacePath:"readonly",projectId:1},assembly:{selectedChrName:"chr1",refTrackMembers:members,subview:{summary}}});
 return {store,summary,members};
}
const deps=(load,render=()=>{})=>({load,render,mapError:error=>error.message});
test("Main and opposite-CTG Ref modes never request raw evidence",async()=>{
 for(const mode of [null,{mode:"2-contig",top:{role:"ref"},bottom:{role:"primary"}},{mode:"track-pair",topTrack:{role:"ref"},bottomTrack:{role:"primary"}},{mode:"composition"}]){
  const f=fixture();f.store.setState({assembly:{...f.store.getState().assembly,subview:{summary:mode}}});
  assert.equal(await ensureSubviewReferenceEvidence(null,f.store,deps(()=>{throw Error("must not fetch");})),true);
 }
});
test("two-Ref loading has explicit pending UI, deduplicates, preserves runtime IDs and old snapshots",async()=>{
 const f=fixture();const snapshot=structuredClone(f.store.getState());let settle,calls=0;
 const d=deps(args=>{calls++;assert.equal(args.geometryOnly,false);assert.equal(args.deferHits,true);return new Promise(r=>{settle=r;});});
 const first=ensureSubviewReferenceEvidence(null,f.store,d),second=ensureSubviewReferenceEvidence(null,f.store,d);
 assert.equal(calls,1);assert.deepEqual(f.members,snapshot.assembly.refTrackMembers);
 const html=renderAssemblyLocalRestoreStatus(f.store.getState().assembly,getAssemblyI18n(f.store.getState()));
 assert.match(html,/aria-busy="true"/);assert.match(html,/参考序列/);
 settle(full());assert.equal(await first,true);assert.equal(await second,true);
 assert.equal(missingSubviewReferenceEvidence(f.store.getState().assembly).length,0);
 assert.equal(f.store.getState().assembly.refTrackMembers[0].assemblyCtgId,9001);
 assert.equal(readReferenceHits(f.store.getState().assembly.refTrackMembers[0])[0].mapq,0);
 assert.deepEqual(f.members,snapshot.assembly.refTrackMembers);
});
for(const change of ["route","project","chromosome","summary","members"])test(`stale raw response does not publish after ${change} changes`,async()=>{
 const f=fixture();let settle;
 const pending=ensureSubviewReferenceEvidence(null,f.store,deps(()=>new Promise(r=>{settle=r;})));
 const state=f.store.getState();
 if(change==="route")f.store.setState({activeRoute:"projectPreview"});
 if(change==="project")f.store.setState({session:{...state.session,projectId:2}});
 if(change==="chromosome")f.store.setState({assembly:{...state.assembly,selectedChrName:"chr2"}});
 if(change==="summary")f.store.setState({assembly:{...state.assembly,subview:{summary:{...f.summary}}}});
 if(change==="members")f.store.setState({assembly:{...state.assembly,refTrackMembers:[...state.assembly.refTrackMembers]}});
 const before=f.store.getState();settle(full());assert.equal(await pending,false);assert.equal(f.store.getState(),before);
});
test("failure shows independent retry and cannot masquerade as a valid empty graph",async()=>{
 const f=fixture();assert.equal(await ensureSubviewReferenceEvidence(null,f.store,deps(async()=>{throw Error("controlled failure");})),false);
 const html=renderAssemblyLocalRestoreStatus(f.store.getState().assembly,getAssemblyI18n(f.store.getState()));
 assert.match(html,/controlled failure/);assert.match(html,/data-assembly-subview-retry/);
 assert.throws(()=>readReferenceHits(f.store.getState().assembly.refTrackMembers[0]),/not loaded/);
 assert.equal(await ensureSubviewReferenceEvidence(null,f.store,deps(async()=>full())),true);
});
test("geometry mismatch or missing evidence fails closed",async()=>{
 for(const response of [{items:[]},{items:[{...metadata,segmentEndBp:101,hits:[]}]},{items:[metadata]}, {items:[{...metadata,referenceEvidence:{encoding:"bad"}}]},
   {items:[full().items[0],{...metadata,segmentOrder:2,hits:[]}]}, {items:[full().items[0],full().items[0]]}]){
  const f=fixture();assert.equal(await ensureSubviewReferenceEvidence(null,f.store,deps(async()=>response)),false);
  assert.equal(missingSubviewReferenceEvidence(f.store.getState().assembly).length,1);
 }
});
test("actual pairwise controller hydrates raw Ref evidence without starting an unrelated pairwise request",async()=>{
 const f=fixture();let loads=0;
 const controller=createSubviewPairwiseController({session:{subviewPairwiseEvidenceRequestSeq:0},rerenderSubviewPanel(){},scheduleDeferredSubviewPanelRerender(){},
  listReferenceTrackMembers:async()=>{loads++;return full();},getTrackPairwiseEvidence:()=>{throw Error("wrong API");},getJunctionInspection:()=>{throw Error("wrong API");}});
 await controller.refreshSubviewPairwiseEvidence(null,f.store);assert.equal(loads,1);assert.equal(missingSubviewReferenceEvidence(f.store.getState().assembly).length,0);
});


test("route A -> B -> A cannot revive an obsolete raw evidence request",async()=>{
 const f=fixture();let settle;const pending=ensureSubviewReferenceEvidence(null,f.store,deps(()=>new Promise(r=>{settle=r;})));
 f.store.setState({activeRoute:"projectPreview"});f.store.setState({activeRoute:"assembly"});const before=f.store.getState();
 settle(full());assert.equal(await pending,false);assert.equal(f.store.getState(),before);
 assert.equal(missingSubviewReferenceEvidence(before.assembly).length,1);
 assert.equal(await ensureSubviewReferenceEvidence(null,f.store,deps(async()=>full())),true);
});


test("synchronous store subscribers join a fully initialized request rather than a missing promise",async()=>{
 const f=fixture();let joined,settle,calls=0;
 const options=deps(()=>{calls++;return new Promise(resolve=>{settle=resolve;});});
 let entered=false;
 const unsubscribe=f.store.subscribe(()=>{if(!entered){entered=true;joined=ensureSubviewReferenceEvidence(null,f.store,options);}});
 const first=ensureSubviewReferenceEvidence(null,f.store,options);
 assert.equal(calls,1);unsubscribe();settle(full());assert.equal(await first,true);assert.equal(await joined,true);
});
