import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { filterEditableTrackCtgIds, filterTrackMemberRows, matchesTrackMembersScope, resolveTrackMembersScope, trackMemberRows } from "../track-members-model.js";
import { normalizeHiddenSupportCtgs, hiddenSupportCtgIds, setSupportCtgsHidden } from "../support-visibility-state.js";
import { resolveTrackPrefs } from "../track-prefs.js";
import { renderTrackMembersContent, openTrackMembersDialog } from "../track-members-dialog.js";
import { deleteSelectedTrackCtgs, runBatchDeleteTrackCtgs } from "../editor-actions-runtime.js";
import { shouldHandleTrackDeleteHotkey } from "../track-hotkeys-runtime.js";
import { createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";

function state(locale = "zh") {
  return { ...createState({ initializer: {
    existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    datasets: [{ datasetId: 11, name: "main" }, { datasetId: 22, name: "support <unsafe>" }],
  }, assembly: {
    supportDatasetId: 22,
    chrCtgs: [{ assemblyCtgId: 1, name: "main", totalLength: 1000 }],
    supportChrCtgs: [{ assemblyCtgId: 2, name: "short <x>", totalLength: 50 }, { assemblyCtgId: 3, name: "long", totalLength: 1000 },
      { assemblyCtgId: 4, name: "other-owner", totalLength: 2000, assignedChrName: "Chr02" }],
    trackView: { supportDsCtgLen: 100 },
  } }), locale, activeRoute: "assembly" };
}
const context = { trackRole: "support", datasetId: 22 };
const deleted = [{ assemblyCtgId: 8, deletedCtgRecordId: 80, name: "deleted", totalLength: 30 }];
const ui = (overrides = {}) => ({ deleted, selected: new Set(), filter: "all", query: "", page: 0, busy: false, loading: false, error: "", ...overrides });

test("member scope is a real primary/support mother track, never a mirror, reference or another dataset", () => {
  const s = state(), scope = resolveTrackMembersScope(s, context);
  assert.equal(scope.datasetId, 22); assert.equal(scope.chrName, "Chr01");
  for (const target of [{ ...context, isMirror: true }, { ...context, datasetId: 33 }, { trackRole: "ref" }, { trackRole: "phased" }, { trackRole: "primary", datasetId: 22 }]) {
    assert.equal(resolveTrackMembersScope(s, target), null);
  }
  assert.ok(resolveTrackMembersScope(s, { trackRole: "primary", datasetId: 11 }));
  assert.ok(matchesTrackMembersScope(s, scope));
  assert.ok(!matchesTrackMembersScope({ ...s, session: { ...s.session, projectId: 8 } }, scope));
  assert.ok(!matchesTrackMembersScope({ ...s, assembly: { ...s.assembly, supportDatasetId: 33 } }, scope));
});

test("membership uses unfiltered authoritative pools and separates filter, hide and deletion", () => {
  const s = state(), scope = resolveTrackMembersScope(s, context);
  s.assembly = setSupportCtgsHidden(s.assembly, 22, [3], true);
  const rows = trackMemberRows(s, scope, deleted);
  assert.equal(rows.length, 4);
  assert.deepEqual(filterTrackMemberRows(rows, "filtered").map(row => row.ctg.assemblyCtgId), [2]);
  assert.deepEqual(filterTrackMemberRows(rows, "hidden").map(row => row.ctg.assemblyCtgId), [3]);
  assert.deepEqual(filterTrackMemberRows(rows, "displayed").map(row => row.ctg.assemblyCtgId), [4]);
  assert.deepEqual(filterTrackMemberRows(rows, "deleted").map(row => row.ctg.deletedCtgRecordId), [80]);
  assert.equal(rows[2].editable, false);
  assert.equal(filterTrackMemberRows(rows, "all", "SHORT").length, 1);
  // Restoring does not override filters.
  s.assembly.supportChrCtgs.push(deleted[0]);
  assert.ok(trackMemberRows(s, scope).find(row => row.ctg.assemblyCtgId === 8).filtered);
});

test("per-region filtering and effective threshold reasons use the same rule resolver as Main", () => {
  const s = state();
  s.assembly.supportDsCtgLenRulesByChr = { Chr01: [{ startBp: 1, endBp: 1000, supportDsCtgLen: 2000 }] };
  s.assembly.supportChrCtgs[1].hits = [{ refStart: 100, refEnd: 900 }];
  const row = trackMemberRows(s, resolveTrackMembersScope(s, context))[1];
  assert.equal(row.threshold, 2000); assert.equal(row.filtered, true);
});

test("support hiding is project-view data scoped to chromosome and dataset, not membership or Local View", () => {
  const s = state(), original = structuredClone(s.assembly);
  const hidden = setSupportCtgsHidden(s.assembly, 22, [2,3,999], true);
  assert.equal(hidden.supportChrCtgs, s.assembly.supportChrCtgs);
  assert.equal(hidden.subview, s.assembly.subview);
  assert.deepEqual([...hiddenSupportCtgIds(hidden)], [2,3]);
  assert.equal(hiddenSupportCtgIds({ ...hidden, selectedChrName: "Chr02" }).size, 0);
  assert.equal(hiddenSupportCtgIds(hidden, 33).size, 0);
  assert.deepEqual(s.assembly, original);
  assert.deepEqual(resolveTrackPrefs(hidden.trackView).hiddenSupportCtgs, hidden.trackView.hiddenSupportCtgs);
  assert.equal(hiddenSupportCtgIds(setSupportCtgsHidden(hidden, 22, [2,3], false)).size, 0);
  assert.equal(setSupportCtgsHidden(hidden, 33, [2], false), hidden);
  assert.deepEqual(normalizeHiddenSupportCtgs([null, { chrName: "x", datasetId: -1, assemblyCtgId: 3 }]), []);
});

test("support deletion requires explicit current-track identity and excludes mirrors / co-assigned instances", () => {
  const s = state();
  assert.deepEqual(filterEditableTrackCtgIds([1,2,3,4,999], s.assembly), [1]);
  assert.deepEqual(filterEditableTrackCtgIds([1,2,3,4,999], s.assembly, context), [2,3]);
  assert.deepEqual(filterEditableTrackCtgIds([2,3], s.assembly, { ...context, datasetId: 99 }), []);
});

for (const locale of ["en", "zh"]) test(`shared panel escapes text, exposes separate recovery/filter actions and paginates without truncating membership (${locale})`, () => {
  const s = state(locale), scope = resolveTrackMembersScope(s, context);
  let html = renderTrackMembersContent(s, scope, ui({ selected: new Set(["ctg:2"]) }));
  assert.ok(html.includes("short &lt;x&gt;")); assert.ok(!html.includes("short <x>"));
  assert.match(html, /50 &lt; 100 bp/);
  assert.match(html, /data-member-action="delete" >|data-member-action="delete"\s*>/);
  assert.doesNotMatch(html, /data-reset-members-state/);
  html = renderTrackMembersContent(s, scope, ui({ filter: "deleted", selected: new Set(["deleted:80"]) }));
  assert.match(html, /data-member-key="deleted:80" checked/);
  assert.match(html, /data-member-action="restore"\s*>/);
  for (let i = 10; i < 215; i++) s.assembly.supportChrCtgs.push({ assemblyCtgId: i, name: `n-${i}`, totalLength: i });
  html = renderTrackMembersContent(s, scope, ui());
  assert.equal((html.match(/data-member-key=/g) || []).length, 100);
  assert.ok(html.includes("1 / 3 · 208"));
  assert.ok(renderTrackMembersContent(s, scope, ui({ page: 2 })).includes("n-214"));
});

test("Main has no legacy member toolbar; hiding support suppresses its bands while retaining geometry and mirror semantics", () => {
  const s = state();
  s.assembly.supportChrCtgs[1].hits = [{ refStart: 1, refEnd: 1000, ctgStart: 1, ctgEnd: 1000, blockLength: 1000, identityPct: 100 }];
  s.assembly = setSupportCtgsHidden(s.assembly, 22, [3], true);
  const html = renderAssemblyPage(s);
  assert.doesNotMatch(html, /data-members-card-toggle|assembly-members-panel-popover/);
  assert.match(html, /class="track-ctg-group[^\"]*is-hidden-contig[^\"]*"[^>]*data-track-contig-id="3"/);
  assert.doesNotMatch(html, /data-band-contig-id="3"/);
  assert.match(html, /data-track-label-role="support"[^>]*data-track-label-dataset-id="22"/);
});

test("deleted-member read failure is not silently presented as an empty successful list", () => {
  const s = state();
  const html = renderTrackMembersContent(s, resolveTrackMembersScope(s, context), ui({ deleted: [], filter: "deleted", error: "read failed" }));
  assert.match(html, /role="alert"/); assert.match(html, /data-member-action="retry"/);
  assert.doesNotMatch(html, /没有匹配的成员/);
});

test("support delete includes dependency inspection and confirmation; scope switching cancels the pending request", async () => {
  const store = createStore(state()), calls = [];
  let accept;
  const deps = { inspectMainViewDelete: async args => { calls.push(args); return { finalPathReferenceCount: 2 }; },
    rerender() {}, mapAssemblyError: ({ error }) => ({ userMessage: String(error) }), runBatchDeleteTrackCtgs: async (...args) => calls.push(args) };
  const pending = deleteSelectedTrackCtgs({}, store, [1,2], deps, { ...context, confirm: () => new Promise(resolve => { accept = resolve; }) });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls[0].assemblyCtgIds, [2]);
  store.setState({ assembly: { ...store.getState().assembly, supportDatasetId: 33 } }); accept(true); await pending;
  assert.equal(calls.length, 1);
});

test("support batch delete bypasses primary-only summary deltas and reloads authoritative data", async () => {
  const store = createStore(state()), calls = [];
  const result = await runBatchDeleteTrackCtgs({}, store, [2], {
    localRefresh: true, loadAssemblyView: async () => calls.push("reload"),
    mapAssemblyError: ({ error }) => ({ userMessage: String(error) }), rerender() {},
    runBatchDelete: async args => { calls.push(args); return { changed: true }; },
    refreshAfterBatchDelete: () => { throw Error("must not apply primary-only deltas to support"); },
  }, context);
  assert.equal(result.deletedCount, 1); assert.equal(calls.at(-1), "reload");
  assert.deepEqual(calls[0].assemblyCtgIds, [2]);
  assert.equal(store.getState().assembly.chrCtgs.length, 1);
});

test("the global Delete hotkey cannot delete underlying selections while the member dialog owns focus", () => {
  const s = state(); s.assembly.trackSelectedCtgIds = [1];
  assert.equal(shouldHandleTrackDeleteHotkey({ key: "Delete", target: { closest: selector => selector.includes("data-track-members-dialog") } }, s), false);
});

// Minimal DOM event harness; no browser or external DOM dependency is needed for lifecycle/race checks.
function dialogHarness(overrides = {}) {
  const store = createStore(state()), events = new Map();
  const content = { innerHTML: "", querySelector: () => null, contains: () => false };
  const input = { focus() {} };
  const dialog = { open: false, removed: false, setAttribute() {},
    querySelector: selector => selector === "[data-track-members-content]" ? content : input,
    addEventListener: (type, fn) => events.set(type, fn),
    showModal() { this.open = true; }, close() { this.open = false; events.get("close")?.(); }, remove() { this.removed = true; } };
  const doc = { activeElement: null, body: { append() {} }, createElement: () => dialog };
  const calls = [];
  const deps = { listDeletedCtgs: async args => { calls.push(args); return { items: deleted }; },
    setHidden: async (...args) => calls.push(args), restore: async (...args) => calls.push(args), delete: async (...args) => calls.push(args),
    locate: async (...args) => calls.push(args), confirm: async () => true, ...overrides };
  const controller = openTrackMembersDialog({ ownerDocument: doc }, store, context, deps);
  return { store, dialog, content, calls, controller,
    click(action) { events.get("click")({ target: { closest: selector => selector === "[data-member-action]" ? { dataset: { memberAction: action } } : null } }); },
    select(key) { events.get("change")({ target: { dataset: { memberKey: key }, checked: true } }); },
    key(key) { events.get("keydown")({ key, target: { matches: () => false }, preventDefault() {}, stopPropagation() {} }); } };
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test("dialog loads exact dataset scope, batches only its selection and supports its own Delete key", async () => {
  const h = dialogHarness(); await tick();
  assert.equal(h.calls[0].datasetId, 22); assert.equal(h.calls[0].chrName, "Chr01");
  h.select("ctg:2"); h.key("Delete"); await tick();
  assert.deepEqual(h.calls[1][2], [2]); assert.equal(h.calls[1][3].datasetId, 22);
  assert.equal(h.calls[1][3].trackRole, "support");
  h.controller.close(); assert.ok(h.dialog.removed);
});

test("dialog errors remain actionable and late reads cannot reopen a closed/switched scope", async () => {
  let finish;
  const h = dialogHarness({ listDeletedCtgs: () => new Promise(resolve => { finish = resolve; }) });
  h.store.setState({ assembly: { ...h.store.getState().assembly, selectedChrName: "Chr02" } });
  assert.ok(h.dialog.removed);
  const html = h.content.innerHTML; finish({ items: deleted }); await tick(); assert.equal(h.content.innerHTML, html);
  const failing = dialogHarness({ listDeletedCtgs: async () => { throw Error("disk failed"); } }); await tick();
  assert.match(failing.content.innerHTML, /disk failed/); assert.match(failing.content.innerHTML, /data-member-action="retry"/);
  failing.controller.close();
});

test("switching routes closes the modal and no background member action can run", async () => {
  const h = dialogHarness(); await tick(); h.select("ctg:2");
  h.store.setState({ activeRoute: "importer" }); assert.ok(h.dialog.removed);
  h.click("delete"); await tick(); assert.equal(h.calls.length, 1);
});

test("pending restoration confirmation cannot restore records into a switched project", async () => {
  let accept;
  const h = dialogHarness({ confirm: () => new Promise(resolve => { accept = resolve; }) });
  await tick(); h.select("deleted:80"); h.click("restore"); await tick();
  h.store.setState({ session: { workspacePath: "/other", projectId: 88 } }); accept(true); await tick();
  assert.ok(h.dialog.removed); assert.equal(h.calls.length, 1);
});

test("a late auxiliary deletion response cannot overwrite another chromosome's history or trigger its reload", async () => {
  const store = createStore(state()); let done;
  const pending = runBatchDeleteTrackCtgs({}, store, [2], {
    loadAssemblyView: async () => { throw Error("must not reload a different scope"); },
    mapAssemblyError: ({ error }) => ({ userMessage: String(error) }), rerender() {},
    runBatchDelete: () => new Promise(resolve => { done = resolve; }),
  }, context);
  await tick();
  const next = { ...store.getState().assembly, selectedChrName: "Chr02", mainViewHistory: { chrName: "Chr02", canUndo: false } };
  store.setState({ assembly: next }); done({ changed: true, status: { chrName: "Chr01", canUndo: true } });
  assert.equal((await pending).stale, true); assert.equal(store.getState().assembly, next);
});

test("an empty auxiliary track retains its label so deleted members remain recoverable", () => {
  const s = state(); s.assembly.supportChrCtgs = [];
  assert.match(renderAssemblyPage(s), /data-track-label-role="support" data-track-label-selectable="1"[^>]*data-track-label-dataset-id="22"/);
  const html = renderTrackMembersContent(s, resolveTrackMembersScope(s, context), ui({ filter: "deleted", selected: new Set(["deleted:80"]) }));
  assert.match(html, /data-member-action="restore"\s*>/);
});

test("Delete in a nested native confirmation cannot act on the underlying Main selection", () => {
  const s = state(); s.assembly.trackSelectedCtgIds = [1];
  assert.equal(shouldHandleTrackDeleteHotkey({ key: "Delete", target: { tagName: "BUTTON", closest: selector => selector.includes(", dialog") ? {} : null } }, s), false);
});

test("shared primary panel preserves real membership and lengths while describing local split/deletion state", async () => {
  const { createIdentityRenderState } = await import("./identity-render-fixture.mjs");
  const { applySubviewComposition, getSubviewComposition } = await import("../subview-composition-state.js");
  const { splitLocalMember, deleteLocalMember } = await import("../subview-fragment-model.js");
  const s = createIdentityRenderState("composition"), real = s.assembly.chrCtgs;
  const split = splitLocalMember(getSubviewComposition(s.assembly.subview), "assembly:2", 8000);
  s.assembly.subview = applySubviewComposition(s.assembly.subview, deleteLocalMember(split.composition, split.members[0].entityKey).composition);
  const html = renderTrackMembersContent(s, { trackRole: "primary", datasetId: 11, chrName: "Chr01" }, ui({ deleted: [] }));
  assert.equal(s.assembly.chrCtgs, real);
  assert.equal((html.match(/data-member-key="ctg:/g) || []).length, 1);
  assert.match(html, /16,000 bp/);
  assert.match(html, /局部保留 8,000\/16,000 bp/);
});
