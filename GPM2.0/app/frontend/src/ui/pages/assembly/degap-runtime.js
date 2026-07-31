import {
  buildDegapJobKey,
  buildDegapDefaultJobOutPath,
  buildDegapExportJobs,
  buildDegapExportSettings,
  buildDegapJobsForGap,
  buildDegapProjectStateForPersistence,
  buildTelseekerCtgJobsForFinalPath,
  findDuplicateDegapJobs,
  mergeDegapJobs,
  normalizeDegapRuntimeState,
  normalizeDegapSettings,
  readDegapSoftwareSettings,
  resolveDegapTerminalCtgSides,
  resolveDegapExportSettings,
  validateDegapSettings,
  writeDegapSoftwareSettings,
} from "./degap-state.js";
import {
  getCurrentChrFinalPath,
  resolveCurrentFinalPathChrName,
} from "./final-path-state.js";
import {
  getRuntimeSettings,
  updateRuntimeSettings,
} from "../../../services/workflow-api.js";
import { tAssembly } from "./i18n.js";

const DEGAP_CARD_BOUND = Symbol("degapCardBound");
const DEGAP_TOAST_DISMISS_MS = 800;

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizeStringList(value) {
  return normalizeString(value).split(/[\n,;]+/).map(normalizeString).filter(Boolean);
}

function resolveDegapJobKeyFromNode(node) {
  return normalizeString(node?.dataset?.degapJobKey) || normalizeString(node?.dataset?.degapJobId);
}

function findDegapJobByKey(jobs, jobKey) {
  const normalizedKey = normalizeString(jobKey);
  return (Array.isArray(jobs) ? jobs : []).find((job) =>
    buildDegapJobKey(job) === normalizedKey || normalizeString(job.jobId) === normalizedKey,
  ) || null;
}

function getDegapState(store) {
  return normalizeDegapRuntimeState(store.getState()?.assembly?.degap);
}

function getDegapToastSignature(degap) {
  const runtime = normalizeDegapRuntimeState(degap);
  if (runtime.panelOpen) {
    return "";
  }
  return runtime.error ? `error:${runtime.error}` : runtime.feedback ? `feedback:${runtime.feedback}` : "";
}

function scheduleDegapToastDismiss(host, store, deps, signature) {
  if (!host) {
    return;
  }
  clearTimeout(host.__degapToastDismissTimer);
  if (!signature) {
    return;
  }
  const setTimeoutFn = globalThis.setTimeout || ((callback) => callback());
  host.__degapToastDismissTimer = setTimeoutFn(() => {
    if (getDegapToastSignature(getDegapState(store)) !== signature) {
      return;
    }
    updateDegapState(host, store, {
      feedback: "",
      error: "",
    }, deps);
  }, DEGAP_TOAST_DISMISS_MS);
}

function updateDegapState(host, store, patch, deps = {}, { persist = false } = {}) {
  const state = store.getState();
  const nextDegap = normalizeDegapRuntimeState({
    ...getDegapState(store),
    ...(typeof patch === "function" ? patch(getDegapState(store)) : patch),
  });
  store.setState({
    ...state,
    assembly: {
      ...state.assembly,
      degap: nextDegap,
      degapProjectState: buildDegapProjectStateForPersistence(nextDegap),
    },
  });
  deps.rerender?.(host, store);
  if (persist && typeof deps.persistDegapProjectState === "function") {
    void deps.persistDegapProjectState(host, store);
  }
  scheduleDegapToastDismiss(host, store, deps, getDegapToastSignature(nextDegap));
}

function getConfirm(deps = {}) {
  if (typeof deps.confirm === "function") {
    return deps.confirm;
  }
  return (message) => globalThis.window?.confirm?.(message) ?? false;
}

function scrollDegapJobsToBottom(host, chrName = "") {
  const doc = host?.ownerDocument || globalThis.document;
  const normalizedChrName = normalizeString(chrName);
  const matchingJobCard = Array.from(host?.querySelectorAll?.("[data-degap-job-card]") || [])
    .find((node) => normalizeString(node?.dataset?.degapJobCardChrName) === normalizedChrName);
  const scrollTarget = matchingJobCard
    || host?.querySelector?.("[data-degap-jobs-panel]")
    || host?.querySelector?.("[data-degap-panel]")
    || host;
  const scrollContainers = [
    scrollTarget?.closest?.(".stage-panel"),
    doc?.scrollingElement,
    doc?.documentElement,
    doc?.body,
  ].filter(Boolean);
  const applyScroll = () => {
    scrollTarget?.scrollIntoView?.({ block: "end" });
    scrollContainers.forEach((node) => {
      node.scrollTop = node.scrollHeight;
    });
  };
  const requestFrame = globalThis.requestAnimationFrame || ((callback) => globalThis.setTimeout(callback, 0));
  requestFrame(() => requestFrame(applyScroll));
}

function collectSettings(root, selectorName) {
  const readField = (field) => root.querySelector?.(`[${selectorName}="${field}"]`);
  return normalizeDegapSettings({
    degapPath: readField("degapPath")?.value || "",
    hifiReads: normalizeStringList(readField("hifiReads")?.value || ""),
    ontReads: normalizeStringList(readField("ontReads")?.value || ""),
    gpmServerPath: readField("gpmServerPath")?.value || "",
    outRoot: readField("outRoot")?.value || "",
    thread: readField("thread")?.value || "",
    kmerFilter: Boolean(readField("kmerFilter")?.checked),
    kmerSize: readField("kmerSize")?.value || "",
    kmerNum: readField("kmerNum")?.value || "",
    maximumExtensionRound: readField("maximumExtensionRound")?.value || "",
    maximumExtensionLength: readField("maximumExtensionLength")?.value || "",
    filterDepthHifi: readField("filterDepthHifi")?.value || "",
    filterDepthOnt: readField("filterDepthOnt")?.value || "",
    remove: readField("remove")?.value || "",
    edge: readField("edge")?.value || "",
    motif: readField("motif")?.value || "",
    work: readField("work")?.value || "",
    telN: readField("telN")?.value || "",
    telR: readField("telR")?.value || "",
    telMm: readField("telMm")?.value || "",
  });
}

function buildWorkspaceSettings(settings) {
  const normalized = normalizeDegapSettings(settings);
  return {
    hifiReads: normalized.hifiReads,
    ontReads: normalized.ontReads,
    gpmServerPath: normalized.gpmServerPath,
    outRoot: normalized.outRoot,
  };
}

function areWorkspaceSettingsEqual(left, right) {
  return JSON.stringify(buildWorkspaceSettings(left)) === JSON.stringify(buildWorkspaceSettings(right));
}

export async function ensureDegapWorkspaceSettingsLoaded(host, store, deps = {}) {
  const state = store.getState();
  const workspaceRoot = normalizeString(state?.session?.workspacePath);
  if (!workspaceRoot || !host?.querySelector?.("[data-degap-runtime]")) {
    return;
  }
  const degap = getDegapState(store);
  if (degap.loadedWorkspaceRoot === workspaceRoot || degap.loadingWorkspaceSettings) {
    return;
  }
  updateDegapState(host, store, {
    loadingWorkspaceSettings: true,
    error: "",
  }, deps);
  try {
    const softwareSettings = readDegapSoftwareSettings(deps.storage);
    const runtimeSettings = await (deps.getRuntimeSettings || getRuntimeSettings)({
      workspaceRoot,
      stateOrLocale: state,
    });
    const workspaceSettings = runtimeSettings?.degapWorkspaceSettings || {};
    updateDegapState(host, store, {
      settings: normalizeDegapSettings({
        ...softwareSettings,
        ...workspaceSettings,
      }),
      loadedWorkspaceRoot: workspaceRoot,
      loadingWorkspaceSettings: false,
    }, deps);
  } catch (error) {
    updateDegapState(host, store, {
      settings: normalizeDegapSettings(readDegapSoftwareSettings(deps.storage)),
      loadedWorkspaceRoot: workspaceRoot,
      loadingWorkspaceSettings: false,
      error: String(error?.message || error || ""),
    }, deps);
  }
}

async function saveGlobalSettings(host, store, deps = {}) {
  const panel = host.querySelector?.("[data-degap-settings-panel]");
  if (!panel) {
    return;
  }
  const state = store.getState();
  const currentDegap = getDegapState(store);
  const previousSettings = currentDegap.settings;
  const pendingJobIntent = currentDegap.pendingJobIntent;
  const settings = collectSettings(panel, "data-degap-setting-field");
  const validation = validateDegapSettings(settings, { stateOrLocale: state });
  if (validation) {
    updateDegapState(host, store, { error: validation, feedback: "" }, deps);
    return;
  }
  try {
    writeDegapSoftwareSettings(settings, deps.storage);
    if (!areWorkspaceSettingsEqual(previousSettings, settings)) {
      await (deps.updateRuntimeSettings || updateRuntimeSettings)({
        workspaceRoot: state.session?.workspacePath || "",
        degapWorkspaceSettings: buildWorkspaceSettings(settings),
        stateOrLocale: state,
      });
    }
    updateDegapState(host, store, {
      settings,
      panelOpen: false,
      settingsPanelDismissed: true,
      feedback: tAssembly(state, "degap.saveSuccess"),
      error: "",
    }, deps, { persist: true });
    if (pendingJobIntent) {
      createDegapJobFromIntent(host, store, pendingJobIntent, deps);
    }
  } catch (error) {
    updateDegapState(host, store, {
      error: String(error?.message || error || ""),
      feedback: "",
    }, deps);
  }
}

function closeGlobalSettings(host, store, deps = {}) {
  updateDegapState(host, store, {
    panelOpen: false,
    settingsPanelDismissed: true,
    pendingJobIntent: null,
    error: "",
  }, deps, { persist: true });
}

export function openDegapSettings(host, store, deps = {}) {
  updateDegapState(host, store, {
    panelOpen: true,
    pendingJobIntent: null,
    error: "",
  }, deps);
}

function resolveDegapMenuFinalPathEntry(assembly, menu) {
  const menuChrName = normalizeString(menu?.chrName);
  if (menuChrName) {
    const entry = assembly?.finalPathByChr?.[menuChrName];
    if (entry) {
      return entry;
    }
  }
  return getCurrentChrFinalPath(assembly);
}

function createDegapJobFromIntent(host, store, intent, deps = {}) {
  const state = store.getState();
  const degap = getDegapState(store);
  const finalPathEntry = resolveDegapMenuFinalPathEntry(state.assembly, intent);
  try {
    if (
      intent?.kind === "telseeker"
      && !resolveDegapTerminalCtgSides(finalPathEntry, intent.segmentId).includes(intent.endpointSide)
    ) {
      throw new Error(tAssembly(state, "degap.missingEndpointCtg"));
    }
    const nextJobs = intent?.kind === "telseeker"
      ? buildTelseekerCtgJobsForFinalPath({
        finalPathEntry,
        ends: [intent.endpointSide],
        settings: degap.settings,
        stateOrLocale: state,
      })
      : buildDegapJobsForGap({
        finalPathEntry,
        gapSegmentId: intent?.gapSegmentId || "",
        sides: [intent?.side === "right" ? "right" : "left"],
        settings: degap.settings,
        stateOrLocale: state,
      });
    const duplicateJobs = findDuplicateDegapJobs(degap.jobs, nextJobs);
    if (duplicateJobs.length) {
      const duplicateLabels = duplicateJobs.map((job) => job.label || job.jobId).join(", ");
      updateDegapState(host, store, {
        menu: null,
        pendingJobIntent: null,
        feedback: "",
        error: tAssembly(state, "degap.duplicateJob", { label: duplicateLabels }),
      }, deps, { persist: true });
      return false;
    }
    const chrName = normalizeString(finalPathEntry?.chrName || intent?.chrName);
    const hadJobsForChr = degap.jobs.some((job) => normalizeString(job.chrName) === chrName);
    const collapsedJobCardChrNames = hadJobsForChr
      ? degap.collapsedJobCardChrNames
      : degap.collapsedJobCardChrNames.filter((item) => item !== chrName);
    updateDegapState(host, store, {
      jobs: mergeDegapJobs(degap.jobs, nextJobs),
      menu: null,
      pendingJobIntent: null,
      collapsedJobCardChrNames,
      feedback: tAssembly(state, "degap.jobAdded", { label: nextJobs[0]?.label || "" }),
      error: "",
    }, deps, { persist: true });
    scrollDegapJobsToBottom(host, chrName);
    return true;
  } catch (error) {
    updateDegapState(host, store, {
      menu: null,
      pendingJobIntent: null,
      feedback: "",
      error: String(error?.message || error || ""),
    }, deps);
    return false;
  }
}

function requestDegapJobIntent(host, store, intent, deps = {}) {
  const state = store.getState();
  const degap = getDegapState(store);
  const validation = validateDegapSettings(degap.settings, { stateOrLocale: state });
  if (validation) {
    updateDegapState(host, store, {
      menu: null,
      pendingJobIntent: intent,
      panelOpen: true,
      feedback: "",
      error: validation,
    }, deps);
    return false;
  }
  return createDegapJobFromIntent(host, store, intent, deps);
}

export function requestDegapGapJob(host, store, payload, deps = {}) {
  return requestDegapJobIntent(host, store, {
    kind: "gapfiller",
    chrName: normalizeString(payload?.chrName),
    gapSegmentId: normalizeString(payload?.gapSegmentId),
    side: normalizeString(payload?.side).toLowerCase() === "right" ? "right" : "left",
  }, deps);
}

export function requestDegapTelseekerJob(host, store, payload, deps = {}) {
  return requestDegapJobIntent(host, store, {
    kind: "telseeker",
    chrName: normalizeString(payload?.chrName),
    segmentId: normalizeString(payload?.segmentId),
    endpointSide: normalizeString(payload?.endpointSide).toLowerCase() === "right" ? "right" : "left",
  }, deps);
}

async function removeJob(host, store, jobKey, deps = {}) {
  const degap = getDegapState(store);
  const job = findDegapJobByKey(degap.jobs, jobKey);
  if (!job) {
    return;
  }
  const resolvedJobKey = buildDegapJobKey(job);
  const confirm = getConfirm(deps);
  const state = store.getState();
  if (!(await confirm(tAssembly(state, "degap.confirmRemoveJob", { label: job.label || job.jobId }), { host, store }))) {
    return;
  }
  const nextJobs = degap.jobs.filter((item) => buildDegapJobKey(item) !== resolvedJobKey);
  const chrName = normalizeString(job.chrName);
  const hasJobsForChr = nextJobs.some((item) => normalizeString(item.chrName) === chrName);
  updateDegapState(host, store, {
    jobs: nextJobs,
    collapsedJobCardChrNames: hasJobsForChr
      ? degap.collapsedJobCardChrNames
      : degap.collapsedJobCardChrNames.filter((item) => item !== chrName),
    expandedJobId: degap.expandedJobId === resolvedJobKey || degap.expandedJobId === job.jobId
      ? ""
      : degap.expandedJobId,
    feedback: tAssembly(state, "degap.jobRemoved"),
    error: "",
  }, deps, { persist: true });
}

function toggleJobCard(host, store, chrName, deps = {}) {
  const normalizedChrName = normalizeString(chrName);
  if (!normalizedChrName) {
    return;
  }
  const degap = getDegapState(store);
  const collapsed = degap.collapsedJobCardChrNames.includes(normalizedChrName);
  const collapsedJobCardChrNames = collapsed
    ? degap.collapsedJobCardChrNames.filter((item) => item !== normalizedChrName)
    : [...degap.collapsedJobCardChrNames, normalizedChrName];
  updateDegapState(host, store, {
    collapsedJobCardChrNames,
    error: "",
  }, deps, { persist: true });
}

function toggleJob(host, store, jobKey, deps = {}) {
  const degap = getDegapState(store);
  const job = findDegapJobByKey(degap.jobs, jobKey);
  const resolvedJobKey = job ? buildDegapJobKey(job) : normalizeString(jobKey);
  updateDegapState(host, store, {
    expandedJobId: degap.expandedJobId === resolvedJobKey || (job && degap.expandedJobId === job.jobId)
      ? ""
      : resolvedJobKey,
    error: "",
  }, deps);
}

function saveJob(host, store, jobKey, deps = {}) {
  const editor = Array.from(host.querySelectorAll?.("[data-degap-job-editor]") || [])
    .find((node) => resolveDegapJobKeyFromNode(node) === normalizeString(jobKey));
  if (!editor) {
    return;
  }
  const settings = collectSettings(editor, "data-degap-job-field");
  const outPath = normalizeString(editor.querySelector?.("[data-degap-job-field='outPath']")?.value);
  const state = store.getState();
  const validation = validateDegapSettings(settings, { requireOutRoot: false, stateOrLocale: state })
    || (!outPath ? tAssembly(state, "degap.validation.jobOutRequired") : "");
  if (validation) {
    updateDegapState(host, store, { error: validation, feedback: "" }, deps);
    return;
  }
  const degap = getDegapState(store);
  const job = findDegapJobByKey(degap.jobs, jobKey);
  const resolvedJobKey = job ? buildDegapJobKey(job) : normalizeString(jobKey);
  const baselineSettings = normalizeDegapSettings(degap.settings);
  const baselineOutPath = buildDegapDefaultJobOutPath(job, baselineSettings);
  updateDegapState(host, store, {
    jobs: degap.jobs.map((job) => buildDegapJobKey(job) === resolvedJobKey
      ? { ...job, settings, baselineSettings, outPath, baselineOutPath }
      : job),
    expandedJobId: "",
    feedback: tAssembly(state, "degap.jobSaved"),
    error: "",
  }, deps, { persist: true });
}

function resetJob(host, store, jobKey, deps = {}) {
  const degap = getDegapState(store);
  const state = store.getState();
  const job = findDegapJobByKey(degap.jobs, jobKey);
  const resolvedJobKey = job ? buildDegapJobKey(job) : normalizeString(jobKey);
  const baselineSettings = normalizeDegapSettings(degap.settings);
  const baselineOutPath = buildDegapDefaultJobOutPath(job, baselineSettings);
  updateDegapState(host, store, {
    jobs: degap.jobs.map((job) => buildDegapJobKey(job) === resolvedJobKey
      ? {
        ...job,
        settings: baselineSettings,
        baselineSettings,
        outPath: baselineOutPath,
        baselineOutPath,
      }
      : job),
    feedback: tAssembly(state, "degap.jobReset"),
    error: "",
  }, deps, { persist: true });
}

export function bindDegapCard(host, store, deps = {}) {
  void ensureDegapWorkspaceSettingsLoaded(host, store, deps);
  if (typeof host?.addEventListener !== "function" || host[DEGAP_CARD_BOUND]) {
    return;
  }
  host.addEventListener("click", (event) => {
    const settingsOpen = event.target?.closest?.("[data-degap-settings-open]");
    if (settingsOpen) {
      openDegapSettings(host, store, deps);
      return;
    }
    if (event.target?.closest?.("[data-degap-settings-close]")) {
      closeGlobalSettings(host, store, deps);
      return;
    }
    if (event.target?.closest?.("[data-degap-settings-save]")) {
      void saveGlobalSettings(host, store, deps);
      return;
    }
    const cardToggle = event.target?.closest?.("[data-degap-job-card-toggle]");
    if (cardToggle) {
      toggleJobCard(host, store, normalizeString(cardToggle.dataset.degapJobCardChrName), deps);
      return;
    }
    const remove = event.target?.closest?.("[data-degap-job-remove]");
    if (remove) {
      void removeJob(host, store, resolveDegapJobKeyFromNode(remove), deps);
      return;
    }
    const toggle = event.target?.closest?.("[data-degap-job-toggle]");
    if (toggle) {
      toggleJob(host, store, resolveDegapJobKeyFromNode(toggle), deps);
      return;
    }
    const save = event.target?.closest?.("[data-degap-job-save]");
    if (save) {
      saveJob(host, store, resolveDegapJobKeyFromNode(save), deps);
      return;
    }
    const reset = event.target?.closest?.("[data-degap-job-reset]");
    if (reset) {
      resetJob(host, store, resolveDegapJobKeyFromNode(reset), deps);
    }
  });
  host[DEGAP_CARD_BOUND] = true;
}

export function buildDegapExportPayload(state) {
  const degap = normalizeDegapRuntimeState(state?.assembly?.degap);
  const exportSettings = resolveDegapExportSettings(degap.settings, degap.jobs);
  const chrName = resolveCurrentFinalPathChrName(state?.assembly || {});
  const settingsError = validateDegapSettings(exportSettings, { stateOrLocale: state });
  if (settingsError) {
    throw new Error(settingsError);
  }
  const jobs = degap.jobs.filter((job) => normalizeString(job.chrName) === chrName);
  if (!jobs.length) {
    throw new Error(tAssembly(state, "degap.noJobsConfiguredForCurrentChr", { chrName }));
  }
  return {
    workspaceRoot: state?.session?.workspacePath || "",
    projectId: Number(state?.session?.projectId || 0),
    chrName,
    settings: buildDegapExportSettings(exportSettings),
    jobs: buildDegapExportJobs(jobs, exportSettings),
  };
}
