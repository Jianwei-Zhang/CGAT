import test from "node:test";
import assert from "node:assert/strict";
import { paintMainSelection } from "../main-selection-paint.js";
function node(dataset = {}, classes = []) {
  const values = new Set(classes);
  return { dataset, attrs: {}, classList: { contains: key => values.has(key), remove: key => values.delete(key),
    toggle: (key, on) => on ? values.add(key) : values.delete(key) },
    setAttribute(key, value) { this.attrs[key] = value; }, querySelectorAll: () => [], closest: () => null };
}
function fixture() {
  const chips = [node({ assemblyCtgId: "1" }, ["is-active"]), node({ assemblyCtgId: "2" })];
  const bars = [node({}, ["is-active"]), node({})];
  const groups = [1, 2].map((id, i) => {
    const group = node({ trackContigId: String(id), trackRole: "primary", trackRectX: String(id * 100), trackRectWidth: "50" });
    group.querySelectorAll = () => [bars[i]]; return group;
  });
  const deleted = node({ deletedCtgRecordId: "9" }), localBar = node({}, ["is-multi-selected"]), localGroup = node({}, ["is-multi-selected"]);
  localGroup.querySelectorAll = () => [localBar];
  const scroll = { dataset: { trackViewboxMinX: "-40" }, scrollLeft: 300 }; groups.forEach(g => g.closest = () => scroll);
  const root = { closest() { return this; }, querySelector: () => ({}), querySelectorAll: selector =>
    selector.startsWith(".assembly-member") ? chips : selector === "[data-deleted-ctg-record-id]" ? [deleted]
      : selector.startsWith(".track-ctg-group") ? groups : [localGroup] };
  return { root, chips, bars, groups, deleted, localGroup, localBar, scroll };
}

test("plain selection updates both bars and labels/cards, and sets existing focus geometry without replacing nodes", () => {
  const f = fixture();
  assert.equal(paintMainSelection(f.root, { assembly: { selectedCtgId: 2 } }, { focus: true }), true);
  assert.equal(f.chips[0].classList.contains("is-active"), false); assert.equal(f.bars[0].classList.contains("is-active"), false);
  assert.equal(f.chips[1].classList.contains("is-active"), true); assert.equal(f.bars[1].classList.contains("is-active"), true);
  assert.equal(f.groups[1].classList.contains("is-active"), true);
  assert.equal(f.scroll.dataset.focusStart, "240"); assert.equal(f.scroll.dataset.focusCenter, "265");
  assert.equal(f.scroll.scrollLeft, 300, "paint never performs unsolicited focus/scroll");
});

test("multi and deleted selection keeps card dimensions unchanged and clears only obsolete Local multi paint", () => {
  const f = fixture();
  paintMainSelection(f.root, { assembly: { selectedCtgId: 2, trackSelectedCtgIds: [1], selectedDeletedCtgRecordIds: [9], subview: { trackPairSelectedCtgs: [] } } });
  assert.equal(f.chips[0].classList.contains("is-multi-selected"), true); assert.equal(f.bars[0].classList.contains("is-multi-selected"), true);
  assert.equal(f.deleted.attrs["aria-pressed"], "true");
  assert.equal(f.localGroup.classList.contains("is-multi-selected"), false); assert.equal(f.localBar.classList.contains("is-multi-selected"), false);
  assert.equal(f.chips[0].attrs["aria-pressed"], "true");
});
