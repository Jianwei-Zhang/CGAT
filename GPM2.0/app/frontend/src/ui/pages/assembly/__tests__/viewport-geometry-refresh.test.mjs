import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { refreshViewportGeometry } from "../viewport-geometry-refresh.js";

function fixture() {
  const events = [], old = new Map(), next = new Map(), header = {}, input = { value: "uncommitted" }, panel = { scrollTop: 65 }, tableEditor = {};
  const selectors = [".assembly-track-unified .assembly-track-layout:not(.subview-track-layout)", ".subview-track-layout", "[data-final-path-graph-viewport]"];
  for (const selector of selectors) {
    const incoming = { selector }; next.set(selector, incoming);
    old.set(selector, { replaceWith(node) { assert.equal(node, incoming); old.set(selector, node); events.push(["replace", selector]); } });
  }
  let state = { activeRoute: "assembly", assembly: { loading: false, subviewCompositionViewport: { leftBp: -1000, bpPerPx: 20 } } };
  const root = { header, input, panel, tableEditor, ownerDocument: { createElement: () => ({ content: { querySelector: selector => next.get(selector) } }) }, querySelector: selector => old.get(selector) };
  const store = { getState: () => state, setState: value => { state = value; } };
  const deps = { resolveRouteHost: () => root, renderPage(current) { assert.equal(current, state); events.push(["render", current.assembly.subviewCompositionViewport]); return "geometry"; },
    bindGraph(node, currentStore, scope) { assert.equal(currentStore, store); events.push(["bind", scope]); },
    syncViewport(current) { assert.equal(current, root); events.push(["viewport"]); return false; },
    syncInteractions(current) { assert.equal(current, root); events.push(["sync"]); } };
  return { root, store, deps, events, input, panel, header, tableEditor, old, next };
}

test("viewport refresh only replaces plot layouts and rebinds each graph before navigation/highlight sync", () => {
  const f = fixture(); refreshViewportGeometry(f.root, f.store, f.deps);
  assert.deepEqual(f.events.map(e => e[0]), ["render", "replace", "replace", "replace", "viewport", "bind", "bind", "bind", "sync"]);
  assert.deepEqual(f.events.filter(e => e[0] === "bind").map(e => e[1]), ["main", "subview", "final-path"]);
  for (const name of ["header", "input", "panel", "tableEditor"]) assert.equal(f.root[name], f[name]);
  assert.equal(f.input.value, "uncommitted"); assert.equal(f.panel.scrollTop, 65);
});

test("resizing another route or temporary loading shell does not rebuild or publish Assembly DOM", () => {
  for (const patch of [{ activeRoute: "importer" }, { assembly: { loading: true } }]) {
    const f = fixture(); f.store.setState({ ...f.store.getState(), ...patch });
    refreshViewportGeometry(f.root, f.store, f.deps); assert.deepEqual(f.events, []);
  }
});

test("production viewport controller explicitly uses graph refresh rather than full route rerender", () => {
  const source = readFileSync(new URL("../../assembly-page.js", import.meta.url), "utf8");
  const wiring = source.slice(source.indexOf("} = createAssemblyViewportController({"), source.indexOf("const renderTracksDeps ="));
  assert.match(wiring, /refreshViewportGeometry:.*refreshAssemblyViewportGeometry/);
  assert.doesNotMatch(wiring, /rerender:/);
  const refresh = readFileSync(new URL("../viewport-geometry-refresh.js", import.meta.url), "utf8");
  assert.doesNotMatch(refresh, /root\.innerHTML|assembly-track-unified["']|subview-panel-head|replaceChildren/);
});

test("All-mode resize refreshes every Final Path graph by path identity across shrink/grow, not only the first slot", () => {
  let width = 1000, current = [], incoming = [];
  const make = (name, graphWidth, left = 0) => ({ name, graphWidth, scrollLeft: left, scrollTop: 0,
    closest: () => ({ dataset: { finalPathAllCard: name } }),
    replaceWith(next) { current[current.indexOf(this)] = next; } });
  current = [make("Chr01A", 1000, 120), make("Chr01B", 1000, 240)];
  const root = { ownerDocument: { createElement: () => ({ content: {
    querySelectorAll: selector => selector === "[data-final-path-graph-viewport]" ? incoming : [], querySelector: () => null } }) },
    querySelectorAll: selector => selector === "[data-final-path-graph-viewport]" ? current : [], querySelector: () => null };
  const store = { getState: () => ({ activeRoute: "assembly", assembly: {} }) }, bound = [];
  const deps = { resolveRouteHost: () => root, renderPage() { incoming = [make("Chr01B", width), make("Chr01A", width)]; return "all graphs"; },
    syncViewport() { assert.deepEqual(current.map(n => n.graphWidth), [width, width], "both graphs must have the new geometry before any global synchronization"); return false; },
    bindGraph(node, _store, scope) { assert.equal(scope, "final-path"); bound.push(node.name); }, syncInteractions() {} };
  for (width of [500, 1200]) {
    refreshViewportGeometry(root, store, deps);
    assert.deepEqual(current.map(n => n.name), ["Chr01A", "Chr01B"]);
    assert.deepEqual(current.map(n => n.graphWidth), [width, width]);
    assert.deepEqual(current.map(n => n.scrollLeft), [120, 240]);
  }
  assert.deepEqual(bound, ["Chr01A", "Chr01B", "Chr01A", "Chr01B"]);
});
