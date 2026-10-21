import test from "node:test";
import assert from "node:assert/strict";
import { parseManualCut, manualCutGeometry, manualBoundaryX, renderManualSplitPreview, openManualContigSplit } from "../manual-contig-split.js";
import { resolveContigSplitModel } from "../contig-split-boundary.js";

const model={assemblyCtgId:6,name:"tig",sourceStart:101,sourceEnd:1100,orient:"-",chrName:"ChrA",refLength:2000,
  hits:[{queryStart:201,queryEnd:400,refStart:501,refEnd:700,strand:"-"},{queryStart:601,queryEnd:900,refStart:101,refEnd:400,strand:"-"}]};
test("manual coordinate is a strict source boundary, including inside a previously split interval",()=>{
  assert.equal(parseManualCut("700",model),700);
  for(const value of ["", "100","1100","700.5","7e2","9007199254740993"]) assert.equal(parseManualCut(value,model),null);
});
test("manual preview lengths and line position follow display orientation",()=>{
  assert.deepEqual(manualCutGeometry(model,300),{leftLength:800,rightLength:200,x:64+632*.8});
  assert.deepEqual(manualCutGeometry({...model,orient:"+"},300),{leftLength:200,rightLength:800,x:64+632*.2});
  assert.equal(manualBoundaryX(model,300),manualCutGeometry(model,300).x);
});
test("preview exposes every alignment edge including internal edges, escapes source labels, and has no assignment/recommendation copy",()=>{
  const html=renderManualSplitPreview({...model,name:'tig<unsafe>"'});
  for(const cut of [200,400,600,900]) assert.match(html,new RegExp(`data-manual-cut="${cut}"`));
  assert.match(html,/role="button" tabindex="0"/);assert.match(html,/tig&lt;unsafe&gt;&quot;/);
  assert.doesNotMatch(html,/<unsafe>|MAPQ|归组|推荐|候选/);
  const atEnds=renderManualSplitPreview({...model,hits:[{queryStart:101,queryEnd:1100,refStart:1,refEnd:1000,strand:"+"}]});
  assert.doesNotMatch(atEnds,/data-manual-cut=/);
});
test("manual model reuses length/identity filters and supports contigs without Ref hits",()=>{
  const a={selectedChrName:"A",trackView:{alignmentLength:100,minIdentityPct:90},chrCtgs:[{assemblyCtgId:6,name:"tig",orient:"-",totalLength:1000,
    hits:[{queryStart:201,queryEnd:400,refStart:1,refEnd:200,blockLength:200,identityPct:99},{queryStart:1,queryEnd:1000,blockLength:10,identityPct:99}]}]};
  assert.equal(resolveContigSplitModel(a,6).hits.length,1);
  a.chrCtgs[0].hits=[];assert.equal(resolveContigSplitModel(a,6).sourceEnd,1000);
  assert.equal(resolveContigSplitModel({...a,hiddenPrimaryCtgIds:[6]},6),null);
});

// Event-level DOM harness, not browser/native visual acceptance.
function harness(){
  const nodes=new Map();let dialog;let focusRestored=0;
  const node=(attrs={})=>({attrs,style:{},value:"",disabled:false,textContent:"",handlers:new Map(),
    setAttribute(k,v){attrs[k]=String(v);},getAttribute:k=>attrs[k]??null,
    addEventListener(type,fn){this.handlers.set(type,fn);},fire(type,extra={}){return this.handlers.get(type)?.({target:this,preventDefault(){},...extra});},
    focus(){},select(){},closest(selector){return selector==="[data-manual-cut]"&&attrs["data-manual-cut"]?this:null;}});
  const previousFocus={isConnected:true,focus(){focusRestored++;}};
  const doc={activeElement:previousFocus,body:{append:n=>{dialog=n;}},querySelector:()=>dialog&&!dialog.removed?dialog:null,
    createElement:()=>{const d=node();Object.assign(d,{innerHTML:"",querySelector(selector){if(!nodes.has(selector))nodes.set(selector,node());return nodes.get(selector);},
      querySelectorAll:()=>[...nodes.values()],showModal(){this.open=true;},close(){this.open=false;},remove(){this.removed=true;}});return d;}};
  return {host:{ownerDocument:doc},node,dialog:()=>dialog,el:name=>dialog.querySelector(`[data-manual-split-${name}]`),svg:name=>dialog.querySelector(`[data-manual-${name}]`),focusRestored:()=>focusRestored};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test("numeric edits and alignment-edge clicks immediately update the same preview and input without writing",async()=>{
  const h=harness();const writes=[];
  const done=openManualContigSplit(h.host,model,{commit:async args=>{writes.push(args);return true;}});
  const originalMarkup=h.dialog().innerHTML;
  h.el("position").value="300";h.el("position").fire("input");
  assert.match(h.el("lengths").textContent,/800 bp.*200 bp/);
  assert.equal(+h.svg("cut-line").attrs.x1,manualCutGeometry(model,300).x);
  await h.dialog().fire("click",{target:h.node({"data-manual-cut":"900"})});
  assert.equal(h.el("position").value,"900");assert.match(h.el("lengths").textContent,/200 bp.*800 bp/);
  assert.equal(h.dialog().innerHTML,originalMarkup,"preview update does not replace panel/edge DOM");assert.equal(writes.length,0);
  await h.el("form").fire("submit");assert.equal(await done,true);
  assert.deepEqual(writes,[{assemblyCtgId:6,cutAfter:900,sourceStart:101,sourceEnd:1100,orient:"-"}]);
  assert.equal(h.focusRestored(),1);
});
test("invalid input disables split and hides old preview; correcting it restores live lengths",async()=>{
  const h=harness();let writes=0;const done=openManualContigSplit(h.host,model,{commit:async()=>{writes++;}});
  h.el("position").value="1100";h.el("position").fire("input");
  assert.equal(h.el("confirm").disabled,true);assert.equal(h.svg("cut-line").attrs.visibility,"hidden");
  await h.el("form").fire("submit");assert.equal(writes,0);
  h.el("position").value="500";h.el("position").fire("input");assert.equal(h.el("confirm").disabled,false);
  h.el("cancel").fire("click");assert.equal(await done,false);assert.equal(writes,0);
});
test("keyboard edge selection and Escape are non-destructive",async()=>{
  const h=harness();let writes=0;const done=openManualContigSplit(h.host,model,{commit:async()=>{writes++;}});
  h.dialog().fire("keydown",{key:"Enter",target:h.node({"data-manual-cut":"400"})});assert.equal(h.el("position").value,"400");
  h.dialog().fire("cancel");assert.equal(await done,false);assert.equal(writes,0);
});
test("stale source and backend failures keep the draft instead of closing or pretending success",async()=>{
  const h=harness();let current=false,writes=0;
  const done=openManualContigSplit(h.host,model,{isCurrent:()=>current,commit:async()=>{writes++;throw new Error("backend failed");}});
  h.el("position").value="700";h.el("position").fire("input");await h.el("form").fire("submit");assert.equal(writes,0);
  current=true;h.el("position").fire("input");await h.el("form").fire("submit");assert.equal(writes,1);
  assert.equal(h.el("position").value,"700");assert.match(h.el("error").textContent,/backend failed/);assert.equal(h.dialog().removed,undefined);
  h.el("cancel").fire("click");assert.equal(await done,false);
});
test("confirmation serializes one write and cannot be duplicated while it is in flight",async()=>{
  const h=harness();let writes=0,resolveCommit;
  const done=openManualContigSplit(h.host,model,{commit:()=>{writes++;return new Promise(resolve=>{resolveCommit=resolve;});}});
  const committing=h.el("form").fire("submit");await tick();await h.el("form").fire("submit");
  h.dialog().fire("cancel");assert.equal(h.dialog().removed,undefined);assert.equal(writes,1);
  resolveCommit(true);await committing;assert.equal(await done,true);
});


test("manual split preview is scoped to the primary lane, not an auxiliary contig", () => {
  const assembly = {selectedChrName:"Chr1", chrCtgs:[], supportChrCtgs:[{assemblyCtgId:99, totalLength:1000}]};
  assert.equal(resolveContigSplitModel(assembly, 99), null);
});
