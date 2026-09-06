import test from "node:test";
import assert from "node:assert/strict";

import { renderSubviewAnchorList } from "../render-subview-anchor-list.js";

const labels = {
  search: "Search",
  searchPlaceholder: "name",
  deleteSelected: "Delete ({count})",
  empty: "Empty",
  noMatches: "No matches",
  userGroup: "User anchors",
  grtGroup: "GRT anchors",
  userEmpty: "No user anchors",
  grtEmpty: "No GRT anchors",
  leftEdge: "Left edge",
  rightEdge: "Right edge",
  manualType: "Offset {direction} {offset}",
  grtCopyType: "Copied from GRT",
  grtLinkType: "GRT link",
  grtGapType: "GRT gap {size} bp",
  left: "left",
  right: "right",
  contig: "contig",
  sourcePrimary: "Primary",
  sourceSupport: "Support",
  sourceGrt: "GRT",
  sourceWithName: "{role} ({name})",
  sourceUnavailable: "Unavailable",
  coordinateUnavailable: "?",
  endpointDetailsUnavailable: "No details",
  grtSameLane: "Same lane",
  grtReadOnly: "Read only",
  copy: "Copy",
  copyGrt: "Copy as user anchor",
  selectObject: "Select",
  deleteObject: "Delete",
};

test("anchor list separates user and read-only GRT objects and disables same-lane copy", () => {
  const html = renderSubviewAnchorList([
    {
      objectId: "manual:user",
      kind: "manual",
      direction: "right",
      offsetBp: 10,
      canDelete: true,
      endpoints: [],
      searchText: "user",
    },
    {
      objectId: "grt:origin",
      kind: "grt",
      originId: "origin",
      connectionKind: "gap",
      gapSizeBp: 250,
      canDelete: false,
      canCopy: false,
      reason: "grtSameLane",
      endpoints: [],
      searchText: "grt",
    },
  ], {
    query: "",
    focusedObjectId: "grt:origin",
    checkedObjectIds: ["manual:user", "grt:origin"],
  }, labels, { escapeHtml: String, escapeAttr: String });

  assert.match(html, /User anchors/);
  assert.match(html, /GRT anchors/);
  assert.match(html, /data-subview-anchor-check="manual:user"/);
  assert.doesNotMatch(html, /data-subview-anchor-check="grt:origin"/);
  assert.doesNotMatch(html, /data-subview-anchor-delete="grt:origin"/);
  assert.match(html, /data-subview-anchor-copy-grt="origin"[\s\S]*disabled/);
  assert.match(html, /GRT gap 250 bp/);
  assert.match(html, /Delete \(1\)/);

  const filtered = renderSubviewAnchorList([
    { objectId: "manual:user", kind: "manual", canDelete: true, endpoints: [], searchText: "user" },
    { objectId: "grt:origin", kind: "grt", originId: "origin", connectionKind: "link",
      canDelete: false, canCopy: true, endpoints: [], searchText: "grt" },
  ], {
    query: "grt", focusedObjectId: "", checkedObjectIds: ["manual:user"],
  }, labels, { escapeHtml: String, escapeAttr: String });
  assert.doesNotMatch(filtered, /data-subview-anchor-check="manual:user"/);
  assert.match(filtered, /Delete \(1\)/);
});
