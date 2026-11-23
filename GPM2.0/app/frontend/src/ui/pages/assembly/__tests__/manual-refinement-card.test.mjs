import test from "node:test";
import assert from "node:assert/strict";

import { renderManualRefinementCard } from "../manual-refinement-card.js";
import {
  bindManualRefinementCard,
  registerManualRefinementLocus,
} from "../manual-refinement-runtime.js";
import {
  buildManualRefinementExportRequest,
  normalizeManualRefinementState,
} from "../manual-refinement-state.js";

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;");
const escapeAttr = (value) => escapeHtml(value).replaceAll('"', "&quot;");

const sampleFinalPathEntry = {
  chrName: "Chr01",
  segments: [
    { segmentId: "seg-1", type: "ctg", ctgName: "ctg_left_very_long_identifier_001", overallLen: 5000, start: 1, end: 5000 },
    { segmentId: "gap-1", type: "gap", length: 100 },
    { segmentId: "seg-2", type: "ctg", ctgName: "ctg_right_very_long_identifier_002", overallLen: 6000, start: 1, end: 6000 },
  ],
};

test("renderManualRefinementCard renders separate Gap and Tel blocks, per-tool gap rows, and hides empty blocks", () => {
  const bothHtml = renderManualRefinementCard(
    {
      chrName: "Chr01",
      finalPathEntry: sampleFinalPathEntry,
      locale: "zh",
      manualRefinement: {
        panelOpen: true,
        readsMode: "inherit",
        loci: [
          {
            chr: "Chr01",
            kind: "gap",
            segmentId: "gap-1",
            label: "ctg_left_very_long_identifier_001 ↔ ctg_right_very_long_identifier_002",
            tools: ["degap", "tgsgapcloser"],
          },
          {
            chr: "Chr01",
            kind: "tel_left",
            segmentId: "seg-1",
            label: "ctg_left_very_long_identifier_001",
            motif: "TTTAGGG",
          },
          {
            chr: "Chr02",
            kind: "gap",
            segmentId: "gap-9",
            label: "ctgA ↔ ctgB",
            tool: "quartet",
          },
        ],
      },
    },
    { escapeAttr, escapeHtml },
  );

  // Chr01 has 2 gap tool jobs + 1 tel job = 3; project total = 4.
  assert.match(bothHtml, /data-manual-ref-count-current[\s\S]*?>Chr01 · 3</);
  assert.match(bothHtml, /data-manual-ref-count-all[\s\S]*?>全部 · 4</);
  assert.match(bothHtml, /data-manual-ref-gap-section/);
  assert.match(bothHtml, /data-manual-ref-tel-section/);
  assert.match(bothHtml, /data-manual-ref-gap-row="Chr01\tgap\tgap-1"/);
  assert.match(bothHtml, /data-manual-ref-gap-tool-row="Chr01\tgap\tgap-1"\s+data-manual-ref-tool="degap"/);
  assert.match(bothHtml, /data-manual-ref-gap-tool-row="Chr01\tgap\tgap-1"\s+data-manual-ref-tool="tgsgapcloser"/);
  assert.doesNotMatch(bothHtml, /data-manual-ref-gap-row="Chr02\tgap\tgap-9"/);
  assert.match(bothHtml, /data-app-tooltip="ctg_left_very_long_identifier_001 ↔ ctg_right_very_long_identifier_002"[\s\S]*?data-app-tooltip-overflow/);
  assert.match(bothHtml, /manual-ref-fixed-tool[\s\S]*?>DEGAP TelSeeker<\/span>/);
  assert.match(bothHtml, /data-manual-ref-motif-input[\s\S]*?value="TTTAGGG"/);
  assert.match(bothHtml, /data-manual-ref-settings-open/);
  assert.match(bothHtml, /button primary tiny manual-ref-export-primary"[\s\S]*?data-manual-ref-export="current-chr"[\s\S]*?导出 \(3\)/);
  assert.doesNotMatch(bothHtml, /manual-ref-quick-add/);

  // Only Gap present -> Tel block is NOT rendered.
  const gapOnlyHtml = renderManualRefinementCard(
    {
      chrName: "Chr01",
      locale: "zh",
      manualRefinement: {
        panelOpen: true,
        loci: [{ chr: "Chr01", kind: "gap", segmentId: "gap-1", label: "a ↔ b", tools: ["quartet"] }],
      },
    },
    { escapeAttr, escapeHtml },
  );
  assert.match(gapOnlyHtml, /data-manual-ref-gap-section/);
  assert.doesNotMatch(gapOnlyHtml, /data-manual-ref-tel-section/);

  // Only Tel present -> Gap block is NOT rendered.
  const telOnlyHtml = renderManualRefinementCard(
    {
      chrName: "Chr01",
      locale: "zh",
      manualRefinement: {
        panelOpen: true,
        loci: [{ chr: "Chr01", kind: "tel_right", segmentId: "seg-2", label: "ctg_r" }],
      },
    },
    { escapeAttr, escapeHtml },
  );
  assert.doesNotMatch(telOnlyHtml, /data-manual-ref-gap-section/);
  assert.match(telOnlyHtml, /data-manual-ref-tel-section/);
});

test("renderManualRefinementCard renders top-right settings modal with 4 tool tabs and reads tab", () => {
  const modalHtml = renderManualRefinementCard(
    {
      chrName: "Chr01",
      locale: "en",
      manualRefinement: {
        panelOpen: true,
        settingsOpen: true,
        settingsTab: "tgsgapcloser",
        readsMode: "override",
        hifiReadsInput: "/reads/hifi.fq.gz",
        toolParams: {
          degap: { max_extension_rounds: "unlimited", kmer_filter: false },
          lrgapcloser: { iterations: 5 },
          tgsgapcloser: { hifi_correction: "native_racon", hifi_racon_rounds: 2, hifi_minimap: "-x map-hifi" },
          quartet: { minimap: "-x asm10" },
        },
        loci: [{ chr: "Chr01", kind: "gap", segmentId: "gap-1", label: "c1 ↔ c2", tool: "lrgapcloser" }],
        lastExport: {
          batchSha256: "abcdef1234567890",
          outputPath: "/tmp/proj_Chr01_refinement_tasks.zip",
          scope: "current-chr",
          chrName: "Chr01",
          lociCount: 1,
          tasksCount: 1,
        },
      },
    },
    { escapeAttr, escapeHtml },
  );

  assert.match(modalHtml, /data-manual-ref-settings-modal/);
  assert.match(modalHtml, /data-manual-ref-settings-tab="degap"/);
  assert.match(modalHtml, /data-manual-ref-settings-tab="lrgapcloser"/);
  assert.match(modalHtml, /data-manual-ref-settings-tab="tgsgapcloser"[\s\S]*?aria-selected="true"/);
  assert.match(modalHtml, /data-manual-ref-settings-tab="quartet"/);
  assert.match(modalHtml, /data-manual-ref-settings-tab="reads"/);
  assert.match(modalHtml, /data-manual-ref-param-tool="tgsgapcloser" data-manual-ref-param-field="hifi_minimap"/);
  assert.match(modalHtml, /data-manual-ref-receipt/);
  assert.match(modalHtml, /data-manual-ref-copy-cmd="python \.lib\/tools\/refine\.py proj_Chr01_refinement_tasks\.zip"/);
});

test("registerManualRefinementLocus adds unique (gap, tool) jobs and remove-tool deletes one tool at a time", () => {
  const handlers = {};
  const host = { addEventListener: (name, fn) => { handlers[name] = fn; } };
  let state = {
    locale: "zh",
    assembly: {
      selectedChrName: "Chr01",
      finalPathByChr: { Chr01: sampleFinalPathEntry },
      degap: { manualRefinement: { loci: [] } },
    },
  };
  const store = { getState: () => state, setState: (next) => { state = next; } };
  bindManualRefinementCard(host, store);

  assert.equal(registerManualRefinementLocus(host, store, { chrName: "Chr01", kind: "gap", segmentId: "gap-1", tool: "degap" }), true);
  // Duplicate (gap-1, degap) is ignored.
  assert.equal(registerManualRefinementLocus(host, store, { chrName: "Chr01", kind: "gap", segmentId: "gap-1", tool: "degap" }), false);
  // Adding a second distinct tool to the same gap appends cleanly.
  assert.equal(registerManualRefinementLocus(host, store, { chrName: "Chr01", kind: "gap", segmentId: "gap-1", tool: "quartet" }), true);
  assert.deepEqual(state.assembly.degap.manualRefinement.loci[0].tools, ["degap", "quartet"]);

  // Remove only degap tool -> quartet remains.
  const removeBtn = {
    dataset: { manualRefLocusKey: "Chr01\tgap\tgap-1", manualRefTool: "degap" },
    closest: (selector) => (selector === "[data-manual-ref-remove-tool]" ? removeBtn : null),
  };
  handlers.click({ target: removeBtn });
  assert.deepEqual(state.assembly.degap.manualRefinement.loci[0].tools, ["quartet"]);

  // Remove last remaining tool -> gap row is removed completely.
  const removeLast = {
    dataset: { manualRefLocusKey: "Chr01\tgap\tgap-1", manualRefTool: "quartet" },
    closest: (selector) => (selector === "[data-manual-ref-remove-tool]" ? removeLast : null),
  };
  handlers.click({ target: removeLast });
  assert.equal(state.assembly.degap.manualRefinement.loci.length, 0);
});

test("tool parameter edits persist and serialize into export request only when customized", () => {
  const handlers = {};
  const host = { addEventListener: (name, fn) => { handlers[name] = fn; } };
  let state = {
    locale: "zh",
    assembly: {
      degap: {
        manualRefinement: {
          loci: [{ chr: "Chr01", kind: "gap", segmentId: "g1", tools: ["degap", "lrgapcloser"] }],
        },
      },
    },
  };
  const store = { getState: () => state, setState: (next) => { state = next; } };
  bindManualRefinementCard(host, store);

  // Default state omits tool_parameters.
  const defaultReq = buildManualRefinementExportRequest(state.assembly.degap.manualRefinement).request;
  assert.equal("tool_parameters" in defaultReq, false);

  // Change LR_Gapcloser iterations to 5 and DEGAP max_extension_rounds to unlimited.
  const lrInput = {
    type: "number",
    value: "5",
    dataset: { manualRefParamTool: "lrgapcloser", manualRefParamField: "iterations" },
    closest: (selector) => (selector === "[data-manual-ref-param-field]" ? lrInput : null),
  };
  handlers.change({ target: lrInput });

  const unlimitedBox = {
    type: "checkbox",
    checked: true,
    dataset: { manualRefParamTool: "degap", manualRefParamUnlimited: "max_extension_rounds" },
    closest: (selector) => (selector === "[data-manual-ref-param-unlimited]" ? unlimitedBox : null),
  };
  handlers.change({ target: unlimitedBox });

  const persisted = JSON.parse(JSON.stringify(state.assembly.degapProjectState)).manualRefinement;
  const restored = normalizeManualRefinementState(persisted);
  const built = buildManualRefinementExportRequest(restored);
  assert.equal(built.ok, true);
  assert.deepEqual(built.request.tool_parameters, {
    degap: { max_extension_rounds: "unlimited" },
    lrgapcloser: { iterations: 5 },
  });
});

test("the queue defaults to expanded on restore but can be collapsed without hiding its counts", () => {
  const args = {
    chrName: "Chr01",
    manualRefinement: { loci: [{ chr: "Chr01", kind: "gap", segmentId: "gap-1" }] },
  };
  assert.match(renderManualRefinementCard(args, { escapeAttr, escapeHtml }), /data-manual-ref-body/);
  args.manualRefinement.panelOpen = false;
  const collapsed = renderManualRefinementCard(args, { escapeAttr, escapeHtml });
  assert.doesNotMatch(collapsed, /data-manual-ref-body/);
  assert.match(collapsed, /aria-expanded="false"/);
  assert.match(collapsed, /data-manual-ref-count-current[\s\S]*?>Chr01 · 1</);
});
