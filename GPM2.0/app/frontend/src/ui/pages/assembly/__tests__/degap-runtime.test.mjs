import test from "node:test";
import assert from "node:assert/strict";

import { bindDegapCard, buildDegapExportPayload } from "../degap-runtime.js";

function createStore(initialState) {
  let state = initialState;
  return {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
}

function createHost() {
  const listeners = {};
  return {
    listeners,
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
}

function createFakeTimerApi() {
  let now = 0;
  let nextId = 1;
  const timers = new Map();
  return {
    setTimeout(callback, delay) {
      const id = nextId += 1;
      timers.set(id, { callback, at: now + Number(delay || 0) });
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    advance(ms) {
      now += Number(ms || 0);
      Array.from(timers.entries())
        .filter(([, timer]) => timer.at <= now)
        .sort((left, right) => left[1].at - right[1].at)
        .forEach(([id, timer]) => {
          if (!timers.has(id)) {
            return;
          }
          timers.delete(id);
          timer.callback();
        });
    },
  };
}

function createDegapJob(jobId = "CtgA_vs_CtgB_Left-job") {
  return {
    jobId,
    label: "CtgA_vs_CtgB Left-job",
    left: { assemblyCtgId: 1, start: 1, end: 100 },
    right: { assemblyCtgId: 2, start: 1, end: 100 },
    baselineSettings: {
      degapPath: "/opt/DEGAP/bin/DEGAP.py",
      hifiReads: ["/reads/a.fq.gz"],
      gpmServerPath: "/srv/gpm_server",
      outRoot: "/srv/degap",
    },
    baselineOutPath: "/srv/degap/CtgA_vs_CtgB_Left-job",
  };
}

function createSettingsPanel(overrides = {}) {
  const values = {
    degapPath: "/opt/DEGAP/bin/DEGAP.py",
    hifiReads: "/reads/a.fq.gz",
    ontReads: "",
    gpmServerPath: "/srv/gpm_server",
    outRoot: "/srv/degap",
    thread: "20",
    kmerFilter: true,
    kmerSize: "41",
    kmerNum: "20",
    maximumExtensionRound: "30",
    maximumExtensionLength: "",
    filterDepthHifi: "",
    filterDepthOnt: "",
    remove: "2",
    edge: "500",
    motif: "TTAGGG",
    work: "1",
    telN: "100",
    telR: "0.6",
    telMm: "0",
    ...overrides,
  };
  return {
    querySelector(selector) {
      const field = String(selector || "").match(/^\[data-degap-setting-field="([^"]+)"\]$/)?.[1];
      if (!field || !Object.hasOwn(values, field)) {
        return null;
      }
      return field === "kmerFilter"
        ? { checked: values[field] === true }
        : { value: String(values[field]) };
    },
  };
}

function createStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
  };
}

function createSaveClickEvent() {
  return {
    target: {
      closest(selector) {
        return selector === "[data-degap-settings-save]" ? {} : null;
      },
    },
  };
}

test("bindDegapCard dismisses DEGAP toast feedback after 0.8 seconds", () => {
  const timerApi = createFakeTimerApi();
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  globalThis.setTimeout = timerApi.setTimeout;
  globalThis.clearTimeout = timerApi.clearTimeout;
  const job = createDegapJob();
  const store = createStore({
    session: {},
    assembly: {
      degap: {
        settingsPanelDismissed: true,
        jobs: [job],
      },
    },
  });
  const host = createHost();
  try {
    bindDegapCard(host, store, { rerender() {} });
    host.listeners.click({
      target: {
        closest(selector) {
          return selector === "[data-degap-job-reset]" ? { dataset: { degapJobId: job.jobId } } : null;
        },
      },
    });

    assert.equal(store.getState().assembly.degap.feedback, "任务已重置");
    timerApi.advance(799);
    assert.equal(store.getState().assembly.degap.feedback, "任务已重置");
    timerApi.advance(1);
    assert.equal(store.getState().assembly.degap.feedback, "");
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});

test("bindDegapCard saves one software-only global settings change without workspace persistence", async () => {
  const storage = createStorage();
  const panel = createSettingsPanel({ thread: "24" });
  const host = createHost();
  host.querySelector = (selector) => selector === "[data-degap-settings-panel]" ? panel : null;
  const store = createStore({
    session: {},
    assembly: {
      degap: {
        settingsPanelDismissed: false,
        panelOpen: true,
        settings: {
          degapPath: "/opt/DEGAP/bin/DEGAP.py",
          hifiReads: ["/reads/a.fq.gz"],
          gpmServerPath: "/srv/gpm_server",
          outRoot: "/srv/degap",
          thread: 20,
        },
      },
    },
  });
  let workspaceSaveCount = 0;

  bindDegapCard(host, store, {
    storage,
    rerender() {},
    async updateRuntimeSettings() {
      workspaceSaveCount += 1;
      throw new Error("workspace persistence should not run");
    },
  });
  host.listeners.click(createSaveClickEvent());
  await Promise.resolve();

  const degap = store.getState().assembly.degap;
  assert.equal(degap.settings.thread, 24);
  assert.equal(degap.panelOpen, false);
  assert.equal(degap.settingsPanelDismissed, true);
  assert.equal(workspaceSaveCount, 0);
  assert.match(storage.getItem("gpm_next:degap_software_settings"), /"thread":24/);
});

test("bindDegapCard persists workspace settings when a workspace-level field changes", async () => {
  const storage = createStorage();
  const panel = createSettingsPanel({ outRoot: "/srv/degap-next" });
  const host = createHost();
  host.querySelector = (selector) => selector === "[data-degap-settings-panel]" ? panel : null;
  const store = createStore({
    session: { workspacePath: "/workspace/demo" },
    assembly: {
      degap: {
        settingsPanelDismissed: false,
        panelOpen: true,
        settings: {
          degapPath: "/opt/DEGAP/bin/DEGAP.py",
          hifiReads: ["/reads/a.fq.gz"],
          gpmServerPath: "/srv/gpm_server",
          outRoot: "/srv/degap",
          thread: 20,
        },
      },
    },
  });
  const workspaceSaves = [];

  bindDegapCard(host, store, {
    storage,
    rerender() {},
    async updateRuntimeSettings(payload) {
      workspaceSaves.push(payload);
      return {};
    },
  });
  host.listeners.click(createSaveClickEvent());
  await Promise.resolve();

  assert.equal(workspaceSaves.length, 1);
  assert.equal(workspaceSaves[0].workspaceRoot, "/workspace/demo");
  assert.deepEqual(workspaceSaves[0].degapWorkspaceSettings, {
    hifiReads: ["/reads/a.fq.gz"],
    ontReads: [],
    gpmServerPath: "/srv/gpm_server",
    outRoot: "/srv/degap-next",
  });
  assert.equal(store.getState().assembly.degap.settings.outRoot, "/srv/degap-next");
});

test("buildDegapExportPayload backfills job software settings for reopened workspaces", () => {
  const job = createDegapJob();
  const payload = buildDegapExportPayload({
    session: {
      workspacePath: "D:\\Desktop\\example1",
      projectId: 5,
    },
    assembly: {
      selectedChrName: "Chr05",
      finalPathByChr: {
        Chr05: {
          chrName: "Chr05",
          segments: [],
        },
      },
      degap: {
        settings: {
          hifiReads: ["/home/xbzhang/hifi.fa"],
          ontReads: ["/home/xbzhang/ont.fa"],
          gpmServerPath: "/home/xbzhang/gpm_server",
          outRoot: "/home/xbzhang/cgat_main_out",
        },
        jobs: [
          {
            ...job,
            chrName: "Chr05",
            settings: {
              ...job.baselineSettings,
              hifiReads: ["/home/xbzhang/hifi.fa"],
              ontReads: ["/home/xbzhang/ont.fa"],
              gpmServerPath: "/home/xbzhang/gpm_server",
              outRoot: "/home/xbzhang/cgat_main_out",
            },
            baselineSettings: {
              ...job.baselineSettings,
              hifiReads: ["/home/xbzhang/hifi.fa"],
              ontReads: ["/home/xbzhang/ont.fa"],
              gpmServerPath: "/home/xbzhang/gpm_server",
              outRoot: "/home/xbzhang/cgat_main_out",
            },
            outPath: "/home/xbzhang/cgat_main_out/CtgA_vs_CtgB_Left-job",
            baselineOutPath: "/home/xbzhang/cgat_main_out/CtgA_vs_CtgB_Left-job",
          },
        ],
      },
    },
  });

  assert.equal(payload.workspaceRoot, "D:\\Desktop\\example1");
  assert.equal(payload.projectId, 5);
  assert.equal(payload.chrName, "Chr05");
  assert.equal(payload.settings.degapPath, "/opt/DEGAP/bin/DEGAP.py");
  assert.equal(payload.settings.outRoot, "/home/xbzhang/cgat_main_out");
  assert.equal(payload.jobs[0].settings.degapPath, "/opt/DEGAP/bin/DEGAP.py");
  assert.equal(payload.jobs[0].settings.outRoot, "/home/xbzhang/cgat_main_out");
  assert.equal(payload.jobs[0].outPath, "/home/xbzhang/cgat_main_out/CtgA_vs_CtgB_Left-job");
});

test("buildDegapExportPayload exports only current chromosome jobs", () => {
  const chr01Job = {
    ...createDegapJob("Chr01_gap_left"),
    chrName: "Chr01",
    outPath: "/srv/degap/Chr01_gap_left",
  };
  const chr02Job = {
    ...createDegapJob("Chr02_gap_left"),
    chrName: "Chr02",
    outPath: "/srv/degap/Chr02_gap_left",
  };
  const payload = buildDegapExportPayload({
    session: {
      workspacePath: "/workspace/demo",
      projectId: 7,
    },
    assembly: {
      selectedChrName: "Chr02",
      finalPathByChr: {
        Chr01: { chrName: "Chr01", segments: [] },
        Chr02: { chrName: "Chr02", segments: [] },
      },
      degap: {
        settings: {
          degapPath: "/opt/DEGAP/bin/DEGAP.py",
          hifiReads: ["/reads/a.fq.gz"],
          gpmServerPath: "/srv/gpm_server",
          outRoot: "/srv/degap",
        },
        jobs: [chr01Job, chr02Job],
      },
    },
  });

  assert.equal(payload.chrName, "Chr02");
  assert.deepEqual(payload.jobs.map((job) => job.jobId), ["Chr02_gap_left"]);
  assert.equal(payload.jobs[0].chrName, "Chr02");
});

test("buildDegapExportPayload scopes phased exports to the active haplotype final path", () => {
  const payload = buildDegapExportPayload({
    session: {
      workspacePath: "/workspace/demo",
      projectId: 7,
    },
    assembly: {
      selectedChrName: "Chr01",
      isChrPhased: true,
      activeFinalPathKey: "B",
      phasedChrTracks: [
        { haplotypeKey: "A", label: "Chr01A" },
        { haplotypeKey: "B", label: "Chr01B" },
      ],
      finalPathByChr: {
        Chr01A: { chrName: "Chr01A", segments: [] },
        Chr01B: { chrName: "Chr01B", segments: [] },
      },
      degap: {
        settings: {
          degapPath: "/opt/DEGAP/bin/DEGAP.py",
          hifiReads: ["/reads/a.fq.gz"],
          gpmServerPath: "/srv/gpm_server",
          outRoot: "/srv/degap",
        },
        jobs: [
          {
            ...createDegapJob("Chr01A_gap_left"),
            chrName: "Chr01A",
            outPath: "/srv/degap/Chr01A_gap_left",
          },
          {
            ...createDegapJob("Chr01B_gap_left"),
            chrName: "Chr01B",
            outPath: "/srv/degap/Chr01B_gap_left",
          },
        ],
      },
    },
  });

  assert.equal(payload.chrName, "Chr01B");
  assert.deepEqual(payload.jobs.map((job) => job.jobId), ["Chr01B_gap_left"]);
});

test("buildDegapExportPayload fails when current chromosome has no jobs", () => {
  assert.throws(
    () => buildDegapExportPayload({
      locale: "en",
      session: {
        workspacePath: "/workspace/demo",
        projectId: 7,
      },
      assembly: {
        selectedChrName: "Chr02",
        finalPathByChr: {
          Chr02: { chrName: "Chr02", segments: [] },
        },
        degap: {
          settings: {
            degapPath: "/opt/DEGAP/bin/DEGAP.py",
            hifiReads: ["/reads/a.fq.gz"],
            gpmServerPath: "/srv/gpm_server",
            outRoot: "/srv/degap",
          },
          jobs: [{
            ...createDegapJob("Chr01_gap_left"),
            chrName: "Chr01",
            outPath: "/srv/degap/Chr01_gap_left",
          }],
        },
      },
    }),
    /No DEGAP jobs configured for the current final path \(Chr02\)/,
  );
});

test("bindDegapCard does not collapse an expanded job editor on pointer leave", () => {
  const job = createDegapJob();
  const store = createStore({
    session: {},
    assembly: {
      degap: {
        settingsPanelDismissed: true,
        expandedJobId: job.jobId,
        jobs: [job],
      },
    },
  });
  const host = createHost();

  bindDegapCard(host, store, { rerender() {} });
  host.listeners.pointerout({
    target: {
      closest(selector) {
        return selector === ".degap-job-shell" ? { contains: () => false } : null;
      },
    },
    relatedTarget: null,
  });

  assert.equal(store.getState().assembly.degap.expandedJobId, job.jobId);
});

test("bindDegapCard creates All-mode gap jobs for the clicked haplotype final path", () => {
  const listeners = {};
  const host = {
    listeners,
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
    querySelector(selector) {
      if (selector === "[data-degap-jobs-panel]" || selector === "[data-degap-panel]") {
        return {
          scrollIntoView() {},
          closest() {
            return null;
          },
        };
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
  const store = createStore({
    session: {},
    assembly: {
      selectedChrName: "Chr01",
      isChrPhased: true,
      activeFinalPathKey: "__all__",
      phasedChrTracks: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A" },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B" },
      ],
      finalPathByChr: {
        Chr01A: {
          chrName: "Chr01A",
          segments: [
            { segmentId: "a-left", type: "ctg", assemblyCtgId: 1, ctgName: "A-left", overallLen: 100, start: 1, end: 100 },
            { segmentId: "gap-a", type: "gap", gapSizeBp: 20 },
            { segmentId: "a-right", type: "ctg", assemblyCtgId: 2, ctgName: "A-right", overallLen: 100, start: 1, end: 100 },
          ],
        },
        Chr01B: {
          chrName: "Chr01B",
          segments: [
            { segmentId: "b-left", type: "ctg", assemblyCtgId: 3, ctgName: "B-left", overallLen: 100, start: 1, end: 100 },
            { segmentId: "gap-b", type: "gap", gapSizeBp: 20 },
            { segmentId: "b-right", type: "ctg", assemblyCtgId: 4, ctgName: "B-right", overallLen: 100, start: 1, end: 100 },
          ],
        },
      },
      degap: {
        settingsPanelDismissed: true,
        settings: {
          degapPath: "/opt/DEGAP/bin/DEGAP.py",
          hifiReads: ["/reads/a.fq.gz"],
          gpmServerPath: "/srv/gpm_server",
          outRoot: "/srv/degap",
        },
        jobs: [],
      },
    },
  });
  const graphNode = {
    getBoundingClientRect() {
      return { left: 0, top: 0 };
    },
  };
  const panelNode = {};
  const gapNode = {
    dataset: {
      finalPathSegmentId: "gap-b",
      finalPathTargetChrName: "Chr01B",
    },
    closest(selector) {
      if (selector === "[data-degap-panel]") return panelNode;
      if (selector === "[data-degap-graph]") return graphNode;
      if (selector === "[data-final-path-target-chr-name]") {
        return { dataset: { finalPathTargetChrName: "Chr01B" } };
      }
      return null;
    },
  };

  bindDegapCard(host, store, { rerender() {}, persistDegapProjectState() {} });
  listeners.contextmenu({
    target: {
      closest(selector) {
        return selector === "[data-final-path-segment-type='gap']" ? gapNode : null;
      },
    },
    clientX: 10,
    clientY: 20,
    preventDefault() {},
  });
  listeners.click({
    target: {
      closest(selector) {
        return selector === "[data-degap-gap-action]"
          ? { dataset: { degapGapAction: "left" } }
          : null;
      },
    },
  });

  const jobs = store.getState().assembly.degap.jobs;
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].chrName, "Chr01B");
  assert.equal(jobs[0].leftCtg, "B-left");
  assert.equal(jobs[0].rightCtg, "B-right");
});

test("bindDegapCard creates All-mode telseeker jobs from the clicked haplotype endpoint ctg", () => {
  const listeners = {};
  const host = {
    listeners,
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
    querySelector(selector) {
      if (selector === "[data-degap-jobs-panel]" || selector === "[data-degap-panel]") {
        return {
          scrollIntoView() {},
          closest() {
            return null;
          },
        };
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
  const store = createStore({
    session: {},
    assembly: {
      selectedChrName: "Chr01",
      isChrPhased: true,
      activeFinalPathKey: "__all__",
      phasedChrTracks: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A" },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B" },
      ],
      finalPathByChr: {
        Chr01A: {
          chrName: "Chr01A",
          segments: [
            { segmentId: "a-left", type: "ctg", assemblyCtgId: 1, ctgName: "A-left", overallLen: 100, start: 1, end: 100 },
            { segmentId: "gap-a", type: "gap", gapSizeBp: 20 },
            { segmentId: "a-right", type: "ctg", assemblyCtgId: 2, ctgName: "A-right", overallLen: 100, start: 1, end: 100 },
          ],
        },
        Chr01B: {
          chrName: "Chr01B",
          segments: [
            { segmentId: "b-left", type: "ctg", assemblyCtgId: 3, ctgName: "B-left", overallLen: 100, start: 1, end: 100 },
            { segmentId: "gap-b", type: "gap", gapSizeBp: 20 },
            { segmentId: "b-right", type: "ctg", assemblyCtgId: 4, ctgName: "B-right", overallLen: 100, start: 100, end: 1 },
          ],
        },
      },
      degap: {
        settingsPanelDismissed: true,
        settings: {
          degapPath: "/opt/DEGAP/bin/DEGAP.py",
          hifiReads: ["/reads/a.fq.gz"],
          gpmServerPath: "/srv/gpm_server",
          outRoot: "/srv/degap",
        },
        jobs: [],
      },
    },
  });
  const graphNode = {
    getBoundingClientRect() {
      return { left: 0, top: 0 };
    },
  };
  const panelNode = {};
  const ctgNode = {
    dataset: {
      finalPathSegmentId: "b-right",
      finalPathTargetChrName: "Chr01B",
    },
    closest(selector) {
      if (selector === "[data-degap-panel]") return panelNode;
      if (selector === "[data-degap-graph]") return graphNode;
      if (selector === "[data-final-path-target-chr-name]") {
        return { dataset: { finalPathTargetChrName: "Chr01B" } };
      }
      return null;
    },
  };

  bindDegapCard(host, store, { rerender() {}, persistDegapProjectState() {} });
  listeners.contextmenu({
    target: {
      closest(selector) {
        return selector === "[data-final-path-segment-type='ctg']" ? ctgNode : null;
      },
    },
    clientX: 10,
    clientY: 20,
    preventDefault() {},
  });
  listeners.click({
    target: {
      closest(selector) {
        return selector === "[data-degap-telseeker-action]"
          ? { dataset: { degapTelseekerAction: "right" } }
          : null;
      },
    },
  });

  const jobs = store.getState().assembly.degap.jobs;
  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].jobType, "telseeker_ctg");
  assert.equal(jobs[0].chrName, "Chr01B");
  assert.equal(jobs[0].endpointCtg, "B-right");
  assert.equal(jobs[0].endpointEnd, "R");
  assert.deepEqual(jobs[0].endpoint, { assemblyCtgId: 4, start: 100, end: 1 });
});
