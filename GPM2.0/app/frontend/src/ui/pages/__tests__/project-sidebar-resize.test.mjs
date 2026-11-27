import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { bindProjectSidebarResize, projectSidebarBounds, SIDEBAR_COLLAPSED_KEY } from "../project-sidebar-resize.js";
import { renderProjectsBody } from "../projects-view.js";
import { getMessages } from "../../i18n/index.js";

function fixture({ saved = null, blockedStorage = false, containerWidth = 1200 } = {}) {
  const listeners = new Map(), attributes = new Map(), classes = new Set();
  let stored = saved, writes = 0, captured = null, disconnected = false, notify;
  const style = new Map();
  const view = {
    getComputedStyle: () => ({ getPropertyValue: () => "280px" }),
    get localStorage() {
      if (blockedStorage) throw Error("Storage unavailable");
      return { getItem: () => stored, setItem: (_, value) => { stored = value; writes++; }, removeItem: () => { stored = null; } };
    },
    ResizeObserver: class {
      constructor(callback) { notify = callback; }
      observe() {}
      disconnect() { disconnected = true; }
    },
  };
  const browser = {
    ownerDocument: { defaultView: view }, isConnected: true,
    getBoundingClientRect: () => ({ width: containerWidth }),
    style: { setProperty: (key, value) => style.set(key, value) },
    classList: { add: name => classes.add(name), remove: name => classes.delete(name) },
  };
  const handle = {
    setAttribute: (key, value) => attributes.set(key, value),
    addEventListener: (key, fn) => { assert.ok(!listeners.has(key)); listeners.set(key, fn); },
    removeEventListener: key => listeners.delete(key), focus() {},
    setPointerCapture: id => { captured = id; }, hasPointerCapture: id => captured === id,
    releasePointerCapture: () => { captured = null; },
  };
  const host = { querySelector: selector => selector === ".project-browser" ? browser : handle };
  return {
    host, browser, classes, attributes, view,
    event(type, props = {}) {
      const event = { button: 0, pointerId: 1, clientX: 280, preventDefault() { this.prevented = true; }, ...props };
      listeners.get(type)?.(event);
      return event;
    },
    resize(width = containerWidth) { containerWidth = width; notify(); },
    get width() { return Number.parseInt(style.get("--project-sidebar-width")); },
    get stored() { return stored; }, get writes() { return writes; },
    get captured() { return captured; }, get disconnected() { return disconnected; },
    get listenerCount() { return listeners.size; },
  };
}

test("sidebar bounds protect both the library and detail without exceeding the maximum", () => {
  assert.deepEqual(projectSidebarBounds(1800), { min: 220, max: 560 });
  assert.deepEqual(projectSidebarBounds(800), { min: 220, max: 400 });
  assert.deepEqual(projectSidebarBounds(500), { min: 220, max: 220 });
});

test("pointer capture resizes immediately, clamps, and persists only the finished gesture", () => {
  const f = fixture(); bindProjectSidebarResize(f.host);
  f.event("pointerdown");
  assert.equal(f.captured, 1);
  f.event("pointermove", { clientX: 400 });
  assert.equal(f.width, 400);
  assert.equal(f.writes, 0);
  f.resize(); // Initial / height-only observer delivery must not interrupt dragging.
  assert.ok(f.classes.has("is-sidebar-resizing"));
  f.event("pointermove", { clientX: 900, pointerId: 2 });
  assert.equal(f.width, 400);
  f.event("pointermove", { clientX: 900 });
  assert.equal(f.width, 560);
  f.event("pointerup", { clientX: 460 });
  assert.equal(f.width, 460);
  assert.equal(f.stored, "460");
  assert.equal(f.writes, 1);
  assert.equal(f.captured, null);
  assert.equal(f.classes.size, 0);
  assert.equal(f.attributes.get("aria-valuenow"), "460");
});

for (const ending of ["pointercancel", "lostpointercapture", "Escape"]) {
  test(`${ending} restores the width without saving an interrupted drag`, () => {
    const f = fixture({ saved: "320" }); bindProjectSidebarResize(f.host);
    f.event("pointerdown"); f.event("pointermove", { clientX: 40 });
    assert.equal(f.width, 220);
    if (ending === "Escape") f.event("keydown", { key: "Escape" });
    else f.event(ending);
    assert.equal(f.width, 320);
    assert.equal(f.stored, "320");
    assert.equal(f.writes, 0);
    assert.equal(f.classes.size, 0);
  });
}

test("secondary mouse buttons and non-primary pointers do not start drags", () => {
  const f = fixture(); bindProjectSidebarResize(f.host);
  f.event("pointerdown", { button: 2 });
  f.event("pointerdown", { isPrimary: false });
  f.event("pointermove", { clientX: 500 });
  assert.equal(f.width, 280); assert.equal(f.captured, null);
});

test("keyboard resizing, bounds, and double-click reset update the accessible separator", () => {
  const f = fixture({ containerWidth: 800 }); bindProjectSidebarResize(f.host);
  assert.ok(f.event("keydown", { key: "ArrowRight" }).prevented);
  assert.equal(f.width, 290);
  f.event("keydown", { key: "ArrowLeft", shiftKey: true }); assert.equal(f.width, 250);
  f.event("keydown", { key: "End" }); assert.equal(f.width, 400);
  f.event("keydown", { key: "Home" }); assert.equal(f.width, 220);
  assert.equal(f.attributes.get("aria-valuemax"), "400");
  assert.ok(!f.event("keydown", { key: "Tab" }).prevented);
  f.event("dblclick"); assert.equal(f.width, 280); assert.equal(f.stored, null);
});

test("window resizing clamps but retains preferred width for later expansion and rebind", () => {
  const f = fixture({ saved: "520" }); bindProjectSidebarResize(f.host);
  f.resize(800); assert.equal(f.width, 400); assert.equal(f.stored, "520");
  f.resize(1400); assert.equal(f.width, 520);
  bindProjectSidebarResize(f.host); // no duplicate handlers
  assert.equal(f.width, 520);
  f.event("keydown", { key: "ArrowLeft" }); assert.equal(f.width, 510);
});

test("rebinding, explicit disposal and route removal clean up observers and pointer state", () => {
  const f = fixture(); const dispose = bindProjectSidebarResize(f.host);
  f.event("pointerdown"); dispose(); dispose();
  assert.equal(f.listenerCount, 0); assert.equal(f.captured, null); assert.ok(f.disconnected);
  bindProjectSidebarResize(f.host);
  dispose(); // A stale cleanup must not unregister the replacement binding.
  bindProjectSidebarResize(f.host);
  f.browser.isConnected = false; f.resize(0);
  assert.equal(f.listenerCount, 0); assert.equal(f.classes.size, 0);
  assert.doesNotThrow(() => bindProjectSidebarResize({ querySelector: () => null }));
});

test("invalid or blocked storage cannot prevent resizing", () => {
  for (const options of [{ saved: "NaN" }, { saved: "Infinity" }, { saved: "-30" }, { saved: "9000" }, { blockedStorage: true }]) {
    const f = fixture(options); bindProjectSidebarResize(f.host);
    assert.equal(f.width, 280);
    f.event("keydown", { key: "ArrowRight" }); assert.equal(f.width, 290);
    f.event("dblclick"); assert.equal(f.width, 280);
  }
});

for (const locale of ["en", "zh"]) test(`splitter sits between library and detail with a localized accessible label (${locale})`, () => {
  const state = { locale, session: {}, importer: {}, initializer: {} };
  const render = records => renderProjectsBody(state, { records, messages: getMessages(state, "importer"), summaryHtml: '<section class="project-current">Detail</section>' });
  const html = render([{ path: "/rice" }]);
  assert.match(html, /id="project-recents"[\s\S]*class="project-sidebar-splitter"[\s\S]*class="project-current"/);
  assert.match(html, /role="separator" tabindex="0" aria-orientation="vertical" aria-controls="project-recents"/);
  assert.ok(html.includes(locale === "en" ? "Resize project library" : "调整项目库宽度"));
  assert.match(render([]), /project-sidebar-splitter/);
});

test("splitter CSS keeps a generous hit area on the existing border and hides it in stacked mode", () => {
  const css = readFileSync(new URL("../../../styles/importer.css", import.meta.url), "utf8");
  assert.match(css, /grid-template-columns: var\(--project-sidebar-width, var\(--project-sidebar-default\)\) 0 minmax\(0, 1fr\)/);
  assert.match(css, /\.project-browser\.is-sidebar-collapsed \{ grid-template-columns: 48px minmax\(0, 1fr\); \}/);
  assert.match(css, /\.project-browser\.is-sidebar-collapsed \.library-search,/);
  assert.match(css, /\.project-sidebar-splitter \{[^}]*width: 10px;[^}]*cursor: col-resize;[^}]*touch-action: none;/);
  assert.match(css, /@media \(max-width: 760px\)[\s\S]*\.project-sidebar-splitter \{ display: none; \}/);
  assert.match(css, /\.project-sidebar-splitter:focus-visible/);
  assert.match(css, /\.project-dataset-table \{[^}]*table-layout: fixed;/);
  assert.match(css, /\.project-dataset-table thead th:nth-child\(2\),[\s\S]*width: 19%;/);
  assert.match(css, /\.project-dataset-table \.numeric \{[^}]*text-align: left;/);
});

test("sidebar collapse toggle switches to the narrow icon rail, persists state, and restores width on expand", () => {
  const storeMap = new Map();
  const classes = new Set();
  const style = new Map();
  const makeNode = (dataset = {}, attrs = {}) => {
    const listeners = new Map();
    const map = new Map(Object.entries(attrs));
    return {
      dataset,
      innerHTML: "",
      addEventListener: (type, fn) => listeners.set(type, fn),
      removeEventListener: type => listeners.delete(type),
      setAttribute: (k, v) => map.set(k, v),
      getAttribute: k => map.get(k) || "",
      removeAttribute: k => map.delete(k),
      attrs: map,
      click: () => listeners.get("click")?.({}),
    };
  };
  const toggleBtn = makeNode({ collapseLabel: "Collapse library", expandLabel: "Expand library" });
  const expandRailBtn = makeNode();
  const importBtn = makeNode({}, { "aria-label": "Import" });
  const openBtn = makeNode({}, { "aria-label": "Open" });
  const view = {
    getComputedStyle: () => ({ getPropertyValue: () => "280px" }),
    localStorage: {
      getItem: key => storeMap.get(key) ?? null,
      setItem: (key, value) => storeMap.set(key, value),
      removeItem: key => storeMap.delete(key),
    },
  };
  const browser = {
    ownerDocument: { defaultView: view },
    isConnected: true,
    getBoundingClientRect: () => ({ width: 1200 }),
    style: { setProperty: (key, value) => style.set(key, value) },
    classList: { add: name => classes.add(name), remove: name => classes.delete(name) },
    querySelector(selector) {
      if (selector === "[data-project-sidebar-toggle]") return toggleBtn;
      if (selector === "[data-project-sidebar-expand]") return expandRailBtn;
      if (selector === "#project-import-button") return importBtn;
      if (selector === "#project-open-button") return openBtn;
      return null;
    },
  };
  const handle = { setAttribute() {}, addEventListener() {}, removeEventListener() {}, hasPointerCapture: () => false };
  const host = { querySelector: selector => selector === ".project-browser" ? browser : handle };

  bindProjectSidebarResize(host);
  assert.equal(classes.has("is-sidebar-collapsed"), false);
  assert.equal(importBtn.attrs.has("data-app-tooltip"), false);

  toggleBtn.click();
  assert.equal(classes.has("is-sidebar-collapsed"), true);
  assert.equal(storeMap.get(SIDEBAR_COLLAPSED_KEY), "1");
  assert.equal(toggleBtn.attrs.get("aria-expanded"), "false");
  assert.equal(toggleBtn.attrs.get("data-app-tooltip"), "Expand library");
  assert.equal(importBtn.attrs.get("data-app-tooltip"), "Import");
  assert.equal(openBtn.attrs.get("data-app-tooltip"), "Open");

  expandRailBtn.click();
  assert.equal(classes.has("is-sidebar-collapsed"), false);
  assert.equal(storeMap.has(SIDEBAR_COLLAPSED_KEY), false);
  assert.equal(toggleBtn.attrs.get("aria-expanded"), "true");
  assert.equal(importBtn.attrs.has("data-app-tooltip"), false);
});
