import test from "node:test";
import assert from "node:assert/strict";

import {
  appendTimestampToOutputPath,
  bindFinalPathExport,
  buildDegapJobsDisplaySteps,
  buildFinalPathExportBaseName,
  buildTimestampedExportBaseName,
  formatExportTimestamp,
  buildViewportScopedSvgMarkup,
  buildFinalPathTsvText,
  closeFinalPathExportDialog,
  launchFinalPathExportJob,
  planFinalPathExportSteps,
  requestCancelFinalPathExport,
  renderFinalPathViewportPng,
  resolveFinalPathViewportSnapshot,
  runFinalPathExportJob,
  runFinalPathExportAction,
} from "../final-path-export-runtime.js";
import { FLOATING_MENU_CLOSE_DELAY_MS } from "../../floating-menu-runtime.js";

function createStore(state) {
  let currentState = state;
  return {
    getState() {
      return currentState;
    },
    setState(nextState) {
      currentState = {
        ...currentState,
        ...nextState,
      };
    },
  };
}

test("buildFinalPathExportBaseName uses project and chr labels", () => {
  assert.equal(
    buildFinalPathExportBaseName({ projectName: "project1", chrName: "Chr01" }),
    "project1_Chr01_path",
  );
});

test("export timestamp helpers append sortable timestamps before the extension", () => {
  assert.equal(
    formatExportTimestamp(new Date(2026, 3, 30, 20, 59, 30)),
    "20260430205930",
  );
  assert.equal(
    buildTimestampedExportBaseName("project1_Chr01_path", "20260430205930"),
    "project1_Chr01_path_20260430205930",
  );
  assert.equal(
    appendTimestampToOutputPath("D:\\Desktop\\GPM\\exports\\project1_Chr01_path.png", "20260430205930"),
    "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png",
  );
  assert.equal(
    appendTimestampToOutputPath("D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png", "20260430210000"),
    "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png",
  );
});

test("buildFinalPathTsvText emits fixed gap export semantics", () => {
  const tsv = buildFinalPathTsvText({
    segments: [
      {
        segmentId: "seg-1",
        type: "ctg",
        datasetName: "canu2",
        ctgName: "Ctg1914",
        originId: "tig00000001",
        overallLen: 43725274,
        start: 1,
        end: 43725274,
      },
      {
        segmentId: "seg-2",
        type: "gap",
        gapSizeBp: 100,
      },
    ],
  });

  assert.match(tsv, /#\tCtg\tOrigin ID\toverall_len\torient\tCtg_start\tCtg_end\tChr_start\tChr_end/);
  assert.match(tsv, /1\tcanu2_Ctg1914\ttig00000001\t43725274\t\+\t1\t43725274\t1\t43725274/);
  assert.match(tsv, /2\tGap\tNA\t100\tNA\t1\t100\t43725275\t43725374/);
});

test("buildFinalPathTsvText emits derived ref-segment names from bounded reference coordinates", () => {
  const tsv = buildFinalPathTsvText({
    segments: [
      {
        segmentId: "seg-1",
        type: "ctg",
        sourceKind: "ref_segment",
        assemblyCtgId: 9001,
        referenceChrId: 1,
        referenceChrName: "Chr01",
        datasetName: "",
        ctgName: "ref_Chr01:5201-5600",
        originId: "Chr01",
        overallLen: 5000,
        memberStartBp: 5101,
        memberEndBp: 10100,
        start: 101,
        end: 500,
      },
    ],
  });

  assert.match(tsv, /1\tref_Chr01:5201-5600\tChr01\t5000\t\+\t101\t500\t1\t400/);
});

test("resolveFinalPathViewportSnapshot reads the current visible graph viewport only", () => {
  const viewport = {
    clientWidth: 640,
    clientHeight: 154,
    scrollLeft: 320,
    scrollTop: 0,
  };
  const svg = {
    outerHTML: "<svg width=\"1600\" height=\"154\"></svg>",
  };

  assert.deepEqual(
    resolveFinalPathViewportSnapshot({ viewportNode: viewport, svgNode: svg }),
    {
      width: 640,
      height: 154,
      scrollLeft: 320,
      scrollTop: 0,
      svgMarkup: "<svg width=\"1600\" height=\"154\"></svg>",
    },
  );
});

test("buildViewportScopedSvgMarkup normalizes a standalone export svg namespace", () => {
  const scoped = buildViewportScopedSvgMarkup({
    width: 640,
    height: 154,
    scrollLeft: 320,
    scrollTop: 0,
    svgMarkup: "<svg width=\"1600\" height=\"154\" viewBox=\"0 0 1600 154\"><rect width=\"10\" height=\"10\" /></svg>",
  });

  assert.match(scoped, /xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
  assert.match(scoped, /viewBox="320 0 640 154"/);
  assert.match(scoped, /<style>[\s\S]*\.track-ctg\s*\{[\s\S]*fill:\s*#d2dfef;/);
  assert.match(scoped, /\.track-ctg\.is-ref(?:,\.track-ctg\.is-ref\.is-active)?\s*\{[\s\S]*fill:\s*#cfcfcf;[\s\S]*stroke:\s*#8e8e8e;/);
  assert.match(scoped, /\.track-ctg-label\.is-ref\s*\{[\s\S]*fill:\s*#4f4f4f;/);
  assert.match(scoped, /<rect[^>]*fill="#fff"/);
});

test("bindFinalPathExport toggles the menu and dispatches export actions", async () => {
  const menuNode = {
    hidden: true,
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
  const exportRoot = {
    querySelector(selector) {
      if (selector === "[data-final-path-export-menu]") {
        return menuNode;
      }
      if (selector === "[data-final-path-export-toggle]") {
        return toggleNode;
      }
      return null;
    },
  };
  const toggleNode = {
    dataset: {
      finalPathExportToggle: "true",
    },
    closest(selector) {
      if (selector === "[data-final-path-export]") {
        return exportRoot;
      }
      return null;
    },
    setAttribute(name, value) {
      this[name] = value;
    },
  };
  const actionNode = {
    dataset: {
      finalPathExportAction: "png",
    },
    closest(selector) {
      if (selector === "[data-final-path-export]") {
        return exportRoot;
      }
      return null;
    },
  };
  const listeners = new Map();
  const host = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const calls = [];
  const store = createStore({
    session: {
      projectName: "project1",
    },
    assembly: {
      selectedChrName: "Chr01",
    },
  });

  bindFinalPathExport(host, store, {
    exportFinalPathArtifacts: async (payload) => {
      calls.push(payload.kind);
    },
  });

  await listeners.get("click")({
    target: {
      closest(selector) {
        if (selector === "[data-final-path-export-toggle]") {
          return toggleNode;
        }
        return null;
      },
    },
  });
  assert.equal(menuNode.hidden, false);

  await listeners.get("click")({
    target: {
      closest(selector) {
        if (selector === "[data-final-path-export-toggle]") {
          return null;
        }
        if (selector === "[data-final-path-export-action]") {
          return actionNode;
        }
        return null;
      },
    },
  });

  assert.deepEqual(calls, ["png"]);
  assert.equal(menuNode.hidden, true);
  assert.equal(toggleNode["aria-expanded"], "false");
});

test("bindFinalPathExport closes the menu after leaving the export root", async () => {
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
        if (selector === "[data-final-path-export-menu]") {
          return menuNode;
        }
        if (selector === "[data-final-path-export-toggle]") {
          return toggleNode;
        }
        return null;
      },
    };
    const exportTarget = {
      closest(selector) {
        if (selector === "[data-final-path-export]") {
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
    };
    const store = createStore({
      assembly: {
        selectedChrName: "Chr01",
      },
    });

    bindFinalPathExport(host, store);

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

test("renderFinalPathViewportPng uses a higher-density canvas for clearer exports", async () => {
  const originalDocument = globalThis.document;
  const originalUrl = globalThis.URL;
  const originalBlob = globalThis.Blob;
  const originalImage = globalThis.Image;
  const canvasCalls = {
    scale: [],
    drawImage: [],
  };
  const canvas = {
    width: 0,
    height: 0,
    getContext() {
      return {
        scale(x, y) {
          canvasCalls.scale.push([x, y]);
        },
        clearRect() {},
        drawImage(...args) {
          canvasCalls.drawImage.push(args);
        },
      };
    },
    toDataURL() {
      return "data:image/png;base64,YWJj";
    },
  };

  globalThis.document = {
    createElement(tagName) {
      assert.equal(tagName, "canvas");
      return canvas;
    },
  };
  globalThis.URL = {
    createObjectURL() {
      return "blob:final-path";
    },
    revokeObjectURL() {},
  };
  globalThis.Blob = class FakeBlob {
    constructor(parts, options) {
      this.parts = parts;
      this.options = options;
    }
  };
  globalThis.Image = class FakeImage {
    set src(_value) {
      queueMicrotask(() => {
        this.onload?.();
      });
    }
  };

  try {
    const base64 = await renderFinalPathViewportPng({
      width: 320,
      height: 120,
      scrollLeft: 0,
      scrollTop: 0,
      svgMarkup: "<svg width=\"320\" height=\"120\"></svg>",
    });

    assert.equal(base64, "YWJj");
    assert.equal(canvas.width, 640);
    assert.equal(canvas.height, 240);
    assert.deepEqual(canvasCalls.scale, [[2, 2]]);
    assert.equal(canvasCalls.drawImage.length, 1);
  } finally {
    globalThis.document = originalDocument;
    globalThis.URL = originalUrl;
    globalThis.Blob = originalBlob;
    globalThis.Image = originalImage;
  }
});

test("bindFinalPathExport requests cancel for a running export dialog", async () => {
  const listeners = new Map();
  const host = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const store = createStore({
    assembly: {
      finalPathExportJob: {
        open: true,
        status: "running",
        completedOutputs: ["a.png"],
        cancelRequested: false,
      },
    },
  });
  let rerenderCount = 0;

  bindFinalPathExport(host, store, {
    rerender() {
      rerenderCount += 1;
    },
  });

  await listeners.get("click")({
    target: {
      closest(selector) {
        if (selector === "[data-final-path-export-close]") {
          return { dataset: { finalPathExportClose: "true" } };
        }
        return null;
      },
    },
  });

  assert.equal(store.getState().assembly.finalPathExportJob.cancelRequested, true);
  assert.deepEqual(store.getState().assembly.finalPathExportJob.completedOutputs, ["a.png"]);
  assert.equal(rerenderCount, 1);
});

test("bindFinalPathExport closes a finished export dialog", async () => {
  const listeners = new Map();
  const host = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const store = createStore({
    assembly: {
      finalPathExportJob: {
        open: true,
        status: "success",
        completedOutputs: ["a.png"],
      },
    },
  });
  let rerenderCount = 0;

  bindFinalPathExport(host, store, {
    rerender() {
      rerenderCount += 1;
    },
  });

  await listeners.get("click")({
    target: {
      closest(selector) {
        if (selector === "[data-final-path-export-close]") {
          return { dataset: { finalPathExportClose: "true" } };
        }
        return null;
      },
    },
  });

  assert.equal(store.getState().assembly.finalPathExportJob, null);
  assert.equal(rerenderCount, 1);
});

test("launchFinalPathExportJob surfaces raw non-runtime export errors", async () => {
  const store = createStore({
    session: {
      projectName: "project1",
    },
    assembly: {
      selectedChrName: "Chr05",
      finalPathByChr: {
        Chr05: {
          mode: "segments",
          chrName: "Chr05",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              assemblyCtgId: 101,
              datasetName: "hifiasm",
              ctgName: "ptg000001l",
              originId: "ptg000001l",
              overallLen: 100,
              start: 1,
              end: 100,
            },
          ],
        },
      },
    },
  });

  const ok = await launchFinalPathExportJob({
    host: {},
    store,
    kind: "png",
    deps: {
      resolveFinalPathExportTarget: async () => "D:\\Desktop\\exports\\project1_Chr05_path.png",
      runFinalPathExportStep: async () => {
        throw new Error("DEGAP PATH is required");
      },
      mapAssemblyError() {
        return {
          category: "invalid-params",
          rawMessage: "DEGAP PATH is required",
          userMessage: "装配操作参数无效，请检查当前选择后重试。",
        };
      },
    },
  });

  assert.equal(ok, false);
  assert.equal(store.getState().assembly.finalPathExportJob.status, "error");
  assert.equal(store.getState().assembly.finalPathExportJob.error, "DEGAP PATH is required");
});

test("runFinalPathExportAction writes the current graph viewport to a chosen PNG path", async () => {
  const writes = [];
  const host = {
    querySelector(selector) {
      if (selector === "[data-final-path-graph-viewport]") {
        return {
          clientWidth: 640,
          clientHeight: 154,
          scrollLeft: 320,
          scrollTop: 0,
        };
      }
      if (selector === "[data-final-path-graph-svg]") {
        return {
          outerHTML: "<svg width=\"1600\" height=\"154\"></svg>",
        };
      }
      return null;
    },
  };
  const store = createStore({
    session: {
      workspacePath: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      projectName: "project1",
    },
    assembly: {
      selectedChrName: "Chr01",
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              datasetName: "canu2",
              ctgName: "Ctg1914",
              originId: "tig00000001",
              overallLen: 43725274,
              start: 1,
              end: 43725274,
            },
          ],
        },
      },
    },
  });

  await runFinalPathExportAction({
    host,
    store,
    kind: "png",
    deps: {
      getExportTimestamp: () => "20260430205930",
      pickSaveFilePath: async () => "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png",
      renderFinalPathViewportPng: async () => "YWJj",
      writeFinalPathExportBinaryFile: async (payload) => {
        writes.push(payload);
      },
    },
  });

  assert.deepEqual(writes, [{
    outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png",
    bytesBase64: "YWJj",
    stateOrLocale: store.getState(),
  }]);
});

test("runFinalPathExportAction still exports PNG from table mode when graph DOM is absent", async () => {
  const writes = [];
  const host = {
    querySelector() {
      return null;
    },
  };
  const store = createStore({
    session: {
      workspacePath: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      projectName: "project1",
    },
    initializer: {
      datasets: [
        { datasetId: 11, name: "canu2" },
      ],
      existingProjects: [
        { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] },
      ],
    },
    assembly: {
      selectedChrName: "Chr01",
      finalPathViewMode: "table",
      finalPathTrackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
      },
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              datasetName: "canu2",
              ctgName: "Ctg1914",
              originId: "tig00000001",
              overallLen: 43725274,
              start: 1,
              end: 43725274,
            },
          ],
        },
      },
    },
  });

  await runFinalPathExportAction({
    host,
    store,
    kind: "png",
    deps: {
      getExportTimestamp: () => "20260430205930",
      pickSaveFilePath: async () => "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png",
      renderFinalPathViewportPng: async (snapshot) => {
        assert.match(String(snapshot.svgMarkup || ""), /^<svg[\s\S]*<\/svg>$/);
        assert.ok(Number(snapshot.width) > 0);
        assert.ok(Number(snapshot.height) > 0);
        return "YWJj";
      },
      writeFinalPathExportBinaryFile: async (payload) => {
        writes.push(payload);
      },
    },
  });

  assert.deepEqual(writes, [{
    outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png",
    bytesBase64: "YWJj",
    stateOrLocale: store.getState(),
  }]);
});

test("runFinalPathExportAction uses the measured graph viewport width when table mode falls back to a synthetic graph", async () => {
  const host = {
    querySelector() {
      return null;
    },
  };
  const store = createStore({
    session: {
      workspacePath: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      projectName: "project1",
    },
    initializer: {
      datasets: [
        { datasetId: 11, name: "canu2" },
      ],
      existingProjects: [
        { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] },
      ],
    },
    assembly: {
      selectedChrName: "Chr01",
      finalPathViewMode: "table",
      finalPathTrackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
      },
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              datasetName: "canu2",
              ctgName: "Ctg1914",
              originId: "tig00000001",
              overallLen: 43725274,
              start: 1,
              end: 43725274,
            },
          ],
        },
      },
    },
  });

  await runFinalPathExportAction({
    host,
    store,
    kind: "png",
    deps: {
      getExportTimestamp: () => "20260430205930",
      getMeasuredTrackViewportPx: () => 2048,
      pickSaveFilePath: async () => "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png",
      renderFinalPathViewportPng: async (snapshot) => {
        assert.equal(snapshot.width, 2048);
        assert.match(snapshot.svgMarkup, /\bx2="2048"/);
        return "YWJj";
      },
      writeFinalPathExportBinaryFile: async () => {},
    },
  });
});

test("runFinalPathExportAction prefers an offscreen DOM graph snapshot in table mode when document is available", async () => {
  const originalDocument = globalThis.document;
  const writes = [];
  const viewportNode = {
    clientWidth: 640,
    clientHeight: 154,
    scrollLeft: 120,
    scrollTop: 0,
  };
  const svgNode = {
    outerHTML: "<svg width=\"1600\" height=\"154\"></svg>",
  };
  const wrapper = {
    style: {},
    set innerHTML(value) {
      this._html = value;
    },
    get innerHTML() {
      return this._html || "";
    },
    querySelector(selector) {
      if (selector === "[data-final-path-graph-viewport]") {
        return viewportNode;
      }
      if (selector === "[data-final-path-graph-svg]") {
        return svgNode;
      }
      return null;
    },
    remove() {},
  };
  globalThis.document = {
    body: {
      appendChild() {},
      removeChild() {},
    },
    createElement(tagName) {
      assert.equal(tagName, "div");
      return wrapper;
    },
  };

  try {
    const host = {
      querySelector() {
        return null;
      },
    };
    const store = createStore({
      session: {
        workspacePath: "D:\\Desktop\\GPM\\ws1",
        projectId: 7,
        projectName: "project1",
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "canu2" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] },
        ],
      },
      assembly: {
        selectedChrName: "Chr01",
        finalPathViewMode: "table",
        finalPathTrackView: {
          minTickUnitKb: 10000,
          maxTickCount: 10,
        },
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                datasetName: "canu2",
                ctgName: "Ctg1914",
                originId: "tig00000001",
                overallLen: 43725274,
                start: 1,
                end: 43725274,
              },
            ],
          },
        },
      },
    });

    await runFinalPathExportAction({
      host,
      store,
      kind: "png",
      deps: {
        getExportTimestamp: () => "20260430205930",
        pickSaveFilePath: async () => "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png",
        renderFinalPathViewportPng: async (snapshot) => {
          assert.equal(snapshot.width, 640);
          assert.equal(snapshot.height, 154);
          assert.equal(snapshot.scrollLeft, 120);
          assert.equal(snapshot.svgMarkup, "<svg width=\"1600\" height=\"154\"></svg>");
          return "YWJj";
        },
        writeFinalPathExportBinaryFile: async (payload) => {
          writes.push(payload);
        },
      },
    });
  } finally {
    globalThis.document = originalDocument;
  }

  assert.equal(writes.length, 1);
});

test("runFinalPathExportAction sizes the synthetic graph from the live final-path card outer width so the right edge is not cropped", async () => {
  const originalDocument = globalThis.document;
  const liveCardOuterWidth = 2208;
  const liveCardBodyWidth = 2186;
  const wrapper = {
    style: {},
    set innerHTML(value) {
      this._html = value;
    },
    get innerHTML() {
      return this._html || "";
    },
    querySelector(selector) {
      if (selector === "[data-final-path-graph-viewport]") {
        const outerWidth = Number.parseInt(String(this.style.width || "0"), 10) || 0;
        return {
          clientWidth: Math.max(0, outerWidth - 160),
          clientHeight: 154,
          scrollLeft: 0,
          scrollTop: 0,
        };
      }
      if (selector === "[data-final-path-graph-svg]") {
        return {
          outerHTML: "<svg width=\"2050\" height=\"154\"></svg>",
        };
      }
      return null;
    },
    remove() {},
  };
  globalThis.document = {
    body: {
      appendChild() {},
      removeChild() {},
    },
    createElement(tagName) {
      assert.equal(tagName, "div");
      return wrapper;
    },
  };

  try {
    const host = {
      querySelector(selector) {
        if (selector === "[data-final-path-graph-viewport]" || selector === "[data-final-path-graph-svg]") {
          return null;
        }
        if (selector === ".final-path-card-body") {
          return {
            clientWidth: liveCardBodyWidth,
          };
        }
        if (selector === ".final-path-card") {
          return {
            clientWidth: liveCardOuterWidth - 2,
            getBoundingClientRect() {
              return { width: liveCardOuterWidth };
            },
          };
        }
        return null;
      },
    };
    const store = createStore({
      session: {
        workspacePath: "D:\\Desktop\\GPM\\ws1",
        projectId: 7,
        projectName: "project1",
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "canu2" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] },
        ],
      },
      assembly: {
        selectedChrName: "Chr01",
        finalPathViewMode: "table",
        finalPathTrackView: {
          minTickUnitKb: 10000,
          maxTickCount: 10,
        },
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                datasetName: "canu2",
                ctgName: "Ctg1914",
                originId: "tig00000001",
                overallLen: 43725274,
                start: 1,
                end: 43725274,
              },
            ],
          },
        },
      },
    });

    await runFinalPathExportAction({
      host,
      store,
      kind: "png",
      deps: {
        getExportTimestamp: () => "20260430205930",
        getMeasuredTrackViewportPx: () => 2048,
        pickSaveFilePath: async () => "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png",
        renderFinalPathViewportPng: async (snapshot) => {
          assert.equal(wrapper.style.width, `${liveCardOuterWidth}px`);
          assert.equal(snapshot.width, 2048);
          return "YWJj";
        },
        writeFinalPathExportBinaryFile: async () => {},
      },
    });
  } finally {
    globalThis.document = originalDocument;
  }
});

test("runFinalPathExportAction writes sibling PNG TSV and FASTA outputs for all export", async () => {
  const calls = [];
  const host = {
    querySelector(selector) {
      if (selector === "[data-final-path-graph-viewport]") {
        return {
          clientWidth: 640,
          clientHeight: 154,
          scrollLeft: 320,
          scrollTop: 0,
        };
      }
      if (selector === "[data-final-path-graph-svg]") {
        return {
          outerHTML: "<svg width=\"1600\" height=\"154\"></svg>",
        };
      }
      return null;
    },
  };
  const store = createStore({
    session: {
      workspacePath: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      projectName: "project1",
    },
    assembly: {
      selectedChrName: "Chr01",
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              datasetName: "canu2",
              ctgName: "Ctg1914",
              originId: "tig00000001",
              overallLen: 43725274,
              start: 1,
              end: 43725274,
            },
            {
              segmentId: "seg-2",
              type: "gap",
              gapSizeBp: 100,
            },
          ],
        },
      },
    },
  });

  await runFinalPathExportAction({
    host,
    store,
    kind: "all",
    deps: {
      getExportTimestamp: () => "20260430205930",
      pickDirectoryPath: async () => "D:\\Desktop\\GPM\\exports",
      renderFinalPathViewportPng: async () => "YWJj",
      writeFinalPathExportBinaryFile: async (payload) => {
        calls.push(["png", payload.outputPath]);
      },
      writeFinalPathExportTextFile: async (payload) => {
        calls.push(["tsv", payload.outputPath, payload.text]);
      },
      exportFinalPathFasta: async (payload) => {
        calls.push(["fasta", payload.outputPath]);
      },
    },
  });

  assert.deepEqual(calls, [
    ["png", "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png"],
    [
      "tsv",
      "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.tsv",
      "#\tCtg\tOrigin ID\toverall_len\torient\tCtg_start\tCtg_end\tChr_start\tChr_end\n1\tcanu2_Ctg1914\ttig00000001\t43725274\t+\t1\t43725274\t1\t43725274\n2\tGap\tNA\t100\tNA\t1\t100\t43725275\t43725374\n",
    ],
    [
      "tsv",
      "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.log",
      "primary_ctg_count\t\t\t\t\t\t\t\t0/0\nprimary_ctg_length\t\t\t\t\t\t\t\t0/0\nsection\tdataset\tctg\torigin_id\tstart\tend\tlength_bp\tused_by_chr\tcounted\nsupport\tcanu2\tCtg1914\ttig00000001\t1\t43725274\t43725274\t\ttrue\n",
    ],
    ["fasta", "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.fasta"],
  ]);
});

test("runFinalPathExportAction writes only sibling PNG and TSV outputs for all export when fasta is unavailable", async () => {
  const calls = [];
  const host = {
    querySelector(selector) {
      if (selector === "[data-final-path-graph-viewport]") {
        return {
          clientWidth: 640,
          clientHeight: 154,
          scrollLeft: 320,
          scrollTop: 0,
        };
      }
      if (selector === "[data-final-path-graph-svg]") {
        return {
          outerHTML: "<svg width=\"1600\" height=\"154\"></svg>",
        };
      }
      return null;
    },
  };
  const store = createStore({
    session: {
      workspacePath: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      projectName: "project1",
    },
    initializer: {
      datasets: [
        { datasetId: 3, name: "canu2", label: "canu2", fastaAvailable: false },
      ],
      existingProjects: [
        {
          projectId: 7,
          projectName: "project1",
          primaryDatasetId: 3,
          supportDatasetIds: [],
        },
      ],
    },
    assembly: {
      selectedChrName: "Chr01",
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              datasetName: "canu2",
              ctgName: "Ctg1914",
              originId: "tig00000001",
              overallLen: 43725274,
              start: 1,
              end: 43725274,
            },
          ],
        },
      },
    },
  });

  await runFinalPathExportAction({
    host,
    store,
    kind: "all",
    deps: {
      getExportTimestamp: () => "20260430205930",
      pickDirectoryPath: async () => "D:\\Desktop\\GPM\\exports",
      renderFinalPathViewportPng: async () => "YWJj",
      writeFinalPathExportBinaryFile: async (payload) => {
        calls.push(["png", payload.outputPath]);
      },
      writeFinalPathExportTextFile: async (payload) => {
        calls.push(["tsv", payload.outputPath]);
      },
      exportFinalPathFasta: async (payload) => {
        calls.push(["fasta", payload.outputPath]);
      },
    },
  });

  assert.deepEqual(calls, [
    ["png", "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png"],
    [
      "tsv",
      "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.tsv",
    ],
    [
      "tsv",
      "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.log",
    ],
  ]);
});

test("runFinalPathExportAction omits log from all export when final path contains ref segments", async () => {
  const calls = [];
  const host = {
    querySelector(selector) {
      if (selector === "[data-final-path-graph-viewport]") {
        return {
          clientWidth: 640,
          clientHeight: 154,
          scrollLeft: 0,
          scrollTop: 0,
        };
      }
      if (selector === "[data-final-path-graph-svg]") {
        return {
          outerHTML: "<svg width=\"640\" height=\"154\"></svg>",
        };
      }
      return null;
    },
  };
  const store = createStore({
    session: {
      workspacePath: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      projectName: "project1",
    },
    initializer: {
      datasets: [
        { datasetId: 3, name: "hifiasm", label: "hifiasm", fastaAvailable: false },
      ],
      existingProjects: [
        {
          projectId: 7,
          projectName: "project1",
          primaryDatasetId: 3,
          supportDatasetIds: [],
        },
      ],
    },
    assembly: {
      selectedChrName: "Chr01",
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "ref-1",
              type: "ctg",
              sourceKind: "ref_segment",
              ctgName: "ref_Chr01:1-100",
              originId: "Chr01",
              overallLen: 100,
              start: 1,
              end: 100,
            },
          ],
        },
      },
    },
  });

  await runFinalPathExportAction({
    host,
    store,
    kind: "all",
    deps: {
      getExportTimestamp: () => "20260430205930",
      pickDirectoryPath: async () => "D:\\Desktop\\GPM\\exports",
      renderFinalPathViewportPng: async () => "YWJj",
      writeFinalPathExportBinaryFile: async (payload) => {
        calls.push(["png", payload.outputPath]);
      },
      writeFinalPathExportTextFile: async (payload) => {
        calls.push(["text", payload.outputPath]);
      },
      exportFinalPathFasta: async (payload) => {
        calls.push(["fasta", payload.outputPath]);
      },
    },
  });

  assert.deepEqual(calls, [
    ["png", "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png"],
    ["text", "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.tsv"],
  ]);
});

test("runFinalPathExportAction keeps FASTA export for partitioned full packages when datasets report fastaAvailable", async () => {
  const calls = [];
  const host = {
    querySelector(selector) {
      if (selector === "[data-final-path-graph-viewport]") {
        return {
          clientWidth: 640,
          clientHeight: 154,
          scrollLeft: 0,
          scrollTop: 0,
        };
      }
      if (selector === "[data-final-path-graph-svg]") {
        return {
          outerHTML: "<svg width=\"640\" height=\"154\"></svg>",
        };
      }
      return null;
    },
  };
  const store = createStore({
    session: {
      workspacePath: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
      projectName: "project1",
    },
    initializer: {
      packageMetadata: {
        packageMode: "fast",
        sequenceLayout: "partitioned",
        preassignedChr: true,
        chrAssignmentMinCoveragePercent: 60,
        selfAlignmentScope: "chr_partition",
        crossAlignmentScope: "chr_partition",
      },
      datasets: [
        { datasetId: 3, name: "canu2", label: "canu2", fastaAvailable: true },
      ],
      existingProjects: [
        {
          projectId: 7,
          projectName: "project1",
          primaryDatasetId: 3,
          supportDatasetIds: [],
        },
      ],
    },
    assembly: {
      selectedChrName: "Chr01",
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              datasetName: "canu2",
              ctgName: "Ctg1914",
              originId: "tig00000001",
              overallLen: 43725274,
              start: 1,
              end: 43725274,
            },
          ],
          updatedAt: "1",
        },
      },
    },
  });

  await runFinalPathExportAction({
    host,
    store,
    kind: "all",
    deps: {
      getExportTimestamp: () => "20260430205930",
      pickDirectoryPath: async () => "D:\\Desktop\\GPM\\exports",
      renderFinalPathViewportPng: async () => "YWJj",
      writeFinalPathExportBinaryFile: async (payload) => {
        calls.push(["png", payload.outputPath]);
      },
      writeFinalPathExportTextFile: async (payload) => {
        calls.push(["tsv", payload.outputPath]);
      },
      exportFinalPathFasta: async (payload) => {
        calls.push(["fasta", payload.outputPath]);
      },
    },
  });

  assert.deepEqual(calls, [
    ["png", "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.png"],
    ["tsv", "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.tsv"],
    ["tsv", "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.log"],
    ["fasta", "D:\\Desktop\\GPM\\exports\\project1_Chr01_path_20260430205930.fasta"],
  ]);
});

test("planFinalPathExportSteps expands all export into png tsv fasta order", () => {
  assert.deepEqual(
    planFinalPathExportSteps({
      kind: "all",
      baseName: "project1_Chr01_path",
      targetPath: "D:\\Desktop\\GPM\\exports",
    }),
    [
      {
        kind: "png",
        label: "图(.png)",
        outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.png",
      },
      {
        kind: "tsv",
        label: "表(.tsv)",
        outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.tsv",
      },
      {
        kind: "log",
        label: "日志(.log)",
        outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.log",
      },
      {
        kind: "fasta",
        label: "序列(.fasta)",
        outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.fasta",
      },
    ],
  );
});

test("planFinalPathExportSteps expands all export into png tsv order when fasta is unavailable", () => {
  assert.deepEqual(
    planFinalPathExportSteps({
      kind: "all",
      baseName: "project1_Chr01_path",
      targetPath: "D:\\Desktop\\GPM\\exports",
      canExportFasta: false,
    }),
    [
      {
        kind: "png",
        label: "图(.png)",
        outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.png",
      },
      {
        kind: "tsv",
        label: "表(.tsv)",
        outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.tsv",
      },
      {
        kind: "log",
        label: "日志(.log)",
        outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.log",
      },
    ],
  );
});

test("planFinalPathExportSteps omits log when log export is unavailable", () => {
  assert.deepEqual(
    planFinalPathExportSteps({
      kind: "all",
      baseName: "project1_Chr01_path",
      targetPath: "D:\\Desktop\\GPM\\exports",
      canExportFasta: false,
      canExportLog: false,
    }),
    [
      {
        kind: "png",
        label: "图(.png)",
        outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.png",
      },
      {
        kind: "tsv",
        label: "表(.tsv)",
        outputPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.tsv",
      },
    ],
  );
  assert.deepEqual(
    planFinalPathExportSteps({
      kind: "log",
      baseName: "project1_Chr01_path",
      targetPath: "D:\\Desktop\\GPM\\exports\\project1_Chr01_path.log",
      canExportLog: false,
    }),
    [],
  );
});

test("buildDegapJobsDisplaySteps expands current chr DEGAP jobs for the export dialog", () => {
  const state = {
    assembly: {
      selectedChrName: "Chr01",
      degap: {
        jobs: [
          {
            jobType: "gapfiller",
            jobId: "CtgA_vs_CtgB_Left-job",
            chrName: "Chr01",
            side: "left",
            leftCtg: "CtgA",
            rightCtg: "CtgB",
            left: { assemblyCtgId: 301, start: 8, end: 5 },
            right: { assemblyCtgId: 302, start: 1, end: 4 },
          },
          {
            jobType: "telseeker_ctg",
            jobId: "telseeker_ctg_right_CtgB",
            chrName: "Chr01",
            endpointCtg: "CtgB",
            endpointEnd: "R",
            endpoint: { assemblyCtgId: 302, start: 1, end: 8 },
          },
          {
            jobType: "gapfiller",
            jobId: "CtgX_vs_CtgY_Left-job",
            chrName: "Chr02",
            side: "left",
            leftCtg: "CtgX",
            rightCtg: "CtgY",
            left: { assemblyCtgId: 401, start: 8, end: 5 },
            right: { assemblyCtgId: 402, start: 1, end: 4 },
          },
        ],
      },
    },
  };

  assert.deepEqual(buildDegapJobsDisplaySteps(state), [
    { id: "degap-prepare", kind: "degap-prepare", label: "prepare_degap_shared.sh" },
    {
      id: "degap-job:CtgA_vs_CtgB_Left-job",
      kind: "degap-job",
      label: "gapfiller left CtgA -> CtgB",
    },
    {
      id: "degap-job:telseeker_ctg_right_CtgB",
      kind: "degap-job",
      label: "telseeker-ctg right CtgB",
    },
    { id: "degap-manifest", kind: "degap-manifest", label: "jobs.tsv" },
  ]);
});

test("runFinalPathExportJob stops before the next step after cancel is requested", async () => {
  const updates = [];

  await runFinalPathExportJob({
    job: {
      kind: "all",
      chrName: "Chr01",
      steps: [
        { kind: "png", label: "图(.png)", outputPath: "a.png" },
        { kind: "tsv", label: "表(.tsv)", outputPath: "a.tsv" },
        { kind: "fasta", label: "序列(.fasta)", outputPath: "a.fasta" },
      ],
      completedOutputs: [],
      cancelRequested: false,
    },
    runStep: async (step, currentJob) => {
      updates.push(["step", step.kind]);
      if (step.kind === "png") {
        currentJob.cancelRequested = true;
      }
      return { outputPath: step.outputPath };
    },
    onUpdate: async (nextJob) => {
      updates.push(["status", nextJob.status, nextJob.currentStep, [...nextJob.completedOutputs]]);
    },
  });

  assert.deepEqual(updates, [
    ["status", "running", "图(.png)", []],
    ["step", "png"],
    ["status", "canceled", "图(.png)", ["a.png"]],
  ]);
});

test("runFinalPathExportJob records expanded DEGAP-JOBS outputs and completed step ids", async () => {
  const finalJob = await runFinalPathExportJob({
    job: {
      kind: "degap-jobs",
      chrName: "Chr01",
      steps: [
        { kind: "degap-jobs", label: "DEGAP-JOBS", outputPath: "D:\\exports\\degap" },
      ],
      completedOutputs: [],
      completedStepIds: [],
      cancelRequested: false,
    },
    runStep: async () => ({
      outputPaths: [
        "D:\\exports\\degap\\prepare_degap_shared.sh",
        "D:\\exports\\degap\\degap_jobs\\Chr01_gapfiller_left_CtgA_to_CtgB.sh",
        "D:\\exports\\degap\\jobs.tsv",
      ],
      completedStepIds: [
        "degap-prepare",
        "degap-job:CtgA_vs_CtgB_Left-job",
        "degap-manifest",
      ],
    }),
    onUpdate: async () => {},
  });

  assert.equal(finalJob.status, "success");
  assert.deepEqual(finalJob.completedOutputs, [
    "D:\\exports\\degap\\prepare_degap_shared.sh",
    "D:\\exports\\degap\\degap_jobs\\Chr01_gapfiller_left_CtgA_to_CtgB.sh",
    "D:\\exports\\degap\\jobs.tsv",
  ]);
  assert.deepEqual(finalJob.completedStepIds, [
    "degap-prepare",
    "degap-job:CtgA_vs_CtgB_Left-job",
    "degap-manifest",
  ]);
});

test("launchFinalPathExportJob opens no dialog when target picking is canceled", async () => {
  const stateChanges = [];
  const store = createStore({
    session: {
      projectName: "project1",
      workspacePath: "D:\\Desktop\\GPM\\ws1",
      projectId: 7,
    },
    assembly: {
      selectedChrName: "Chr01",
      finalPathByChr: {
        Chr01: {
          segments: [],
        },
      },
    },
  });
  store.setState = (nextState) => {
    stateChanges.push(nextState.assembly?.finalPathExportJob ?? null);
  };

  await launchFinalPathExportJob({
    host: {},
    store,
    kind: "png",
    deps: {
      resolveFinalPathExportTarget: async () => "",
    },
  });

  assert.deepEqual(stateChanges, []);
});

test("requestCancelFinalPathExport marks a running job without clearing completed outputs", () => {
  const nextAssembly = requestCancelFinalPathExport({
    finalPathExportJob: {
      open: true,
      status: "running",
      completedOutputs: ["a.png"],
      cancelRequested: false,
    },
  });

  assert.equal(nextAssembly.finalPathExportJob.cancelRequested, true);
  assert.deepEqual(nextAssembly.finalPathExportJob.completedOutputs, ["a.png"]);
});

test("closeFinalPathExportDialog clears a completed export job", () => {
  const nextAssembly = closeFinalPathExportDialog({
    finalPathExportJob: {
      open: true,
      status: "success",
      completedOutputs: ["a.png"],
    },
  });

  assert.equal(nextAssembly.finalPathExportJob, null);
});
