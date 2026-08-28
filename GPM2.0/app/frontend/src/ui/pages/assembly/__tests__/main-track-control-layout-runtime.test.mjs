import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  bindMainTrackControlLayout,
  measureMainTrackControlLayout,
  resolveMainTrackControlLayout,
} from "../main-track-control-layout-runtime.js";
import {
  createState,
  readStylesheetTree,
  renderAssemblyPage,
} from "./tabs-semantics-harness.mjs";

function createMeasuredNode(width, children = []) {
  return {
    children,
    getBoundingClientRect() {
      return { width: Number(width.value ?? width) || 0 };
    },
  };
}

function createLayoutFixture({ availableWidth = 900 } = {}) {
  const headerWidth = { value: availableWidth };
  const title = createMeasuredNode(100);
  const quickActions = createMeasuredNode(0, [
    createMeasuredNode(120),
    createMeasuredNode(90),
  ]);
  const inlineControls = createMeasuredNode(0, [
    createMeasuredNode(150),
    createMeasuredNode(170),
    createMeasuredNode(190),
    createMeasuredNode(94),
  ]);
  const actions = createMeasuredNode(0);
  const selectors = new Map([
    ["[data-main-track-control-title]", title],
    ["[data-main-track-control-actions]", actions],
    ["[data-main-track-quick-actions]", quickActions],
    ["[data-main-track-inline-controls]", inlineControls],
  ]);
  const header = {
    dataset: { mainTrackControlLayout: "auto" },
    isConnected: true,
    children: [],
    getBoundingClientRect() {
      return { width: headerWidth.value };
    },
    querySelector(selector) {
      return selectors.get(selector) || null;
    },
  };
  const host = {
    matches() {
      return false;
    },
    querySelectorAll(selector) {
      return selector === "[data-main-track-control-layout]" ? [header] : [];
    },
  };
  return { host, header, headerWidth, title, quickActions, inlineControls, actions };
}

function getFixtureStyle(node, fixture) {
  if (node === fixture.header || node === fixture.actions) {
    return { columnGap: "8px" };
  }
  if (node === fixture.quickActions || node === fixture.inlineControls) {
    return { columnGap: "8px" };
  }
  return { columnGap: "0px" };
}

test("main-track control layout is selected from measured widths instead of viewport breakpoints", () => {
  const widths = {
    titleWidth: 100,
    quickActionsWidth: 210,
    inlineControlsWidth: 628,
    headerGap: 8,
    actionsGap: 8,
  };

  assert.equal(resolveMainTrackControlLayout({ ...widths, availableWidth: 954 }), "single");
  assert.equal(resolveMainTrackControlLayout({ ...widths, availableWidth: 700 }), "split");
  assert.equal(resolveMainTrackControlLayout({ ...widths, availableWidth: 300 }), "stacked");
});

test("main-track control measurement sums live child widths and computed gaps", () => {
  const fixture = createLayoutFixture({ availableWidth: 1_000 });
  assert.deepEqual(
    measureMainTrackControlLayout(fixture.header, {
      getComputedStyle: (node) => getFixtureStyle(node, fixture),
    }),
    {
      availableWidth: 1_000,
      titleWidth: 100,
      quickActionsWidth: 218,
      inlineControlsWidth: 628,
      headerGap: 8,
      actionsGap: 8,
    },
  );
});

test("ResizeObserver recomputes layout and repeated binding stays idempotent", () => {
  const fixture = createLayoutFixture({ availableWidth: 1_000 });
  const observers = [];
  const frames = [];
  class FakeResizeObserver {
    constructor(callback) {
      this.callback = callback;
      this.observed = [];
      this.disconnected = false;
      observers.push(this);
    }

    observe(node) {
      this.observed.push(node);
    }

    disconnect() {
      this.disconnected = true;
    }
  }
  const options = {
    ResizeObserver: FakeResizeObserver,
    getComputedStyle: (node) => getFixtureStyle(node, fixture),
    requestAnimationFrame(callback) {
      frames.push(callback);
      return frames.length;
    },
    cancelAnimationFrame() {},
  };

  bindMainTrackControlLayout(fixture.host, options);
  assert.equal(fixture.header.dataset.mainTrackControlLayout, "single");
  assert.equal(observers.length, 1);
  assert.equal(observers[0].observed.length, 4);

  fixture.headerWidth.value = 800;
  observers[0].callback();
  assert.equal(frames.length, 1);
  frames.shift()();
  assert.equal(fixture.header.dataset.mainTrackControlLayout, "split");

  fixture.headerWidth.value = 280;
  observers[0].callback();
  frames.shift()();
  assert.equal(fixture.header.dataset.mainTrackControlLayout, "stacked");

  bindMainTrackControlLayout(fixture.host, options);
  assert.equal(observers.length, 1);

  fixture.header.isConnected = false;
  observers[0].callback();
  assert.equal(observers[0].disconnected, true);
});

test("window resize fallback is installed and removed when ResizeObserver is unavailable", () => {
  const fixture = createLayoutFixture({ availableWidth: 1_000 });
  const listeners = new Map();
  const frames = [];
  const windowObject = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    removeEventListener(type, handler) {
      if (listeners.get(type) === handler) {
        listeners.delete(type);
      }
    },
  };
  const cleanup = bindMainTrackControlLayout(fixture.host, {
    ResizeObserver: null,
    windowObject,
    getComputedStyle: (node) => getFixtureStyle(node, fixture),
    requestAnimationFrame(callback) {
      frames.push(callback);
      return frames.length;
    },
    cancelAnimationFrame() {},
  });

  assert.equal(listeners.has("resize"), true);
  fixture.headerWidth.value = 800;
  listeners.get("resize")?.();
  frames.shift()();
  assert.equal(fixture.header.dataset.mainTrackControlLayout, "split");

  cleanup();
  assert.equal(listeners.has("resize"), false);
});

test("main-track markup and CSS expose content-driven layouts without header media breakpoints", () => {
  const html = renderAssemblyPage(createState());
  const css = readStylesheetTree(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );
  const assemblyCss = readFileSync(
    new URL("../../../../styles/assembly.css", import.meta.url),
    "utf8",
  );

  assert.match(html, /data-main-track-control-layout="auto"/);
  assert.match(html, /data-main-track-control-title/);
  assert.match(html, /data-main-track-control-actions/);
  assert.match(html, /data-main-track-quick-actions/);
  assert.match(html, /data-main-track-inline-controls/);
  assert.match(css, /data-main-track-control-layout="single"/);
  assert.match(css, /data-main-track-control-layout="split"/);
  assert.match(css, /data-main-track-control-layout="stacked"/);
  const fixedViewportRules = assemblyCss.slice(assemblyCss.indexOf("@media (max-width: 1200px)"));
  assert.doesNotMatch(fixedViewportRules, /\.assembly-track-inline-controls\s*\{/);
});
