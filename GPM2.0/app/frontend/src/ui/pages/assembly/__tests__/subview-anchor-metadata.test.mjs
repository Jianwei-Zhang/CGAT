import test from "node:test";
import assert from "node:assert/strict";
import { renderCompactSubviewAnchors, readSubviewAnchorAttribute } from "../subview-anchor-metadata.js";
import { buildSubviewAnchorObjectId, collectSubviewAnchorScene } from "../subview-anchor-objects.js";
import { resolveSubviewAnchorEdgeContextTarget } from "../context-menu.js";
import { projectRenderedSubviewToComposition } from "../subview-composition-controller.js";
import { createState } from "./tabs-semantics-harness.mjs";
const escapeAttr = value => String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
const edge = (index = 0) => ({ hitKey: `hit:${index}`, edge: index % 2 ? "right" : "left", topContigId: 1, bottomContigId: 2,
  topEndpointKey: "primary:1", bottomEndpointKey: "support:2", topLengthBp: 1000, bottomLengthBp: 2000,
  topName: 'ctg <a> & "b"', bottomName: "other", topSourceLabel: "primary", bottomSourceLabel: "support",
  topSourceRole: "primary", bottomSourceRole: "support", topSourceKind: "mother", bottomSourceKind: "mirror",
  topSourceName: "hifiasm", bottomSourceName: "flye", topCutBp: 100+index, bottomCutBp: 200+index,
  topX: 10+index, bottomX: 20+index });
const render = edges => renderCompactSubviewAnchors(edges, { topY: 20, bottomY: 70 }, { escapeAttr, buildObjectId: buildSubviewAnchorObjectId });
function nodes(markup) {
  const result = []; let group;
  const parse = tag => new Map([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(([,k,v]) => [k,v.replaceAll("&quot;", '"').replaceAll("&lt;", "<").replaceAll("&gt;", ">").replaceAll("&amp;", "&")]));
  for (const [tag] of markup.matchAll(/<g\b[^>]*>|<line\b[^>]*>/g)) {
    const attrs = parse(tag);
    if (tag.startsWith("<g ")) { group = { getAttribute: key => attrs.get(key) ?? null }; continue; }
    const parent = group;
    const node = { getAttribute: key => attrs.get(key) ?? null, closest: selector => selector.includes("metadata") ? parent : node };
    if (attrs.has("data-subview-anchor-kind")) result.push(node);
  }
  return result;
}
test("22,008 independent anchor targets retain all cuts and keys while endpoint provenance is shared once", () => {
  const edges = Array.from({ length: 22008 }, (_, i) => edge(i));
  const html = render(edges);
  assert.equal((html.match(/class="subview-anchor-hit-zone/g) || []).length, edges.length);
  assert.equal((html.match(/data-subview-anchor-metadata="1"/g) || []).length, 1);
  assert.equal((html.match(/data-subview-anchor-top-name=/g) || []).length, 1);
  assert.doesNotMatch(html, /class="subview-anchor-line/);
  const rendered = nodes(html);
  assert.equal(rendered.length, edges.length);
  for (const i of [0,100,22007]) {
    assert.equal(rendered[i].getAttribute("data-subview-anchor-top-cut-bp"), String(edges[i].topCutBp));
    assert.equal(rendered[i].getAttribute("data-subview-anchor-object-id"), buildSubviewAnchorObjectId("evidence", edges[i].hitKey, edges[i].edge));
  }
});
test("shared metadata hydrates the same scene descriptors and context menu without losing source identity", () => {
  const rendered = nodes(render([edge()]));
  const scene = collectSubviewAnchorScene({ querySelectorAll: () => rendered });
  assert.equal(scene[0].descriptor.top.name, edge().topName);
  assert.equal(scene[0].descriptor.top.lengthBp, 1000);
  assert.equal(scene[0].descriptor.bottom.sourceKind, "mirror");
  const context = resolveSubviewAnchorEdgeContextTarget(rendered[0]);
  assert.equal(context.topEndpointKey, "primary:1");
  assert.equal(context.bottomSourceName, "flye");
  assert.equal(context.topX, 10); assert.equal(context.topCutBp, 100);
});
test("provenance changes create separate consecutive groups and never reorder edge records", () => {
  const first = edge(), second = { ...edge(1), topSourceName: "another source" }, third = edge(2);
  const html = render([first, second, third]), rendered = nodes(html);
  assert.equal((html.match(/data-subview-anchor-metadata="1"/g) || []).length, 3);
  assert.deepEqual(rendered.map(node => readSubviewAnchorAttribute(node, "data-subview-anchor-top-source-name")), ["hifiasm", "another source", "hifiasm"]);
  assert.deepEqual(rendered.map(node => node.getAttribute("data-subview-anchor-hit-key")), ["hit:0", "hit:1", "hit:2"]);
});
test("explicit empty node metadata overrides its parent; legacy nodes still read directly", () => {
  assert.equal(readSubviewAnchorAttribute({ getAttribute: () => "", closest: () => ({ getAttribute: () => "wrong" }) }, "data-subview-anchor-top-name"), "");
  assert.equal(readSubviewAnchorAttribute({ getAttribute: () => "legacy" }, "data-subview-anchor-top-name"), "legacy");
});
test("compact active/manual display lines stay visible outside the hidden hit-target groups", () => {
  const html = render([{ ...edge(), active: true }, { ...edge(1), active: true, manualAnchorId: "manual-1" }]);
  assert.equal((html.match(/class="subview-anchor-line is-active"/g) || []).length, 2);
  assert.ok(html.indexOf('class="subview-anchor-line') > html.lastIndexOf("</g>"));
  assert.equal(nodes(html).length, 2);
});
test("history migration reads shared provenance and does not overwrite active anchors with display-only lines", () => {
  const state = createState({ assembly: { chrCtgs: [{ assemblyCtgId: 1, name: "one", totalLength: 1000 }, { assemblyCtgId: 2, name: "two", totalLength: 2000 }],
    subview: { summary: { mode: "2-contig", top: { role: "primary", contigId: 1 }, bottom: { role: "primary", contigId: 2 } }, activeAnchors: [{ hitKey: "hit:0", edge: "left" }] } } });
  const html = '<div data-subview-domain-span-bp="2000" data-subview-inner-width="100"><svg>' + render([{ ...edge(), active: true }]) + '</svg></div>';
  const composition = projectRenderedSubviewToComposition(state, html);
  assert.equal(composition.activeAnchors.length, 1);
  assert.equal(composition.activeAnchors[0].descriptor.top.cutBp, 100);
  assert.equal(composition.activeAnchors[0].descriptor.top.name, edge().topName);
});
