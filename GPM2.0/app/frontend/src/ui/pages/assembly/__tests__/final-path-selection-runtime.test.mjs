import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { bindFinalPathSelection, snapshotWithoutFinalPathSelection } from "../final-path-selection-runtime.js";
import { updateFinalPathRow } from "../final-path-runtime.js";
import { syncAssemblyTransientInteractions } from "../../assembly-page.js";
import { rememberAssemblyDom, restoreAssemblyDom, clearAssemblySessionCache } from "../../../shell/assembly-session-cache.js";

const key = name => name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
class Element {
  constructor(doc, attrs = {}) { this.ownerDocument = doc; this.attrs = {}; this.dataset = {}; this.children = []; this.events = new Map(); this.style = {};
    for (const [k, v] of Object.entries(attrs)) this.setAttribute(k, v); }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith("data-")) this.dataset[key(k)] = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  removeAttribute(k) { delete this.attrs[k]; if (k.startsWith("data-")) delete this.dataset[key(k)]; }
  matches(selector) { return selector.split(/,\s*/).some(s => s === "#route-host" ? this.attrs.id === "route-host"
    : s === '[contenteditable]:not([contenteditable="false"])' ? this.getAttribute("contenteditable") !== null && this.getAttribute("contenteditable") !== "false"
    : s === "a[href]" ? this.tag === "a" && this.getAttribute("href") !== null
    : s.startsWith(".") ? (this.attrs.class || "").split(" ").includes(s.slice(1))
    : /^[a-z]+$/.test(s) ? this.tag === s
    : /^\[[^\]]+\]$/.test(s) && this.getAttribute(s.slice(1, -1)) !== null); }
  closest(selector) { return this.matches(selector) ? this : this.parent?.closest(selector) || null; }
  querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  append(child) { child.parent = this; this.children.push(child); }
  get childNodes() { return this.children; }
  getBoundingClientRect() { return this.rect || { left: 0, top: 0, right: 0, bottom: 0 }; }
  replaceChildren(...nodes) { this.children = []; nodes.forEach(node => this.append(node)); }
  remove() { this.parent.children = this.parent.children.filter(child => child !== this); }
  addEventListener(type, fn) { const list = this.events.get(type) || []; list.push(fn); this.events.set(type, list); }
  cloneNode() { const clone = new Element(this.ownerDocument, this.attrs); this.children.forEach(child => clone.append(child.cloneNode(true))); return clone; }
  get outerHTML() { return `<g ${Object.entries(this.attrs).map(([k,v]) => `${k}="${v}"`).join(" ")}>${this.children.map(c => c.outerHTML).join("")}</g>`; }
}
function fixture() {
  const created = [];
  const documentEvents = new Map(), windowEvents = new Map();
  const listen = events => (type, fn) => {
    const list = events.get(type) || []; list.push(fn); events.set(type, list);
  };
  const doc = { addEventListener: listen(documentEvents), defaultView: { addEventListener: listen(windowEvents) }, createElementNS: (_namespace, tag) => {
    const node = new Element(doc); node.tag = tag; created.push(node); return node;
  } };
  doc.body = new Element(doc);
  const host = new Element(doc, { id: "route-host" }); doc.body.append(host);
  const plot = new Element(doc, { "data-final-path-graph-viewport": "" }); host.append(plot);
  const list = new Element(doc, { "data-final-path-card-list": "" }); host.append(list);
  const graph = new Element(doc, { "data-final-path-segment-id": "seg1" }); plot.append(graph);
  const row = new Element(doc, { "data-final-path-segment-id": "seg1" }); list.append(row);
  const input = new Element(doc); input.tag = "input"; row.append(input);
  const makeGroup = (range, local = false) => {
    const node = new Element(doc, { "data-source-interval-projection": JSON.stringify(range),
      [local ? "data-subview-contig-id" : "data-track-contig-id"]: "1",
      [local ? "data-subview-rect-x" : "data-track-rect-x"]: "20",
      [local ? "data-subview-rect-y" : "data-track-rect-y"]: "60",
      [local ? "data-subview-rect-width" : "data-track-rect-width"]: local ? "200" : "100",
      [local ? "data-subview-rect-height" : "data-track-rect-height"]: "14" });
    host.append(node); return node;
  };
  const main = makeGroup({ assemblyCtgId: 1, sourceStart: 1, sourceEnd: 10000, orient: "+" });
  const local = makeGroup({ assemblyCtgId: 1, sourceStart: 4001, sourceEnd: 8000, orient: "-" }, true);
  const other = makeGroup({ assemblyCtgId: 2, sourceStart: 1, sourceEnd: 10000, orient: "+" });
  const segment = { type: "ctg", segmentId: "seg1", assemblyCtgId: 1, datasetName: "Data", ctgName: "ctg1",
    overallLen: 10000, start: 5001, end: 10000 };
  const store = createStore({ activeRoute: "assembly", session: { workspacePath: "workspace", projectId: 7 },
    assembly: { activeTab: "assembly", selectedChrName: "Chr1", trackSelectedCtgIds: [], subview: { trackPairSelectedCtgs: [] },
      finalPathByChr: { Chr1: { mode: "segments", chrName: "Chr1", segments: [segment] } } } });
  bindFinalPathSelection(host, store);
  const fire = (type, target, extra = {}) => {
    for (const events of [documentEvents, host.events]) {
      events.get(type)?.forEach(fn => fn({ type, target, button: 0, pointerId: 1, clientX: 10, clientY: 10, ...extra }));
    }
  };
  const blur = () => windowEvents.get("blur")?.forEach(fn => fn());
  const overlay = node => node.querySelector("[data-final-path-selection-overlay]");
  const patch = value => store.setState({ assembly: { ...store.getState().assembly, ...value } });
  const click = (target, extra = {}) => {
    fire("pointerdown", target, extra); fire("pointerup", target, extra); fire("click", target, extra);
  };
  return { host, plot, list, graph, row, input, main, local, other, store, fire, click, overlay, patch, created, blur };
}

test("graph/table hover paints only adopted Main/Local source intersections", () => {
  const f = fixture(); f.fire("pointerover", f.graph);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.row.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.overlay(f.main).getAttribute("x"), "70");
  assert.equal(f.overlay(f.main).getAttribute("width"), "50");
  assert.equal(f.overlay(f.local).getAttribute("data-source-start"), "5001");
  assert.equal(f.overlay(f.local).getAttribute("data-source-end"), "8000");
  assert.equal(f.overlay(f.local).getAttribute("x"), "20");
  assert.equal(f.overlay(f.local).getAttribute("width"), "150");
  assert.equal(f.overlay(f.other), null);
  assert.deepEqual(f.store.getState().assembly.trackSelectedCtgIds, []);
  assert.deepEqual(f.store.getState().assembly.subview.trackPairSelectedCtgs, []);
});

test("focus selects table row without saving, rerendering, or altering input value", () => {
  const f = fixture(); let notifications = 0; f.store.subscribe(() => notifications++);
  f.input.value = "invalid draft"; f.fire("focusin", f.input);
  assert.equal(f.row.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.input.value, "invalid draft");
  assert.equal(notifications, 0);
});

test("same-context scroll/zoom retains hover and existing overlay nodes", () => {
  const f = fixture(); f.fire("pointerover", f.graph);
  const overlay = f.overlay(f.main);
  f.patch({ trackView: { zoom: 2 }, trackScrollState: { scrollLeft: 300 } });
  bindFinalPathSelection(f.host, f.store);
  assert.equal(f.overlay(f.main), overlay);
  assert.equal(f.host.events.get("pointerover").length, 1);
  assert.equal(f.host.events.get("pointerout").length, 1);
});

test("new Main/Local selection clears correlation without changing editing selections", () => {
  const f = fixture(); f.fire("pointerover", f.graph); f.fire("pointerdown", f.main);
  assert.equal(f.overlay(f.main), null); assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  f.fire("keydown", f.input, { key: "Tab" });
  f.fire("focusin", f.input); f.patch({ subview: { trackPairSelectedCtgs: [{ contigId: 1, trackRole: "primary" }] } });
  assert.equal(f.overlay(f.local), null);
});

test("changing chromosome/project/path or deleting the selected segment clears transient paint", () => {
  for (const change of [f => f.patch({ selectedChrName: "Chr2" }),
    f => f.store.setState({ session: { workspacePath: "workspace", projectId: 8 } }),
    f => f.patch({ activeFinalPathKey: "A" }), f => f.patch({ finalPathByChr: {} })]) {
    const f = fixture(); f.fire("pointerover", f.graph); change(f);
    assert.equal(f.overlay(f.main), null); assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  }
});

test("live export selection is removed only from a clone", () => {
  const f = fixture(); f.fire("pointerover", f.graph);
  const snapshot = snapshotWithoutFinalPathSelection(f.host);
  assert.doesNotMatch(snapshot, /data-final-path-selection-overlay|data-final-path-selected/);
  assert.ok(f.overlay(f.main)); assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
});

test("highlight coordinates update only after successful persisted edits, not focus or invalid input", async () => {
  const f = fixture(); f.fire("focusin", f.input);
  let resolveSave; const pending = new Promise(resolve => { resolveSave = resolve; }); let saves = 0;
  const deps = { persistProjectAssemblyViewState: () => { saves++; return pending; }, rerender() {} };
  await updateFinalPathRow(f.host, f.store, { segmentId: "seg1", field: "start", value: "invalid" }, deps);
  assert.equal(saves, 0); assert.equal(f.overlay(f.main).getAttribute("data-source-start"), "5001");
  const committing = updateFinalPathRow(f.host, f.store, { segmentId: "seg1", field: "start", value: "6001" }, deps);
  assert.equal(saves, 1); assert.equal(f.overlay(f.main).getAttribute("data-source-start"), "5001");
  resolveSave({}); await committing;
  assert.equal(f.overlay(f.main).getAttribute("data-source-start"), "6001");
});


test("path plot background and GAP hover clear only transient correlation", () => {
  const f = fixture(); f.fire("pointerover", f.graph);
  const gap = new Element(f.host.ownerDocument, { "data-final-path-segment-id": "gap" }); f.host.append(gap);
  f.fire("pointerover", gap); assert.equal(f.overlay(f.main), null);
  f.fire("pointerover", f.graph);
  const plot = new Element(f.host.ownerDocument, { class: "assembly-final-path-svg-wrap" }); f.host.append(plot);
  f.fire("pointerdown", plot); assert.equal(f.overlay(f.main), null);
  assert.deepEqual(f.store.getState().assembly.trackSelectedCtgIds, []);
});

test("deleting a phase clears selection even when another path reuses its label/segment IDs", () => {
  const f = fixture(); f.patch({ isChrPhased: true, activeFinalPathKey: "__all__",
    phasedChrTracks: [{ phasedTrackId: 1, label: "Chr1A" }, { phasedTrackId: 2, label: "Chr1B" }],
    finalPathByChr: { Chr1A: f.store.getState().assembly.finalPathByChr.Chr1 } });
  f.graph.setAttribute("data-final-path-target-chr-name", "Chr1A");
  f.fire("pointerover", f.graph); assert.ok(f.overlay(f.main));
  f.patch({ phasedChrTracks: [{ phasedTrackId: 2, label: "Chr1A" }] });
  assert.equal(f.overlay(f.main), null);
});

test("failed persistence keeps the last successfully saved adopted source interval", async () => {
  const f = fixture(); f.fire("focusin", f.input);
  await assert.rejects(updateFinalPathRow(f.host, f.store, { segmentId: "seg1", field: "end", value: "8000" },
    { persistProjectAssemblyViewState: async () => { throw new Error("disk failure"); }, rerender() {} }), /disk failure/);
  assert.equal(f.overlay(f.main).getAttribute("data-source-end"), "10000");
});


test("All mode distinguishes repeated segment IDs by owning path and selects only one instance", () => {
  const f = fixture(); const entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ isChrPhased: true, activeFinalPathKey: "__all__",
    phasedChrTracks: [{ phasedTrackId: 1, label: "Chr1A", haplotypeKey: "A" }, { phasedTrackId: 2, label: "Chr1B", haplotypeKey: "B" }],
    finalPathByChr: { Chr1A: entry, Chr1B: entry } });
  f.graph.setAttribute("data-final-path-target-chr-name", "Chr1A");
  f.row.setAttribute("data-final-path-target-chr-name", "Chr1B");
  f.fire("pointerover", f.graph);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.row.getAttribute("data-final-path-selected"), null);
  f.fire("focusin", f.input);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.row.getAttribute("data-final-path-selected"), "1");
});

test("selection survives a fragment-local DOM replacement by painting the new nodes only", () => {
  const f = fixture(); f.fire("pointerover", f.graph);
  const next = f.main.cloneNode(true); next.querySelector("[data-final-path-selection-overlay]").remove();
  f.main.remove(); f.host.append(next); bindFinalPathSelection(f.host, f.store);
  assert.equal(f.overlay(next).getAttribute("data-source-start"), "5001");
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
});


test("invalidated source coordinates clear selection rather than retaining an obsolete range", () => {
  const f = fixture(); f.fire("pointerover", f.graph);
  const entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ finalPathByChr: { Chr1: { ...entry, segments: [{ ...entry.segments[0], start: 20000 }] } } });
  assert.equal(f.overlay(f.main), null);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
});


test("standalone export restores native source titles only in its cloned SVG", () => {
  const f = fixture(); f.graph.setAttribute("data-final-path-tooltip", "full source identity\nAdopted length: 5,000 bp");
  f.fire("pointerover", f.graph); snapshotWithoutFinalPathSelection(f.host);
  const title = f.created.find(node => node.tag === "title");
  assert.equal(title.textContent, "full source identity\nAdopted length: 5,000 bp");
  assert.notEqual(title.parent, f.graph);
  assert.equal(f.graph.children.length, 0);
  assert.ok(f.overlay(f.main));
});


test("route departure clears hover and never selects non-Assembly previews", () => {
  const f = fixture(); f.fire("pointerover", f.graph);
  f.store.setState({ activeRoute: "overview" });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.overlay(f.main), null);
  f.fire("pointerover", f.graph);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  f.store.setState({ activeRoute: "assembly" });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  f.fire("pointerover", f.graph);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
});


test("restoring cached project DOM reconciles invalidated transient paint immediately", () => {
  clearAssemblySessionCache();
  const f = fixture(); f.fire("pointerover", f.graph);
  const projectA = f.store.getState().session;
  assert.ok(rememberAssemblyDom(f.host, f.store.getState()));
  f.host.replaceChildren(); f.store.setState({ activeRoute: "importer" });
  f.store.setState({ session: { ...projectA, projectId: 8 } });
  f.store.setState({ session: projectA, activeRoute: "assembly" });
  assert.ok(restoreAssemblyDom(f.host, f.store.getState()));
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1", "the cached DOM really contains obsolete paint");
  syncAssemblyTransientInteractions(f.host, f.store);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.overlay(f.main), null);
  clearAssemblySessionCache();
});

test("same-project cached route restoration does not revive an obsolete hover", () => {
  clearAssemblySessionCache();
  const f = fixture(); f.fire("pointerover", f.graph);
  rememberAssemblyDom(f.host, f.store.getState()); f.host.replaceChildren();
  f.store.setState({ activeRoute: "importer" }); f.store.setState({ activeRoute: "assembly" });
  assert.ok(restoreAssemblyDom(f.host, f.store.getState()));
  syncAssemblyTransientInteractions(f.host, f.store);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.overlay(f.main), null);
  f.fire("pointerover", f.graph);
  assert.ok(f.overlay(f.main));
  clearAssemblySessionCache();
});


test("an already-open off-chromosome Local source uses known candidate provenance without inserting a Contig", () => {
  const f = fixture();
  const localRange = { assemblyCtgId: 1, sourceSeqId: 7, sourceStart: 6001, sourceEnd: 10000, orient: "+" };
  f.local.setAttribute("data-source-interval-projection", JSON.stringify(localRange));
  const entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ chrCtgs: [], supportChrCtgs: [], subviewCompositionCandidates: [{ ctg: { assemblyCtgId: 1,
    sourceFragment: { sourceSeqId: 7, sourceStart: 6001, sourceEnd: 10000, sourceLength: 15000 } } }],
    finalPathByChr: { Chr1: { ...entry, segments: [{ ...entry.segments[0], overallLen: 4000, start: 1001, end: 4000 }] } } });
  const existingSubview = f.store.getState().assembly.subview;
  f.fire("pointerover", f.graph);
  assert.equal(f.overlay(f.local).getAttribute("data-source-start"), "7001");
  assert.equal(f.overlay(f.local).getAttribute("data-source-end"), "10000");
  assert.equal(f.store.getState().assembly.subview, existingSubview);
  assert.deepEqual(f.store.getState().assembly.chrCtgs, []);
});


test("leaving graph/table clears all correlation without saving or changing editing selection", () => {
  for (const target of ["graph", "input"]) {
    const f = fixture(); let notifications = 0; f.store.subscribe(() => notifications++);
    f.fire("pointerover", f[target]);
    assert.ok(f.overlay(f.main));
    f.fire("pointerout", f[target], { relatedTarget: f.main });
    assert.equal(f.overlay(f.main), null);
    assert.equal(f.overlay(f.local), null);
    assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
    assert.equal(f.row.getAttribute("data-final-path-selected"), null);
    assert.equal(notifications, 0);
    assert.deepEqual(f.store.getState().assembly.trackSelectedCtgIds, []);
  }
});

test("moving between children of one segment keeps overlays without repainting", () => {
  const f = fixture(); f.fire("pointerover", f.row);
  const overlay = f.overlay(f.main), count = f.created.length;
  f.fire("pointerout", f.row, { relatedTarget: f.input });
  f.fire("pointerover", f.input, { relatedTarget: f.row });
  assert.equal(f.overlay(f.main), overlay);
  assert.equal(f.created.length, count);
});

test("pointer leave, cancellation, drag start and Escape remove transient paint", () => {
  for (const [type, extra] of [["pointerleave", {}], ["pointercancel", {}], ["dragstart", {}], ["keydown", { key: "Escape" }]]) {
    const f = fixture(); f.fire("pointerover", f.graph); f.fire(type, f.host, extra);
    assert.equal(f.overlay(f.main), null);
    assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  }
});

test("pointerdown/touch/field focus alone never pin correlation; keyboard focus remains available", () => {
  const f = fixture();
  f.fire("pointerdown", f.graph);
  assert.equal(f.overlay(f.main), null);
  f.fire("pointerover", f.input);
  f.fire("pointerdown", f.input);
  f.fire("focusin", f.input);
  f.fire("pointerout", f.input);
  assert.equal(f.overlay(f.main), null, "mouse focus must not pin hover after leaving");
  f.fire("pointerover", f.graph, { pointerType: "touch" });
  f.fire("pointerdown", f.input, { pointerType: "touch" });
  f.fire("focusin", f.input);
  assert.equal(f.overlay(f.main), null);
  f.fire("pointerover", f.graph, { buttons: 1 });
  assert.equal(f.overlay(f.main), null, "dragging across a segment must not activate hover");
  f.fire("keydown", f.input, { key: "Tab" });
  f.fire("focusin", f.input);
  assert.ok(f.overlay(f.main));
  f.fire("focusout", f.input);
  assert.equal(f.overlay(f.main), null);
});

test("switching between graph/table targets immediately transfers hover", () => {
  const f = fixture();
  f.fire("pointerover", f.graph);
  f.fire("pointerout", f.graph, { relatedTarget: f.input });
  f.fire("pointerover", f.input, { relatedTarget: f.graph });
  assert.ok(f.overlay(f.main));
  f.fire("pointerout", f.input);
  assert.equal(f.overlay(f.main), null);
});


test("window blur removes hover without reviving it on later state updates", () => {
  const f = fixture(); f.fire("pointerover", f.graph); f.blur();
  assert.equal(f.overlay(f.main), null);
  f.patch({ trackView: { zoom: 3 } });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
});

test("a late leave from another segment cannot clear the current hovered source", () => {
  const f = fixture(), entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ finalPathByChr: { Chr1: { ...entry, segments: [...entry.segments,
    { ...entry.segments[0], segmentId: "seg2", start: 6001 }] } } });
  const second = new Element(f.host.ownerDocument, { "data-final-path-segment-id": "seg2" });
  f.host.append(second);
  f.fire("pointerover", f.graph);
  f.fire("pointerover", second);
  f.fire("pointerout", f.graph);
  assert.equal(second.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.overlay(f.main).getAttribute("data-source-start"), "6001");
});

function addSegment(f, overrides) {
  const entry = f.store.getState().assembly.finalPathByChr.Chr1;
  const segment = { ...entry.segments[0], segmentId: "seg2", ...overrides };
  f.patch({ finalPathByChr: { Chr1: { ...entry, segments: [...entry.segments, segment] } } });
  const graph = new Element(f.host.ownerDocument, { "data-final-path-segment-id": segment.segmentId }); f.plot.append(graph);
  const row = new Element(f.host.ownerDocument, { "data-final-path-segment-id": segment.segmentId }); f.list.append(row);
  return { graph, row, segment };
}
const sourceRanges = node => node.querySelectorAll("[data-final-path-selection-overlay]")
  .map(overlay => [Number(overlay.getAttribute("data-source-start")), Number(overlay.getAttribute("data-source-end"))]);

test("ordinary click pins one instance across graph/table without editing or notifying the store", () => {
  const f = fixture(); let notifications = 0; f.store.subscribe(() => notifications++);
  const state = f.store.getState();
  f.click(f.graph); f.fire("pointerout", f.graph); f.fire("pointerleave", f.host);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.row.getAttribute("data-final-path-selected"), "1");
  assert.ok(f.overlay(f.main)); assert.ok(f.overlay(f.local));
  assert.equal(f.store.getState(), state); assert.equal(notifications, 0);
  assert.deepEqual(state.assembly.trackSelectedCtgIds, []);
  assert.deepEqual(state.assembly.subview.trackPairSelectedCtgs, []);
});

for (const modifier of ["ctrlKey", "metaKey"]) {
  test(`${modifier} + click adds/removes instances and key release does not clear them`, () => {
    const f = fixture(), second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2", start: 1, end: 2000 });
    f.click(f.graph); f.click(second.row, { [modifier]: true });
    f.fire("keyup", f.host, { key: modifier === "ctrlKey" ? "Control" : "Meta" });
    f.fire("pointerleave", f.host);
    assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
    assert.equal(second.graph.getAttribute("data-final-path-selected"), "1");
    assert.ok(f.overlay(f.main)); assert.ok(f.overlay(f.other));
    f.fire("pointerover", f.graph); f.click(f.graph, { [modifier]: true });
    assert.equal(f.graph.getAttribute("data-final-path-selected"), null, "toggle off is immediate, not kept by the same hover");
    assert.equal(f.overlay(f.main), null);
    assert.equal(second.row.getAttribute("data-final-path-selected"), "1");
    f.click(second.graph, { [modifier]: true });
    assert.equal(f.overlay(f.other), null);
  });
}

test("ordinary click replaces multiple pins, while hover only temporarily adds to them", () => {
  const f = fixture(), second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2", start: 1, end: 2000 });
  f.click(f.graph); f.fire("pointerover", second.graph);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(second.graph.getAttribute("data-final-path-selected"), "1");
  f.fire("pointerout", second.graph, { relatedTarget: f.main });
  assert.equal(second.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  f.click(second.row, { ctrlKey: true });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(second.graph.getAttribute("data-final-path-selected"), "1");
  f.click(second.row);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(second.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.overlay(f.main), null); assert.ok(f.overlay(f.other));
});

test("two pieces of one original Contig stay separate, including reversed Local projection", () => {
  const f = fixture();
  const second = addSegment(f, { start: 1001, end: 2000 });
  f.local.setAttribute("data-source-interval-projection", JSON.stringify({ assemblyCtgId: 1, sourceStart: 1, sourceEnd: 10000, orient: "-" }));
  f.click(f.graph); f.click(second.graph, { ctrlKey: true });
  assert.deepEqual(sourceRanges(f.main), [[1001, 2000], [5001, 10000]]);
  assert.deepEqual(sourceRanges(f.local), [[1001, 2000], [5001, 10000]]);
  const localOverlays = f.local.querySelectorAll("[data-final-path-selection-overlay]");
  assert.ok(Math.abs(Number(localOverlays[0].getAttribute("x")) - 180) < 1e-9);
  assert.ok(Math.abs(Number(localOverlays[0].getAttribute("width")) - 20) < 1e-9);
  assert.ok(Math.abs(Number(localOverlays[1].getAttribute("x")) - 20) < 1e-9);
  assert.ok(Math.abs(Number(localOverlays[1].getAttribute("width")) - 100) < 1e-9);
  f.click(second.graph, { ctrlKey: true });
  assert.deepEqual(sourceRanges(f.main), [[5001, 10000]]);
  assert.deepEqual(sourceRanges(f.local), [[5001, 10000]]);
});

for (const [start, end] of [[4001, 7000], [5001, 10000], [1001, 5000]]) {
  test(`overlapping, repeated and adjacent source intervals merge without duplicate paint: ${start}-${end}`, () => {
    const f = fixture(), second = addSegment(f, { start, end });
    f.click(f.graph); f.click(second.graph, { ctrlKey: true });
    assert.deepEqual(sourceRanges(f.main), [[Math.min(start, 5001), 10000]]);
    assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
    assert.equal(second.graph.getAttribute("data-final-path-selected"), "1");
  });
}

test("All mode pins repeated segment IDs independently by their owning paths", () => {
  const f = fixture(), entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ isChrPhased: true, activeFinalPathKey: "__all__",
    phasedChrTracks: [{ phasedTrackId: 1, label: "Chr1A" }, { phasedTrackId: 2, label: "Chr1B" }],
    finalPathByChr: { Chr1A: entry, Chr1B: entry } });
  f.graph.setAttribute("data-final-path-target-chr-name", "Chr1A");
  f.row.setAttribute("data-final-path-target-chr-name", "Chr1B");
  f.click(f.graph); f.click(f.row, { ctrlKey: true });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.row.getAttribute("data-final-path-selected"), "1");
  assert.equal(sourceRanges(f.main).length, 1, "the same adopted source does not get a darker duplicate overlay");
  f.click(f.graph, { ctrlKey: true });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.row.getAttribute("data-final-path-selected"), "1");
});

for (const clear of [f => f.click(f.plot), f => f.click(f.list), f => f.fire("keydown", f.host, { key: "Escape" })]) {
  test(`Final Path background/Escape clears all pins and transient overlays: ${clear}`, () => {
    const f = fixture(), second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2" });
    f.click(f.graph); f.click(second.graph, { metaKey: true }); f.fire("pointerover", f.graph);
    clear(f);
    assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
    assert.equal(second.row.getAttribute("data-final-path-selected"), null);
    assert.equal(f.overlay(f.main), null); assert.equal(f.overlay(f.other), null);
  });
}

test("editing fields, toolbar controls and unrelated blank clicks do not replace or clear pins", () => {
  const f = fixture(), second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2" });
  const before = f.store.getState();
  const field = new Element(f.host.ownerDocument); field.tag = "input"; field.value = "draft"; second.row.append(field);
  f.click(f.graph); f.click(field, { ctrlKey: true });
  f.fire("keydown", field, { key: "Escape" });
  const button = new Element(f.host.ownerDocument); button.tag = "button"; second.row.append(button);
  f.click(button); f.click(f.host); f.click(f.main);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(second.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(field.value, "draft"); assert.equal(f.store.getState(), before);
});

for (const end of ["drag", "cancel", "native-drag", "blur"]) {
  test(`a ${end} gesture cannot pin the hovered segment or replace existing pins`, () => {
    const f = fixture(), second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2" });
    f.click(f.graph); f.fire("pointerdown", second.graph);
    if (end === "drag") {
      f.fire("pointermove", f.host, { clientX: 30 });
      f.fire("pointermove", f.host, { clientX: 10 });
    } else if (end === "cancel") f.fire("pointercancel", second.graph);
    else if (end === "native-drag") f.fire("dragstart", second.graph);
    else f.blur();
    f.fire("pointerup", second.graph); f.fire("click", second.graph);
    assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
    assert.equal(second.graph.getAttribute("data-final-path-selected"), null);
  });
}

test("pinned comparisons survive redraw, scroll/zoom and Main/Local editing selection changes", () => {
  const f = fixture(); f.click(f.graph);
  const overlay = f.overlay(f.main);
  f.patch({ trackView: { zoom: 2 }, trackScrollState: { scrollLeft: 300 }, trackSelectedCtgIds: [2],
    subview: { trackPairSelectedCtgs: [{ contigId: 2, trackRole: "primary" }] } });
  bindFinalPathSelection(f.host, f.store);
  assert.equal(f.overlay(f.main), overlay);
  const next = f.main.cloneNode(true); next.querySelector("[data-final-path-selection-overlay]").remove();
  f.main.remove(); f.host.append(next); bindFinalPathSelection(f.host, f.store);
  assert.ok(f.overlay(next)); assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.deepEqual(f.store.getState().assembly.trackSelectedCtgIds, [2]);
  assert.equal(f.host.events.get("click").length, 1);
});

for (const change of [f => f.patch({ selectedChrName: "Chr2" }),
  f => f.store.setState({ session: { workspacePath: "workspace", projectId: 8 } }),
  f => f.patch({ activeFinalPathKey: "A" }), f => f.store.setState({ activeRoute: "overview" })]) {
  test(`context change clears fixed selection: ${change}`, () => {
    const f = fixture(); f.click(f.graph); change(f);
    assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
    assert.equal(f.overlay(f.main), null);
  });
}

test("deleting/invalidating one pinned segment prunes only that instance", () => {
  const f = fixture(), second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2" });
  f.click(f.graph); f.click(second.graph, { ctrlKey: true });
  const entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ finalPathByChr: { Chr1: { ...entry, segments: [second.segment] } } });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(second.row.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.overlay(f.main), null); assert.ok(f.overlay(f.other));
});

test("export strips every pinned/hover overlay from a clone without altering live pins", () => {
  const f = fixture(), second = addSegment(f, { start: 1001, end: 2000 });
  f.click(f.graph); f.click(second.graph, { ctrlKey: true });
  const count = sourceRanges(f.main).length;
  const snapshot = snapshotWithoutFinalPathSelection(f.host);
  assert.doesNotMatch(snapshot, /data-final-path-selection-overlay|data-final-path-selected/);
  assert.equal(sourceRanges(f.main).length, count);
  f.fire("pointerleave", f.host); assert.equal(sourceRanges(f.main).length, count);
});


test("removing a phase prunes its pins even if another phase reuses the label", () => {
  const f = fixture(), entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ isChrPhased: true, activeFinalPathKey: "__all__",
    phasedChrTracks: [{ phasedTrackId: 1, label: "Chr1A" }, { phasedTrackId: 2, label: "Chr1B" }],
    finalPathByChr: { Chr1A: entry, Chr1B: entry } });
  f.graph.setAttribute("data-final-path-target-chr-name", "Chr1A");
  f.row.setAttribute("data-final-path-target-chr-name", "Chr1B");
  f.click(f.graph); f.click(f.row, { ctrlKey: true });
  f.patch({ phasedChrTracks: [{ phasedTrackId: 2, label: "Chr1A" }] });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.row.getAttribute("data-final-path-selected"), null);
  assert.equal(f.overlay(f.main), null);
});

test("loading may temporarily hide an unresolved pin without reviving invalid ranges", () => {
  const f = fixture(), entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.click(f.graph);
  f.patch({ loading: true, finalPathByChr: {} });
  assert.equal(f.overlay(f.main), null);
  f.patch({ loading: false, finalPathByChr: { Chr1: entry } });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.ok(f.overlay(f.main));
  f.patch({ finalPathByChr: { Chr1: { ...entry, segments: [{ ...entry.segments[0], start: 20000 }] } } });
  assert.equal(f.overlay(f.main), null);
  f.patch({ finalPathByChr: { Chr1: entry } });
  assert.equal(f.overlay(f.main), null, "a proven invalid pin was pruned, not silently restored");
});

test("keyboard focus previews beside pins and Escape inside a field leaves pins alone", () => {
  const f = fixture(), second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2" });
  const field = new Element(f.host.ownerDocument); field.tag = "input"; second.row.append(field);
  f.click(f.graph); f.fire("keydown", field, { key: "Tab" }); f.fire("focusin", field);
  assert.ok(f.overlay(f.main)); assert.ok(f.overlay(f.other));
  f.fire("keydown", field, { key: "Escape" });
  assert.ok(f.overlay(f.main));
  f.fire("focusout", field);
  assert.ok(f.overlay(f.main)); assert.equal(f.overlay(f.other), null);
});

test("a click on a different target after pointerdown cannot select or clear the wrong instance", () => {
  const f = fixture(), second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2" });
  f.click(f.graph); f.fire("pointerdown", second.graph); f.fire("click", f.plot);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(second.graph.getAttribute("data-final-path-selected"), null);
  f.fire("pointerdown", f.plot); f.fire("click", second.graph);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(second.graph.getAttribute("data-final-path-selected"), null);
});


test("Escape on a non-editing button clears pins, but an already-handled Escape does not", () => {
  const f = fixture();
  const button = new Element(f.host.ownerDocument); button.tag = "button"; f.host.append(button);
  f.click(f.graph); f.fire("keydown", button, { key: "Escape", defaultPrevented: true });
  assert.ok(f.overlay(f.main));
  f.fire("keydown", button, { key: "Escape" });
  assert.equal(f.overlay(f.main), null);
});

function boxFixture() {
  const f = fixture(), second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2", start: 1, end: 2000 });
  const doc = f.host.ownerDocument;
  doc.createElement = tag => { const node = new Element(doc); node.tag = tag; return node; };
  f.plot.rect = f.list.rect = { left: 0, top: 0, right: 500, bottom: 200 };
  f.graph.rect = f.row.rect = { left: 30, top: 40, right: 100, bottom: 60 };
  second.graph.rect = second.row.rect = { left: 160, top: 40, right: 230, bottom: 60 };
  const boxes = () => f.host.ownerDocument.body.querySelectorAll(".final-path-selection-box");
  const box = (surface = f.plot, modifier = "ctrlKey", start = [10, 20], end = [250, 80]) => {
    f.fire("pointerdown", surface, { [modifier]: true, clientX: start[0], clientY: start[1] });
    f.fire("pointermove", surface, { clientX: end[0], clientY: end[1] });
    f.fire("pointerup", surface, { clientX: end[0], clientY: end[1] });
    f.fire("click", surface, { clientX: end[0], clientY: end[1] });
  };
  return { ...f, second, boxes, box };
}

for (const mode of ["plot", "list"]) for (const modifier of ["ctrlKey", "metaKey"]) {
  test(`${modifier} blank box in ${mode} adds intersecting instances without editing or persistence`, () => {
    const f = boxFixture(), state = f.store.getState(); let writes = 0;
    f.store.subscribe(() => writes++);
    f.box(f[mode], modifier);
    for (const node of [f.graph, f.row, f.second.graph, f.second.row]) assert.equal(node.getAttribute("data-final-path-selected"), "1");
    assert.ok(f.overlay(f.main)); assert.ok(f.overlay(f.other));
    assert.equal(f.store.getState(), state); assert.equal(writes, 0); assert.equal(f.boxes().length, 0);
    assert.deepEqual(state.assembly.trackSelectedCtgIds, []);
    assert.deepEqual(state.assembly.subview.trackPairSelectedCtgs, []);
  });
}

test("box preview is screen-space, clipped, reversible and absent from snapshot exports", () => {
  const f = boxFixture();
  f.fire("pointerdown", f.plot, { ctrlKey: true, clientX: 250, clientY: 80 });
  f.fire("pointermove", f.plot, { clientX: -100, clientY: -20 });
  assert.equal(f.boxes().length, 1);
  assert.deepEqual(f.boxes()[0].style, { left: "0px", top: "0px", width: "250px", height: "80px" });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null, "preview does not commit pins");
  assert.doesNotMatch(snapshotWithoutFinalPathSelection(f.host), /final-path-selection-box/);
  f.fire("pointerup", f.plot, { clientX: -100, clientY: -20 });
  f.fire("click", f.plot);
  assert.equal(f.second.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.boxes().length, 0);
});

test("boxes add rather than toggle existing pins, ignore GAPs and do not include a neighboring surface", () => {
  const f = boxFixture(), gap = addSegment(f, { type: "gap", segmentId: "gap" });
  gap.graph.rect = { left: 110, top: 40, right: 130, bottom: 60 };
  const outside = addSegment(f, { segmentId: "outside" });
  outside.row.rect = { left: 30, top: 40, right: 100, bottom: 60 };
  outside.graph.rect = { left: 600, top: 40, right: 700, bottom: 60 };
  f.click(f.graph);
  f.box(); f.box();
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.second.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(gap.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(outside.row.getAttribute("data-final-path-selected"), null);
});

for (const end of ["pointercancel", "blur", "lostpointercapture", "scroll", "loading", "scope", "removed", "Escape"]) {
  test(`${end} cancels box and cleans its overlay without adding instances`, () => {
    const f = boxFixture(); f.click(f.graph);
    f.fire("pointerdown", f.plot, { ctrlKey: true, clientX: 120, clientY: 20 });
    f.fire("pointermove", f.plot, { clientX: 250, clientY: 80 });
    assert.equal(f.boxes().length, 1);
    if (end === "blur") f.blur();
    else if (end === "loading") f.patch({ loading: true });
    else if (end === "scope") f.patch({ selectedChrName: "Chr2" });
    else if (end === "removed") { f.plot.isConnected = false; f.patch({}); }
    else if (end === "Escape") f.fire("keydown", f.host, { key: "Escape" });
    else f.fire(end, f.plot);
    f.fire("pointerup", f.plot, { clientX: 250, clientY: 80 }); f.fire("click", f.plot);
    assert.equal(f.second.graph.getAttribute("data-final-path-selected"), null);
    assert.equal(f.boxes().length, 0);
    assert.equal(f.host.dataset.finalPathBoxSelecting, undefined);
    if (end !== "scope") assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  });
}

for (const extra of [{}, { ctrlKey: true, altKey: true }, { ctrlKey: true, button: 2 }, { ctrlKey: true, pointerType: "touch" }]) {
  test(`unmodified/unsupported blank drag does not start a correlation box: ${JSON.stringify(extra)}`, () => {
    const f = boxFixture();
    f.fire("pointerdown", f.plot, { ...extra, clientX: 10, clientY: 20 });
    f.fire("pointermove", f.plot, { clientX: 250, clientY: 80 });
    f.fire("pointerup", f.plot, { clientX: 250, clientY: 80 });
    assert.equal(f.boxes().length, 0); assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  });
}

test("segment/control-origin drags and another pointer cannot acquire or finish the box", () => {
  const f = boxFixture();
  for (const target of [f.graph, f.input]) {
    f.fire("pointerdown", target, { ctrlKey: true });
    f.fire("pointermove", f.plot, { clientX: 250, clientY: 80 });
    assert.equal(f.boxes().length, 0);
    f.fire("pointerup", f.plot, { clientX: 250, clientY: 80 });
  }
  f.fire("pointerdown", f.plot, { ctrlKey: true, clientX: 120, clientY: 20 });
  f.fire("pointerdown", f.plot, { pointerId: 2, ctrlKey: true, clientX: 10, clientY: 20 });
  f.fire("pointermove", f.plot, { pointerId: 2, clientX: 250, clientY: 80 });
  assert.equal(f.boxes().length, 0);
  f.fire("pointermove", f.plot, { clientX: 250, clientY: 80 });
  f.fire("pointerup", f.plot, { pointerId: 2, clientX: 250, clientY: 80 });
  assert.equal(f.boxes().length, 1); assert.equal(f.second.graph.getAttribute("data-final-path-selected"), null);
  f.fire("pointerup", f.plot, { clientX: 250, clientY: 80 });
  assert.equal(f.second.graph.getAttribute("data-final-path-selected"), "1");
});

test("All-mode boxes distinguish equal segment IDs by path and never widen adopted source intervals", () => {
  const f = boxFixture(), original = f.store.getState().assembly.finalPathByChr.Chr1.segments[0];
  f.patch({ activeFinalPathKey: "__all__", phasedChrTracks: [{ phasedTrackId: 1, label: "Chr1A" }, { phasedTrackId: 2, label: "Chr1B" }],
    finalPathByChr: { Chr1A: { segments: [original] }, Chr1B: { segments: [{ ...original, start: 1001, end: 2000 }] } } });
  for (const node of [f.graph, f.row]) node.setAttribute("data-final-path-target-chr-name", "Chr1A");
  for (const node of [f.second.graph, f.second.row]) {
    node.setAttribute("data-final-path-target-chr-name", "Chr1B"); node.setAttribute("data-final-path-segment-id", original.segmentId);
  }
  f.box();
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.second.graph.getAttribute("data-final-path-selected"), "1");
  assert.deepEqual(sourceRanges(f.main), [[1001, 2000], [5001, 10000]]);
  assert.deepEqual(sourceRanges(f.local), [[5001, 8000]]);
});

test("Escape from an earlier focused field cancels only the active box, then normal Escape clears pins", () => {
  const f = boxFixture(); f.click(f.graph);
  f.fire("pointerdown", f.plot, { ctrlKey: true, clientX: 120, clientY: 20 });
  f.fire("pointermove", f.plot, { clientX: 250, clientY: 80 });
  f.fire("keydown", f.input, { key: "Escape" });
  assert.equal(f.boxes().length, 0);
  f.fire("pointerup", f.plot, { clientX: 250, clientY: 80 });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.second.graph.getAttribute("data-final-path-selected"), null);
  f.fire("keydown", f.host, { key: "Escape" });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
});
