import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import { bindFinalPathTooltips } from "../final-path-tooltip-runtime.js";
import { buildFinalPathTooltip, resolveFinalPathSourceRange } from "../final-path-presentation.js";

function fixture() {
  const events = new Map(); let panel;
  const host = { isConnected: true, children: [], closest() { return this; },
    contains(node) { return this.children.includes(node); }, append(node) { this.children.push(node); },
    addEventListener(type, callback) { const list = events.get(type) || []; list.push(callback); events.set(type, list); },
    ownerDocument: { defaultView: { innerWidth: 900, innerHeight: 600 }, createElement() {
      const classes = new Set(["is-hidden"]);
      panel = { style: {}, attrs: {}, offsetWidth: 240, offsetHeight: 100,
        classList: { add: v => classes.add(v), remove: v => classes.delete(v), contains: v => classes.has(v) },
        setAttribute(k, v) { this.attrs[k] = v; } }; return panel;
    } },
  };
  const fire = (type, target, extra = {}) => events.get(type)?.forEach(fn => fn({ target, clientX: 899, clientY: 599, ...extra }));
  const group = text => { const g = { isConnected: true, getAttribute: () => text,
    closest: () => g, contains: node => node === g || node?.parent === g }; return g; };
  bindFinalPathTooltips(host);
  return { host, events, fire, group, panel: () => panel };
}

test("Final Path tooltip is synchronous with no dwell timer and accepts escaped plain text", () => {
  const h = fixture(), group = h.group("<full name>\nAdopted length: 5,000 bp");
  h.fire("pointerover", group);
  assert.equal(h.panel().attrs["aria-hidden"], "false");
  assert.equal(h.panel().textContent, "<full name>\nAdopted length: 5,000 bp");
  assert.equal(h.panel().style.left, "652px");
  assert.equal(h.panel().style.top, "492px");
  assert.equal(h.host.children.length, 1);
});

test("bar and label share one hover group without hiding, reset on scroll/interaction", () => {
  const h = fixture(), group = h.group("fragment");
  const label = { parent: group, closest: () => group };
  h.fire("pointerover", group);
  h.fire("pointerout", group, { relatedTarget: label });
  assert.equal(h.panel().attrs["aria-hidden"], "false");
  h.fire("pointermove", label, { clientX: 20, clientY: 30 });
  assert.equal(h.panel().style.left, "34px");
  for (const type of ["scroll", "pointerdown", "contextmenu", "keydown"]) {
    h.fire(type, label); assert.equal(h.panel().attrs["aria-hidden"], "true");
    h.fire("pointerover", group);
  }
  h.fire("pointerout", label, { relatedTarget: null });
  assert.equal(h.panel().attrs["aria-hidden"], "true");
});

test("delegation tolerates markup patches, disconnected fragments and repeated bindings", () => {
  const h = fixture(); bindFinalPathTooltips(h.host);
  assert.equal(h.events.get("pointerover").length, 1);
  const old = h.group("old"); old.isConnected = false;
  h.fire("pointerover", old); assert.equal(h.panel().attrs["aria-hidden"], "true");
  const next = h.group("new"); h.host.children = [];
  h.fire("pointerover", next);
  assert.ok(h.host.contains(h.panel()));
  assert.equal(h.panel().textContent, "new");
});

const segment = { type: "ctg", assemblyCtgId: 1, datasetName: "Data", ctgName: "ctg1",
  overallLen: 10000, start: 5001, end: 10000 };

test("tooltip leads with adopted length, not the full Contig length", () => {
  assert.equal(buildFinalPathTooltip(segment),
    "Data_ctg1\nAdopted length: 5,000 bp\nSource Contig length: 10,000 bp\nSource interval: 5,001–10,000 bp\nOrientation: +");
});

test("fragment source offset and source total remain distinct from adopted coordinates", () => {
  const sources = [{ assemblyCtgId: 1, sourceFragment: { sourceStart: 2001, sourceEnd: 6000, sourceLength: 10000 } }];
  const value = { ...segment, overallLen: 4000, start: 3000, end: 1001 };
  assert.match(buildFinalPathTooltip(value, { sourceCtgs: sources }),
    /Adopted length: 2,000 bp\nSource Contig length: 10,000 bp\nSource interval: 3,001–5,000 bp\nOrientation: -/);
});

test("source-provenance coordinates do not override committed edits or get double-offset", () => {
  const value = { ...segment, source: { dataset: "Data", contig: "ctg1", start: 1, end: 10000 } };
  const range = resolveFinalPathSourceRange(value, [{ assemblyCtgId: 1, sourceFragment: { sourceStart: 5001, sourceLength: 10000 } }]);
  assert.equal(range.sourceStart, 5001); assert.equal(range.sourceEnd, 10000);
});

test("reference tooltip uses source chromosome coordinates, GAP/draft do not invent a range", () => {
  const reference = { ...segment, sourceKind: "ref_segment", referenceChrName: "Chr1",
    memberStartBp: 20001, memberEndBp: 30000 };
  assert.match(buildFinalPathTooltip(reference), /Source interval: 25,001–30,000 bp/);
  assert.equal(buildFinalPathTooltip({ type: "gap", gapSizeBp: 100 }), "");
  assert.equal(buildFinalPathTooltip({ type: "ctg" }), "");
});


test("rebind after a fragment-local patch hides a stale tooltip without rebuilding its owner", () => {
  const h = fixture(), node = h.group("old fragment");
  h.fire("pointerover", node); assert.equal(h.panel().attrs["aria-hidden"], "false");
  node.isConnected = false; bindFinalPathTooltips(h.host);
  assert.equal(h.panel().attrs["aria-hidden"], "true");
  assert.equal(h.events.get("pointerover").length, 1);
});


test("dragging across fragments keeps tooltip hidden; release restores ordinary hover", () => {
  const h = fixture(), first = h.group("first"), second = h.group("second");
  h.fire("pointerover", first); h.fire("pointerdown", first, { buttons: 1 });
  assert.equal(h.panel().attrs["aria-hidden"], "true");
  h.fire("pointerover", second, { buttons: 1 }); h.fire("pointermove", second, { buttons: 1 });
  assert.equal(h.panel().attrs["aria-hidden"], "true");
  h.fire("pointerup", second, { buttons: 0 });
  assert.equal(h.panel().attrs["aria-hidden"], "false"); assert.equal(h.panel().textContent, "second");
  h.fire("pointercancel", second); assert.equal(h.panel().attrs["aria-hidden"], "true");
});


test("Final Path bar and label are hit-testable as one group without changing other views", () => {
  const css = readFileSync(new URL("../../../../styles/assembly.css", import.meta.url), "utf8");
  assert.match(css, /\.assembly-final-path-svg \[data-final-path-tooltip\] > \.track-ctg-label\s*\{\s*pointer-events: all;/);
  assert.match(css, /\.track-ctg-label\s*\{[^}]*pointer-events: none;/);
});
