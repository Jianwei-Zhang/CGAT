import test from "node:test";
import assert from "node:assert/strict";
import { bindAssemblyScopePopovers } from "../scope-popover-runtime.js";
import { createScopePopoverFixture, withPopoverClock } from "./scope-popover-fixture.mjs";

function fixture() {
  const f = createScopePopoverFixture();
  let state = { session: { workspacePath: "/ws", projectId: 1 }, assembly: { chrPickerOpen: false, membersCardCollapsed: true } };
  const store = { getState: () => state, setState: patch => { state = { ...state, ...patch }; } };
  const owner = bindAssemblyScopePopovers(f.host, store);
  return { ...f, store, owner };
}

test("single trigger toggles an existing panel with no data loads or layout replacement", () => {
  const f = fixture(), panel = f.panels.chromosomes;
  f.emit("click", f.triggers.chromosomes);
  assert.equal(f.store.getState().assembly.chrPickerOpen, true);
  assert.equal(f.triggers.chromosomes.attrs["aria-expanded"], "true");
  assert.equal(panel.hidden, false); assert.equal(panel.style.position, "fixed");
  f.emit("click", f.triggers.chromosomes);
  assert.equal(panel.hidden, true); assert.equal(panel.scrollTop, 75);
});

test("selection inside panel stays open, outside click closes, Escape restores trigger focus", () => {
  const f = fixture(); f.owner.setOpen("members", true);
  f.emit("pointerdown", f.child("members"), {}, f.documentEvents);
  assert.equal(f.panels.members.hidden, false);
  f.emit("keydown", f.child("members"), { key: "Escape" });
  assert.equal(f.triggers.members.focusCount, 1); assert.equal(f.panels.members.hidden, true);
  f.owner.setOpen("chromosomes", true);
  f.emit("pointerdown", {}, {}, f.documentEvents);
  assert.equal(f.store.getState().assembly.chrPickerOpen, false);
});

test("combined trigger, panel and owned context menu have one 400ms grace/reentry owner", () => withPopoverClock(timers => {
  const f = fixture(); f.owner.setOpen("members", true);
  const menu = { closest: selector => selector.includes("data-members-popover-owner") ? menu : null };
  f.emit("pointerout", f.triggers.members, { relatedTarget: f.child("members") }); assert.equal(timers.size, 0);
  f.emit("pointerout", f.child("members"), { relatedTarget: menu }); assert.equal(timers.size, 0);
  f.emit("pointerout", menu, { relatedTarget: null }); assert.equal(timers.size, 1);
  assert.equal([...timers.values()][0].delay, 400);
  f.emit("pointerover", f.child("members")); assert.equal(timers.size, 0);
  f.emit("pointerout", f.child("members"), { relatedTarget: {} });
  [...timers.values()][0].fn(); assert.equal(f.panels.members.hidden, true);
}));

test("rebinding preserves close grace across mounted section patches without multiplying handlers", () => withPopoverClock(timers => {
  const f = fixture(); f.owner.setOpen("chromosomes", true);
  f.emit("pointerout", f.triggers.chromosomes, { relatedTarget: null });
  const count = [...f.events.values()].reduce((n, list) => n + list.length, 0);
  bindAssemblyScopePopovers(f.host, f.store); bindAssemblyScopePopovers(f.host, f.store);
  assert.equal([...f.events.values()].reduce((n, list) => n + list.length, 0), count);
  assert.equal(timers.size, 1); [...timers.values()][0].fn();
  assert.equal(f.store.getState().assembly.chrPickerOpen, false);
}));

test("project scope changes cancel old close timers and disconnected roots cannot mutate state", () => withPopoverClock(timers => {
  const f = fixture(); f.owner.setOpen("chromosomes", true);
  f.emit("pointerout", f.triggers.chromosomes, { relatedTarget: null });
  f.store.setState({ session: { workspacePath: "/ws", projectId: 2 }, assembly: { chrPickerOpen: false } });
  f.owner.refresh(); assert.equal(timers.size, 0);
  f.owner.setOpen("chromosomes", true); f.emit("pointerout", f.triggers.chromosomes, { relatedTarget: null });
  const previous = f.store.getState(); f.host.isConnected = false;
  [...timers.values()][0].fn(); assert.equal(f.store.getState(), previous);
}));

test("member marquee owns departure until release, then the ordinary 400ms close grace resumes", () => withPopoverClock(timers => {
  const f = fixture(); f.owner.setOpen("members", true);
  const selector = ".assembly-member-chip-region[data-member-marquee-active='1']";
  f.nodes.set(selector, {});
  f.emit("pointerout", f.child("members"), { relatedTarget: {}, buttons: 1 });
  assert.equal(timers.size, 0); assert.equal(f.panels.members.hidden, false);
  f.nodes.delete(selector);
  f.emit("pointerup", {}, {}, f.windowEvents); assert.equal(timers.size, 1);
  assert.equal([...timers.values()][0].delay, 400);
  [...timers.values()][0].fn(); assert.equal(f.panels.members.hidden, true);
}));

test("an obsolete leave timer cannot close or persist another project's panel before its next bind", () => withPopoverClock(timers => {
  const f = fixture(); f.owner.setOpen("members", true);
  f.emit("pointerout", f.child("members"), { relatedTarget: null });
  const expire = [...timers.values()][0].fn;
  f.store.setState({ session: { workspacePath: "/other", projectId: 2 }, assembly: { membersCardCollapsed: false } });
  const current = f.store.getState();
  expire(); assert.equal(f.store.getState(), current); assert.equal(current.assembly.membersCardCollapsed, false);
}));
