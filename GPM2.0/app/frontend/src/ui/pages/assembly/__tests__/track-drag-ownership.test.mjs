import test from "node:test";
import assert from "node:assert/strict";
import { bindSubviewTrackContigDrag, bindTrackContigDrag } from "../track-drag-runtime.js";

function pointerEvent(type, properties = {}) {
  const event = new Event(type, { cancelable: true });
  Object.defineProperties(event, Object.fromEntries(Object.entries({
    button: 0, clientX: 100, ...properties,
  }).map(([key, value]) => [key, { value }])));
  return event;
}

function createFixture(t, mode) {
  // Native EventTarget retains all listeners of a type, as the browser does.
  const windowObject = new EventTarget();
  // Node's boolean capture removal differs from DOM; normalize it to options.
  for (const method of ["addEventListener", "removeEventListener"]) {
    const nativeMethod = windowObject[method].bind(windowObject);
    windowObject[method] = (type, handler, options) => nativeMethod(type, handler,
      typeof options === "boolean" ? { capture: options } : options);
  }
  const frames = new Map();
  let frameId = 0;
  windowObject.requestAnimationFrame = (callback) => {
    frames.set(++frameId, callback);
    return frameId;
  };
  windowObject.cancelAnimationFrame = (id) => frames.delete(id);
  const originalWindow = globalThis.window;
  globalThis.window = windowObject;
  t.after(() => { globalThis.window = originalWindow; });
  const composition = mode === "composition";
  const main = mode === "main";
  const scroll = {
    scrollLeft: 20,
    dataset: {
      trackDomainSpanBp: "1000", trackInnerWidth: "100",
      subviewDomainSpanBp: "1000", subviewInnerWidth: "100",
      subviewViewboxMinX: "-30",
    },
    getBoundingClientRect: () => ({ left: 0 }),
  };
  const attributes = {
    "data-track-role": "primary", "data-track-contig-id": "3",
    "data-subview-track-slot": "bottom", "data-subview-contig-id": "3",
    "data-subview-composition-entity-key": composition ? "assembly:3" : "",
  };
  const track = {
    getAttribute: (name) => attributes[name] ?? null,
    closest: () => scroll,
  };
  const target = { closest: () => track };
  const commits = [];
  const previews = [];
  let persists = 0;
  let positionBp = 2000;
  const state = { assembly: { activeTab: "assembly" } };
  const store = { getState: () => state };
  const preview = (_host, payload) => previews.push(payload);
  const commit = (_host, _store, payload) => {
    commits.push(payload);
    positionBp = composition ? positionBp + payload.dragDeltaBp : payload.offsetBp;
  };
  const deps = {
    convertTrackOffsetPxToBp: (px) => px * 10,
    roundTrackMetric: (value) => value,
    resolveActiveTrackScrollElement: () => scroll,
    clearTrackDragPreview() {}, clearSubviewTrackDragPreview() {},
    setTrackContigDragActive() {}, setSuppressTrackContigClickUntil() {},
    resolveTrackDragOffsetBp: () => positionBp,
    resolveSubviewTrackDragOffsetBp: () => positionBp,
    previewTrackContigDrag: preview, previewSubviewTrackContigDrag: preview,
    commitTrackDragOffset: commit, applySubviewTrackDragOffset: commit,
    persistSubviewTrackDragOffsets: () => { persists += 1; },
  };
  const bind = (host) => (main ? bindTrackContigDrag : bindSubviewTrackContigDrag)(host, store, deps);
  return {
    bind, commits, previews, frames,
    get persists() { return persists; },
    get positionBp() { return positionBp; },
    down(hosts, properties = {}) {
      const event = pointerEvent("pointerdown", { target, ...properties });
      // Propagate the same event from the replaced panel to its retained route host.
      hosts.forEach((host) => host.dispatchEvent(event));
    },
    move(clientX) {
      windowObject.dispatchEvent(pointerEvent("pointermove", { clientX }));
      const callbacks = [...frames.values()];
      frames.clear();
      callbacks.forEach((callback) => callback());
    },
    up(clientX) { windowObject.dispatchEvent(pointerEvent("pointerup", { clientX })); },
    cancel() { windowObject.dispatchEvent(pointerEvent("pointercancel")); },
  };
}

for (const mode of ["composition", "pair", "main"]) {
  test(`${mode} drag commits once after panel replacement beneath a bound route host`, (t) => {
    const fixture = createFixture(t, mode);
    const route = new EventTarget();
    fixture.bind(route);
    fixture.bind(route);
    fixture.down([route]);
    fixture.move(130);
    fixture.up(130);
    assert.equal(fixture.commits.length, 1);
    assert.equal(fixture.positionBp, 2300);

    for (let gesture = 1; gesture <= 3; gesture += 1) {
      const panel = new EventTarget();
      panel.parentElement = route;
      fixture.bind(panel);
      const previousPreviews = fixture.previews.length;
      fixture.down([panel, route]);
      fixture.move(80);
      assert.equal(fixture.previews.length, previousPreviews + 1, "one preview per frame");
      fixture.up(80);
      assert.equal(fixture.commits.length, gesture + 1, "one commit per gesture");
      assert.equal(fixture.positionBp, 2300 - gesture * 200);
      assert.equal(fixture.frames.size, 0);
    }
    if (mode !== "main") assert.equal(fixture.persists, 4);
    fixture.move(200);
    fixture.up(200);
    assert.equal(fixture.commits.length, 4, "released listeners are removed");
  });
}

test("nested Subview cancellation and modified clicks leave the next drag usable", (t) => {
  const fixture = createFixture(t, "composition");
  const route = new EventTarget();
  const panel = new EventTarget();
  panel.parentElement = route;
  fixture.bind(route);
  fixture.bind(panel);
  for (const properties of [{ ctrlKey: true }, { metaKey: true }, { button: 2 }]) {
    fixture.down([panel, route], properties);
    fixture.move(150);
    fixture.up(150);
  }
  assert.equal(fixture.previews.length, 0);
  fixture.down([panel, route]);
  fixture.move(150);
  fixture.cancel();
  fixture.up(150);
  assert.equal(fixture.commits.length, 0);
  assert.equal(fixture.frames.size, 0);

  fixture.down([panel, route]);
  fixture.move(120);
  fixture.up(140);
  assert.equal(fixture.commits.length, 1);
  assert.equal(fixture.positionBp, 2400, "release still uses the final pointer position");
  assert.equal(fixture.persists, 1);
});
