import test from "node:test";
import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { applySubviewComposition, getSubviewComposition } from "../subview-composition-state.js";
import { splitLocalMember, deleteLocalMember } from "../subview-fragment-model.js";
import { commitSubviewHistoryOperation, rollbackSubviewHistory } from "../subview-history-state.js";
import { describeMainMemberLocalState, resolveMainMemberSourceRange, resolveMainMemberCardName } from "../main-member-local-state.js";
import { createEditingOperations } from "../../../../dev-bridge/operations/editing.js";

const memberPanel = (html) => html.match(/<article class="card assembly-members-panel[^]*?<\/article>/)?.[0] || "";
test("Main DS chips keep real membership and total lengths while annotating local split/delete/undo", () => {
  const state = createIdentityRenderState("composition"); state.assembly.membersCardCollapsed = false;
  const real = state.assembly.chrCtgs;
  const before = memberPanel(renderAssemblyPage(state));
  const composition = getSubviewComposition(state.assembly.subview), split = splitLocalMember(composition, "assembly:2", 8000);
  const committed = commitSubviewHistoryOperation(state.assembly, { nextSubview: applySubviewComposition(state.assembly.subview, split.composition), operation: { kind: "split-contig" } });
  state.assembly = committed.assembly;
  const after = memberPanel(renderAssemblyPage(state));
  assert.equal((before.match(/data-assembly-ctg-id=/g) || []).length, 1);
  assert.equal((after.match(/data-assembly-ctg-id=/g) || []).length, 1);
  assert.match(after, /局部：2 个对象/);
  assert.equal(state.assembly.chrCtgs, real);
  const deleted = deleteLocalMember(split.composition, split.members[0].entityKey);
  state.assembly = { ...state.assembly, subview: applySubviewComposition(state.assembly.subview, deleted.composition) };
  const detail = describeMainMemberLocalState(real[0], state.assembly);
  assert.equal(detail.retainedBp, 8000); assert.equal(detail.totalBp, 16000);
  assert.match(memberPanel(renderAssemblyPage(state)), /局部保留 8,000\/16,000 bp/);
  const allGone = deleteLocalMember(deleted.composition, split.members[1].entityKey);
  state.assembly = { ...state.assembly, subview: applySubviewComposition(state.assembly.subview, allGone.composition) };
  assert.match(memberPanel(renderAssemblyPage(state)), /仅局部已删除/);
  state.assembly = rollbackSubviewHistory(committed.assembly).assembly;
  assert.equal(describeMainMemberLocalState(real[0], state.assembly), null);
});

test("real source fragments and deleted native entities display actual source ranges, never virtual lengths", () => {
  const state = createIdentityRenderState("composition"), original = state.assembly.chrCtgs[0];
  state.locale = "en"; state.assembly.membersCardCollapsed = false;
  state.assembly.chrCtgs = [[701, 1, 4000], [703, 6001, 16000]].map(([id, start, end]) => ({ ...original,
    assemblyCtgId: id, totalLength: end - start + 1, sourceFragment: { sourceSeqId: 700, groupKey: "manual-fragment:2", sourceStart: start, sourceEnd: end } }));
  state.assembly.deletedCtgs = [{ deletedCtgRecordId: 91, assemblyCtgId: 702, name: "deleted-piece", totalLength: 2000,
    sourceRange: { sourceSeqId: 700, sourceStart: 4001, sourceEnd: 6000 } }];
  const html = memberPanel(renderAssemblyPage(state));
  assert.equal((html.match(/data-assembly-ctg-id=/g) || []).length, 2);
  assert.equal((html.match(/data-deleted-ctg-record-id=/g) || []).length, 1);
  assert.match(html, /Source 1–4,000/); assert.match(html, /Source 6,001–16,000/); assert.match(html, /Source 4,001–6,000/);
  assert.equal(resolveMainMemberSourceRange({ sourceRange: { sourceStart: 0, sourceEnd: 50 } }), null);
});

test("development bridge keeps retained source ranges and accepts older deleted-list output", async () => {
  const common = "deleted_ctg record_id=3 ctg_id=702 name=part chr=Chr01 chr_order=1 anchor_start=10 ref_orient=+ mode=auto members=1 bp=2000 deleted_at=1";
  for (const suffix of ["", " source_seq_id=700 source_start=4001 source_end=6000"]) {
    const runtime = createEditingOperations({ runBackend: async () => ({ stdout: common + suffix }) });
    const result = await runtime.listDeletedCtgs({ workspaceRoot: "D:/fixture", projectId: 7 });
    assert.equal(result.items.length, 1);
    assert.deepEqual(result.items[0].sourceRange, suffix ? { sourceSeqId: 700, sourceStart: 4001, sourceEnd: 6000 } : undefined);
  }
});


test("member annotation refresh follows local edits but does not redraw on drag-preview or selection-only rebinds", async () => {
  const { createMainMemberAnnotationRefresh } = await import("../main-member-local-state.js");
  let state = createIdentityRenderState("composition");
  const host = {}, calls = [], store = { getState: () => state };
  const refresh = createMainMemberAnnotationRefresh({ rerenderMembers: (_host, value) => { assert.equal(value, store); calls.push("members only"); return true; } });
  assert.equal(refresh(host, store), true);
  assert.equal(refresh(host, store), false);
  state = { ...state, assembly: { ...state.assembly, subview: { ...state.assembly.subview,
    pairwiseEvidence: { ...state.assembly.subview.pairwiseEvidence }, trackPairSelectedCtgs: [{ contigId: 2, trackRole: "primary" }] } } };
  assert.equal(refresh(host, store), false, "selection/evidence alone does not replace the Main track or chips");
  const split = splitLocalMember(getSubviewComposition(state.assembly.subview), "assembly:2", 8000);
  state = { ...state, assembly: { ...state.assembly, subview: applySubviewComposition(state.assembly.subview, split.composition) } };
  assert.equal(refresh(host, store), true);
  assert.deepEqual(calls, ["members only", "members only"]);
});


test("compact member names strip only generated coordinate suffixes backed by authoritative ranges", () => {
  const ctg = { sourceFragment: { sourceStart: 46280956, sourceEnd: 59056711 } };
  assert.equal(resolveMainMemberCardName(ctg, "Chr01[42739070-59056711].2"), "Chr01.2");
  assert.equal(resolveMainMemberCardName(ctg, "Chr01[1-100][20-80].1.2"), "Chr01.1.2");
  assert.equal(resolveMainMemberCardName({}, "sample[1-100].2"), "sample[1-100].2");
  assert.equal(resolveMainMemberCardName(ctg, "sample[custom-name]"), "sample[custom-name]");
});

test("member card separates short title, real length, current source range and compact local status", () => {
  const state = createIdentityRenderState("composition");
  state.assembly.membersCardCollapsed = false;
  const original = state.assembly.chrCtgs[0];
  const split = splitLocalMember(getSubviewComposition(state.assembly.subview), "assembly:2", 8000);
  const deleted = deleteLocalMember(split.composition, split.members[0].entityKey);
  state.assembly.subview = applySubviewComposition(state.assembly.subview, deleted.composition);
  const partial = memberPanel(renderAssemblyPage(state));
  assert.match(partial, /ctg-chip-heading/);
  assert.match(partial, /ctg-chip-length[^>]*>16,000 bp/);
  assert.match(partial, /data-main-member-local-state="partial"[^>]*>局部部分保留<\/span>/);
  assert.match(partial, /title="局部保留 8,000\/16,000 bp · 1 个对象/);
  state.assembly.chrCtgs = [{ ...original, name: "Chr01[42739070-59056711].2", totalLength: 12775756,
    sourceFragment: { sourceSeqId: 1, groupKey: "manual-fragment:2", sourceStart: 46280956, sourceEnd: 59056711 } }];
  const html = memberPanel(renderAssemblyPage(state));
  assert.match(html, /title="Chr01\[42739070-59056711\]\.2"/);
  assert.match(html, />Chr01\.2<\/span>/);
  assert.match(html, /ctg-chip-source-range[^>]*>源 46,280,956–59,056,711<\/span>/);
  assert.equal((html.match(/data-assembly-ctg-id=/g) || []).length, 1);
  assert.equal(state.assembly.chrCtgs[0].name, "Chr01[42739070-59056711].2", "presentation never renames the source entity");
});
