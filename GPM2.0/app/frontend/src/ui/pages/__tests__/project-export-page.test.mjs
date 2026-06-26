import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { FLOATING_MENU_CLOSE_DELAY_MS } from "../floating-menu-runtime.js";
import { __test, bindProjectExportPage, renderProjectExportPage } from "../project-export-page.js";

const componentsCss = readFileSync(new URL("../../../styles/components.css", import.meta.url), "utf8");

function createState(overrides = {}) {
  return {
    locale: "zh",
    session: {
      workspacePath: "/tmp/ws",
      projectId: 7,
      projectName: "p1",
    },
    initializer: {
      datasets: [{ datasetId: 1, name: "hifiasm", fastaAvailable: true }],
      existingProjects: [
        {
          projectId: 7,
          projectName: "p1",
          primaryDatasetId: 1,
          supportDatasetIds: [],
        },
      ],
    },
    assembly: {
      finalPathTrackView: {},
    },
    projectExport: {
      loading: false,
      projectId: 7,
      chromosomes: [{ chrName: "Chr01" }],
      unplacedCtgCount: 0,
      unplacedBp: 0,
      primaryCtgsByChr: {
        Chr01: [
          {
            assemblyCtgId: 1,
            name: "ptg1",
            datasetName: "hifiasm",
            originId: "ptg1",
            totalLength: 1000,
          },
        ],
      },
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 1,
              datasetName: "hifiasm",
              ctgName: "ptg1",
              overallLen: 1000,
              start: 1,
              end: 1000,
            },
          ],
        },
      },
      job: null,
    },
    ...overrides,
  };
}

test("project export page renders assignment bars before placed statistics with a final-path style export menu", () => {
  const html = renderProjectExportPage(createState());

  assert.match(html, />项目导出</);
  assert.match(html, /<div class="project-export-title-row">[\s\S]*<h3>项目导出<\/h3>[\s\S]*项目: p1 · 主 ds: hifiasm/);
  assert.doesNotMatch(html, /card project-export-card/);
  assert.doesNotMatch(html, /data-project-export-refresh/);
  assert.match(html, /class="button ghost tiny final-path-export-toggle"[\s\S]*data-project-export-toggle="true"[\s\S]*>Export<\/button>/);
  assert.match(html, /class="final-path-export-menu is-hidden" data-project-export-menu/);
  assert.match(html, /data-project-export-action="png"/);
  assert.match(html, /data-project-export-action="tsv"/);
  assert.match(html, /data-project-export-action="log"/);
  assert.match(html, /data-project-export-action="fasta"/);
  assert.match(html, /data-project-export-action="all"/);
  assert.match(html, />图\(.png\)<\/button>/);
  assert.match(html, />表\(.tsv\)<\/button>/);
  assert.match(html, />日志\(.log\)<\/button>/);
  assert.match(html, />序列\(.fasta\)<\/button>/);
  assert.match(html, />All<\/button>/);
  assert.doesNotMatch(html, /导出图|导出表|导出日志|导出序列|一键导出/);
  assert.doesNotMatch(html, /final path chr/i);
  assert.doesNotMatch(html, /project-export-summary-line/);
  assert.ok(html.indexOf(">主 ds 分配统计<") < html.indexOf(">placed统计<"));
  assert.match(html, />placed统计</);
  assert.match(html, /used_主ds_ctg数目/);
  assert.match(html, /final-path-log-ratio-segment is-appended/);
  assert.match(html, /1\/1/);
  assert.match(html, /主 ds 分配统计/);
  assert.match(html, />数目</);
  assert.match(html, />长度</);
  assert.equal((html.match(/class="project-export-assignment-bar"/g) || []).length, 2);
  assert.match(html, /project-export-assignment-segment is-placed/);
  assert.match(html, /project-export-assignment-segment is-unassigned/);
  assert.match(html, />placed</);
  assert.match(html, /unplaced/);
  assert.doesNotMatch(html, /project-export-assignment-value-part is-/);
  assert.match(html, /实际 append/);
  assert.match(html, /主图 hidden/);
  assert.match(html, /<div class="project-export-used-metrics">[\s\S]*class="project-export-used-row"[\s\S]*class="project-export-used-row"/);
  assert.match(html, /class="project-export-final-path-list"/);
  assert.match(html, /class="project-export-final-path-row"[\s\S]*data-project-export-jump-chr="Chr01"/);
  assert.match(html, /class="project-export-final-path-row-label">Chr01<\/strong>/);
  assert.match(html, /class="project-export-final-path-preview-track"/);
  assert.match(html, /class="project-export-final-path-preview-ctg"[\s\S]*?width: 100\.0000%;/);
  assert.match(html, /class="project-export-final-path-preview-length">1,000 bp<\/span>/);
  assert.doesNotMatch(html, /track-ruler-line/);
  assert.doesNotMatch(html, /final-path-card-toggle/);
});

test("project export menu closes after leaving the export root", () => {
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  const timers = new Map();
  let nextTimerId = 1;
  globalThis.setTimeout = (callback, delayMs) => {
    assert.equal(delayMs, FLOATING_MENU_CLOSE_DELAY_MS);
    const timerId = nextTimerId;
    nextTimerId += 1;
    timers.set(timerId, callback);
    return timerId;
  };
  globalThis.clearTimeout = (timerId) => {
    timers.delete(timerId);
  };
  try {
    const menuNode = {
      hidden: false,
      classList: {
        contains(name) {
          return name === "is-hidden" ? menuNode.hidden : false;
        },
        toggle(name, force) {
          if (name === "is-hidden") {
            menuNode.hidden = Boolean(force);
          }
        },
      },
    };
    const toggleNode = {
      setAttribute(name, value) {
        this[name] = value;
      },
    };
    const exportRoot = {
      contains(node) {
        return node === menuNode || node === toggleNode;
      },
      querySelector(selector) {
        if (selector === "[data-project-export-menu]") {
          return menuNode;
        }
        if (selector === "[data-project-export-toggle]") {
          return toggleNode;
        }
        return null;
      },
    };
    const exportTarget = {
      closest(selector) {
        if (selector === "[data-project-export]") {
          return exportRoot;
        }
        return null;
      },
    };
    const listeners = new Map();
    const host = {
      addEventListener(type, handler) {
        listeners.set(type, [...(listeners.get(type) || []), handler]);
      },
      querySelectorAll() {
        return [];
      },
    };
    let state = createState();
    const store = {
      getState() {
        return state;
      },
      setState(nextState) {
        state = nextState;
      },
    };

    bindProjectExportPage(host, store);

    listeners.get("pointerout").forEach((handler) => handler({
      target: exportTarget,
      relatedTarget: null,
    }));
    assert.equal(menuNode.hidden, false);
    assert.equal(timers.size, 1);
    const [[closeTimerId, closeTimer]] = timers.entries();
    timers.delete(closeTimerId);
    closeTimer();
    assert.equal(menuNode.hidden, true);
    assert.equal(toggleNode["aria-expanded"], "false");

    menuNode.hidden = false;
    listeners.get("pointerout").forEach((handler) => handler({
      target: exportTarget,
      relatedTarget: null,
    }));
    assert.equal(timers.size, 1);
    listeners.get("pointerover").forEach((handler) => handler({
      target: exportTarget,
    }));
    assert.equal(timers.size, 0);
    assert.equal(menuNode.hidden, false);
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});

test("project export page ignores cached export data from a different current project", () => {
  const baseState = createState();
  const html = renderProjectExportPage(createState({
    session: {
      workspacePath: "/tmp/ws",
      projectId: 8,
      projectName: "p1",
    },
    initializer: {
      ...baseState.initializer,
      existingProjects: [
        {
          projectId: 8,
          projectName: "p1",
          primaryDatasetId: 1,
          supportDatasetIds: [],
        },
      ],
    },
    projectExport: {
      ...baseState.projectExport,
      projectId: 7,
      finalPathByChr: {
        ChrOld: {
          chrName: "ChrOld",
          segments: [
            {
              segmentId: "old-seg",
              type: "ctg",
              assemblyCtgId: 99,
              datasetName: "hifiasm",
              ctgName: "old_project_ctg",
              overallLen: 500,
              start: 1,
              end: 500,
            },
          ],
        },
      },
    },
    assembly: {
      finalPathTrackView: {},
      finalPathByChr: {},
    },
  }));

  assert.doesNotMatch(html, /ChrOld/);
  assert.doesNotMatch(html, /old_project_ctg/);
});

test("loadProjectExportData clears previous project results before loading current project", async () => {
  const baseState = createState();
  let state = createState({
    session: {
      workspacePath: "/tmp/ws",
      projectId: 8,
      projectName: "p1",
    },
    initializer: {
      ...baseState.initializer,
      existingProjects: [
        {
          projectId: 8,
          projectName: "p1",
          primaryDatasetId: 1,
          supportDatasetIds: [],
        },
      ],
    },
    projectExport: {
      ...baseState.projectExport,
      projectId: 7,
      finalPathByChr: {
        ChrOld: {
          chrName: "ChrOld",
          segments: [{ segmentId: "old-seg", type: "gap", gapSizeBp: 100 }],
        },
      },
      chromosomes: [{ chrName: "ChrOld" }],
      primaryCtgsByChr: {
        ChrOld: [{ assemblyCtgId: 99, name: "old_project_ctg", totalLength: 500 }],
      },
    },
    assembly: {
      finalPathTrackView: {},
      finalPathByChr: {},
    },
  });
  let resolveChromosomes;
  const chromosomePromise = new Promise((resolve) => {
    resolveChromosomes = resolve;
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const host = {
    innerHTML: "",
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };

  const loading = __test.loadProjectExportData(host, store, {
    listProjectChromosomes: async () => chromosomePromise,
    listChrViewCtgs: async () => ({ items: [] }),
    getProjectAssemblyViewState: async () => ({
      finalPathByChr: {},
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: {},
    }),
  });

  assert.equal(state.projectExport.loading, true);
  assert.equal(state.projectExport.projectId, 8);
  assert.equal(state.projectExport.workspacePath, "/tmp/ws");
  assert.deepEqual(state.projectExport.finalPathByChr, {});
  assert.deepEqual(state.projectExport.chromosomes, []);
  assert.deepEqual(state.projectExport.primaryCtgsByChr, {});

  resolveChromosomes({ items: [], unplacedCtgCount: 0, unplacedBp: 0 });
  assert.equal(await loading, true);
});

test("loadProjectExportData ignores late responses after switching projects", async () => {
  let state = createState({
    session: {
      workspacePath: "/tmp/ws",
      projectId: 7,
      projectName: "p-old",
    },
    initializer: {
      ...createState().initializer,
      existingProjects: [
        {
          projectId: 7,
          projectName: "p-old",
          primaryDatasetId: 1,
          supportDatasetIds: [],
        },
        {
          projectId: 8,
          projectName: "p-new",
          primaryDatasetId: 1,
          supportDatasetIds: [],
        },
      ],
    },
    projectExport: {},
  });
  let resolveChromosomes;
  const chromosomePromise = new Promise((resolve) => {
    resolveChromosomes = resolve;
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const host = {
    innerHTML: "",
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };

  const loading = __test.loadProjectExportData(host, store, {
    listProjectChromosomes: async () => chromosomePromise,
    listChrViewCtgs: async () => ({
      items: [{ assemblyCtgId: 1, name: "old_project_ctg", totalLength: 100 }],
    }),
    getProjectAssemblyViewState: async () => ({
      finalPathByChr: {
        ChrOld: {
          chrName: "ChrOld",
          segments: [{ segmentId: "old-seg", type: "gap", gapSizeBp: 100 }],
        },
      },
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: {},
    }),
  });
  state = {
    ...state,
    session: {
      ...state.session,
      projectId: 8,
      projectName: "p-new",
    },
    projectExport: {
      loading: false,
      loaded: false,
      error: "",
      projectId: null,
      finalPathByChr: {},
      chromosomes: [],
      primaryCtgsByChr: {},
    },
  };

  resolveChromosomes({ items: [{ chrName: "ChrOld" }], unplacedCtgCount: 0, unplacedBp: 0 });

  assert.equal(await loading, false);
  assert.equal(state.session.projectId, 8);
  assert.deepEqual(state.projectExport.finalPathByChr, {});
  assert.deepEqual(state.projectExport.chromosomes, []);
  assert.deepEqual(state.projectExport.primaryCtgsByChr, {});
});

test("project export page renders export progress as a final-path style modal", () => {
  const html = renderProjectExportPage(createState({
    projectExport: {
      ...createState().projectExport,
      job: {
        open: true,
        kind: "all",
        projectName: "p1",
        status: "running",
        currentStep: "图(.png)",
        completedOutputs: [],
        error: "",
        steps: [
          { kind: "png", label: "图(.png)", outputPath: "/exports/p1_project_path_20260430205930.png" },
          { kind: "tsv", label: "表(.tsv)", outputPath: "/exports/p1_project_path_20260430205930.tsv" },
          { kind: "fasta", label: "序列(.fasta)", outputPath: "/exports/p1_project_path_20260430205930.fasta" },
        ],
      },
    },
  }));

  assert.match(html, /data-project-export-modal="true"/);
  assert.match(html, /data-project-export-overlay="true"/);
  assert.match(html, /正在导出 final path/);
  assert.match(html, /p1 · All/);
  assert.match(html, /data-project-export-step-status="running"/);
  assert.match(html, /class="pipeline-spinner"/);
  assert.match(html, /data-project-export-close="true"/);
  assert.doesNotMatch(html, /project-export-job/);
});

test("project export page hides log action and stats when any final path contains ref", () => {
  const state = createState({
    projectExport: {
      ...createState().projectExport,
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              sourceKind: "ref_segment",
              referenceChrName: "Chr01",
              memberStartBp: 1,
              memberEndBp: 1000,
              originId: "Chr01",
              overallLen: 1000,
              start: 1,
              end: 1000,
            },
          ],
        },
      },
    },
  });
  const html = renderProjectExportPage(state);

  assert.match(html, /data-project-export-action="png"/);
  assert.match(html, /data-project-export-action="tsv"/);
  assert.match(html, /data-project-export-action="fasta"/);
  assert.match(html, /data-project-export-action="all"/);
  assert.doesNotMatch(html, /data-project-export-action="log"/);
  assert.match(html, /<div class="project-export-summary-line"><span>ref: <strong>Chr01<\/strong><\/span><\/div>/);
  assert.match(html, /项目统计和 log 导出已关闭/);
  assert.doesNotMatch(html, /used_主ds_ctg数目/);
});

test("project export assignment values show placed over total instead of placed over unplaced", () => {
  const baseState = createState();
  const html = renderProjectExportPage(createState({
    projectExport: {
      ...baseState.projectExport,
      unplacedCtgCount: 3,
      unplacedBp: 250,
    },
  }));

  assert.match(
    html,
    /<div class="project-export-assignment-row">[\s\S]*?>数目<[\s\S]*title="placed: 1">1<\/span>[\s\S]*title="placed \+ unplaced: 4">4<\/span>/,
  );
  assert.match(
    html,
    /<div class="project-export-assignment-row">[\s\S]*?>长度<[\s\S]*title="placed: 1,000 bp">1,000<\/span>[\s\S]*title="placed \+ unplaced: 1,250 bp">1,250<\/span>/,
  );
  assert.doesNotMatch(html, /title="unplaced: 3">3<\/span>/);
  assert.doesNotMatch(html, /title="unplaced: 250 bp">250<\/span>/);
});

test("project export page counts current main-track hidden primary contigs", () => {
  const baseState = createState();
  const html = renderProjectExportPage(createState({
    assembly: {
      ...baseState.assembly,
      selectedChrName: "Chr01",
      hiddenPrimaryCtgIds: [2],
    },
    projectExport: {
      ...baseState.projectExport,
      primaryCtgsByChr: {
        Chr01: [
          {
            assemblyCtgId: 1,
            name: "ptg1",
            datasetName: "hifiasm",
            totalLength: 1000,
          },
          {
            assemblyCtgId: 2,
            name: "ptg2",
            datasetName: "hifiasm",
            totalLength: 2000,
          },
        ],
      },
    },
  }));

  assert.match(html, /role="img" aria-label="实际 append: 1\/2; 主图 hidden: 1\/2"/);
  assert.match(html, /title="主图 hidden: 2,000\/3,000 bp"/);
  assert.match(html, /used_主ds_ctg数目[\s\S]*<strong>2\/2<\/strong>/);
  assert.match(html, /used_主ds_ctg长度[\s\S]*<strong>3,000\/3,000<\/strong>/);
});

test("project export stat rows share parent grids so bar ends align within each panel", () => {
  assert.match(
    componentsCss,
    /\.project-export-used-metrics,\s*\.project-export-assignment\s*\{[\s\S]*grid-template-columns:\s*max-content minmax\(0,\s*1fr\) max-content;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-used-row\s*\{\s*display:\s*contents;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-assignment-row\s*\{\s*display:\s*contents;/,
  );
});

test("project export stat values are left aligned after the bars", () => {
  assert.match(
    componentsCss,
    /\.project-export-used-row strong\s*\{[\s\S]*text-align:\s*left;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-assignment-value\s*\{[\s\S]*justify-content:\s*flex-start;[\s\S]*text-align:\s*left;/,
  );
});

test("project export stat bar segments highlight hovered slices with their own color", () => {
  assert.match(
    componentsCss,
    /\.final-path-log-ratio-segment:hover,\s*\.project-export-assignment-segment:hover\s*\{[\s\S]*box-shadow:\s*inset 0 0 0 2px var\(--stat-segment-highlight/,
  );
  assert.match(
    componentsCss,
    /\.final-path-log-ratio-segment\.is-appended\s*\{[\s\S]*--stat-segment-highlight:\s*#14532d;/,
  );
  assert.match(
    componentsCss,
    /\.final-path-log-ratio-segment\.is-log-hidden\s*\{[\s\S]*--stat-segment-highlight:\s*#b45309;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-assignment-segment\.is-placed\s*\{[\s\S]*--stat-segment-highlight:\s*#14532d;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-assignment-segment\.is-unassigned\s*\{[\s\S]*--stat-segment-highlight:\s*#6b7280;/,
  );
});

test("project export detail table is unwrapped, hides ctg, and supports header filters plus length sort", () => {
  const baseState = createState();
  const state = createState({
    projectExport: {
      ...baseState.projectExport,
      chromosomes: [{ chrName: "Chr01" }, { chrName: "Chr02" }],
      primaryCtgsByChr: {
        Chr01: [
          {
            assemblyCtgId: 1,
            name: "ptg1",
            datasetName: "hifiasm",
            totalLength: 1000,
          },
        ],
        Chr02: [
          {
            assemblyCtgId: 2,
            name: "ptg2",
            datasetName: "hifiasm",
            totalLength: 1000,
          },
        ],
      },
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 1,
              datasetName: "hifiasm",
              ctgName: "ptg1",
              originId: "ptg1",
              overallLen: 1000,
              start: 1,
              end: 1000,
            },
            {
              segmentId: "seg-2",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 10,
              datasetName: "flye",
              ctgName: "contig_10",
              originId: "origin_flye",
              overallLen: 300,
              start: 1,
              end: 300,
            },
          ],
        },
        Chr02: {
          mode: "segments",
          chrName: "Chr02",
          segments: [
            {
              segmentId: "seg-3",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 1,
              datasetName: "hifiasm",
              ctgName: "ptg1",
              originId: "ptg1",
              overallLen: 1000,
              start: 1,
              end: 1000,
            },
            {
              segmentId: "seg-4",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 20,
              datasetName: "canu",
              ctgName: "contig_20",
              originId: "origin_canu",
              overallLen: 700,
              start: 1,
              end: 700,
            },
          ],
        },
      },
    },
  });
  const html = renderProjectExportPage(state);

  assert.match(html, /class="project-export-detail-section"/);
  assert.doesNotMatch(html, />明细</);
  assert.doesNotMatch(html, /<th>ctg<\/th>/);
  assert.doesNotMatch(html, /<select data-project-export-detail-filter=/);
  assert.match(html, /辅助 ds_ctg使用情况/);
  assert.match(html, /重复主ds_ctg使用情况/);
  assert.match(html, /class="project-export-detail-filter/);
  assert.match(html, /data-project-export-detail-filter-menu="type"/);
  assert.match(html, /data-project-export-detail-filter="type"/);
  assert.match(html, /data-project-export-detail-filter="chr"/);
  assert.match(html, /data-project-export-detail-filter="dataset"/);
  assert.match(html, /data-project-export-detail-filter-state="all"[\s\S]*value=""\s+checked/);
  assert.match(html, /data-project-export-detail-sort="length_bp"/);

  const filteredHtml = renderProjectExportPage(createState({
    projectExport: {
      ...state.projectExport,
      detailTableFilters: { dataset: "canu" },
    },
  }));
  assert.match(filteredHtml, /data-project-export-detail-filter-state="mixed"/);
  assert.match(filteredHtml, /value="canu"\s+checked/);
  assert.match(filteredHtml, /origin_canu/);
  assert.doesNotMatch(filteredHtml, /origin_flye/);

  const noneHtml = renderProjectExportPage(createState({
    projectExport: {
      ...state.projectExport,
      detailTableFilters: { dataset: ["__project_export_filter_none__"] },
    },
  }));
  assert.match(noneHtml, />暂无记录<\/td>/);
  assert.match(noneHtml, /data-project-export-detail-filter-state="none"/);

  const sortedHtml = renderProjectExportPage(createState({
    projectExport: {
      ...state.projectExport,
      detailTableSort: { key: "length_bp", direction: "desc" },
    },
  }));
  assert.ok(sortedHtml.indexOf("1,000") < sortedHtml.indexOf("700"));
  assert.ok(sortedHtml.indexOf("700") < sortedHtml.indexOf("300"));
});

test("project export final path rows sort by chromosome order and skip empty paths", () => {
  const state = createState({
    projectExport: {
      ...createState().projectExport,
      chromosomes: [{ chrName: "Chr02" }, { chrName: "Chr01" }, { chrName: "Chr03" }],
      finalPathByChr: {
        Chr01: {
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 1,
              ctgName: "ptg1",
              overallLen: 100,
              start: 1,
              end: 100,
            },
          ],
        },
        Chr02: {
          chrName: "Chr02",
          segments: [
            {
              segmentId: "seg-2",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 2,
              ctgName: "ptg2",
              overallLen: 200,
              start: 1,
              end: 200,
            },
          ],
        },
        Chr03: {
          chrName: "Chr03",
          segments: [],
        },
      },
    },
  });

  const entries = __test.getFinalPathPreviewEntries(state);

  assert.deepEqual(entries.map((entry) => entry.chrName), ["Chr02", "Chr01"]);
  assert.deepEqual(entries.map((entry) => entry.lengthBp), [200, 100]);
});

test("project export final path rows merge the latest assembly final paths", () => {
  const entries = __test.getFinalPathPreviewEntries(createState({
    assembly: {
      finalPathTrackView: {},
      finalPathByChr: {
        Chr02: {
          chrName: "Chr02",
          segments: [
            {
              segmentId: "seg-2",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 2,
              ctgName: "ptg2",
              overallLen: 200,
              start: 1,
              end: 200,
            },
          ],
        },
      },
    },
  }));

  assert.deepEqual(entries.map((entry) => entry.chrName), ["Chr01", "Chr02"]);
});

test("project export final path rows expand phased chromosomes and omit the parent path", () => {
  const segment = (segmentId, assemblyCtgId, lengthBp) => ({
    segmentId,
    type: "ctg",
    sourceKind: "assembly_ctg",
    assemblyCtgId,
    datasetName: "hifiasm",
    ctgName: `ptg${assemblyCtgId}`,
    originId: `ptg${assemblyCtgId}`,
    overallLen: lengthBp,
    start: 1,
    end: lengthBp,
  });
  const state = createState({
    initializer: {
      datasets: [{ datasetId: 1, name: "hifiasm", fastaAvailable: true }],
      existingProjects: [
        {
          projectId: 7,
          projectName: "p1",
          primaryDatasetId: 1,
          supportDatasetIds: [],
          phasedAssemblyEnabled: true,
        },
      ],
    },
    projectExport: {
      ...createState().projectExport,
      chromosomes: [{ chrName: "Chr01" }, { chrName: "Chr02" }],
      phasedChrTracksByChr: {
        Chr01: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", displayOrder: 1 },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", displayOrder: 2 },
        ],
      },
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [segment("parent", 1, 100)],
        },
        Chr01A: {
          mode: "segments",
          chrName: "Chr01A",
          segments: [segment("hap-a", 1, 100)],
        },
        Chr01B: {
          mode: "segments",
          chrName: "Chr01B",
          segments: [segment("hap-b", 1, 200)],
        },
        Chr02: {
          mode: "segments",
          chrName: "Chr02",
          segments: [segment("chr02", 2, 300)],
        },
      },
    },
  });
  const entries = __test.getFinalPathPreviewEntries(state);
  const model = __test.buildProjectExportDataModel(state);

  assert.deepEqual(
    entries.map((entry) => [entry.chrName, entry.parentChrName, entry.phasedTrackKey]),
    [
      ["Chr01A", "Chr01", "A"],
      ["Chr01B", "Chr01", "B"],
      ["Chr02", "Chr02", ""],
    ],
  );
  assert.deepEqual(entries.map((entry) => entry.lengthBp), [100, 200, 300]);
  assert.equal(model.statsDisabledByRef, false);
  assert.equal(model.finalPathChrCount, 3);
  assert.match(
    renderProjectExportPage(state),
    /data-project-export-jump-parent-chr="Chr01"[\s\S]*data-project-export-jump-phased-key="A"[\s\S]*data-project-export-jump-chr="Chr01A"/,
  );
});

test("project export loading fetches phased tracks for every parent chromosome", async () => {
  let state = createState({
    initializer: {
      datasets: [{ datasetId: 1, name: "hifiasm", fastaAvailable: true }],
      existingProjects: [
        {
          projectId: 7,
          projectName: "p1",
          primaryDatasetId: 1,
          supportDatasetIds: [],
          phasedAssemblyEnabled: true,
        },
      ],
    },
    projectExport: {},
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const host = {
    innerHTML: "",
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };

  const loaded = await __test.loadProjectExportData(host, store, {
    listProjectChromosomes: async () => ({
      items: [{ chrName: "Chr01" }, { chrName: "Chr02" }],
      unplacedCtgCount: 0,
      unplacedBp: 0,
    }),
    listChrViewCtgs: async ({ chrName }) => ({
      items: [{ assemblyCtgId: chrName === "Chr01" ? 1 : 2, name: `${chrName}_ptg`, totalLength: 100 }],
    }),
    listPhasedChrTracks: async ({ parentChrName }) => ({
      tracks: parentChrName === "Chr01"
        ? [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", displayOrder: 1 },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", displayOrder: 2 },
        ]
        : [],
    }),
    getProjectAssemblyViewState: async () => ({
      finalPathByChr: {
        Chr01: {
          chrName: "Chr01",
          segments: [{ segmentId: "parent", type: "gap", gapSizeBp: 100 }],
        },
        Chr01A: {
          chrName: "Chr01A",
          segments: [{ segmentId: "hap-a", type: "gap", gapSizeBp: 100 }],
        },
      },
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: {},
    }),
  });

  assert.equal(loaded, true);
  assert.deepEqual(state.projectExport.phasedChrTracksByChr.Chr01.map((track) => track.label), ["Chr01A", "Chr01B"]);
  assert.deepEqual(__test.getFinalPathPreviewEntries(state).map((entry) => entry.chrName), ["Chr01A"]);
});

test("project export TSV contains all final path chromosomes in one file", async () => {
  const baseState = createState();
  let state = createState({
    projectExport: {
      ...baseState.projectExport,
      chromosomes: [{ chrName: "Chr01" }, { chrName: "Chr02" }],
      finalPathByChr: {
        ...baseState.projectExport.finalPathByChr,
        Chr02: {
          chrName: "Chr02",
          segments: [
            {
              segmentId: "seg-2",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 2,
              datasetName: "hifiasm",
              ctgName: "ptg2",
              originId: "ptg2",
              overallLen: 200,
              start: 1,
              end: 200,
            },
          ],
        },
      },
    },
  });
  const host = {
    innerHTML: "",
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const saveOptions = [];
  const writes = [];

  const result = await __test.runProjectExport(host, store, "tsv", {
    getExportTimestamp: () => "20260430205930",
    pickSaveFilePath: async (options) => {
      saveOptions.push(options);
      return "/exports/p1_project_path.tsv";
    },
    writeFinalPathExportTextFile: async (payload) => {
      writes.push(payload);
    },
  });

  assert.equal(result, true);
  assert.equal(saveOptions[0].defaultPath, "p1_project_path_20260430205930.tsv");
  assert.equal(writes.length, 1);
  assert.equal(writes[0].outputPath, "/exports/p1_project_path_20260430205930.tsv");
  assert.match(writes[0].text, /^Chr\t#\tCtg\tOrigin ID/m);
  assert.match(writes[0].text, /Chr01\t1\thifiasm_ptg1/);
  assert.match(writes[0].text, /Chr02\t1\thifiasm_ptg2/);
  assert.doesNotMatch(writes[0].text, /p1_Chr01_path/);
});

test("project export TSV fills missing origin id from loaded ctg data without guessing names", async () => {
  let state = createState({
    projectExport: {
      ...createState().projectExport,
      ctgsByChr: {
        Chr01: [
          {
            assemblyCtgId: 1,
            name: "degap_gf_chr2_gap4@Chr2",
            datasetName: "degap",
            originId: "gf_chr2_gap4",
            totalLength: 144525333,
          },
        ],
      },
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 1,
              datasetName: "degap",
              ctgName: "degap_gf_chr2_gap4@Chr2",
              overallLen: 144525333,
              start: 1,
              end: 100,
            },
          ],
        },
      },
    },
  });
  const host = {
    innerHTML: "",
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const writes = [];

  const result = await __test.runProjectExport(host, store, "tsv", {
    getExportTimestamp: () => "20260430205930",
    pickSaveFilePath: async () => "/exports/p1_project_path.tsv",
    writeFinalPathExportTextFile: async (payload) => {
      writes.push(payload);
    },
  });

  assert.equal(result, true);
  assert.match(writes[0].text, /Chr01\t1\tdegap_gf_chr2_gap4@Chr2\tgf_chr2_gap4\t144525333\t\+\t1\t100\t1\t100/);
});

test("project export TSV fails instead of guessing missing origin id from ctg name", async () => {
  let state = createState({
    projectExport: {
      ...createState().projectExport,
      primaryCtgsByChr: { Chr01: [] },
      ctgsByChr: { Chr01: [] },
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 99,
              datasetName: "degap",
              ctgName: "degap_gf_chr2_gap4@Chr2",
              overallLen: 144525333,
              start: 1,
              end: 100,
            },
          ],
        },
      },
    },
  });
  const host = {
    innerHTML: "",
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const writes = [];

  const result = await __test.runProjectExport(host, store, "tsv", {
    getExportTimestamp: () => "20260430205930",
    pickSaveFilePath: async () => "/exports/p1_project_path.tsv",
    writeFinalPathExportTextFile: async (payload) => {
      writes.push(payload);
    },
  });

  assert.equal(result, false);
  assert.equal(writes.length, 0);
  assert.equal(store.getState().projectExport.job.status, "error");
  assert.match(store.getState().projectExport.job.error, /Missing Origin ID/);
  assert.doesNotMatch(store.getState().projectExport.job.error, /gf_chr2_gap4/);
});

test("project export all writes one merged artifact per export type", async () => {
  const baseState = createState();
  let state = createState({
    projectExport: {
      ...baseState.projectExport,
      chromosomes: [{ chrName: "Chr01" }, { chrName: "Chr02" }],
      finalPathByChr: {
        ...baseState.projectExport.finalPathByChr,
        Chr02: {
          chrName: "Chr02",
          segments: [
            {
              segmentId: "seg-2",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 2,
              datasetName: "hifiasm",
              ctgName: "ptg2",
              originId: "ptg2",
              overallLen: 200,
              start: 1,
              end: 200,
            },
          ],
        },
      },
    },
  });
  const host = {
    innerHTML: "",
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const textWrites = [];
  const binaryWrites = [];
  const fastaExports = [];

  const result = await __test.runProjectExport(host, store, "all", {
    getExportTimestamp: () => "20260430205930",
    pickDirectoryPath: async () => "/exports",
    renderFinalPathViewportPng: async () => "png-bytes",
    writeFinalPathExportTextFile: async (payload) => {
      textWrites.push(payload);
    },
    writeFinalPathExportBinaryFile: async (payload) => {
      binaryWrites.push(payload);
    },
    exportProjectFinalPathFasta: async (payload) => {
      fastaExports.push(payload);
    },
  });

  assert.equal(result, true);
  assert.deepEqual(binaryWrites.map((item) => item.outputPath), ["/exports/p1_project_path_20260430205930.png"]);
  assert.deepEqual(textWrites.map((item) => item.outputPath), [
    "/exports/p1_project_path_20260430205930.tsv",
    "/exports/p1_project_path_20260430205930.log",
  ]);
  assert.deepEqual(fastaExports.map((item) => item.outputPath), ["/exports/p1_project_path_20260430205930.fasta"]);
  assert.deepEqual(Object.keys(fastaExports[0].finalPathByChr), ["Chr01", "Chr02"]);
  assert.match(textWrites[0].text, /Chr01\t1\thifiasm_ptg1/);
  assert.match(textWrites[0].text, /Chr02\t1\thifiasm_ptg2/);
});

test("project export all sends phased haplotypes to fasta and omits phased parent chr", async () => {
  const baseState = createState();
  let state = createState({
    initializer: {
      ...baseState.initializer,
      existingProjects: [
        {
          projectId: 7,
          projectName: "p1",
          primaryDatasetId: 1,
          supportDatasetIds: [],
          phasedAssemblyEnabled: true,
        },
      ],
    },
    projectExport: {
      ...baseState.projectExport,
      chromosomes: [{ chrName: "Chr01" }],
      phasedChrTracksByChr: {
        Chr01: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", displayOrder: 1 },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", displayOrder: 2 },
        ],
      },
      finalPathByChr: {
        Chr01: {
          chrName: "Chr01",
          segments: [{ segmentId: "parent", type: "gap", gapSizeBp: 100 }],
        },
        Chr01A: {
          chrName: "Chr01A",
          segments: [{ segmentId: "hap-a", type: "gap", gapSizeBp: 100 }],
        },
        Chr01B: {
          chrName: "Chr01B",
          segments: [{ segmentId: "hap-b", type: "gap", gapSizeBp: 200 }],
        },
      },
    },
  });
  const host = {
    innerHTML: "",
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  const fastaExports = [];

  const result = await __test.runProjectExport(host, store, "fasta", {
    getExportTimestamp: () => "20260430205930",
    pickSaveFilePath: async () => "/exports/p1_project_path.fasta",
    exportProjectFinalPathFasta: async (payload) => {
      fastaExports.push(payload);
    },
  });

  assert.equal(result, true);
  assert.deepEqual(Object.keys(fastaExports[0].finalPathByChr), ["Chr01A", "Chr01B"]);
});

test("project export final path preview uses the longest chr as the shared scale", () => {
  const html = renderProjectExportPage(createState({
    projectExport: {
      ...createState().projectExport,
      chromosomes: [{ chrName: "Chr02" }, { chrName: "Chr01" }],
      finalPathByChr: {
        Chr02: {
          chrName: "Chr02",
          segments: [
            {
              segmentId: "seg-2",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 2,
              ctgName: "ptg2",
              overallLen: 200,
              start: 1,
              end: 200,
            },
          ],
        },
        Chr01: {
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 1,
              ctgName: "ptg1",
              overallLen: 100,
              start: 1,
              end: 100,
            },
          ],
        },
      },
    },
  }));
  const chr02Width = Number(html.match(/data-project-export-jump-chr="Chr02"[\s\S]*?class="project-export-final-path-preview-ctg"[\s\S]*?width: ([0-9.]+)%;/)?.[1] || 0);
  const chr01Width = Number(html.match(/data-project-export-jump-chr="Chr01"[\s\S]*?class="project-export-final-path-preview-ctg"[\s\S]*?width: ([0-9.]+)%;/)?.[1] || 0);

  assert.ok(chr02Width > 0);
  assert.ok(chr01Width > 0);
  assert.ok(Math.abs(chr02Width - 100) < 0.001);
  assert.ok(Math.abs((chr01Width / chr02Width) - 0.5) < 0.02);
  assert.match(html, /class="project-export-final-path-preview-length">200 bp<\/span>/);
  assert.match(html, /class="project-export-final-path-preview-length">100 bp<\/span>/);
});

test("project export final path preview clamps edge gap markers inside the track", () => {
  const html = renderProjectExportPage(createState({
    projectExport: {
      ...createState().projectExport,
      finalPathByChr: {
        Chr01: {
          chrName: "Chr01",
          segments: [
            {
              segmentId: "gap-start",
              type: "gap",
              gapSizeBp: 100,
            },
            {
              segmentId: "seg-1",
              type: "ctg",
              sourceKind: "assembly_ctg",
              assemblyCtgId: 1,
              ctgName: "ptg1",
              overallLen: 1000,
              start: 1,
              end: 1000,
            },
          ],
        },
      },
    },
  }));

  assert.match(html, /class="project-export-final-path-preview-gap"/);
  assert.match(html, /class="project-export-final-path-preview-ctg is-after-gap"/);
  assert.match(html, /left: clamp\(0px, calc\([0-9.]+% - 4px\), calc\(100% - 8px\)\);/);
  assert.match(html, /class="project-export-final-path-preview-gap-label" style="left: clamp\(14px, [0-9.]+%, calc\(100% - 14px\)\);">GAP<\/span>/);
});

test("project export final path row jump switches to assembly chr and requests bottom scroll", () => {
  let state = createState({
    activeRoute: "projectExport",
    assembly: {
      finalPathTrackView: {},
      chromosomes: [{ chrName: "Chr01" }],
      selectedChrName: "Chr01",
      loading: false,
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };

  assert.equal(__test.jumpToAssemblyChr(store, "Chr02"), true);
  assert.equal(state.activeRoute, "assembly");
  assert.equal(state.assembly.selectedChrName, "Chr02");
  assert.equal(state.assembly.activeTab, "assembly");
  assert.equal(state.assembly.projectExportScrollToBottom, true);
  assert.deepEqual(state.assembly.chromosomes, []);
});

test("project export final path row jump switches phased rows to the parent chr and active haplotype", () => {
  let state = createState({
    activeRoute: "projectExport",
    assembly: {
      finalPathTrackView: {},
      chromosomes: [{ chrName: "Chr01" }],
      selectedChrName: "Chr01",
      loading: false,
      activePhasedTrackKeyByChr: { Chr01: "A" },
      activeFinalPathKey: "A",
      activeFinalPathKeyByChr: { Chr01: "A" },
      projectExportScrollToBottom: false,
    },
    initializer: {
      existingProjects: [
        {
          projectId: 7,
          projectName: "p1",
          primaryDatasetId: 1,
          supportDatasetIds: [],
          phasedAssemblyEnabled: true,
        },
      ],
    },
    projectExport: {
      projectId: 7,
      phasedChrTracksByChr: {
        Chr01: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", displayOrder: 1 },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", displayOrder: 2 },
        ],
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };

  assert.equal(
    __test.jumpToAssemblyChr(store, {
      selectedChrName: "Chr01B",
    }),
    true,
  );
  assert.equal(state.activeRoute, "assembly");
  assert.equal(state.assembly.selectedChrName, "Chr01");
  assert.equal(state.assembly.activePhasedTrackKey, "B");
  assert.equal(state.assembly.activePhasedTrackKeyByChr.Chr01, "B");
  assert.equal(state.assembly.activeFinalPathKey, "B");
  assert.equal(state.assembly.activeFinalPathKeyByChr.Chr01, "B");
  assert.equal(state.assembly.projectExportScrollToBottom, true);
});

test("project export final path row jump keeps clicked phased chr target instead of reusing previous final path", () => {
  let state = createState({
    activeRoute: "projectExport",
    assembly: {
      finalPathTrackView: {},
      chromosomes: [{ chrName: "Chr01" }],
      selectedChrName: "Chr01",
      loading: false,
      activePhasedTrackKeyByChr: { Chr01: "A" },
      activeFinalPathKey: "A",
      activeFinalPathKeyByChr: { Chr01: "A" },
    },
    initializer: {
      existingProjects: [
        {
          projectId: 7,
          projectName: "p1",
          primaryDatasetId: 1,
          supportDatasetIds: [],
          phasedAssemblyEnabled: true,
        },
      ],
    },
    projectExport: {
      ...createState().projectExport,
      phasedChrTracksByChr: {
        Chr01: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", displayOrder: 1 },
        ],
        Chr02: [
          { phasedTrackId: 201, haplotypeKey: "A", label: "Chr02A", displayOrder: 1 },
          { phasedTrackId: 202, haplotypeKey: "B", label: "Chr02B", displayOrder: 2 },
        ],
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };

  assert.equal(
    __test.jumpToAssemblyChr(store, {
      parentChrName: "Chr02",
      chrName: "Chr02B",
      activePhasedTrackKey: "B",
    }),
    true,
  );
  assert.equal(state.activeRoute, "assembly");
  assert.equal(state.assembly.selectedChrName, "Chr02");
  assert.equal(state.assembly.activePhasedTrackKey, "B");
  assert.equal(state.assembly.activePhasedTrackKeyByChr.Chr02, "B");
  assert.equal(state.assembly.activeFinalPathKey, "B");
  assert.equal(state.assembly.activeFinalPathKeyByChr.Chr02, "B");
  assert.equal(state.assembly.activeFinalPathKeyByChr.Chr01, "A");
  assert.equal(state.assembly.projectExportScrollToBottom, true);
});

test("project export final path preview css is clickable and hides graph label spacer", () => {
  assert.match(
    componentsCss,
    /\.project-export-detail-table\s*\{[\s\S]*border:\s*1px solid #d1d1d1;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-detail-table td\s*\{[\s\S]*background:\s*#fff;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-detail-filter-menu\s*\{[\s\S]*position:\s*absolute;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-detail-filter\[open\] > summary::before\s*\{[\s\S]*border-bottom:\s*5px solid #333;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-row:hover,\s*\.project-export-final-path-row:focus-visible\s*\{[\s\S]*box-shadow:\s*inset 0 0 0 1px #7c9bbc;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-row-graph\s*\{[\s\S]*display:\s*flex;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-track\s*\{[\s\S]*height:\s*52px;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-length\s*\{[\s\S]*flex:\s*0 0 120px;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-ctg\s*\{[\s\S]*font-size:\s*11px;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-ctg\s*\{[\s\S]*height:\s*16px;[\s\S]*line-height:\s*14px;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-ctg\.is-after-gap span\s*\{[\s\S]*padding-left:\s*10px;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-ctg\.is-label-hidden span\s*\{[\s\S]*visibility:\s*hidden;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-gap\s*\{[\s\S]*z-index:\s*3;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-gap-label\s*\{[\s\S]*z-index:\s*4;/,
  );
});

test("project export final path preview hides labels that cannot fit fully", () => {
  function createCtgNode(labelWidth, visibleWidth) {
    const classes = new Set();
    return {
      classes,
      classList: {
        add(value) {
          classes.add(value);
        },
        remove(value) {
          classes.delete(value);
        },
      },
      querySelector(selector) {
        return selector === "span"
          ? { scrollWidth: labelWidth, clientWidth: visibleWidth }
          : null;
      },
    };
  }
  const clippedNode = createCtgNode(80, 40);
  const fittingNode = createCtgNode(40, 80);

  __test.syncProjectExportPreviewLabels({
    querySelectorAll() {
      return [clippedNode, fittingNode];
    },
  });

  assert.equal(clippedNode.classes.has("is-label-hidden"), true);
  assert.equal(fittingNode.classes.has("is-label-hidden"), false);
});

test("project export detail filter syncs mixed all-checkbox state", () => {
  const allInput = {
    dataset: { projectExportDetailFilterState: "mixed" },
    indeterminate: false,
  };

  __test.syncProjectExportDetailFilterControls({
    querySelectorAll() {
      return [allInput];
    },
  });

  assert.equal(allInput.indeterminate, true);
});
