import test from "node:test";
import assert from "node:assert/strict";
import { gestureHarness } from "./subview-fragment-gesture-harness.mjs";
import { memberSourceInterval } from "../subview-fragment-model.js";
import { resolveLocalFragmentMenu } from "../subview-fragment-controller.js";
import { rollbackSubviewHistory, restoreSubviewHistoryRollback, resolveCurrentSubviewHistory } from "../subview-history-state.js";

const middleAnchor = (h) => h.scene.fragments.filter((n) => n.getAttribute("data-subview-fragment-contig-id") === "30")[1];
const historyDepth = (assembly) => resolveCurrentSubviewHistory(assembly).record?.past.length || 0;
const markers = (h, cut) => (h.scene.html.split('data-subview-panel="1"')[1].match(new RegExp(`data-manual-split-after="${cut}"`, "g")) || []).length;
function drag(h, target, delta) {
  h.host.emit("pointerdown", h.pointer(target, 300, 70));
  h.win.emit("pointermove", h.pointer(target, 300 + delta, 70)); h.win.flush();
  h.win.emit("pointerup", h.pointer(target, 300 + delta, 70));
}
function boxMiddle(h, both = false) {
  const target = middleAnchor(h);
  const x = Number(target.getAttribute("x")), width = Number(target.getAttribute("width"));
  const y = Number(target.getAttribute("y")), vx = Number(h.scene.scroll.dataset.subviewViewboxMinX || 0);
  const bottom = h.scene.groups.find((node) => node.getAttribute("data-subview-track-slot") === "bottom");
  const endY = both ? Number(bottom.getAttribute("data-subview-rect-y")) + 16 : y + 16;
  const blank = { closest: (selector) => selector.includes("assembly-track-scroll") ? h.scene.scroll : null };
  h.host.emit("pointerdown", h.pointer(blank, x - vx + width * .2, y - 2));
  h.win.emit("pointermove", h.pointer(blank, x - vx + width * .8, endY));
  h.win.emit("pointerup", {});
}
function assertIntact(before, after) {
  assert.equal(after.subview.summary.mode, before.subview.summary.mode);
  if (before.subview.summary.mode === "composition") {
    assert.deepEqual(after.subview.summary.members.map(({ xBp, ...member }) => member),
      before.subview.summary.members.map(({ xBp, ...member }) => member));
  } else assert.deepEqual(after.subview.summary, before.subview.summary);
  assert.deepEqual(after.subview.activeAnchors, before.subview.activeAnchors);
  assert.deepEqual(after.subview.manualAnchors, before.subview.manualAnchors);
  assert.equal(after.chrCtgs, before.chrCtgs);
}

for (const mode of ["2-contig", "track-pair", "composition"]) for (const fullRange of [false, true]) for (const flipped of [false, true]) for (const delta of [-15, 20]) {
  test(`anchor hit-zone drag moves the intact ctg without a split: ${mode}, overview=${fullRange}, flipped=${flipped}, delta=${delta}`, () => {
    const oldWindow = globalThis.window, h = gestureHarness(mode, { fullRange, flipped }); globalThis.window = h.win;
    try {
      h.bindDrag(); const before = h.store.getState().assembly, target = middleAnchor(h);
      assert.ok(target, "active anchors expose a display interval");
      h.host.emit("pointerdown", h.pointer(target, 300, 70));
      assert.equal(h.store.getState().assembly, before);
      h.win.emit("pointermove", h.pointer(target, 300 + delta, 70)); h.win.flush();
      assert.equal(h.store.getState().assembly, before, "preview cannot materialize anchor pieces");
      h.win.emit("pointerup", h.pointer(target, 300 + delta, 70));
      const after = h.store.getState().assembly;
      assertIntact(before, after);
      assert.equal(h.payloads.length, 1); assert.equal(h.persisted(), 1);
      assert.equal(h.payloads[0].contigId, 30); assert.equal(h.payloads[0].slot, "top");
      assert.equal(historyDepth(after), 1);
      if (mode === "composition") {
        const changed = after.subview.summary.members.filter((m, i) => m.xBp !== before.subview.summary.members[i].xBp);
        assert.equal(changed.length, 1); assert.equal(changed[0].assemblyCtgId, 30);
      } else assert.ok(after.subviewTrackDragOffsets.some((offset) => offset.contigId === 30 && offset.offsetBp !== 0));
      const menu = resolveLocalFragmentMenu(h.store.getState(), h.host, { assemblyCtgId: 30, trackRole: "support", slot: "top", start: 1001, end: 3000 });
      assert.equal(menu.left, false); assert.equal(menu.right, false);
      assert.doesNotMatch(h.scene.html, /data-manual-split-after=/);
      const undo = rollbackSubviewHistory(JSON.parse(JSON.stringify(after)));
      assert.equal(undo.changed, true); assert.deepEqual(undo.assembly.subview.summary, before.subview.summary);
      assert.equal(restoreSubviewHistoryRollback(undo.assembly).changed, true);
      assert.equal(h.win.listeners.get("pointermove")?.size || 0, 0);
    } finally { globalThis.window = oldWindow; }
  });
}

for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`cancelled anchor hit-zone drag leaves ${mode} unchanged`, () => {
    for (const move of [false, true]) {
      const oldWindow = globalThis.window, h = gestureHarness(mode); globalThis.window = h.win;
      try {
        h.bindDrag(); const before = JSON.stringify(h.store.getState().assembly), target = middleAnchor(h);
        h.host.emit("pointerdown", h.pointer(target, 50, 70));
        if (move) h.win.emit("pointermove", h.pointer(target, 70, 70));
        h.win.emit("pointercancel", h.pointer(target, 70, 70));
        assert.equal(JSON.stringify(h.store.getState().assembly), before);
        assert.equal(h.persisted(), 0); assert.equal(h.payloads.length, 0);
      } finally { globalThis.window = oldWindow; }
    }
  });
  test(`box over an anchor interval selects the owning whole ctg without partitioning: ${mode}`, () => {
    const oldWindow = globalThis.window, h = gestureHarness(mode); globalThis.window = h.win;
    try {
      h.bindBox(); h.bindDrag(); const before = h.store.getState().assembly;
      boxMiddle(h);
      const selected = h.store.getState().assembly.subview.trackPairSelectedCtgs;
      assert.equal(selected.length, 1); assert.equal(selected[0].contigId, 30);
      assertIntact(before, h.store.getState().assembly);
      assert.equal(historyDepth(h.store.getState().assembly), 0);
      drag(h, middleAnchor(h), 30);
      assertIntact(before, h.store.getState().assembly); assert.equal(h.persisted(), 1);
      assert.equal(historyDepth(h.store.getState().assembly), 1);
    } finally { globalThis.window = oldWindow; }
  });
}

for (const mode of ["2-contig", "track-pair", "composition"]) for (const fullRange of [false, true]) for (const delta of [-20, 25]) {
  test(`box-selected ctgs on both lanes move together without cutting at anchors: ${mode}, overview=${fullRange}, delta=${delta}`, () => {
    const oldWindow = globalThis.window, h = gestureHarness(mode, { fullRange }); globalThis.window = h.win;
    try {
      h.bindBox(); h.bindDrag(); const before = h.store.getState().assembly;
      boxMiddle(h, true);
      assert.equal(h.store.getState().assembly.subview.trackPairSelectedCtgs.length, 2);
      drag(h, middleAnchor(h), delta);
      assertIntact(before, h.store.getState().assembly);
      assert.equal(h.payloads[0].targets.length, 2);
      const offsets = h.payloads[0].targets.map((t) => t.dragDeltaBp ?? t.offsetBp);
      assert.equal(offsets[0], offsets[1]); assert.ok(offsets[0] * delta > 0);
      assert.equal(h.persisted(), 1); assert.equal(historyDepth(h.store.getState().assembly), 1);
    } finally { globalThis.window = oldWindow; }
  });
}

for (const mode of ["2-contig", "track-pair", "composition"]) for (const flipped of [false, true]) {
  test(`an explicit split still moves independently and keeps split marks/history: ${mode}, flipped=${flipped}`, () => {
    const oldWindow = globalThis.window, h = gestureHarness(mode, { flipped }); globalThis.window = h.win;
    try {
      h.split(30, 8000); h.bindDrag();
      const before = h.store.getState().assembly;
      const member = before.subview.summary.members.find((m) => memberSourceInterval(m).sourceEnd === 8000);
      const target = h.scene.groups.find((n) => n.getAttribute("data-subview-composition-entity-key") === member.entityKey);
      assert.equal(markers(h, 8000), 2);
      drag(h, target, -20);
      const after = h.store.getState().assembly;
      assertIntact(before, after);
      for (const m of after.subview.summary.members) assert.equal(m.xBp !== before.subview.summary.members.find((b) => b.entityKey === m.entityKey).xBp, m.entityKey === member.entityKey);
      assert.equal(markers(h, 8000), 2);
      h.store.setState({ assembly: rollbackSubviewHistory(after).assembly }); h.render(); assert.equal(markers(h, 8000), 2);
      h.store.setState({ assembly: restoreSubviewHistoryRollback(h.store.getState().assembly).assembly }); h.render(); assert.equal(markers(h, 8000), 2);
    } finally { globalThis.window = oldWindow; }
  });
}
