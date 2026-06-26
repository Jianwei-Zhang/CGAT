import test from "node:test";
import assert from "node:assert/strict";

import {
  clearTrackDragPreview,
  clearSubviewTrackDragPreview,
  previewTrackContigDrag,
  previewSubviewTrackContigDrag,
} from "../track-drag-preview-runtime.js";

function createNode(attrs = {}) {
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
