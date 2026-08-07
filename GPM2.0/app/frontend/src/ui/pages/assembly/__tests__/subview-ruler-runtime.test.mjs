import test from "node:test";
import assert from "node:assert/strict";
import {
  bindSubviewRulerRuntime,
  buildVisibleSubviewRulerMarkup,
  buildVisibleSubviewRulerTicks,
} from "../subview-ruler-runtime.js";

function createRulerFixture({ scrollLeft = 0, clientWidth = 1200 } = {}) {
  const listeners = new Map();
  const layer = {
    dataset: {
      subviewRulerWindowStart: "0",
      subviewRulerWindowEnd: "43726252",
      subviewRulerTickBp: "1000",
      subviewRulerInnerWidth: "7430000",
      subviewRulerDomainSpanBp: "43726252",
      subviewRulerTickY1: "52",
      subviewRulerTickY2: "130",
      subviewRulerTickLabelY: "46",
      subviewRulerEdgeLabelPadding: "16",
    },
    innerHTML: "",
  };
  const scrollNode = {
    dataset: {
      subviewViewboxMinX: "-80",
    },
    scrollLeft,
    clientWidth,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    querySelector(selector) {
      return selector === "[data-subview-virtual-ruler='1']" ? layer : null;
    },
  };
  const host = {
    querySelectorAll(selector) {
      return selector === ".subview-track-scroll" ? [scrollNode] : [];
    },
  };
  return { host, layer, scrollNode, listeners };
}

test("visible Subview ruler ticks stay bounded for a 43.7 Mb 1 kb domain", () => {
  const ticks = buildVisibleSubviewRulerTicks({
    windowStart: 0,
    windowEnd: 43_726_252,
    tickBp: 1_000,
    innerWidth: 7_430_000,
    domainSpanBp: 43_726_252,
    viewportLeft: 0,
    viewportWidth: 1_200,
    edgeLabelPadding: 16,
  });

  assert.ok(ticks.length <= 20, `expected a bounded ruler, got ${ticks.length} ticks`);
  assert.equal(ticks[0].bp, 0);
  assert.ok(ticks.at(-1).bp < 43_726_252);
});

test("visible Subview ruler includes the endpoint when the viewport reaches the domain end", () => {
  const ticks = buildVisibleSubviewRulerTicks({
    windowStart: 0,
    windowEnd: 43_726_252,
    tickBp: 1_000,
    innerWidth: 7_430_000,
    domainSpanBp: 43_726_252,
    viewportLeft: 7_428_800,
    viewportWidth: 1_200,
    edgeLabelPadding: 16,
  });

  assert.equal(ticks.at(-1).bp, 43_726_252);
  assert.match(ticks.at(-1).labelText, /43,726,252 bp/);
});

test("Subview ruler runtime updates only the bounded layer while scrolling", () => {
  const fixture = createRulerFixture();
  const queuedFrames = [];
  const previousRequestAnimationFrame = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (callback) => {
    queuedFrames.push(callback);
    return queuedFrames.length;
  };
  try {
    bindSubviewRulerRuntime(fixture.host);
    const initialMarkup = fixture.layer.innerHTML;
    assert.ok(initialMarkup.length > 0);
    assert.ok((initialMarkup.match(/track-tick-guide/g) || []).length <= 20);

    fixture.scrollNode.scrollLeft = 7_428_880;
    fixture.listeners.get("scroll")?.();
    assert.equal(queuedFrames.length, 1);
    queuedFrames.shift()();

    assert.notEqual(fixture.layer.innerHTML, initialMarkup);
    assert.match(fixture.layer.innerHTML, /43,726,252 bp/);
    assert.ok((fixture.layer.innerHTML.match(/track-tick-guide/g) || []).length <= 20);

    bindSubviewRulerRuntime(fixture.host);
    assert.equal(fixture.listeners.size, 1);
  } finally {
    globalThis.requestAnimationFrame = previousRequestAnimationFrame;
  }
});

test("virtual ruler markup carries geometry metadata without serializing ticks", () => {
  const markup = buildVisibleSubviewRulerMarkup({
    windowStart: 0,
    windowEnd: 43_726_252,
    tickBp: 1_000,
    innerWidth: 7_430_000,
    domainSpanBp: 43_726_252,
    viewportLeft: 7_428_800,
    viewportWidth: 1_200,
    tickY1: 52,
    tickY2: 130,
    tickLabelY: 46,
    edgeLabelPadding: 16,
  });

  assert.ok((markup.match(/track-tick-guide/g) || []).length <= 20);
  assert.match(markup, /43,726,252 bp/);
});
