import test from "node:test";
import assert from "node:assert/strict";

import {
  resolveActiveTrackScrollElement,
  resolveTrackPointerContentPoint,
  resolveScrollLeftForViewportAnchorBp,
  resolveScrollLeftForViewboxMinXShift,
  resolveTrackScrollLeftForViewboxShift,
  resolveViewportAnchorBp,
} from "../track-viewport.js";

test("viewBox min-x shift keeps visual scroll anchoring stable", () => {
  assert.equal(resolveScrollLeftForViewboxMinXShift(0, 0, -50), 50);
  assert.equal(resolveScrollLeftForViewboxMinXShift(50, -50, 0), 0);
  assert.equal(resolveScrollLeftForViewboxMinXShift(120, -80, -80), 120);
  assert.equal(resolveScrollLeftForViewboxMinXShift(20, 10, 100), 0);
});

test("primary viewport anchor bp round-trips across zoom metrics with negative viewBox offset", () => {
  const metrics = {
    viewportWidth: 240,
    windowStartBp: -200,
    domainSpanBp: 2000,
    innerWidth: 1000,
    viewboxMinX: -40,
  };
  const anchorBp = resolveViewportAnchorBp(340, metrics);
  assert.equal(anchorBp, 640);
  assert.equal(resolveScrollLeftForViewportAnchorBp(anchorBp, metrics), 340);
});

test("subview viewport anchor bp round-trips across zoom metrics", () => {
  const metrics = {
    viewportWidth: 180,
    windowStartBp: 0,
    domainSpanBp: 1500,
    innerWidth: 750,
    viewboxMinX: -30,
  };
  const anchorBp = resolveViewportAnchorBp(210, metrics);
  assert.equal(anchorBp, 540);
  assert.equal(resolveScrollLeftForViewportAnchorBp(anchorBp, metrics), 210);
});

test("drag-follow mode keeps the viewport moving into newly exposed negative viewBox space", () => {
  assert.equal(
    resolveTrackScrollLeftForViewboxShift(50, 0, -50, { preserveViewport: false }),
    50,
  );
  assert.equal(
    resolveTrackScrollLeftForViewboxShift(50, -50, -20, { preserveViewport: false }),
    50,
  );
  assert.equal(
    resolveTrackScrollLeftForViewboxShift(0, 0, -40, { preserveViewport: false }),
    0,
  );
});

test("track viewport resolves the current live scroll element instead of a stale detached node", () => {
  const staleScrollEl = { scrollLeft: 0 };
  const liveScrollEl = { scrollLeft: 860 };
  const host = {
    querySelector(selector) {
      if (selector === ".assembly-track-scroll[data-track-role='primary']") {
        return liveScrollEl;
      }
      return null;
    },
  };

  const resolved = resolveActiveTrackScrollElement(host, "primary", staleScrollEl);

  assert.equal(resolved, liveScrollEl);
  assert.notEqual(resolved, staleScrollEl);
});

test("track viewport resolves pointer content point using scroll offsets and viewBox min-x", () => {
  const scrollEl = {
    scrollLeft: 120,
    scrollTop: 35,
    dataset: {
      subviewViewboxMinX: "-40",
    },
    getBoundingClientRect() {
      return {
        left: 10,
        top: 20,
      };
    },
  };
  const point = resolveTrackPointerContentPoint(
    {
      clientX: 210,
      clientY: 180,
    },
    scrollEl,
  );

  assert.deepEqual(point, { x: 280, y: 195 });
});
