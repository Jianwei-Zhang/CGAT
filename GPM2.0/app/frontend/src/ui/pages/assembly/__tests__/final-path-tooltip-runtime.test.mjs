import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { tooltipFixture } from "../../../__tests__/tooltip-fixture.mjs";
import { bindFinalPathTooltips } from "../final-path-tooltip-runtime.js";
import { bindImmediateTooltips, hideImmediateTooltips } from "../immediate-tooltip-runtime.js";
import { buildFinalPathTooltip, resolveFinalPathSourceRange } from "../final-path-presentation.js";
import { rememberAssemblyDom, restoreAssemblyDom, clearAssemblySessionCache } from "../../../shell/assembly-session-cache.js";

const segment = { type: "ctg", assemblyCtgId: 1, datasetName: "Data", ctgName: "ctg1",
  overallLen: 10000, start: 5001, end: 10000 };

test("tooltip leads with adopted length, not the full Contig length", () => {
  assert.equal(buildFinalPathTooltip(segment),
    "Data_ctg1\nAdopted length: 5,000 bp\nSource contig length: 10,000 bp\nSource interval: 5,001–10,000 bp\nOrientation: +");
});

test("fragment source offset and source total remain distinct from adopted coordinates", () => {
  const sources = [{ assemblyCtgId: 1, sourceFragment: { sourceStart: 2001, sourceEnd: 6000, sourceLength: 10000 } }];
  const value = { ...segment, overallLen: 4000, start: 3000, end: 1001 };
  assert.match(buildFinalPathTooltip(value, { sourceCtgs: sources }),
    /Adopted length: 2,000 bp\nSource contig length: 10,000 bp\nSource interval: 3,001–5,000 bp\nOrientation: -/);
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



test("Final Path and member adapters share the App owner and cannot show two panels", () => {
  const h = tooltipFixture(); bindFinalPathTooltips(h.host);
  bindImmediateTooltips(h.host, { attribute: "data-member-tooltip", className: "member-card-tooltip" });
  const first = h.create("g", { "data-final-path-tooltip": "fragment" }, {}, true);
  const member = h.create("button", { "data-member-tooltip": "member" });
  h.fire("pointerover", first); assert.equal(h.panel.textContent, "fragment");
  h.fire("pointerover", member); assert.equal(h.panel.textContent, "member");
  assert.equal(first.getAttribute("aria-describedby"), null);
  assert.equal(h.doc.body.querySelectorAll(".app-tooltip").length, 1);
  assert.equal(h.events.get("pointerover").length, 1);
  hideImmediateTooltips(h.host); assert.equal(h.panel.getAttribute("aria-hidden"), "true");
});

test("Assembly DOM cache never captures/resurrects the document tooltip or replaces its owner", () => {
  clearAssemblySessionCache();
  const h = tooltipFixture(), member = h.create("button", { "data-member-tooltip": "member details" });
  h.host.append(member);
  const state = { locale: "en", session: { workspacePath: "D:/cache-hover", projectId: 1 } };
  h.fire("pointerover", member); assert.equal(h.panel.getAttribute("aria-hidden"), "false");
  assert.equal(rememberAssemblyDom(h.host, state), true);
  assert.equal(h.panel.getAttribute("aria-hidden"), "true");
  assert.equal(h.host.contains(h.panel), false);
  h.host.replaceChildren(); assert.equal(restoreAssemblyDom(h.host, state), true);
  bindFinalPathTooltips(h.host); bindImmediateTooltips(h.host);
  assert.equal(h.events.get("pointerover").length, 1);
  assert.equal(h.panel.getAttribute("aria-hidden"), "true");
  h.fire("pointerover", member); assert.equal(h.panel.getAttribute("aria-hidden"), "false");
  clearAssemblySessionCache();
});

test("Final Path label and bar retain shared hit testing without changing other views", () => {
  const css = readFileSync(new URL("../../../../styles/assembly.css", import.meta.url), "utf8");
  assert.match(css, /\.assembly-final-path-svg \[data-final-path-tooltip\] > \.track-ctg-label\s*\{\s*pointer-events: all;/);
  assert.match(css, /\.track-ctg-label\s*\{[^}]*pointer-events: none;/);
});
