import test from "node:test";
import assert from "node:assert/strict";
import { gestureHarness } from "./subview-fragment-gesture-harness.mjs";
import { memberSourceInterval } from "../subview-fragment-model.js";
import { rollbackSubviewHistory, resolveCurrentSubviewHistory } from "../subview-history-state.js";

for (const mode of ["2-contig", "track-pair", "composition"]) for (const fullRange of [false, true]) for (const flipped of [false, true]) {
  for (const delta of [-15, 20]) {
    test(`direct virtual fragment drag ${mode}, overview=${fullRange}, flipped=${flipped}, delta=${delta}`, () => {
      const oldWindow = globalThis.window, h = gestureHarness(mode, { fullRange, flipped }); globalThis.window = h.win;
      try {
        h.bindDrag();
        const initial = h.store.getState(), main = initial.assembly.chrCtgs;
        const target = h.scene.fragments.filter((node) => node.getAttribute("data-subview-fragment-contig-id") === "30")[1];
        assert.ok(target, "an active anchor exposes a middle fragment");
        const start = Number(target.getAttribute("x")) + 1;
        const event = h.pointer(target, start, Number(target.getAttribute("y")) + 2);
        h.host.emit("pointerdown", event);
        assert.equal(h.store.getState().assembly.subview, initial.assembly.subview, "pointerdown does not mutate or partition state");
        h.win.emit("pointermove", h.pointer(target, start + delta, event.clientY));
        h.win.flush();
        const prepared = h.store.getState().assembly.subview.summary.members;
        const targetKey = h.previews.at(-1)?.compositionEntityKey;
        assert.ok(targetKey);
        const before = new Map(prepared.map((member) => [member.entityKey, member.xBp]));
        const scale = Number(h.scene.scroll.dataset.subviewDomainSpanBp) / Number(h.scene.scroll.dataset.subviewInnerWidth);
        h.win.emit("pointerup", h.pointer(target, start + delta, event.clientY));
        assert.equal(h.payloads.length, 1); assert.equal(h.persisted(), 1);
        const after = h.store.getState().assembly;
        for (const member of after.subview.summary.members) {
          const shift = member.xBp - before.get(member.entityKey);
          assert.ok(Math.abs(shift - (member.entityKey === targetKey ? delta * scale : 0)) < 0.01, "only clicked interval moves by the source-scale delta");
        }
        assert.equal(after.chrCtgs, main);
        assert.equal(resolveCurrentSubviewHistory(after).record.past.length, 1);
        const undo = rollbackSubviewHistory(JSON.parse(JSON.stringify(after)));
        assert.equal(undo.changed, true);
        if (mode === "composition") assert.equal(undo.assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30).length, 1);
        else assert.equal(undo.assembly.subview.summary.mode, mode, "undo restores the original comparison mode as well as layout");
        assert.equal(h.win.listeners.get("pointermove")?.size || 0, 0);
      } finally { globalThis.window = oldWindow; }
    });
  }
}

for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`cancel or click before/after virtual preparation keeps ${mode} state and history untouched`, () => {
    for (const prepare of [false, true]) {
      const oldWindow = globalThis.window, h = gestureHarness(mode); globalThis.window = h.win;
      try {
        h.bindDrag(); const before = JSON.parse(JSON.stringify(h.store.getState().assembly));
        const target = h.scene.fragments.filter((node) => node.getAttribute("data-subview-fragment-contig-id") === "30")[1];
        h.host.emit("pointerdown", h.pointer(target, 50, 70));
        if (prepare) h.win.emit("pointermove", h.pointer(target, 70, 70));
        h.win.emit("pointercancel", h.pointer(target, 70, 70));
        assert.deepEqual(JSON.parse(JSON.stringify(h.store.getState().assembly)), before);
        assert.equal(h.persisted(), 0); assert.equal(h.payloads.length, 0);
      } finally { globalThis.window = oldWindow; }
    }
  });
}

for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`box selection materializes anchor pieces and translates exactly selected instances in ${mode}`, () => {
    const oldWindow = globalThis.window, h = gestureHarness(mode); globalThis.window = h.win;
    try {
      h.bindBox(); h.bindDrag();
      const target = h.scene.fragments.filter((node) => node.getAttribute("data-subview-fragment-contig-id") === "30")[1];
      const x = Number(target.getAttribute("x")), width = Number(target.getAttribute("width"));
      const y = Number(target.getAttribute("y")), viewbox = Number(h.scene.scroll.dataset.subviewViewboxMinX || 0);
      const blank = { closest: (selector) => selector.includes("assembly-track-scroll") ? h.scene.scroll : null };
      h.host.emit("pointerdown", h.pointer(blank, x - viewbox + width * 0.2, y - 2));
      h.win.emit("pointermove", h.pointer(blank, x - viewbox + width * 0.8, y + 16));
      h.win.emit("pointerup", {});
      const assembly = h.store.getState().assembly;
      const selected = assembly.subview.trackPairSelectedCtgs;
      assert.equal(selected.length, 1, "box intersects only the middle interval, not the entire parent");
      assert.equal(resolveCurrentSubviewHistory(assembly).record.past.length, 0, "selection does not insert a mutation");
      const key = selected[0].compositionEntityKey;
      const node = h.scene.groups.find((group) => group.getAttribute("data-subview-composition-entity-key") === key);
      const initial = new Map(assembly.subview.summary.members.map((m) => [m.entityKey, m.xBp]));
      h.host.emit("pointerdown", h.pointer(node, 50, y));
      h.win.emit("pointermove", h.pointer(node, 80, y)); h.win.flush();
      h.win.emit("pointerup", h.pointer(node, 80, y));
      assert.equal(h.persisted(), 1);
      for (const member of h.store.getState().assembly.subview.summary.members) {
        assert.equal(member.xBp !== initial.get(member.entityKey), member.entityKey === key);
      }
      assert.equal(resolveCurrentSubviewHistory(h.store.getState().assembly).record.past.length, 1);
    } finally { globalThis.window = oldWindow; }
  });
}

for (const mode of ["2-contig", "track-pair", "composition"]) for (const fullRange of [false, true]) for (const delta of [-20, 25]) {
  test(`selected virtual intervals on both lanes move rigidly and an unselected leader stays independent: ${mode}, overview=${fullRange}, delta=${delta}`, () => {
    const oldWindow = globalThis.window, h = gestureHarness(mode, { fullRange }); globalThis.window = h.win;
    try {
      h.bindBox(); h.bindDrag();
      const middle = h.scene.fragments.filter((node) => node.getAttribute("data-subview-fragment-contig-id") === "30")[1];
      const x = Number(middle.getAttribute("x")), width = Number(middle.getAttribute("width"));
      const bottom = h.scene.fragments.find((node) => node.getAttribute("data-subview-fragment-slot") === "bottom");
      const topY = Number(middle.getAttribute("y")), bottomY = Number(bottom.getAttribute("y"));
      const vx = Number(h.scene.scroll.dataset.subviewViewboxMinX || 0);
      const blank = { closest: (selector) => selector.includes("assembly-track-scroll") ? h.scene.scroll : null };
      h.host.emit("pointerdown", h.pointer(blank, x - vx + width * 0.2, topY - 2));
      h.win.emit("pointermove", h.pointer(blank, x - vx + width * 0.8, bottomY + 16)); h.win.emit("pointerup", {});
      const selected = h.store.getState().assembly.subview.trackPairSelectedCtgs;
      assert.equal(selected.length, 2);
      const keys = new Set(selected.map((entry) => entry.compositionEntityKey));
      const before = new Map(h.store.getState().assembly.subview.summary.members.map((m) => [m.entityKey, m.xBp]));
      const leader = h.scene.groups.find((node) => node.getAttribute("data-subview-composition-entity-key") === selected[1].compositionEntityKey);
      const scale = Number(h.scene.scroll.dataset.subviewDomainSpanBp) / Number(h.scene.scroll.dataset.subviewInnerWidth);
      h.host.emit("pointerdown", h.pointer(leader, 300, bottomY));
      h.win.emit("pointermove", h.pointer(leader, 300 + delta, bottomY)); h.win.flush();
      h.win.emit("pointerup", h.pointer(leader, 300 + delta, bottomY));
      assert.equal(h.payloads[0].targets.length, 2);
      for (const m of h.store.getState().assembly.subview.summary.members) {
        assert.ok(Math.abs(m.xBp - before.get(m.entityKey) - (keys.has(m.entityKey) ? delta * scale : 0)) < 0.01);
      }
      assert.equal(h.store.getState().assembly.subview.trackPairSelectedCtgs.length, 2);
      assert.equal(resolveCurrentSubviewHistory(h.store.getState().assembly).record.past.length, 1);
      const current = h.store.getState().assembly.subview.summary.members;
      const unselected = current.find((m) => !keys.has(m.entityKey));
      const nextLeader = h.scene.groups.find((node) => node.getAttribute("data-subview-composition-entity-key") === unselected.entityKey);
      const previous = new Map(current.map((m) => [m.entityKey, m.xBp]));
      h.host.emit("pointerdown", h.pointer(nextLeader, 300, topY));
      h.win.emit("pointermove", h.pointer(nextLeader, 320, topY)); h.win.flush();
      h.win.emit("pointerup", h.pointer(nextLeader, 320, topY));
      for (const m of h.store.getState().assembly.subview.summary.members) assert.equal(m.xBp !== previous.get(m.entityKey), m.entityKey === unselected.entityKey);
      assert.equal(h.persisted(), 2);
    } finally { globalThis.window = oldWindow; }
  });
}
