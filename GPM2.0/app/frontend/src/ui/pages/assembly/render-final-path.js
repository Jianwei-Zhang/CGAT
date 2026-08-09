import { normalizeSupportDatasetId } from "./selection-state.js";
import { renderFinalPathCard } from "./final-path-card.js";
import { renderDegapJobCard, renderDegapRuntime } from "./degap-card.js";
import {
  FINAL_PATH_ALL_KEY,
  areFinalPathEntriesSemanticallyEqual,
  buildFinalPathEntry,
  getCurrentChrFinalPath,
  resolveCurrentFinalPathChrName,
  resolveFinalPathSelectionKey,
} from "./final-path-state.js";
import { buildFinalPathLogModel } from "./final-path-log-state.js";
import { getFinalPathGraphPreviewState } from "./final-path-graph-drag-runtime.js";

const DEFAULT_TRACK_VIEWPORT_PX = 1200;

function buildPhasedFinalPathOptions(assembly) {
  if (!assembly?.isChrPhased) {
    return [];
  }
  const tracks = Array.isArray(assembly?.phasedChrTracks) ? assembly.phasedChrTracks : [];
  if (!tracks.length) {
    return [];
  }
  const activeKey = resolveFinalPathSelectionKey(assembly) || FINAL_PATH_ALL_KEY;
  const allOption = {
    key: FINAL_PATH_ALL_KEY,
    label: "All",
    chrName: String(assembly?.selectedChrName || "").trim(),
    active: activeKey === FINAL_PATH_ALL_KEY,
  };
  return [allOption, ...tracks
    .map((track) => {
      const key = String(track?.haplotypeKey || "").trim();
      const chrName = String(track?.label || "").trim();
      if (!key || !chrName) {
        return null;
      }
      return {
        key,
        chrName,
        active: key === activeKey,
      };
    })
    .filter(Boolean)];
}

function buildFinalPathDisplayEntries(assembly) {
  const selectedChrName = String(assembly?.selectedChrName || "").trim();
  const finalPathByChr = assembly?.finalPathByChr || {};
  const tracks = Array.isArray(assembly?.phasedChrTracks) ? assembly.phasedChrTracks : [];
  if (!assembly?.isChrPhased || !tracks.length) {
    const chrName = resolveCurrentFinalPathChrName(assembly) || selectedChrName;
    const entry = getCurrentChrFinalPath(assembly)
      || (chrName ? buildFinalPathEntry({ chrName, segments: [], updatedAt: "" }) : null);
    return entry ? [{ key: "", label: chrName, chrName, finalPathEntry: entry }] : [];
  }
  const selectedKey = resolveFinalPathSelectionKey(assembly);
  const selectedTracks = selectedKey === FINAL_PATH_ALL_KEY
    ? tracks
    : tracks.filter((track) => String(track?.haplotypeKey || "").trim() === selectedKey);
  return selectedTracks
    .map((track) => {
      const key = String(track?.haplotypeKey || "").trim();
      const chrName = String(track?.label || "").trim();
      if (!key || !chrName) {
        return null;
      }
      return {
        key,
        label: chrName,
        chrName,
        finalPathEntry: finalPathByChr[chrName]
          || buildFinalPathEntry({ chrName, segments: [], updatedAt: "" }),
      };
    })
    .filter(Boolean);
}

function isDatasetFastaAvailable(datasets, datasetId) {
  const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
  if (normalizedDatasetId === null || !Array.isArray(datasets)) {
    return false;
  }
  const matched = datasets.find((dataset) => Number(dataset?.datasetId || 0) === normalizedDatasetId);
  if (!matched) {
    return true;
  }
  return matched.fastaAvailable !== false;
}

function canProjectExportFinalPathFasta(state, currentProject) {
  if (!currentProject) {
    return true;
  }
  const datasetIds = [
    normalizeSupportDatasetId(currentProject.primaryDatasetId),
    ...(Array.isArray(currentProject.supportDatasetIds) ? currentProject.supportDatasetIds : [])
      .map((datasetId) => normalizeSupportDatasetId(datasetId)),
  ].filter((datasetId) => datasetId !== null);
  if (!datasetIds.length) {
    return false;
  }
  return datasetIds.every((datasetId) =>
    isDatasetFastaAvailable(state.initializer?.datasets || [], datasetId),
  );
}

export function renderAssemblyFinalPathCard(state, deps = {}) {
  const {
    escapeAttr,
    escapeHtml,
    getAssemblyI18n,
    getCurrentProject,
    getDatasetNameById,
    getMeasuredTrackViewportPx: getMeasuredTrackViewportPxImpl,
  } = deps;
  if (
    typeof escapeAttr !== "function"
    || typeof escapeHtml !== "function"
    || typeof getAssemblyI18n !== "function"
    || typeof getCurrentProject !== "function"
    || typeof getDatasetNameById !== "function"
  ) {
    throw new Error("render-final-path.js missing required render dependencies");
  }
  const getMeasuredTrackViewportPx = (role = "final-path") => {
    const value = Number(getMeasuredTrackViewportPxImpl?.(role));
    return Number.isFinite(value) && value > 0 ? value : DEFAULT_TRACK_VIEWPORT_PX;
  };
  const assembly = state.assembly;
  if (assembly.loading) {
    return "";
  }
  const session = state.session || {};
  const i18n = getAssemblyI18n(state);
  const currentProject = getCurrentProject(state);
  const primaryDatasetName = getDatasetNameById(
    state.initializer?.datasets || [],
    currentProject?.primaryDatasetId,
  );
  const currentChrLabel = String(assembly.selectedChrName || "current-chr");
  const currentFinalPathChrName = resolveCurrentFinalPathChrName(assembly) || currentChrLabel;
  const finalPathDisplayEntries = buildFinalPathDisplayEntries(assembly);
  const currentFinalPath = finalPathDisplayEntries[0]?.finalPathEntry
    || getCurrentChrFinalPath(assembly)
    || (currentFinalPathChrName
      ? buildFinalPathEntry({
        chrName: currentFinalPathChrName,
        segments: [],
        updatedAt: "",
      })
      : null);
  const phasedFinalPathOptions = buildPhasedFinalPathOptions(assembly);
  const graphPreviewState = getFinalPathGraphPreviewState();
  const graphPreviewSegmentOrder =
    String(assembly.finalPathViewMode || "").trim() === "graph"
    && String(graphPreviewState?.selectedChrName || "").trim() === currentFinalPathChrName
      ? graphPreviewState.previewSegmentOrder
      : null;
  const finalPathLogModel = buildFinalPathLogModel({
    chrName: currentFinalPathChrName,
    finalPathEntry: currentFinalPath,
    finalPathByChr: assembly.finalPathByChr,
    primaryCtgs: assembly.chrCtgs,
    hiddenPrimaryCtgIds: assembly.hiddenPrimaryCtgIds,
    primaryDatasetName,
  });
  const finalPathEntriesWithLog = finalPathDisplayEntries.map((entry) => ({
    ...entry,
    graphPreviewSegmentOrder:
      String(assembly.finalPathViewMode || "").trim() === "graph"
      && String(graphPreviewState?.selectedChrName || "").trim() === entry.chrName
        ? graphPreviewState.previewSegmentOrder
        : null,
    finalPathLogModel: buildFinalPathLogModel({
      chrName: entry.chrName,
      finalPathEntry: entry.finalPathEntry,
      finalPathByChr: assembly.finalPathByChr,
      primaryCtgs: assembly.chrCtgs,
      hiddenPrimaryCtgIds: assembly.hiddenPrimaryCtgIds,
      primaryDatasetName,
    }),
  }));
  const degapRenderDeps = { escapeAttr, escapeHtml, i18n };
  const graphAddonByChr = Object.fromEntries(
    finalPathEntriesWithLog.map((entry) => [
      entry.chrName,
      renderDegapJobCard(
        { chrName: entry.chrName, degap: assembly.degap },
        degapRenderDeps,
      ),
    ]),
  );
  const grtBaselineEntry = finalPathEntriesWithLog.length === 1
    ? assembly.grtProjectView?.baselineFinalPathByChr?.[currentFinalPathChrName] || null
    : null;
  const grtBaselineRestore = grtBaselineEntry
    ? {
      available: true,
      targetChrName: currentFinalPathChrName,
      current: areFinalPathEntriesSemanticallyEqual(currentFinalPath, grtBaselineEntry),
    }
    : { available: false };
  return renderFinalPathCard(
    {
      projectName: String(session.projectName || session.projectId || "project"),
      chrName: currentFinalPathChrName,
      finalPathEntry: currentFinalPath,
      viewMode: assembly.finalPathViewMode,
      trackView: assembly.finalPathTrackView,
      trackViewportPx: getMeasuredTrackViewportPx("final-path"),
      primaryDatasetName,
      graphPreviewSegmentOrder,
      graphAddonByChr,
      degapRuntimeBody: renderDegapRuntime({ degap: assembly.degap }, degapRenderDeps),
      canExportFasta: canProjectExportFinalPathFasta(state, currentProject),
      canExportDegapJobs: Array.isArray(assembly.degap?.jobs) && assembly.degap.jobs.length > 0,
      finalPathLogModel,
      phasedFinalPathOptions,
      finalPathEntries: finalPathEntriesWithLog,
      grtBaselineRestore,
    },
    {
      escapeAttr,
      escapeHtml,
      i18n,
    },
  );
}
