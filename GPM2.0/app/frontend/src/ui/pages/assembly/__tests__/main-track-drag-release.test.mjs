import test from "node:test";
import assert from "node:assert/strict";
import { bindTrackContigDrag } from "../track-drag-runtime.js";

function fixture(commit) {
  const host = new EventTarget();
  const window = new EventTarget();
  // Node needs the options form to remove capture listeners like a browser.
  for (const method of ["addEventListener", "removeEventListener"]) {
    const native = window[method].bind(window);
    window[method] = (type, listener, options) => native(type, listener,
      typeof options === "boolean" ? { capture: options } : options);
  }
  const frames = new Map();
  let nextFrame = 0;
  window.requestAnimationFrame = (callback) => { frames.set(++nextFrame, callback); return nextFrame; };
  window.cancelAnimationFrame = (id) => frames.delete(id);
  const scroll = { scrollLeft: 0, dataset: { trackDomainSpanBp: 100, trackInnerWidth: 100 } };
  const node = {
    getAttribute: (name) => ({ "data-track-role": "primary", "data-track-contig-id": "11" })[name] || null,
    closest: () => scroll,
  };
  const calls = [];
  const store = { getState: () => ({ assembly: { activeTab: "assembly", trackDragOffsets: [] } }) };
  bindTrackContigDrag(host, store, {
    clearTrackDragPreview: (target) => calls.push({ kind: "clear", target }),
    commitTrackDragOffset: (_host, _store, offset) => { calls.push({ kind: "commit", offset }); return commit?.(); },
    convertTrackOffsetPxToBp: (value) => value,
    resolveActiveTrackScrollElement: () => scroll,
    previewTrackContigDrag: (target, offset) => calls.push({ kind: "preview", target, offset }),
    resolveTrackDragOffsetBp: () => 10,
    roundTrackMetric: (value) => value,
    setTrackContigDragActive: (active) => calls.push({ kind: "active", active }),
    setSuppressTrackContigClickUntil() {},
  });
  const fire = (type, clientX) => {
    const event = new Event(type);
    Object.assign(event, { clientX, button: 0 });
    if (type === "pointerdown") {
      Object.defineProperty(event, "target", { value: { closest: () => node } });
      host.dispatchEvent(event);
    } else window.dispatchEvent(event);
  };
  return { window, scroll, calls, fire, frames };
}

for (const rejected of [false, true]) {
  test(`main drag keeps preview through ${rejected ? "failed" : "successful"} async commit and scopes cleanup to its old graph`, async () => {
    let settle;
    const pending = new Promise((resolve, reject) => { settle = rejected ? reject : resolve; });
    const f = fixture(() => pending);
    const originalWindow = globalThis.window;
    globalThis.window = f.window;
    try {
      f.fire("pointerdown", 20);
      f.fire("pointermove", 50);
      f.fire("pointerup", 65); // Release may precede the last pointermove/frame.
      assert.equal(f.calls.find((c) => c.kind === "preview").offset.offsetPx, 45);
      assert.equal(f.calls.find((c) => c.kind === "commit").offset.offsetBp, 55);
      assert.equal(f.calls.some((c) => c.kind === "clear"), false);
      f.fire("pointermove", 100);
      f.fire("pointerup", 100);
      assert.equal(f.calls.filter((c) => c.kind === "commit").length, 1);
      settle(rejected ? new Error("save failed") : true);
      await Promise.resolve();
      assert.equal(f.calls.filter((c) => c.kind === "clear").length, 1);
      assert.equal(f.calls.at(-1).target, f.scroll, "do not clear previews on the persistent route host");
      assert.equal(f.frames.size, 0);
    } finally { globalThis.window = originalWindow; }
  });
}

test("main drag cancellation discards queued preview without saving and allows a later drag", async () => {
  const f = fixture();
  const originalWindow = globalThis.window;
  globalThis.window = f.window;
  try {
    f.fire("pointerdown", 20);
    f.fire("pointermove", 60);
    f.fire("pointercancel", 60);
    f.fire("pointerup", 60);
    assert.equal(f.calls.some((c) => c.kind === "commit"), false);
    assert.equal(f.frames.size, 0);
    assert.deepEqual(f.calls.at(-1), { kind: "active", active: false });
    f.fire("pointerdown", 20);
    f.fire("pointerup", 20);
    assert.equal(f.calls.some((c) => c.kind === "commit"), false, "click remains a no-op");
    f.fire("pointerdown", 20);
    f.fire("pointerup", 40);
    await Promise.resolve();
    assert.equal(f.calls.filter((c) => c.kind === "commit").length, 1);
  } finally { globalThis.window = originalWindow; }
});
