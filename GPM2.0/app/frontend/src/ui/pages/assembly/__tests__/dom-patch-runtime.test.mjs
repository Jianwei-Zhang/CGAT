import test from "node:test";
import assert from "node:assert/strict";

import { createAssemblyDomPatchController } from "../dom-patch-runtime.js";

function createController(overrides = {}) {
  return createAssemblyDomPatchController({
    bindBandCanvasRuntime() {},
    escapeHtml(value) {
      return String(value).replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return Array.from(new Set((Array.isArray(values) ? values : []).map(Number).filter(Boolean)));
    },
    getAssemblyI18n() {
      return { page: { deletedHiddenTag: "<hidden>" } };
    },
    normalizeTrackSelectionCtgIds(values) {
      return Array.from(new Set((Array.isArray(values) ? values : []).map(Number).filter(Boolean)));
    },
    renderAssemblyMainTrackSections() {
      return "";
    },
    ...overrides,
  });
}

function createClassList(initial = []) {
  const values = new Set(initial);
  return {
    contains(value) {
      return values.has(value);
    },
    toggle(value, force) {
      if (force) {
        values.add(value);
      } else {
        values.delete(value);
      }
    },
    values,
  };
}

test("assembly DOM patch controller replaces the shared status toast", () => {
  const nextToast = { id: "next" };
  let replacedWith = null;
  const currentToast = {
    replaceWith(node) {
      replacedWith = node;
    },
  };
  const currentMain = {
    querySelector(selector) {
      return selector === ".assembly-status-toast-wrap" ? currentToast : null;
    },
  };
  const routeHost = {
    querySelector(selector) {
      return selector === ".assembly-main-view" ? currentMain : null;
    },
  };
  const nextContent = {
    querySelector(selector) {
      return selector === ".assembly-status-toast-wrap" ? nextToast : null;
    },
  };

  const { patchAssemblyStatusToast } = createController();

  assert.equal(patchAssemblyStatusToast(routeHost, nextContent), true);
  assert.equal(replacedWith, nextToast);
});

test("assembly DOM patch controller hides the matching member, track group, and band", () => {
  let insertedMarkup = "";
  const chipClassList = createClassList();
  const chip = {
    dataset: { assemblyCtgId: "2" },
    classList: chipClassList,
    querySelector(selector) {
      if (selector === "strong") {
        return {
          insertAdjacentHTML(_position, markup) {
            insertedMarkup = markup;
          },
        };
      }
      return null;
    },
  };
  const trackCtgClassList = createClassList();
  const groupClassList = createClassList();
  let transform = "";
  const group = {
    dataset: { trackContigId: "2" },
    classList: groupClassList,
    querySelectorAll(selector) {
      return selector === ".track-ctg" ? [{ classList: trackCtgClassList }] : [];
    },
    setAttribute(name, value) {
      if (name === "transform") {
        transform = value;
      }
    },
  };
  const band = {
    dataset: { bandContigId: "2" },
    style: {},
  };
  const routeHost = {
    querySelectorAll(selector) {
      if (selector === ".assembly-member-chip-region [data-assembly-ctg-id]") {
        return [chip];
      }
      if (selector === "[data-track-role='primary'][data-track-contig-id]") {
        return [group];
      }
      if (selector === "[data-band-track-role='primary'][data-band-contig-id]") {
        return [band];
      }
      return [];
    },
  };
  const host = {
    closest(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
  };
  const store = { getState: () => ({ assembly: {} }) };

  const { patchPrimaryHiddenCtgDom } = createController();
  const changed = patchPrimaryHiddenCtgDom(host, store, [2], { changedIds: [2] });

  assert.equal(changed, true);
  assert.equal(chipClassList.values.has("is-hidden-contig"), true);
  assert.match(insertedMarkup, /&lt;hidden&gt;/);
  assert.equal(groupClassList.values.has("is-hidden-contig"), true);
  assert.equal(trackCtgClassList.values.has("is-hidden-contig"), true);
  assert.equal(transform, "translate(0 -30)");
  assert.equal(band.dataset.hiddenByPrimaryCtg, "1");
  assert.equal(band.style.display, "none");
});

test("assembly DOM patch controller removes only matching deleted primary nodes", () => {
  let groupRemoved = false;
  let bandRemoved = false;
  const group = {
    dataset: { trackContigId: "2" },
    remove() {
      groupRemoved = true;
    },
  };
  const band = {
    dataset: { bandContigId: "2" },
    remove() {
      bandRemoved = true;
    },
  };
  const routeHost = {
    querySelectorAll(selector) {
      if (selector === "[data-track-role='primary'][data-track-contig-id]") {
        return [group];
      }
      if (selector === "[data-band-track-role='primary'][data-band-contig-id]") {
        return [band];
      }
      return [];
    },
  };
  const host = {
    closest(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
  };

  const { patchDeletedPrimaryTrackCtgsDom } = createController();

  assert.equal(patchDeletedPrimaryTrackCtgsDom(host, [2]), true);
  assert.equal(groupRemoved, true);
  assert.equal(bandRemoved, true);
});
