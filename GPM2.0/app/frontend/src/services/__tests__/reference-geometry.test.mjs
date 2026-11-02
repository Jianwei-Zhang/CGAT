import test from "node:test";
import assert from "node:assert/strict";
import {createTauriAssemblyOperations} from "../workflow/tauri/assembly.js";
import {decodeReferenceTracks} from "../workflow/reference-transport.js";
import {referenceHitsUnloaded,hasDeferredReferenceHits,readReferenceHits,iterateReferenceHits} from "../workflow/reference-evidence.js";
const geometry={encoding:"reference-geometry-v1",items:[{referenceChrId:1,segmentOrder:1,segmentStartBp:1,segmentEndBp:100,name:"ref",totalLength:100}]};
test("geometry response retains explicit unread evidence, not an empty-hit result",()=>{
 const member=decodeReferenceTracks(geometry,{deferHits:true}).items[0];
 assert.equal(referenceHitsUnloaded(member),true);assert.equal(hasDeferredReferenceHits(member),true);
 assert.equal(Object.hasOwn(member,"hits"),false);assert.equal(Object.hasOwn(member.referenceEvidence,"hitRows"),false);
 assert.throws(()=>readReferenceHits(member),/not loaded/);assert.throws(()=>[...iterateReferenceHits(member)],/not loaded/);
 assert.deepEqual(structuredClone(member),member);
});
test("new first-paint request negotiates geometry while old calls still request complete evidence",async()=>{
 const calls=[];const ops=createTauriAssemblyOperations({invokeCommand:async(name,args)=>{calls.push({name,args});return geometry;}});
 await ops.listReferenceTrackMembers({workspaceRoot:"fixture",projectId:1,chrName:"chr1",deferHits:true,geometryOnly:true});
 await ops.listReferenceTrackMembers({workspaceRoot:"fixture",projectId:1,chrName:"chr1",deferHits:true});
 await ops.listReferenceTrackMembers({workspaceRoot:"fixture",projectId:1,chrName:"chr1"});
 assert.deepEqual(calls.map(c=>c.args.encoding),["reference-geometry-v1","reference-hits-v2",undefined]);
});
test("only explicit unsupported-geometry negotiation falls back; real query failures propagate",async()=>{
 let calls=0;const ops=createTauriAssemblyOperations({invokeCommand:async(_name,args)=>{
  calls++;if(calls===1)throw Error("unsupported reference evidence encoding: reference-geometry-v1");
  assert.equal(args.encoding,"reference-hits-v2");return {items:[{hits:[{hitId:7}]}]};
 }});
 const result=await ops.listReferenceTrackMembers({geometryOnly:true,deferHits:true});assert.equal(calls,2);assert.equal(result.items[0].hits[0].hitId,7);
 calls=0;const bad=createTauriAssemblyOperations({invokeCommand:async()=>{calls++;throw Error("database corrupted");}});
 await assert.rejects(()=>bad.listReferenceTrackMembers({geometryOnly:true}),/database corrupted/);assert.equal(calls,1);
});
