import test from "node:test";
import assert from "node:assert/strict";

import { renderManualRefinementCard } from "../manual-refinement-card.js";

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

test("renderManualRefinementCard renders compact single-select Gap rows, fixed Tel rows, overflow tooltips, and distinct scope counts", () => {
  const html = renderManualRefinementCard(
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
            tool: "degap",
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

  assert.match(html, /data-manual-ref-count-current>当前 Chr01 · 2<\/span>/);
  assert.match(html, /data-manual-ref-count-all>全项目 · 3<\/span>/);
  assert.doesNotMatch(html, /type="checkbox"/);
  assert.doesNotMatch(html, /manual-ref-seg-id/);
  assert.match(html, /data-app-tooltip="ctg_left_very_long_identifier_001 ↔ ctg_right_very_long_identifier_002"[\s\S]*?data-app-tooltip-overflow/);
  assert.match(html, /manual-ref-sr-only">Chr01 Gap ctg_left_very_long_identifier_001 ↔ ctg_right_very_long_identifier_002 \(gap-1\)/);
  assert.match(html, /class="manual-ref-tool-option is-selected"[\s\S]*?value="degap"[\s\S]*?checked/);
  assert.match(html, /class="manual-ref-tool-option is-selected"[\s\S]*?value="quartet"[\s\S]*?checked/);
  assert.match(html, /manual-ref-fixed-tool[\s\S]*?>DEGAP TelSeeker<\/span>/);
  assert.match(html, /data-manual-ref-motif-input[\s\S]*?value="TTTAGGG"/);
  assert.match(html, /<details class="manual-ref-reads-disclosure">/);
  assert.match(html, /button primary tiny manual-ref-export-primary"[\s\S]*?data-manual-ref-export="current-chr"[\s\S]*?导出当前染色体 \(2\)/);
  assert.match(html, /button tiny manual-ref-export-secondary"[\s\S]*?data-manual-ref-export="all"[\s\S]*?预览并导出全项目 \(3\)/);
});

test("renderManualRefinementCard covers empty, exporting, override reads, receipt, and English locale states", () => {
  const emptyHtml = renderManualRefinementCard(
    {
      chrName: "Chr01",
      finalPathEntry: sampleFinalPathEntry,
      locale: "en",
      manualRefinement: { panelOpen: true, loci: [] },
    },
    { escapeAttr, escapeHtml },
  );
  assert.match(emptyHtml, /Refinement Tasks/);
  assert.match(emptyHtml, /Chr01 · 0/);
  assert.match(emptyHtml, /Project · 0/);
  assert.match(emptyHtml, /manual-ref-empty/);
  assert.match(emptyHtml, /data-manual-ref-export="current-chr"[\s\S]*?disabled/);
  assert.match(emptyHtml, /data-manual-ref-export="all"[\s\S]*?disabled/);

  const exportingHtml = renderManualRefinementCard(
    {
      chrName: "Chr01",
      finalPathEntry: sampleFinalPathEntry,
      locale: "en",
      manualRefinement: {
        panelOpen: true,
        exporting: true,
        readsMode: "override",
        hifiReadsInput: "/reads/hifi.fq.gz",
        feedback: "Saving current Final Path...",
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
  assert.match(exportingHtml, /aria-busy="true"/);
  assert.match(exportingHtml, /manual-ref-exporting-pill/);
  assert.match(exportingHtml, /<details class="manual-ref-reads-disclosure" open>/);
  assert.match(exportingHtml, /data-manual-ref-reads-field="hifi"[\s\S]*?value="\/reads\/hifi\.fq\.gz"/);
  assert.match(exportingHtml, /data-manual-ref-receipt/);
  assert.match(exportingHtml, /data-manual-ref-copy-cmd="python \.lib\/tools\/refine\.py proj_Chr01_refinement_tasks\.zip"/);
});

test("the queue defaults to expanded on restore but can be collapsed without hiding its counts", () => {
  const args = { chrName: "Chr01", finalPathEntry: sampleFinalPathEntry,
    manualRefinement: { loci: [{ chr: "Chr01", kind: "gap", segmentId: "gap-1" }] } };
  assert.match(renderManualRefinementCard(args, { escapeAttr, escapeHtml }), /data-manual-ref-body/);
  args.manualRefinement.panelOpen = false;
  const collapsed = renderManualRefinementCard(args, { escapeAttr, escapeHtml });
  assert.doesNotMatch(collapsed, /data-manual-ref-body/);
  assert.match(collapsed, /aria-expanded="false"/);
  assert.match(collapsed, /data-manual-ref-count-current>当前 Chr01 · 1</);
});
