import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { renderFinalPathCard } from "../final-path-card.js";
import { renderDegapPanel } from "../degap-card.js";

function createDeps() {
  return {
    escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    },
    escapeAttr(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll('"', "&quot;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    },
  };
}

function createI18n() {
  return {
    page: {
      finalPathGraph: "图",
      finalPathTable: "表",
      finalPathDegap: "DEGAP",
      finalPathDegapControls: "DEGAP 图控件",
      finalPathLog: "日志",
      finalPathExport: "Export",
      finalPathExportPng: "图(.png)",
      finalPathExportTsv: "表(.tsv)",
      finalPathExportLog: "日志(.log)",
      finalPathExportFasta: "序列(.fasta)",
      finalPathExportDegapJobs: "DEGAP-JOBS",
      finalPathExportAll: "All",
      finalPathIndexCol: "#",
      finalPathCtgCol: "Ctg",
      finalPathOriginIdCol: "Origin ID",
      finalPathOverallLenCol: "overall_len",
      finalPathOrientCol: "orient",
      finalPathCtgStartCol: "Ctg_start",
      finalPathCtgEndCol: "Ctg_end",
      finalPathChrStartCol: "Chr_start",
      finalPathChrEndCol: "Chr_end",
      finalPathLogPrimaryCount: "used_主ds_ctg数目",
      finalPathLogPrimaryLength: "used_主ds_ctg长度",
      finalPathLogAppended: "实际 append",
      finalPathLogHidden: "主图 hidden",
      finalPathLogSupportTitle: "辅助 ds_ctg使用情况",
      finalPathLogOtherChrTitle: "重复主ds_ctg使用情况",
      finalPathLogNoRows: "暂无记录",
    },
    trackControls: {
      minTickUnitKb: "最小刻度单位(kb)",
      maxTickCount: "最多可展示数",
      openOptionCandidates: "打开{label}候选值",
    },
    degap: {
      settingsTitle: "DEGAP 设置",
      close: "关闭",
      settingsSummary: "配置服务器端 DEGAP gapfiller 路径；HiFi Reads PATH 或 ONT Reads PATH 至少填写一个。",
      requiredPaths: "必填路径",
      degapPath: "DEGAP PATH",
      hifiReadsPath: "HiFi Reads PATH",
      ontReadsPath: "ONT Reads PATH",
      gpmServerPath: "GPM_server PATH",
      mainOut: "Main DEGAP --out",
      jobOut: "Job --out",
      readsHelp: "READS path 为服务器端原始测序数据；HiFi 或 ONT 至少填写一个。",
      recommendedParameters: "推荐参数",
      otherGapfillerDefaults: "其他 gapfiller 默认参数",
      addLeftJob: "添加 Left-job",
      addRightJob: "添加 Right-job",
      addAllJob: "添加 All-job",
      jobsTitle: "任务",
      noJobs: "暂无 DEGAP 任务",
      removeJobAria: "删除任务",
      reset: "重置",
      save: "保存",
    },
  };
}

test("renderFinalPathCard renders DEGAP as a final path view between table and log", () => {
  const deps = createDeps();
  const entry = createEntry();
  const degapBody = renderDegapPanel(
    {
      finalPathEntry: entry,
      trackView: null,
      trackViewportPx: 900,
      primaryDatasetName: "hifiasm",
      degap: {
        settingsPanelDismissed: false,
        jobs: [{
          jobId: "Ctg9_vs_Ctg10_Left-job",
          label: "Ctg9_vs_Ctg10 Left-job",
          outPath: "/server/degap_out/Ctg9_vs_Ctg10_Left-job",
        }],
      },
    },
    {
      ...deps,
      i18n: createI18n(),
    },
  );
  const html = renderFinalPathCard(
    {
      projectName: "Demo",
      chrName: "Chr01",
      finalPathEntry: entry,
      viewMode: "degap",
      trackViewportPx: 900,
      primaryDatasetName: "hifiasm",
      degapTrackView: {
        minTickUnitKb: 500,
        maxTickCount: 15,
      },
      degapBody,
      canExportDegapJobs: true,
    },
    {
      ...deps,
      i18n: createI18n(),
    },
  );

  assert.match(html, /data-final-path-view-mode="graph"[\s\S]*data-final-path-view-mode="table"[\s\S]*data-final-path-view-mode="degap"[\s\S]*data-final-path-view-mode="log"/);
  assert.match(html, /<article class="card final-path-card" data-final-path-view-mode="degap"/);
  assert.match(html, /data-degap-panel/);
  assert.match(html, /data-degap-settings-modal/);
  assert.match(html, /data-degap-settings-open/);
  assert.doesNotMatch(html, /配置服务器端 DEGAP gapfiller 路径；HiFi Reads PATH 或 ONT Reads PATH 至少填写一个。/);
  assert.doesNotMatch(html, /DEGAP PATH 为必填项。/);
  assert.match(html, /<input type="text" data-degap-setting-field="hifiReads" value="" placeholder="\/server\/reads\/hifi.fastq.gz">/);
  assert.match(html, /<input type="text" data-degap-setting-field="ontReads" value="" placeholder="\/server\/reads\/ont.fastq.gz">/);
  assert.doesNotMatch(html, /<textarea[^>]+data-degap-setting-field="(?:hifiReads|ontReads)"/);
  assert.match(html, /<p class="helper-hint degap-form-help">READS path 为服务器端原始测序数据；HiFi 或 ONT 至少填写一个。<\/p>/);
  assert.match(html, /DEGAP-JOBS/);
  assert.match(html, /data-final-path-export-action="all"[\s\S]*final-path-export-divider[\s\S]*data-final-path-export-action="degap-jobs"/);
  assert.match(html, /class="final-path-card-head-controls"[\s\S]*最小刻度单位\(kb\)[\s\S]*data-track-combo-field="minTickUnitKb" data-degap-scale-combo-field="minTickUnitKb"[\s\S]*data-degap-scale-field="minTickUnitKb"[\s\S]*value="500"[\s\S]*最多可展示数[\s\S]*data-track-combo-field="maxTickCount" data-degap-scale-combo-field="maxTickCount"[\s\S]*data-degap-scale-field="maxTickCount"[\s\S]*value="15"[\s\S]*Export/);
  assert.doesNotMatch(html, /degap-graph-toolbar/);
  assert.match(html, /height="78"/);
  assert.doesNotMatch(html, /DEGAP-gapfiller-config/);
  assert.doesNotMatch(html, /DEGAP job added/);
  assert.doesNotMatch(html, /<span class="muted">1<\/span>/);
});

test("DEGAP reads help uses reusable helper hint styling", () => {
  const baseCss = readFileSync(new URL("../../../../styles/base.css", import.meta.url), "utf8");
  const componentsCss = readFileSync(new URL("../../../../styles/components.css", import.meta.url), "utf8");

  assert.match(baseCss, /--helper-hint-bg:\s*#fff7ed;/);
  assert.match(baseCss, /--helper-hint-border:\s*#f59e0b;/);
  assert.match(baseCss, /--helper-hint-text:\s*#92400e;/);
  assert.match(
    componentsCss,
    /\.helper-hint\s*\{[^}]*border-left:\s*3px solid var\(--helper-hint-border\);[^}]*background:\s*var\(--helper-hint-bg\);[^}]*color:\s*var\(--helper-hint-text\);/,
  );
  assert.match(
    componentsCss,
    /\.degap-form-help\s*\{[^}]*grid-column:\s*1 \/ -1;/,
  );
});

test("renderDegapPanel renders compact expanded job settings and icon controls", () => {
  const deps = createDeps();
  const jobId = "Ctg9_vs_Ctg10_Left-job";
  const html = renderDegapPanel(
    {
      finalPathEntry: createEntry(),
      trackView: null,
      trackViewportPx: 900,
      primaryDatasetName: "hifiasm",
      degap: {
        settingsPanelDismissed: true,
        expandedJobId: jobId,
        jobs: [{
          jobId,
          label: "Ctg9_vs_Ctg10 Left-job",
          outPath: "/server/degap_out/Ctg9_vs_Ctg10_Left-job",
          left: { assemblyCtgId: 9, start: 1, end: 1200 },
          right: { assemblyCtgId: 10, start: 1, end: 900 },
          settings: {
            degapPath: "/opt/DEGAP/bin/DEGAP.py",
            hifiReads: ["/reads/hifi-1.fq.gz", "/reads/hifi-2.fq.gz"],
            ontReads: ["/reads/ont.fq.gz"],
            gpmServerPath: "/srv/gpm_server",
            outRoot: "/srv/degap",
          },
        }],
      },
    },
    {
      ...deps,
      i18n: createI18n(),
    },
  );

  assert.match(html, /data-degap-jobs-panel/);
  assert.match(html, /class="degap-settings-button"[\s\S]*data-degap-settings-open/);
  assert.doesNotMatch(html, /class="button ghost tiny degap-settings-button"/);
  assert.match(html, /class="degap-job-remove"[\s\S]*data-degap-job-remove/);
  assert.match(html, /class="degap-job-expand"[\s\S]*aria-expanded="true"[\s\S]*▴/);
  assert.doesNotMatch(html, /class="degap-settings-fields is-job"/);
  assert.match(html, /class="degap-settings-fields"/);
  assert.match(html, /<input type="text" data-degap-job-field="hifiReads" value="\/reads\/hifi-1.fq.gz; \/reads\/hifi-2.fq.gz" placeholder="\/server\/reads\/hifi.fastq.gz">/);
  assert.match(html, /<input type="text" data-degap-job-field="ontReads" value="\/reads\/ont.fq.gz" placeholder="\/server\/reads\/ont.fastq.gz">/);
  assert.doesNotMatch(html, /<textarea[^>]+data-degap-job-field="(?:hifiReads|ontReads)"/);
  assert.match(html, />kmer_filter<\/span>/);
  assert.match(html, />MaximumExtensionRound<\/span>/);
  assert.match(html, />thread<\/span>/);
  assert.match(html, />filterDepthOnt<\/span>/);
  assert.doesNotMatch(html, />--kmer_filter<\/span>/);
  assert.doesNotMatch(html, />-t \/ --thread<\/span>/);
  assert.doesNotMatch(html, />--filterDepthOnt<\/span>/);
  assert.match(html, /class="degap-job-editor-foot"[\s\S]*data-degap-job-reset[\s\S]*data-degap-job-save/);
});

test("renderDegapPanel styles DEGAP job type badges", () => {
  const deps = createDeps();
  const html = renderDegapPanel(
    {
      finalPathEntry: createEntry(),
      trackView: null,
      trackViewportPx: 900,
      primaryDatasetName: "hifiasm",
      degap: {
        settingsPanelDismissed: true,
        jobs: [
          {
            jobId: "gapfiller-job",
            jobType: "gapfiller",
            label: "gapfiller job",
            outPath: "/server/degap_out/gapfiller-job",
            left: { assemblyCtgId: 9, start: 1, end: 1200 },
            right: { assemblyCtgId: 10, start: 1, end: 900 },
          },
          {
            jobId: "telseeker-job",
            jobType: "telseeker_ctg",
            label: "telseeker job",
            outPath: "/server/degap_out/telseeker-job",
            endpointCtg: "hifiasm_Ctg9",
            endpointEnd: "L",
            endpoint: { assemblyCtgId: 9, start: 1, end: 1200 },
          },
        ],
      },
    },
    {
      ...deps,
      i18n: createI18n(),
    },
  );

  assert.match(html, /<span class="degap-job-type-badge is-gapfiller">gapfiller<\/span>/);
  assert.match(html, /<span class="degap-job-type-badge is-telseeker">telseeker<\/span>/);
  assert.doesNotMatch(html, /telseeker-ctg/);
});

test("renderDegapPanel renders DEGAP messages as a card toast outside Jobs flow", () => {
  const deps = createDeps();
  const html = renderDegapPanel(
    {
      finalPathEntry: createEntry(),
      trackView: null,
      trackViewportPx: 900,
      primaryDatasetName: "hifiasm",
      degap: {
        settingsPanelDismissed: true,
        error: "已有该任务 Ctg9_vs_Ctg10 Left-job",
        jobs: [],
      },
    },
    {
      ...deps,
      i18n: createI18n(),
    },
  );

  assert.match(html, /class="degap-toast is-danger"[\s\S]*data-degap-toast[\s\S]*已有该任务 Ctg9_vs_Ctg10 Left-job/);
  assert.doesNotMatch(html, /degap-feedback/);
  assert.match(html, /data-degap-toast[\s\S]*<div class="degap-panel-body">[\s\S]*<section class="degap-jobs-panel"/);
});

function extractFinalPathSegmentHtml(html, segmentId) {
  const pattern = new RegExp(`data-final-path-segment-id="${segmentId}"[\\s\\S]*?</g>`);
  return html.match(pattern)?.[0] || "";
}

function createEntry() {
  return {
    mode: "segments",
    chrName: "Chr01",
    segments: [
      {
        segmentId: "seg-1",
        type: "ctg",
        assemblyCtgId: 9,
        datasetName: "hifiasm",
        ctgName: "Ctg9",
        originId: "utig4-001122l",
        overallLen: 1200,
        start: 1,
        end: 1200,
      },
      {
        segmentId: "seg-2",
        type: "gap",
        gapSizeBp: 100,
      },
      {
        segmentId: "seg-3",
        type: "ctg",
        assemblyCtgId: 10,
        datasetName: "flye",
        ctgName: "Ctg10",
        originId: "contig_98",
        overallLen: 800,
        start: 700,
        end: 200,
      },
    ],
    totalLength: 1701,
    updatedAt: "",
  };
}

function createRefEntry() {
  return {
    mode: "segments",
    chrName: "Chr01",
    segments: [
      {
        segmentId: "seg-ref",
        type: "ctg",
        sourceKind: "ref_segment",
        referenceChrId: 1,
        referenceChrName: "Chr01",
        ctgName: "ref_Chr01:5201-5600",
        originId: "Chr01:5201-5600",
        overallLen: 400,
        start: 5201,
        end: 5600,
      },
      {
        segmentId: "seg-ds",
        type: "ctg",
        assemblyCtgId: 9,
        datasetName: "hifiasm",
        ctgName: "Ctg9",
        originId: "utig4-001122l",
        overallLen: 1200,
        start: 1,
        end: 1200,
      },
    ],
    totalLength: 1600,
    updatedAt: "",
  };
}

test("renderFinalPathCard respects the requested graph mode when current chr has no final path", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: null,
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /projA_Chr01 path/);
  assert.match(html, /data-final-path-view-mode="graph"/);
  assert.match(html, /assembly-final-path-svg/);
  assert.match(html, /data-final-path-export-toggle="true"/);
  assert.match(html, /data-final-path-export-action="png"/);
  assert.match(html, /data-final-path-export-action="tsv"/);
  assert.match(html, /data-final-path-export-action="fasta"/);
  assert.match(html, /data-final-path-export-action="all"/);
  assert.doesNotMatch(html, /data-final-path-view-mode="log"/);
  assert.doesNotMatch(html, /data-final-path-export-action="log"/);
});

test("renderFinalPathCard integrates phased haplotype switching as an upper-left dropdown", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01B",
      finalPathEntry: createEntry(),
      viewMode: "graph",
      phasedFinalPathOptions: [
        { key: "A", chrName: "Chr01A", active: false },
        { key: "B", chrName: "Chr01B", active: true },
        { key: "C", chrName: "Chr01C", active: false },
      ],
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /class="final-path-phased-selector"/);
  assert.match(html, /data-phased-final-path-menu="true"/);
  assert.match(html, /data-phased-final-path-current-key="B"/);
  assert.match(html, /data-phased-final-path-key="A"/);
  assert.match(html, /data-phased-final-path-key="C"/);
  assert.ok(
    html.indexOf("projA_Chr01B path") < html.indexOf("data-phased-final-path-menu"),
    "expected selector to be placed beside the final path title",
  );
  assert.doesNotMatch(html, /role="tablist" aria-label="Haplotype path"/);
});

test("renderFinalPathCard keeps all export while hiding fasta when fasta is unavailable", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: null,
      viewMode: "graph",
      trackViewportPx: 800,
      canExportFasta: false,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /data-final-path-export-action="png"/);
  assert.match(html, /data-final-path-export-action="tsv"/);
  assert.doesNotMatch(html, /data-final-path-export-action="fasta"/);
  assert.match(html, /data-final-path-export-action="all"/);
});

test("renderFinalPathCard shows an editable draft row in table mode when current chr has no final path", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: null,
      viewMode: "table",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /data-final-path-view-mode="table"/);
  assert.match(html, /class="final-path-card-table-body"/);
  assert.match(html, /data-final-path-empty-row="true"/);
  assert.match(html, /data-final-path-export-toggle="true"/);
  assert.match(html, /<input type="text" data-final-path-empty-cell="ctg" value="" autocomplete="off" \/>/);
  assert.match(html, /<input type="text" data-final-path-empty-cell="overall-len" value="" disabled \/>/);
  assert.doesNotMatch(html, /data-final-path-segment-id=/);
});

test("renderFinalPathCard graph mode renders ctg + gap segments", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: createEntry(),
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );
  assert.match(html, /projA_Chr01 path/);
  assert.match(html, /data-final-path-view-mode="graph"/);
  assert.match(html, /hifiasm_Ctg9/);
  assert.match(html, /class="assembly-track-svg assembly-final-path-svg"/);
  assert.match(html, /data-final-path-segment-id="seg-1"/);
  assert.match(html, /data-final-path-segment-id="seg-2"/);
  assert.match(html, /data-final-path-segment-type="ctg"/);
  assert.match(html, /data-final-path-segment-type="gap"/);
  assert.match(html, /final-path-gap-marker/);
  assert.match(html, />GAP</);
  assert.match(
    html,
    /data-final-path-segment-id="seg-1"[\s\S]*?<text class="track-ctg-label[^"]*"[^>]*>hifiasm_Ctg9 \(\+\)<\/text>/,
  );
  assert.match(
    html,
    /data-final-path-segment-id="seg-3"[\s\S]*?<text class="track-ctg-label[^"]*"[^>]*>flye_Ctg10 \(-\)<\/text>/,
  );
  assert.match(
    html,
    /data-final-path-segment-id="seg-1"[\s\S]*?<title>hifiasm_Ctg9 \| len=1200 \| start=1 \| end=1200 \| orient=\+<\/title>/,
  );
  assert.match(html, /data-final-path-segment-id="seg-1"[^>]*data-final-path-slot-left="[^"]+"/);
  assert.match(html, /data-final-path-segment-id="seg-1"[^>]*data-final-path-slot-right="[^"]+"/);
  assert.match(html, /data-final-path-segment-id="seg-1"[^>]*data-final-path-slot-mid="[^"]+"/);
  assert.match(html, /data-final-path-segment-id="seg-2"[^>]*data-final-path-slot-mid="[^"]+"/);
});

test("renderFinalPathCard shows log tab and renders compact log metrics when final path has segments", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: createEntry(),
      viewMode: "log",
      trackViewportPx: 800,
      primaryDatasetName: "hifiasm",
      finalPathLogModel: {
        primaryDatasetName: "hifiasm",
        primaryCount: {
          used: 2,
          total: 3,
          appended: 1,
          hidden: 1,
          appendedRows: [
            {
              datasetName: "hifiasm",
              ctgName: "Ctg9",
              originId: "utig4-001122l",
              finalPathStart: 1,
              finalPathEnd: 1200,
              lengthBp: 1200,
            },
          ],
          hiddenRows: [
            {
              datasetName: "hifiasm",
              ctgName: "Ctg12",
              originId: "utig4-001212l",
              lengthBp: 900,
              counted: true,
            },
          ],
        },
        primaryLength: {
          usedBp: 2100,
          totalBp: 5000,
          appendedBp: 1200,
          hiddenBp: 900,
          appendedRows: [
            {
              datasetName: "hifiasm",
              ctgName: "Ctg9",
              originId: "utig4-001122l",
              finalPathStart: 1,
              finalPathEnd: 1200,
              lengthBp: 1200,
            },
          ],
          hiddenRows: [
            {
              datasetName: "hifiasm",
              ctgName: "Ctg12",
              originId: "utig4-001212l",
              lengthBp: 900,
              counted: true,
            },
          ],
        },
        supportRows: [
          {
            datasetName: "flye",
            ctgName: "Ctg10",
            originId: "contig_98",
            finalPathStart: 1301,
            finalPathEnd: 1801,
            lengthBp: 501,
          },
          {
            datasetName: "flye",
            ctgName: "Ctg11",
            originId: "contig_99",
            finalPathStart: 1802,
            finalPathEnd: 2302,
            lengthBp: 501,
          },
        ],
        otherChrPrimaryRows: [
          {
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            originId: "utig4-001122l",
            finalPathStart: 1,
            finalPathEnd: 1200,
            lengthBp: 1200,
            usedByChrNames: ["Chr02"],
          },
        ],
      },
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /data-final-path-view-mode="log"/);
  assert.match(html, /data-final-path-export-action="log"/);
  assert.match(html, />日志<\/button>/);
  assert.doesNotMatch(html, /<details class="final-path-log-metric">/);
  assert.match(html, /final-path-log-stat/);
  assert.match(html, /final-path-log-ratio-segment is-appended/);
  assert.match(html, /final-path-log-ratio-segment is-log-hidden/);
  assert.match(html, /final-path-log-swatch is-log-hidden/);
  assert.match(html, /role="img" aria-label="实际 append: 1\/3; 主图 hidden: 1\/3"/);
  assert.match(html, /title="实际 append: 1,200\/5,000 bp"/);
  assert.match(html, /title="主图 hidden: 900\/5,000 bp"/);
  assert.match(html, /<span class="final-path-log-stat-label">used_主ds_ctg数目<\/span>\s*<span class="final-path-log-ratio-bar"[\s\S]*?<\/span>\s*<strong class="final-path-log-stat-value">2\/3<\/strong>/);
  assert.match(html, /used_主ds_ctg数目/);
  assert.match(html, /2\/3/);
  assert.match(html, /used_主ds_ctg长度/);
  assert.match(html, /2,100\/5,000/);
  assert.match(html, /实际 append/);
  assert.match(html, /主图 hidden/);
  assert.match(html, /<th>Type<\/th>/);
  assert.doesNotMatch(html, /<th>ctg<\/th>/);
  assert.match(html, /<th>used_by_chr<\/th>/);
  assert.match(html, /<td class="final-path-log-type-cell" rowspan="2">辅助 ds_ctg使用情况<\/td>\s*<td>flye<\/td>/);
  assert.doesNotMatch(html, /<td>Ctg10<\/td>/);
  assert.doesNotMatch(html, /<td>Ctg11<\/td>/);
  assert.match(html, /<td>contig_98<\/td>[\s\S]*?<td>Chr01<\/td>/);
  assert.match(html, /<td>contig_99<\/td>[\s\S]*?<td>Chr01<\/td>/);
  assert.match(html, /<td class="final-path-log-type-cell" rowspan="1">重复主ds_ctg使用情况<\/td>\s*<td>hifiasm<\/td>/);
  assert.doesNotMatch(html, /<h5>辅助 ds_ctg使用情况<\/h5>/);
  assert.doesNotMatch(html, /<h5>重复主ds_ctg使用情况<\/h5>/);
  assert.match(html, /flye/);
  assert.match(html, /Chr02/);
});

test("renderFinalPathCard hides empty log detail sections", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: createEntry(),
      viewMode: "log",
      finalPathLogModel: {
        primaryDatasetName: "hifiasm",
        primaryCount: {
          used: 1,
          total: 2,
          appended: 1,
          hidden: 0,
          appendedRows: [],
          hiddenRows: [],
        },
        primaryLength: {
          usedBp: 1200,
          totalBp: 3000,
          appendedBp: 1200,
          hiddenBp: 0,
          appendedRows: [],
          hiddenRows: [],
        },
        supportRows: [],
        otherChrPrimaryRows: [],
      },
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /used_主ds_ctg数目/);
  assert.doesNotMatch(html, /辅助 ds_ctg使用情况/);
  assert.doesNotMatch(html, /重复主ds_ctg使用情况/);
  assert.doesNotMatch(html, /暂无记录/);
});

test("renderFinalPathCard falls back to graph and hides log controls when log mode is requested for an empty path", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: null,
      viewMode: "log",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /data-final-path-view-mode="graph"/);
  assert.doesNotMatch(html, /data-final-path-view-mode="log"/);
  assert.doesNotMatch(html, /data-final-path-export-action="log"/);
});

test("renderFinalPathCard hides log controls when final path contains ref segments", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "ref-1",
            type: "ctg",
            sourceKind: "ref_segment",
            ctgName: "ref_Chr01:1-100",
            start: 1,
            end: 100,
          },
        ],
      },
      viewMode: "log",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /data-final-path-view-mode="graph"/);
  assert.doesNotMatch(html, /data-final-path-view-mode="log"/);
  assert.doesNotMatch(html, />日志<\/button>/);
  assert.doesNotMatch(html, /data-final-path-export-action="log"/);
});

test("renderFinalPathCard strips chr suffix from visible ctg names while keeping hover titles full", () => {
  const finalPathEntry = {
    mode: "segments",
    chrName: "Chr22",
    segments: [
      {
        segmentId: "seg-1",
        type: "ctg",
        assemblyCtgId: 9,
        datasetName: "hifiasm",
        ctgName: "ptg000009l@Chr22",
        originId: "ptg000009l",
        overallLen: 1200,
        start: 1,
        end: 1200,
      },
    ],
    totalLength: 1200,
  };
  const graphHtml = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr22",
      finalPathEntry,
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );
  const tableHtml = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr22",
      finalPathEntry,
      viewMode: "table",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(
    graphHtml,
    /data-final-path-segment-id="seg-1"[\s\S]*?<text class="track-ctg-label[^"]*"[^>]*>hifiasm_ptg000009l \(\+\)<\/text>/,
  );
  assert.match(
    graphHtml,
    /data-final-path-segment-id="seg-1"[\s\S]*?<title>hifiasm_ptg000009l@Chr22 \| len=1200 \| start=1 \| end=1200 \| orient=\+<\/title>/,
  );
  assert.doesNotMatch(graphHtml, />hifiasm_ptg000009l@Chr22 \(\+\)<\/text>/);
  assert.match(
    tableHtml,
    /data-final-path-cell="ctg"[\s\S]*value="hifiasm_ptg000009l"[\s\S]*title="hifiasm_ptg000009l@Chr22"/,
  );
});

test("renderFinalPathCard graph mode can render a supplied preview segment order", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: createEntry(),
      viewMode: "graph",
      trackViewportPx: 800,
      graphPreviewSegmentOrder: ["seg-3", "seg-2", "seg-1"],
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.ok(html.indexOf('data-final-path-segment-id="seg-3"') < html.indexOf('data-final-path-segment-id="seg-2"'));
  assert.ok(html.indexOf('data-final-path-segment-id="seg-2"') < html.indexOf('data-final-path-segment-id="seg-1"'));
});

test("renderFinalPathCard table mode renders a readonly Origin ID column after Ctg", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: createEntry(),
      viewMode: "table",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /data-final-path-view-mode="table"/);
  assert.match(
    html,
    /<div>Ctg<\/div>\s*<div>Origin ID<\/div>\s*<div>overall_len<\/div>\s*<div>orient<\/div>\s*<div>Ctg_start<\/div>\s*<div>Ctg_end<\/div>\s*<div>Chr_start<\/div>\s*<div>Chr_end<\/div>/,
  );
  assert.match(
    html,
    /data-final-path-cell="ctg"[\s\S]*value="hifiasm_Ctg9"[\s\S]*data-final-path-cell="origin-id"[\s\S]*value="utig4-001122l"[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-segment-id="seg-2"[\s\S]*data-final-path-cell="origin-id"[\s\S]*value=""[\s\S]*disabled/,
  );
});

test("renderFinalPathCard graph mode keeps a tiny gap marker from overlapping the following ctg start", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 1914,
            datasetName: "canu2",
            ctgName: "Ctg1914",
            overallLen: 43725274,
            start: 1,
            end: 43725274,
          },
          {
            segmentId: "seg-gap",
            type: "gap",
            gapSizeBp: 100,
          },
          {
            segmentId: "seg-2",
            type: "ctg",
            assemblyCtgId: 2,
            datasetName: "hifiasm",
            ctgName: "Ctg2",
            overallLen: 43726252,
            start: 1,
            end: 43726252,
          },
        ],
        totalLength: 87451626,
      },
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  const gapMatch = html.match(
    /data-final-path-segment-id="seg-gap"[\s\S]*?<rect[\s\S]*?class="final-path-gap-marker"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/,
  );
  const nextCtgMatch = html.match(
    /data-final-path-segment-id="seg-2"[\s\S]*?<rect[\s\S]*?class="track-ctg is-active"[\s\S]*?x="([^"]+)"/,
  );

  assert.ok(gapMatch);
  assert.ok(nextCtgMatch);

  const gapRight = Number(gapMatch[1]) + Number(gapMatch[2]);
  const nextCtgX = Number(nextCtgMatch[1]);
  assert.ok(nextCtgX >= gapRight, `expected next ctg x ${nextCtgX} to be >= gap right ${gapRight}`);
});

test("renderFinalPathCard graph mode shrinks all ctg bars proportionally when a tiny GAP becomes visible", () => {
  const renderWidths = (segments, totalLength) => {
    const html = renderFinalPathCard(
      {
        projectName: "projA",
        chrName: "Chr01",
        finalPathEntry: {
          mode: "segments",
          chrName: "Chr01",
          segments,
          totalLength,
        },
        viewMode: "graph",
        trackViewportPx: 800,
      },
      {
        ...createDeps(),
        i18n: createI18n(),
      },
    );
    return {
      first: Number(html.match(/data-final-path-segment-id="seg-1"[\s\S]*?<rect[^>]*class="track-ctg is-active"[^>]*width="([^"]+)"/)?.[1]),
      second: Number(html.match(/data-final-path-segment-id="seg-2"[\s\S]*?<rect[^>]*class="track-ctg is-active"[^>]*width="([^"]+)"/)?.[1]),
      third: Number(html.match(/data-final-path-segment-id="seg-3"[\s\S]*?<rect[^>]*class="track-ctg is-active"[^>]*width="([^"]+)"/)?.[1]),
      gap: Number(html.match(/data-final-path-segment-id="seg-gap"[\s\S]*?<rect[^>]*class="final-path-gap-marker"[^>]*width="([^"]+)"/)?.[1] || 0),
    };
  };

  const withoutGap = renderWidths(
    [
      {
        segmentId: "seg-1",
        type: "ctg",
        assemblyCtgId: 1,
        datasetName: "hifiasm",
        ctgName: "Ctg1",
        overallLen: 10_000_000,
        start: 1,
        end: 10_000_000,
      },
      {
        segmentId: "seg-2",
        type: "ctg",
        assemblyCtgId: 2,
        datasetName: "hifiasm",
        ctgName: "Ctg2",
        overallLen: 10_000_000,
        start: 1,
        end: 10_000_000,
      },
      {
        segmentId: "seg-3",
        type: "ctg",
        assemblyCtgId: 3,
        datasetName: "hifiasm",
        ctgName: "Ctg3",
        overallLen: 10_000_000,
        start: 1,
        end: 10_000_000,
      },
    ],
    30_000_000,
  );

  const withGap = renderWidths(
    [
      {
        segmentId: "seg-1",
        type: "ctg",
        assemblyCtgId: 1,
        datasetName: "hifiasm",
        ctgName: "Ctg1",
        overallLen: 10_000_000,
        start: 1,
        end: 10_000_000,
      },
      {
        segmentId: "seg-gap",
        type: "gap",
        gapSizeBp: 100,
      },
      {
        segmentId: "seg-2",
        type: "ctg",
        assemblyCtgId: 2,
        datasetName: "hifiasm",
        ctgName: "Ctg2",
        overallLen: 10_000_000,
        start: 1,
        end: 10_000_000,
      },
      {
        segmentId: "seg-3",
        type: "ctg",
        assemblyCtgId: 3,
        datasetName: "hifiasm",
        ctgName: "Ctg3",
        overallLen: 10_000_000,
        start: 1,
        end: 10_000_000,
      },
    ],
    30_000_100,
  );

  assert.ok(withGap.gap >= 8, `expected visible GAP width >= 8, got ${withGap.gap}`);
  assert.ok(withGap.first < withoutGap.first - 1, `expected first ctg to shrink globally: ${withGap.first} vs ${withoutGap.first}`);
  assert.ok(withGap.second < withoutGap.second - 1, `expected second ctg to shrink globally: ${withGap.second} vs ${withoutGap.second}`);
  assert.ok(withGap.third < withoutGap.third - 1, `expected third ctg to shrink globally: ${withGap.third} vs ${withoutGap.third}`);
  assert.ok(
    Math.abs((withoutGap.first - withGap.first) - (withoutGap.third - withGap.third)) < 0.2,
    `expected non-adjacent ctg shrink to match global scaling, got first delta ${withoutGap.first - withGap.first} and third delta ${withoutGap.third - withGap.third}`,
  );
});

test("renderFinalPathCard graph mode hides overflowing ctg labels and keeps tooltip titles", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 2,
            datasetName: "hifiasm",
            ctgName: "LongLongLongLongLongLongLongLongLongLongCtg2",
            overallLen: 100,
            start: 1,
            end: 100,
          },
          {
            segmentId: "seg-2",
            type: "ctg",
            assemblyCtgId: 3,
            datasetName: "hifiasm",
            ctgName: "Ctg3",
            overallLen: 10_000_000,
            start: 1,
            end: 10_000_000,
          },
        ],
      },
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  const segmentHtml = extractFinalPathSegmentHtml(html, "seg-1");
  assert.match(
    segmentHtml,
    /<title>hifiasm_LongLongLongLongLongLongLongLongLongLongCtg2 \| len=100 \| start=1 \| end=100 \| orient=\+<\/title>/,
  );
  assert.doesNotMatch(
    segmentHtml,
    /<text class="track-ctg-label/,
    "expected the overflowing label to be hidden and rely on the title tooltip",
  );

  assert.match(
    html,
    /class="assembly-track-svg assembly-final-path-svg"[\s\S]*height="154"[\s\S]*viewBox="0 0 [^"]+ 154"/,
  );
});

test("renderFinalPathCard graph mode hides adjacent overflowing ctg labels", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 1914,
            datasetName: "canu2",
            ctgName: "Ctg1914",
            overallLen: 36_000_000,
            start: 1,
            end: 36_000_000,
          },
          {
            segmentId: "seg-2",
            type: "ctg",
            assemblyCtgId: 1948,
            datasetName: "hifiasm",
            ctgName: "VeryLongVeryLongVeryLongVeryLongCtg1948",
            overallLen: 150_000,
            start: 1,
            end: 150_000,
          },
          {
            segmentId: "seg-3",
            type: "ctg",
            assemblyCtgId: 1949,
            datasetName: "hifiasm",
            ctgName: "VeryLongVeryLongVeryLongVeryLongCtg1949",
            overallLen: 150_000,
            start: 1,
            end: 150_000,
          },
        ],
        totalLength: 36_300_000,
      },
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  const firstSegmentHtml = extractFinalPathSegmentHtml(html, "seg-2");
  const secondSegmentHtml = extractFinalPathSegmentHtml(html, "seg-3");
  assert.match(
    firstSegmentHtml,
    /<title>hifiasm_VeryLongVeryLongVeryLongVeryLongCtg1948 \| len=150000 \| start=1 \| end=150000 \| orient=\+<\/title>/,
  );
  assert.match(
    secondSegmentHtml,
    /<title>hifiasm_VeryLongVeryLongVeryLongVeryLongCtg1949 \| len=150000 \| start=1 \| end=150000 \| orient=\+<\/title>/,
  );
  assert.doesNotMatch(firstSegmentHtml, /<text class="track-ctg-label/);
  assert.doesNotMatch(secondSegmentHtml, /<text class="track-ctg-label/);
  assert.doesNotMatch(html, /is-outside is-tilt-(?:up|down)/);
});

test("renderFinalPathCard max-scale graph keeps svg width equal to the viewport even with a right-edge overflow label", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 10,
            datasetName: "hifiasm",
            ctgName: "Ctg10",
            overallLen: 30_000,
            start: 1,
            end: 30_000,
          },
          {
            segmentId: "seg-2",
            type: "ctg",
            assemblyCtgId: 11,
            datasetName: "hifiasm",
            ctgName: "right-edge-overflow-label-very-very-long-contig-name",
            overallLen: 120,
            start: 1,
            end: 120,
          },
        ],
        totalLength: 30_120,
      },
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  const svgWidthMatch = html.match(/class="assembly-track-svg assembly-final-path-svg"[\s\S]*?width="([^"]+)"/);
  assert.ok(svgWidthMatch, "expected final path svg width");
  const svgWidth = Number(svgWidthMatch[1]);

  assert.equal(
    svgWidth,
    800,
    `expected max-scale final path svg width ${svgWidth} to match the viewport width 800`,
  );
});

test("renderFinalPathCard graph mode clamps edge gap markers inside the viewport", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-gap-left",
            type: "gap",
            gapSizeBp: 100,
          },
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 1914,
            datasetName: "canu2",
            ctgName: "Ctg1914",
            overallLen: 43725274,
            start: 1,
            end: 43725274,
          },
          {
            segmentId: "seg-gap-right",
            type: "gap",
            gapSizeBp: 100,
          },
        ],
        totalLength: 43725374,
      },
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  const leftGapMatch = html.match(
    /data-final-path-segment-id="seg-gap-left"[\s\S]*?<rect[\s\S]*?class="final-path-gap-marker"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/,
  );
  const rightGapMatch = html.match(
    /data-final-path-segment-id="seg-gap-right"[\s\S]*?<rect[\s\S]*?class="final-path-gap-marker"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/,
  );
  const leftGapBlockMatch = html.match(
    /<g[\s\S]*?data-final-path-segment-id="seg-gap-left"[\s\S]*?class="final-path-gap-segment"[\s\S]*?<\/g>/,
  );
  const rightGapBlockMatch = html.match(
    /<g[\s\S]*?data-final-path-segment-id="seg-gap-right"[\s\S]*?class="final-path-gap-segment"[\s\S]*?<\/g>/,
  );

  assert.ok(leftGapMatch);
  assert.ok(rightGapMatch);
  assert.ok(leftGapBlockMatch);
  assert.ok(rightGapBlockMatch);

  const leftGapX = Number(leftGapMatch[1]);
  const rightGapX = Number(rightGapMatch[1]);
  const rightGapWidth = Number(rightGapMatch[2]);
  const innerWidth = 800;

  assert.ok(leftGapX >= 0, `expected left gap x ${leftGapX} to stay within the viewport`);
  assert.ok(
    rightGapX + rightGapWidth <= innerWidth,
    `expected right gap right edge ${rightGapX + rightGapWidth} to stay within viewport width ${innerWidth}`,
  );
  assert.doesNotMatch(leftGapBlockMatch[0], /final-path-gap-label/);
  assert.match(rightGapBlockMatch[0], /<text class="final-path-gap-label" x="([^"]+)"[\s\S]*?text-anchor="end">GAP<\/text>/);
});

test("renderFinalPathCard graph mode lays adjacent gap markers sequentially without overlap", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 1914,
            datasetName: "canu2",
            ctgName: "Ctg1914",
            overallLen: 14814047,
            start: 1,
            end: 14814047,
          },
          {
            segmentId: "seg-gap-1",
            type: "gap",
            gapSizeBp: 100,
          },
          {
            segmentId: "seg-gap-2",
            type: "gap",
            gapSizeBp: 100,
          },
        ],
        totalLength: 14814247,
      },
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  const firstGapMatch = html.match(
    /data-final-path-segment-id="seg-gap-1"[\s\S]*?<rect[\s\S]*?class="final-path-gap-marker"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/,
  );
  const secondGapMatch = html.match(
    /data-final-path-segment-id="seg-gap-2"[\s\S]*?<rect[\s\S]*?class="final-path-gap-marker"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/,
  );

  assert.ok(firstGapMatch);
  assert.ok(secondGapMatch);

  const firstGapX = Number(firstGapMatch[1]);
  const firstGapWidth = Number(firstGapMatch[2]);
  const secondGapX = Number(secondGapMatch[1]);

  assert.ok(
    Math.abs(secondGapX - (firstGapX + firstGapWidth)) < 0.01,
    `expected adjacent gaps to be packed sequentially, got first gap right ${firstGapX + firstGapWidth} and second gap x ${secondGapX}`,
  );
});

test("renderFinalPathCard graph mode renders one left-anchored GAP label for an adjacent gap run", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 1,
            datasetName: "hifiasm",
            ctgName: "Ctg1",
            overallLen: 1000,
            start: 1,
            end: 1000,
          },
          {
            segmentId: "seg-gap-1",
            type: "gap",
            gapSizeBp: 100,
          },
          {
            segmentId: "seg-gap-2",
            type: "gap",
            gapSizeBp: 100,
          },
          {
            segmentId: "seg-2",
            type: "ctg",
            assemblyCtgId: 2,
            datasetName: "flye",
            ctgName: "Ctg2",
            overallLen: 1000,
            start: 1,
            end: 1000,
          },
        ],
        totalLength: 2200,
      },
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  const gapLabelMatches = Array.from(html.matchAll(/<text class="final-path-gap-label" x="([^"]+)"[\s\S]*?text-anchor="([^"]+)"[\s\S]*?>GAP<\/text>/g));
  const firstGapMatch = html.match(
    /data-final-path-segment-id="seg-gap-1"[\s\S]*?<rect[\s\S]*?class="final-path-gap-marker"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/,
  );
  const secondGapMatch = html.match(
    /data-final-path-segment-id="seg-gap-2"[\s\S]*?<rect[\s\S]*?class="final-path-gap-marker"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/,
  );

  assert.equal(gapLabelMatches.length, 1, "expected one GAP label for an adjacent gap run");
  assert.ok(firstGapMatch);
  assert.ok(secondGapMatch);

  const firstGapX = Number(firstGapMatch[1]);
  const labelAnchor = gapLabelMatches[0][2];
  const labelX = Number(gapLabelMatches[0][1]);

  assert.equal(labelAnchor, "start");
  assert.ok(
    Math.abs(labelX - firstGapX) < 0.01,
    `expected GAP label x ${labelX} to match adjacent gap run left edge ${firstGapX}`,
  );
});

test("renderFinalPathCard graph mode keeps a GAP label when the adjacent ctg label is hidden", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr05",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr05",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 2,
            datasetName: "hifiasm",
            ctgName: "Ctg2",
            overallLen: 30_000_000,
            start: 1,
            end: 30_000_000,
          },
          {
            segmentId: "seg-gap",
            type: "gap",
            gapSizeBp: 100,
          },
          {
            segmentId: "seg-2",
            type: "ctg",
            assemblyCtgId: 3,
            datasetName: "hifiasm",
            ctgName: "Ctg3",
            overallLen: 405_280,
            start: 1,
            end: 405_280,
          },
        ],
        totalLength: 30_405_380,
      },
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  const gapSegmentHtml = extractFinalPathSegmentHtml(html, "seg-gap");
  const ctgSegmentHtml = extractFinalPathSegmentHtml(html, "seg-2");
  assert.match(gapSegmentHtml, /class="final-path-gap-marker"/);
  assert.match(gapSegmentHtml, /<text class="final-path-gap-label"[\s\S]*?>GAP<\/text>/);
  assert.match(
    ctgSegmentHtml,
    /<title>hifiasm_Ctg3 \| len=405280 \| start=1 \| end=405280 \| orient=\+<\/title>/,
  );
  assert.doesNotMatch(ctgSegmentHtml, /<text class="track-ctg-label/);
});

test("renderFinalPathCard graph mode applies companion color class for non-primary dataset segments", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      primaryDatasetName: "hifiasm",
      finalPathEntry: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "hifiasm",
            ctgName: "Ctg9",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
          {
            segmentId: "seg-2",
            type: "ctg",
            assemblyCtgId: 30,
            datasetName: "flye",
            ctgName: "Ctg30",
            overallLen: 600,
            start: 1,
            end: 600,
          },
        ],
        totalLength: 1800,
      },
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );
  assert.match(html, /data-final-path-segment-id="seg-1"[\s\S]*class="track-ctg is-active"/);
  assert.match(html, /data-final-path-segment-id="seg-2"[\s\S]*class="track-ctg is-active is-companion"/);
});

test("renderFinalPathCard graph mode keeps ref segments on the ref gray palette", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: createRefEntry(),
      viewMode: "graph",
      trackViewportPx: 800,
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );

  assert.match(html, /data-final-path-segment-id="seg-ref"[\s\S]*class="track-ctg is-active is-ref"/);
  assert.match(
    html,
    /data-final-path-segment-id="seg-ref"[\s\S]*?<text class="track-ctg-label is-ref[^"]*"[^>]*>ref_Chr01:5201-5600 \(\+\)<\/text>/,
  );
  assert.match(html, /data-final-path-segment-id="seg-ds"[\s\S]*class="track-ctg is-active"/);
});

test("renderFinalPathCard table mode renders editable card rows and actions", () => {
  const html = renderFinalPathCard(
    {
      projectName: "projA",
      chrName: "Chr01",
      finalPathEntry: createEntry(),
      viewMode: "table",
    },
    {
      ...createDeps(),
      i18n: createI18n(),
    },
  );
  assert.match(html, /class="final-path-card-table-body"/);
  assert.match(html, /class="final-path-card-list-head"/);
  assert.match(html, /class="final-path-card-list-head"[\s\S]*?>orient</);
  assert.match(html, /class="final-path-card-list-head"[\s\S]*?>Ctg_start</);
  assert.match(html, /class="final-path-card-list-head"[\s\S]*?>Ctg_end</);
  assert.match(html, /class="final-path-card-list-head"[\s\S]*?>Chr_start</);
  assert.match(html, /class="final-path-card-list-head"[\s\S]*?>Chr_end</);
  assert.match(html, /data-final-path-card-list/);
  assert.match(html, /data-final-path-row-id="seg-1"/);
  assert.match(html, /data-final-path-row-id="seg-2"/);
  assert.match(html, /data-final-path-row-id="seg-3"/);
  assert.match(html, /class="final-path-sort-row(?:[^"]*)"/);
  assert.match(html, /data-final-path-card-body="seg-1"/);
  assert.match(html, /data-final-path-row-drag-id="seg-1"/);
  assert.match(
    html,
    /data-final-path-row-id="seg-1"[\s\S]*data-final-path-card-body="seg-1"[\s\S]*data-final-path-row-drag-id="seg-1"[\s\S]*data-final-path-cell="ctg"/,
  );
  assert.match(html, /data-final-path-cell="ctg"/);
  assert.match(html, /data-final-path-cell="overall-len"/);
  assert.match(html, /data-final-path-cell="orient"/);
  assert.match(html, /data-final-path-cell="start"/);
  assert.match(html, /data-final-path-cell="end"/);
  assert.match(html, /data-final-path-derived-cell="chr-start"/);
  assert.match(html, /data-final-path-derived-cell="chr-end"/);
  assert.match(html, /value="hifiasm_Ctg9"/);
  assert.match(html, /value="Gap"/);
  assert.match(
    html,
    /data-final-path-row-id="seg-1"[\s\S]*data-final-path-cell="overall-len"[\s\S]*value="1200"[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-1"[\s\S]*<select[^>]*data-final-path-cell="orient"[^>]*>[\s\S]*<option value="\+" selected>\+<\/option>[\s\S]*<option value="-"[^>]*>-<\/option>[\s\S]*<\/select>/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-3"[\s\S]*<select[^>]*data-final-path-cell="orient"[^>]*>[\s\S]*<option value="\+"[^>]*>\+<\/option>[\s\S]*<option value="-" selected>-<\/option>[\s\S]*<\/select>/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-2"[\s\S]*data-final-path-cell="overall-len"[\s\S]*value=""[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-2"[\s\S]*<select[^>]*data-final-path-cell="orient"[^>]*disabled[^>]*>[\s\S]*<option value="" selected><\/option>[\s\S]*<\/select>/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-2"[\s\S]*data-final-path-cell="start"[\s\S]*value="1"[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-2"[\s\S]*data-final-path-cell="end"[\s\S]*value="100"[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-1"[\s\S]*data-final-path-derived-cell="chr-start"[\s\S]*value="1"[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-1"[\s\S]*data-final-path-derived-cell="chr-end"[\s\S]*value="1200"[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-2"[\s\S]*data-final-path-derived-cell="chr-start"[\s\S]*value="1201"[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-2"[\s\S]*data-final-path-derived-cell="chr-end"[\s\S]*value="1300"[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-3"[\s\S]*data-final-path-derived-cell="chr-start"[\s\S]*value="1301"[\s\S]*disabled/,
  );
  assert.match(
    html,
    /data-final-path-row-id="seg-3"[\s\S]*data-final-path-derived-cell="chr-end"[\s\S]*value="1801"[\s\S]*disabled/,
  );
  assert.match(html, /data-final-path-remove-row="seg-1"/);
  assert.match(html, /data-final-path-add-row/);
  assert.match(
    html,
    /data-final-path-card-body="seg-1"[\s\S]*data-final-path-row-drag-id="seg-1"[\s\S]*data-final-path-cell="ctg"[\s\S]*value="hifiasm_Ctg9"/,
  );
  assert.match(
    html,
    /data-final-path-card-body="seg-1"[\s\S]*data-final-path-cell="end"[\s\S]*data-final-path-remove-row="seg-1"/,
  );
  assert.doesNotMatch(html, />删</);
  assert.doesNotMatch(html, /<table\b/i);
  assert.doesNotMatch(html, /placeholder="-"/);
});
