import test from "node:test";
import assert from "node:assert/strict";
import { fitFullRangeDragBounds,compactFullRangeEdges,fullRangeTextMatrix,
  IDENTITY_MATRIX,inverseMatrix,matrixPoint,multiplyMatrix } from "../full-range-drag-geometry.js";
const close = (actual,expected) => assert.ok(Math.abs(actual-expected)<1e-7*Math.max(1,Math.abs(expected)),`${actual} != ${expected}`);
const rotation = angle => { const a=angle*Math.PI/180;return [Math.cos(a),Math.sin(a),-Math.sin(a),Math.cos(a),3,5]; };
const edges = [{position:0,motion:0,offset:0},{position:100,motion:0,offset:0},
  {position:20,motion:1,offset:0},{position:40,motion:1,offset:0},
  {position:30,motion:1,offset:-20},{position:30,motion:1,offset:20}];
for (const delta of [-1e12,-1000,-100,-10,0,10,100,1000,1e12]) test(`fit dynamic geometry and fixed glyphs, delta=${delta}`,()=>{
  const fit=fitFullRangeDragBounds(edges,delta,200);
  assert.ok(fit.scale>0&&Number.isFinite(fit.width));
  for (const edge of edges) {
    const x=(edge.position+edge.motion*delta-fit.minX)*fit.scale+edge.offset;
    assert.ok(x>=-1e-5 && x<=200+1e-5,`edge outside viewport: ${x}`);
  }
  if (Math.abs(delta)>100) assert.ok(fit.scale<fitFullRangeDragBounds(edges,0,200).scale);
});
test("moving back into range expands the live scale, not a monotonically growing envelope",()=>{
  assert.deepEqual(fitFullRangeDragBounds(edges,0,200),fitFullRangeDragBounds(edges,0,200));
  assert.ok(fitFullRangeDragBounds(edges,0,200).scale>fitFullRangeDragBounds(edges,1000,200).scale);
});
for (const angle of [0,15,-45,90]) for (const scale of [0.001,0.5,1,4]) test(`text shape and anchor stay correct, rotation=${angle}, scale=${scale}`,()=>{
  const original=rotation(angle),parent=multiplyMatrix(rotation(23),[2,0,0,1.5,11,7]);
  const counter=fullRangeTextMatrix(original,parent,17,29,scale);
  const fit=[scale,0,0,1,-13,0];
  const before=multiplyMatrix(parent,original),after=multiplyMatrix(fit,multiplyMatrix(parent,counter));
  const anchor=matrixPoint(before,17,29),nextAnchor=matrixPoint(after,17,29);
  close(nextAnchor[0],anchor[0]*scale-13);close(nextAnchor[1],anchor[1]);
  for(const [dx,dy] of [[1,0],[0,1],[13,7]]) {
    const old=matrixPoint(before,17+dx,29+dy),next=matrixPoint(after,17+dx,29+dy);
    close(next[0]-nextAnchor[0],old[0]-anchor[0]);close(next[1]-nextAnchor[1],old[1]-anchor[1]);
  }
});
test("compact bounds preserve the exact fit without argument-count limits on large scenes",()=>{
  const large=Array.from({length:150000},(_,i)=>({position:i/100,motion:i%3,offset:i%4}));
  const compact=compactFullRangeEdges(large);
  assert.ok(compact.length<=24);
  for(const delta of [-1000,0,1000]) {
    const full=fitFullRangeDragBounds(large,delta,500),fast=fitFullRangeDragBounds(compact,delta,500);
    close(full.scale,fast.scale);close(full.minX,fast.minX);
  }
});
test("invalid geometry fails explicitly and affine inversion is lossless",()=>{
  for(const args of [[[],0,100],[edges,NaN,100],[edges,0,0]])
    assert.throws(()=>fitFullRangeDragBounds(...args),RangeError);
  const matrix=[2,3,4,7,11,13];
  multiplyMatrix(matrix,inverseMatrix(matrix)).forEach((value,index)=>close(value,IDENTITY_MATRIX[index]));
  assert.throws(()=>inverseMatrix([0,0,0,0,0,0]),RangeError);
});

test("an impossibly narrow label is clipped without freezing or rejecting the drag",()=>{
 const narrow=[{position:0,motion:0,offset:0},{position:100,motion:0,offset:0},{position:30,motion:1,offset:-150},{position:30,motion:1,offset:150}];
 const fit=fitFullRangeDragBounds(narrow,200,100);
 assert.equal(fit.labelsClipped,true);assert.ok(fit.scale>0&&fit.scale<1);
});
