import test from "node:test";
import assert from "node:assert/strict";
import {createFullRangeDragPreview} from "../full-range-drag-preview.js";

function fixture(subview=false,composition=false){
 const all=[],queryMaps=new Map();
 const node=(name,attrs={},box={x:0,y:0,width:0,height:0})=>{
  const attributes=new Map(Object.entries(attrs)),classes=new Set();
  const result={localName:name,style:{},parentNode:null,isConnected:true,clientWidth:100,scrollLeft:0,
   getAttribute:key=>attributes.has(key)?attributes.get(key):null,
   setAttribute:(key,value)=>attributes.set(key,String(value)),removeAttribute:key=>attributes.delete(key),hasAttribute:key=>attributes.has(key),
   classList:{add:key=>classes.add(key),remove:key=>classes.delete(key),contains:key=>classes.has(key)},
   getCTM:()=>({a:1,b:0,c:0,d:1,e:0,f:0}),getBBox:()=>box,
   closest:selector=>selector==="[data-subview-composition-scene]"&&composition?result:null,
   contains:child=>{for(let current=child;current;current=current.parentNode)if(current===result)return true;return false;},
   querySelector:selector=>result.querySelectorAll(selector)[0]||null,
   querySelectorAll:selector=>{
    const mapped=queryMaps.get(result)?.[selector];if(mapped)return mapped;
    const match=selector.match(/^\[([^=]+)='([^']+)'\]$/);
    return match?all.filter(item=>item.getAttribute(match[1])===match[2]):[];
   },snapshot:()=>[...attributes].sort((a,b)=>a[0].localeCompare(b[0]))};all.push(result);return result;
 };
 const prefix=subview?'subview':'track';
 const scroll=node('div',{[`data-${prefix}-inner-width`]:'100',[`data-${prefix}-domain-span-bp`]:'100',
  [`data-${prefix}-window-start-bp`]:'0',[`data-${prefix}-viewbox-min-x`]:'0','data-view-navigation-start-bp':'0','data-view-navigation-end-bp':'100'});
 const svg=node('svg',{width:'100',height:'60',viewBox:'0 0 100 60',preserveAspectRatio:'xMinYMin meet'});svg.parentNode=scroll;
 const group=node('g',{'data-subview-rect-x':'20','data-subview-rect-width':'20'});group.parentNode=svg;svg.firstElementChild=group;svg.childElementCount=2;
 const bar=node('rect',{x:'20',y:'10',width:'20',height:'10'},{x:20,y:10,width:20,height:10});bar.parentNode=group;
 const text=node('text',{x:'30',y:'10'},{x:20,y:0,width:20,height:10});text.parentNode=group;
 const ref=node('rect',{x:'0',y:'40',width:'100',height:'10'},{x:0,y:40,width:100,height:10});ref.parentNode=svg;
 const band=node('polygon',{points:'20,20 40,20 60,40 50,40'});band.parentNode=svg;
 queryMaps.set(scroll,{'svg.assembly-track-svg':[svg],
  '[data-track-contig-id="1"][data-track-role="primary"]':[group],
  '[data-band-track-role="primary"][data-band-contig-id="1"]':[band],
  '[data-subview-track-slot="top"][data-subview-contig-id="1"]':[group],
  '[data-subview-top-contig-id="1"]':[band]});
 queryMaps.set(svg,{'rect.track-ctg, rect.track-reference-member, rect.track-reference-bar, text':[bar,text,ref],
  '[data-subview-rect-x][data-subview-rect-width]':[group]});
 const payload=subview?{slot:'top',contigId:1}:{trackRole:'primary',assemblyCtgId:1};
 return {all,scroll,svg,group,band,text,handle:()=>createFullRangeDragPreview(scroll,payload,{subview}),snapshot:()=>all.map(item=>item.snapshot())};
}
for(const view of ['main','pair','composition'])test(`${view} handle keeps live geometry, updates pointer scale, and restores only its own graph`,()=>{
 const f=fixture(view!=='main',view==='composition'),before=f.snapshot(),handle=f.handle();
 const first=handle.update(150),inner=Number(f.scroll.getAttribute(`data-${view==='main'?'track':'subview'}-inner-width`));
 assert.equal(inner,100*first.scale);assert.ok(inner<100);assert.equal(handle.isCurrent(),true);
 assert.equal(f.group.getAttribute('transform'),'translate(150.00 0)');
 assert.equal(f.svg.getAttribute('preserveAspectRatio'),'none');assert.match(f.text.style.transform,/^matrix\([^,]+,[^,]+,[^,]+,[^,]+,[^,]+,[^,]+\)$/);
 assert.equal(f.band.getAttribute('points'),view==='main'?'20.00,20.00 40.00,20.00 210.00,40.00 200.00,40.00':'170.00,20.00 190.00,20.00 60.00,40.00 50.00,40.00');
 const second=handle.update(0);assert.ok(second.scale>first.scale,'inward drag must refit, not freeze or accumulate envelope');
 f.svg.isConnected=false;assert.equal(handle.isCurrent(),false);
 handle.restore();handle.restore();assert.deepEqual(f.snapshot(),before);assert.equal(handle.isCurrent(),false);
});
test('a resized or replaced graph invalidates the gesture handle',()=>{
 const f=fixture(),handle=f.handle();f.scroll.clientWidth=80;assert.equal(handle.isCurrent(),false);handle.restore();
 const g=fixture(),next=g.handle();g.svg.firstElementChild={};assert.equal(next.isCurrent(),false);next.restore();
});
test('missing plot fails before any DOM or store mutation',()=>{
 assert.throws(()=>createFullRangeDragPreview({querySelector:()=>null},{trackRole:'primary',assemblyCtgId:1}),TypeError);
});
