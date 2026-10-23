import test from "node:test";
import assert from "node:assert/strict";
import { normalizeAnchorCuts, localAnchorCuts, splitLocalMemberAtAnchors, anchorSplitRanges } from "../anchor-contig-split.js";
import { memberAnchorEndpointKey, memberSourceInterval } from "../subview-fragment-model.js";
import { openAnchorContigSplit, renderAnchorSplitPreview } from "../anchor-contig-split-dialog.js";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { projectRenderedSubviewToComposition } from "../subview-composition-controller.js";
import { renderAssemblyPage } from "./tabs-semantics-harness.mjs";

const model = { sourceStart: 101, sourceEnd: 1100, orient: "+", name: "ctg<1>", refLength: 1000,
  hits: [{ queryStart: 201, queryEnd: 900, refStart: 101, refEnd: 800, strand: "+" }] };

test("anchor cuts exclude ends/invalid values, deduplicate and order in source coordinates", () => {
  assert.deepEqual(normalizeAnchorCuts([100,101,300,300,1099,1100,Infinity,1.5],model),[101,300,1099]);
  assert.deepEqual(anchorSplitRanges({...model,orient:"-"},[300,900]),[[901,1100],[301,900],[101,300]]);
});
for (const orient of ["+", "-"]) for (const flipped of [false,true]) {
  test(`active manual/evidence anchor cuts target only source-owned ${orient}/${flipped} member`, () => {
    const state = createIdentityRenderState("composition");
    const composition = projectRenderedSubviewToComposition(state,renderAssemblyPage(state));
    const member = composition.members.find(m => m.assemblyCtgId === 30);
    member.baseOrientation = orient; member.flipped = flipped;
    const endpointKey = memberAnchorEndpointKey(member);
    const endpoint = (sourceCutAfter) => ({endpointKey, cutBp: orient === "+" ? sourceCutAfter+1 : 16000-sourceCutAfter+1});
    composition.activeAnchors = [{hitKey:"active",edge:"left",descriptor:{top:endpoint(4000),bottom:{endpointKey:"other",cutBp:5001}}}];
    composition.manualAnchors = [{endpointA:endpoint(8000),endpointB:{endpointKey:"other",cutBp:9001}},
      {endpointA:{...endpoint(4000),sourceCutAfter:4000}}];
    assert.deepEqual(localAnchorCuts(composition,member),[4000,8000]);
    const before = structuredClone(composition);
    const split = splitLocalMemberAtAnchors(composition,member.entityKey,[8000,4000,4000]);
    assert.equal(split.changed,true);
    assert.deepEqual(composition,before,"input is immutable");
    const parts = split.composition.members.filter(m => m.assemblyCtgId === 30);
    assert.deepEqual(parts.map(m => memberSourceInterval(m)).map(r => [r.sourceStart,r.sourceEnd]),[[1,4000],[4001,8000],[8001,16000]]);
    assert.equal(parts.every(m => m.flipped === flipped),true);
    assert.equal(split.composition.members.filter(m => m.assemblyCtgId === 2).length,1,"opposite anchor endpoint is not split");
    assert.equal(splitLocalMemberAtAnchors(composition,member.entityKey,[]).changed,false);
  });
}

// Event-level harness: tests dialog behavior without claiming native visual QA.
function harness() {
  const nodes = new Map(); let dialog, restored = 0;
  const node = (attrs={}) => ({attrs,style:{},disabled:false,textContent:"",handlers:new Map(),
    setAttribute(k,v){attrs[k]=String(v);},getAttribute:k=>attrs[k]??null,
    addEventListener(type,fn){this.handlers.set(type,fn);},
    fire(type,extra={}){return this.handlers.get(type)?.({target:this,preventDefault(){},...extra});},focus(){},
    closest(selector){return Object.keys(attrs).some(k=>selector===`[${k}]`)?this:null;}});
  const doc = {activeElement:{isConnected:true,focus(){restored++;}},body:{append:n=>{dialog=n;}},
    querySelector:()=>dialog&&!dialog.removed?dialog:null,createElement:()=>{
      const d=node();Object.assign(d,{querySelector(s){if(!nodes.has(s))nodes.set(s,node());return nodes.get(s);},
        showModal(){this.open=true;},close(){this.open=false;},remove(){this.removed=true;}});return d;}};
  return {host:{ownerDocument:doc},node,dialog:()=>dialog,el:name=>dialog.querySelector(`[data-anchor-${name}]`),restored:()=>restored};
}
test("anchor edge click and keyboard toggle multiple cuts without numeric input or premature writes",async()=>{
  const h=harness(),writes=[];
  const done=openAnchorContigSplit(h.host,model,{commit:async args=>{writes.push(args);return true;}});
  assert.doesNotMatch(h.dialog().innerHTML,/<input/); assert.equal(h.el("confirm").disabled,true);
  h.dialog().fire("click",{target:h.node({"data-anchor-cut":"200"})});
  h.dialog().fire("keydown",{key:"Enter",target:h.node({"data-anchor-cut":"900"})});
  h.dialog().fire("click",{target:h.node({"data-anchor-cut":"200"})});
  assert.equal(writes.length,0);assert.match(h.el("ranges").textContent,/800 bp.*200 bp/);
  await h.el("confirm").fire("click"); assert.equal(await done,true);
  assert.deepEqual(writes,[{cuts:[900]}]);assert.equal(h.restored(),1);
});
for(const orient of ["+","-"]) test(`bar click maps ${orient} display to source cut`,async()=>{
  const h=harness(),writes=[];
  const done=openAnchorContigSplit(h.host,{...model,orient},{commit:async args=>{writes.push(args);}});
  Object.assign(h.el("split-svg"),{createSVGPoint:()=>({matrixTransform(){return {x:this.x};}}),getScreenCTM:()=>({inverse(){return {};}})});
  h.dialog().fire("click",{target:h.node({"data-anchor-split-bar":"1"}),clientX:200,clientY:105});
  await h.el("confirm").fire("click");assert.equal(await done,true);
  assert.deepEqual(writes,[{cuts:[orient==="+"?350:850]}]);
});
test("Local anchor preview is read-only, cancellation and stale context never mutate",async()=>{
  const h=harness();let writes=0,current=false;
  const done=openAnchorContigSplit(h.host,{...model,cuts:[300,900],readOnlyAnchors:true},{isCurrent:()=>current,commit:()=>{writes++;}});
  h.dialog().fire("click",{target:h.node({"data-anchor-cut":"300"})});
  assert.match(h.el("ranges").textContent,/200 bp.*600 bp.*200 bp/);
  await h.el("confirm").fire("click");assert.equal(writes,0);assert.match(h.el("error").textContent,/变化/);
  h.dialog().fire("cancel");assert.equal(await done,false);
});
test("commit errors preserve draft and busy confirmation serializes exactly one write",async()=>{
  const h=harness();let writes=0,release;
  const done=openAnchorContigSplit(h.host,{...model,cuts:[300]},{commit:()=>{
    writes++;if(writes===1)throw new Error("native failed");return new Promise(r=>{release=r;});}});
  await h.el("confirm").fire("click");assert.match(h.el("error").textContent,/native failed/);
  const committing=h.el("confirm").fire("click");
  await h.el("confirm").fire("click");h.dialog().fire("cancel");
  assert.equal(writes,2);assert.equal(h.dialog().removed,undefined);
  release(true);await committing;assert.equal(await done,true);
});
test("alignment preview respects hit strand and escapes labels",()=>{
  const forward=renderAnchorSplitPreview(model,[300]);
  const reverse=renderAnchorSplitPreview({...model,hits:model.hits.map(h=>({...h,strand:"-"}))},[300]);
  assert.match(forward,/ctg&lt;1&gt;/);assert.notEqual(forward,reverse);
  assert.match(forward,/552,100 104,100/);assert.match(reverse,/104,100 552,100/);
});
