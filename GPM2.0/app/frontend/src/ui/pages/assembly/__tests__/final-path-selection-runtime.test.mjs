import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { bindFinalPathSelection, snapshotWithoutFinalPathSelection } from "../final-path-selection-runtime.js";
import { updateFinalPathRow } from "../final-path-runtime.js";
import { syncAssemblyTransientInteractions } from "../../assembly-page.js";
import { rememberAssemblyDom, restoreAssemblyDom, clearAssemblySessionCache } from "../../../shell/assembly-session-cache.js";

const key = name => name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
class Element {
  constructor(doc, attrs = {}) { this.ownerDocument = doc; this.attrs = {}; this.dataset = {}; this.children = []; this.events = new Map();
    for (const [k, v] of Object.entries(attrs)) this.setAttribute(k, v); }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith("data-")) this.dataset[key(k)] = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  removeAttribute(k) { delete this.attrs[k]; if (k.startsWith("data-")) delete this.dataset[key(k)]; }
  matches(selector) { return selector.split(", ").some(s => s === "#route-host" ? this.attrs.id === "route-host"
    : s.startsWith(".") ? (this.attrs.class || "").split(" ").includes(s.slice(1))
    : /^\[[^\]]+\]$/.test(s) && this.getAttribute(s.slice(1, -1)) !== null); }
  closest(selector) { return this.matches(selector) ? this : this.parent?.closest(selector) || null; }
  querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  append(child) { child.parent = this; this.children.push(child); }
  get childNodes() { return this.children; }
  replaceChildren(...nodes) { this.children = []; nodes.forEach(node => this.append(node)); }
  remove() { this.parent.children = this.parent.children.filter(child => child !== this); }
  addEventListener(type, fn) { const list = this.events.get(type) || []; list.push(fn); this.events.set(type, list); }
  cloneNode() { const clone = new Element(this.ownerDocument, this.attrs); this.children.forEach(child => clone.append(child.cloneNode(true))); return clone; }
  get outerHTML() { return `<g ${Object.entries(this.attrs).map(([k,v]) => `${k}="${v}"`).join(" ")}>${this.children.map(c => c.outerHTML).join("")}</g>`; }
}
function fixture() {
  const created = [];
  const doc = { createElementNS: (_namespace, tag) => {
    const node = new Element(doc); node.tag = tag; created.push(node); return node;
  } };
  const host = new Element(doc, { id: "route-host" });
  const graph = new Element(doc, { "data-final-path-segment-id": "seg1" }); host.append(graph);
  const row = new Element(doc, { "data-final-path-segment-id": "seg1" }); host.append(row);
  const input = new Element(doc); row.append(input);
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
  const fire = (type, target, extra = {}) => host.events.get(type)?.forEach(fn => fn({ type, target, button: 0, ...extra }));
  const overlay = node => node.querySelector("[data-final-path-selection-overlay]");
  const patch = value => store.setState({ assembly: { ...store.getState().assembly, ...value } });
  return { host, graph, row, input, main, local, other, store, fire, overlay, patch, created };
}

test("graph/table single selection paints only adopted Main/Local source intersections", () => {
  const f = fixture(); f.fire("pointerdown", f.graph);
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

test("same-context route/scroll/zoom retains selection and existing overlay nodes", () => {
  const f = fixture(); f.fire("pointerdown", f.graph);
  f.store.setState({ activeRoute: "importer" }); f.store.setState({ activeRoute: "assembly" });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  const overlay = f.overlay(f.main);
  f.patch({ trackView: { zoom: 2 }, trackScrollState: { scrollLeft: 300 } });
  bindFinalPathSelection(f.host, f.store);
  assert.equal(f.overlay(f.main), overlay);
  assert.equal(f.host.events.get("pointerdown").length, 1);
});

test("new Main/Local selection clears correlation without changing editing selections", () => {
  const f = fixture(); f.fire("pointerdown", f.graph); f.fire("pointerdown", f.main);
  assert.equal(f.overlay(f.main), null); assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  f.fire("focusin", f.input); f.patch({ subview: { trackPairSelectedCtgs: [{ contigId: 1, trackRole: "primary" }] } });
  assert.equal(f.overlay(f.local), null);
});

test("changing chromosome/project/path or deleting the selected segment clears transient paint", () => {
  for (const change of [f => f.patch({ selectedChrName: "Chr2" }),
    f => f.store.setState({ session: { workspacePath: "workspace", projectId: 8 } }),
    f => f.patch({ activeFinalPathKey: "A" }), f => f.patch({ finalPathByChr: {} })]) {
    const f = fixture(); f.fire("pointerdown", f.graph); change(f);
    assert.equal(f.overlay(f.main), null); assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  }
});

test("live export selection is removed only from a clone", () => {
  const f = fixture(); f.fire("pointerdown", f.graph);
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


test("path plot background clears only transient correlation, GAP/hover do not select Contigs", () => {
  const f = fixture(); f.fire("pointerdown", f.graph);
  const gap = new Element(f.host.ownerDocument, { "data-final-path-segment-id": "gap" }); f.host.append(gap);
  f.fire("pointerdown", gap); assert.ok(f.overlay(f.main));
  const plot = new Element(f.host.ownerDocument, { class: "assembly-final-path-svg-wrap" }); f.host.append(plot);
  f.fire("pointerdown", plot); assert.equal(f.overlay(f.main), null);
  assert.deepEqual(f.store.getState().assembly.trackSelectedCtgIds, []);
});

test("deleting a phase clears selection even when another path reuses its label/segment IDs", () => {
  const f = fixture(); f.patch({ isChrPhased: true, activeFinalPathKey: "__all__",
    phasedChrTracks: [{ phasedTrackId: 1, label: "Chr1A" }, { phasedTrackId: 2, label: "Chr1B" }],
    finalPathByChr: { Chr1A: f.store.getState().assembly.finalPathByChr.Chr1 } });
  f.graph.setAttribute("data-final-path-target-chr-name", "Chr1A");
  f.fire("pointerdown", f.graph); assert.ok(f.overlay(f.main));
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
  f.fire("pointerdown", f.graph);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
  assert.equal(f.row.getAttribute("data-final-path-selected"), null);
  f.fire("focusin", f.input);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.row.getAttribute("data-final-path-selected"), "1");
});

test("selection survives a fragment-local DOM replacement by painting the new nodes only", () => {
  const f = fixture(); f.fire("pointerdown", f.graph);
  const next = f.main.cloneNode(true); next.querySelector("[data-final-path-selection-overlay]").remove();
  f.main.remove(); f.host.append(next); bindFinalPathSelection(f.host, f.store);
  assert.equal(f.overlay(next).getAttribute("data-source-start"), "5001");
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
});


test("invalidated source coordinates clear selection rather than retaining an obsolete range", () => {
  const f = fixture(); f.fire("pointerdown", f.graph);
  const entry = f.store.getState().assembly.finalPathByChr.Chr1;
  f.patch({ finalPathByChr: { Chr1: { ...entry, segments: [{ ...entry.segments[0], start: 20000 }] } } });
  assert.equal(f.overlay(f.main), null);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
});


test("standalone export restores native source titles only in its cloned SVG", () => {
  const f = fixture(); f.graph.setAttribute("data-final-path-tooltip", "full source identity\nAdopted length: 5,000 bp");
  f.fire("pointerdown", f.graph); snapshotWithoutFinalPathSelection(f.host);
  const title = f.created.find(node => node.tag === "title");
  assert.equal(title.textContent, "full source identity\nAdopted length: 5,000 bp");
  assert.notEqual(title.parent, f.graph);
  assert.equal(f.graph.children.length, 0);
  assert.ok(f.overlay(f.main));
});


test("route departure retains the descriptor but never paints or selects non-Assembly previews", () => {
  const f = fixture(); f.fire("pointerdown", f.graph);
  f.store.setState({ activeRoute: "overview" });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  assert.equal(f.overlay(f.main), null);
  f.fire("pointerdown", f.graph);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), null);
  f.store.setState({ activeRoute: "assembly" });
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
});


test("restoring cached project DOM reconciles invalidated transient paint immediately", () => {
  clearAssemblySessionCache();
  const f = fixture(); f.fire("pointerdown", f.graph);
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

test("same-project cached route restoration retains the valid source selection", () => {
  clearAssemblySessionCache();
  const f = fixture(); f.fire("pointerdown", f.graph);
  rememberAssemblyDom(f.host, f.store.getState()); f.host.replaceChildren();
  f.store.setState({ activeRoute: "importer" }); f.store.setState({ activeRoute: "assembly" });
  assert.ok(restoreAssemblyDom(f.host, f.store.getState()));
  syncAssemblyTransientInteractions(f.host, f.store);
  assert.equal(f.graph.getAttribute("data-final-path-selected"), "1");
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
  f.fire("pointerdown", f.graph);
  assert.equal(f.overlay(f.local).getAttribute("data-source-start"), "7001");
  assert.equal(f.overlay(f.local).getAttribute("data-source-end"), "10000");
  assert.equal(f.store.getState().assembly.subview, existingSubview);
  assert.deepEqual(f.store.getState().assembly.chrCtgs, []);
});
