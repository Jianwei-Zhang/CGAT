import { previewMutationStamp, beginPreviewContentOperation, finishPreviewContentOperation } from "../../../services/preview-content-events.js";
import { currentProjectExportJob } from "../../../services/project-export-jobs.js";
import test from "node:test";
import assert from "node:assert/strict";

import { buildProjectPreviewModel, previewProjectKey } from "../project-preview-state.js";
import { PREVIEW_MODEL_VERSION, previewOverrideSignature } from "../project-preview-cache.js";
import { FLOATING_MENU_CLOSE_DELAY_MS } from "../floating-menu-runtime.js";
import { __test, bindProjectExportPage, renderProjectExportPage, renderProjectPathOverview, bindProjectPathOverview, releaseProjectPathOverview } from "../project-export-page.js";
import { readStylesheetTree } from "../../../styles/__tests__/style-test-support.mjs";

const componentsCss = readStylesheetTree(new URL("../../../styles/components.css", import.meta.url));

function renderLoadedPathOverview(state) {
  return renderProjectPathOverview({ ...state, projectExport: { ...state.projectExport,
    loaded: true, workspacePath: state.session.workspacePath, mutationStamp: previewMutationStamp({ workspaceRoot: state.session.workspacePath, projectId: state.session.projectId }) } });
}

function createState(overrides = {}) {
  const value = {
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
      loaded: true,
      workspacePath: "/tmp/ws",
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
  };  if (value.projectExport) value.projectExport = {
    loaded: true, workspacePath: value.session.workspacePath,
    mutationStamp: previewMutationStamp({ workspaceRoot: value.session.workspacePath, projectId: value.session.projectId }),
    ...value.projectExport,
  };
  return value;
}

test("project export page renders assignment bars before placed statistics with a final-path style export menu", () => {
  const html = renderProjectExportPage(createState());

  assert.doesNotMatch(html, /<h[1-6][^>]*>概览</);
  assert.match(html, /<dl class="project-export-identity">[\s\S]*<dt>项目<\/dt><dd[^>]*>p1<\/dd>[\s\S]*<dt>主数据集<\/dt><dd[^>]*>hifiasm<\/dd>/);
  assert.ok(html.indexOf("data-preview-download") < html.indexOf("data-project-export-toggle"));
  assert.equal((html.match(/data-preview-download/g) || []).length, 1);
  assert.doesNotMatch(html, /project-preview-heading|project-preview-subtitle|project-preview-legend/);
  assert.doesNotMatch(html, /card project-export-card/);
  assert.doesNotMatch(html, /data-project-export-refresh/);
  assert.match(html, /class="button ghost tiny final-path-export-toggle"[\s\S]*data-project-export-toggle="true"[\s\S]*>导出<\/button>/);
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
  assert.match(html, />全部<\/button>/);
  assert.doesNotMatch(html, /导出图|导出表|导出日志|导出序列|一键导出/);
  assert.doesNotMatch(html, /final path chr/i);
  assert.doesNotMatch(html, /project-export-summary-line/);
  assert.ok(html.indexOf(">主数据集分配统计<") < html.indexOf(">已放置统计<"));
  assert.match(html, />已放置统计</);
  assert.match(html, /已使用主组装 Contig 数量/);
  assert.match(html, /final-path-log-ratio-segment is-appended/);
  assert.match(html, /1\/1/);
  assert.match(html, /主数据集分配统计/);
  assert.match(html, />数目</);
  assert.match(html, />长度</);
  assert.equal((html.match(/class="project-export-assignment-bar"/g) || []).length, 2);
  assert.match(html, /project-export-assignment-segment is-placed/);
  assert.match(html, /project-export-assignment-segment is-unassigned/);
  assert.match(html, />已放置</);
  assert.match(html, /未分配/);
  assert.doesNotMatch(html, /project-export-assignment-value-part is-/);
  assert.match(html, /实际追加/);
  assert.match(html, /主图已隐藏/);
  assert.match(html, /<div class="project-export-used-metrics">[\s\S]*class="project-export-used-row"[\s\S]*class="project-export-used-row"/);
  assert.doesNotMatch(html, /class="project-export-final-path-list"/);
  assert.match(html, /data-overview-preview[\s\S]*project-preview-page/);
  const pathHtml = renderLoadedPathOverview(createState());
  assert.match(pathHtml, /class="project-export-final-path-list"/);
  assert.match(pathHtml, /class="project-export-final-path-row"[\s\S]*data-project-export-jump-chr="Chr01"/);
  assert.match(pathHtml, /class="project-export-final-path-row-label">Chr01<\/strong>/);
  assert.match(pathHtml, /class="project-export-final-path-preview-track"/);
  assert.match(pathHtml, /class="project-export-final-path-preview-ctg"[\s\S]*?width: 100\.0000%;/);
  assert.match(pathHtml, /class="project-export-final-path-preview-length">1,000 bp<\/span>/);
  assert.doesNotMatch(pathHtml, /track-ruler-line/);
  assert.doesNotMatch(pathHtml, /final-path-card-toggle/);
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

test("project export load failure settles with an error and explicit refresh", async () => {
  let state = createState({
    activeRoute: "projectExport",
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
    listProjectChromosomes: async () => {
      throw new Error("workspace missing project.sqlite");
    },
  });

  assert.equal(loaded, false);
  assert.equal(state.projectExport.loading, false);
  assert.equal(state.projectExport.loaded, false);
  assert.equal(state.projectExport.error, "workspace missing project.sqlite");
  assert.doesNotMatch(host.innerHTML, /正在加载项目导出数据/);
  assert.match(host.innerHTML, /概览数据加载失败/);
  assert.match(host.innerHTML, /data-project-export-refresh="1"[^>]*>刷新<\/button>/);
});

test("late project export work cannot redraw a different active route", () => {
  const host = { innerHTML: "assembly stays mounted" };
  const state = createState({ activeRoute: "assembly" });
  const store = {
    getState() {
      return state;
    },
  };

  __test.rerender(host, store);

  assert.equal(host.innerHTML, "assembly stays mounted");
});

test("project export loading canonicalizes persisted GRT overallLen from the project view", async () => {
  let state = createState({
    projectExport: {
      ...createState().projectExport,
      finalPathByChr: {},
    },
    assembly: {
      finalPathByChr: {},
      grtProjectView: {},
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
  const host = {
    innerHTML: "",
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };

  const loaded = await __test.loadProjectExportData(host, store, {
    listProjectChromosomes: async () => ({
      items: [{ chrName: "Chr01" }],
      unplacedCtgCount: 0,
      unplacedBp: 0,
    }),
    listChrViewCtgs: async () => ({ items: [] }),
    getProjectAssemblyViewState: async () => ({
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [{
            segmentId: "patch-1",
            type: "ctg",
            datasetName: "hifiasm",
            ctgName: "ptg000002l",
            originId: "ptg000002l",
            overallLen: 28_911_543,
            start: 28_911_543,
            end: 28_911_536,
            source: {
              dataset: "hifiasm",
              contig: "ptg000002l",
              start: 28_911_536,
              end: 28_911_543,
              orientation: "-",
            },
            serverBaseline: true,
          }],
        },
      },
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: {},
    }),
    getGrtProjectView: async () => ({
      final_path_by_chr: {
        Chr01: {
          chr: "Chr01",
          q4_length: 8,
          q4_sha256: "q4-sha",
          segments: [{
            segment_id: "patch-1",
            kind: "patch",
            length: 8,
            source_length: 43_726_252,
            source: {
              dataset: "hifiasm",
              contig: "ptg000002l",
              start: 28_911_536,
              end: 28_911_543,
              orientation: "-",
            },
          }],
        },
      },
    }),
  });

  assert.equal(loaded, true);
  assert.equal(
    state.projectExport.finalPathByChr.Chr01.segments[0].overallLen,
    43_726_252,
  );
  assert.deepEqual(
    [
      state.projectExport.finalPathByChr.Chr01.segments[0].start,
      state.projectExport.finalPathByChr.Chr01.segments[0].end,
    ],
    [28_911_543, 28_911_536],
  );
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
  assert.match(html, /正在导出 Final Path/);
  assert.match(html, /p1 · 全部/);
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
  assert.match(html, /<div class="project-export-summary-line"><span>参考: <strong>Chr01<\/strong><\/span><\/div>/);
  assert.match(html, /项目统计和日志导出已关闭/);
  assert.doesNotMatch(html, /已使用主组装 Contig 数量/);
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
    /<div class="project-export-assignment-row">[\s\S]*?>数目<[\s\S]*data-app-tooltip="已放置: 1">1<\/span>[\s\S]*data-app-tooltip="已放置 \+ 未分配: 4">4<\/span>/,
  );
  assert.match(
    html,
    /<div class="project-export-assignment-row">[\s\S]*?>长度<[\s\S]*data-app-tooltip="已放置: 1,000 bp">1,000<\/span>[\s\S]*data-app-tooltip="已放置 \+ 未分配: 1,250 bp">1,250<\/span>/,
  );
  assert.doesNotMatch(html, /title="未分配: 3">3<\/span>/);
  assert.doesNotMatch(html, /title="未分配: 250 bp">250<\/span>/);
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

  assert.match(html, /role="img" aria-label="实际追加: 1\/2; 主图已隐藏: 1\/2"/);
  assert.match(html, /data-app-tooltip="主图已隐藏: 2,000\/3,000 bp"/);
  assert.match(html, /已使用主组装 Contig 数量[\s\S]*<strong>2\/2<\/strong>/);
  assert.match(html, /已使用主组装 Contig 长度[\s\S]*<strong>3,000\/3,000<\/strong>/);
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
  assert.match(html, /辅助组装 Contig 使用情况/);
  assert.match(html, /重复主组装 Contig 使用情况/);
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

test("project export final path rows sort numeric chromosomes naturally and skip empty paths", () => {
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

  assert.deepEqual(entries.map((entry) => entry.chrName), ["Chr01", "Chr02"]);
  assert.deepEqual(entries.map((entry) => entry.lengthBp), [100, 200]);
});

test("project export final path rows use natural order before project export chromosomes load", () => {
  const baseState = createState();
  const makePath = (chrName) => ({
    chrName,
    segments: [{
      segmentId: `gap-${chrName}`,
      type: "gap",
      gapSizeBp: 100,
    }],
  });
  const state = createState({
    assembly: {
      finalPathTrackView: {},
      chromosomes: [
        { chrName: "Chr1" },
        { chrName: "Chr10" },
        { chrName: "Chr2" },
        { chrName: "Chr3" },
      ],
      finalPathByChr: {
        Chr1: makePath("Chr1"),
        Chr10: makePath("Chr10"),
        Chr2: makePath("Chr2"),
        Chr3: makePath("Chr3"),
      },
    },
    projectExport: {
      ...baseState.projectExport,
      chromosomes: [],
      finalPathByChr: {},
    },
  });

  const entries = __test.getFinalPathPreviewEntries(state);
  const expectedNames = ["Chr1", "Chr2", "Chr3", "Chr10"];
  assert.deepEqual(entries.map((entry) => entry.chrName), expectedNames);

  const htmlNames = [...renderLoadedPathOverview(state).matchAll(/data-project-export-jump-chr="([^"]+)"/g)]
    .map(([, chrName]) => chrName);
  assert.deepEqual(htmlNames, expectedNames);

  const tsvNames = __test.buildProjectFinalPathTsvText(entries)
    .trimEnd()
    .split("\n")
    .slice(1)
    .map((row) => row.split("\t")[0]);
  assert.deepEqual(tsvNames, expectedNames);

  const svgMarkup = __test.buildProjectFinalPathSvgSnapshot({
    entries,
    projectName: "p1",
    primaryDatasetName: "hifiasm",
  }).svgMarkup;
  expectedNames.slice(0, -1).forEach((chrName, index) => {
    assert.ok(svgMarkup.indexOf(`>${chrName}</text>`) < svgMarkup.indexOf(`>${expectedNames[index + 1]}</text>`));
  });
});

test("project export final path rows preserve nonnumeric chromosome source slots", () => {
  const names = ["Chr10", "ChrX", "Chr2", "ChrM", "Chr1"];
  const finalPathByChr = Object.fromEntries(names.map((chrName) => [chrName, {
    chrName,
    segments: [{ segmentId: `gap-${chrName}`, type: "gap", gapSizeBp: 100 }],
  }]));
  const entries = __test.getFinalPathPreviewEntries(createState({
    projectExport: {
      ...createState().projectExport,
      chromosomes: names.map((chrName) => ({ chrName })),
      finalPathByChr,
    },
  }));

  assert.deepEqual(entries.map((entry) => entry.chrName), ["Chr1", "ChrX", "Chr2", "ChrM", "Chr10"]);
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
    renderLoadedPathOverview(state),
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
  const html = renderLoadedPathOverview(createState({
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
  const html = renderLoadedPathOverview(createState({
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
  assert.doesNotMatch(html, /project-export-final-path-preview-gap-label|>GAP<\/span>/);
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
    /\.project-export-detail-section\s*\{[\s\S]*border:\s*1px solid var\(--theme-line,\s*#cdd6e0\);/,
  );
  assert.match(
    componentsCss,
    /\.project-export-detail-table td\s*\{[\s\S]*background:\s*var\(--surface-panel,\s*#fff\);/,
  );
  assert.match(
    componentsCss,
    /\.project-export-detail-filter-menu\s*\{[\s\S]*position:\s*absolute;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-detail-filter\[open\] > summary::before\s*\{[\s\S]*border-bottom:\s*5px solid var\(--theme-strong-line,\s*#333\);/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-row:hover::after,\s*\.project-export-final-path-row:focus-visible::after\s*\{[^}]*border-color:\s*var\(--theme-line,\s*#7c9bbc\);/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-row-graph\s*\{[\s\S]*display:\s*flex;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-track\s*\{[^}]*min-height:\s*40px;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-length\s*\{[\s\S]*flex:\s*0 0 120px;/,
  );
  assert.match(
    componentsCss,
    /\.project-export-final-path-preview-ctg\s*\{[\s\S]*font-size:\s*var\(--font-small\);/,
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
});

test("project export preview fills the card height without a nested frame", () => {
  const rowRule = componentsCss.match(/\.project-export-final-path-row\s*\{([^}]*)\}/)?.[1] || "";
  const graphRule = componentsCss.match(/\.project-export-final-path-row-graph\s*\{([^}]*)\}/)?.[1] || "";
  const trackRule = componentsCss.match(/\.project-export-final-path-preview-track\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(rowRule, /padding:\s*0 10px;/);
  assert.match(rowRule, /border:\s*1px solid var\(--border-subtle, #dbe3ec\);/);
  assert.match(graphRule, /align-self:\s*stretch;/);
  assert.match(graphRule, /align-items:\s*center;/);
  assert.match(trackRule, /align-self:\s*stretch;/);
  assert.match(trackRule, /min-height:\s*40px;/);
  assert.match(trackRule, /height:\s*auto;/);
  assert.match(trackRule, /border:\s*0;/);
  assert.match(trackRule, /border-radius:\s*0;/);
  assert.match(trackRule, /background:\s*var\(--surface-panel,\s*#fff\);/);

  for (const selector of ["ctg", "gap"]) {
    const rule = componentsCss.match(new RegExp(`\\.project-export-final-path-preview-${selector}\\s*\\{([^}]*)\\}`))?.[1] || "";
    assert.match(rule, /top:\s*calc\(50% - 8px\);/);
    assert.match(rule, /height:\s*16px;/);
  }
});

test("project export hover and focus ring stays above the preview without intercepting input", () => {
  const rowRule = componentsCss.match(/\.project-export-final-path-row\s*\{([^}]*)\}/)?.[1] || "";
  const ringRule = componentsCss.match(/\.project-export-final-path-row::after\s*\{([^}]*)\}/)?.[1] || "";
  const activeRowRule = componentsCss.match(/\.project-export-final-path-row:hover,\s*\.project-export-final-path-row:focus-visible\s*\{([^}]*)\}/)?.[1] || "";
  const activeRingRule = componentsCss.match(/\.project-export-final-path-row:hover::after,\s*\.project-export-final-path-row:focus-visible::after\s*\{([^}]*)\}/)?.[1] || "";

  assert.match(rowRule, /position:\s*relative;/);
  assert.match(rowRule, /isolation:\s*isolate;/);
  assert.match(ringRule, /content:\s*"";/);
  assert.match(ringRule, /position:\s*absolute;/);
  assert.match(ringRule, /inset:\s*-1px;/);
  assert.match(ringRule, /border:\s*2px solid transparent;/);
  assert.match(ringRule, /border-radius:\s*inherit;/);
  assert.match(ringRule, /pointer-events:\s*none;/);
  assert.doesNotMatch(activeRowRule, /box-shadow:/);
  assert.match(activeRingRule, /border-color:\s*var\(--theme-line,\s*#7c9bbc\);/);

  const ringZIndex = Number(ringRule.match(/z-index:\s*(\d+);/)?.[1] || 0);
  for (const selector of ["ctg", "gap"]) {
    const rule = componentsCss.match(new RegExp(`\\.project-export-final-path-preview-${selector}\\s*\\{([^}]*)\\}`))?.[1] || "";
    const contentZIndex = Number(rule.match(/z-index:\s*(\d+);/)?.[1] || 0);
    assert.ok(ringZIndex > contentZIndex, `${selector} must stay below the interaction ring`);
  }
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
    querySelectorAll(selector) {
      return selector === ".project-export-final-path-preview-ctg" ? [clippedNode, fittingNode] : [];
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


test("detail card defaults collapsed and remembers expansion while preserving its data", async () => {
  let state = createState();
  state.projectExport.finalPathByChr.Chr01.segments.push({
    segmentId: "support-1", type: "ctg", assemblyCtgId: 2, datasetName: "assembly",
    ctgName: "contig_40", originId: "contig_40", overallLen: 1000, start: 1, end: 500,
  });
  state.projectExport.detailTableFilters = { chr: ["Chr01"] };
  state.projectExport.detailTableSort = { key: "length_bp", direction: "desc" };
  const before = structuredClone(state.projectExport);
  const listeners = new Map();
  let focused = 0;
  const button = { focus() { focused += 1; } };
  const host = {
    innerHTML: renderProjectExportPage(state),
    addEventListener(type, handler) { listeners.set(type, [...(listeners.get(type) || []), handler]); },
    querySelectorAll() { return []; },
    querySelector() { return button; },
  };
  const store = { getState: () => state, setState(next) { state = next; } };
  bindProjectExportPage(host, store);
  assert.match(host.innerHTML, /id="project-export-detail-title">项目明细/);
  assert.match(host.innerHTML, /aria-expanded="false"[\s\S]*?展开/);
  assert.match(host.innerHTML, /id="project-export-detail-body"[^>]* hidden/);
  const click = async () => {
    for (const handler of listeners.get("click")) await handler({ target: { closest(selector) {
      return selector === "[data-project-export-detail-toggle]" ? button : null;
    } } });
  };
  await click();
  assert.equal(state.projectExport.detailTableCollapsed, false);
  assert.doesNotMatch(host.innerHTML, /id="project-export-detail-body"[^>]* hidden/);
  assert.match(host.innerHTML, /aria-expanded="true"[\s\S]*?收起/);
  assert.doesNotMatch(renderProjectExportPage(state), /id="project-export-detail-body"[^>]* hidden/);
  await click();
  assert.equal(state.projectExport.detailTableCollapsed, true);
  assert.match(host.innerHTML, /id="project-export-detail-body"[^>]* hidden/);
  assert.equal(focused, 2);
  assert.deepEqual(state.projectExport.detailTableFilters, before.detailTableFilters);
  assert.deepEqual(state.projectExport.detailTableSort, before.detailTableSort);
  assert.deepEqual(state.projectExport.finalPathByChr, before.finalPathByChr);
});


test("project export preview tags both gaps and contigs for shared minimum-pixel layout", () => {
  const value = createState();
  value.projectExport.finalPathByChr = { Chr01: { mode: "segments", chrName: "Chr01", segments: [
    { type: "ctg", assemblyCtgId: 1, datasetName: "primary", ctgName: "long", overallLen: 1000000, start: 1, end: 1000000 },
    { type: "gap", gapSizeBp: 1 },
    { type: "ctg", assemblyCtgId: 2, datasetName: "primary", ctgName: "tiny", overallLen: 1, start: 1, end: 1 },
  ] } };
  const output = renderLoadedPathOverview(value);
  assert.match(output, /data-final-path-strip="1"/);
  assert.match(output, /data-final-path-kind="gap" data-final-path-length="1"/);
  assert.match(output, /data-final-path-kind="ctg" data-final-path-length="1"/);
  assert.doesNotMatch(output, /data-final-path-gap-label|>GAP<\/span>/);
});


test("project export SVG keeps white gap markers and tooltips without GAP text", () => {
  const { svgMarkup } = __test.buildProjectFinalPathSvgSnapshot({ entries: [{ chrName: "Chr1", lengthBp: 102,
    entry: { segments: [{ type: "gap", gapSizeBp: 100 },
      { type: "ctg", start: 1, end: 2, overallLen: 2, ctgName: "a" }] } }], projectName: "test" });
  assert.match(svgMarkup, /fill="#ffffff"[^>]*><title>GAP 100 bp<\/title>/);
  assert.doesNotMatch(svgMarkup, /<text[^>]*>GAP<\/text>/);
});

function exportDeferred() { let resolve, reject; const promise = new Promise((r, j) => { resolve = r; reject = j; }); return { promise, resolve, reject }; }
function exportHarness(initial = createState()) {
  let state = { ...initial, activeRoute: "projectExport" }, paints = 0;
  const listeners = new Set();
  const host = { addEventListener() {}, querySelectorAll: () => [], querySelector: () => null,
    get innerHTML() { return ""; }, set innerHTML(_html) { paints++; } };
  const store = { getState: () => state, setState: patch => { state = { ...state, ...patch }; listeners.forEach(fn => fn()); },
    subscribe: fn => { listeners.add(fn); return () => listeners.delete(fn); } };
  return { host, store, get paints() { return paints; }, get subscriptions() { return listeners.size; } };
}
const exportDataDeps = paths => ({ listProjectChromosomes: async () => ({ items: [] }),
  getProjectAssemblyViewState: async () => ({ finalPathByChr: paths }), getGrtProjectView: async () => ({}) });

test("background export completes its original snapshot without overwriting another project's job, and restores its result on return", async () => {
  const h = exportHarness(), a = h.store.getState(), started = exportDeferred(), writing = exportDeferred(), writes = [];
  const running = __test.runProjectExport(h.host, h.store, "tsv", {
    getExportTimestamp: () => "20261028030000", resolveProjectExportTarget: async () => "/exports/A.tsv",
    writeFinalPathExportTextFile: async payload => { writes.push(payload); started.resolve(); await writing.promise; },
  });
  await started.promise;
  const bJob = { projectName: "B", status: "running", marker: "must remain B" };
  h.store.setState({ session: { workspacePath: "/b", projectId: 8, projectName: "B" },
    projectExport: { projectId: 8, workspacePath: "/b", loaded: true, job: bJob } });
  const bData = h.store.getState().projectExport, paints = h.paints;
  writing.resolve(); assert.equal(await running, true);
  assert.equal(h.store.getState().projectExport, bData); assert.equal(h.store.getState().projectExport.job, bJob);
  assert.equal(h.paints, paints, "A completion cannot repaint B");
  assert.equal(writes.length, 1); assert.match(writes[0].text, /Chr01/);
  h.store.setState({ ...a, projectExport: { projectId: null, loaded: false, loading: false } });
  assert.equal(currentProjectExportJob(h.store).status, "success");
  const loading = __test.loadProjectExportData(h.host, h.store, exportDataDeps(a.projectExport.finalPathByChr));
  assert.equal(h.store.getState().projectExport.job.status, "success");
  assert.equal(await loading, true);
  assert.deepEqual(h.store.getState().projectExport.job.completedOutputs, ["/exports/A_20261028030000.tsv"]);
});

test("one running export per project prevents duplicate pickers/writers without blocking other project ownership", async () => {
  const h = exportHarness(), started = exportDeferred(), writing = exportDeferred(); let picks = 0, writes = 0;
  const deps = { resolveProjectExportTarget: async () => { picks++; return "/exports/snapshot.tsv"; },
    writeFinalPathExportTextFile: async () => { writes++; started.resolve(); await writing.promise; } };
  const first = __test.runProjectExport(h.host, h.store, "tsv", deps); await started.promise;
  assert.equal(await __test.runProjectExport(h.host, h.store, "tsv", deps), false);
  assert.equal(picks, 1); assert.equal(writes, 1); writing.resolve(); assert.equal(await first, true);
});

test("project data generations reject obsolete success/failure after A-B-A, without mixing local paths or repainting", async () => {
  for (const fail of [false, true]) {
    const h = exportHarness(), original = h.store.getState(), firstList = exportDeferred();
    const first = __test.loadProjectExportData(h.host, h.store, { ...exportDataDeps({ Old: { chrName: "Old", segments: [] } }),
      listProjectChromosomes: () => firstList.promise });
    h.store.setState({ session: { workspacePath: "/b", projectId: 8 } });
    h.store.setState({ ...original, projectExport: { projectId: null, loaded: false } });
    const second = __test.loadProjectExportData(h.host, h.store, exportDataDeps({ Fresh: { chrName: "Fresh", mode: "segments", segments: [] } }));
    assert.equal(await second, true); const current = h.store.getState(), paints = h.paints;
    if (fail) firstList.reject(Error("obsolete failure")); else firstList.resolve({ items: [] });
    assert.equal(await first, false); assert.equal(h.store.getState(), current); assert.equal(h.paints, paints);
    assert.equal(current.projectExport.error, ""); assert.equal(current.projectExport.finalPathByChr.Old, undefined);
    assert.ok(current.projectExport.finalPathByChr.Fresh);
  }
});

function mutateProjectData(store, command = "bootstrap_project_assembly") {
  const state = store.getState(), args = { workspaceRoot: state.session.workspacePath, projectId: state.session.projectId };
  const operation = beginPreviewContentOperation(command, args);
  finishPreviewContentOperation(operation, command, {}, true);
}
const freshOverviewPaths = () => ({ Fresh: { chrName: "Fresh", mode: "segments", segments: [
  { segmentId: "fresh", type: "ctg", assemblyCtgId: 2, datasetName: "hifiasm", ctgName: "fresh_ctg", originId: "fresh_origin", overallLen: 1000, start: 1, end: 500 },
] } });

test("Project preload invalidates after bootstrap/content mutation and reloads rather than retaining a pre-bootstrap empty path", async () => {
  const h = exportHarness();
  h.store.setState({ activeRoute: "importer", projectExport: { ...h.store.getState().projectExport, chromosomes: [], finalPathByChr: {} } });
  assert.match(renderProjectPathOverview(h.store.getState()), /暂无可用的 Final Path/);
  const job = { status: "running", marker: "keep existing snapshot job" };
  h.store.setState({ projectExport: { ...h.store.getState().projectExport, job } });
  mutateProjectData(h.store);
  let reads = 0;
  const root = { addEventListener() {}, querySelectorAll: () => [], querySelector: selector => selector === "[data-project-path-overview]"
    ? { dataset: { projectPathOverview: JSON.stringify(["/tmp/ws", 7]) } } : null };
  bindProjectPathOverview(root, h.store, { ...exportDataDeps(freshOverviewPaths()), listProjectChromosomes: async () => { reads++; return { items: [] }; } });
  for (let i = 0; i < 30 && h.store.getState().projectExport.loading; i++) await new Promise(resolve => setImmediate(resolve));
  const data = h.store.getState().projectExport;
  assert.equal(reads, 1); assert.equal(data.loaded, true); assert.equal(data.job, job);
  assert.equal(data.mutationStamp, previewMutationStamp({ workspaceRoot: "/tmp/ws", projectId: 7 }));
  assert.match(renderProjectPathOverview(h.store.getState()), /data-project-export-jump-chr="Fresh"/);
  assert.equal(h.subscriptions, 1);
  for (let i = 0; i < 5; i++) h.store.setState({ projectExport: { ...h.store.getState().projectExport, job: { ...job, currentStep: String(i) } } });
  assert.equal(reads, 1, "job progress cannot reload content with an unchanged mutation stamp");
  mutateProjectData(h.store, "auto_assign_chr");
  h.store.setState({ assembly: { ...h.store.getState().assembly, summary: "mutation finished while Project stays open" } });
  for (let i = 0; i < 30 && h.store.getState().projectExport.loading; i++) await new Promise(resolve => setImmediate(resolve));
  assert.equal(reads, 2, "a completed mutation updates the mounted path surface without requiring route reentry");
  releaseProjectPathOverview(root); assert.equal(h.subscriptions, 0);
  mutateProjectData(h.store); h.store.setState({ assembly: { ...h.store.getState().assembly } });
  assert.equal(reads, 2, "unmounted surfaces have no retained data subscription");
});

test("data responses spanning a content mutation are discarded and retried before any loaded publication", async () => {
  const h = exportHarness(), first = exportDeferred(), published = [];
  const originalSet = h.store.setState; h.store.setState = patch => {
    originalSet(patch); if (patch.projectExport?.loaded) published.push(Object.keys(patch.projectExport.finalPathByChr));
  };
  let reads = 0, views = 0;
  const loading = __test.loadProjectExportData(h.host, h.store, { ...exportDataDeps({}),
    listProjectChromosomes: async () => { reads++; return reads === 1 ? first.promise : { items: [] }; },
    getProjectAssemblyViewState: async () => ({ finalPathByChr: ++views === 1 ? { Old: { chrName: "Old", segments: [] } } : freshOverviewPaths() }),
  });
  mutateProjectData(h.store, "auto_assign_chr"); first.resolve({ items: [] });
  assert.equal(await loading, true); assert.equal(reads, 2);
  assert.deepEqual(published, [["Fresh"]]);
  assert.equal(h.store.getState().projectExport.finalPathByChr.Old, undefined);
});

test("continuous content mutation settles with a bounded retry/error and can be explicitly refreshed", async () => {
  const h = exportHarness(); let reads = 0;
  assert.equal(await __test.loadProjectExportData(h.host, h.store, { ...exportDataDeps(freshOverviewPaths()),
    listProjectChromosomes: async () => { reads++; mutateProjectData(h.store, "auto_orient_contigs"); return { items: [] }; },
  }), false);
  assert.equal(reads, 3); assert.equal(h.store.getState().projectExport.loading, false);
  assert.match(h.store.getState().projectExport.error, /项目内容发生变化/);
  assert.equal(await __test.loadProjectExportData(h.host, h.store, exportDataDeps(freshOverviewPaths())), true);
  assert.equal(h.store.getState().projectExport.error, "");
});

test("export entry requires the same content freshness as the composite surface, not just matching project identity", async () => {
  const h = exportHarness(); mutateProjectData(h.store, "run_ctg_editor_action");
  let reads = 0; const outputs = [];
  const result = await __test.runProjectExport(h.host, h.store, "tsv", { ...exportDataDeps(freshOverviewPaths()),
    listProjectChromosomes: async () => { reads++; return { items: [] }; },
    resolveProjectExportTarget: async () => "/output/fresh.tsv",
    writeFinalPathExportTextFile: async payload => outputs.push(payload.text),
  });
  assert.equal(result, true, h.store.getState().projectExport.job?.error); assert.equal(reads, 1);
  assert.match(outputs[0], /fresh_ctg/); assert.doesNotMatch(outputs[0], /ptg1/);
});

test("Overview progress patches only the summary and neither renders nor replaces its independent Preview owner", () => {
  let value = createState(), previewReadsForbidden = false, previewsBound = 0, replaced = 0, parsed = "";
  const scoped = new Proxy(value, { get(target, key) { if (previewReadsForbidden && key === "projectPreview") assert.fail("summary patches must not render/read Preview models"); return target[key]; } });
  const preview = { addEventListener() {} }, nextSummary = {}, summary = { querySelectorAll: () => [], replaceWith(next) { assert.equal(next, nextSummary); replaced++; } };
  const page = { dataset: { overviewProject: JSON.stringify(["/tmp/ws", 7]) }, querySelector: selector => selector === "[data-overview-summary]" ? summary : null };
  const host = { addEventListener() {}, querySelectorAll: () => [],
    querySelector: selector => selector === "[data-overview-project]" ? page : selector === "[data-overview-summary]" ? summary : selector === "[data-overview-preview]" ? preview : null,
    set innerHTML(_html) { assert.fail("progress must not replace the composite route"); },
    ownerDocument: { createElement: () => ({ content: { querySelector: () => nextSummary }, set innerHTML(html) { parsed = html; } }) } };
  const store = { getState: () => scoped, setState() { assert.fail("already-fresh bind/paint should not mutate data"); } };
  bindProjectExportPage(host, store, { bindProjectPreviewPage() { previewsBound++; } });
  previewReadsForbidden = true;
  __test.rerender(host, store);
  assert.equal(replaced, 1); assert.equal(previewsBound, 1); assert.equal(host.querySelector("[data-overview-preview]"), preview);
  assert.match(parsed, /data-overview-summary/); assert.doesNotMatch(parsed, /data-overview-preview|project-preview-page/);
});


test("Overview toolbar download exports Preview through its own handler without opening the export menu", async () => {
  const value = createState();
  value.projectPreview = { loaded: true, modelVersion: PREVIEW_MODEL_VERSION, key: previewProjectKey(value),
    mutationStamp: previewMutationStamp({ workspaceRoot: value.session.workspacePath, projectId: value.session.projectId }),
    localSignature: previewOverrideSignature({}, {}), savedPathSignatures: {},
    cards: buildProjectPreviewModel({ chromosomes: [{ chrName: "Chr01", chrLength: 1000 }],
      ctgs: [{ assemblyCtgId: 1, name: "ptg1", datasetName: "hifiasm", totalLength: 1000, assignedChrName: "Chr01", anchorStart: 0 }],
      finalPathByChr: { Chr01: { segments: [{ type: "ctg", assemblyCtgId: 1, datasetName: "hifiasm", start: 1, end: 1000 }] } } }) };
  const h = exportHarness(value), listeners = new Map(), writes = [];
  const button = { disabled: true, closest: selector => selector === "[data-preview-download]" ? button : null };
  h.host.addEventListener = (name, fn) => listeners.set(name, [...(listeners.get(name) || []), fn]);
  h.host.querySelector = selector => selector === "[data-preview-download]" ? button : null;
  bindProjectExportPage(h.host, h.store, { preview: {
    pickSaveFilePath: async () => "D:/all-chromosomes.png",
    renderProjectPreviewPng: async snapshot => { assert.match(snapshot.svgMarkup, />Chr01</); return "PNG"; },
    writeFinalPathExportBinaryFile: async args => writes.push(args),
  } });
  assert.equal(button.disabled, false);
  for (const listener of listeners.get("click") || []) await listener({ target: button });
  assert.equal(writes.length, 1); assert.equal(writes[0].outputPath, "D:/all-chromosomes.png");
  assert.equal(h.store.getState().activeRoute, "projectExport"); assert.equal(h.paints, 0);
});

for (const locale of ["zh", "en"]) test(`Overview has compact identity groups and exactly one download action before Export (${locale})`, () => {
  const html = renderProjectExportPage(createState({ locale }));
  const toolbar = html.slice(0, html.indexOf('data-overview-preview'));
  assert.doesNotMatch(html, /<h[1-6][^>]*>(?:概览|Overview|预览|Preview)<|project-preview-heading|project-preview-subtitle|project-preview-legend/);
  assert.equal((html.match(/data-preview-download/g) || []).length, 1);
  assert.ok(toolbar.indexOf("data-preview-download") < toolbar.indexOf("data-project-export-toggle"));
  assert.match(toolbar, /<dl class="project-export-identity">/);
  assert.match(toolbar, /<dd data-app-tooltip="p1">p1<\/dd>/);
  assert.match(toolbar, /<dd data-app-tooltip="hifiasm">hifiasm<\/dd>/);
});

for (const locale of ["zh", "en"]) test(`Overview includes all configured auxiliary names in its single-line identity (${locale})`, () => {
  const state = createState({ locale });
  const name = 'Flye_Very_Long_Auxiliary_Name<&"';
  state.initializer.datasets.push({ datasetId: 2, name }, { datasetId: 3, name: "RagTag_MiXeD" });
  state.initializer.existingProjects[0].supportDatasetIds = [2, 3, 2, 1, -1, "invalid", 99];
  const html = renderProjectExportPage(state);
  const toolbar = html.slice(0, html.indexOf("data-overview-preview"));
  const label = locale === "zh" ? "辅助数据集" : "Auxiliary datasets";
  const names = "Flye_Very_Long_Auxiliary_Name&lt;&amp;&quot;, RagTag_MiXeD, ds-99";
  assert.ok(toolbar.includes(`<dt>${label}</dt><dd data-app-tooltip="${names}">${names.replaceAll("&quot;", '"')}</dd>`));
  assert.equal((toolbar.match(/class="project-export-identity-item"/g) || []).length, 3);
  assert.ok(toolbar.indexOf(locale === "zh" ? "<dt>项目" : "<dt>Project") < toolbar.indexOf(locale === "zh" ? "<dt>主数据集" : "<dt>Primary dataset"));
  assert.ok(toolbar.indexOf(locale === "zh" ? "<dt>主数据集" : "<dt>Primary dataset") < toolbar.indexOf(`<dt>${label}`));
});

for (const locale of ["zh", "en"]) test(`Overview reports no configured auxiliary datasets honestly (${locale})`, () => {
  const html = renderProjectExportPage(createState({ locale }));
  const toolbar = html.slice(0, html.indexOf("data-overview-preview"));
  assert.ok(toolbar.includes(locale === "zh" ? '<dt>辅助数据集</dt><dd data-app-tooltip="未配置">未配置</dd>'
    : '<dt>Auxiliary datasets</dt><dd data-app-tooltip="Not configured">Not configured</dd>'));
});

test("Overview identity never wraps, ellipsizes names and preserves fixed right-side actions", () => {
  const rule = selector => {
    const start = componentsCss.indexOf(`\n${selector} {`);
    assert.ok(start >= 0, `missing ${selector}`);
    return componentsCss.slice(componentsCss.indexOf("{", start), componentsCss.indexOf("}", start));
  };
  assert.match(rule(".project-export-head"), /flex-wrap:\s*nowrap[\s\S]*min-width:\s*0/);
  assert.match(rule(".project-export-identity"), /flex:\s*1 1 0[\s\S]*flex-wrap:\s*nowrap[\s\S]*overflow:\s*hidden/);
  assert.match(rule(".project-export-identity dd"), /overflow:\s*hidden[\s\S]*text-overflow:\s*ellipsis[\s\S]*white-space:\s*nowrap/);
  assert.match(rule(".project-export-head > .project-export-actions"), /flex:\s*0 0 auto[\s\S]*flex-wrap:\s*nowrap/);
});

test("Overview image download is borderless, Export-height and has enabled hover/active plus keyboard focus feedback", () => {
  assert.match(componentsCss, /\.project-export-head :is\(\.project-preview-download, \.final-path-export-toggle\)\s*\{[^}]*height:\s*2\.1429rem;[^}]*min-height:\s*2\.1429rem;/);
  assert.match(componentsCss, /\.project-export-head \.project-preview-download\s*\{[^}]*border:\s*0;[^}]*background:\s*transparent;[^}]*box-shadow:\s*none;/);
  assert.match(componentsCss, /\.project-export-head \.project-preview-download:hover:not\(:disabled\)\s*\{[^}]*background:[^}]*color:/);
  assert.match(componentsCss, /\.project-export-head \.project-preview-download:active:not\(:disabled\)\s*\{/);
  assert.match(componentsCss, /\.project-export-head \.project-preview-download:focus-visible\s*\{[^}]*outline:\s*2px solid/);
});
