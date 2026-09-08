import test from "node:test";
import assert from "node:assert/strict";

import { renderSubviewCompositionPanel } from "../render-subview-composition.js";

const labels = {
  lanes: { top: "Top", bottom: "Bottom" },
  add: "Add",
  addTo: { top: "Add top", bottom: "Add bottom" },
  back: "Back",
  search: "Search",
  searchPlaceholder: "Find",
  sourceFilter: "Source",
  allSources: "All",
  sources: { primary: "Primary", support: "Support", phased: "Phased", ref: "Reference" },
  unknownSource: "Unknown",
  loading: "Loading",
  retry: "Retry",
  noMatches: "None",
  emptyLane: "Empty",
  addSelected: "Add ({count})",
  alreadyAdded: "Already",
  willMove: { top: "Move from top", bottom: "Move from bottom" },
  moveTo: { top: "Move top", bottom: "Move bottom" },
  remove: "Remove",
  compact: "Compact",
  flipped: "flipped",
  sourceUnavailable: "Unavailable",
};
const helpers = {
  escapeHtml: (value) => String(value ?? ""),
  escapeAttr: (value) => String(value ?? ""),
};

function member(id, lane, sourceRole = "support") {
  return {
    assemblyCtgId: id,
    source: { role: sourceRole, datasetId: id, datasetName: `ds${id}` },
    label: `ctg${id}`,
    lengthBp: 100,
    baseOrientation: "+",
    lane,
    xBp: id * 100,
  };
}

test("composition manager renders both lane counts and the focused member", () => {
  const flipped = {
    ...member(3, "bottom"),
    label: "ctg3 (+)",
    flipped: true,
  };
  const html = renderSubviewCompositionPanel({
    composition: { members: [member(2, "top"), member(1, "bottom"), flipped] },
    candidates: [],
    candidatesLoaded: false,
    ui: { view: "members", focusedEntityKey: "assembly:3" },
    labels,
  }, helpers);

  assert.match(html, /Top \(1\)/);
  assert.match(html, /Bottom \(2\)/);
  assert.match(html, /data-subview-composition-member="assembly:3"[\s\S]*aria-pressed="true"/);
  assert.match(html, /data-subview-composition-member="assembly:3"[\s\S]*title="ctg3 \(-\)"[\s\S]*<strong>ctg3 \(-\)<\/strong>/);
  assert.doesNotMatch(html, /ctg3 \(\+\) \(-\)/);
  assert.match(html, /data-subview-composition-add="top"/);
  assert.match(html, /data-subview-composition-add="bottom"/);
  assert.doesNotMatch(html, /data-subview-composition-swap/);
  assert.match(html, /data-subview-composition-compact="1">Compact<\/button>/);
});

test("composition picker makes a cross-lane add explicit and supports checked batches", () => {
  const existing = member(1, "bottom", "primary");
  const candidate = {
    ...existing,
    candidateKey: "assembly:1|primary:1:mother:0:0:",
    entityKey: "assembly:1",
    sourceKey: "primary:1:mother:0:0:",
  };
  const html = renderSubviewCompositionPanel({
    composition: { members: [existing] },
    candidates: [candidate],
    candidatesLoaded: true,
    ui: {
      view: "picker",
      targetLane: "top",
      query: "",
      source: "all",
      checkedKeys: [candidate.candidateKey],
      loading: false,
      error: "",
    },
    labels,
  }, helpers);

  assert.match(html, /Move from bottom/);
  assert.match(html, /<strong title="ctg1 \(\+\)">ctg1 \(\+\)<\/strong>/);
  assert.match(html, /data-subview-composition-candidate="assembly:1\|primary:1:mother:0:0:"[\s\S]*checked/);
  assert.match(html, />Add \(1\)<\/button>/);
});
