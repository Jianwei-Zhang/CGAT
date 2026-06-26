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
const DEGAP_CLOSE_DELAY_MS = 400;
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
  if (runtime.panelOpen || !runtime.settingsPanelDismissed) {
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

function scrollDegapJobsToBottom(host) {
  const doc = host?.ownerDocument || globalThis.document;
  const scrollTarget = host?.querySelector?.("[data-degap-jobs-panel]")
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
  if (!workspaceRoot || !host?.querySelector?.("[data-degap-panel]")) {
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
  const previousSettings = getDegapState(store).settings;
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
    error: "",
  }, deps, { persist: true });
}

function openGlobalSettings(host, store, deps = {}) {
  updateDegapState(host, store, {
    panelOpen: true,
    error: "",
  }, deps);
}

function closeMenu(host, store, deps = {}) {
  const degap = getDegapState(store);
  if (!degap.menu) {
    return;
  }
  updateDegapState(host, store, { menu: null }, deps);
}

function openGapMenu(host, store, event, deps = {}) {
  const gapNode = event.target?.closest?.("[data-final-path-segment-type='gap']");
  if (!gapNode || !gapNode.closest?.("[data-degap-panel]")) {
    return false;
  }
  event.preventDefault();
  const graphRoot = gapNode.closest?.("[data-degap-graph]") || gapNode.closest?.("[data-degap-panel]");
  const rect = graphRoot?.getBoundingClientRect?.() || { left: 0, top: 0 };
  updateDegapState(host, store, {
    menu: {
      gapSegmentId: normalizeString(gapNode.dataset.finalPathSegmentId),
      chrName: normalizeString(gapNode.dataset.finalPathTargetChrName)
        || normalizeString(gapNode.closest?.("[data-final-path-target-chr-name]")?.dataset?.finalPathTargetChrName),
      x: Number(event.clientX || 0) - Number(rect.left || 0),
      y: Number(event.clientY || 0) - Number(rect.top || 0),
    },
    error: "",
  }, deps);
  return true;
}

function isDegapEndpointCtgSegment(segment) {
  return normalizeString(segment?.type).toLowerCase() !== "gap" && Number(segment?.assemblyCtgId || 0) > 0;
}

function resolveTerminalCtgSides(finalPathEntry, segmentId) {
  const normalizedSegmentId = normalizeString(segmentId);
  if (!normalizedSegmentId) {
    return [];
  }
  const segments = Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : [];
  const left = segments.find((segment) => isDegapEndpointCtgSegment(segment));
  const right = segments.slice().reverse().find((segment) => isDegapEndpointCtgSegment(segment));
  const sides = [];
  if (normalizeString(left?.segmentId) === normalizedSegmentId) {
    sides.push("left");
  }
  if (normalizeString(right?.segmentId) === normalizedSegmentId && normalizeString(right?.segmentId) !== normalizeString(left?.segmentId)) {
    sides.push("right");
  } else if (
    normalizeString(right?.segmentId) === normalizedSegmentId
    && normalizeString(right?.segmentId) === normalizeString(left?.segmentId)
  ) {
    sides.push("right");
  }
  return sides;
}

function openCtgEndMenu(host, store, event, deps = {}) {
  const ctgNode = event.target?.closest?.("[data-final-path-segment-type='ctg']");
  if (!ctgNode || !ctgNode.closest?.("[data-degap-panel]")) {
    return false;
  }
  const state = store.getState();
  const chrName = normalizeString(ctgNode.dataset.finalPathTargetChrName)
    || normalizeString(ctgNode.closest?.("[data-final-path-target-chr-name]")?.dataset?.finalPathTargetChrName);
  const finalPathEntry = resolveDegapMenuFinalPathEntry(state.assembly, { chrName });
  const endpointSides = resolveTerminalCtgSides(finalPathEntry, ctgNode.dataset.finalPathSegmentId);
  if (!endpointSides.length) {
    return false;
  }
  event.preventDefault();
  const graphRoot = ctgNode.closest?.("[data-degap-graph]") || ctgNode.closest?.("[data-degap-panel]");
  const rect = graphRoot?.getBoundingClientRect?.() || { left: 0, top: 0 };
  updateDegapState(host, store, {
    menu: {
      type: "ctg-end",
      chrName,
      segmentId: normalizeString(ctgNode.dataset.finalPathSegmentId),
      endpointSides,
      x: Number(event.clientX || 0) - Number(rect.left || 0),
      y: Number(event.clientY || 0) - Number(rect.top || 0),
    },
    error: "",
  }, deps);
  return true;
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

function addJobsForGap(host, store, action, deps = {}) {
  const state = store.getState();
  const degap = getDegapState(store);
  const finalPathEntry = resolveDegapMenuFinalPathEntry(state.assembly, degap.menu);
  const sides = action === "all" ? ["left", "right"] : [action === "right" ? "right" : "left"];
  try {
    const nextJobs = buildDegapJobsForGap({
      finalPathEntry,
      gapSegmentId: degap.menu?.gapSegmentId || "",
      sides,
      settings: degap.settings,
      stateOrLocale: state,
    });
    const duplicateJobs = findDuplicateDegapJobs(degap.jobs, nextJobs);
    if (duplicateJobs.length) {
      const duplicateLabels = duplicateJobs.map((job) => job.label || job.jobId).join(", ");
      updateDegapState(host, store, {
        menu: null,
        feedback: "",
        error: tAssembly(state, "degap.duplicateJob", { label: duplicateLabels }),
      }, deps, { persist: true });
      return;
    }
    updateDegapState(host, store, {
      jobs: mergeDegapJobs(degap.jobs, nextJobs),
      menu: null,
      feedback: "",
      error: "",
    }, deps, { persist: true });
    scrollDegapJobsToBottom(host);
  } catch (error) {
    updateDegapState(host, store, {
      menu: null,
      feedback: "",
      error: String(error?.message || error || ""),
    }, deps);
  }
}

function addTelseekerJobsForPathEnds(host, store, action, deps = {}) {
  const state = store.getState();
  const degap = getDegapState(store);
  const finalPathEntry = resolveDegapMenuFinalPathEntry(state.assembly, degap.menu);
  const entries = finalPathEntry ? [finalPathEntry] : [];
  const ends = action === "all" ? ["left", "right"] : [action === "right" ? "right" : "left"];
  try {
    const nextJobs = entries.flatMap((finalPathEntry) => buildTelseekerCtgJobsForFinalPath({
      finalPathEntry,
      ends,
      settings: degap.settings,
      stateOrLocale: state,
    }));
    const duplicateJobs = findDuplicateDegapJobs(degap.jobs, nextJobs);
    if (duplicateJobs.length) {
      const duplicateLabels = duplicateJobs.map((job) => job.label || job.jobId).join(", ");
      updateDegapState(host, store, {
        menu: null,
        feedback: "",
        error: tAssembly(state, "degap.duplicateJob", { label: duplicateLabels }),
      }, deps, { persist: true });
      return;
    }
    updateDegapState(host, store, {
      jobs: mergeDegapJobs(degap.jobs, nextJobs),
      menu: null,
      feedback: "",
      error: "",
    }, deps, { persist: true });
    scrollDegapJobsToBottom(host);
  } catch (error) {
    updateDegapState(host, store, {
      menu: null,
      feedback: "",
      error: String(error?.message || error || ""),
    }, deps);
  }
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
  updateDegapState(host, store, {
    jobs: degap.jobs.filter((job) => buildDegapJobKey(job) !== resolvedJobKey),
    expandedJobId: degap.expandedJobId === resolvedJobKey || degap.expandedJobId === job.jobId
      ? ""
      : degap.expandedJobId,
    feedback: tAssembly(state, "degap.jobRemoved"),
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

function updateScale(host, store, node, deps = {}) {
  const field = normalizeString(node?.dataset?.degapScaleField);
  if (!field) {
    return;
  }
  const degap = getDegapState(store);
  updateDegapState(host, store, {
    trackView: {
      ...degap.trackView,
      [field]: Number(node.value || 0),
    },
  }, deps);
}

function scheduleClose(host, key, callback) {
  clearTimeout(host[key]);
  host[key] = setTimeout(callback, DEGAP_CLOSE_DELAY_MS);
}

function cancelClose(host, key) {
  clearTimeout(host[key]);
  host[key] = null;
}

function setDegapScaleComboOpenState(comboNode, isOpen) {
  if (!comboNode) {
    return;
  }
  const input = comboNode.querySelector?.(".assembly-track-combo-input");
  const toggle = comboNode.querySelector?.("[data-track-combo-toggle]");
  const menu = comboNode.querySelector?.(".assembly-track-combo-menu");
  comboNode.classList.toggle("is-open", isOpen);
  input?.setAttribute("aria-expanded", isOpen ? "true" : "false");
  toggle?.setAttribute("aria-expanded", isOpen ? "true" : "false");
  menu?.classList.toggle("is-hidden", !isOpen);
}

function closeDegapScaleCombos(host, keepNode = null) {
  host.querySelectorAll?.("[data-degap-scale-combo-field]")?.forEach((comboNode) => {
    if (keepNode && comboNode === keepNode) {
      return;
    }
    setDegapScaleComboOpenState(comboNode, false);
  });
}

function syncDegapScaleComboSelection(comboNode, selectedValue) {
  comboNode?.querySelectorAll?.("[data-track-combo-option]")?.forEach((optionNode) => {
    const active = Number(optionNode.dataset.trackComboValue || 0) === Number(selectedValue);
    optionNode.classList.toggle("is-active", active);
    optionNode.setAttribute("aria-selected", active ? "true" : "false");
  });
}

export function bindDegapCard(host, store, deps = {}) {
  void ensureDegapWorkspaceSettingsLoaded(host, store, deps);
  if (typeof host?.addEventListener !== "function" || host[DEGAP_CARD_BOUND]) {
    return;
  }
  host.addEventListener("contextmenu", (event) => {
    if (openGapMenu(host, store, event, deps)) {
      return;
    }
    openCtgEndMenu(host, store, event, deps);
  });
  host.addEventListener("click", (event) => {
    const scaleCombo = event.target?.closest?.("[data-degap-scale-combo-field]");
    const scaleToggle = event.target?.closest?.("[data-degap-scale-combo-field] [data-track-combo-toggle]");
    if (scaleToggle) {
      event.preventDefault();
      const comboNode = scaleToggle.closest("[data-degap-scale-combo-field]");
      const isOpen = comboNode?.classList.contains("is-open");
      closeDegapScaleCombos(host, isOpen ? null : comboNode);
      setDegapScaleComboOpenState(comboNode, !isOpen);
      comboNode?.querySelector?.(".assembly-track-combo-input")?.focus?.();
      return;
    }
    const scaleOption = event.target?.closest?.("[data-degap-scale-combo-field] [data-track-combo-option]");
    if (scaleOption) {
      event.preventDefault();
      const comboNode = scaleOption.closest("[data-degap-scale-combo-field]");
      const input = comboNode?.querySelector?.("[data-degap-scale-field]");
      if (input) {
        input.value = scaleOption.dataset.trackComboValue || "";
        updateScale(host, store, input, deps);
        syncDegapScaleComboSelection(comboNode, input.value);
      }
      setDegapScaleComboOpenState(comboNode, false);
      input?.focus?.();
      return;
    }
    if (!scaleCombo) {
      closeDegapScaleCombos(host);
    }
    const settingsOpen = event.target?.closest?.("[data-degap-settings-open]");
    if (settingsOpen) {
      openGlobalSettings(host, store, deps);
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
    const gapAction = event.target?.closest?.("[data-degap-gap-action]");
    if (gapAction) {
      addJobsForGap(host, store, normalizeString(gapAction.dataset.degapGapAction), deps);
      return;
    }
    const telseekerAction = event.target?.closest?.("[data-degap-telseeker-action]");
    if (telseekerAction) {
      addTelseekerJobsForPathEnds(
        host,
        store,
        normalizeString(telseekerAction.dataset.degapTelseekerAction),
        deps,
      );
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
  host.addEventListener("change", (event) => {
    const scale = event.target?.closest?.("[data-degap-scale-field]");
    if (scale) {
      updateScale(host, store, scale, deps);
      syncDegapScaleComboSelection(scale.closest?.("[data-degap-scale-combo-field]"), scale.value);
    }
  });
  host.addEventListener("pointerover", (event) => {
    if (event.target?.closest?.("[data-degap-gap-menu]")) {
      cancelClose(host, "__degapMenuCloseTimer");
    }
  });
  host.addEventListener("pointerout", (event) => {
    const menu = event.target?.closest?.("[data-degap-gap-menu]");
    if (menu && !menu.contains(event.relatedTarget)) {
      scheduleClose(host, "__degapMenuCloseTimer", () => closeMenu(host, store, deps));
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
