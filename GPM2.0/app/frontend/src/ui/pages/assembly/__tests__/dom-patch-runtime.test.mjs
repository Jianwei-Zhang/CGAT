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

test("hiding a contig preserves remaining identity values in the rebuilt Canvas scene", () => {
  const bands = ["93.27", "0", ""].map((bandIdentityPct, index) => ({
    dataset: { bandContigId: String(index + 2), bandTrackRole: "primary", bandIdentityPct },
    style: {}, getAttribute: () => "0,0 50,0 50,50 0,50",
  }));
  const sceneNode = { textContent: JSON.stringify({ bands: [] }) };
  const layer = { querySelector: () => sceneNode };
  const scroll = {
    querySelector: () => ({ querySelectorAll: () => bands }),
    querySelectorAll: () => [layer],
  };
  const routeHost = {
    querySelectorAll(selector) {
      if (selector === ".assembly-track-scroll[data-track-role='primary']") return [scroll];
      if (selector === "[data-band-track-role='primary'][data-band-contig-id]") return bands;
      return [];
    },
  };
  let redraws = 0;
  const { patchPrimaryHiddenCtgDom } = createController({ bindBandCanvasRuntime: () => { redraws++; } });
  const host = { closest: () => routeHost };
  assert.equal(patchPrimaryHiddenCtgDom(host, { getState: () => ({ assembly: {} }) }, [4], { changedIds: [4] }), true);
  assert.deepEqual(JSON.parse(sceneNode.textContent).bands.map((band) => band.identityPct), ["93.27", "0"]);
  assert.equal(redraws, 1);
});

test("Subview panel patch preserves the mounted panel and viewport while replacing head and plot", () => {
  const liveScroll = { scrollLeft: 18817, scrollTop: 73 };
  const nextScroll = { scrollLeft: 0, scrollTop: 0 };
  const live = new Map(), next = new Map();
  const replaceable = (key, owner) => ({ replaceWith(node) { owner.set(key, node); } });
  live.set(".subview-panel-head", replaceable(".subview-panel-head", live));
  live.set(".subview-alignment-card", { replaceWith(node) {
    live.set(".subview-alignment-card", node); live.set(".subview-track-scroll", nextScroll);
  } });
  live.set(".subview-track-scroll", liveScroll);
  next.set(".subview-panel-head", { id: "next-head" });
  next.set(".subview-alignment-card", { id: "next-card" });
  next.set(".subview-track-scroll", nextScroll);
  const panel = { querySelector: (selector) => live.get(selector) || null };
  const nextPanel = { querySelector: (selector) => next.get(selector) || null };
  const fragment = { querySelector: (selector) => selector === "[data-subview-panel='1']" ? nextPanel : null };
  const routeHost = {
    ownerDocument: { createElement: () => ({ content: fragment, set innerHTML(_value) {} }) },
    querySelector: (selector) => selector === "[data-subview-panel='1']" ? panel : null,
  };
  const { patchSubviewPanelDom } = createController({ renderAssemblySubviewPanel: () => "<article></article>" });
  const replaced = patchSubviewPanelDom(routeHost, { getState: () => ({ assembly: {} }) });
  assert.deepEqual(replaced.map((node) => node.id), ["next-head", "next-card"]);
  assert.equal(routeHost.querySelector("[data-subview-panel='1']"), panel, "panel identity stays mounted");
  assert.equal(nextScroll.scrollLeft, 18817); assert.equal(nextScroll.scrollTop, 73);
});

test("hidden-state paint stays on the second member row and keeps immediate tooltip/status count current", () => {
  const values = new Set(), attrs = { "data-member-tooltip": "name\nContig length: 5,000 bp" }, inserted = [];
  const tags = { dataset: { memberStateCount: "2" }, querySelector: () => null,
    insertAdjacentHTML: (_where, html) => inserted.push(html) };
  const details = { querySelector: () => tags };
  const chip = { dataset: { assemblyCtgId: "2" }, classList: { contains: key => values.has(key), toggle: (key, on) => on ? values.add(key) : values.delete(key) },
    getAttribute: key => attrs[key], setAttribute: (key, value) => { attrs[key] = value; },
    querySelector: selector => selector === ".ctg-chip-details" ? details : null };
  const host = { closest() { return this; }, querySelectorAll: selector => selector === ".assembly-member-chip-region [data-assembly-ctg-id]" ? [chip] : [] };
  const { patchPrimaryHiddenCtgDom } = createController();
  patchPrimaryHiddenCtgDom(host, { getState: () => ({ assembly: {} }) }, [2], { changedIds: [2] });
  assert.equal(tags.dataset.memberStateCount, "3");
  assert.match(attrs["data-member-tooltip"], /\n<hidden>$/);
  assert.match(inserted.join(""), /ctg-chip-hidden-tag/); assert.match(inserted.join(""), />\+2<\/span>/);
});

for (const mode of ["track", "members-only"]) {
  for (const changed of [false, true]) {
    test(`${mode} patch ${changed ? "discards old-owner" : "retains same-owner"} member popup scroll and focus`, () => {
      let focusOptions = null;
      const active = { getAttribute: name => name === "data-assembly-ctg-id" ? "11" : null };
      const nextButton = { getAttribute: active.getAttribute, focus: options => { focusOptions = options; } };
      const oldScroll = { scrollTop: 145, scrollLeft: 3 }, nextScroll = { scrollTop: 0, scrollLeft: 0 };
      const oldPanel = { scrollTop: 75, scrollLeft: 0 }, nextPanel = { scrollTop: 0, scrollLeft: 0 };
      const group = (key, scroll, panel) => ({
        getAttribute: name => name === "data-assembly-scope-key" ? key : null,
        querySelector: selector => selector === ".assembly-member-chip-region" ? scroll
          : selector === "#assembly-members-panel-popover" ? panel : null,
        querySelectorAll: () => [nextButton], contains: node => node === active,
        matches: selector => selector === '[data-assembly-popup="members"]',
      });
      const liveGroup = group("project-1:chr-1", oldScroll, oldPanel);
      const nextGroup = group(changed ? "project-2:chr-1" : "project-1:chr-1", nextScroll, nextPanel);
      const section = value => mode === "members-only" ? value : {
        querySelector: selector => selector === '[data-assembly-popup="members"]' ? value : null,
      };
      const current = section(liveGroup), next = section(nextGroup);
      current.ownerDocument = { activeElement: active };
      current.replaceWith = value => { assert.equal(value, next); };
      const result = createController().replaceRenderedAssemblySection(
        { querySelector: () => current }, { querySelector: () => next }, mode);
      assert.equal(result, next);
      assert.equal(nextScroll.scrollTop, changed ? 0 : 145);
      assert.equal(nextScroll.scrollLeft, changed ? 0 : 3);
      assert.equal(nextPanel.scrollTop, changed ? 0 : 75);
      assert.deepEqual(focusOptions, changed ? null : { preventScroll: true });
    });
  }
}

test("chromosome selection retains the project-owned picker scroll while its selected option changes", () => {
  const currentPanel = { scrollTop: 280, scrollLeft: 0 }, nextPanel = { scrollTop: 0, scrollLeft: 0 };
  const group = panel => ({ getAttribute: () => "same-project",
    querySelector: selector => selector === "#assembly-chr-picker-panel" ? panel : null });
  const liveGroup = group(currentPanel), nextGroup = group(nextPanel);
  const current = { replaceWith() {}, querySelector: selector => selector === '[data-assembly-popup="chromosomes"]' ? liveGroup : null };
  const next = { querySelector: selector => selector === '[data-assembly-popup="chromosomes"]' ? nextGroup : null };
  createController().replaceRenderedAssemblySection({ querySelector: () => current }, { querySelector: () => next }, "track");
  assert.equal(nextPanel.scrollTop, 280);
});
