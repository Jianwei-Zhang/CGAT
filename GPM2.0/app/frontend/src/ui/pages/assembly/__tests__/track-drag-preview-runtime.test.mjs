import test from "node:test";
import assert from "node:assert/strict";

import {
  clearTrackDragPreview,
  clearSubviewTrackDragPreview,
  previewTrackContigDrag,
  previewSubviewTrackContigDrag,
} from "../track-drag-preview-runtime.js";

function createNode(attrs = {}, queryMap = {}) {
  const attributes = new Map(Object.entries(attrs));
  const classNames = new Set();
  return {
    style: {},
    classList: {
      add(...names) {
        names.forEach((name) => classNames.add(name));
      },
      remove(...names) {
        names.forEach((name) => classNames.delete(name));
      },
      contains(name) {
        return classNames.has(name);
      },
    },
    getAttribute(name) {
      return attributes.has(name) ? attributes.get(name) : null;
    },
    setAttribute(name, value) {
      attributes.set(name, String(value));
    },
    hasAttribute(name) {
      return attributes.has(name);
    },
    removeAttribute(name) {
      attributes.delete(name);
    },
    querySelectorAll(selector) {
      return queryMap[selector] || [];
    },
  };
}

function createHost(queryMap = {}) {
  const classNames = new Set();
  return {
    classList: {
      add(...names) {
        names.forEach((name) => classNames.add(name));
      },
      remove(...names) {
        names.forEach((name) => classNames.delete(name));
      },
      contains(name) {
        return classNames.has(name);
      },
    },
    querySelectorAll(selector) {
      return queryMap[selector] || [];
    },
  };
}

test("previewTrackContigDrag limits duplicate phased bands by phased item id", () => {
  const groupNode = createNode({
    "data-track-contig-id": "8",
    "data-track-role": "phased",
    "data-track-phased-track-id": "101",
    "data-track-phased-track-item-id": "9001",
  });
  const draggedBandNode = createNode({
    points: "0,0 1,0 10,1 0,1",
    "data-band-track-role": "phased",
    "data-band-contig-id": "8",
    "data-band-phased-track-id": "101",
    "data-band-phased-track-item-id": "9001",
  });
  const siblingBandNode = createNode({
    points: "2,0 3,0 12,1 2,1",
    "data-band-track-role": "phased",
    "data-band-contig-id": "8",
    "data-band-phased-track-id": "101",
    "data-band-phased-track-item-id": "9002",
  });
  const host = createHost({
    '[data-track-contig-id="8"][data-track-role="phased"][data-track-phased-track-item-id="9001"]': [groupNode],
    '[data-band-track-role="phased"][data-band-contig-id="8"]': [draggedBandNode, siblingBandNode],
    '[data-band-track-role="phased"][data-band-contig-id="8"][data-band-phased-track-item-id="9001"]': [draggedBandNode],
    "[data-drag-preview-group='1']": [groupNode],
    "[data-drag-preview-band='1']": [draggedBandNode],
    "[data-drag-preview-sticky-label='1']": [],
  });

  previewTrackContigDrag(host, {
    trackRole: "phased",
    assemblyCtgId: 8,
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
    offsetPx: 12,
  });

  assert.equal(groupNode.getAttribute("transform"), "translate(12.00 0)");
  assert.equal(draggedBandNode.getAttribute("points"), "0.00,0.00 1.00,0.00 22.00,1.00 12.00,1.00");
  assert.equal(siblingBandNode.getAttribute("points"), "2,0 3,0 12,1 2,1");

  clearTrackDragPreview(host);

  assert.equal(groupNode.getAttribute("transform"), null);
  assert.equal(draggedBandNode.getAttribute("points"), "0,0 1,0 10,1 0,1");
});

test("previewTrackContigDrag shifts only the dragged GRT junction endpoint and restores it", () => {
  const draggedGroup = createNode({
    "data-track-contig-id": "22",
    "data-track-role": "primary",
    "data-track-is-mirror": "0",
    "data-grt-result-entry-key": "primary:22:0",
  });
  const visibleLine = createNode({ x1: "10", x2: "30" });
  const hoverLine = createNode({ x1: "10", x2: "30" });
  const gapLabel = createNode({ x: "20" });
  const junctionNode = createNode({
    "data-grt-result-junction": "gap",
    "data-grt-result-junction-left-entry-key": "support:11:0",
    "data-grt-result-junction-right-entry-key": "primary:22:0",
  }, {
    "[data-grt-result-junction-line='1']": [visibleLine, hoverLine],
    "[data-grt-result-junction-label='1']": [gapLabel],
  });
  const host = createHost({
    '[data-track-contig-id="22"][data-track-role="primary"]': [draggedGroup],
    '[data-sticky-label-key="track:primary:22:0"]': [],
    '[data-band-track-role="primary"][data-band-contig-id="22"]': [],
    "[data-grt-result-junction]": [junctionNode],
    "[data-drag-preview-group='1']": [draggedGroup],
    "[data-drag-preview-band='1']": [],
    "[data-drag-preview-sticky-label='1']": [],
    "[data-drag-preview-junction-line='1']": [visibleLine, hoverLine],
    "[data-drag-preview-junction-label='1']": [gapLabel],
  });

  previewTrackContigDrag(host, {
    trackRole: "primary",
    assemblyCtgId: 22,
    offsetPx: 12,
  });

  assert.equal(visibleLine.getAttribute("x1"), "10.00");
  assert.equal(visibleLine.getAttribute("x2"), "42.00");
  assert.equal(hoverLine.getAttribute("x2"), "42.00");
  assert.equal(gapLabel.getAttribute("x"), "26.00");

  previewTrackContigDrag(host, {
    trackRole: "primary",
    assemblyCtgId: 22,
    offsetPx: 0,
  });
  assert.equal(visibleLine.getAttribute("x2"), "30.00");
  assert.equal(gapLabel.getAttribute("x"), "20.00");

  clearTrackDragPreview(host);

  assert.equal(draggedGroup.getAttribute("transform"), null);
  assert.equal(visibleLine.getAttribute("x1"), "10");
  assert.equal(visibleLine.getAttribute("x2"), "30");
  assert.equal(gapLabel.getAttribute("x"), "20");
  assert.equal(visibleLine.getAttribute("data-drag-preview-original-x1"), null);
});

test("previewTrackContigDrag translates a same-ctg GRT junction arc", () => {
  const draggedGroup = createNode({
    "data-track-contig-id": "22",
    "data-track-role": "primary",
    "data-track-is-mirror": "0",
    "data-grt-result-entry-key": "primary:22:0",
  });
  const junctionNode = createNode({
    "data-grt-result-junction": "link",
    "data-grt-result-junction-left-entry-key": "primary:22:0",
    "data-grt-result-junction-right-entry-key": "primary:22:0",
  });
  const host = createHost({
    '[data-track-contig-id="22"][data-track-role="primary"]': [draggedGroup],
    '[data-sticky-label-key="track:primary:22:0"]': [],
    '[data-band-track-role="primary"][data-band-contig-id="22"]': [],
    "[data-grt-result-junction]": [junctionNode],
    "[data-drag-preview-group='1']": [draggedGroup, junctionNode],
    "[data-drag-preview-band='1']": [],
    "[data-drag-preview-sticky-label='1']": [],
    "[data-drag-preview-junction-line='1']": [],
    "[data-drag-preview-junction-label='1']": [],
  });

  previewTrackContigDrag(host, {
    trackRole: "primary",
    assemblyCtgId: 22,
    offsetPx: 15,
  });

  assert.equal(junctionNode.getAttribute("transform"), "translate(15.00 0)");

  clearTrackDragPreview(host);
  assert.equal(junctionNode.getAttribute("transform"), null);
});

test("previewTrackContigDrag shifts matching phased sticky labels by phased item id", () => {
  const groupNode = createNode({
    "data-track-contig-id": "8",
    "data-track-role": "phased",
    "data-track-is-mirror": "0",
    "data-track-phased-track-id": "101",
    "data-track-phased-track-item-id": "9001",
  });
  const stickyLabelNode = createNode({
    "data-sticky-label-key": "track:phased:8:0:item:9001",
  });
  const siblingStickyLabelNode = createNode({
    "data-sticky-label-key": "track:phased:8:0:item:9002",
  });
  const host = createHost({
    '[data-track-contig-id="8"][data-track-role="phased"][data-track-phased-track-item-id="9001"]': [groupNode],
    '[data-sticky-label-key="track:phased:8:0:item:9001"]': [stickyLabelNode],
    '[data-band-track-role="phased"][data-band-contig-id="8"][data-band-phased-track-item-id="9001"]': [],
    "[data-drag-preview-group='1']": [groupNode],
    "[data-drag-preview-band='1']": [],
    "[data-drag-preview-sticky-label='1']": [stickyLabelNode],
  });

  previewTrackContigDrag(host, {
    trackRole: "phased",
    assemblyCtgId: 8,
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
    offsetPx: 16,
  });

  assert.equal(groupNode.getAttribute("transform"), "translate(16.00 0)");
  assert.equal(stickyLabelNode.style.transform, "translateX(16px)");
  assert.equal(siblingStickyLabelNode.style.transform, undefined);

  clearTrackDragPreview(host);

  assert.equal(groupNode.getAttribute("transform"), null);
  assert.equal(stickyLabelNode.style.transform, "");
});

test("previewSubviewTrackContigDrag shifts matching sticky labels together with the dragged subview contig", () => {
  const groupNode = createNode({
    "data-subview-track-slot": "top",
    "data-subview-track-role": "support",
    "data-subview-contig-id": "12",
  });
  const stickyLabelNode = createNode({
    "data-sticky-label-key": "subview:top:support:12",
  });
  const host = createHost({
    '[data-subview-track-slot="top"][data-subview-contig-id="12"]': [groupNode],
    '[data-subview-top-contig-id="12"]': [],
    '[data-sticky-label-key="subview:top:support:12"]': [stickyLabelNode],
    "[data-drag-preview-group='1']": [groupNode],
    "[data-drag-preview-band='1']": [],
    "[data-drag-preview-sticky-label='1']": [stickyLabelNode],
  });

  previewSubviewTrackContigDrag(host, { slot: "top", contigId: 12, offsetPx: 18 });

  assert.equal(groupNode.getAttribute("transform"), "translate(18.00 0)");
  assert.equal(stickyLabelNode.style.transform, "translateX(18px)");

  clearSubviewTrackDragPreview(host);

  assert.equal(groupNode.getAttribute("transform"), null);
  assert.equal(stickyLabelNode.style.transform, "");
});

test("previewSubviewTrackContigDrag shifts the matching GRT junction endpoint", () => {
  const groupNode = createNode({
    "data-subview-track-slot": "top",
    "data-subview-track-role": "support",
    "data-subview-contig-id": "12",
    "data-grt-result-entry-key": "top",
  });
  const visibleLine = createNode({ x1: "5", x2: "25" });
  const junctionNode = createNode({
    "data-grt-result-junction": "link",
    "data-grt-result-junction-left-entry-key": "top",
    "data-grt-result-junction-right-entry-key": "bottom",
  }, {
    "[data-grt-result-junction-line='1']": [visibleLine],
    "[data-grt-result-junction-label='1']": [],
  });
  const host = createHost({
    '[data-subview-track-slot="top"][data-subview-contig-id="12"]': [groupNode],
    '[data-subview-top-contig-id="12"]': [],
    '[data-sticky-label-key="subview:top:support:12"]': [],
    '[data-subview-label-slot="top"][data-subview-label-role="support"][data-subview-label-contig-id="12"]': [],
    "[data-grt-result-junction]": [junctionNode],
    "[data-drag-preview-group='1']": [groupNode],
    "[data-drag-preview-band='1']": [],
    "[data-drag-preview-sticky-label='1']": [],
    "[data-drag-preview-junction-line='1']": [visibleLine],
    "[data-drag-preview-junction-label='1']": [],
  });

  previewSubviewTrackContigDrag(host, { slot: "top", contigId: 12, offsetPx: 9 });

  assert.equal(visibleLine.getAttribute("x1"), "14.00");
  assert.equal(visibleLine.getAttribute("x2"), "25.00");

  clearSubviewTrackDragPreview(host);
  assert.equal(visibleLine.getAttribute("x1"), "5");
  assert.equal(visibleLine.getAttribute("x2"), "25");
});

test("previewSubviewTrackContigDrag shifts external subview-ctg labels with the dragged contig", () => {
  const groupNode = createNode({
    "data-subview-track-slot": "top",
    "data-subview-track-role": "support",
    "data-subview-contig-id": "12",
  });
  const externalLabelNode = createNode({
    "data-subview-label-slot": "top",
    "data-subview-label-role": "support",
    "data-subview-label-contig-id": "12",
  });
  const host = createHost({
    '[data-subview-track-slot="top"][data-subview-contig-id="12"]': [groupNode],
    '[data-subview-top-contig-id="12"]': [],
    '[data-sticky-label-key="subview:top:support:12"]': [],
    '[data-subview-label-slot="top"][data-subview-label-role="support"][data-subview-label-contig-id="12"]': [externalLabelNode],
    "[data-drag-preview-group='1']": [groupNode],
    "[data-drag-preview-band='1']": [],
    "[data-drag-preview-sticky-label='1']": [externalLabelNode],
  });

  previewSubviewTrackContigDrag(host, { slot: "top", contigId: 12, offsetPx: 18 });

  assert.equal(groupNode.getAttribute("transform"), "translate(18.00 0)");
  assert.equal(externalLabelNode.style.transform, "translateX(18px)");

  clearSubviewTrackDragPreview(host);

  assert.equal(groupNode.getAttribute("transform"), null);
  assert.equal(externalLabelNode.style.transform, "");
});

test("previewSubviewTrackContigDrag expands and restores the live subview-ctg scroll envelope", () => {
  const svgNode = createNode({
    width: "100",
    viewBox: "0 0 100 80",
  });
  const canvasLayerNode = createNode({
    "data-track-band-canvas-scene-kind": "subview-ctg",
  });
  canvasLayerNode.style.width = "100px";
  const scrollNode = createNode({
    "data-subview-viewbox-min-x": "0",
  }, {
    ".subview-track-svg": [svgNode],
    "[data-track-band-canvas-scene-kind='subview-ctg']": [canvasLayerNode],
  });
  scrollNode.clientWidth = 100;
  scrollNode.scrollLeft = 0;
  const groupNode = createNode({
    "data-subview-track-slot": "top",
    "data-subview-track-role": "support",
    "data-subview-contig-id": "12",
    "data-subview-rect-x": "80",
    "data-subview-rect-width": "20",
  });
  groupNode.closest = (selector) => (
    selector === ".assembly-track-scroll[data-track-role='subview']" ? scrollNode : null
  );
  const host = createHost({
    '[data-subview-track-slot="top"][data-subview-contig-id="12"]': [groupNode],
    '[data-subview-top-contig-id="12"]': [],
    '[data-sticky-label-key="subview:top:support:12"]': [],
    '[data-subview-label-slot="top"][data-subview-label-role="support"][data-subview-label-contig-id="12"]': [],
    "[data-drag-preview-group='1']": [groupNode],
    "[data-drag-preview-band='1']": [],
    "[data-drag-preview-sticky-label='1']": [],
    "[data-drag-preview-envelope='1']": [svgNode, canvasLayerNode, scrollNode],
  });

  const previewState = previewSubviewTrackContigDrag(host, {
    slot: "top",
    contigId: 12,
    offsetPx: 40,
  });

  assert.equal(groupNode.getAttribute("transform"), "translate(40.00 0)");
  assert.equal(svgNode.getAttribute("width"), "140");
  assert.equal(svgNode.getAttribute("viewBox"), "0 0 140 80");
  assert.equal(canvasLayerNode.style.width, "140px");
  assert.equal(scrollNode.scrollLeft, 40);
  assert.deepEqual(previewState, { scrollLeft: 40 });

  clearSubviewTrackDragPreview(host);

  assert.equal(svgNode.getAttribute("width"), "100");
  assert.equal(svgNode.getAttribute("viewBox"), "0 0 100 80");
  assert.equal(canvasLayerNode.style.width, "100px");
  assert.equal(scrollNode.getAttribute("data-subview-viewbox-min-x"), "0");
});
