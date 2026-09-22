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
  grtGroup: "Precomputed anchors",
  userEmpty: "No user anchors",
  grtEmpty: "No precomputed anchors",
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
  assert.match(html, /Precomputed anchors/);
  assert.match(html, /data-subview-anchor-check="manual:user"/);
  assert.doesNotMatch(html, /data-subview-anchor-check="grt:origin"/);
  assert.doesNotMatch(html, /data-subview-anchor-delete="grt:origin"/);
  assert.match(html, /data-subview-anchor-copy-grt="origin"[\s\S]*disabled/);
  assert.match(html, /GRT gap 250 bp/);
  assert.match(html, /class="subview-anchor-object-name">A01</);
  assert.match(html, /class="subview-anchor-object-name" title="Read only">P01</);
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

test("anchor list orders user anchors from left to right and renders passive cards", () => {
  const html = renderSubviewAnchorList([
    {
      objectId: "manual:right",
      kind: "manual",
      direction: "right",
      offsetBp: 10,
      canDelete: true,
      scene: { topX: 420, bottomX: 460 },
      endpoints: [
        { name: "right_top", cutBp: 20, sourceRole: "primary", sourceName: "hifiasm" },
        { name: "right_bottom", cutBp: 30, sourceRole: "support", sourceName: "flye" },
      ],
      searchText: "right",
    },
    {
      objectId: "edge:left:left",
      kind: "evidence",
      edge: "left",
      canDelete: true,
      scene: { topX: 120, bottomX: 160 },
      endpoints: [
        { name: "left_top", cutBp: 20, sourceRole: "primary", sourceName: "hifiasm" },
        { name: "left_bottom", cutBp: 30, sourceRole: "support", sourceName: "flye" },
      ],
      searchText: "left",
    },
  ], {
    query: "",
    focusedObjectId: "edge:left:left",
    checkedObjectIds: [],
  }, labels, { escapeHtml: String, escapeAttr: String });

  assert.ok(html.indexOf('data-subview-anchor-list-row="edge:left:left"')
    < html.indexOf('data-subview-anchor-list-row="manual:right"'));
  assert.ok(html.indexOf('class="subview-anchor-object-name">A01')
    < html.indexOf('class="subview-anchor-object-name">A02'));
  assert.doesNotMatch(html, /Left edge|Right edge/);
  assert.match(html, /class="subview-anchor-object is-focused"[\s\S]*aria-current="true"/);
  assert.match(html, /class="subview-anchor-object-identity"[\s\S]*data-subview-anchor-check="edge:left:left"[\s\S]*>A01</);
  assert.match(html, /<div class="subview-anchor-object-main">/);
  assert.doesNotMatch(html, /<button type="button" class="subview-anchor-object-main"/);
});

test("precomputed anchor numbers follow full left-to-right order and survive filtering", () => {
  const html = renderSubviewAnchorList([
    { objectId: "grt:right", kind: "grt", originId: "right", connectionKind: "link",
      canDelete: false, canCopy: true, scene: { topX: 400, bottomX: 440 }, endpoints: [], searchText: "target" },
    { objectId: "grt:left", kind: "grt", originId: "left", connectionKind: "link",
      canDelete: false, canCopy: true, scene: { topX: 100, bottomX: 140 }, endpoints: [], searchText: "other" },
  ], {
    query: "target", focusedObjectId: "", checkedObjectIds: [],
  }, labels, { escapeHtml: String, escapeAttr: String });

  assert.doesNotMatch(html, /data-subview-anchor-list-row="grt:left"/);
  assert.match(html, /data-subview-anchor-list-row="grt:right"[\s\S]*>P02<\/span>/);
});
