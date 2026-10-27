import { createProjectViewMutationCoordinator } from "../project-view-mutation-coordinator.js";
import { beginAssemblyViewRequest } from "../assembly-view-request.js";
import test from "node:test";
import assert from "node:assert/strict";
import { createPhasedTrackController } from "../phased-track-controller.js";
import { renderAssemblyFinalPathCard } from "../render-final-path.js";
import { buildFinalPathEntry, buildFinalPathCtgSegment } from "../final-path-state.js";
import { getAssemblyI18n } from "../i18n.js";

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
};
const track = (id, key) => ({ phasedTrackId: id, displayOrder: key.charCodeAt(0) - 65,
  haplotypeKey: key, label: `Chr01${key}`, items: [] });
const path = (chrName, start = 21, end = 80) => buildFinalPathEntry({ chrName, segments: [
  buildFinalPathCtgSegment({ segmentId: `${chrName}-segment`, assemblyCtgId: 1,
    datasetName: "Primary", ctgName: "ctg1", overallLen: 100, start, end, orient: "+" }),
] });
const escape = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const renderDeps = { escapeHtml: escape, escapeAttr: escape, getAssemblyI18n,
  getCurrentProject: () => ({ primaryDatasetId: 1, supportDatasetIds: [] }),
  getDatasetNameById: () => "Primary" };
const restoreAction = /data-final-path-restore-grt-baseline=/;

function fixture({ initialTracks = [], tracksAfter = [], activeKey,
  create = async () => ({}), remove = async () => ({}), list, serialize, persist = async () => {} } = {}) {
  const mainPath = path("Chr01");
  let state = { locale: "en", session: { workspacePath: "D:/project", projectId: 7 },
    initializer: { datasets: [] }, assembly: {
      selectedChrName: "Chr01", chrCtgs: [], supportChrCtgs: [],
      phasedChrTracks: initialTracks, isChrPhased: initialTracks.length > 0,
      activePhasedTrackKey: initialTracks[0]?.haplotypeKey || "",
      activePhasedTrackKeyByChr: { Chr02: "B" },
      activeFinalPathKey: activeKey ?? (initialTracks.length ? "__all__" : ""),
      activeFinalPathKeyByChr: { Chr02: "B", Chr01: activeKey ?? (initialTracks.length ? "__all__" : "") },
      finalPathViewMode: "graph", finalPathTrackView: {},
      finalPathByChr: { Chr01: mainPath, Chr02: path("Chr02"),
        ...Object.fromEntries(initialTracks.map(t => [t.label, path(t.label)])) },
      grtProjectView: { baselineFinalPathByChr: { Chr01: path("Chr01", 1, 100) } },
    } };
  const store = { getState: () => state, setState: next => { state = { ...state, ...next }; } };
  const renders = [], feedback = [], notices = [];
  let listCalls = 0, persists = 0;
  const render = () => renderAssemblyFinalPathCard(state, renderDeps);
  let html = render();
  const controller = createPhasedTrackController({
    createPhasedChrTrack: create, deletePhasedChrTrack: remove,
    ...(serialize ? { runSerializedProjectViewMutation: serialize } : {}),
    listPhasedChrTracks: async args => { listCalls++; return list ? list(args) : { tracks: tracksAfter }; },
    addCtgToPhasedChrTrack: async () => ({}), removePhasedChrTrackItem: async () => ({}),
    persistMainTrackViewState: async () => { persists++; await persist(store.getState()); }, persistTrackDragOffsets: async () => {},
    mapAssemblyError: ({ error }) => ({ userMessage: error.message }),
    requestAssemblyNotice: async (...args) => { notices.push(args); },
    rerenderAssemblyMainTab: () => { renders.push("main"); },
    rerenderFinalPathCard: () => { renders.push("final-path"); html = render(); },
    setAssemblyActionFeedbackInMainTab: (...args) => { feedback.push(args); },
  });
  return { store, controller, renders, feedback, notices, mainPath, render,
    get html() { return html; }, get listCalls() { return listCalls; }, get persists() { return persists; } };
}

for (const mode of ["graph", "table", "log"]) {
  test(`first phase creation synchronously refreshes Final Path action in ${mode} mode`, async () => {
    const f = fixture({ tracksAfter: [track(1, "A")] });
    f.store.setState({ assembly: { ...f.store.getState().assembly, finalPathViewMode: mode } });
    assert.match(f.render(), restoreAction);
    await f.controller.createPhasedChrTrack({}, f.store);
    assert.doesNotMatch(f.html, restoreAction);
    assert.deepEqual(f.renders, ["main", "final-path"]);
    assert.equal(f.store.getState().assembly.finalPathByChr.Chr01, f.mainPath);
    assert.equal(f.store.getState().assembly.activeFinalPathKey, "__all__");
    assert.equal(f.store.getState().assembly.activeFinalPathKeyByChr.Chr02, "B");
  });
}

test("deleting the last phase restores the main-path action but never restores baseline data", async () => {
  const f = fixture({ initialTracks: [track(1, "A")], activeKey: "A" });
  const other = f.store.getState().assembly.finalPathByChr.Chr02;
  assert.doesNotMatch(f.html, restoreAction);
  await f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  assert.match(f.html, restoreAction);
  assert.equal(f.store.getState().assembly.isChrPhased, false);
  assert.equal(f.store.getState().assembly.activeFinalPathKey, "");
  assert.equal(f.store.getState().assembly.activeFinalPathKeyByChr.Chr01, "");
  assert.equal(f.store.getState().assembly.finalPathByChr.Chr01, f.mainPath);
  assert.equal(f.store.getState().assembly.finalPathByChr.Chr02, other);
  assert.equal(f.store.getState().assembly.finalPathByChr.Chr01A, undefined);
  assert.deepEqual(f.renders, ["main", "final-path"]);
  assert.equal(f.persists, 1);
});

test("adding another phase preserves an explicitly selected path", async () => {
  const f = fixture({ initialTracks: [track(1, "A")], tracksAfter: [track(1, "A"), track(2, "B")], activeKey: "A" });
  await f.controller.createPhasedChrTrack({}, f.store);
  assert.equal(f.store.getState().assembly.activeFinalPathKey, "A");
  assert.doesNotMatch(f.html, restoreAction);
  assert.equal(f.notices.length, 0);
});

test("non-last deletion retains the selected track by identity after label compaction", async () => {
  const f = fixture({ initialTracks: [track(1, "A"), track(2, "B"), track(3, "C")],
    tracksAfter: [track(2, "A"), track(3, "B")], activeKey: "B" });
  const oldB = f.store.getState().assembly.finalPathByChr.Chr01B;
  f.store.setState({ assembly: { ...f.store.getState().assembly, activePhasedTrackKey: "B" } });
  await f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  assert.equal(f.store.getState().assembly.activeFinalPathKey, "A");
  assert.equal(f.store.getState().assembly.activePhasedTrackKey, "A");
  assert.deepEqual(f.store.getState().assembly.finalPathByChr.Chr01A.segments, oldB.segments);
  assert.equal(f.store.getState().assembly.finalPathByChr.Chr01A.chrName, "Chr01A");
  assert.doesNotMatch(f.html, restoreAction);
});

test("deleting the selected path clears it to All rather than selecting a different renamed track", async () => {
  const f = fixture({ initialTracks: [track(1, "A"), track(2, "B")], tracksAfter: [track(2, "A")], activeKey: "A" });
  await f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  assert.equal(f.store.getState().assembly.activeFinalPathKey, "__all__");
  assert.doesNotMatch(f.html, restoreAction);
});

test("All remains All when a non-last track is removed", async () => {
  const f = fixture({ initialTracks: [track(1, "A"), track(2, "B")], tracksAfter: [track(2, "A")] });
  await f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  assert.equal(f.store.getState().assembly.activeFinalPathKey, "__all__");
});

test("deletion does not overwrite main-path edits made while its backend call was pending", async () => {
  const wait = deferred();
  const f = fixture({ initialTracks: [track(1, "A")], remove: () => wait.promise });
  const deleting = f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  const edited = path("Chr01", 31, 70);
  f.store.setState({ assembly: { ...f.store.getState().assembly,
    finalPathByChr: { ...f.store.getState().assembly.finalPathByChr, Chr01: edited } } });
  wait.resolve(); await deleting;
  assert.equal(f.store.getState().assembly.finalPathByChr.Chr01, edited);
});

for (const operation of ["create", "delete"]) {
  test(`failed phase ${operation} leaves path, selection and rendered card unchanged`, async () => {
    const fail = async () => { throw new Error("backend failed"); };
    const f = fixture({ initialTracks: operation === "delete" ? [track(1, "A")] : [],
      create: operation === "create" ? fail : undefined, remove: operation === "delete" ? fail : undefined });
    const before = f.store.getState().assembly, html = f.html;
    if (operation === "create") await f.controller.createPhasedChrTrack({}, f.store);
    else await f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
    assert.equal(f.store.getState().assembly, before);
    assert.equal(f.html, html);
    assert.deepEqual(f.renders, []);
    assert.equal(f.listCalls, 0);
    assert.equal(f.notices.length, 0);
  });
}

test("stale refresh cannot write or render into a newly selected chromosome", async () => {
  const wait = deferred(); const f = fixture({ list: () => wait.promise });
  const loading = f.controller.refreshPhasedTracksForCurrentChr({}, f.store);
  const switched = { ...f.store.getState().assembly, selectedChrName: "Chr02" };
  f.store.setState({ assembly: switched });
  wait.resolve({ tracks: [track(1, "A")] });
  assert.equal(await loading, null);
  assert.equal(f.store.getState().assembly, switched);
  assert.deepEqual(f.renders, []);
});

test("a backend mutation completing after project switch cannot refresh or notify the new project", async () => {
  const wait = deferred(); const f = fixture({ create: () => wait.promise, tracksAfter: [track(1, "A")] });
  const creating = f.controller.createPhasedChrTrack({}, f.store);
  f.store.setState({ session: { workspacePath: "D:/other", projectId: 8 } });
  wait.resolve(); await creating;
  assert.equal(f.listCalls, 0);
  assert.deepEqual(f.renders, []);
  assert.deepEqual(f.feedback, []);
  assert.deepEqual(f.notices, []);
});

test("newer same-scope refresh wins when list responses arrive out of order", async () => {
  const first = deferred(), second = deferred(); let calls = 0;
  const f = fixture({ list: () => (++calls === 1 ? first.promise : second.promise) });
  const a = f.controller.refreshPhasedTracksForCurrentChr({}, f.store);
  const b = f.controller.refreshPhasedTracksForCurrentChr({}, f.store);
  second.resolve({ tracks: [track(2, "B")] }); await b;
  first.resolve({ tracks: [track(1, "A")] });
  assert.equal(await a, null);
  assert.equal(f.store.getState().assembly.phasedChrTracks[0].phasedTrackId, 2);
  assert.deepEqual(f.renders, ["main", "final-path"]);
});

test("no baseline keeps the restored action absent; an already-current baseline disables it", () => {
  const f = fixture();
  f.store.setState({ assembly: { ...f.store.getState().assembly, grtProjectView: {} } });
  assert.doesNotMatch(f.render(), restoreAction);
  f.store.setState({ assembly: { ...f.store.getState().assembly,
    grtProjectView: { baselineFinalPathByChr: { Chr01: f.mainPath } } } });
  assert.match(f.render(), /data-final-path-restore-grt-baseline="Chr01"[^>]*disabled/);
});

test("a phased path never offers a precomputed restore action even with a same-name baseline", () => {
  const f = fixture({ initialTracks: [track(1, "A")], activeKey: "A" });
  f.store.setState({ assembly: { ...f.store.getState().assembly,
    grtProjectView: { baselineFinalPathByChr: { Chr01A: path("Chr01A", 1, 100) } } } });
  assert.doesNotMatch(f.render(), restoreAction);
});

test("a refresh from before an away-and-back navigation cannot overwrite freshly loaded tracks", async () => {
  const wait = deferred();
  const f = fixture({ list: () => wait.promise });
  beginAssemblyViewRequest(f.store);
  const loading = f.controller.refreshPhasedTracksForCurrentChr({}, f.store);
  beginAssemblyViewRequest(f.store);
  f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "Chr02" } });
  beginAssemblyViewRequest(f.store);
  const fresh = { ...f.store.getState().assembly, selectedChrName: "Chr01",
    phasedChrTracks: [track(20, "A")], isChrPhased: true };
  f.store.setState({ assembly: fresh });
  wait.resolve({ tracks: [track(10, "A")] });
  assert.equal(await loading, null);
  assert.equal(f.store.getState().assembly, fresh);
  assert.deepEqual(f.renders, []);
});

test("an obsolete create completion does not refresh after away-and-back navigation", async () => {
  const wait = deferred();
  const f = fixture({ create: () => wait.promise, tracksAfter: [track(10, "A")] });
  beginAssemblyViewRequest(f.store);
  const creating = f.controller.createPhasedChrTrack({}, f.store);
  beginAssemblyViewRequest(f.store);
  beginAssemblyViewRequest(f.store);
  wait.resolve(); await creating;
  assert.equal(f.listCalls, 0);
  assert.deepEqual(f.renders, []);
  assert.deepEqual(f.feedback, []);
});

test("successful deletion reconciles original-chromosome paths even after navigating away", async () => {
  const wait = deferred();
  const f = fixture({ initialTracks: [track(1, "A"), track(2, "B")],
    tracksAfter: [track(2, "A")], remove: () => wait.promise });
  const retainedPath = f.store.getState().assembly.finalPathByChr.Chr01B;
  const deleting = f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  beginAssemblyViewRequest(f.store);
  const newTracks = [{ ...track(3, "A"), label: "Chr02A" }];
  f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "Chr02",
    phasedChrTracks: newTracks, activePhasedTrackKey: "A", activeFinalPathKey: "A" } });
  wait.resolve(); await deleting;
  const current = f.store.getState().assembly;
  assert.equal(current.selectedChrName, "Chr02");
  assert.equal(current.phasedChrTracks, newTracks);
  assert.deepEqual(current.finalPathByChr.Chr01A.segments, retainedPath.segments);
  assert.equal(current.finalPathByChr.Chr01B, undefined);
  assert.ok(f.persists > 0, "successful data mutation must persist despite obsolete UI scope");
  assert.deepEqual(f.renders, []);
  assert.deepEqual(f.feedback, []);
});

test("successful deletion persists cleanup even if a newer refresh supersedes its UI response", async () => {
  const first = deferred(); let calls = 0;
  const f = fixture({ initialTracks: [track(1, "A"), track(2, "B")],
    list: () => (++calls === 1 ? first.promise : { tracks: [track(2, "A")] }) });
  const deleting = f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  await Promise.resolve(); await Promise.resolve();
  assert.equal(calls, 1);
  await f.controller.refreshPhasedTracksForCurrentChr({}, f.store);
  first.resolve({ tracks: [track(2, "A")] });
  await deleting;
  assert.deepEqual(f.renders, ["main", "final-path"],
    "a superseding item-only refresh cannot consume the committed deletion redraw");
  assert.ok(f.persists > 0, "superseded refresh must not discard the successful deletion save");
  assert.equal(f.store.getState().assembly.finalPathByChr.Chr01B, undefined);
});

test("project-switch drain waits for committed deletion cleanup before caching the departing project", async () => {
  const coordinator = createProjectViewMutationCoordinator(), backend = deferred(), saved = [];
  const f = fixture({ initialTracks: [track(1, "A"), track(2, "B")], tracksAfter: [track(2, "A")],
    remove: () => backend.promise,
    serialize: (_store, action) => coordinator.enqueue(action),
    persist: state => { saved.push({ projectId: state.session.projectId, paths: state.assembly.finalPathByChr }); },
  });
  const retained = f.store.getState().assembly.finalPathByChr.Chr01B;
  const deleting = f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  let cached;
  const switching = (async () => {
    await coordinator.whenIdle();
    cached = f.store.getState().assembly;
    f.store.setState({ session: { workspacePath: "D:/other", projectId: 8 } });
  })();
  await Promise.resolve();
  assert.equal(f.store.getState().session.projectId, 7);
  backend.resolve(); await deleting; await switching;
  assert.equal(saved.length, 1);
  assert.equal(saved[0].projectId, 7);
  assert.deepEqual(saved[0].paths.Chr01A.segments, retained.segments);
  assert.equal(saved[0].paths.Chr01B, undefined);
  assert.equal(cached.finalPathByChr, saved[0].paths);
  assert.equal(f.store.getState().session.projectId, 8);
});

test("a deletion still persists cleanup when replacement track listing fails", async () => {
  const f = fixture({ initialTracks: [track(1, "A"), track(2, "B")],
    list: async () => { throw new Error("listing failed"); } });
  const retained = f.store.getState().assembly.finalPathByChr.Chr01B;
  await f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  assert.equal(f.persists, 1);
  assert.deepEqual(f.store.getState().assembly.finalPathByChr.Chr01A.segments, retained.segments);
  assert.equal(f.store.getState().assembly.finalPathByChr.Chr01B, undefined);
  assert.deepEqual(f.renders, ["main", "final-path"]);
  assert.equal(f.store.getState().assembly.phasedChrTracks[0].phasedTrackId, 2);
});

test("mutation start invalidates an earlier phase list before the replacement list starts", async () => {
  const old = deferred(), backend = deferred(); let calls = 0;
  const f = fixture({ create: () => backend.promise,
    list: () => (++calls === 1 ? old.promise : { tracks: [track(20, "A")] }) });
  const oldRefresh = f.controller.refreshPhasedTracksForCurrentChr({}, f.store);
  const creating = f.controller.createPhasedChrTrack({}, f.store);
  old.resolve({ tracks: [track(10, "A")] });
  assert.equal(await oldRefresh, null);
  assert.deepEqual(f.renders, []);
  backend.resolve(); await creating;
  assert.equal(f.store.getState().assembly.phasedChrTracks[0].phasedTrackId, 20);
});

test("queued deletions after navigation preserve the path belonging to the backend survivor", async () => {
  const coordinator = createProjectViewMutationCoordinator(), firstDelete = deferred();
  let deletes = 0;
  const f = fixture({ initialTracks: [track(1, "A"), track(2, "B"), track(3, "C")], activeKey: "B",
    tracksAfter: [track(3, "A")], serialize: (_store, action) => coordinator.enqueue(action),
    remove: () => (++deletes === 1 ? firstDelete.promise : Promise.resolve({})),
  });
  const survivingPath = f.store.getState().assembly.finalPathByChr.Chr01C;
  const first = f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  await Promise.resolve();
  const second = f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 2, haplotypeKey: "B" });
  beginAssemblyViewRequest(f.store);
  const navigating = coordinator.whenIdle();
  firstDelete.resolve(); await Promise.all([first, second, navigating]);
  const a = f.store.getState().assembly;
  assert.deepEqual(a.finalPathByChr.Chr01A.segments, survivingPath.segments);
  assert.equal(a.finalPathByChr.Chr01B, undefined);
  assert.equal(a.finalPathByChr.Chr01C, undefined);
  assert.equal(a.phasedChrTracks[0].phasedTrackId, 3);
  assert.equal(a.phasedChrTracks[0].haplotypeKey, "A");
  assert.equal(f.persists, 2);
});

test("a committed deletion reconciles surviving selection keys even when navigation suppresses rendering", async () => {
  const backend = deferred();
  const f = fixture({ initialTracks: [track(1, "A"), track(2, "B"), track(3, "C")],
    activeKey: "B", remove: () => backend.promise });
  f.store.setState({ assembly: { ...f.store.getState().assembly, activePhasedTrackKey: "B" } });
  const deleting = f.controller.deletePhasedTrack({}, f.store, { phasedTrackId: 1, haplotypeKey: "A" });
  beginAssemblyViewRequest(f.store);
  backend.resolve(); await deleting;
  const a = f.store.getState().assembly;
  assert.equal(a.phasedChrTracks[0].phasedTrackId, 2);
  assert.equal(a.activeFinalPathKeyByChr.Chr01, "A");
  assert.equal(a.activePhasedTrackKeyByChr.Chr01, "A");
  assert.deepEqual(f.renders, []);
  assert.equal(f.persists, 1);
});
