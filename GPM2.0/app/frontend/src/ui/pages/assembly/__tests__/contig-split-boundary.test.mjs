import test from "node:test";
import assert from "node:assert/strict";
import { resolveContigUnsplitModel, resolveContigSplitBoundaries, highlightContigSplitBoundary, bandBoundaryAnchors } from "../contig-split-boundary.js";
import { buildCollinearityBandPoints } from "../track-render-geometry.js";
import { createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
const hit=(a,b,identityPct=99,blockLength=b-a+1)=>({queryStart:a,queryEnd:b,identityPct,blockLength});
const assembly=(orient="+")=>({selectedChrName:"A",trackView:{alignmentLength:100,minIdentityPct:90},chrCtgs:[{assemblyCtgId:6,totalLength:1000,orient,hits:[hit(101,300),hit(501,800),hit(1,1000,50),hit(1,20),{...hit(1,1000),chrName:"B"}]}]});
test("envelope uses all qualifying current-Ref alignments, not Ref coordinates or a single block",()=>{
  assert.deepEqual(resolveContigSplitBoundaries(assembly(),6),{assemblyCtgId:6,left:100,right:800,reverse:false,minAlignmentLength:100,minIdentityPct:90});
  const a=assembly();a.chrCtgs[0].hits.reverse();assert.equal(resolveContigSplitBoundaries(a,6).left,100);
});
test("reverse display swaps visual sides and preserves original source coordinates",()=>{
  const result=resolveContigSplitBoundaries(assembly("-"),6);assert.equal(result.left,800);assert.equal(result.right,100);
  const a=assembly("-");a.chrCtgs[0].totalLength=700;a.chrCtgs[0].sourceFragment={sourceStart:101,sourceEnd:800};
  assert.equal(resolveContigSplitBoundaries(a,6).left,null);assert.equal(resolveContigSplitBoundaries(a,6).right,null);
});
test("missing, hidden or fully filtered contigs have no usable boundary",()=>{
  const a=assembly();a.trackView.alignmentLength=2000;assert.equal(resolveContigSplitBoundaries(a,6),null);
  assert.equal(resolveContigSplitBoundaries(assembly(),999),null);
  assert.equal(resolveContigSplitBoundaries({...assembly(),activeHitsTrackKey:"A"},6),null);
  const b=assembly();b.hiddenPrimaryCtgIds=[6];assert.equal(resolveContigSplitBoundaries(b,6),null);
});
for(const direction of ["up","down"]) for(const reversed of [false,true]) {
  test(`preview follows actual polygon edge: ${direction}, reversed=${reversed}`,()=>{
    const points=buildCollinearityBandPoints({ctgRect:{x:20,width:80},refRect:{x:200,width:50},refTop:10,refBottom:24,ctgTop:90,ctgBottom:104,direction,reversed});
    const anchors=bandBoundaryAnchors(points,direction,reversed);
    assert.deepEqual(anchors.left.split(" ")[0].split(",").map(Number),[20,direction==="down"?104:90]);
    assert.deepEqual(anchors.right.split(" ")[0].split(",").map(Number),[100,direction==="down"?104:90]);
    assert.deepEqual(anchors.left.split(" ")[1].split(",").map(Number),[reversed?250:200,direction==="down"?10:24]);
    assert.deepEqual(anchors.right.split(" ")[1].split(",").map(Number),[reversed?200:250,direction==="down"?10:24]);
  });
}
test("hover uses the chosen outer edge, draws a local-anchor style line, and removes it without edits",()=>{
  const groups=[];
  const doc={createElementNS:(_ns,tag)=>({tag,attrs:{},children:[],setAttribute(k,v){this.attrs[k]=v;},append(n){this.children.push(n);},remove(){this.removed=true;}})};
  const band=(a,b)=>({ownerDocument:doc,ownerSVGElement:{append:(n)=>groups.push(n)},getAttribute:(key)=>({"data-band-query-start":a,"data-band-query-end":b,"data-band-left-anchor":"20,90 200,24","data-band-right-anchor":"100,90 250,24"})[key]});
  const host={querySelectorAll:()=>[band(101,300),band(501,800)]};const boundary=resolveContigSplitBoundaries(assembly(),6);
  const cleanup=highlightContigSplitBoundary(host,boundary,"left");assert.equal(groups.length,1);
  assert.match(groups[0].children[0].attrs.class,/subview-anchor-line is-focused/);
  assert.equal(groups[0].children[0].attrs.points,"20,90 200,24");cleanup();assert.ok(groups[0].removed);
  const cleanup2=highlightContigSplitBoundary(host,boundary,"right");assert.equal(groups.length,2);cleanup2();assert.ok(groups[1].removed);
});
test("main rendering keeps .1 then .2 on one ds row with visible spacing and matching band endpoints",()=>{
  const ctgs=[{assemblyCtgId:3,name:"tig.1",totalLength:400,orient:"-",anchorStart:-399,datasetId:1,sourceFragment:{sourceSeqId:1,groupKey:"manual-fragment:1",sourceStart:601,sourceEnd:1000,sourceLength:1000,gapBeforeBp:0,gapAfterBp:0},hits:[]},
    {assemblyCtgId:2,name:"tig.2",totalLength:600,orient:"-",anchorStart:1,datasetId:1,sourceFragment:{sourceSeqId:1,groupKey:"manual-fragment:1",sourceStart:1,sourceEnd:600,sourceLength:1000,gapBeforeBp:0,gapAfterBp:0},hits:[{...hit(1,600),ctgStart:1,ctgEnd:600,refStart:1,refEnd:600,strand:"-"}]}];
  const html=renderAssemblyPage(createState({assembly:{selectedChrName:"Chr01",chromosomes:[{chrName:"Chr01",chrLength:600}],chrCtgs:ctgs,supportChrCtgs:[],refTrackMembers:[{segmentStartBp:1,segmentEndBp:600}],trackView:{alignmentLength:1,supportDsCtgLen:0}}}));
  const boxes=ctgs.map(c=>{const m=html.match(new RegExp(`<g class="track-ctg-group[^>]*data-track-contig-id="${c.assemblyCtgId}"[^>]*data-track-role="primary"[^>]*data-track-rect-x="([^"]+)"[^>]*data-track-rect-y="([^"]+)"[^>]*data-track-rect-width="([^"]+)"`));assert.ok(m);return {x:+m[1],y:+m[2],width:+m[3]};});
  assert.equal(boxes[0].y,boxes[1].y);assert.ok(boxes[1].x-boxes[0].x-boxes[0].width>=19.98);
  assert.match(html,/tig.1/);assert.match(html,/tig.2/);assert.match(html,/data-band-left-anchor=/);assert.doesNotMatch(html,/ctg-split-dialog/);
});

function splitAssembly(orient = "+") {
  return { chrCtgs: [[2, 1, 300], [3, 301, 700], [4, 701, 1000]].map(([assemblyCtgId, sourceStart, sourceEnd]) => ({
    assemblyCtgId, orient, sourceFragment: { sourceSeqId: 1, groupKey: "manual-fragment:1", sourceStart, sourceEnd, sourceLength: 1000 },
  })) };
}
test("unsplit sides follow display orientation and retain immutable source preconditions", () => {
  for (const orient of ["+", "-"]) {
    const a = splitAssembly(orient), m = resolveContigUnsplitModel(a, 3);
    assert.equal(m.left.neighborCtgId, orient === "+" ? 2 : 4);
    assert.equal(m.right.neighborCtgId, orient === "+" ? 4 : 2);
    assert.equal(m.left.sourceStart, 301); assert.equal(m.left.sourceEnd, 700);
    assert.equal(m.left.orient, orient);
    assert.equal(resolveContigUnsplitModel(a, 2)[orient === "+" ? "left" : "right"], null);
  }
});
test("unsplit excludes full contigs, inspection-only copies, other sources/groups, gaps, hidden and flipped neighbors", () => {
  assert.equal(resolveContigUnsplitModel({ chrCtgs: [{ assemblyCtgId: 1, totalLength: 1000 }] }, 1), null);
  const full = splitAssembly(); full.chrCtgs = [full.chrCtgs[0]]; full.chrCtgs[0].sourceFragment.sourceEnd = 1000;
  assert.equal(resolveContigUnsplitModel(full, 2), null);
  const copy = splitAssembly(); copy.chrCtgs = [copy.chrCtgs[0]]; copy.chrCtgs[0].sourceFragment.groupKey = "manual-fragment:chr-add:1:2";
  assert.equal(resolveContigUnsplitModel(copy, 2), null);
  for (const mutate of [
    (a) => { a.chrCtgs[0].sourceFragment.sourceSeqId = 2; },
    (a) => { a.chrCtgs[0].sourceFragment.groupKey = "manual-fragment:2"; },
    (a) => { a.chrCtgs[0].sourceFragment.sourceEnd = 299; },
    (a) => { a.hiddenPrimaryCtgIds = [2]; },
    (a) => { a.chrCtgs[0].orient = "-"; },
  ]) {
    const a = splitAssembly(); mutate(a); assert.equal(resolveContigUnsplitModel(a, 3).left, null);
  }
  const ambiguous = splitAssembly(); ambiguous.chrCtgs.push({ ...ambiguous.chrCtgs[0], assemblyCtgId: 9 });
  assert.equal(resolveContigUnsplitModel(ambiguous, 3).left, null);
});
