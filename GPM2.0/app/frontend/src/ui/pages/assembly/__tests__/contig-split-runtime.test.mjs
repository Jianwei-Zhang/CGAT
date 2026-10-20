import test from "node:test";
import assert from "node:assert/strict";
import { openContigSplitDialog } from "../contig-split-runtime.js";

// Event-level harness only; not a browser/native visual acceptance test.
function harness() {
  const nodes = new Map(); let dialog;
  const node = (attrs = {}) => ({
    dataset: Object.fromEntries(Object.entries(attrs).filter(([k]) => k.startsWith("data-")).map(([k,v]) => [k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase()), v])),
    value: "", style: {}, innerHTML: "", textContent: "", disabled: false,
    getAttribute: (k) => attrs[k] ?? null, hasAttribute: (k) => k in attrs,
    setAttribute: (k,v) => { attrs[k] = v; }, closest() { return this; }, focus() {},
    getBoundingClientRect: () => ({ left: 0, width: 1000 }),
  });
  const doc = {
    activeElement: null,
    body: { append: (value) => { dialog = value; } },
    querySelector: () => dialog && !dialog.removed ? dialog : null,
    createElement: () => {
      const listeners = new Map();
      const d = node();
      Object.assign(d, {
        querySelector: (selector) => {
          if (!nodes.has(selector)) nodes.set(selector, node({ [selector.slice(1,-1)]: "" }));
          return nodes.get(selector);
        },
        querySelectorAll: (selector) => selector === "[data-split-mode]"
          ? ["manual", "boundary", "recommended"].map((m) => node({ "data-split-mode": m })) : [...nodes.values()],
        addEventListener: (type, handler) => { listeners.set(type, handler); },
        async fire(type, target, extra = {}) { return listeners.get(type)?.({ target, preventDefault() {}, ...extra }); },
        showModal() { this.open = true; }, close() { this.open = false; }, remove() { this.removed = true; },
      });
      return d;
    },
  };
  const state = { locale: "en", session: { workspacePath: "D:/ws", projectId: 1 }, assembly: { selectedChrName: "A" } };
  return { host: { ownerDocument: doc }, store: { getState: () => state }, state, node,
    dialog: () => dialog, el: (name) => dialog.querySelector(`[data-split-${name}]`) };
}
function evidence(cuts = []) {
  const ranges = cuts.length ? [[1,cuts[0]],[cuts[0]+1,1000]] : [[1,1000]];
  return { source: { name: "tig", sourceStart: 1, sourceEnd: 1000, orient: "-", assignedChrName: "A" },
    hits: [{ chrName: "B", queryStart: 501, queryEnd: 1000, refStart: 10, refEnd: 509, mapq: 60 }],
    cutAfter: cuts, previewToken: `token:${cuts}`, finalPathReferenceCount: 1,
    recommendations: [{ cutAfter: [500], regionStart: 500, regionEnd: 501, kind: "boundary", leftChr: "A", rightChr: "B" }],
    parts: ranges.map(([a,b],i) => ({ sourceStart:a, sourceEnd:b, length:b-a+1, candidates:[{ chrName:i ? "B":"A", highQualityCoveragePercent:100, coveragePercent:100, identityPercent:99, minMapq:60, orient:"-", refStart:1, refEnd:b-a+1 }] })),
  };
}
const tick = () => new Promise((resolve) => setImmediate(resolve));

test("recommended split previews evidence and commits explicit assignments with the token", async () => {
  const h = harness(); const calls = [];
  const done = openContigSplitDialog(h.host,h.store,{assemblyCtgId:6,mode:"recommended"},{preview:async ({cutAfter})=>evidence(cutAfter),commit:async (p)=>calls.push(p)});
  await tick();
  await h.dialog().fire("click", h.node({ "data-split-recommendation":"0" }));
  await h.dialog().fire("change", { ...h.node({ "data-split-assignment":"1" }), value:"" });
  await h.dialog().fire("click", h.el("confirm"));
  assert.equal(await done,true);
  assert.deepEqual(calls[0].args,{assemblyCtgId:6,cutAfter:[500],assignments:["A",null],previewToken:"token:500",reason:"recommended"});
  assert.equal(h.dialog().removed,true);
});

test("manual coordinate edits disable confirmation until a matching preview arrives", async () => {
  const h = harness(); const calls = [];
  const done=openContigSplitDialog(h.host,h.store,{assemblyCtgId:6},{preview:async ({cutAfter})=>evidence(cutAfter),commit:async (p)=>calls.push(p)});
  await tick(); h.el("cuts").value="600";
  await h.dialog().fire("input",h.el("cuts"));
  assert.equal(h.el("confirm").disabled,true);
  await h.dialog().fire("click",h.el("confirm")); assert.equal(calls.length,0);
  await h.dialog().fire("click",h.el("refresh"));
  await h.dialog().fire("click",h.el("confirm"));
  assert.equal(await done,true);assert.deepEqual(calls[0].args.cutAfter,[600]);assert.equal(calls[0].args.reason,"manual");
});

test("alignment endpoint shortcut uses its source cut and records boundary provenance", async () => {
  const h=harness();let committed;
  const done=openContigSplitDialog(h.host,h.store,{assemblyCtgId:6},{preview:async ({cutAfter})=>evidence(cutAfter),commit:async (p)=>{committed=p;}});
  await tick();await h.dialog().fire("click",h.node({"data-split-cut":"500"}));
  await h.dialog().fire("click",h.el("confirm"));await done;
  assert.equal(committed.args.reason,"alignment-boundary");
});

test("closing a pending read prevents late preview publication and never mutates", async () => {
  const h=harness();let resolvePreview;let writes=0;
  const done=openContigSplitDialog(h.host,h.store,{assemblyCtgId:6},{preview:()=>new Promise((resolve)=>{resolvePreview=resolve;}),commit:async ()=>{writes++;}});
  await h.dialog().fire("cancel",h.el("cancel"));assert.equal(await done,false);
  resolvePreview(evidence());await tick();assert.equal(writes,0);assert.equal(h.dialog().removed,true);
});

test("project switches and backend failures do not become successful commits", async () => {
  const h=harness();let writes=0;
  const done=openContigSplitDialog(h.host,h.store,{assemblyCtgId:6},{preview:async ({cutAfter})=>evidence(cutAfter),commit:async ()=>{writes++;throw new Error("stale evidence");}});
  await tick();await h.dialog().fire("click",h.el("confirm"));
  assert.equal(h.dialog().removed,undefined);assert.match(h.el("error").textContent,/stale evidence/);
  await h.dialog().fire("click",h.el("refresh"));h.state.session.projectId=2;
  await h.dialog().fire("click",h.el("confirm"));assert.equal(writes,1);
  await h.dialog().fire("click",h.el("cancel"));assert.equal(await done,false);
});

test("recommended entry cannot silently confirm an arbitrary midpoint before choosing evidence", async () => {
  const h=harness();let writes=0;
  const done=openContigSplitDialog(h.host,h.store,{assemblyCtgId:6,mode:"recommended"},{preview:async ({cutAfter})=>evidence(cutAfter),commit:async ()=>{writes++;}});
  await tick();assert.equal(h.el("cuts").value,"");assert.equal(h.el("confirm").disabled,true);
  await h.dialog().fire("click",h.el("confirm"));assert.equal(writes,0);
  await h.dialog().fire("click",h.el("cancel"));assert.equal(await done,false);
});
