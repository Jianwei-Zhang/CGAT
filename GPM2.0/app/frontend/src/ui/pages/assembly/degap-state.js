import {
  isFinalPathCtgSegment,
  isFinalPathGapSegment,
  resolveFinalPathSegmentDisplayName,
} from "./final-path-state.js";
import { tAssembly } from "./i18n.js";

export const DEGAP_SOFTWARE_SETTINGS_STORAGE_KEY = "gpm_next:degap_software_settings";

export const DEFAULT_DEGAP_SETTINGS = Object.freeze({
  degapPath: "",
  hifiReads: [],
  ontReads: [],
  gpmServerPath: "",
  outRoot: "",
  thread: 20,
  kmerFilter: true,
  kmerSize: 41,
  kmerNum: 20,
  maximumExtensionRound: 30,
  maximumExtensionLength: "",
  filterDepthHifi: "",
  filterDepthOnt: "",
  remove: 2,
  edge: 500,
  motif: "TTAGGG",
  work: 1,
  telN: 100,
  telR: 0.6,
  telMm: 0,
});

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizeStringList(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeString).filter(Boolean);
  }
  return normalizeString(value)
    .split(/[\n,;]+/)
    .map(normalizeString)
    .filter(Boolean);
}

function normalizePositiveInt(value, fallback) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.trunc(numeric) : fallback;
}

function normalizeOptionalPositiveInt(value) {
  const text = normalizeString(value);
  if (!text) {
    return "";
  }
  const numeric = Number(text);
  return Number.isFinite(numeric) && numeric > 0 ? Math.trunc(numeric) : "";
}

function normalizeOptionalPositiveNumber(value) {
  const text = normalizeString(value);
  if (!text) {
    return "";
  }
  const numeric = Number(text);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : "";
}

function normalizeMotif(value, fallback = DEFAULT_DEGAP_SETTINGS.motif) {
  const text = normalizeString(value).toUpperCase();
  return /^[ACGT]+$/.test(text) ? text : fallback;
}

function normalizeTelMm(value) {
  const numeric = Number(value);
  return numeric === 1 ? 1 : 0;
}

function normalizeJobType(value) {
  const normalized = normalizeString(value).toLowerCase().replace(/-/g, "_");
  return normalized === "telseeker_ctg" ? "telseeker_ctg" : "gapfiller";
}

export function normalizeDegapSettings(value = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    ...DEFAULT_DEGAP_SETTINGS,
    degapPath: normalizeString(source.degapPath ?? DEFAULT_DEGAP_SETTINGS.degapPath),
    hifiReads: normalizeStringList(source.hifiReads ?? DEFAULT_DEGAP_SETTINGS.hifiReads),
    ontReads: normalizeStringList(source.ontReads ?? DEFAULT_DEGAP_SETTINGS.ontReads),
    gpmServerPath: normalizeString(source.gpmServerPath ?? DEFAULT_DEGAP_SETTINGS.gpmServerPath),
    outRoot: normalizeString(source.outRoot ?? DEFAULT_DEGAP_SETTINGS.outRoot),
    thread: normalizePositiveInt(source.thread, DEFAULT_DEGAP_SETTINGS.thread),
    kmerFilter: source.kmerFilter === false ? false : true,
    kmerSize: normalizePositiveInt(source.kmerSize, DEFAULT_DEGAP_SETTINGS.kmerSize),
    kmerNum: normalizePositiveInt(source.kmerNum, DEFAULT_DEGAP_SETTINGS.kmerNum),
    maximumExtensionRound:
      normalizeOptionalPositiveInt(source.maximumExtensionRound) || DEFAULT_DEGAP_SETTINGS.maximumExtensionRound,
    maximumExtensionLength: normalizeOptionalPositiveInt(source.maximumExtensionLength),
    filterDepthHifi: normalizeOptionalPositiveNumber(source.filterDepthHifi),
    filterDepthOnt: normalizeOptionalPositiveNumber(source.filterDepthOnt),
    remove: normalizePositiveInt(source.remove, DEFAULT_DEGAP_SETTINGS.remove),
    edge: normalizePositiveInt(source.edge, DEFAULT_DEGAP_SETTINGS.edge),
    motif: normalizeMotif(source.motif ?? DEFAULT_DEGAP_SETTINGS.motif),
    work: normalizePositiveInt(source.work, DEFAULT_DEGAP_SETTINGS.work),
    telN: normalizePositiveInt(source.telN, DEFAULT_DEGAP_SETTINGS.telN),
    telR: normalizeOptionalPositiveNumber(source.telR) || DEFAULT_DEGAP_SETTINGS.telR,
    telMm: normalizeTelMm(source.telMm ?? DEFAULT_DEGAP_SETTINGS.telMm),
  };
}

export function normalizeDegapProjectState(value = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    jobs: normalizeDegapJobs(source.jobs),
    settingsPanelDismissed: source.settingsPanelDismissed === true,
  };
}

export function normalizeDegapRuntimeState(value = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const projectState = normalizeDegapProjectState(source.projectState || source);
  return {
    settings: normalizeDegapSettings(source.settings),
    jobs: projectState.jobs,
    settingsPanelDismissed: projectState.settingsPanelDismissed,
    panelOpen: source.panelOpen === true,
    feedback: normalizeString(source.feedback),
    error: normalizeString(source.error),
    menu: source.menu && typeof source.menu === "object" ? source.menu : null,
    expandedJobId: normalizeString(source.expandedJobId),
    trackView: source.trackView && typeof source.trackView === "object" && !Array.isArray(source.trackView)
      ? source.trackView
      : {},
    loadedWorkspaceRoot: normalizeString(source.loadedWorkspaceRoot),
    loadingWorkspaceSettings: source.loadingWorkspaceSettings === true,
  };
}

export function buildDegapProjectStateForPersistence(degap) {
  const runtime = normalizeDegapRuntimeState(degap);
  return {
    jobs: runtime.jobs,
    settingsPanelDismissed: runtime.settingsPanelDismissed,
  };
}

function normalizeDegapJob(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const jobId = normalizeString(source.jobId);
  const jobType = normalizeJobType(source.jobType);
  const side = normalizeString(source.side).toLowerCase() === "right" ? "right" : "left";
  const endpointEnd = normalizeString(source.endpointEnd).toUpperCase() === "R" ? "R" : "L";
  const settings = source.settings && typeof source.settings === "object"
    ? normalizeDegapSettings(source.settings)
    : null;
  return {
    jobType,
    jobId,
    label: normalizeString(source.label) || jobId,
    chrName: normalizeString(source.chrName),
    gapSegmentId: normalizeString(source.gapSegmentId),
    gapIndex: Number.isFinite(Number(source.gapIndex)) ? Math.trunc(Number(source.gapIndex)) : 0,
    side,
    flag: side,
    leftCtg: normalizeString(source.leftCtg),
    rightCtg: normalizeString(source.rightCtg),
    outPath: normalizeString(source.outPath),
    baselineOutPath: normalizeString(source.baselineOutPath || source.outPath),
    left: normalizeSeedSegment(source.left),
    right: normalizeSeedSegment(source.right),
    endpointCtg: normalizeString(source.endpointCtg),
    endpointEnd,
    endpoint: normalizeSeedSegment(source.endpoint),
    settings,
    baselineSettings: normalizeDegapSettings(source.baselineSettings || settings || {}),
  };
}

export function normalizeDegapJobs(value) {
  return (Array.isArray(value) ? value : [])
    .map(normalizeDegapJob)
    .filter((job) => {
      if (!job.jobId) {
        return false;
      }
      if (job.jobType === "telseeker_ctg") {
        return job.endpoint.assemblyCtgId > 0 && job.endpointCtg && ["L", "R"].includes(job.endpointEnd);
      }
      return job.left.assemblyCtgId > 0 && job.right.assemblyCtgId > 0;
    })
    .sort(compareDegapJobs);
}

function normalizeSeedSegment(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    assemblyCtgId: normalizePositiveInt(source.assemblyCtgId, 0),
    start: normalizePositiveInt(source.start, 0),
    end: normalizePositiveInt(source.end, 0),
  };
}

function compareDegapJobs(left, right) {
  const chrDelta = normalizeString(left.chrName).localeCompare(normalizeString(right.chrName));
  if (chrDelta) {
    return chrDelta;
  }
  const gapDelta = Number(left.gapIndex || 0) - Number(right.gapIndex || 0);
  if (gapDelta) {
    return gapDelta;
  }
  const sideDelta = (left.side === "right" ? 1 : 0) - (right.side === "right" ? 1 : 0);
  if (sideDelta) {
    return sideDelta;
  }
  const typeDelta = normalizeString(left.jobType).localeCompare(normalizeString(right.jobType));
  if (typeDelta) {
    return typeDelta;
  }
  return left.jobId.localeCompare(right.jobId);
}

export function buildDegapJobKey(job) {
  const jobId = normalizeString(job?.jobId);
  const chrName = normalizeString(job?.chrName);
  const jobType = normalizeJobType(job?.jobType);
  const key = `${jobType}\t${jobId}`;
  return chrName ? `${chrName}\t${key}` : key;
}

function sanitizePathPart(value) {
  return normalizeString(value).replace(/[^A-Za-z0-9_.-]+/g, "_").replace(/^_+|_+$/g, "") || "degap_job";
}

function joinServerPath(root, child) {
  const base = normalizeString(root).replace(/\/+$/, "");
  const rel = normalizeString(child).replace(/^\/+/, "");
  if (!base) {
    return "";
  }
  return rel ? `${base}/${rel}` : base;
}

function buildJobId(leftName, rightName, side) {
  return `${sanitizePathPart(leftName)}_vs_${sanitizePathPart(rightName)}_${side === "right" ? "Right" : "Left"}-job`;
}

function buildJobLabel(leftName, rightName, side) {
  return `${leftName}_vs_${rightName} ${side === "right" ? "Right" : "Left"}-job`;
}

function buildTelseekerJobId(ctgName, endpointEnd) {
  const side = endpointEnd === "R" ? "right" : "left";
  return `telseeker_ctg_${side}_${sanitizePathPart(ctgName)}`;
}

function buildTelseekerJobLabel(ctgName, endpointEnd) {
  return `telseeker-ctg ${endpointEnd} ${ctgName}`;
}

function areDegapSettingValuesEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function isDegapSettingValueConfigured(value) {
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "string") {
    return normalizeString(value) !== "";
  }
  return value !== undefined && value !== null && value !== "";
}

function hasConfiguredDegapSettings(settings) {
  const normalized = normalizeDegapSettings(settings);
  return Boolean(
    normalized.degapPath
    || normalized.hifiReads.length
    || normalized.ontReads.length
    || normalized.gpmServerPath
    || normalized.outRoot
  );
}

export function buildDegapDefaultJobOutPath(job, globalSettings) {
  const normalizedSettings = normalizeDegapSettings(globalSettings);
  return joinServerPath(normalizedSettings.outRoot, job?.jobId);
}

export function resolveDegapJobOutPath(job, globalSettings) {
  const currentOutPath = normalizeString(job?.outPath);
  const baselineOutPath = normalizeString(job?.baselineOutPath);
  if (!hasConfiguredDegapSettings(globalSettings)) {
    return currentOutPath;
  }
  if (!currentOutPath || (baselineOutPath && currentOutPath === baselineOutPath)) {
    return buildDegapDefaultJobOutPath(job, globalSettings);
  }
  return currentOutPath;
}

export function resolveDegapJobSettings(job, globalSettings) {
  const inheritedSettings = normalizeDegapSettings(globalSettings);
  if (!job?.settings || typeof job.settings !== "object" || Array.isArray(job.settings)) {
    return inheritedSettings;
  }
  const jobSettings = normalizeDegapSettings(job.settings);
  if (!hasConfiguredDegapSettings(globalSettings)) {
    return jobSettings;
  }
  const baselineSettings = normalizeDegapSettings(job.baselineSettings || job.settings);
  const resolved = { ...inheritedSettings };
  Object.keys(DEFAULT_DEGAP_SETTINGS).forEach((field) => {
    if (
      !isDegapSettingValueConfigured(resolved[field])
      && isDegapSettingValueConfigured(jobSettings[field])
    ) {
      resolved[field] = jobSettings[field];
      return;
    }
    if (!areDegapSettingValuesEqual(jobSettings[field], baselineSettings[field])) {
      resolved[field] = jobSettings[field];
    }
  });
  return normalizeDegapSettings(resolved);
}

export function resolveDegapExportSettings(settings, jobs) {
  const resolved = normalizeDegapSettings(settings);
  normalizeDegapJobs(jobs).forEach((job) => {
    const jobSettings = resolveDegapJobSettings(job, resolved);
    Object.keys(DEFAULT_DEGAP_SETTINGS).forEach((field) => {
      if (
        !isDegapSettingValueConfigured(resolved[field])
        && isDegapSettingValueConfigured(jobSettings[field])
      ) {
        resolved[field] = jobSettings[field];
      }
    });
  });
  return normalizeDegapSettings(resolved);
}

function buildSeedFromSegment(segment) {
  return {
    assemblyCtgId: normalizePositiveInt(segment?.assemblyCtgId, 0),
    start: normalizePositiveInt(segment?.start, 0),
    end: normalizePositiveInt(segment?.end, 0),
  };
}

function isDegapCtgSegment(segment) {
  return isFinalPathCtgSegment(segment) && normalizePositiveInt(segment?.assemblyCtgId, 0) > 0;
}

function findNearestDegapCtgSegment(segments, startIndex, step) {
  for (let index = startIndex; index >= 0 && index < segments.length; index += step) {
    const segment = segments[index];
    if (isFinalPathGapSegment(segment)) {
      continue;
    }
    return isDegapCtgSegment(segment) ? { segment, index } : null;
  }
  return null;
}

export function buildDegapJobsForGap({
  finalPathEntry,
  gapSegmentId,
  sides,
  settings,
  stateOrLocale = "en",
}) {
  const segments = Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : [];
  const gapIndex = segments.findIndex(
    (segment, index) => {
      const segmentId = normalizeString(segment?.segmentId) || `seg-${index + 1}`;
      return isFinalPathGapSegment(segment)
        && (segmentId === normalizeString(gapSegmentId) || (!gapSegmentId && index >= 0));
    },
  );
  if (gapIndex < 0) {
    throw new Error(tAssembly(stateOrLocale, "degap.noGapSelected"));
  }
  const leftFlank = findNearestDegapCtgSegment(segments, gapIndex - 1, -1);
  const rightFlank = findNearestDegapCtgSegment(segments, gapIndex + 1, 1);
  if (!leftFlank || !rightFlank) {
    throw new Error(tAssembly(stateOrLocale, "degap.missingCtgFlanks"));
  }
  const leftSegment = leftFlank.segment;
  const rightSegment = rightFlank.segment;
  const leftName = resolveFinalPathSegmentDisplayName(leftSegment);
  const rightName = resolveFinalPathSegmentDisplayName(rightSegment);
  const normalizedSettings = normalizeDegapSettings(settings);
  const requestedSides = Array.isArray(sides) && sides.length ? sides : ["left"];
  return requestedSides.map((sideValue) => {
    const side = normalizeString(sideValue).toLowerCase() === "right" ? "right" : "left";
    const jobId = buildJobId(leftName, rightName, side);
    const outPath = joinServerPath(normalizedSettings.outRoot, jobId);
    return normalizeDegapJob({
      jobId,
      label: buildJobLabel(leftName, rightName, side),
      chrName: normalizeString(finalPathEntry?.chrName),
      gapSegmentId: normalizeString(segments[gapIndex]?.segmentId),
      gapIndex: leftFlank.index + 1,
      side,
      flag: side,
      leftCtg: leftName,
      rightCtg: rightName,
      outPath,
      baselineOutPath: outPath,
      left: buildSeedFromSegment(leftSegment),
      right: buildSeedFromSegment(rightSegment),
      settings: normalizedSettings,
      baselineSettings: normalizedSettings,
    });
  });
}

function findEndpointDegapCtgSegment(segments, direction) {
  const start = direction === "right" ? segments.length - 1 : 0;
  const step = direction === "right" ? -1 : 1;
  for (let index = start; index >= 0 && index < segments.length; index += step) {
    const segment = segments[index];
    if (isFinalPathGapSegment(segment)) {
      continue;
    }
    return isDegapCtgSegment(segment) ? { segment, index } : null;
  }
  return null;
}

export function buildTelseekerCtgJobsForFinalPath({
  finalPathEntry,
  ends,
  settings,
  stateOrLocale = "en",
}) {
  const segments = Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : [];
  const requestedEnds = Array.isArray(ends) && ends.length ? ends : ["left"];
  const normalizedSettings = normalizeDegapSettings({
    ...settings,
    filterDepthHifi: "",
    filterDepthOnt: "",
  });
  return requestedEnds.map((endValue) => {
    const direction = normalizeString(endValue).toLowerCase() === "right" ? "right" : "left";
    const endpoint = findEndpointDegapCtgSegment(segments, direction);
    if (!endpoint) {
      throw new Error(tAssembly(stateOrLocale, "degap.missingEndpointCtg"));
    }
    const endpointEnd = direction === "right" ? "R" : "L";
    const segment = endpoint.segment;
    const ctgName = resolveFinalPathSegmentDisplayName(segment);
    const jobId = buildTelseekerJobId(ctgName, endpointEnd);
    const outPath = joinServerPath(normalizedSettings.outRoot, jobId);
    return normalizeDegapJob({
      jobType: "telseeker_ctg",
      jobId,
      label: buildTelseekerJobLabel(ctgName, endpointEnd),
      chrName: normalizeString(finalPathEntry?.chrName),
      side: direction,
      flag: direction,
      endpointCtg: ctgName,
      endpointEnd,
      outPath,
      baselineOutPath: outPath,
      endpoint: buildSeedFromSegment(segment),
      settings: normalizedSettings,
      baselineSettings: normalizedSettings,
    });
  });
}

export function mergeDegapJobs(currentJobs, nextJobs) {
  const byId = new Map();
  normalizeDegapJobs(currentJobs).forEach((job) => byId.set(buildDegapJobKey(job), job));
  normalizeDegapJobs(nextJobs).forEach((job) => byId.set(buildDegapJobKey(job), job));
  return Array.from(byId.values()).sort(compareDegapJobs);
}

export function findDuplicateDegapJobs(currentJobs, nextJobs) {
  const existingIds = new Set(normalizeDegapJobs(currentJobs).map(buildDegapJobKey));
  return normalizeDegapJobs(nextJobs).filter((job) => existingIds.has(buildDegapJobKey(job)));
}

export function validateDegapSettings(settings, { requireOutRoot = true, stateOrLocale = "en" } = {}) {
  const normalized = normalizeDegapSettings(settings);
  if (!normalized.degapPath) {
    return tAssembly(stateOrLocale, "degap.validation.degapPathRequired");
  }
  if (!normalized.hifiReads.length && !normalized.ontReads.length) {
    return tAssembly(stateOrLocale, "degap.validation.readsPathRequired");
  }
  if (!normalized.gpmServerPath) {
    return tAssembly(stateOrLocale, "degap.validation.gpmServerPathRequired");
  }
  if (requireOutRoot && !normalized.outRoot) {
    return tAssembly(stateOrLocale, "degap.validation.mainOutRequired");
  }
  return "";
}

export function buildDegapExportSettings(settings) {
  const normalized = normalizeDegapSettings(settings);
  return {
    degapPath: normalized.degapPath,
    hifiReads: normalized.hifiReads,
    ontReads: normalized.ontReads,
    gpmServerPath: normalized.gpmServerPath,
    outRoot: normalized.outRoot,
    thread: normalized.thread,
    kmerFilter: normalized.kmerFilter,
    kmerSize: normalized.kmerSize,
    kmerNum: normalized.kmerNum,
    maximumExtensionRound: normalized.maximumExtensionRound || null,
    maximumExtensionLength: normalized.maximumExtensionLength || null,
    filterDepthHifi: normalized.filterDepthHifi || null,
    filterDepthOnt: normalized.filterDepthOnt || null,
    remove: normalized.remove,
    edge: normalized.edge,
    motif: normalized.motif,
    work: normalized.work,
    telN: normalized.telN,
    telR: normalized.telR,
    telMm: normalized.telMm,
  };
}

export function buildDegapExportJobs(jobs, globalSettings) {
  const normalizedGlobalSettings = normalizeDegapSettings(globalSettings);
  return normalizeDegapJobs(jobs).map((job) => {
    const sourceSettings = normalizeDegapSettings({
      ...resolveDegapJobSettings(job, normalizedGlobalSettings),
      outRoot: normalizedGlobalSettings.outRoot,
    });
    const effectiveSettings = job.jobType === "telseeker_ctg"
      ? normalizeDegapSettings({
        ...sourceSettings,
        filterDepthHifi: "",
        filterDepthOnt: "",
      })
      : sourceSettings;
    const base = {
      jobType: job.jobType,
      jobId: job.jobId,
      chrName: job.chrName,
      leftCtg: job.leftCtg,
      rightCtg: job.rightCtg,
      flag: job.flag || job.side,
      outPath: resolveDegapJobOutPath(job, normalizedGlobalSettings),
      settings: buildDegapExportSettings(effectiveSettings),
    };
    if (job.jobType === "telseeker_ctg") {
      return {
        ...base,
        endpointCtg: job.endpointCtg,
        endpointEnd: job.endpointEnd,
        endpoint: job.endpoint,
      };
    }
    return {
      ...base,
      left: job.left,
      right: job.right,
    };
  });
}

export function readDegapSoftwareSettings(storage = globalThis.localStorage) {
  try {
    return normalizeDegapSettings(JSON.parse(storage?.getItem?.(DEGAP_SOFTWARE_SETTINGS_STORAGE_KEY) || "{}"));
  } catch {
    return normalizeDegapSettings({});
  }
}

export function writeDegapSoftwareSettings(settings, storage = globalThis.localStorage) {
  const normalized = normalizeDegapSettings(settings);
  storage?.setItem?.(DEGAP_SOFTWARE_SETTINGS_STORAGE_KEY, JSON.stringify({
    degapPath: normalized.degapPath,
    thread: normalized.thread,
    kmerFilter: normalized.kmerFilter,
    kmerSize: normalized.kmerSize,
    kmerNum: normalized.kmerNum,
    maximumExtensionRound: normalized.maximumExtensionRound,
    maximumExtensionLength: normalized.maximumExtensionLength,
    filterDepthHifi: normalized.filterDepthHifi,
    filterDepthOnt: normalized.filterDepthOnt,
    remove: normalized.remove,
    edge: normalized.edge,
    motif: normalized.motif,
    work: normalized.work,
    telN: normalized.telN,
    telR: normalized.telR,
    telMm: normalized.telMm,
  }));
}
