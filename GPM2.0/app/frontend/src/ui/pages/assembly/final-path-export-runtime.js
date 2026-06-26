import {
  getCurrentChrFinalPath,
  isFinalPathGapSegment,
  resolveCurrentFinalPathChrName,
  resolveFinalPathSegmentDisplayName,
  resolveFinalPathSegmentLengthBp,
} from "./final-path-state.js";
import {
  buildFinalPathLogModel,
  buildFinalPathLogTsvText,
  canUseFinalPathLog,
} from "./final-path-log-state.js";
import { renderFinalPathCard } from "./final-path-card.js";
import { pickDirectoryPath, pickSaveFilePath } from "../../../services/backend-api.js";
import {
  exportDegapJobs,
  exportFinalPathFasta,
  writeFinalPathExportBinaryFile,
  writeFinalPathExportTextFile,
} from "../../../services/workflow-api.js";
import { buildDegapExportPayload } from "./degap-runtime.js";
import { normalizeDegapRuntimeState } from "./degap-state.js";
import { bindDelegatedDelayedFloatingClose } from "../floating-menu-runtime.js";

const FINAL_PATH_EXPORT_BOUND = Symbol("finalPathExportBound");
const FINAL_PATH_EXPORT_CLOSE_TIMER = "__finalPathExportCloseTimer";
const FINAL_PATH_FALLBACK_CARD_CONTENT_INSET_PX = 22;
const FINAL_PATH_FALLBACK_CARD_LAYOUT_OFFSET_PX = 138;
const FINAL_PATH_EXPORT_SVG_STYLE_TEXT = [
  ".assembly-track-svg{display:block;background:#fff;}",
  ".track-ruler-line{stroke:#5f5f5f;stroke-width:1;}",
  ".track-tick-guide{stroke-dasharray:3,3;stroke-width:1;stroke:#d7d7d7;}",
  ".track-tick-guide.is-major{stroke:#8d8d8d;}",
  ".track-tick-guide.is-minor{display:none;}",
  ".track-tick-label{fill:#666;font-size:10px;}",
  ".track-ctg{fill:#d2dfef;stroke:#6d85a1;stroke-width:1;}",
  ".track-ctg.is-active{fill:#b9d0ea;stroke:#38516c;}",
  ".track-ctg.is-ref,.track-ctg.is-ref.is-active{fill:#cfcfcf;stroke:#8e8e8e;}",
  ".track-ctg.is-companion{fill:#e7dec4;stroke:#8a7551;}",
  ".track-ctg.is-companion.is-active{fill:#dccba4;stroke:#725d39;}",
  ".track-ctg-label{fill:#243a54;font-size:10px;}",
  ".track-ctg-label.is-ref{fill:#4f4f4f;}",
  ".track-ctg-label.is-companion{fill:#5c492a;}",
  ".track-ctg-label.is-outside{font-size:9px;}",
  ".final-path-gap-marker{fill:#ffffff;stroke:#1b1b1b;stroke-width:1;}",
  ".final-path-gap-label{fill:#1b1b1b;font-size:10px;font-weight:700;}",
].join("");

function normalizeString(value) {
  return String(value || "").trim();
}

function resolveFinalPathExportCanvasScale() {
  const deviceScale = Number(globalThis.devicePixelRatio || 1);
  if (Number.isFinite(deviceScale) && deviceScale > 2) {
    return deviceScale;
  }
  return 2;
}

function resolveFinalPathExportDisplayName(segment) {
  return isFinalPathGapSegment(segment) ? "Gap" : resolveFinalPathSegmentDisplayName(segment);
}

function resolveFinalPathSegmentOrient(segment) {
  if (isFinalPathGapSegment(segment)) {
    return "NA";
  }
  return Number(segment?.start) > Number(segment?.end) ? "-" : "+";
}

export function buildFinalPathExportBaseName({ projectName, chrName }) {
  const normalizedProjectName = normalizeString(projectName) || "project";
  const normalizedChrName = normalizeString(chrName);
  return `${normalizedProjectName}_${normalizedChrName}_path`;
}

function padExportTimestampPart(value) {
  return String(Math.trunc(Number(value) || 0)).padStart(2, "0");
}

export function formatExportTimestamp(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
    return "";
  }
  return [
    String(date.getFullYear()).padStart(4, "0"),
    padExportTimestampPart(date.getMonth() + 1),
    padExportTimestampPart(date.getDate()),
    padExportTimestampPart(date.getHours()),
    padExportTimestampPart(date.getMinutes()),
    padExportTimestampPart(date.getSeconds()),
  ].join("");
}

function normalizeExportTimestamp(value) {
  const text = normalizeString(value);
  if (/^\d{14}$/.test(text)) {
    return text;
  }
  return formatExportTimestamp(value);
}

export function resolveExportTimestamp(deps = {}) {
  const source = typeof deps.getExportTimestamp === "function"
    ? deps.getExportTimestamp()
    : deps.exportTimestamp;
  return normalizeExportTimestamp(source) || formatExportTimestamp(new Date());
}

export function buildTimestampedExportBaseName(baseName, timestamp) {
  const normalizedBaseName = normalizeString(baseName) || "project";
  const normalizedTimestamp = normalizeExportTimestamp(timestamp);
  return normalizedTimestamp ? `${normalizedBaseName}_${normalizedTimestamp}` : normalizedBaseName;
}

export function appendTimestampToOutputPath(outputPath, timestamp) {
  const normalizedPath = normalizeString(outputPath);
  const normalizedTimestamp = normalizeExportTimestamp(timestamp);
  if (!normalizedPath || !normalizedTimestamp) {
    return normalizedPath;
  }
  const separatorIndex = Math.max(normalizedPath.lastIndexOf("/"), normalizedPath.lastIndexOf("\\"));
  const directoryPrefix = separatorIndex >= 0 ? normalizedPath.slice(0, separatorIndex + 1) : "";
  const fileName = separatorIndex >= 0 ? normalizedPath.slice(separatorIndex + 1) : normalizedPath;
  if (!fileName) {
    return normalizedPath;
  }
  const extensionIndex = fileName.lastIndexOf(".");
  const stem = extensionIndex > 0 ? fileName.slice(0, extensionIndex) : fileName;
  const extension = extensionIndex > 0 ? fileName.slice(extensionIndex) : "";
  if (/_\d{14}$/.test(stem)) {
    return normalizedPath;
  }
  return `${directoryPrefix}${stem}_${normalizedTimestamp}${extension}`;
}

export function buildFinalPathTsvText(finalPathEntry) {
  const rows = [
    "#\tCtg\tOrigin ID\toverall_len\torient\tCtg_start\tCtg_end\tChr_start\tChr_end",
  ];
  let chrCursor = 1;
  const segments = Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : [];
  segments.forEach((segment, index) => {
    const chrStart = chrCursor;
    const chrEnd = chrStart + Math.max(0, resolveFinalPathSegmentLengthBp(segment)) - 1;
    chrCursor = chrEnd + 1;
    if (isFinalPathGapSegment(segment)) {
      rows.push(`${index + 1}\tGap\tNA\t100\tNA\t1\t100\t${chrStart}\t${chrEnd}`);
      return;
    }
    rows.push([
      index + 1,
      resolveFinalPathExportDisplayName(segment),
      normalizeString(segment?.originId),
      normalizeString(segment?.overallLen),
      resolveFinalPathSegmentOrient(segment),
      normalizeString(segment?.start),
      normalizeString(segment?.end),
      chrStart,
      chrEnd,
    ].join("\t"));
  });
  return `${rows.join("\n")}\n`;
}

export function resolveFinalPathViewportSnapshot({ viewportNode, svgNode }) {
  return {
    width: Number(viewportNode?.clientWidth || 0),
    height: Number(viewportNode?.clientHeight || 0),
    scrollLeft: Number(viewportNode?.scrollLeft || 0),
    scrollTop: Number(viewportNode?.scrollTop || 0),
    svgMarkup: String(svgNode?.outerHTML || ""),
  };
}

function joinOutputPath(directoryPath, fileName) {
  const base = String(directoryPath || "").trim().replace(/[\\/]+$/, "");
  if (!base) {
    return String(fileName || "").trim();
  }
  const separator = base.includes("\\") ? "\\" : "/";
  return `${base}${separator}${String(fileName || "").trim()}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll('"', "&quot;");
}

function normalizePositiveNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : fallback;
}

function normalizeDatasetId(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function getCurrentProject(state) {
  const projectId = Number(state?.session?.projectId || 0);
  if (!projectId || !Array.isArray(state?.initializer?.existingProjects)) {
    return null;
  }
  return state.initializer.existingProjects.find((project) => Number(project?.projectId || 0) === projectId) || null;
}

function isDatasetFastaAvailable(datasets, datasetId) {
  const normalizedDatasetId = normalizeDatasetId(datasetId);
  if (normalizedDatasetId === null || !Array.isArray(datasets)) {
    return false;
  }
  const matched = datasets.find((dataset) => Number(dataset?.datasetId || 0) === normalizedDatasetId);
  if (!matched) {
    return true;
  }
  return matched.fastaAvailable !== false;
}

function canProjectExportFinalPathFasta(state) {
  const currentProject = getCurrentProject(state);
  if (!currentProject) {
    return true;
  }
  const datasetIds = [
    normalizeDatasetId(currentProject.primaryDatasetId),
    ...(Array.isArray(currentProject.supportDatasetIds) ? currentProject.supportDatasetIds : [])
      .map((datasetId) => normalizeDatasetId(datasetId)),
  ].filter((datasetId) => datasetId !== null);
  if (!datasetIds.length) {
    return false;
  }
  return datasetIds.every((datasetId) =>
    isDatasetFastaAvailable(state?.initializer?.datasets || [], datasetId),
  );
}

function getDatasetNameById(datasets, datasetId) {
  const normalizedDatasetId = Number(datasetId || 0);
  if (!normalizedDatasetId || !Array.isArray(datasets)) {
    return "";
  }
  const matched = datasets.find((dataset) => Number(dataset?.datasetId || 0) === normalizedDatasetId);
  return String(matched?.name || matched?.label || "");
}

function resolveFallbackFinalPathTrackViewportPx({ host, deps = {} }) {
  const measuredViewportPx = normalizePositiveNumber(deps.getMeasuredTrackViewportPx?.(), 0);
  if (measuredViewportPx > 0) {
    return Math.round(measuredViewportPx);
  }
  const primaryTrackViewportPx = normalizePositiveNumber(
    host?.querySelector?.(".assembly-track-scroll[data-track-role='primary']")?.clientWidth,
    0,
  );
  if (primaryTrackViewportPx > 0) {
    return Math.round(primaryTrackViewportPx);
  }
  const docPrimaryTrackViewportPx = normalizePositiveNumber(
    globalThis.document?.querySelector?.(".assembly-track-scroll[data-track-role='primary']")?.clientWidth,
    0,
  );
  if (docPrimaryTrackViewportPx > 0) {
    return Math.round(docPrimaryTrackViewportPx);
  }
  return 0;
}

function resolveElementOuterWidthPx(node) {
  const rectWidth = normalizePositiveNumber(node?.getBoundingClientRect?.().width, 0);
  if (rectWidth > 0) {
    return Math.round(rectWidth);
  }
  const offsetWidth = normalizePositiveNumber(node?.offsetWidth, 0);
  if (offsetWidth > 0) {
    return Math.round(offsetWidth);
  }
  const clientWidth = normalizePositiveNumber(node?.clientWidth, 0);
  if (clientWidth > 0) {
    return Math.round(clientWidth + 2);
  }
  return 0;
}

function resolveFallbackFinalPathCardWidthPx({ host, trackViewportPx = 0 }) {
  const liveCardOuterWidth = resolveElementOuterWidthPx(host?.querySelector?.(".final-path-card"));
  if (liveCardOuterWidth > 0) {
    return liveCardOuterWidth;
  }
  const documentCardOuterWidth = resolveElementOuterWidthPx(globalThis.document?.querySelector?.(".final-path-card"));
  if (documentCardOuterWidth > 0) {
    return documentCardOuterWidth;
  }
  const liveCardBodyWidth = normalizePositiveNumber(host?.querySelector?.(".final-path-card-body")?.clientWidth, 0);
  if (liveCardBodyWidth > 0) {
    return Math.round(liveCardBodyWidth + FINAL_PATH_FALLBACK_CARD_CONTENT_INSET_PX);
  }
  const documentCardBodyWidth = normalizePositiveNumber(
    globalThis.document?.querySelector?.(".final-path-card-body")?.clientWidth,
    0,
  );
  if (documentCardBodyWidth > 0) {
    return Math.round(documentCardBodyWidth + FINAL_PATH_FALLBACK_CARD_CONTENT_INSET_PX);
  }
  const derivedCardWidth = normalizePositiveNumber(trackViewportPx, 0);
  if (derivedCardWidth > 0) {
    return Math.round(
      derivedCardWidth
      + FINAL_PATH_FALLBACK_CARD_LAYOUT_OFFSET_PX
      + FINAL_PATH_FALLBACK_CARD_CONTENT_INSET_PX,
    );
  }
  return 0;
}

function buildFallbackFinalPathGraphCardHtml({ state, finalPathEntry, trackViewportPx = 0 }) {
  const assembly = state?.assembly || {};
  const currentProject = getCurrentProject(state);
  const primaryDatasetName = getDatasetNameById(
    state?.initializer?.datasets || [],
    currentProject?.primaryDatasetId,
  );
  return renderFinalPathCard(
    {
      projectName: state?.session?.projectName || state?.session?.projectId || "project",
      chrName: resolveCurrentFinalPathChrName(assembly) || finalPathEntry?.chrName,
      finalPathEntry,
      viewMode: "graph",
      trackView: assembly.finalPathTrackView,
      trackViewportPx,
      primaryDatasetName,
    },
    {
      escapeAttr,
      escapeHtml,
      i18n: {},
    },
  );
}

function resolveHtmlStringFinalPathViewportSnapshot(graphCardHtml, trackViewportPx = 0) {
  const svgMarkup = String(graphCardHtml.match(/<svg[\s\S]*?<\/svg>/i)?.[0] || "");
  const resolvedViewportWidth = normalizePositiveNumber(trackViewportPx, 0);
  return {
    width: resolvedViewportWidth || normalizePositiveNumber(svgMarkup.match(/\bwidth="([^"]+)"/i)?.[1], 1200),
    height: normalizePositiveNumber(svgMarkup.match(/\bheight="([^"]+)"/i)?.[1], 154),
    scrollLeft: 0,
    scrollTop: 0,
    svgMarkup,
  };
}

function resolveFallbackFinalPathViewportSnapshot({ host, state, finalPathEntry, deps = {} }) {
  const trackViewportPx = resolveFallbackFinalPathTrackViewportPx({ host, deps });
  const fallbackCardWidthPx = resolveFallbackFinalPathCardWidthPx({ host, trackViewportPx });
  const graphCardHtml = buildFallbackFinalPathGraphCardHtml({
    state,
    finalPathEntry,
    trackViewportPx,
  });
  const doc = globalThis.document;
  if (doc?.createElement && doc?.body?.appendChild) {
    const container = doc.createElement("div");
    try {
      if (container?.style) {
        container.style.position = "absolute";
        container.style.left = "-100000px";
        container.style.top = "0";
        container.style.visibility = "hidden";
        container.style.pointerEvents = "none";
        container.style.width = `${normalizePositiveNumber(
          fallbackCardWidthPx,
          normalizePositiveNumber(globalThis.window?.innerWidth, 1200),
        )}px`;
      }
      container.innerHTML = graphCardHtml;
      doc.body.appendChild(container);
      const snapshot = resolveFinalPathViewportSnapshot({
        viewportNode: container.querySelector?.("[data-final-path-graph-viewport]"),
        svgNode: container.querySelector?.("[data-final-path-graph-svg]"),
      });
      if (
        snapshot.width > 0
        && snapshot.height > 0
        && String(snapshot.svgMarkup || "").trim().startsWith("<svg")
      ) {
        return snapshot;
      }
    } finally {
      if (typeof container.remove === "function") {
        container.remove();
      } else if (typeof doc.body.removeChild === "function") {
        try {
          doc.body.removeChild(container);
        } catch {
          // ignore cleanup failures for detached test stubs
        }
      }
    }
  }
  return resolveHtmlStringFinalPathViewportSnapshot(graphCardHtml, trackViewportPx);
}

function resolveEffectiveFinalPathViewportSnapshot({ host, state, finalPathEntry, deps = {} }) {
  const liveSnapshot = resolveFinalPathViewportSnapshot({
    viewportNode: host.querySelector?.("[data-final-path-graph-viewport]"),
    svgNode: host.querySelector?.("[data-final-path-graph-svg]"),
  });
  if (
    liveSnapshot.width > 0
    && liveSnapshot.height > 0
    && String(liveSnapshot.svgMarkup || "").trim().startsWith("<svg")
  ) {
    return liveSnapshot;
  }
  return resolveFallbackFinalPathViewportSnapshot({
    host,
    state,
    finalPathEntry,
    deps,
  });
}

function createFinalPathExportJob({ kind, chrName, targetPath, steps, displaySteps }) {
  return {
    open: true,
    kind,
    chrName,
    status: "running",
    currentStep: "",
    completedOutputs: [],
    completedStepIds: [],
    error: "",
    cancelRequested: false,
    targetPath,
    steps: Array.isArray(steps) ? steps : [],
    displaySteps: Array.isArray(displaySteps) ? displaySteps : [],
  };
}

function setFinalPathExportJob(host, store, nextJob, deps = {}) {
  const state = store.getState();
  store.setState({
    ...state,
    assembly: {
      ...state.assembly,
      finalPathExportJob: nextJob,
    },
  });
  if (typeof deps.rerender === "function") {
    deps.rerender(host, store);
  }
}

function resolveExportErrorMessage(error, state, deps = {}) {
  if (typeof deps.mapAssemblyError === "function") {
    const mappedError = deps.mapAssemblyError({ error, stateOrLocale: state });
    if (mappedError?.rawMessage && mappedError.category !== "runtime") {
      return mappedError.rawMessage;
    }
    return mappedError?.userMessage || String(error?.message || error || "");
  }
  return String(error?.message || error || "");
}

export function planFinalPathExportSteps({
  kind,
  baseName,
  targetPath,
  canExportFasta = true,
  canExportLog = true,
}) {
  const normalizedKind = normalizeString(kind).toLowerCase();
  if (normalizedKind === "png") {
    return [{ kind: "png", label: "图(.png)", outputPath: targetPath }];
  }
  if (normalizedKind === "tsv") {
    return [{ kind: "tsv", label: "表(.tsv)", outputPath: targetPath }];
  }
  if (normalizedKind === "log") {
    return canExportLog ? [{ kind: "log", label: "日志(.log)", outputPath: targetPath }] : [];
  }
  if (normalizedKind === "fasta") {
    return [{ kind: "fasta", label: "序列(.fasta)", outputPath: targetPath }];
  }
  if (normalizedKind === "degap-jobs") {
    return [{ kind: "degap-jobs", label: "DEGAP-JOBS", outputPath: targetPath }];
  }
  if (normalizedKind === "all") {
    const steps = [
      { kind: "png", label: "图(.png)", outputPath: joinOutputPath(targetPath, `${baseName}.png`) },
      { kind: "tsv", label: "表(.tsv)", outputPath: joinOutputPath(targetPath, `${baseName}.tsv`) },
    ];
    if (canExportLog) {
      steps.push({ kind: "log", label: "日志(.log)", outputPath: joinOutputPath(targetPath, `${baseName}.log`) });
    }
    if (canExportFasta) {
      steps.push({
        kind: "fasta",
        label: "序列(.fasta)",
        outputPath: joinOutputPath(targetPath, `${baseName}.fasta`),
      });
    }
    return steps;
  }
  return [];
}

function resolveDegapJobDisplayLabel(job) {
  if (normalizeString(job?.jobType) === "telseeker_ctg") {
    const side = normalizeString(job?.endpointEnd).toUpperCase() === "R" ? "right" : "left";
    return `telseeker-ctg ${side} ${normalizeString(job?.endpointCtg) || normalizeString(job?.jobId)}`;
  }
  const side = normalizeString(job?.side || job?.flag).toLowerCase() === "right" ? "right" : "left";
  const leftCtg = normalizeString(job?.leftCtg) || "left-ctg";
  const rightCtg = normalizeString(job?.rightCtg) || "right-ctg";
  return `gapfiller ${side} ${leftCtg} -> ${rightCtg}`;
}

export function buildDegapJobsDisplaySteps(state) {
  const assembly = state?.assembly || {};
  const chrName = resolveCurrentFinalPathChrName(assembly);
  const degap = normalizeDegapRuntimeState(assembly.degap);
  const jobs = degap.jobs.filter((job) => normalizeString(job.chrName) === chrName);
  if (!jobs.length) {
    return [];
  }
  return [
    { id: "degap-prepare", kind: "degap-prepare", label: "prepare_degap_shared.sh" },
    ...jobs.map((job) => ({
      id: `degap-job:${normalizeString(job.jobId)}`,
      kind: "degap-job",
      label: resolveDegapJobDisplayLabel(job),
    })),
    { id: "degap-manifest", kind: "degap-manifest", label: "jobs.tsv" },
  ];
}

export function buildViewportScopedSvgMarkup(snapshot) {
  const width = Math.max(1, Math.round(Number(snapshot?.width || 0)));
  const height = Math.max(1, Math.round(Number(snapshot?.height || 0)));
  const scrollLeft = Math.max(0, Number(snapshot?.scrollLeft || 0));
  const scrollTop = Math.max(0, Number(snapshot?.scrollTop || 0));
  const svgMarkup = String(snapshot?.svgMarkup || "").trim();
  if (!svgMarkup.startsWith("<svg")) {
    throw new Error("final-path export snapshot is missing svg markup");
  }
  let scopedMarkup = svgMarkup
    .replace(/width="[^"]*"/i, `width="${width}"`)
    .replace(/height="[^"]*"/i, `height="${height}"`);
  if (/viewBox="[^"]*"/i.test(scopedMarkup)) {
    scopedMarkup = scopedMarkup.replace(
      /viewBox="[^"]*"/i,
      `viewBox="${scrollLeft} ${scrollTop} ${width} ${height}"`,
    );
  } else {
    scopedMarkup = scopedMarkup.replace(
      "<svg",
      `<svg viewBox="${scrollLeft} ${scrollTop} ${width} ${height}"`,
    );
  }
  if (!/\sxmlns=("[^"]*"|'[^']*')/i.test(scopedMarkup)) {
    scopedMarkup = scopedMarkup.replace(
      "<svg",
      '<svg xmlns="http://www.w3.org/2000/svg"',
    );
  }
  if (!/\sxmlns:xlink=("[^"]*"|'[^']*')/i.test(scopedMarkup)) {
    scopedMarkup = scopedMarkup.replace(
      "<svg",
      '<svg xmlns:xlink="http://www.w3.org/1999/xlink"',
    );
  }
  scopedMarkup = scopedMarkup.replace(
    /(>)([\s\S]*)$/m,
    `><style>${FINAL_PATH_EXPORT_SVG_STYLE_TEXT}</style><rect x="${scrollLeft}" y="${scrollTop}" width="${width}" height="${height}" fill="#fff" />$2`,
  );
  return scopedMarkup;
}

export async function renderFinalPathViewportPng(snapshot) {
  const scopedSvgMarkup = buildViewportScopedSvgMarkup(snapshot);
  const blob = new Blob([scopedSvgMarkup], { type: "image/svg+xml;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  try {
    const image = await new Promise((resolve, reject) => {
      const nextImage = new Image();
      nextImage.onload = () => resolve(nextImage);
      nextImage.onerror = () => reject(new Error("failed to decode final-path svg"));
      nextImage.src = objectUrl;
    });
    const canvas = document.createElement("canvas");
    const exportWidth = Math.max(1, Math.round(Number(snapshot?.width || 0)));
    const exportHeight = Math.max(1, Math.round(Number(snapshot?.height || 0)));
    const canvasScale = resolveFinalPathExportCanvasScale();
    canvas.width = Math.max(1, Math.round(exportWidth * canvasScale));
    canvas.height = Math.max(1, Math.round(exportHeight * canvasScale));
    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("failed to create final-path export canvas context");
    }
    context.scale(canvasScale, canvasScale);
    context.clearRect(0, 0, exportWidth, exportHeight);
    if ("imageSmoothingEnabled" in context) {
      context.imageSmoothingEnabled = true;
    }
    if ("imageSmoothingQuality" in context) {
      context.imageSmoothingQuality = "high";
    }
    context.drawImage(image, 0, 0, exportWidth, exportHeight);
    return canvas.toDataURL("image/png").replace(/^data:image\/png;base64,/, "");
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export async function runFinalPathExportJob({ job, runStep, onUpdate }) {
  const nextJob = {
    ...job,
    status: "running",
    completedOutputs: Array.isArray(job?.completedOutputs) ? job.completedOutputs : [],
    completedStepIds: Array.isArray(job?.completedStepIds) ? job.completedStepIds : [],
  };
  for (const step of Array.isArray(job?.steps) ? job.steps : []) {
    if (nextJob.cancelRequested) {
      nextJob.status = "canceled";
      await onUpdate({ ...nextJob });
      return nextJob;
    }
    nextJob.currentStep = step.label;
    await onUpdate({ ...nextJob });
    const result = await runStep(step, nextJob);
    const outputPaths = Array.isArray(result?.outputPaths) ? result.outputPaths : [result?.outputPath];
    const nextOutputPaths = outputPaths.map(normalizeString).filter(Boolean);
    if (nextOutputPaths.length) {
      nextJob.completedOutputs = [...nextJob.completedOutputs, ...nextOutputPaths];
    }
    const completedStepIds = Array.isArray(result?.completedStepIds) ? result.completedStepIds : [];
    const nextCompletedStepIds = completedStepIds.map(normalizeString).filter(Boolean);
    if (nextCompletedStepIds.length) {
      nextJob.completedStepIds = [...nextJob.completedStepIds, ...nextCompletedStepIds];
    }
    if (nextJob.cancelRequested) {
      nextJob.status = "canceled";
      await onUpdate({ ...nextJob });
      return nextJob;
    }
  }
  nextJob.status = "success";
  await onUpdate({ ...nextJob });
  return nextJob;
}

export function requestCancelFinalPathExport(assembly) {
  const job = assembly?.finalPathExportJob;
  if (!job || job.status !== "running") {
    return assembly;
  }
  return {
    ...assembly,
    finalPathExportJob: {
      ...job,
      cancelRequested: true,
    },
  };
}

export function closeFinalPathExportDialog(assembly) {
  return {
    ...assembly,
    finalPathExportJob: null,
  };
}

export async function resolveFinalPathExportTarget({ state, kind, baseName, deps = {} }) {
  const pickSaveFilePathImpl = deps.pickSaveFilePath || pickSaveFilePath;
  const pickDirectoryPathImpl = deps.pickDirectoryPath || pickDirectoryPath;
  const normalizedKind = normalizeString(kind).toLowerCase();

  if (normalizedKind === "png") {
    return pickSaveFilePathImpl({
      defaultPath: `${baseName}.png`,
      filters: [{ name: "PNG", extensions: ["png"] }],
    }, state);
  }
  if (normalizedKind === "tsv") {
    return pickSaveFilePathImpl({
      defaultPath: `${baseName}.tsv`,
      filters: [{ name: "TSV", extensions: ["tsv"] }],
    }, state);
  }
  if (normalizedKind === "log") {
    return pickSaveFilePathImpl({
      defaultPath: `${baseName}.log`,
      filters: [{ name: "LOG", extensions: ["log"] }],
    }, state);
  }
  if (normalizedKind === "fasta") {
    return pickSaveFilePathImpl({
      defaultPath: `${baseName}.fasta`,
      filters: [{ name: "FASTA", extensions: ["fasta", "fa"] }],
    }, state);
  }
  if (normalizedKind === "all") {
    return pickDirectoryPathImpl(state);
  }
  if (normalizedKind === "degap-jobs") {
    return pickDirectoryPathImpl(state);
  }
  return "";
}

function buildFinalPathLogModelForState(state, finalPathEntry) {
  const assembly = state?.assembly || {};
  const currentProject = getCurrentProject(state);
  const primaryDatasetName = getDatasetNameById(
    state?.initializer?.datasets || [],
    currentProject?.primaryDatasetId,
  );
  return buildFinalPathLogModel({
    chrName: resolveCurrentFinalPathChrName(assembly) || finalPathEntry?.chrName,
    finalPathEntry,
    finalPathByChr: assembly.finalPathByChr,
    primaryCtgs: assembly.chrCtgs,
    hiddenPrimaryCtgIds: assembly.hiddenPrimaryCtgIds,
    primaryDatasetName,
  });
}

export async function runFinalPathExportStep({
  step,
  finalPathEntry,
  state,
  host,
  deps = {},
}) {
  const assembly = state.assembly || {};
  const writeTextFileImpl = deps.writeFinalPathExportTextFile || writeFinalPathExportTextFile;
  const writeBinaryFileImpl = deps.writeFinalPathExportBinaryFile || writeFinalPathExportBinaryFile;
  const exportFastaImpl = deps.exportFinalPathFasta || exportFinalPathFasta;
  const exportDegapJobsImpl = deps.exportDegapJobs || exportDegapJobs;
  const renderPngImpl = deps.renderFinalPathViewportPng || renderFinalPathViewportPng;
  const viewportSnapshot = () => resolveEffectiveFinalPathViewportSnapshot({
    host,
    state,
    finalPathEntry,
    deps,
  });

  if (step?.kind === "png") {
    await writeBinaryFileImpl({
      outputPath: step.outputPath,
      bytesBase64: await renderPngImpl(viewportSnapshot()),
      stateOrLocale: state,
    });
    return { outputPath: step.outputPath };
  }
  if (step?.kind === "tsv") {
    await writeTextFileImpl({
      outputPath: step.outputPath,
      text: buildFinalPathTsvText(finalPathEntry),
      stateOrLocale: state,
    });
    return { outputPath: step.outputPath };
  }
  if (step?.kind === "log") {
    await writeTextFileImpl({
      outputPath: step.outputPath,
      text: buildFinalPathLogTsvText(buildFinalPathLogModelForState(state, finalPathEntry)),
      stateOrLocale: state,
    });
    return { outputPath: step.outputPath };
  }
  if (step?.kind === "fasta") {
    await exportFastaImpl({
      workspaceRoot: state.session?.workspacePath || "",
      projectId: Number(state.session?.projectId || 0),
      chrName: resolveCurrentFinalPathChrName(assembly),
      finalPathEntry,
      outputPath: step.outputPath,
      stateOrLocale: state,
    });
    return { outputPath: step.outputPath };
  }
  if (step?.kind === "degap-jobs") {
    const payload = buildDegapExportPayload(state);
    const result = await exportDegapJobsImpl({
      ...payload,
      outputDir: step.outputPath,
      stateOrLocale: state,
    });
    const scripts = Array.isArray(result?.scripts) ? result.scripts : [];
    return {
      outputPath: result?.manifestPath || step.outputPath,
      outputPaths: [
        result?.prepareScriptPath,
        ...scripts.map((script) => script?.scriptPath),
        result?.manifestPath,
      ],
      completedStepIds: [
        "degap-prepare",
        ...scripts
          .map((script) => normalizeString(script?.jobId))
          .filter(Boolean)
          .map((jobId) => `degap-job:${jobId}`),
        "degap-manifest",
      ],
    };
  }
  return { outputPath: "" };
}

export async function launchFinalPathExportJob({
  host,
  store,
  kind,
  deps = {},
}) {
  const state = store.getState();
  const assembly = state.assembly || {};
  const runningJob = assembly.finalPathExportJob;
  if (runningJob?.open && runningJob.status === "running") {
    return false;
  }
  const finalPathEntry = getCurrentChrFinalPath(assembly);
  if (!finalPathEntry) {
    return false;
  }
  const normalizedKind = normalizeString(kind).toLowerCase();
  if (!normalizedKind) {
    return false;
  }
  const canExportLog = canUseFinalPathLog(finalPathEntry);
  if (normalizedKind === "log" && !canExportLog) {
    return false;
  }
  const exportTimestamp = resolveExportTimestamp(deps);
  const baseName = buildTimestampedExportBaseName(
    buildFinalPathExportBaseName({
      projectName: state.session?.projectName,
      chrName: resolveCurrentFinalPathChrName(assembly),
    }),
    exportTimestamp,
  );
  const resolveTarget = deps.resolveFinalPathExportTarget || resolveFinalPathExportTarget;
  const runStep = deps.runFinalPathExportStep || runFinalPathExportStep;
  let targetPath = await resolveTarget({
    state,
    kind: normalizedKind,
    baseName,
    deps,
  });
  if (!targetPath) {
    return false;
  }
  if (normalizedKind !== "all" && normalizedKind !== "degap-jobs") {
    targetPath = appendTimestampToOutputPath(targetPath, exportTimestamp);
  }
  const steps = planFinalPathExportSteps({
    kind: normalizedKind,
    baseName,
    targetPath,
    canExportFasta: canProjectExportFinalPathFasta(state),
    canExportLog,
  });
  if (!steps.length) {
    return false;
  }
  const job = createFinalPathExportJob({
    kind: normalizedKind,
    chrName: resolveCurrentFinalPathChrName(assembly),
    targetPath,
    steps,
    displaySteps: normalizedKind === "degap-jobs" ? buildDegapJobsDisplaySteps(state) : [],
  });
  setFinalPathExportJob(host, store, job, deps);
  await Promise.resolve();
  try {
    await runFinalPathExportJob({
      job,
      runStep: async (step) => runStep({
        step,
        finalPathEntry,
        state: store.getState(),
        host,
        deps,
      }),
      onUpdate: async (nextJob) => {
        setFinalPathExportJob(host, store, nextJob, deps);
        await Promise.resolve();
      },
    });
  } catch (error) {
    const currentState = store.getState();
    const currentJob = currentState.assembly?.finalPathExportJob || job;
    setFinalPathExportJob(host, store, {
      ...currentJob,
      status: "error",
      error: resolveExportErrorMessage(error, currentState, deps),
    }, deps);
    return false;
  }
  return true;
}

export async function runFinalPathExportAction({
  host,
  store,
  kind,
  deps = {},
}) {
  const state = store.getState();
  const assembly = state.assembly || {};
  const finalPathEntry = getCurrentChrFinalPath(assembly);
  if (!finalPathEntry) {
    return false;
  }
  const normalizedKind = normalizeString(kind).toLowerCase();
  if (!normalizedKind) {
    return false;
  }
  const canExportLog = canUseFinalPathLog(finalPathEntry);
  if (normalizedKind === "log" && !canExportLog) {
    return false;
  }
  const exportTimestamp = resolveExportTimestamp(deps);
  const baseName = buildTimestampedExportBaseName(
    buildFinalPathExportBaseName({
      projectName: state.session?.projectName,
      chrName: resolveCurrentFinalPathChrName(assembly),
    }),
    exportTimestamp,
  );
  let targetPath = await resolveFinalPathExportTarget({
    state,
    kind: normalizedKind,
    baseName,
    deps,
  });
  if (!targetPath) {
    return false;
  }
  if (normalizedKind !== "all" && normalizedKind !== "degap-jobs") {
    targetPath = appendTimestampToOutputPath(targetPath, exportTimestamp);
  }
  const job = createFinalPathExportJob({
    kind: normalizedKind,
    chrName: resolveCurrentFinalPathChrName(assembly),
    targetPath,
    steps: planFinalPathExportSteps({
      kind: normalizedKind,
      baseName,
      targetPath,
      canExportFasta: canProjectExportFinalPathFasta(state),
      canExportLog,
    }),
    displaySteps: normalizedKind === "degap-jobs" ? buildDegapJobsDisplaySteps(state) : [],
  });
  if (!job.steps.length) {
    return false;
  }
  const finalJob = await runFinalPathExportJob({
    job,
    runStep: async (step) => runFinalPathExportStep({
      step,
      finalPathEntry,
      state,
      host,
      deps,
    }),
    onUpdate: async () => {},
  });
  return finalJob.status === "success";
}

export function bindFinalPathExport(host, store, deps = {}) {
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (host?.[FINAL_PATH_EXPORT_BOUND]) {
    return;
  }
  const setExportMenuOpen = (exportRoot, shouldOpen) => {
    const menuNode = exportRoot?.querySelector?.("[data-final-path-export-menu]");
    const toggleNode = exportRoot?.querySelector?.("[data-final-path-export-toggle]");
    if (!menuNode) {
      return;
    }
    menuNode.classList.toggle("is-hidden", !shouldOpen);
    if (toggleNode) {
      toggleNode.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
    }
  };
  const exportAction = typeof deps.exportFinalPathArtifacts === "function"
    ? deps.exportFinalPathArtifacts
    : async () => {};
  host.addEventListener("click", async (event) => {
    const closeNode = event.target?.closest?.("[data-final-path-export-close]");
    if (closeNode) {
      const state = store.getState();
      const assembly = state.assembly || {};
      const nextAssembly = assembly.finalPathExportJob?.status === "running"
        ? requestCancelFinalPathExport(assembly)
        : closeFinalPathExportDialog(assembly);
      store.setState({
        ...state,
        assembly: nextAssembly,
      });
      if (typeof deps.rerender === "function") {
        deps.rerender(host, store);
      }
      return;
    }
    const toggleNode = event.target?.closest?.("[data-final-path-export-toggle]");
    if (toggleNode) {
      const exportNode = toggleNode.closest?.("[data-final-path-export]");
      const menuNode = exportNode?.querySelector?.("[data-final-path-export-menu]");
      if (!menuNode) {
        return;
      }
      const shouldOpen = menuNode.classList.contains("is-hidden");
      setExportMenuOpen(exportNode, shouldOpen);
      return;
    }
    const actionNode = event.target?.closest?.("[data-final-path-export-action]");
    if (!actionNode) {
      return;
    }
    setExportMenuOpen(actionNode.closest?.("[data-final-path-export]"), false);
    await exportAction({
      host,
      store,
      kind: normalizeString(actionNode.dataset.finalPathExportAction).toLowerCase(),
      deps,
    });
  });
  bindDelegatedDelayedFloatingClose(host, {
    rootSelector: "[data-final-path-export]",
    timerKey: FINAL_PATH_EXPORT_CLOSE_TIMER,
    close: (exportRoot) => setExportMenuOpen(exportRoot, false),
  });
  host[FINAL_PATH_EXPORT_BOUND] = true;
}
