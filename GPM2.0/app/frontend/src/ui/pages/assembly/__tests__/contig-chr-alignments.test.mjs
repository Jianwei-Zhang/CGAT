import test from "node:test";
import assert from "node:assert/strict";
import {resolveContigChrAlignmentModel,chrAlignmentAction,renderChrAlignmentPreview,openContigChrAlignments} from "../contig-chr-alignments.js";
const source={assemblyCtgId:6,sourceSeqId:1,assignedChrName:"chrA",name:"tig.1",sourceStart:101,sourceEnd:1100,orient:"-"};
const candidate=(overrides={})=>({chrName:"chrB",orient:"+",refLength:10000,coveragePercent:80,identityPercent:99,presence:"missing",existingCtgId:null,existingHidden:false,hits:[{queryStart:101,queryEnd:900,refStart:1001,refEnd:1800,strand:"+"}],...overrides});
const report=(items=[candidate()])=>({source,items});
test("actions distinguish identity, visibility, containment and partial overlap",()=>{
  assert.equal(chrAlignmentAction(candidate()),"add");assert.equal(chrAlignmentAction(candidate({presence:"overlap"})),"add");
  assert.equal(chrAlignmentAction(candidate({presence:"existing"})),"locate");assert.equal(chrAlignmentAction(candidate({presence:"contained"})),"locate");
  assert.equal(chrAlignmentAction(candidate({presence:"hidden"})),"show");assert.equal(chrAlignmentAction(candidate({presence:"contained",existingHidden:true})),"show");
});
test("preview uses the selected target orientation and original fragment coordinates and escapes labels",()=>{
  const s=renderChrAlignmentPreview({...source,name:'<tig"&>'},candidate({orient:"-"}));
  assert.match(s,/&lt;tig&quot;&amp;&gt;/);assert.match(s,/1,100/);assert.match(s,/101/);assert.match(s,/chrB/);assert.doesNotMatch(s,/data-manual-cut|推荐|Final Path/);
});
// Event-level DOM harness only; not browser/native visual acceptance.
function harness(){
  const nodes=new Map();let dialog,restored=0;
  const node=(attrs={})=>({attrs,disabled:false,textContent:"",innerHTML:"",handlers:new Map(),
    setAttribute(k,v){attrs[k]=String(v);},getAttribute:k=>attrs[k]??null,
    addEventListener(t,f){this.handlers.set(t,f);},fire(t,extra={}){return this.handlers.get(t)?.({target:this,preventDefault(){},...extra});},focus(){},
    closest(s){return s==="[data-chr-action]"&&attrs["data-chr-action"]!==undefined?this:s==="[data-chr-index]"&&attrs["data-chr-index"]!==undefined?this:null;}});
  const doc={activeElement:{isConnected:true,focus(){restored++;}},body:{append(d){dialog=d;}},querySelector:()=>dialog&&!dialog.removed?dialog:null,
    createElement(){const d=node();return Object.assign(d,{querySelector(s){if(!nodes.has(s))nodes.set(s,node());return nodes.get(s);},querySelectorAll:()=>[],showModal(){this.open=true;},close(){this.open=false;},remove(){this.removed=true;}});}};
  return {host:{ownerDocument:doc},dialog:()=>dialog,el:n=>dialog.querySelector(`[data-chr-${n}]`),clickAction:i=>dialog.fire("click",{target:node({"data-chr-action":String(i)})}),clickRow:i=>dialog.fire("click",{target:node({"data-chr-index":String(i)})}),restored:()=>restored};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test("opening and selecting rows are local read-only previews",async()=>{
  const h=harness();let loads=0,writes=0;const done=openContigChrAlignments(h.host,{load:async()=>{loads++;return report([candidate(),candidate({chrName:"chrC"})]);},add:async()=>{writes++;}});
  await tick();assert.equal(loads,1);assert.match(h.el("table").innerHTML,/覆盖率/);assert.match(h.el("preview").innerHTML,/chrB/);
  h.clickRow(1);assert.match(h.el("preview").innerHTML,/chrC/);assert.equal(loads,1);assert.equal(writes,0);
  h.dialog().fire("cancel");await done;assert.equal(writes,0);assert.equal(h.restored(),1);
});
test("Add writes exact source preconditions once then refreshes to Exists/Locate without navigating",async()=>{
  const h=harness(),writes=[],locations=[];let added=false;
  const done=openContigChrAlignments(h.host,{load:async()=>report([candidate(added?{presence:"existing",existingCtgId:42}:{})]),
    add:async args=>{writes.push(args);added=true;return true;},locate:async i=>locations.push(i.existingCtgId)});
  await tick();h.clickAction(0);await tick();assert.equal(writes.length,1);
  assert.deepEqual(writes[0],{assemblyCtgId:6,sourceSeqId:1,sourceChrName:"chrA",sourceStart:101,sourceEnd:1100,orient:"-",targetChrName:"chrB",allowOverlap:false,revealContained:false});
  assert.match(h.el("table").innerHTML,/已存在/);assert.equal(locations.length,0);assert.equal(h.dialog().removed,undefined);
  h.clickAction(0);await tick();await done;assert.deepEqual(locations,[42]);assert.equal(writes.length,1);
});
test("partial overlap requires a second explicit confirmation and switching rows clears it",async()=>{
  const h=harness(),writes=[];const done=openContigChrAlignments(h.host,{load:async()=>report([candidate({presence:"overlap"}),candidate({chrName:"chrC"})]),add:async args=>{writes.push(args);}});
  await tick();h.clickAction(0);await tick();assert.equal(writes.length,0);assert.match(h.el("table").innerHTML,/确认添加/);
  h.clickRow(1);h.clickAction(0);await tick();assert.equal(writes.length,0);h.clickAction(0);await tick();assert.equal(writes.length,1);assert.equal(writes[0].allowOverlap,true);
  h.el("close").fire("click");await done;
});
test("hidden exact and hidden containing objects request reveal instead of new copies",async()=>{
  for(const presence of ["hidden","contained"]){
    const h=harness(),writes=[];const done=openContigChrAlignments(h.host,{load:async()=>report([candidate({presence,existingHidden:true,existingCtgId:42})]),add:async args=>{writes.push(args);return true;}});
    await tick();assert.match(h.el("table").innerHTML,/显示已有/);h.clickAction(0);await tick();assert.equal(writes.length,1);assert.equal(writes[0].revealContained,presence==="contained");h.el("close").fire("click");await done;
  }
});
test("stale context prevents both adds and navigation; errors retain the panel",async()=>{
  const h=harness();let current=true,writes=0;const done=openContigChrAlignments(h.host,{isCurrent:()=>current,load:async()=>report(),add:async()=>{writes++;throw new Error("backend failed");}});
  await tick();current=false;h.clickAction(0);await tick();assert.equal(writes,0);assert.match(h.el("error").textContent,/变化/);
  current=true;h.clickAction(0);await tick();assert.equal(writes,1);assert.match(h.el("error").textContent,/backend failed/);assert.equal(h.dialog().removed,undefined);h.el("close").fire("click");await done;
});
test("duplicate Add and Escape during an in-flight mutation do not duplicate or abandon the write",async()=>{
  const h=harness();let writes=0,resolveAdd;const done=openContigChrAlignments(h.host,{load:async()=>report(),add:()=>{writes++;return new Promise(resolve=>{resolveAdd=resolve;});}});
  await tick();h.clickAction(0);h.clickAction(0);h.dialog().fire("cancel");assert.equal(writes,1);assert.equal(h.dialog().removed,undefined);
  resolveAdd(true);await tick();h.el("close").fire("click");await done;
});
test("cancelled pending reads never update a removed panel and no-results never offers Add",async()=>{
  const h=harness();let resolveLoad;const done=openContigChrAlignments(h.host,{load:()=>new Promise(resolve=>{resolveLoad=resolve;})});
  h.dialog().fire("cancel");await done;const old=h.el("table").innerHTML;resolveLoad(report());await tick();assert.equal(h.el("table").innerHTML,old);
  const h2=harness();const done2=openContigChrAlignments(h2.host,{load:async()=>report([])});await tick();assert.match(h2.el("table").innerHTML,/没有其他/);assert.doesNotMatch(h2.el("table").innerHTML,/data-chr-action/);h2.el("close").fire("click");await done2;
});


test("a target created after opening is refreshed as existing without claiming another add",async()=>{
  const h=harness();let attempted=false;
  const done=openContigChrAlignments(h.host,{load:async()=>report([candidate(attempted?{presence:"existing",existingCtgId:42}:{})]),add:async()=>{attempted=true;return {changed:false};}});
  await tick();h.clickAction(0);await tick();assert.equal(h.el("status").textContent,"已存在");assert.match(h.el("table").innerHTML,/定位/);h.el("close").fire("click");await done;
});


test("cross-chr source model accepts full, split, auxiliary and single-base contigs without split eligibility", () => {
  const full={assemblyCtgId:1,totalLength:1000,originSourceSeqId:11,orient:"+",assignedChrName:"chrA"};
  const split={assemblyCtgId:2,totalLength:100,orient:"-",sourceFragment:{sourceSeqId:12,sourceStart:501,sourceEnd:600}};
  const tiny={assemblyCtgId:3,totalLength:1,orient:"+",assignedChrName:null};
  const auxiliary={assemblyCtgId:4,totalLength:2000,originSourceSeqId:14,orient:"-",assignedChrName:"chrC"};
  const assembly={selectedChrName:"chrA",chrCtgs:[full,split,tiny],supportChrCtgs:[auxiliary],trackView:{alignmentLength:10}};
  assert.equal(resolveContigChrAlignmentModel(assembly,1).sourceEnd,1000);
  assert.equal(resolveContigChrAlignmentModel(assembly,2).sourceStart,501);
  assert.equal(resolveContigChrAlignmentModel(assembly,2).sourceEnd,600);
  assert.equal(resolveContigChrAlignmentModel(assembly,3).sourceEnd,1);
  assert.equal(resolveContigChrAlignmentModel(assembly,3).sourceChrName,"unplaced");
  assert.equal(resolveContigChrAlignmentModel(assembly,{assemblyCtgId:4,trackRole:"support"}).sourceSeqId,14);
  assert.equal(resolveContigChrAlignmentModel(assembly,{assemblyCtgId:4,trackRole:"support"}).sourceChrName,"chrC");
  assert.equal(resolveContigChrAlignmentModel(assembly,{assemblyCtgId:1,trackRole:"phased"}).sourceEnd,1000);
  assert.equal(resolveContigChrAlignmentModel({...assembly,hiddenPrimaryCtgIds:[1]},1),null);
  assert.equal(resolveContigChrAlignmentModel(assembly,999),null);
  assert.equal(resolveContigChrAlignmentModel({...assembly,chrCtgs:[{...full,memberCount:2}]},1),null);
});

test("cross-chr feedback directs undo to the destination, not the source", async () => {
  const h=harness(),writes=[];
  const done=openContigChrAlignments(h.host,{load:async()=>report(),add:async args=>{writes.push(args);return {changed:true};}});
  await tick();h.clickAction(0);await tick();
  assert.equal(writes[0].sourceChrName,"chrA");
  assert.match(h.el("status").textContent,/目标 chr 撤销/);
  assert.doesNotMatch(h.el("status").textContent,/当前 chr 撤销/);
  h.el("close").fire("click");await done;
});


test("cross-chr preview retains the actual primary or support source role", async () => {
  const ctg = {assemblyCtgId:6, totalLength:1000, memberCount:1};
  const assembly = {chrCtgs:[ctg], supportChrCtgs:[{...ctg, assemblyCtgId:7}]};
  assert.equal(resolveContigChrAlignmentModel(assembly, {assemblyCtgId:6, trackRole:"primary"}).colorRole, "primary");
  assert.equal(resolveContigChrAlignmentModel(assembly, {assemblyCtgId:7, trackRole:"support"}).colorRole, "companion");
  assert.match(renderChrAlignmentPreview(source, candidate(), "companion"), /data-contig-role="companion"/);
  assert.match(renderChrAlignmentPreview(source, candidate()), /data-contig-role="primary"/);
  const h = harness();
  const done = openContigChrAlignments(h.host, {sourceRole:"companion", load:async()=>report()});
  await tick();
  assert.match(h.el("preview").innerHTML, /data-contig-role="companion"/);
  h.el("close").fire("click");
  await done;
});
