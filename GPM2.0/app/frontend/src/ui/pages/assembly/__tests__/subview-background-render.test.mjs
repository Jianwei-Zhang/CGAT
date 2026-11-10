import test from "node:test";
import assert from "node:assert/strict";
import { Worker as NodeWorker } from "node:worker_threads";
import { splitSubviewRenderMarkup, buildSubviewRenderDelta, applySubviewRenderDelta } from "../subview-render-packet.js";
import { createSubviewBackgroundRenderer, prepareSubviewRenderPacket, retireSubviewDragProxies } from "../subview-background-render.js";
import { renderSubviewInWorker } from "../subview-render-worker.js";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { __testRenderAssemblySubviewPanel, __testRenderAssemblyMainMembersPanel, renderAssemblyPage } from "../../assembly-page.js";
import { getAppSettings, setAppSettings } from "../../../../services/app-settings.js";
const expand = packet => packet.skeleton.replace(/<g data-subview-render-batch="(\d+)"><\/g>/g, (_, i) => packet.batches[Number(i)]);
const canonical = text => text.replace(/>\s+</g, "><").trim();
const tick = () => new Promise(resolve => setImmediate(resolve));

test("batch packet preserves complete geometry, order, clips and provenance; active anchors stay in the skeleton", () => {
  const primitives = Array.from({ length: 11004 }, (_, i) => `<polygon class="track-collinearity-band" data-subview-hit-key="${i}" points="1,2 3,2 4,6 5,6"/>`);
  const html = `<svg><defs><clipPath id="test"><rect width="10"/></clipPath></defs><g data-subview-anchor-metadata="1" data-subview-anchor-top-name="a &amp; b">${primitives.join("\n")}<line class="subview-anchor-hit-zone is-active" data-subview-anchor-kind="evidence"/></g><text>complete label</text></svg>`;
  const packet = splitSubviewRenderMarkup(html, 192);
  assert.equal(canonical(expand(packet)), canonical(html));
  assert.equal(packet.batches.length, Math.ceil(11004 / 192));
  assert.match(packet.skeleton, /subview-anchor-hit-zone is-active/);
  assert.match(packet.skeleton, /data-subview-anchor-top-name="a &amp; b"/);
  assert.equal(packet.batches.reduce((n, batch) => n + (batch.match(/<polygon/g) || []).length, 0), 11004);
});

for (const mode of ["2-contig", "track-pair", "composition"]) test(`worker renderer matches authoritative ${mode} markup and font/locale settings`, () => {
  const previous = getAppSettings();
  try {
    const state = createIdentityRenderState(mode); state.locale = "en"; state.assembly.subviewTrackView.fullRange = true;
    const settings = { ...previous, graphFontSize: 16 }; setAppSettings(settings, { persist: false });
    const expected = __testRenderAssemblySubviewPanel(state);
    const packet = renderSubviewInWorker(structuredClone(state), { settings, widths: { primary:1200,subview:1200,finalPath:1200 } });
    assert.equal(canonical(expand(packet)), canonical(expected));
  } finally { setAppSettings(previous, { persist: false }); }
});

test("render deltas retain all unchanged hit arrays, carry edits/removals, and never detach live evidence", () => {
  const state = createIdentityRenderState(), before = structuredClone(state);
  const first = buildSubviewRenderDelta(state, null);
  assert.equal(first.assembly.subview, state.assembly.subview);
  const next = { ...state, assembly: { ...state.assembly, subviewTrackDragOffsets: [{slot:"top",contigId:30,offsetBp:-2000}] } };
  delete next.assembly.deletedCtgs;
  const delta = buildSubviewRenderDelta(next, state);
  assert.equal(Object.hasOwn(delta.assembly, "subview"), false);
  assert.equal(Object.hasOwn(delta.assembly, "deletedCtgs"), true);
  const applied = applySubviewRenderDelta(applySubviewRenderDelta(null, first), delta);
  assert.deepEqual(applied.assembly.subviewTrackDragOffsets, next.assembly.subviewTrackDragOffsets);
  assert.equal(applied.assembly.subview, state.assembly.subview);
  assert.deepEqual(state, before);
});

function workerFixture() {
  const workers = [];
  const renderer = createSubviewBackgroundRenderer({ yieldTask: async () => {}, createWorker() {
    const worker = { sent: [], postMessage(message) { this.sent.push(message); }, terminate() { this.terminated = true; }, emit(data) { this.onmessage({data}); } };
    workers.push(worker); return worker;
  } });
  return { renderer, workers };
}
test("completed worker is reused with lightweight deltas; stale results are discarded and their bitmap is closed", async () => {
  const f = workerFixture(), state = createIdentityRenderState();
  const first = f.renderer.render(state, {}, () => true); await tick();
  f.workers[0].emit({ id:f.workers[0].sent[0].id, packet:{skeleton:"first",batches:[]} }); assert.equal((await first).skeleton, "first");
  const next = { ...state, assembly: { ...state.assembly, subviewTrackDragOffsets:[1] } };
  let valid = true;
  const second = f.renderer.render(next, {}, () => valid); await tick();
  assert.equal(f.workers.length, 1); assert.deepEqual(Object.keys(f.workers[0].sent[1].delta.assembly), ["subviewTrackDragOffsets"]);
  let closed = 0; valid = false;
  f.workers[0].emit({ id:f.workers[0].sent[1].id, packet:{rasters:[{bitmap:{close(){closed++;}}}]} });
  assert.equal(await second, null); assert.equal(closed, 1); f.renderer.cancel();
});
test("a newer job cancels the old worker and old replies cannot complete the new request", async () => {
  const f=workerFixture(), state=createIdentityRenderState();
  const old=f.renderer.render(state,{},()=>true); await tick();
  const next=f.renderer.render(state,{},()=>true); await tick();
  assert.equal(await old,null);assert.equal(f.workers[0].terminated,true);
  let closed=0;f.workers[0].emit({id:f.workers[0].sent[0].id,packet:{rasters:[{bitmap:{close(){closed++;}}}]}});
  assert.equal(closed,1);
  f.workers[1].emit({id:f.workers[1].sent[0].id,packet:{skeleton:"current"}});assert.equal((await next).skeleton,"current");f.renderer.cancel();
});
test("worker failures are observable, terminate the cache and leave the next request able to start cleanly",async()=>{
  const f=workerFixture(), pending=f.renderer.render(createIdentityRenderState(),{},()=>true);await tick();
  f.workers[0].onerror({message:"worker crashed",preventDefault(){}});
  await assert.rejects(pending,/worker crashed/);assert.equal(f.workers[0].terminated,true);
  const next=f.renderer.render(createIdentityRenderState(),{},()=>true);await tick();assert.equal(f.workers.length,2);
  f.renderer.cancel();assert.equal(await next,null);
});

test("DOM hydration yields between bounded batches and cancels before touching a newer graph",async()=>{
  const hydrated=[],slots=Array.from({length:3},(_,i)=>({getAttribute:()=>String(i),set innerHTML(value){hydrated.push(value);}}));
  const content={querySelectorAll:()=>slots},document={createElement:()=>({content,set innerHTML(_value){}})};
  let valid=true,yields=0,skeleton=false;
  const result=await prepareSubviewRenderPacket(document,{skeleton:"<svg/>",batches:["a","b","c"]},()=>valid,{onSkeleton(){skeleton=true;},yieldTask:async()=>{assert.equal(skeleton,true);if(++yields===2)valid=false;}});
  assert.equal(result,null);assert.deepEqual(hydrated,["a"]);
});
test("proxy retirement is bounded, cancellable, and excludes active anchor endpoints",async()=>{
  const removed=[],scroll={querySelectorAll(selector){assert.match(selector,/:not\(\.is-active\)/);return Array.from({length:5},(_,i)=>({remove(){removed.push(i);}}));}};
  let valid=true,yields=0;
  assert.equal(await retireSubviewDragProxies(scroll,()=>valid,{batchSize:2,yieldTask:async()=>{if(++yields===3)valid=false;}}),false);
  assert.deepEqual(removed,[0,1,2,3]);
});

test("production worker renders off-thread and accepts an offset-only follow-up without dropping evidence",async()=>{
  const url=new URL("../subview-render-worker.js",import.meta.url).href;
  const worker=new NodeWorker(`const {parentPort}=require('node:worker_threads');globalThis.self={postMessage:(value,transfer)=>parentPort.postMessage(value,transfer)};(async()=>{await import(${JSON.stringify(url)});parentPort.on('message',data=>self.onmessage({data}));parentPort.postMessage({ready:true});})().catch(error=>{throw error});`,{eval:true});
  const message=()=>new Promise((resolve,reject)=>{worker.once("message",resolve);worker.once("error",reject);});
  try {
    await message();const state=createIdentityRenderState();const reply=message();worker.postMessage({id:1,delta:buildSubviewRenderDelta(state,null),settings:getAppSettings(),widths:{subview:1200}});
    const first=await reply;assert.equal(first.id,1);assert.ok(first.packet.batches.length>0);
    const next={...state,assembly:{...state.assembly,subviewTrackDragOffsets:[{slot:"top",contigId:30,offsetBp:1000}]}};
    const secondReply=message();worker.postMessage({id:2,delta:buildSubviewRenderDelta(next,state),settings:getAppSettings(),widths:{subview:1200}});
    const second=await secondReply;assert.equal(second.id,2);assert.notEqual(expand(first.packet),expand(second.packet));
    assert.equal((expand(first.packet).match(/data-track-band-proxy=/g)||[]).length,(expand(second.packet).match(/data-track-band-proxy=/g)||[]).length);
  } finally { await worker.terminate(); }
});

test("legacy member-only refresh retains its markup without visiting alignment evidence", () => {
  const state = createIdentityRenderState();
  state.assembly.membersPanelOpen = true;
  state.assembly.trackSelectedCtgIds = [2];
  const page = renderAssemblyPage(state);
  assert.doesNotMatch(page, /data-members-card-toggle/);
  const expected = __testRenderAssemblyMainMembersPanel(state);
  for (const ctg of [...state.assembly.chrCtgs, ...state.assembly.supportChrCtgs]) {
    Object.defineProperty(ctg, "hits", { get() { throw new Error("must not render the Main alignment graph"); } });
  }
  assert.equal(canonical(__testRenderAssemblyMainMembersPanel(state)), canonical(expected));
});
