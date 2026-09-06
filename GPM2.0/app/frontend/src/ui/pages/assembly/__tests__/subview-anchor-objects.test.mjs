import test from "node:test";
import assert from "node:assert/strict";

import {
  applySubviewAnchorFocus,
  buildSubviewAnchorObjectId,
  buildSubviewAnchorObjects,
  collectSubviewAnchorScene,
  deleteSubviewAnchorObjects,
  enrichSubviewAnchorObjectDescriptors,
  filterSubviewAnchorObjects,
  findSubviewAnchorDescriptor,
  locateSubviewAnchorObject,
  normalizeSubviewAnchorToolsUi,
} from "../subview-anchor-objects.js";

function sceneNode({ kind = "evidence", objectId, topX = 100, bottomX = 140 } = {}) {
  const attributes = {
    "data-subview-anchor-kind": kind,
    "data-subview-anchor-object-id": objectId,
    "data-subview-anchor-top-endpoint-key": "top-1",
    "data-subview-anchor-top-contig-id": "1",
    "data-subview-anchor-top-cut-bp": "120",
    "data-subview-anchor-top-length-bp": "1000",
    "data-subview-anchor-top-name": "ctg_alpha",
    "data-subview-anchor-top-source-label": "GRT · primary",
    "data-subview-anchor-top-source-role": "primary",
    "data-subview-anchor-top-source-kind": "mother",
    "data-subview-anchor-top-source-name": "hifiasm",
    "data-subview-anchor-bottom-endpoint-key": "bottom-2",
    "data-subview-anchor-bottom-contig-id": "2",
    "data-subview-anchor-bottom-cut-bp": "240",
    "data-subview-anchor-bottom-length-bp": "900",
    "data-subview-anchor-bottom-name": "ctg_beta",
    "data-subview-anchor-bottom-source-label": "User track",
    "data-subview-anchor-bottom-source-role": "support",
    "data-subview-anchor-bottom-source-kind": "mother",
    "data-subview-anchor-bottom-source-name": "flye",
    "data-subview-anchor-top-x": String(topX),
    "data-subview-anchor-bottom-x": String(bottomX),
  };
  return {
    focused: false,
    getAttribute: (name) => attributes[name] ?? null,
    classList: { toggle(_name, value) { this.owner.focused = value; }, owner: null },
  };
}

function fixture() {
  const evidenceId = buildSubviewAnchorObjectId("evidence", "hit:alpha", "left");
  const manualId = buildSubviewAnchorObjectId("manual", "manual-1");
  const evidenceNode = sceneNode({ objectId: evidenceId });
  const manualNode = sceneNode({ kind: "manual", objectId: manualId, topX: 500, bottomX: 540 });
  evidenceNode.classList.owner = evidenceNode;
  manualNode.classList.owner = manualNode;
  const nodes = [evidenceNode, manualNode];
  const scroll = {
    dataset: { subviewViewboxMinX: "20" },
    clientWidth: 200,
    scrollLeft: 0,
    scrollTo(options) { this.lastScroll = options; this.scrollLeft = options.left; },
  };
  const host = {
    querySelectorAll(selector) {
      return selector.includes("data-subview-anchor") ? nodes : [];
    },
    querySelector(selector) {
      return selector === ".subview-track-scroll" ? scroll : null;
    },
  };
  const subview = {
    activeAnchors: [
      { hitKey: "hit:alpha", edge: "left" },
      {
        hitKey: "hit:missing",
        edge: "right",
        descriptor: {
          top: { endpointKey: "old-top", contigId: 7, cutBp: 70, name: "old_top", sourceLabel: "GRT" },
          bottom: { endpointKey: "old-bottom", contigId: 8, cutBp: 80, name: "old_bottom", sourceLabel: "GRT" },
        },
      },
    ],
    manualAnchors: [{
      manualAnchorId: "manual-1",
      direction: "right",
      offsetBp: 50,
      endpointA: { endpointKey: "top-1", contigId: 1, cutBp: 120, name: "ctg_alpha", sourceLabel: "GRT · primary" },
      endpointB: { endpointKey: "bottom-2", contigId: 2, cutBp: 240, name: "ctg_beta", sourceLabel: "User track" },
    }],
  };
  return { evidenceId, manualId, evidenceNode, manualNode, host, scroll, subview };
}

test("anchor objects merge saved identity with current scene details and keep unavailable anchors", () => {
  const f = fixture();
  const scene = collectSubviewAnchorScene(f.host);
  const objects = buildSubviewAnchorObjects(f.subview, scene);

  assert.equal(objects.length, 3);
  assert.deepEqual(findSubviewAnchorDescriptor(f.host, "hit:alpha", "left"), {
    top: {
      endpointKey: "top-1", contigId: 1, cutBp: 120, lengthBp: 1000,
      name: "ctg_alpha", sourceRole: "primary", sourceKind: "mother",
      sourceName: "hifiasm", sourceLabel: "GRT · primary",
    },
    bottom: {
      endpointKey: "bottom-2", contigId: 2, cutBp: 240, lengthBp: 900,
      name: "ctg_beta", sourceRole: "support", sourceKind: "mother",
      sourceName: "flye", sourceLabel: "User track",
    },
  });
  assert.equal(objects[0].objectId, f.evidenceId);
  assert.equal(objects[0].applicability, "applied");
  assert.equal(objects[0].canLocate, true);
  assert.equal(objects[1].objectId, "edge:hit:missing:right");
  assert.equal(objects[1].applicability, "evidence-unavailable");
  assert.equal(objects[1].endpoints[0].name, "old_top");
  assert.equal(objects[1].canDelete, true);
  assert.equal(objects[2].objectId, f.manualId);
  assert.equal(objects[2].direction, "right");
});

test("search and transient selection never mutate or discard saved anchor objects", () => {
  const f = fixture();
  const objects = buildSubviewAnchorObjects(f.subview, collectSubviewAnchorScene(f.host));
  assert.deepEqual(filterSubviewAnchorObjects(objects, "USER TRACK").map((object) => object.objectId), [
    f.evidenceId,
    f.manualId,
  ]);
  assert.deepEqual(filterSubviewAnchorObjects(objects, "old_top").map((object) => object.objectId), [
    "edge:hit:missing:right",
  ]);
  assert.deepEqual(normalizeSubviewAnchorToolsUi({
    scopeKey: "old",
    focusedObjectId: "missing",
    checkedObjectIds: [f.manualId, f.manualId, "missing"],
    query: "ctg",
  }, objects.map((object) => object.objectId)), {
    scopeKey: "old",
    focusedObjectId: "",
    checkedObjectIds: [f.manualId],
    query: "ctg",
  });
  assert.equal(f.subview.activeAnchors.length, 2);
  assert.equal(f.subview.manualAnchors.length, 1);
});

test("mixed deletion removes only selected saved objects in one pure state transition", () => {
  const f = fixture();
  const result = deleteSubviewAnchorObjects(f.subview, [f.evidenceId, f.manualId, "unknown"]);

  assert.equal(result.changed, true);
  assert.equal(result.count, 2);
  assert.deepEqual(result.activeAnchors.map(({ hitKey, edge }) => ({ hitKey, edge })), [
    { hitKey: "hit:missing", edge: "right" },
  ]);
  assert.deepEqual(result.manualAnchors, []);
  assert.equal(deleteSubviewAnchorObjects(f.subview, ["unknown"]).changed, false);
});

test("legacy evidence anchors gain exact scene descriptors without creating a new object", () => {
  const f = fixture();
  const enriched = enrichSubviewAnchorObjectDescriptors(f.subview, collectSubviewAnchorScene(f.host));

  assert.equal(enriched.changed, true);
  assert.equal(enriched.activeAnchors[0].hitKey, "hit:alpha");
  assert.equal(enriched.activeAnchors[0].descriptor.top.name, "ctg_alpha");
  assert.equal(enriched.activeAnchors[0].descriptor.top.sourceRole, "primary");
  assert.equal(enriched.activeAnchors[0].descriptor.top.sourceName, "hifiasm");
  assert.equal(enriched.activeAnchors[0].descriptor.top.sourceLabel, undefined);
  assert.equal(enriched.activeAnchors[1].descriptor.top.name, "old_top");
  assert.equal(enrichSubviewAnchorObjectDescriptors({
    ...f.subview,
    activeAnchors: enriched.activeAnchors,
  }, collectSubviewAnchorScene(f.host)).changed, false);
});

test("focus is visual only and locate centers the anchor without changing its identity", () => {
  const f = fixture();
  applySubviewAnchorFocus(f.host, f.manualId);
  assert.equal(f.evidenceNode.focused, false);
  assert.equal(f.manualNode.focused, true);

  assert.equal(locateSubviewAnchorObject(f.host, f.manualId), true);
  assert.deepEqual(f.scroll.lastScroll, { left: 400, behavior: "smooth" });
  assert.equal(locateSubviewAnchorObject(f.host, "manual:missing"), false);
});
