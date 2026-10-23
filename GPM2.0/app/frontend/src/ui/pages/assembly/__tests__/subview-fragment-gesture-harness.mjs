import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { resolveSubviewTrackDragOffsetBp } from "../render-tracks.js";
import { splitLocalMember } from "../subview-fragment-model.js";
import { projectRenderedSubviewToComposition } from "../subview-composition-controller.js";
import { bindSubviewTrackContigDrag } from "../track-drag-runtime.js";
import { bindTrackBoxSelection } from "../track-selection-runtime.js";
import { applySubviewComposition, getSubviewComposition } from "../subview-composition-state.js";
import { moveSubviewCompositionDrag, setSubviewDragGroupOffsets } from "../source-fragment-drag.js";
import { commitSubviewHistoryOperation } from "../subview-history-state.js";

const attrs = (tag) => Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map((match) => [match[1], match[2].replaceAll("&amp;", "&").replaceAll("&quot;", '"')]));
function eventBus() {
  const listeners = new Map();
  return { listeners,
    addEventListener(name, callback) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(callback); },
    removeEventListener(name, callback) { listeners.get(name)?.delete(callback); },
    emit(name, event) { for (const callback of [...(listeners.get(name) || [])]) callback(event); },
  };
}
export function gestureHarness(mode, { fullRange = false, flipped = false } = {}) {
  let state = createIdentityRenderState(mode);
  state.session = { workspacePath: "D:/fixture", projectId: 7 };
  state.assembly.subviewTrackView = { ...state.assembly.subviewTrackView, fullRange, allowSubViewportScale: true, visibleSpanBp: 16000 };
  state.assembly.subview.activeAnchors = [{ hitKey: "evidence-1", edge: "left" }, { hitKey: "evidence-1", edge: "right" }];
  if (mode === "composition") state.assembly.subview.summary.members.find((m) => m.assemblyCtgId === 30).flipped = flipped;
  else state.assembly.subview.flippedCtgs = flipped ? [{ slot: "top", contigId: 30 }] : [];
  const store = { getState: () => state, setState: (patch) => { state = { ...state, ...patch }; } };
  const host = eventBus(), win = eventBus(); let scene;
  const frames = new Map(); let frame = 0;
  win.requestAnimationFrame = (callback) => { frames.set(++frame, callback); return frame; };
  win.cancelAnimationFrame = (id) => frames.delete(id);
  win.flush = () => { const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach((callback) => callback()); };
  host.closest = (selector) => selector === "#route-host" ? host : null;
  host.querySelector = (selector) => selector === ".subview-track-scroll" ? scene.scroll : null;
  host.querySelectorAll = (selector) => selector.includes("data-subview-fragment-key") ? scene.fragments
    : selector.includes("data-subview-anchor-kind") ? scene.anchors
      : selector.includes("data-subview-composition-entity-key") ? scene.groups.filter((node) => node.getAttribute("data-subview-composition-entity-key")) : scene.groups;
  function render() {
    const html = renderAssemblyPage(state);
    const scrollTag = [...html.matchAll(/<div[^>]*data-subview-domain-span-bp="[^>]*>/g)][0]?.[0];
    assert.ok(scrollTag, "Local View remains rendered");
    const data = attrs(scrollTag), dataset = Object.fromEntries(Object.entries(data).filter(([key]) => key.startsWith("data-")).map(([key, value]) => [key.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase()), value]));
    const box = { style: {}, classList: { add() {}, remove() {} } };
    const scroll = { dataset, clientWidth: 1200, scrollWidth: 1600, scrollLeft: scene?.scroll.scrollLeft || 0, scrollTop: 0,
      getBoundingClientRect: () => ({ left: 0, top: 0 }),
      getAttribute: (key) => key === "data-track-role" ? "subview" : data[key] ?? null,
      closest: (selector) => selector === "#route-host" ? host : null,
      querySelector: (selector) => selector === ".track-selection-box" ? box : null,
      querySelectorAll: (selector) => host.querySelectorAll(selector),
    };
    const node = (tag, kind) => {
      const values = attrs(tag);
      const current = { values, getAttribute: (key) => values[key] ?? null,
        closest(selector) {
          if (selector === "#route-host") return host;
          if (selector.includes("assembly-track-scroll")) return scroll;
          if (selector.includes("data-view-interaction-mode")) return null;
          if (selector.includes("data-subview-fragment-key")) return kind === "fragment" ? current : null;
          if (selector.includes("data-subview-contig-id")) {
            if (kind === "group") return current;
            return groups.find((group) => group.getAttribute("data-subview-contig-id") === values["data-subview-fragment-contig-id"]
              && group.getAttribute("data-subview-track-slot") === values["data-subview-fragment-slot"]
              && (!values["data-subview-fragment-entity-key"] || group.getAttribute("data-subview-composition-entity-key") === values["data-subview-fragment-entity-key"]));
          }
          return null;
        } };
      return current;
    };
    const groups = [...html.matchAll(/<g\b[^>]*data-subview-contig-id="[^>]*>/g)].map((match) => node(match[0], "group"));
    const fragments = [...html.matchAll(/<rect\b[^>]*class="subview-fragment-hit-zone"[^>]*>/g)].map((match) => node(match[0], "fragment"));
    const anchors = [...html.matchAll(/<[^>]*data-subview-anchor-object-id="[^>]*>/g)].map((match) => node(match[0], "anchor"));
    scene = { scroll, groups, fragments, anchors, html };
  }
  render();
  const anchorKey = scene.anchors.find((node) => node.getAttribute("data-subview-anchor-hit-key"))?.getAttribute("data-subview-anchor-hit-key");
  assert.ok(anchorKey, "fixture has real rendered evidence edges");
  state.assembly.subview.activeAnchors = [{ hitKey: anchorKey, edge: "left" }, { hitKey: anchorKey, edge: "right" }];
  render();
  const previews = [], payloads = []; let persisted = 0;
  const dragDeps = {
    deferSubviewFragmentDrag() { assert.fail("drag must not invoke the retired implicit-partition hook"); },
    roundTrackMetric: (value) => Number(value.toFixed(6)),
    resolveSubviewTrackDragOffsetBp,
    convertTrackOffsetPxToBp: (value, metrics) => value * Number(metrics.domainSpanBp) / Number(metrics.innerWidth),
    resolveActiveTrackScrollElement: () => scene.scroll,
    clearSubviewTrackDragPreview() {},
    previewSubviewTrackContigDrag: (_host, payload) => { previews.push(payload); },
    applySubviewTrackDragOffset: (_host, _store, payload) => {
      payloads.push(payload);
      const assembly = store.getState().assembly;
      const composition = getSubviewComposition(assembly.subview);
      const moved = composition ? moveSubviewCompositionDrag(composition, payload) : null;
      if (moved) assert.equal(moved.changed, true);
      const committed = commitSubviewHistoryOperation(assembly, {
        nextSubview: moved ? applySubviewComposition(assembly.subview, moved.composition) : assembly.subview,
        nextSubviewTrackDragOffsets: moved ? assembly.subviewTrackDragOffsets : setSubviewDragGroupOffsets(assembly.subviewTrackDragOffsets, payload),
        operation: { kind: "drag-contig", count: payload.targets?.length || 1 },
      });
      assert.equal(committed.changed, true); store.setState({ assembly: committed.assembly }); render();
    },
    persistSubviewTrackDragOffsets: async () => { persisted += 1; },
  };
  const selectDeps = {
    prepareSubviewFragmentSelection() { assert.fail("selection must not invoke the retired implicit-partition hook"); },
    updateTrackSelection() {},
    updateSubviewTrackPairSelection: (_host, _store, entries) => {
      store.setState({ assembly: { ...state.assembly, subview: { ...state.assembly.subview, trackPairSelectedCtgs: entries } } }); render();
    },
  };
  function pointer(target, clientX, clientY) { return { target, button: 0, pointerId: 1, clientX, clientY, defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; } }; }
  function split(id, cutAfter) {
    const composition = projectRenderedSubviewToComposition(state, renderAssemblyPage(state));
    const parent = composition.members.find((m) => m.assemblyCtgId === id);
    const result = splitLocalMember(composition, parent.entityKey, cutAfter);
    assert.equal(result.changed, true);
    store.setState({ assembly: { ...state.assembly, subview: applySubviewComposition(state.assembly.subview, result.composition) } }); render();
    return result;
  }
  return { store, host, win, previews, payloads, get scene() { return scene; }, render, pointer, split,
    bindDrag() { bindSubviewTrackContigDrag(host, store, dragDeps); },
    bindBox() { bindTrackBoxSelection(host, store, selectDeps); },
    persisted: () => persisted,
  };
}
