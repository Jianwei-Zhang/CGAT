import test from "node:test";
import assert from "node:assert/strict";
import { createAssemblyContigSplitRuntime } from "../contig-split-runtime.js";
import { createState, __testRenderAssemblyFinalPathCard as renderFinalPath } from "./tabs-semantics-harness.mjs";
import { buildFinalPathEntry } from "../final-path-state.js";

function fixture(orient = "+", overrides = {}) {
  const segment = { type: "ctg", assemblyCtgId: 6, ctgName: "ptg000006l", originId: "ptg000006l",
    datasetName: "Mishima_AB", overallLen: 1000, segmentId: "parent", start: orient === "-" ? 1000 : 1,
    end: orient === "-" ? 1 : 1000 };
  const sourceRange = (start, end) => ({ dataset: "Mishima_AB", contig: "ptg000006l", start, end, orientation: orient });
  const children = [[1, 400], [401, 1000]].map(([start, end], i) => ({ ...segment,
    assemblyCtgId: null, segmentId: `split-${i}`, splitFromAssemblyCtgId: 6, splitFragmentCtgId: 85 + i,
    start: orient === "-" ? end : start, end: orient === "-" ? start : end, source: sourceRange(start, end) }));
  if (orient === "-") children.reverse();
  const entry = segments => buildFinalPathEntry({ chrName: "Chr01", segments, updatedAt: "2026-10-27" });
  let state = createState({ session: { workspacePath: "D:/fixture", projectId: 7 }, assembly: {
    selectedChrName: "Chr01", mainViewHistory: { inFlight: false }, subview: { summary: null },
    finalPathViewMode: "graph", finalPathByChr: { Chr01: entry([segment]) },
    finalPathTrackScrollState: { viewportKey: "final-path:Chr01", scrollLeft: 320 },
  } });
  const store = { getState: () => state, setState: patch => { state = { ...state, ...patch }; } };
  const calls = [], renders = [];
  let mountedFinalPath = renderFinalPath(state);
  const commit = createAssemblyContigSplitRuntime({
    flushAssemblyProjectState: async () => calls.push("flush"),
    runSerializedProjectViewMutation: async (_store, run) => run(() => true),
    runMainViewEditorAction: async payload => { calls.push("native"); assert.equal(state.assembly.mainViewHistory.inFlight, true);
      return { changed: true, status: { chrName: payload.chrName, canUndo: true, appliedOperationCount: 1 } }; },
    loadAssemblyView: async (_host, _store, options) => { calls.push("reload");
      assert.deepEqual(options, { keepCurrentChr: true, keepCurrentCtg: false, renderLoading: false, renderResult: false });
      store.setState({ assembly: { ...state.assembly, finalPathByChr: { Chr01: entry(children) } } }); },
    refreshSubviewPairwiseEvidence: async (_host, _store, options) => { calls.push("evidence");
      assert.deepEqual(options, { rerenderLoading: false, rerenderLoaded: false });
      assert.match(mountedFinalPath, /data-final-path-segment-id="parent"/);
      assert.equal(renders.length, 0, "all mounted cards wait until evidence is ready"); },
    rerenderAssemblyMainTab: () => { calls.push("main"); renders.push("main"); },
    rerenderSubviewPanel: () => { calls.push("local"); renders.push("local"); },
    rerenderFinalPathCard: () => { calls.push("final-path"); renders.push("final-path"); mountedFinalPath = renderFinalPath(state); },
    setAssemblyActionFeedback: (_host, _store, patch) => store.setState({ assembly: { ...state.assembly, ...patch } }),
    ...overrides,
  });
  return { store, commit, calls, renders, markup: () => mountedFinalPath, children };
}

for (const orient of ["+", "-"]) for (const action of ["split-ref-boundary", "split-manual-contig", "edit-local-fragment", "undo-contig-split"]) {
  test(`${action} immediately refreshes Final Path after ${orient} source edits, without page reentry`, async () => {
    const h = fixture(orient);
    assert.equal(await h.commit({}, h.store, action, { action: "split", cuts: [400] }), true);
    assert.deepEqual(h.calls, ["flush", "native", "reload", "evidence", "main", "local", "final-path"]);
    for (const id of ["split-0", "split-1"]) assert.match(h.markup(), new RegExp(`data-final-path-segment-id="${id}"`));
    assert.doesNotMatch(h.markup(), /data-final-path-segment-id="parent"/);
    assert.deepEqual(h.store.getState().assembly.finalPathByChr.Chr01.segments.map(s => [s.start, s.end]),
      h.children.map(s => [s.start, s.end]));
    assert.equal(h.store.getState().assembly.finalPathTrackScrollState.scrollLeft, 320);
    assert.equal(h.store.getState().assembly.mainViewHistory.inFlight, false);
  });
}

test("a failed native split does not redraw Final Path or hide the error", async () => {
  const h = fixture("+", { runMainViewEditorAction: async () => { throw new Error("stale source range"); } });
  const before = h.markup();
  assert.equal(await h.commit({}, h.store, "split-manual-contig", {}), false);
  assert.deepEqual(h.renders, []);
  assert.equal(h.markup(), before);
  assert.equal(h.store.getState().assembly.actionError, "stale source range");
  assert.equal(h.store.getState().assembly.mainViewHistory.inFlight, false);
});

test("a stale serialized split cannot redraw another project's Final Path", async () => {
  const h = fixture("+", { runSerializedProjectViewMutation: async (_store, run) => run(() => false) });
  assert.equal(await h.commit({}, h.store, "split-manual-contig", {}), false);
  assert.deepEqual(h.calls, ["flush"]);
  assert.deepEqual(h.renders, []);
});
