import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { bindStickyCtgLabels, resolveStickyLabelDisplay } from "../sticky-ctg-label-runtime.js";

function createClassList(initial = []) {
  const values = new Set(initial);
  return {
    add(...nextValues) {
      nextValues.forEach((value) => values.add(value));
    },
    remove(...nextValues) {
      nextValues.forEach((value) => values.delete(value));
    },
    contains(value) {
      return values.has(value);
    },
    toggle(value, force) {
      if (force === true) {
        values.add(value);
        return true;
      }
      if (force === false) {
        values.delete(value);
        return false;
      }
      if (values.has(value)) {
        values.delete(value);
        return false;
      }
      values.add(value);
      return true;
    },
    toString() {
      return Array.from(values).join(" ");
    },
  };
}

function matchesSelector(node, selector) {
  if (!node) {
    return false;
  }
  const classMatches = Array.from(selector.matchAll(/\.([a-zA-Z0-9_-]+)/g)).map((match) => match[1]);
  if (classMatches.some((className) => !node.classList.contains(className))) {
    return false;
  }
  const attrMatches = Array.from(selector.matchAll(/\[([a-zA-Z0-9_-]+)(?:=['"]?([^'"\]]+)['"]?)?\]/g));
  return attrMatches.every(([, attrName, attrValue]) => {
    const actualValue = node.getAttribute(attrName);
    if (actualValue === null) {
      return false;
    }
    if (typeof attrValue === "string" && attrValue.length > 0) {
      return actualValue === attrValue;
    }
    return true;
  });
}

function collectMatchingNodes(root, selector, results = []) {
  if (!root?.children) {
    return results;
  }
  root.children.forEach((child) => {
    if (matchesSelector(child, selector)) {
      results.push(child);
    }
    collectMatchingNodes(child, selector, results);
  });
  return results;
}

function createElement(tagName, options = {}) {
  const attributes = new Map();
  const classList = createClassList(options.classNames || []);
  const listeners = new Map();
  const element = {
    tagName,
    dataset: { ...(options.dataset || {}) },
    style: {},
    children: [],
    parentNode: null,
    textContent: options.textContent || "",
    classList,
    listeners,
    appendChild(child) {
      child.parentNode = element;
      element.children.push(child);
      return child;
    },
    removeChild(child) {
      element.children = element.children.filter((item) => item !== child);
      child.parentNode = null;
      return child;
    },
    remove() {
      element.parentNode?.removeChild(element);
    },
    addEventListener(type, handler) {
      const handlers = listeners.get(type) || [];
      handlers.push(handler);
      listeners.set(type, handlers);
    },
    querySelector(selector) {
      return collectMatchingNodes(element, selector, [])[0] || null;
    },
    querySelectorAll(selector) {
      return collectMatchingNodes(element, selector, []);
    },
    setAttribute(name, value) {
      const stringValue = String(value);
      attributes.set(name, stringValue);
      if (name === "class") {
        classList.remove(...classList.toString().split(" ").filter(Boolean));
        stringValue.split(" ").filter(Boolean).forEach((className) => classList.add(className));
      }
      if (name.startsWith("data-")) {
        const datasetKey = name
          .slice(5)
          .replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        element.dataset[datasetKey] = stringValue;
      }
    },
    getAttribute(name) {
      if (name === "class") {
        return classList.toString();
      }
      if (attributes.has(name)) {
        return attributes.get(name);
      }
      if (name.startsWith("data-")) {
        const datasetKey = name
          .slice(5)
          .replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        return element.dataset[datasetKey] ?? null;
      }
      return null;
    },
  };
  if (options.attributes) {
    Object.entries(options.attributes).forEach(([name, value]) => {
      element.setAttribute(name, value);
    });
  }
  return element;
}

function createRuntimeDocument() {
  return {
    createElement(tagName) {
      return createElement(tagName);
    },
  };
}

function createMainTrackRuntimeFixture({ scrollLeft = 40, rectX = 10, rectWidth = 120, labelText = "ctg-alpha" } = {}) {
  const originalLabel = createElement("text", {
    classNames: ["track-ctg-label"],
    textContent: labelText,
    attributes: {
      "data-track-label-for-contig-id": "2",
      "data-track-label-role": "primary",
      "data-track-label-is-mirror": "0",
    },
  });
  const group = createElement("g", {
    classNames: ["track-ctg-group"],
    attributes: {
      "data-track-contig-id": "2",
      "data-track-role": "primary",
      "data-track-is-mirror": "0",
      "data-track-contig-name": labelText,
      "data-track-rect-x": String(rectX),
      "data-track-rect-y": "20",
      "data-track-rect-width": String(rectWidth),
      "data-track-rect-height": "14",
    },
  });
  const scrollEl = createElement("div", {
    classNames: ["assembly-track-scroll"],
    dataset: {
      trackRole: "primary",
      trackViewboxMinX: "0",
    },
  });
  scrollEl.clientWidth = 100;
  scrollEl.clientHeight = 80;
  scrollEl.scrollLeft = scrollLeft;
  scrollEl.appendChild(group);
  scrollEl.appendChild(originalLabel);
  const host = createElement("section");
  host.appendChild(scrollEl);
  return {
    host,
    scrollEl,
    originalLabel,
  };
}

function createPhasedTrackRuntimeFixture({
  scrollLeft = 40,
  rectX = 10,
  rectWidth = 120,
  labelText = "ctg-phased",
  contigId = "8",
  phasedTrackId = "101",
  phasedTrackItemId = "9001",
} = {}) {
  const originalLabel = createElement("text", {
    classNames: ["track-ctg-label"],
    textContent: labelText,
    attributes: {
      "data-track-label-for-contig-id": contigId,
      "data-track-label-role": "phased",
      "data-track-label-is-mirror": "0",
      "data-track-label-phased-track-id": phasedTrackId,
      "data-track-label-phased-track-item-id": phasedTrackItemId,
    },
  });
  const group = createElement("g", {
    classNames: ["track-ctg-group"],
    attributes: {
      "data-track-contig-id": contigId,
      "data-track-role": "phased",
      "data-track-is-mirror": "0",
      "data-track-contig-name": labelText,
      "data-track-phased-track-id": phasedTrackId,
      "data-track-phased-track-item-id": phasedTrackItemId,
      "data-track-rect-x": String(rectX),
      "data-track-rect-y": "20",
      "data-track-rect-width": String(rectWidth),
      "data-track-rect-height": "14",
    },
  });
  const scrollEl = createElement("div", {
    classNames: ["assembly-track-scroll"],
    dataset: {
      trackRole: "primary",
      trackViewboxMinX: "0",
    },
  });
  scrollEl.clientWidth = 100;
  scrollEl.clientHeight = 80;
  scrollEl.scrollLeft = scrollLeft;
  scrollEl.appendChild(group);
  scrollEl.appendChild(originalLabel);
  const host = createElement("section");
  host.appendChild(scrollEl);
  return {
    host,
    scrollEl,
    originalLabel,
  };
}

function createSubviewRuntimeFixture({
  scrollLeft = 60,
  rectX = 10,
  rectWidth = 140,
  labelText = "support-top",
  slot = "top",
  role = "support",
  contigId = "30",
} = {}) {
  const originalLabel = createElement("text", {
    classNames: ["track-ctg-label", role === "support" ? "is-companion" : ""].filter(Boolean),
    textContent: labelText,
    attributes: {
      "data-subview-label-slot": slot,
      "data-subview-label-role": role,
      "data-subview-label-contig-id": contigId,
    },
  });
  const group = createElement("g", {
    classNames: ["subview-track-ctg-group", role === "support" ? "is-companion" : ""].filter(Boolean),
    attributes: {
      "data-subview-track-slot": slot,
      "data-subview-track-role": role,
      "data-subview-contig-id": contigId,
      "data-subview-rect-x": String(rectX),
      "data-subview-rect-y": "36",
      "data-subview-rect-width": String(rectWidth),
      "data-subview-rect-height": "14",
    },
  });
  const scrollEl = createElement("div", {
    classNames: ["assembly-track-scroll", "subview-track-scroll"],
    dataset: {
      trackRole: "subview",
      subviewViewboxMinX: "0",
    },
  });
  scrollEl.clientWidth = 100;
  scrollEl.clientHeight = 96;
  scrollEl.scrollLeft = scrollLeft;
  scrollEl.appendChild(group);
  scrollEl.appendChild(originalLabel);
  const host = createElement("section");
  host.appendChild(scrollEl);
  return {
    host,
    scrollEl,
    originalLabel,
  };
}

test("left-clipped visible ctg uses sticky mode when label fits visible width", () => {
  assert.deepEqual(
    resolveStickyLabelDisplay({
      rectX: 100,
      rectWidth: 160,
      viewportLeft: 120,
      viewportRight: 260,
      labelWidth: 60,
    }),
    {
      showSticky: true,
      hideOriginal: true,
      stickyLeft: 120,
      visibleLeft: 120,
      visibleRight: 260,
      visibleWidth: 140,
    },
  );
});

test("left-clipped ctg suppresses sticky label when text would exceed visible right edge", () => {
  const result = resolveStickyLabelDisplay({
    rectX: 100,
    rectWidth: 50,
    viewportLeft: 120,
    viewportRight: 160,
    labelWidth: 45,
  });

  assert.deepEqual(result, {
    showSticky: false,
    hideOriginal: true,
    stickyLeft: null,
    visibleLeft: 120,
    visibleRight: 150,
    visibleWidth: 30,
  });
});

test("fully hidden ctg shows no sticky label and does not force label hiding", () => {
  const result = resolveStickyLabelDisplay({
    rectX: 0,
    rectWidth: 40,
    viewportLeft: 100,
    viewportRight: 200,
    labelWidth: 20,
  });

  assert.deepEqual(result, {
    showSticky: false,
    hideOriginal: false,
    stickyLeft: null,
    visibleLeft: null,
    visibleRight: null,
    visibleWidth: 0,
  });
});

test("visible left edge keeps the original label active", () => {
  const result = resolveStickyLabelDisplay({
    rectX: 120,
    rectWidth: 80,
    viewportLeft: 100,
    viewportRight: 220,
    labelWidth: 40,
  });

  assert.deepEqual(result, {
    showSticky: false,
    hideOriginal: false,
    stickyLeft: null,
    visibleLeft: 120,
    visibleRight: 200,
    visibleWidth: 80,
  });
});

test("right-clipped but left-visible ctg does not enter sticky mode", () => {
  const result = resolveStickyLabelDisplay({
    rectX: 120,
    rectWidth: 120,
    viewportLeft: 100,
    viewportRight: 180,
    labelWidth: 30,
  });

  assert.equal(result.showSticky, false);
  assert.equal(result.hideOriginal, false);
  assert.equal(result.visibleLeft, 120);
  assert.equal(result.visibleRight, 180);
  assert.equal(result.visibleWidth, 60);
});

test("invalid geometry returns no sticky label decision", () => {
  const result = resolveStickyLabelDisplay({
    rectX: Number.NaN,
    rectWidth: 0,
    viewportLeft: 100,
    viewportRight: 200,
    labelWidth: 20,
  });

  assert.deepEqual(result, {
    showSticky: false,
    hideOriginal: false,
    stickyLeft: null,
    visibleLeft: null,
    visibleRight: null,
    visibleWidth: 0,
  });
});

test("bindStickyCtgLabels creates one overlay layer per scroll container and keeps it idempotent", () => {
  const { host, scrollEl } = createMainTrackRuntimeFixture();
  const documentStub = createRuntimeDocument();

  bindStickyCtgLabels(host, { document: documentStub });
  bindStickyCtgLabels(host, { document: documentStub });

  assert.equal(scrollEl.querySelectorAll(".track-sticky-label-layer").length, 1);
  assert.equal((scrollEl.listeners.get("scroll") || []).length, 1);
});

test("bindStickyCtgLabels keeps the overlay layer aligned to the live scroll viewport", () => {
  const { host, scrollEl } = createMainTrackRuntimeFixture();
  const documentStub = createRuntimeDocument();

  bindStickyCtgLabels(host, { document: documentStub });

  const layer = scrollEl.querySelector(".track-sticky-label-layer");
  assert.ok(layer, "expected sticky overlay layer");
  assert.equal(layer.style.left, "40px");
  assert.equal(layer.style.width, "100px");

  scrollEl.scrollLeft = 12;
  const [onScroll] = scrollEl.listeners.get("scroll") || [];
  onScroll?.();

  assert.equal(layer.style.left, "12px");
  assert.equal(layer.style.width, "100px");
});

test("bindStickyCtgLabels shows a sticky label for a left-clipped visible main-track ctg", () => {
  const { host, scrollEl, originalLabel } = createMainTrackRuntimeFixture();
  const documentStub = createRuntimeDocument();

  bindStickyCtgLabels(host, { document: documentStub });

  const stickyLabel = scrollEl.querySelector('[data-sticky-label-key="track:primary:2:0"]');
  assert.ok(stickyLabel, "expected sticky label for left-clipped ctg");
  assert.equal(stickyLabel.textContent, "ctg-alpha");
  assert.equal(originalLabel.classList.contains("is-sticky-hidden"), true);
});

test("bindStickyCtgLabels preserves ref label classes on the sticky overlay", () => {
  const { host, scrollEl, originalLabel } = createMainTrackRuntimeFixture();
  const documentStub = createRuntimeDocument();
  originalLabel.setAttribute("class", "track-ctg-label track-reference-member-label is-ref");
  originalLabel.setAttribute("data-track-label-role", "ref");
  const group = scrollEl.querySelector('[data-track-contig-id="2"]');
  group.setAttribute("data-track-role", "ref");

  bindStickyCtgLabels(host, { document: documentStub });

  const stickyLabel = scrollEl.querySelector('[data-sticky-label-key="track:ref:2:0"]');
  assert.ok(stickyLabel, "expected sticky label for ref member");
  assert.equal(stickyLabel.classList.contains("track-reference-member-label"), true);
  assert.equal(stickyLabel.classList.contains("is-ref"), true);
});

test("bindStickyCtgLabels keys phased sticky labels by phased item id", () => {
  const { host, scrollEl, originalLabel } = createPhasedTrackRuntimeFixture();
  const documentStub = createRuntimeDocument();

  bindStickyCtgLabels(host, { document: documentStub });

  const stickyLabel = scrollEl.querySelector('[data-sticky-label-key="track:phased:8:0:item:9001"]');
  assert.ok(stickyLabel, "expected phased sticky label keyed by item id");
  assert.equal(stickyLabel.textContent, "ctg-phased");
  assert.equal(originalLabel.classList.contains("is-sticky-hidden"), true);
});

test("bindStickyCtgLabels restores the original label when the ctg left edge re-enters the viewport", () => {
  const { host, scrollEl, originalLabel } = createMainTrackRuntimeFixture();
  const documentStub = createRuntimeDocument();

  bindStickyCtgLabels(host, { document: documentStub });
  scrollEl.scrollLeft = 0;
  const [onScroll] = scrollEl.listeners.get("scroll") || [];
  onScroll?.();

  assert.equal(scrollEl.querySelectorAll(".track-sticky-label").length, 0);
  assert.equal(originalLabel.classList.contains("is-sticky-hidden"), false);
});

test("left-clipped ctg with too little visible width hides the original label without rendering sticky text", () => {
  const { host, scrollEl, originalLabel } = createMainTrackRuntimeFixture({
    scrollLeft: 40,
    rectX: 10,
    rectWidth: 45,
    labelText: "ctg-too-wide",
  });
  const documentStub = createRuntimeDocument();

  bindStickyCtgLabels(host, { document: documentStub });

  assert.equal(scrollEl.querySelectorAll(".track-sticky-label").length, 0);
  assert.equal(originalLabel.classList.contains("is-sticky-hidden"), true);
});

test("bindStickyCtgLabels supports subview labels using subview geometry metadata", () => {
  const { host, scrollEl, originalLabel } = createSubviewRuntimeFixture();
  const documentStub = createRuntimeDocument();

  bindStickyCtgLabels(host, { document: documentStub });

  const stickyLabel = scrollEl.querySelector('[data-sticky-label-key="subview:top:support:30"]');
  assert.ok(stickyLabel, "expected subview sticky label");
  assert.equal(stickyLabel.textContent, "support-top");
  assert.equal(originalLabel.classList.contains("is-sticky-hidden"), true);
});

test("off-screen ctgs do not render sticky labels", () => {
  const { host, scrollEl, originalLabel } = createMainTrackRuntimeFixture({
    scrollLeft: 160,
    rectX: 10,
    rectWidth: 40,
    labelText: "ctg-hidden",
  });
  const documentStub = createRuntimeDocument();

  bindStickyCtgLabels(host, { document: documentStub });

  assert.equal(scrollEl.querySelectorAll(".track-sticky-label").length, 0);
  assert.equal(originalLabel.classList.contains("is-sticky-hidden"), false);
});

test("sticky ctg label css defines overlay and hidden-label rules", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.track-sticky-label-layer\s*\{[^}]*position:\s*absolute;[^}]*top:\s*0;[^}]*height:\s*100%;[^}]*z-index:\s*4;/,
  );
  assert.match(css, /\.track-sticky-label\s*\{/);
  assert.match(css, /\.track-ctg-label\.is-sticky-hidden\s*\{[\s\S]*display:\s*none;/);
});
