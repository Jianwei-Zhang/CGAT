import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { bindFinalPathSelection, unbindFinalPathSelection, snapshotWithoutFinalPathSelection } from "../final-path-selection-runtime.js";
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
  get classList() { return {
    remove: (...tokens) => this.setAttribute("class", (this.getAttribute("class") || "").split(/\s+/).filter(token => !tokens.includes(token)).join(" ")),
    contains: token => (this.getAttribute("class") || "").split(/\s+/).includes(token),
  }; }
  removeEventListener(type, fn) { this.events.set(type, (this.events.get(type) || []).filter(item => item !== fn)); }
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
  doc.removeEventListener = (type, fn) => documentEvents.set(type, (documentEvents.get(type) || []).filter(item => item !== fn));
  doc.defaultView.removeEventListener = (type, fn) => windowEvents.set(type, (windowEvents.get(type) || []).filter(item => item !== fn));
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

test("new Local editing selection replaces transient Final Path correlation with reverse correlation", () => {
  const f = fixture(); f.fire("pointerover", f.graph); f.fire("pointerdown", f.main);
  assert.equal(f.overlay(f.main), null); assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  f.fire("keydown", f.input, { key: "Tab" });
  f.fire("focusin", f.input); f.patch({ subview: { trackPairSelectedCtgs: [{ contigId: 1, trackRole: "primary" }] } });
  assert.equal(f.overlay(f.local).getAttribute("data-source-start"), "4001");
  assert.equal(f.graph.getAttribute("data-final-path-correlated"), "1");
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
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
  f.click(button); f.click(f.host);
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


function resultBar(f) {
  const bar = new Element(f.host.ownerDocument, { class: "track-ctg", x: "10", y: "20", width: "100", height: "14" });
  f.graph.append(bar);
  return bar;
}

function peerView(f) {
  const peer = fixture();
  unbindFinalPathSelection(peer.host, peer.store);
  peer.host.replaceChildren(peer.local);
  let localSelection = [];
  let alive = true;
  const scoped = { localViewRootStore: f.store, isLocalViewAlive: () => alive,
    getState: () => ({ ...f.store.getState(), assembly: { ...f.store.getState().assembly,
      subview: { trackPairSelectedCtgs: localSelection } } }) };
  bindFinalPathSelection(peer.host, scoped);
  return { ...peer, scoped, setSelection(entries) { localSelection = entries; f.patch({}); },
    close() { alive = false; unbindFinalPathSelection(peer.host, scoped); } };
}

test("Main hover correlates matching Local ranges and adopted results without store writes", () => {
  const f = fixture(); resultBar(f);
  const before = structuredClone(f.store.getState()); let notifications = 0;
  f.store.subscribe(() => notifications++);
  f.fire("pointerover", f.main);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.graph.getAttribute("data-final-path-correlated"), "1");
  assert.equal(f.overlay(f.graph).getAttribute("width"), "100");
  assert.equal(f.overlay(f.local).getAttribute("data-source-start"), "4001");
  assert.equal(f.overlay(f.other), null);
  assert.deepEqual(f.store.getState(), before); assert.equal(notifications, 0);
  f.fire("pointerout", f.main);
  assert.equal(f.overlay(f.graph), null); assert.equal(f.overlay(f.local), null);
});

test("Local hover highlights only the overlap within each Final Path instance", () => {
  const f = fixture(); resultBar(f);
  f.fire("pointerover", f.local);
  assert.equal(f.overlay(f.graph).getAttribute("data-source-start"), "5001");
  assert.equal(f.overlay(f.graph).getAttribute("data-source-end"), "8000");
  assert.equal(f.overlay(f.graph).getAttribute("width"), "60");
  assert.equal(f.overlay(f.main).getAttribute("data-source-start"), "4001");
  assert.equal(f.overlay(f.main).getAttribute("data-source-end"), "8000");
  assert.equal(f.row.getAttribute("data-final-path-correlated"), "1");
  f.fire("pointerout", f.local);
  assert.equal(f.row.getAttribute("data-final-path-correlated"), null);
});

test("opposite Final Path orientation reverses the partial result overlay", () => {
  const f = fixture(); resultBar(f);
  const path = structuredClone(f.store.getState().assembly.finalPathByChr);
  Object.assign(path.Chr1.segments[0], { start: 10000, end: 5001 });
  f.patch({ finalPathByChr: path }); f.fire("pointerover", f.local);
  assert.equal(f.overlay(f.graph).getAttribute("x"), "50");
  assert.equal(f.overlay(f.graph).getAttribute("width"), "60");
});

test("a Local source outside adopted coordinates cannot light the result", () => {
  const f = fixture(); resultBar(f);
  f.local.setAttribute("data-source-interval-projection", JSON.stringify({ assemblyCtgId: 1, sourceStart: 1, sourceEnd: 2000 }));
  f.fire("pointerover", f.local);
  assert.equal(f.graph.getAttribute("data-final-path-correlated"), null);
  assert.equal(f.overlay(f.graph), null);
  assert.equal(f.overlay(f.main).getAttribute("data-source-end"), "2000");
});

test("selected Main and Local sources maintain reverse correlation after hover leaves", () => {
  const f = fixture(); resultBar(f);
  f.patch({ trackSelectedCtgIds: [1] });
  assert.equal(f.overlay(f.graph).getAttribute("width"), "100");
  f.fire("pointerover", f.other); f.fire("pointerout", f.other);
  assert.ok(f.overlay(f.graph));
  f.patch({ trackSelectedCtgIds: [], subview: { trackPairSelectedCtgs: [{ contigId: 1, trackRole: "primary" }] } });
  assert.equal(f.overlay(f.graph).getAttribute("width"), "60");
  f.patch({ subview: { trackPairSelectedCtgs: [] } });
  assert.equal(f.overlay(f.graph), null);
});

test("multiple native documents share Final Path hover, pins, and reverse source hover", () => {
  const f = fixture(); resultBar(f);
  const a = peerView(f), b = peerView(f);
  f.fire("pointerover", f.graph);
  assert.equal(a.overlay(a.local).getAttribute("data-source-start"), "5001");
  assert.equal(b.overlay(b.local).getAttribute("data-source-end"), "8000");
  f.click(f.graph); f.blur();
  assert.ok(a.overlay(a.local));
  f.fire("keydown", f.host, { key: "Escape" });
  assert.equal(a.overlay(a.local), null);
  a.fire("pointerover", a.local);
  assert.equal(f.overlay(f.graph).getAttribute("width"), "60");
  assert.equal(b.overlay(b.local).getAttribute("data-source-start"), "4001");
  // A delayed leave from Main must not erase the peer's newer hover.
  f.fire("pointerleave", f.host);
  assert.ok(f.overlay(f.graph));
  a.fire("pointerout", a.local);
  assert.equal(f.overlay(f.graph), null);
  a.close(); b.close();
});

test("native selections and rerenders repaint without taking ownership from Main", () => {
  const f = fixture(); resultBar(f); const peer = peerView(f);
  peer.setSelection([{ contigId: 1, trackRole: "primary" }]);
  assert.equal(f.overlay(f.graph).getAttribute("width"), "60");
  const next = peer.local.cloneNode(true); peer.local.remove(); peer.host.append(next);
  bindFinalPathSelection(peer.host, peer.scoped);
  assert.ok(f.overlay(next));
  f.fire("pointerover", f.graph);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  peer.close(); f.fire("pointerout", f.graph);
  assert.equal(f.overlay(f.graph), null);
  assert.equal(peer.host.events.get("pointerover").length, 0);
});

test("Local viewport clipping applies source orientation before reverse matching", () => {
  const f = fixture(); resultBar(f);
  const viewport = new Element(f.host.ownerDocument, { class: "subview-track-scroll" });
  viewport.rect = { left: 100, right: 200, top: 0, bottom: 100 };
  f.local.remove(); f.host.append(viewport); viewport.append(f.local);
  const bar = new Element(f.host.ownerDocument, { class: "track-ctg" });
  bar.rect = { left: 0, right: 200, top: 0, bottom: 14 }; f.local.append(bar);
  // Right half of a reverse 4001..8000 source corresponds to 4001..6000.
  f.fire("pointerover", f.local);
  assert.equal(f.overlay(f.graph).getAttribute("data-source-start"), "5001");
  assert.equal(f.overlay(f.graph).getAttribute("data-source-end"), "6000");
  assert.equal(f.overlay(f.graph).getAttribute("width"), "20");
  viewport.rect = { left: 150, right: 200, top: 0, bottom: 100 };
  f.fire("scroll", viewport);
  assert.equal(f.overlay(f.graph), null);
});

test("export strips reverse-correlation paint from a clone only", () => {
  const f = fixture(); resultBar(f); f.fire("pointerover", f.local);
  assert.doesNotMatch(snapshotWithoutFinalPathSelection(f.host), /data-final-path-correlated|data-final-path-selection-overlay/);
  assert.ok(f.overlay(f.graph));
});


test("source sequence identity prevents cross-dataset name collisions during reverse hover", () => {
  const f = fixture(); resultBar(f);
  f.patch({ chrCtgs: [{ assemblyCtgId: 1, originSourceSeqId: 7 }] });
  f.local.setAttribute("data-source-interval-projection", JSON.stringify({ assemblyCtgId: 1,
    sourceSeqId: 8, sourceStart: 4001, sourceEnd: 8000, datasetName: "Data", contigName: "ctg1" }));
  f.fire("pointerover", f.local);
  assert.equal(f.overlay(f.graph), null);
});

test("merged Local provenance can reverse-match a constituent Final Path contig", () => {
  const f = fixture(); resultBar(f);
  f.local.setAttribute("data-source-interval-projection", JSON.stringify({ sourceStart: 4001, sourceEnd: 8000,
    parts: [{ assemblyCtgId: 1 }], orient: "+" }));
  f.fire("pointerover", f.local);
  assert.equal(f.overlay(f.graph).getAttribute("width"), "60");
});

test("all paths keep reverse correlations scoped by identity and source overlap", () => {
  const f = fixture(); resultBar(f);
  const second = f.graph.cloneNode(true); second.setAttribute("data-final-path-target-chr-name", "Chr2"); f.plot.append(second);
  const base = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ finalPathByChr: { Chr1: base, Chr2: { ...base, segments: [{ ...base.segments[0], start: 1, end: 2000 }] } } });
  f.fire("pointerover", f.local);
  assert.ok(f.overlay(f.graph)); assert.equal(f.overlay(second), null);
});

test("inactive open Local windows supply split provenance, closed windows do not", () => {
  const f = fixture(); resultBar(f);
  const entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ finalPathByChr: { Chr1: { ...entry, segments: [{ ...entry.segments[0], overallLen: 4000, start: 1001, end: 4000 }] } },
    subviewWorkspace: { windows: [{ id: "peer", opened: true, snapshot: { subview: { summary: { mode: "composition", members: [
      { assemblyCtgId: 1, sourceFragment: { sourceSeqId: 7, sourceStart: 6001, sourceEnd: 10000 } },
    ] } } } }] } });
  f.fire("pointerover", f.graph);
  assert.equal(f.overlay(f.local).getAttribute("data-source-start"), "7001");
});

test("leaving Assembly or switching scope clears reverse correlation in every document", () => {
  for (const change of [f => f.store.setState({ activeRoute: "importer" }),
    f => f.patch({ selectedChrName: "Chr2" }), f => f.store.setState({ session: { projectId: 8, workspacePath: "other" } })]) {
    const f = fixture(); resultBar(f); const peer = peerView(f);
    peer.fire("pointerover", peer.local); assert.ok(f.overlay(f.graph));
    change(f);
    assert.equal(f.overlay(f.graph), null); assert.equal(f.overlay(f.main), null);
    assert.equal(peer.overlay(peer.local), null); peer.close();
  }
});


for (const source of ["main", "local"]) {
  test(`${source} plain click pins a source independently and a second click cancels immediately`, () => {
    const f = fixture(); resultBar(f); const before = structuredClone(f.store.getState());
    f.fire("pointerover", f[source]); f.click(f[source]); f.fire("pointerout", f[source]);
    assert.ok(f.overlay(f.graph)); assert.ok(f.overlay(f.main)); assert.ok(f.overlay(f.local));
    f.blur(); assert.ok(f.overlay(f.graph));
    f.fire("pointerover", f[source]); f.click(f[source]);
    assert.equal(f.overlay(f.graph), null); assert.equal(f.overlay(f.local), null);
    assert.deepEqual(f.store.getState(), before);
  });
}

test("Shift-click adds and toggles source pins without borrowing Ctrl comparisons", () => {
  const f = fixture(); resultBar(f); const second = addSegment(f, { assemblyCtgId: 2, ctgName: "ctg2" });
  f.click(f.main); f.click(f.other, { shiftKey: true });
  assert.equal(f.graph.getAttribute("data-final-path-correlated"), "1");
  assert.equal(second.graph.getAttribute("data-final-path-correlated"), "1");
  f.click(f.other, { shiftKey: true });
  assert.equal(second.graph.getAttribute("data-final-path-correlated"), null);
  assert.ok(f.overlay(f.graph));
  f.click(f.other);
  assert.equal(f.graph.getAttribute("data-final-path-correlated"), null);
  assert.equal(second.graph.getAttribute("data-final-path-correlated"), "1");
});

for (const modifier of ["ctrlKey", "metaKey", "altKey"]) {
  test(`${modifier} source clicks stay with the existing gesture owner`, () => {
    const f = fixture(); resultBar(f);
    f.click(f.main, { [modifier]: true }); f.fire("pointerout", f.main);
    assert.equal(f.overlay(f.graph), null);
    f.click(f.local); f.click(f.main, { [modifier]: true });
    assert.equal(f.overlay(f.graph).getAttribute("width"), "60");
  });
}

for (const clear of ["blank-main", "blank-local", "blank-result", "escape"]) {
  test(`${clear} clears source pins and does not resurrect unchanged edit-box selections`, () => {
    const f = fixture(); resultBar(f);
    f.patch({ selectedCtgId: 1, trackSelectedCtgIds: [1], subview: { trackPairSelectedCtgs: [{ contigId: 1, trackRole: "primary" }] } });
    f.click(f.local);
    if (clear === "escape") f.fire("keydown", f.host, { key: "Escape" });
    else if (clear === "blank-result") f.click(f.plot);
    else {
      const blank = new Element(f.host.ownerDocument, { class: "assembly-track-scroll", "data-track-role": clear === "blank-local" ? "subview" : "primary" });
      f.host.append(blank); f.click(blank);
    }
    assert.equal(f.overlay(f.graph), null);
    f.patch({ trackView: { zoom: 2 } }); bindFinalPathSelection(f.host, f.store);
    assert.equal(f.overlay(f.graph), null); assert.equal(f.overlay(f.local), null);
    assert.equal(f.store.getState().assembly.selectedCtgId, clear === "escape" ? null : 1);
    assert.deepEqual(f.store.getState().assembly.trackSelectedCtgIds, clear === "escape" ? [] : [1]);
  });
}

test("canceling a source pin also masks an old matching editing selection", () => {
  const f = fixture(); resultBar(f); f.patch({ trackSelectedCtgIds: [1] });
  f.click(f.main); f.click(f.main); f.patch({});
  assert.equal(f.overlay(f.graph), null);
  f.fire("pointerover", f.local); assert.ok(f.overlay(f.graph));
  f.fire("pointerout", f.local); assert.equal(f.overlay(f.graph), null);
  f.patch({ trackSelectedCtgIds: [] }); f.patch({ trackSelectedCtgIds: [1] });
  assert.ok(f.overlay(f.graph));
});

test("a stale navigation focus alone never becomes persistent source correlation", () => {
  const f = fixture(); resultBar(f); f.patch({ selectedCtgId: 1 });
  assert.equal(f.overlay(f.graph), null);
  f.fire("pointerover", f.main); f.fire("pointerout", f.main);
  assert.equal(f.overlay(f.graph), null);
});

for (const end of ["drag", "cancel", "blur", "scope"]) {
  test(`source ${end} cannot accidentally pin on the resulting click`, () => {
    const f = fixture(); resultBar(f); f.fire("pointerdown", f.main);
    if (end === "drag") f.fire("pointermove", f.main, { clientX: 13 });
    if (end === "cancel") f.fire("pointercancel", f.main);
    if (end === "blur") f.blur();
    if (end === "scope") f.patch({ selectedChrName: "Chr2" });
    f.fire("pointerup", f.main); f.fire("click", f.main);
    assert.equal(f.overlay(f.graph), null);
  });
}

test("source pins survive same-context rerender but not the originating native window closing", () => {
  const f = fixture(); resultBar(f); const peer = peerView(f);
  peer.click(peer.local); peer.fire("pointerout", peer.local);
  const next = peer.local.cloneNode(true); peer.local.remove(); peer.host.append(next);
  bindFinalPathSelection(peer.host, peer.scoped);
  assert.equal(f.overlay(f.graph).getAttribute("width"), "60");
  peer.fire("keydown", peer.host, { key: "Escape" });
  assert.equal(f.overlay(f.graph), null);
  peer.click(next); assert.ok(f.overlay(f.graph));
  peer.close(); assert.equal(f.overlay(f.graph), null);
});

test("starting an existing Ctrl blank-box gesture neither consumes the event nor creates a pin", () => {
  const f = fixture(); resultBar(f);
  const blank = new Element(f.host.ownerDocument, { class: "assembly-track-scroll", "data-track-role": "primary" });
  f.host.append(blank); let consumed = false;
  f.fire("pointerdown", blank, { ctrlKey: true, preventDefault() { consumed = true; }, stopImmediatePropagation() { consumed = true; } });
  assert.equal(consumed, false);
  f.patch({ trackSelectedCtgIds: [1] });
  f.fire("pointerup", blank, { ctrlKey: true }); f.fire("click", blank, { ctrlKey: true });
  assert.ok(f.overlay(f.graph));
  f.patch({ trackSelectedCtgIds: [] }); assert.equal(f.overlay(f.graph), null);
});


test("late Main blur cannot cancel a newer native Local source click or blank cancel", () => {
  const f = fixture(); resultBar(f); const peer = peerView(f);
  peer.fire("pointerdown", peer.local); f.blur(); peer.fire("pointerup", peer.local); peer.fire("click", peer.local);
  assert.equal(f.overlay(f.graph).getAttribute("width"), "60");
  const blank = new Element(peer.host.ownerDocument, { class: "assembly-track-scroll" }); peer.host.append(blank);
  peer.fire("pointerdown", blank); f.blur(); peer.fire("pointerup", blank); peer.fire("click", blank);
  assert.equal(f.overlay(f.graph), null); peer.close();
});

test("a new unchanged Ctrl box can re-enable a previously dismissed edit selection", () => {
  const f = fixture(); resultBar(f);
  const blank = new Element(f.host.ownerDocument, { class: "assembly-track-scroll" }); f.host.append(blank);
  f.patch({ trackSelectedCtgIds: [1] }); f.fire("keydown", f.host, { key: "Escape" });
  assert.equal(f.overlay(f.graph), null);
  // A new box selection is still allowed after Escape clears the old one.
  f.patch({ trackSelectedCtgIds: [1] });
  f.fire("pointerdown", blank, { ctrlKey: true }); f.fire("pointerup", blank, { ctrlKey: true }); f.fire("click", blank, { ctrlKey: true });
  assert.ok(f.overlay(f.graph));
});


test("Escape clears blue Main/Local edit paint and state, including inactive Local snapshots", () => {
  const f = fixture(); resultBar(f); const peer = peerView(f);
  const summary = { mode: "composition", members: [{ assemblyCtgId: 1 }] };
  const snapshot = { subview: { summary, trackPairSelectedCtgs: [{ contigId: 1, trackRole: "primary" }] }, subviewTrackView: { zoom: 2 } };
  const path = f.store.getState().assembly.finalPathByChr;
  const offsets = [{ assemblyCtgId: 1, offsetBp: 40 }];
  f.patch({ selectedCtgId: 1, trackSelectedCtgIds: [1], selectedDeletedCtgRecordIds: [3], trackDragOffsets: offsets,
    subview: snapshot.subview, subviewWorkspace: { generation: 1, activeId: "a", windows: [
      { id: "a", opened: true, snapshot }, { id: "b", opened: false, snapshot },
    ] } });
  const groups = [f.main, f.local, peer.local];
  for (const node of groups) {
    node.setAttribute("class", "track-ctg-group is-active is-multi-selected");
    const bar = new Element(node.ownerDocument, { class: "track-ctg is-active is-multi-selected" }); node.append(bar);
  }
  peer.fire("keydown", peer.host, { key: "Escape" });
  const assembly = f.store.getState().assembly;
  assert.equal(assembly.selectedCtgId, null);
  assert.deepEqual(assembly.trackSelectedCtgIds, []);
  assert.deepEqual(assembly.selectedDeletedCtgRecordIds, []);
  assert.deepEqual(assembly.subview.trackPairSelectedCtgs, []);
  for (const item of assembly.subviewWorkspace.windows) {
    assert.deepEqual(item.snapshot.subview.trackPairSelectedCtgs, []);
    assert.equal(item.snapshot.subview.summary, summary);
    assert.equal(item.snapshot.subviewTrackView, snapshot.subviewTrackView);
  }
  for (const node of groups) {
    assert.equal(node.classList.contains("is-multi-selected"), false);
    assert.equal(node.classList.contains("is-active"), false);
    assert.equal(node.querySelector(".track-ctg").classList.contains("is-multi-selected"), false);
  }
  assert.equal(assembly.finalPathByChr, path); assert.equal(assembly.trackDragOffsets, offsets);
  assert.equal(f.overlay(f.main), null); assert.equal(f.overlay(f.graph), null);
  f.patch({ trackView: { zoom: 3 } });
  assert.deepEqual(f.store.getState().assembly.trackSelectedCtgIds, []);
  peer.close();
});

test("Escape inside an editable field or dialog and outside Assembly leaves edit selections alone", () => {
  for (const mode of ["input", "dialog", "route", "tab", "handled"]) {
    const f = fixture(); f.patch({ selectedCtgId: 1, trackSelectedCtgIds: [1] });
    const dialog = new Element(f.host.ownerDocument); dialog.tag = "dialog"; f.host.append(dialog);
    if (mode === "route") f.store.setState({ activeRoute: "importer" });
    if (mode === "tab") f.patch({ activeTab: "check-new-sequences" });
    f.fire("keydown", mode === "input" ? f.input : mode === "dialog" ? dialog : f.host,
      { key: "Escape", defaultPrevented: mode === "handled" });
    assert.deepEqual(f.store.getState().assembly.trackSelectedCtgIds, [1]);
    assert.equal(f.store.getState().assembly.selectedCtgId, 1);
  }
});
