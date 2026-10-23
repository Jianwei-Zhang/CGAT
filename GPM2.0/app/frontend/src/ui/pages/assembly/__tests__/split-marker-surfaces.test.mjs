import test from "node:test";
import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { renderAssemblyPage } from "./tabs-semantics-harness.mjs";

const attr = (tag, key) => tag.match(new RegExp(`${key}="([^"]*)"`))?.[1];
function group(html, role, id) {
  const key = role === "main" ? "data-track-contig-id" : "data-subview-contig-id";
  const start = [...html.matchAll(/<g\b[^>]*>/g)].find(([tag]) => attr(tag, key) === String(id))?.index;
  if (start == null) return "";
  let depth = 0;
  for (const match of html.slice(start).matchAll(/<\/?g\b[^>]*>/g)) {
    depth += match[0].startsWith("</") ? -1 : 1;
    if (depth === 0) return html.slice(start, start + match.index + match[0].length);
  }
  return "";
}
for (const mode of ["2-contig", "track-pair", "composition"]) for (const flipped of [false, true]) for (const nativeOrient of ["+", "-"]) {
  test(`${mode} real cut markers follow ctgs in Main and Local View, locally flipped=${flipped}, native=${nativeOrient}`, () => {
    const state = createIdentityRenderState(mode);
    const fragment = { sourceSeqId: 7, groupKey: "manual-fragment:6", sourceStart: 1001,
      sourceEnd: 17000, sourceLength: 40000, gapBeforeBp: 100, gapAfterBp: 0 };
    Object.assign(state.assembly.chrCtgs[0], { sourceFragment: fragment, orient: nativeOrient, refOrient: nativeOrient });
    if (mode === "composition") Object.assign(state.assembly.subview.summary.members.find((m) => m.assemblyCtgId === 2),
      { sourceFragment: fragment, flipped, baseOrientation: nativeOrient });
    else state.assembly.subview.flippedCtgs = flipped ? [{ slot: "bottom", contigId: 2 }] : [];
    const html = renderAssemblyPage(state);
    for (const role of ["main", "local"]) {
      const markup = group(html, role, 2);
      assert.ok(markup, `${role} ctg rendered`);
      assert.match(markup, /data-manual-split-after="17000"/);
      assert.doesNotMatch(markup, /data-manual-split-after="1000"/);
      const marker = markup.match(/<path[^>]*data-manual-split-after="17000"[^>]*>/)?.[0];
      const rectangle = markup.match(/<rect[^>]*class="track-ctg[^>]*>/)?.[0];
      const expectedX = Number(attr(rectangle, "x")) + (((nativeOrient === "-") !== (role === "local" && flipped)) ? 0 : Number(attr(rectangle, "width")));
      const x = Number(attr(marker, "d").match(/^M ([\d.-]+)/)[1]) + 2;
      assert.ok(Math.abs(x - expectedX) < 0.03, `${role} marker follows effective orientation`);
    }
  });
}


const localMarkup = (state) => renderAssemblyPage(state).split('data-subview-panel="1"')[1] || "";
const markerCount = (markup, cut) => (markup.match(new RegExp(`data-manual-split-after="${cut}"`, "g")) || []).length;

test("local manual cuts travel with fragments, survive delete/reopen/history and disappear only on local merge", async () => {
  const { splitLocalMember, deleteLocalMember, mergeLocalMember } = await import("../subview-fragment-model.js");
  const { getSubviewComposition, applySubviewComposition } = await import("../subview-composition-state.js");
  const { commitSubviewHistoryOperation, rollbackSubviewHistory, restoreSubviewHistoryRollback } = await import("../subview-history-state.js");
  const state = createIdentityRenderState("composition");
  const originalMain = JSON.stringify(state.assembly.chrCtgs);
  const split = splitLocalMember(getSubviewComposition(state.assembly.subview), "assembly:2", 8000);
  state.assembly = commitSubviewHistoryOperation(state.assembly, {
    nextSubview: applySubviewComposition(state.assembly.subview, split.composition), operation: { kind: "split-contig" },
  }).assembly;
  assert.equal(markerCount(localMarkup(state), 8000), 2);
  assert.equal(markerCount(renderAssemblyPage(state).split('data-subview-panel="1"')[0], 8000), 0);
  const beforeDelete = JSON.parse(JSON.stringify(state.assembly));
  const first = split.members[0];
  const deleted = deleteLocalMember(getSubviewComposition(state.assembly.subview), first.entityKey);
  state.assembly = commitSubviewHistoryOperation(state.assembly, {
    nextSubview: applySubviewComposition(state.assembly.subview, deleted.composition), operation: { kind: "remove-members" },
  }).assembly;
  state.assembly = JSON.parse(JSON.stringify(state.assembly));
  assert.equal(markerCount(localMarkup(state), 8000), 1);
  state.assembly = rollbackSubviewHistory(state.assembly).assembly;
  assert.equal(markerCount(localMarkup(state), 8000), 2);
  state.assembly = restoreSubviewHistoryRollback(state.assembly).assembly;
  assert.equal(markerCount(localMarkup(state), 8000), 1);
  state.assembly = beforeDelete;
  const merged = mergeLocalMember(getSubviewComposition(state.assembly.subview), first.entityKey, "right");
  assert.equal(merged.changed, true);
  state.assembly.subview = applySubviewComposition(state.assembly.subview, merged.composition);
  assert.equal(markerCount(localMarkup(state), 8000), 0);
  assert.equal(JSON.stringify(state.assembly.chrCtgs), originalMain);
});

test("native split history refresh updates source cuts even without candidate cache and never clears independent local cuts", async () => {
  const { splitLocalMember } = await import("../subview-fragment-model.js");
  const { getSubviewComposition, applySubviewComposition } = await import("../subview-composition-state.js");
  const { reconcileLocalSubviewWithMain } = await import("../subview-fragment-reconcile.js");
  const state = createIdentityRenderState("composition"), parent = state.assembly.chrCtgs[0];
  state.assembly.subviewCompositionCandidates = []; state.assembly.subviewCompositionCandidatesLoaded = false;
  const split = splitLocalMember(getSubviewComposition(state.assembly.subview), "assembly:2", 6000);
  state.assembly.subview = applySubviewComposition(state.assembly.subview, split.composition);
  const children = [[201, 1, 8000], [202, 8001, 16000]].map(([id, start, end]) => ({
    ...parent, assemblyCtgId: id, totalLength: end - start + 1, lengthBp: end - start + 1,
    sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:2", sourceStart: start, sourceEnd: end,
      sourceLength: 16000, gapBeforeBp: 0, gapAfterBp: 0 },
  }));
  for (const main of [children, [parent], children]) {
    state.assembly = reconcileLocalSubviewWithMain({ ...state.assembly, chrCtgs: main });
    const html = localMarkup(state);
    assert.equal(markerCount(html, 6000), 2, "independent local cut survives main undo/redo");
    assert.equal(markerCount(html, 8000), main === children ? 1 : 0, "real cut is projected inside the retained local member");
  }
});

test("anchor-derived local intervals do not fabricate manual split marks", async () => {
  const { isolateLocalMemberInterval } = await import("../subview-fragment-model.js");
  const { getSubviewComposition, applySubviewComposition } = await import("../subview-composition-state.js");
  const state = createIdentityRenderState("composition");
  const isolated = isolateLocalMemberInterval(getSubviewComposition(state.assembly.subview), "assembly:2", 1001, 3000);
  state.assembly.subview = applySubviewComposition(state.assembly.subview, isolated.composition);
  assert.doesNotMatch(localMarkup(state), /data-manual-split-after=/);
});


test("a local merge retains the real internal cut, but does not fabricate an extra outer cut", async () => {
  const { reconcileLocalSubviewWithMain } = await import("../subview-fragment-reconcile.js");
  const state = createIdentityRenderState("composition"), parent = state.assembly.chrCtgs[0];
  const children = [[201, 1, 8000], [202, 8001, 16000]].map(([id, start, end]) => ({
    ...parent, assemblyCtgId: id, totalLength: end - start + 1, lengthBp: end - start + 1,
    sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:2", sourceStart: start,
      sourceEnd: end, sourceLength: 16000, gapBeforeBp: 0, gapAfterBp: 0 },
  }));
  state.assembly.subviewCompositionCandidates = [];
  state.assembly = reconcileLocalSubviewWithMain({ ...state.assembly, chrCtgs: children });
  const html = localMarkup(state);
  assert.equal(markerCount(html, 8000), 1);
  const markup = group(html, "local", 201);
  const rect = markup.match(/<rect[^>]*class="track-ctg[^>]*>/)?.[0];
  const marker = markup.match(/<path[^>]*data-manual-split-after="8000"[^>]*>/)?.[0];
  assert.equal(Number(attr(marker, "d").match(/^M ([\d.-]+)/)[1]) + 2,
    Number(attr(rect, "x")) + Number(attr(rect, "width")) / 2);
});

test("local split marks follow a moved and flipped fragment's own rectangle", async () => {
  const { splitLocalMember } = await import("../subview-fragment-model.js");
  const { getSubviewComposition, applySubviewComposition } = await import("../subview-composition-state.js");
  const state = createIdentityRenderState("composition");
  const split = splitLocalMember(getSubviewComposition(state.assembly.subview), "assembly:2", 8000);
  const first = split.members[0];
  first.flipped = true; first.xBp += 4000;
  state.assembly.subview = applySubviewComposition(state.assembly.subview, split.composition);
  const markup = group(localMarkup(state), "local", 2);
  const rect = markup.match(/<rect[^>]*class="track-ctg[^>]*>/)?.[0];
  const marker = markup.match(/<path[^>]*data-manual-split-after="8000"[^>]*>/)?.[0];
  assert.ok(Number(attr(rect, "x")) > 0);
  assert.equal(Number(attr(marker, "d").match(/^M ([\d.-]+)/)[1]) + 2, Number(attr(rect, "x")));
});


test("repeated native splits of an N-delimited parent retain local source ancestry and cut markers", async () => {
  const { reconcileLocalSubviewWithMain } = await import("../subview-fragment-reconcile.js");
  const state = createIdentityRenderState("composition"), parent = state.assembly.chrCtgs[0];
  const sourceFragment = { sourceSeqId: 7, groupKey: "n-fragment:original", sourceStart: 1001,
    sourceEnd: 17000, sourceLength: 18000, gapBeforeBp: 100, gapAfterBp: 1000 };
  Object.assign(parent, { sourceFragment });
  Object.assign(state.assembly.subview.summary.members.find((m) => m.assemblyCtgId === 2), { sourceFragment });
  state.assembly.subviewCompositionCandidates = [];
  const child = (id, start, end) => ({ ...parent, assemblyCtgId: id, totalLength: end - start + 1,
    lengthBp: end - start + 1, sourceFragment: { ...sourceFragment, groupKey: "manual-fragment:2",
      sourceStart: start, sourceEnd: end, gapBeforeBp: start === 1001 ? 100 : 0, gapAfterBp: end === 17000 ? 1000 : 0 } });
  state.assembly = reconcileLocalSubviewWithMain({ ...state.assembly, chrCtgs: [child(201, 1001, 9000), child(202, 9001, 17000)] });
  assert.equal(markerCount(localMarkup(state), 9000), 1);
  state.assembly = reconcileLocalSubviewWithMain({ ...state.assembly,
    chrCtgs: [child(301, 1001, 5000), child(302, 5001, 9000), child(202, 9001, 17000)] });
  const member = state.assembly.subview.summary.members.find((m) => m.source.role === "primary");
  assert.equal(member.lengthBp, 16000, "the next generation must not lose the prior parent's retained bases");
  assert.equal(markerCount(localMarkup(state), 5000), 1);
  assert.equal(markerCount(localMarkup(state), 9000), 1);
  assert.equal(markerCount(localMarkup(state), 1000), 0);
  assert.equal(markerCount(localMarkup(state), 17000), 0);
});
