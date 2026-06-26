import test from "node:test";
import assert from "node:assert/strict";

import {
  __testGetFinalPathGraphPreviewState,
  __testApplyGraphDragPreviewMove,
  __testResolveGraphDragCommitMove,
  bindFinalPathGraphDrag,
} from "../final-path-graph-drag-runtime.js";

function createWindowStub() {
  const listeners = new Map();
  return {
    listeners,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    removeEventListener(type, handler) {
      if (listeners.get(type) === handler) {
        listeners.delete(type);
      }
    },
  };
}

function createSegmentNode(segmentId, width) {
  const node = {
    dataset: {
      finalPathSegmentId: segmentId,
      finalPathSegmentType: segmentId.includes("gap") ? "gap" : "ctg",
      finalPathSlotLeft: "0",
      finalPathSlotRight: "0",
      finalPathSlotMid: "0",
    },
    width,
    attributes: new Map(),
    setAttribute(name, value) {
      this.attributes.set(name, String(value));
    },
    removeAttribute(name) {
      this.attributes.delete(name);
    },
    getAttribute(name) {
      return this.attributes.get(name) || null;
    },
    closest(selector) {
      if (selector === "[data-final-path-segment-id][data-final-path-slot-left]") {
        return this;
      }
      return null;
    },
  };
  return node;
}

function assignSlots(nodesById, orderedIds) {
  let cursor = 0;
  orderedIds.forEach((segmentId) => {
    const node = nodesById.get(segmentId);
    const left = cursor;
    const right = left + node.width;
    const mid = left + ((right - left) / 2);
    node.dataset.finalPathSlotLeft = String(left);
    node.dataset.finalPathSlotRight = String(right);
    node.dataset.finalPathSlotMid = String(mid);
    cursor = right + 10;
  });
}

test("applyGraphDragPreviewMove swaps left when dragged left edge crosses the left neighbor midpoint", () => {
  const result = __testApplyGraphDragPreviewMove({
    previewSegmentIds: ["seg-1", "seg-2", "seg-3"],
    sourceSegmentId: "seg-2",
    dragLeft: 40,
    dragRight: 100,
    slotRects: {
      "seg-1": { left: 0, right: 100, mid: 50 },
      "seg-2": { left: 110, right: 170, mid: 140 },
      "seg-3": { left: 180, right: 260, mid: 220 },
    },
  });

  assert.deepEqual(result.previewSegmentIds, ["seg-2", "seg-1", "seg-3"]);
  assert.equal(result.swapped, true);
  assert.equal(result.direction, "left");
});

test("applyGraphDragPreviewMove swaps right when dragged right edge crosses the right neighbor midpoint", () => {
  const result = __testApplyGraphDragPreviewMove({
    previewSegmentIds: ["seg-1", "seg-2", "seg-3"],
    sourceSegmentId: "seg-2",
    dragLeft: 170,
    dragRight: 230,
    slotRects: {
      "seg-1": { left: 0, right: 100, mid: 50 },
      "seg-2": { left: 110, right: 170, mid: 140 },
      "seg-3": { left: 180, right: 260, mid: 220 },
    },
  });

  assert.deepEqual(result.previewSegmentIds, ["seg-1", "seg-3", "seg-2"]);
  assert.equal(result.swapped, true);
  assert.equal(result.direction, "right");
});

test("applyGraphDragPreviewMove keeps order when no midpoint is crossed", () => {
  const result = __testApplyGraphDragPreviewMove({
    previewSegmentIds: ["seg-1", "seg-2", "seg-3"],
    sourceSegmentId: "seg-2",
    dragLeft: 70,
    dragRight: 130,
    slotRects: {
      "seg-1": { left: 0, right: 100, mid: 50 },
      "seg-2": { left: 110, right: 170, mid: 140 },
      "seg-3": { left: 180, right: 260, mid: 220 },
    },
  });

  assert.deepEqual(result.previewSegmentIds, ["seg-1", "seg-2", "seg-3"]);
  assert.equal(result.swapped, false);
});

test("resolveGraphDragCommitMove converts a rightward final preview order into one moveFinalPathRow payload", () => {
  assert.deepEqual(
    __testResolveGraphDragCommitMove({
      originalSegmentIds: ["seg-1", "seg-2", "seg-3", "seg-4"],
      previewSegmentIds: ["seg-1", "seg-3", "seg-4", "seg-2"],
      sourceSegmentId: "seg-2",
    }),
    {
      sourceSegmentId: "seg-2",
      targetSegmentId: "seg-4",
      placement: "after",
    },
  );
});

test("resolveGraphDragCommitMove converts a leftward final preview order into one moveFinalPathRow payload", () => {
  assert.deepEqual(
    __testResolveGraphDragCommitMove({
      originalSegmentIds: ["seg-1", "seg-2", "seg-3", "seg-4"],
      previewSegmentIds: ["seg-3", "seg-1", "seg-2", "seg-4"],
      sourceSegmentId: "seg-3",
    }),
    {
      sourceSegmentId: "seg-3",
      targetSegmentId: "seg-1",
      placement: "before",
    },
  );
});

test("bindFinalPathGraphDrag commits exactly one move on pointerup after repeated rightward midpoint swaps", async () => {
  const originalWindow = globalThis.window;
  try {
    const windowStub = createWindowStub();
    globalThis.window = windowStub;

    const hostListeners = new Map();
    const nodesById = new Map([
      ["seg-1", createSegmentNode("seg-1", 100)],
      ["seg-gap", createSegmentNode("seg-gap", 60)],
      ["seg-3", createSegmentNode("seg-3", 80)],
    ]);
    let currentOrder = ["seg-1", "seg-gap", "seg-3"];
    assignSlots(nodesById, currentOrder);
    const scrollWrap = {
      scrollLeft: 0,
      getBoundingClientRect() {
        return { left: 0 };
      },
    };
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
      querySelector(selector) {
        if (selector === ".assembly-final-path-svg-wrap") {
          return scrollWrap;
        }
        return null;
      },
      querySelectorAll(selector) {
        if (selector === "[data-final-path-segment-id][data-final-path-slot-left]") {
          return currentOrder.map((segmentId) => nodesById.get(segmentId));
        }
        return [];
      },
    };
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
            finalPathViewMode: "graph",
            selectedChrName: "Chr01",
          },
        };
      },
    };
    const movePayloads = [];
    let rerenderCount = 0;
    bindFinalPathGraphDrag(host, store, {
      moveFinalPathRow(_host, _store, payload) {
        movePayloads.push(payload);
      },
      rerender() {
        rerenderCount += 1;
        const preview = __testGetFinalPathGraphPreviewState();
        currentOrder = Array.isArray(preview?.previewSegmentOrder) ? [...preview.previewSegmentOrder] : currentOrder;
        assignSlots(nodesById, currentOrder);
      },
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      ctrlKey: false,
      metaKey: false,
      clientX: 20,
      clientY: 40,
      preventDefault() {},
      target: nodesById.get("seg-1"),
    });

    windowStub.listeners.get("pointermove")?.({
      clientX: 150,
      clientY: 40,
    });
    windowStub.listeners.get("pointermove")?.({
      clientX: 250,
      clientY: 40,
    });
    await windowStub.listeners.get("pointerup")?.({});

    assert.equal(rerenderCount >= 2, true);
    assert.deepEqual(movePayloads, [
      {
        sourceSegmentId: "seg-1",
        targetSegmentId: "seg-3",
        placement: "after",
      },
    ]);
  } finally {
    globalThis.window = originalWindow;
  }
});

test("bindFinalPathGraphDrag scopes all-mode duplicate segment ids to the target haplotype card", async () => {
  const originalWindow = globalThis.window;
  try {
    const windowStub = createWindowStub();
    globalThis.window = windowStub;

    const hostListeners = new Map();
    const nodesA = new Map([
      ["seg-1", createSegmentNode("seg-1", 100)],
      ["seg-2", createSegmentNode("seg-2", 100)],
    ]);
    const nodesB = new Map([
      ["seg-1", createSegmentNode("seg-1", 100)],
      ["seg-2", createSegmentNode("seg-2", 100)],
    ]);
    let orderA = ["seg-1", "seg-2"];
    let orderB = ["seg-1", "seg-2"];
    assignSlots(nodesA, orderA);
    assignSlots(nodesB, orderB);
    const scrollWrap = {
      scrollLeft: 0,
      getBoundingClientRect() {
        return { left: 0 };
      },
    };
    const createAllCard = (chrName, nodesById, getOrder) => ({
      dataset: {
        finalPathAllCard: chrName,
        finalPathTargetChrName: chrName,
      },
      querySelector(selector) {
        if (selector === ".assembly-final-path-svg-wrap") {
          return scrollWrap;
        }
        return null;
      },
      querySelectorAll(selector) {
        if (selector === "[data-final-path-segment-id][data-final-path-slot-left]") {
          return getOrder().map((segmentId) => nodesById.get(segmentId));
        }
        return [];
      },
    });
    const cardA = createAllCard("Chr01A", nodesA, () => orderA);
    const cardB = createAllCard("Chr01B", nodesB, () => orderB);
    nodesB.forEach((node) => {
      node.dataset.finalPathTargetChrName = "Chr01B";
      node.closest = (selector) => {
        if (selector === "[data-final-path-segment-id][data-final-path-slot-left]") {
          return node;
        }
        if (selector === "[data-final-path-target-chr-name]" || selector === "[data-final-path-all-card]") {
          return cardB;
        }
        return null;
      };
    });
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
      querySelector(selector) {
        if (selector === ".final-path-card") {
          return this;
        }
        if (selector === ".assembly-final-path-svg-wrap") {
          return scrollWrap;
        }
        return null;
      },
      querySelectorAll(selector) {
        if (selector === "[data-final-path-all-card]") {
          return [cardA, cardB];
        }
        if (selector === "[data-final-path-segment-id][data-final-path-slot-left]") {
          return [...orderA.map((segmentId) => nodesA.get(segmentId)), ...orderB.map((segmentId) => nodesB.get(segmentId))];
        }
        return [];
      },
    };
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
            finalPathViewMode: "graph",
            selectedChrName: "Chr01",
            isChrPhased: true,
            phasedChrTracks: [
              { haplotypeKey: "A", label: "Chr01A" },
              { haplotypeKey: "B", label: "Chr01B" },
            ],
          },
        };
      },
    };
    const movePayloads = [];
    let previewDuringDrag = null;
    bindFinalPathGraphDrag(host, store, {
      moveFinalPathRow(_host, _store, payload) {
        movePayloads.push(payload);
      },
      rerender() {
        const preview = __testGetFinalPathGraphPreviewState();
        if (Array.isArray(preview?.previewSegmentOrder)) {
          previewDuringDrag = preview;
          orderB = [...preview.previewSegmentOrder];
          assignSlots(nodesB, orderB);
          assignSlots(nodesA, orderA);
        }
      },
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      ctrlKey: false,
      metaKey: false,
      clientX: 20,
      clientY: 40,
      preventDefault() {},
      target: nodesB.get("seg-1"),
    });
    windowStub.listeners.get("pointermove")?.({
      clientX: 150,
      clientY: 40,
    });
    await windowStub.listeners.get("pointerup")?.({});

    assert.equal(previewDuringDrag?.selectedChrName, "Chr01B");
    assert.deepEqual(previewDuringDrag?.previewSegmentOrder, ["seg-2", "seg-1"]);
    assert.equal(nodesA.get("seg-1").getAttribute("transform"), null);
    assert.match(nodesB.get("seg-1").getAttribute("transform") || "", /^translate\(/);
    assert.deepEqual(movePayloads, [
      {
        sourceSegmentId: "seg-1",
        targetSegmentId: "seg-2",
        placement: "after",
        targetChrName: "Chr01B",
      },
    ]);
  } finally {
    globalThis.window = originalWindow;
  }
});

test("bindFinalPathGraphDrag does not commit when the dragged segment never crosses a midpoint", async () => {
  const originalWindow = globalThis.window;
  try {
    const windowStub = createWindowStub();
    globalThis.window = windowStub;

    const hostListeners = new Map();
    const nodesById = new Map([
      ["seg-1", createSegmentNode("seg-1", 100)],
      ["seg-gap", createSegmentNode("seg-gap", 60)],
      ["seg-3", createSegmentNode("seg-3", 80)],
    ]);
    const currentOrder = ["seg-1", "seg-gap", "seg-3"];
    assignSlots(nodesById, currentOrder);
    const scrollWrap = {
      scrollLeft: 0,
      getBoundingClientRect() {
        return { left: 0 };
      },
    };
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
      querySelector(selector) {
        if (selector === ".assembly-final-path-svg-wrap") {
          return scrollWrap;
        }
        return null;
      },
      querySelectorAll(selector) {
        if (selector === "[data-final-path-segment-id][data-final-path-slot-left]") {
          return currentOrder.map((segmentId) => nodesById.get(segmentId));
        }
        return [];
      },
    };
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
            finalPathViewMode: "graph",
            selectedChrName: "Chr01",
          },
        };
      },
    };
    let movePayload = null;
    bindFinalPathGraphDrag(host, store, {
      moveFinalPathRow(_host, _store, payload) {
        movePayload = payload;
      },
      rerender() {},
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      ctrlKey: false,
      metaKey: false,
      clientX: 20,
      clientY: 40,
      preventDefault() {},
      target: nodesById.get("seg-1"),
    });

    windowStub.listeners.get("pointermove")?.({
      clientX: 40,
      clientY: 40,
    });
    await windowStub.listeners.get("pointerup")?.({});

    assert.equal(movePayload, null);
  } finally {
    globalThis.window = originalWindow;
  }
});
