import test from "node:test";
import assert from "node:assert/strict";

import { createSubviewAnchorManagerController } from "../subview-anchor-manager-controller.js";

const labels = {
  anchorManager: {
    search: "Search", searchPlaceholder: "name or source", deleteSelected: "Delete ({count})",
    empty: "No anchors", noMatches: "No matches", leftEdge: "Left edge", rightEdge: "Right edge",
    userGroup: "User anchors", grtGroup: "GRT anchors", userEmpty: "No user anchors",
    grtEmpty: "No GRT anchors", grtCopyType: "Copied from GRT", grtLinkType: "GRT link",
    grtGapType: "GRT gap {size} bp", grtEndpointUnavailable: "Unavailable",
    grtSameLane: "Same lane", grtReadOnly: "Read only", copy: "Copy", copyGrt: "Copy GRT",
    manualType: "Manual {direction} {offset} bp", left: "left", right: "right", contig: "ctg",
    sourcePrimary: "Primary", sourceSupport: "Support", sourceMirror: "Mirror",
    sourceRef: "Reference", sourcePhased: "Phased", sourceGrt: "GRT",
    sourceWithName: "{role} ({name})",
    sourceUnavailable: "Source unavailable", coordinateUnavailable: "?",
    endpointDetailsUnavailable: "Details unavailable", evidenceUnavailable: "Evidence unavailable",
    endpointUnavailable: "Endpoint unavailable", selectObject: "Select", deleteObject: "Delete",
  },
};

function target(dataset = {}, relationships = {}) {
  return {
    dataset,
    value: "",
    checked: false,
    matches(selector) { return selector === "[data-subview-anchor-search]" && dataset.subviewAnchorSearch; },
    closest(selector) {
      if (selector === "[data-subview-anchor-list-row]" && dataset.subviewAnchorListRow) return this;
      if (selector === "[data-subview-anchor-check]" && dataset.subviewAnchorCheck) return this;
      if (selector === "[data-subview-anchor-delete]" && dataset.subviewAnchorDelete) return this;
      if (selector === "[data-subview-anchor-delete-checked]" && dataset.subviewAnchorDeleteChecked) return this;
      if (selector === "[data-subview-anchor-check],[data-subview-anchor-delete]") {
        return dataset.subviewAnchorCheck || dataset.subviewAnchorDelete ? this : null;
      }
      if (selector === "[data-subview-anchor-manager]") return relationships.manager || null;
      if (selector === ".subview-anchor-object") return relationships.wrapper || null;
      if (selector === "#route-host") return null;
      return null;
    },
    setAttribute(name, value) { this[name] = value; },
  };
}

function fixture() {
  const objectId = "edge:hit-1:left";
  const attributes = {
    "data-subview-anchor-kind": "evidence",
    "data-subview-anchor-object-id": objectId,
    "data-subview-anchor-top-endpoint-key": "top-1",
    "data-subview-anchor-top-contig-id": "1",
    "data-subview-anchor-top-cut-bp": "100",
    "data-subview-anchor-top-name": "ctg_top",
    "data-subview-anchor-top-source-role": "primary",
    "data-subview-anchor-top-source-kind": "mother",
    "data-subview-anchor-top-source-name": "hifiasm",
    "data-subview-anchor-bottom-endpoint-key": "bottom-2",
    "data-subview-anchor-bottom-contig-id": "2",
    "data-subview-anchor-bottom-cut-bp": "200",
    "data-subview-anchor-bottom-name": "ctg_bottom",
    "data-subview-anchor-bottom-source-role": "support",
    "data-subview-anchor-bottom-source-kind": "mother",
    "data-subview-anchor-bottom-source-name": "flye",
    "data-subview-anchor-top-x": "300",
    "data-subview-anchor-bottom-x": "340",
  };
  const anchorNode = {
    focused: false,
    getAttribute: (name) => attributes[name] ?? null,
    classList: { toggle(_name, value) { anchorNode.focused = value; } },
  };
  const scroll = {
    dataset: { subviewViewboxMinX: "20" }, clientWidth: 200,
    scrollTo(options) { this.options = options; },
  };
  const host = {
    querySelectorAll(selector) { return selector.includes("data-subview-anchor") ? [anchorNode] : []; },
    querySelector(selector) { return selector === ".subview-track-scroll" ? scroll : null; },
  };
  const subview = { activeAnchors: [{ hitKey: "hit-1", edge: "left" }], manualAnchors: [] };
  const store = { getState: () => ({ assembly: { subview } }) };
  const session = { subviewAnchorToolsState: {
    scopeKey: "scope", focusedObjectId: "", checkedObjectIds: [], query: "",
  } };
  const deleted = [];
  const controller = createSubviewAnchorManagerController({
    session,
    async deleteSubviewAnchors(_host, _store, objectIds) { deleted.push(objectIds); return true; },
  });
  return { objectId, anchorNode, controller, deleted, host, scroll, session, store };
}

test("anchor manager renders active anchors and resets transient state per scope", () => {
  const f = fixture();
  const html = f.controller.renderContent({
    host: f.host, state: f.store.getState(), tab: "anchors", scopeKey: "scope",
    labels, escapeHtml: String, escapeAttr: String,
  });
  assert.match(html, /data-subview-anchor-list-row="edge:hit-1:left"/);
  assert.match(html, /Left edge/);
  assert.match(html, /Primary \(hifiasm\)/);
  assert.match(html, /Support \(flye\)/);
  assert.equal(f.controller.renderContent({
    host: f.host, state: f.store.getState(), tab: "composition", scopeKey: "scope",
    labels, escapeHtml: String, escapeAttr: String,
  }), "");

  f.controller.resetScope("next");
  assert.deepEqual(f.session.subviewAnchorToolsState, {
    scopeKey: "next", focusedObjectId: "", checkedObjectIds: [], query: "",
  });
});

test("row focus updates in place so double click can locate without rerendering", () => {
  const f = fixture();
  const wrapper = { focused: false, classList: { toggle(_name, value) { wrapper.focused = value; } } };
  const manager = { querySelectorAll: () => [row] };
  const row = target({ subviewAnchorListRow: f.objectId }, { manager, wrapper });
  let syncCount = 0;
  const context = { host: f.host, store: f.store, sync: () => { syncCount += 1; } };

  f.controller.onAction({ target: row }, context);
  assert.equal(f.session.subviewAnchorToolsState.focusedObjectId, f.objectId);
  assert.equal(f.anchorNode.focused, true);
  assert.equal(wrapper.focused, true);
  assert.equal(row["aria-pressed"], "true");
  assert.equal(syncCount, 0);

  f.controller.onDoubleClick({ target: row }, context);
  assert.deepEqual(f.scroll.options, { left: 200, behavior: "smooth" });
});

test("checkbox selection stays separate and batch deletion delegates once", async () => {
  const f = fixture();
  let syncCount = 0;
  const context = { host: f.host, store: f.store, sync: () => { syncCount += 1; } };
  const checkbox = target({ subviewAnchorCheck: f.objectId });
  checkbox.checked = true;

  f.controller.onAction({ target: checkbox }, context);
  assert.deepEqual(f.session.subviewAnchorToolsState.checkedObjectIds, [f.objectId]);
  assert.equal(f.session.subviewAnchorToolsState.focusedObjectId, "");

  const batchDelete = target({ subviewAnchorDeleteChecked: "1" });
  f.controller.onAction({ target: batchDelete }, context);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(f.deleted, [[f.objectId]]);
  assert.deepEqual(f.session.subviewAnchorToolsState.checkedObjectIds, []);
  assert.equal(syncCount, 2);
});

test("search input and Enter location are handled without changing the saved selection", () => {
  const f = fixture();
  let syncCount = 0;
  const search = target({ subviewAnchorSearch: "1" });
  search.value = "GRT";
  f.controller.onInput({ target: search }, { sync: () => { syncCount += 1; } });
  assert.equal(f.session.subviewAnchorToolsState.query, "GRT");
  assert.equal(syncCount, 1);

  const row = target({ subviewAnchorListRow: f.objectId });
  let prevented = false;
  f.controller.onContentKeyDown({
    target: row, key: "Enter", preventDefault() { prevented = true; },
  }, { host: f.host });
  assert.equal(prevented, true);
  assert.deepEqual(f.scroll.options, { left: 200, behavior: "smooth" });
});


test("anchor manager hides GRT baseline anchors absent from the current scene", () => {
  const controller = createSubviewAnchorManagerController({ session: {} });
  const host = { querySelectorAll: () => [] };
  const state = {
    assembly: {
      selectedChrName: "Chr01",
      subview: { activeAnchors: [], manualAnchors: [] },
      grtProjectView: {
        baselineFinalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            grtDisplayAvailable: true,
            segments: [
              {
                segmentId: "left", type: "ctg", assemblyCtgId: 1,
                assemblySourceStart: 1, assemblySourceEnd: 1000,
                start: 1, end: 100,
                source: { dataset: "primary", contig: "ctg1", start: 1, end: 100, orientation: "+" },
              },
              {
                segmentId: "right", type: "ctg", assemblyCtgId: 2,
                assemblySourceStart: 1, assemblySourceEnd: 1000,
                start: 200, end: 300,
                source: { dataset: "support", contig: "ctg2", start: 200, end: 300, orientation: "+" },
              },
            ],
          },
        },
      },
    },
  };

  const html = controller.renderContent({
    host, state, tab: "anchors", scopeKey: "scope", labels, escapeHtml: String, escapeAttr: String,
  });

  assert.match(html, /No anchors/);
  assert.doesNotMatch(html, /GRT link/);
  assert.doesNotMatch(html, /data-subview-anchor-copy-grt/);
});
