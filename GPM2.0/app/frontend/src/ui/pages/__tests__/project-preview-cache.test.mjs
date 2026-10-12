import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../state/store.js";
import { buildProjectPreviewModel, previewProjectKey } from "../project-preview-state.js";
import { loadProjectPreviewData } from "../project-preview-page.js";
import { isPreviewSnapshot, previewSession, previewStateIsApplicable, markPreviewDom, rememberProjectPreviewDom, restoreProjectPreviewDom } from "../project-preview-cache.js";

let fixtureId = 0;
function fixture() {
  const state = { locale: "zh", activeRoute: "projectPreview", session: { workspacePath: `/preview-test-${++fixtureId}`, projectId: 1 },
    initializer: { datasets: [{ datasetId: 1, name: "ds" }], existingProjects: [{ projectId: 1, primaryDatasetId: 1 }] },
    assembly: { selectedChrName: "Chr2", finalPathByChr: {} } };
  const segment = id => ({ type: "ctg", assemblyCtgId: id, datasetName: "ds", ctgName: `ctg${id}`,
    overallLen: 1000, start: 1, end: 1000, orient: "+" });
  const db = { identity: "database-identity", revision: 0, snapshot: null, snapshotRevision: null, dirty: [],
    paths: { Chr1: { mode: "segments", segments: [segment(1)] }, Chr2: { mode: "segments", segments: [segment(2)] } } };
  const metrics = { sources: 0, metadata: 0, writes: 0, builds: [] };
  const deps = {
    async getProjectPreviewCache({ expectedIdentity, sinceRevision }) {
      metrics.metadata++;
      const memoryValid = expectedIdentity === db.identity && sinceRevision === db.revision;
      const since = expectedIdentity === db.identity ? sinceRevision : db.snapshotRevision;
      return { available: true, trackingVersion: 2, identity: db.identity, revision: db.revision, memoryValid,
        valid: memoryValid || Boolean(db.snapshot && db.snapshotRevision === db.revision),
        snapshot: memoryValid ? null : structuredClone(db.snapshot),
        dirtyChrNames: since === db.revision ? [] : db.dirty.length ? db.dirty : ["*"],
        sourceMetadata: { project: { primaryDatasetId: 1 }, datasets: state.initializer.datasets } };
    },
    async putProjectPreviewCache(request) {
      metrics.writes++;
      if (request.expectedRevision !== db.revision || request.expectedIdentity !== db.identity) return { superseded: true, stored: false };
      db.snapshot = structuredClone(request.payload); db.snapshotRevision = db.revision;
      return { stored: true };
    },
    async listProjectChromosomes() { metrics.sources++; return { referenceGenomeId: 1,
      items: [1,2].map(id => ({ chrName: `Chr${id}`, chrLength: 2000, chrOrder: id })) }; },
    async listChrViewCtgs() { metrics.sources++; return { items: [1,2].map(id => ({ assemblyCtgId: id,
      datasetId: 1, datasetName: "ds", name: `ctg${id}`, totalLength: 1000, assignedChrName: `Chr${id}`, anchorStart: 0,
      hits: [{ unusedLargeRawAlignment: true }] })) }; },
    async getProjectAssemblyViewState() { metrics.sources++; return { finalPathByChr: structuredClone(db.paths) }; },
    async getGrtProjectView() { metrics.sources++; return {}; },
    buildProjectPreviewModel(args) { metrics.builds.push(args.chromosomes.map(chr => chr.chrName));
      assert.ok(args.ctgs.every(ctg => !ctg.hits)); return buildProjectPreviewModel(args); },
  };
  const host = { innerHTML: "", querySelectorAll: () => [] };
  return { state, db, deps, metrics, host, store: createStore(state) };
}

async function load(value, options) {
  assert.equal(await loadProjectPreviewData(value.host, value.store, value.deps, options), true);
  return value.store.getState().projectPreview;
}

test("warm entry reuses models and does not read sources, build, or write again", async () => {
  const value = fixture(), first = await load(value);
  assert.equal(value.metrics.sources, 4);
  assert.deepEqual(value.metrics.builds, [["Chr1", "Chr2"]]);
  assert.equal(isPreviewSnapshot(value.db.snapshot), true);
  const second = await load(value);
  assert.equal(second.cards, first.cards);
  assert.equal(second.cacheSource, "memory");
  assert.equal(value.metrics.sources, 4);
  assert.equal(value.metrics.writes, 1);
  assert.equal(value.metrics.builds.length, 1);
});

test("reopened project restores semantic snapshot without whole-project source reads", async () => {
  const value = fixture(); await load(value);
  value.store = createStore(value.state);
  const count = value.metrics.sources, builds = value.metrics.builds.length;
  const restored = await load(value);
  assert.equal(restored.cacheSource, "project");
  assert.equal(value.metrics.sources, count);
  assert.equal(value.metrics.builds.length, builds);
  assert.ok(isPreviewSnapshot(value.db.snapshot));
  assert.equal(JSON.stringify(value.db.snapshot).includes('"hits"'), false);
  assert.equal(JSON.stringify(value.db.snapshot).includes('"ctg":'), false);
});

test("local committed path edits rebuild only the affected chromosome", async () => {
  const value = fixture(), first = await load(value);
  value.db.paths.Chr1.segments[0].end = 500;
  value.db.revision++; value.db.dirty = ["Chr1"];
  const changed = await load(value);
  assert.notEqual(changed.cards[0], first.cards[0]);
  assert.equal(changed.cards[1], first.cards[1]);
  assert.equal(changed.cards[0].paths[0].length, 500);
  assert.deepEqual(value.metrics.builds.at(-1), ["Chr1"]);
  assert.ok(value.db.snapshot.dependencies.find(item => item.chrName === "Chr2").ctgIds.includes(2));
});

test("view state, locale, and populating identical saved paths do not rebuild models", async () => {
  const value = fixture(), first = await load(value);
  const state = value.store.getState();
  value.store.setState({ locale: "en", assembly: { ...state.assembly, selectedChrName: "Chr1",
    finalPathByChr: structuredClone(value.db.paths), trackScrollState: { left: 25 } } });
  assert.equal(previewStateIsApplicable(value.store.getState()), true);
  const changed = await load(value);
  assert.equal(changed.cards, first.cards);
  assert.equal(value.metrics.sources, 4);
  assert.equal(value.metrics.builds.length, 1);
});

test("unsaved edits and explicit empty paths change memory without poisoning saved snapshots", async () => {
  const value = fixture(); await load(value);
  const saved = structuredClone(value.db.snapshot);
  const state = value.store.getState();
  value.store.setState({ assembly: { ...state.assembly, finalPathByChr: { Chr1: { mode: "segments", segments: [] } } } });
  const changed = await load(value);
  assert.equal(changed.cards[0].paths[0].parts.length, 0);
  assert.deepEqual(value.db.snapshot, saved);
  assert.equal(value.metrics.sources, 4);
  assert.equal(value.metrics.writes, 1);
  assert.deepEqual(value.metrics.builds.at(-1), ["Chr1"]);
  const builds = value.metrics.builds.length;
  await load(value);
  assert.equal(value.metrics.builds.length, builds);
});

test("manual refresh bypasses both layers", async () => {
  const value = fixture(), first = await load(value);
  const changed = await load(value, { force: true });
  assert.notEqual(changed.cards, first.cards);
  assert.equal(value.metrics.sources, 8);
  assert.equal(value.metrics.writes, 2);
  assert.deepEqual(value.metrics.builds.at(-1), ["Chr1", "Chr2"]);
});

test("corrupt snapshots and cache I/O failure do not hide a successful fresh view", async () => {
  const value = fixture(); await load(value);
  value.store = createStore(value.state);
  value.db.snapshot.cards[0].tracks[0].color = "not-a-color";
  value.deps.putProjectPreviewCache = async () => { throw new Error("read-only cache"); };
  const preview = await load(value);
  assert.equal(preview.error, "");
  assert.equal(value.metrics.sources, 8);
  value.deps.getProjectPreviewCache = async () => { throw new Error("cache unavailable"); };
  assert.equal((await load(value)).loaded, true);
});

test("content changing during source reads is retried before cache publication", async () => {
  const value = fixture();
  const original = value.deps.getProjectAssemblyViewState;
  let once = true;
  value.deps.getProjectAssemblyViewState = async () => {
    const view = await original();
    if (once) { once = false; value.db.revision++; value.db.dirty = ["Chr1"]; value.db.paths.Chr1.segments[0].end = 500; }
    return view;
  };
  const preview = await load(value);
  assert.equal(preview.cards[0].paths[0].length, 500);
  assert.equal(value.metrics.sources, 8);
  assert.equal(value.metrics.writes, 1);
});

test("duplicate entry shares an applicable pending load", async () => {
  const value = fixture();
  const first = loadProjectPreviewData(value.host, value.store, value.deps);
  const second = loadProjectPreviewData(value.host, value.store, value.deps);
  assert.equal(first, second);
  assert.equal(await first, true);
  assert.equal(value.metrics.sources, 4);
});

test("memory entries distinguish workspace/project keys", async () => {
  const value = fixture(); await load(value);
  const original = previewProjectKey(value.store.getState());
  value.store.setState({ session: { workspacePath: "/a-different-workspace", projectId: 1 }, projectPreview: null });
  const different = previewProjectKey(value.store.getState());
  assert.notEqual(different, original);
  assert.ok(previewSession(value.store).entries.has(original));
  assert.equal(previewSession(value.store).entries.has(different), false);
});


test("malformed nested snapshots are safe misses and rebuild instead of failing rendering", async () => {
  for (const corrupt of [snapshot => { snapshot.cards[0] = null; },
    snapshot => { snapshot.chromosomes[0] = null; },
    snapshot => { snapshot.cards[0].paths[0].parts[0].start = "invalid"; },
    snapshot => { snapshot.cards[0].tracks[0].positioned[0].highlights[0] = null; },
    snapshot => { snapshot.cards.pop(); }]) {
    const value = fixture(); await load(value);
    corrupt(value.db.snapshot);
    assert.equal(isPreviewSnapshot(value.db.snapshot), false);
    value.store = createStore(value.state);
    assert.equal((await load(value)).cacheSource, "rebuilt");
    assert.equal(value.metrics.sources, 8);
  }
});

test("valid card DOM is reused but locale and semantic edits reject stale restoration", async () => {
  const value = fixture(); await load(value);
  const nodes = [{ card: "Chr1" }, { card: "Chr2" }];
  const saved = { childNodes: nodes, querySelector: () => ({}), replaceChildren() {} };
  markPreviewDom(saved, value.store.getState());
  rememberProjectPreviewDom(saved);
  const restored = { replaceChildren(...items) { this.items = items; } };
  assert.equal(restoreProjectPreviewDom(restored, value.store.getState()), true);
  assert.equal(restored.items[0], nodes[0]);
  value.store.setState({ locale: "en" });
  assert.equal(restoreProjectPreviewDom(restored, value.store.getState()), false);
  const state = value.store.getState();
  value.store.setState({ locale: "zh", assembly: { ...state.assembly,
    finalPathByChr: { Chr1: { mode: "segments", segments: [] } } } });
  assert.equal(restoreProjectPreviewDom(restored, value.store.getState()), false);
});

test("source failures remain honest errors and retry recovers", async () => {
  const value = fixture(), read = value.deps.listChrViewCtgs;
  value.deps.listChrViewCtgs = async () => { throw new Error("source unavailable"); };
  assert.equal(await loadProjectPreviewData(value.host, value.store, value.deps), false);
  assert.equal(value.store.getState().projectPreview.error, "source unavailable");
  assert.equal(value.metrics.writes, 0);
  value.deps.listChrViewCtgs = read;
  assert.equal((await load(value)).loaded, true);
});

test("switching routes or closing projects during reads prevents cache and page publication", async () => {
  for (const patch of [{ activeRoute: "assembly" }, { session: { workspacePath: "", projectId: null } }]) {
    const value = fixture(); let resolve;
    value.deps.listProjectChromosomes = () => new Promise(done => { resolve = done; });
    const pending = loadProjectPreviewData(value.host, value.store, value.deps);
    await new Promise(done => setImmediate(done));
    value.store.setState(patch);
    resolve({ items: [] });
    assert.equal(await pending, false);
    assert.equal(value.metrics.writes, 0);
    assert.notEqual(value.store.getState().projectPreview?.loaded, true);
  }
});

test("superseded publication retries against the latest committed revision", async () => {
  const value = fixture(), put = value.deps.putProjectPreviewCache; let first = true;
  value.deps.putProjectPreviewCache = async request => {
    if (first) {
      first = false; value.db.revision++; value.db.dirty = ["Chr1"];
      value.db.paths.Chr1.segments[0].end = 300;
      return { stored: false, superseded: true };
    }
    return put(request);
  };
  const preview = await load(value);
  assert.equal(preview.cards[0].paths[0].length, 300);
  assert.equal(value.db.snapshotRevision, value.db.revision);
});


test("an entry on a different host supersedes rather than sharing an obsolete pending load", async () => {
  const value = fixture(), read = value.deps.listProjectChromosomes;
  let resolve;
  value.deps.listProjectChromosomes = () => new Promise(done => { resolve = done; });
  const old = loadProjectPreviewData(value.host, value.store, value.deps);
  await new Promise(done => setImmediate(done));
  value.deps.listProjectChromosomes = read;
  // A replaced route host is a different request generation.
  const nextHost = { innerHTML: "", querySelectorAll: () => [] };
  const newer = loadProjectPreviewData(nextHost, value.store, value.deps);
  assert.notEqual(old, newer);
  assert.equal(await newer, true);
  resolve({ items: [] });
  // Host-specific request tokens cannot clobber a newer model for this store.
  assert.equal(await old, false);
});
