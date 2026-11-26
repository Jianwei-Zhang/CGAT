import { consumePreparedOverviewSources, hasPreparedOverviewSources, validatePreparedOverviewSources } from "./project-overview-preparation.js";
import { groupProjectOverviewSources } from "./project-overview-sources.js";
import { previewMutationStamp } from "../../services/preview-content-events.js";
import { exportJobScope, currentProjectExportJob, beginProjectExportJob, ownsCurrentProjectExport,
  updateProjectExportJob, syncCurrentProjectExportJob, finishProjectExportJob } from "../../services/project-export-jobs.js";
import { renderProjectPreviewCount, renderProjectPreviewControls, applyProjectPreviewFilter, toggleAllProjectPreviewChromosomes, renderProjectPreviewPage, bindProjectPreviewPage, unbindProjectPreviewPage, restoreProjectPreviewScroll } from "./project-preview-page.js";
import { getPreviewFilterState } from "./project-overview-sections.js";
import { rememberProjectPreviewDom, restoreProjectPreviewDom } from "./project-preview-cache.js";
import {
  canExportPreviewImage, captureProjectPreviewImage, exportProjectPreviewImage,
  previewImageFormats, previewImageStillCurrent, renderProjectPreviewPng, syncPreviewExportActions,
} from "./project-preview-image-export.js";
import { previewProjectKey } from "./project-preview-state.js";
import { renderExportJobDialog } from "./export-job-dialog.js";
import { getMessages } from "../i18n/index.js";
import { projectIcon } from "./project-icons.js";
import { syncFinalPathStripGeometry } from "./assembly/final-path-visual-layout.js";
import { pickDirectoryPath, pickSaveFilePath } from "../../services/backend-api.js";
import {
  exportProjectFinalPathFasta,
  exportProjectFinalPathAgp,
  getGrtProjectView,
  getProjectAssemblyViewState,
  getProjectOverviewSources,
  listManualRefinementExports,
  listManualRefinementResults,
  writeFinalPathExportBinaryFile,
  writeFinalPathExportTextFile,
} from "../../services/workflow-api.js";
import {
  confirmedAgpOutputs,
  pickAgpExportPath,
  appendTimestampToOutputPath,
  buildTimestampedExportBaseName,
  resolveExportTimestamp,
} from "./assembly/final-path-export-runtime.js";
import { bindFloatingSubmenus } from "./floating-submenu-runtime.js";
import { FLOATING_MENU_CLOSE_DELAY_MS, bindDelegatedDelayedFloatingClose } from "./floating-menu-runtime.js";
import {
  canonicalizeFinalPathOverallLengths,
  normalizeFinalPathByChr,
  isFinalPathCtgSegment,
  isFinalPathGapSegment,
  isFinalPathRefSegment,
  isFinalPathRefinementPatchSegment,
  resolveFinalPathSegmentDisplayName,
  resolveFinalPathSegmentLengthBp,
  resolveFinalPathTotalLengthBp,
} from "./assembly/final-path-state.js";
import { normalizeGrtProjectView } from "./assembly/grt-state.js";
import { normalizeHiddenPrimaryCtgIds } from "./assembly/selection-state.js";
import { buildProjectExportLogText, buildProjectExportStatsModel } from "./project-export-state.js";
import { buildEmptyProjectExportState } from "../shell/session-switchers.js";
import { renderProjectRefinementCard } from "./project-refinement-view.js";
import { flushAssemblyProjectState } from "./assembly-page.js";
import {
  executeFrozenManualRefinementExport,
  isSameRefinementExportProject,
  prepareFrozenManualRefinementAllPreview,
  renderManualRefinementExportPreviewModal,
} from "./manual-refinement-export-preview.js";

const OVERVIEW_PREVIEW_BOUND = Symbol("overviewPreviewBound");
const PROJECT_DATA_FRESHNESS_BOUND = Symbol("projectDataFreshnessBound");
const projectDataRequests = new WeakMap();
const PROJECT_EXPORT_BOUND = Symbol("projectExportBound");
const projectExportSubmenuBindings = new WeakMap();
const PROJECT_EXPORT_MENU_CLOSE_TIMER = "__projectExportMenuCloseTimer";
const PROJECT_EXPORT_DETAIL_FILTER_KEYS = new Set(["type", "chr", "dataset"]);
const PROJECT_EXPORT_DETAIL_FILTER_NONE = "__project_export_filter_none__";
const projectExportDetailFilterCloseTimers = new WeakMap();

function normalizeString(value) {
  return String(value || "").trim();
}

function getNumericChromosomeNumber(name) {
  const match = normalizeString(name).match(/^(?:chr)?0*(\d+)$/i);
  if (!match) {
    return null;
  }
  const numeric = Number(match[1]);
  return Number.isSafeInteger(numeric) && numeric > 0 ? numeric : null;
}

function buildProjectExportChromosomeOrder(names) {
  const normalizedNames = [];
  const seenNames = new Set();
  (Array.isArray(names) ? names : []).forEach((name) => {
    const normalizedName = normalizeString(name);
    if (!normalizedName || seenNames.has(normalizedName)) {
      return;
    }
    seenNames.add(normalizedName);
    normalizedNames.push(normalizedName);
  });

  // Keep nonnumeric source slots stable and sort only numeric names so the
  // ordering remains total even when the two name kinds are mixed.
  const numericPositions = [];
  const numericNames = [];
  normalizedNames.forEach((name, index) => {
    const numeric = getNumericChromosomeNumber(name);
    if (numeric === null) {
      return;
    }
    numericPositions.push(index);
    numericNames.push({ name, numeric, sourceIndex: index });
  });
  numericNames.sort((left, right) => left.numeric - right.numeric || left.sourceIndex - right.sourceIndex);

  const orderedNames = [...normalizedNames];
  numericPositions.forEach((position, index) => {
    orderedNames[position] = numericNames[index].name;
  });
  return new Map(orderedNames.map((name, index) => [name, index]));
}

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function normalizeDatasetId(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.trunc(numeric) : null;
}

function isProjectExportStateForCurrentSession(state) {
  const currentProjectId = Number(state?.session?.projectId || 0);
  const exportProjectId = Number(state?.projectExport?.projectId || 0);
  if (!currentProjectId || !exportProjectId || currentProjectId !== exportProjectId) {
    return false;
  }
  const exportWorkspacePath = normalizeString(state?.projectExport?.workspacePath);
  return !exportWorkspacePath || exportWorkspacePath === normalizeString(state?.session?.workspacePath);
}

function getScopedProjectExportState(state) {
  return isProjectExportStateForCurrentSession(state)
    ? (state?.projectExport || {})
    : buildEmptyProjectExportState();
}

function projectDataMutationStamp(state) {
  return previewMutationStamp({ workspaceRoot: state.session?.workspacePath, projectId: state.session?.projectId });
}
function isProjectOverviewDataFresh(state) {
  const data = getScopedProjectExportState(state);
  return data.loaded === true && data.mutationStamp === projectDataMutationStamp(state);
}

function mergePositiveIntegerLists(...sources) {
  const merged = new Set();
  sources.forEach((source) => {
    normalizeHiddenPrimaryCtgIds(source).forEach((id) => merged.add(id));
  });
  return Array.from(merged.values());
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

function formatNumber(value) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? Math.trunc(numeric).toLocaleString("en-US") : "0";
}


function buildProjectExportOriginIdByCtgId(state) {
  const byId = new Map();
  const exportState = getScopedProjectExportState(state);
  const visit = (ctgs) => {
    (Array.isArray(ctgs) ? ctgs : []).forEach((ctg) => {
      const assemblyCtgId = Number(ctg?.assemblyCtgId || 0);
      const originId = normalizeString(ctg?.originId ?? ctg?.origin_id);
      if (assemblyCtgId > 0 && originId && !byId.has(assemblyCtgId)) {
        byId.set(assemblyCtgId, originId);
      }
    });
  };
  Object.values(exportState.ctgsByChr || {}).forEach(visit);
  Object.values(exportState.primaryCtgsByChr || {}).forEach(visit);
  visit(state?.assembly?.chrCtgs);
  visit(state?.assembly?.supportChrCtgs);
  visit(state?.assembly?.supportMirroredCtgs);
  return byId;
}

function enrichProjectFinalPathEntriesForExport(entries, state) {
  const originIdByCtgId = buildProjectExportOriginIdByCtgId(state);
  return (Array.isArray(entries) ? entries : []).map((row) => {
    const segments = Array.isArray(row?.entry?.segments) ? row.entry.segments : [];
    let changed = false;
    const nextSegments = segments.map((segment, index) => {
      if (
        !segment
        || typeof segment !== "object"
        || isFinalPathGapSegment(segment)
        || isFinalPathRefSegment(segment)
        || isFinalPathRefinementPatchSegment(segment)
        || normalizeString(segment?.originId)
      ) {
        return segment;
      }
      const assemblyCtgId = Number(segment?.assemblyCtgId || 0);
      const originId = assemblyCtgId > 0 ? originIdByCtgId.get(assemblyCtgId) || "" : "";
      if (!originId) {
        const chrName = normalizeString(row?.chrName || row?.entry?.chrName);
        throw new Error(
          `Missing Origin ID for ${chrName || "final path"} row ${index + 1}; refresh project data or rebuild this final path before TSV export.`,
        );
      }
      changed = true;
      return {
        ...segment,
        originId,
      };
    });
    if (!changed) {
      return row;
    }
    return {
      ...row,
      entry: {
        ...row.entry,
        segments: nextSegments,
      },
    };
  });
}


function mergeFinalPathByChr(...sources) {
  const merged = {};
  sources.forEach((source) => {
    const normalized = normalizeFinalPathByChr(source);
    Object.entries(source && typeof source === "object" && !Array.isArray(source) ? source : {}).forEach(([key, rawEntry]) => {
      if (!rawEntry || typeof rawEntry !== "object" || !Array.isArray(rawEntry.segments)) {
        return;
      }
      const chrName = normalizeString(rawEntry.chrName || key);
      if (!chrName) {
        return;
      }
      merged[chrName] = {
        ...rawEntry,
        chrName,
      };
    });
    Object.entries(normalized).forEach(([chrName, entry]) => {
      merged[chrName] = entry;
    });
  });
  return merged;
}

function getProjectExportFinalPathByChr(state) {
  const exportState = getScopedProjectExportState(state);
  const merged = mergeFinalPathByChr(
    exportState.finalPathByChr,
    state?.assembly?.finalPathByChr,
  );
  return expandProjectFinalPathByChrForPhasedTracks(state, merged);
}

function normalizePhasedTrackMap(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  const result = {};
  Object.entries(value).forEach(([parentChrName, tracks]) => {
    const normalizedParentChrName = normalizeString(parentChrName);
    if (!normalizedParentChrName) {
      return;
    }
    const normalizedTracks = (Array.isArray(tracks) ? tracks : [])
      .map((track, index) => {
        const haplotypeKey = normalizeString(track?.haplotypeKey);
        const label = normalizeString(track?.label);
        if (!haplotypeKey || !label) {
          return null;
        }
        return {
          ...track,
          haplotypeKey,
          label,
          displayOrder: Number.isFinite(Number(track?.displayOrder))
            ? Number(track.displayOrder)
            : index + 1,
        };
      })
      .filter(Boolean)
      .sort((left, right) =>
        left.displayOrder - right.displayOrder || left.haplotypeKey.localeCompare(right.haplotypeKey),
      );
    if (normalizedTracks.length) {
      result[normalizedParentChrName] = normalizedTracks;
    }
  });
  return result;
}

function getProjectExportPhasedChrTracksByChr(state) {
  const exportState = getScopedProjectExportState(state);
  const fromProjectExport = normalizePhasedTrackMap(exportState.phasedChrTracksByChr);
  const assemblyChrName = normalizeString(state?.assembly?.selectedChrName);
  const assemblyTracks = Array.isArray(state?.assembly?.phasedChrTracks) ? state.assembly.phasedChrTracks : [];
  if (assemblyChrName && assemblyTracks.length && !fromProjectExport[assemblyChrName]) {
    const normalizedAssemblyTracks = normalizePhasedTrackMap({ [assemblyChrName]: assemblyTracks });
    return {
      ...fromProjectExport,
      ...normalizedAssemblyTracks,
    };
  }
  return fromProjectExport;
}

function expandProjectFinalPathByChrForPhasedTracks(state, finalPathByChr) {
  const currentProject = getCurrentProject(state);
  if (!currentProject?.phasedAssemblyEnabled) {
    return finalPathByChr;
  }
  const phasedTracksByChr = getProjectExportPhasedChrTracksByChr(state);
  if (!Object.keys(phasedTracksByChr).length) {
    return finalPathByChr;
  }
  const source = finalPathByChr && typeof finalPathByChr === "object" && !Array.isArray(finalPathByChr)
    ? finalPathByChr
    : {};
  const expanded = {};
  const exportState = getScopedProjectExportState(state);
  const chromosomes = Array.isArray(exportState.chromosomes)
    ? exportState.chromosomes
    : Array.isArray(state?.assembly?.chromosomes)
      ? state.assembly.chromosomes
      : [];
  const orderedParentNames = chromosomes
    .map((chr) => normalizeString(chr?.chrName))
    .filter(Boolean);
  Object.keys(source).forEach((chrName) => {
    if (!orderedParentNames.includes(chrName) && !hasOwn(phasedTracksByChr, chrName)) {
      orderedParentNames.push(chrName);
    }
  });
  orderedParentNames.forEach((parentChrName) => {
    const tracks = phasedTracksByChr[parentChrName] || [];
    if (!tracks.length) {
      if (source[parentChrName]) {
        expanded[parentChrName] = source[parentChrName];
      }
      return;
    }
    tracks.forEach((track) => {
      const entry = source[track.label];
      if (entry) {
        expanded[track.label] = {
          ...entry,
          chrName: track.label,
        };
      }
    });
  });
  Object.entries(source).forEach(([chrName, entry]) => {
    const belongsToPhasedParent = Object.values(phasedTracksByChr)
      .some((tracks) => tracks.some((track) => track.label === chrName));
    const isPhasedParent = hasOwn(phasedTracksByChr, chrName);
    if (!isPhasedParent && !belongsToPhasedParent && !expanded[chrName]) {
      expanded[chrName] = entry;
    }
  });
  return expanded;
}

function getProjectExportHiddenPrimaryCtgIdsByChr(state, finalPathByChr = getProjectExportFinalPathByChr(state)) {
  const hiddenByChr = {};
  Object.entries(finalPathByChr && typeof finalPathByChr === "object" && !Array.isArray(finalPathByChr) ? finalPathByChr : {})
    .forEach(([key, entry]) => {
      const chrName = normalizeString(entry?.chrName || key);
      const hiddenIds = normalizeHiddenPrimaryCtgIds(entry?.hiddenPrimaryCtgIds);
      if (chrName && hiddenIds.length) {
        hiddenByChr[chrName] = mergePositiveIntegerLists(hiddenByChr[chrName], hiddenIds);
      }
    });
  const exportState = getScopedProjectExportState(state);
  const exportedHiddenByChr = exportState.hiddenPrimaryCtgIdsByChr;
  Object.entries(exportedHiddenByChr && typeof exportedHiddenByChr === "object" && !Array.isArray(exportedHiddenByChr) ? exportedHiddenByChr : {})
    .forEach(([key, hiddenIds]) => {
      const chrName = normalizeString(key);
      const normalizedHiddenIds = normalizeHiddenPrimaryCtgIds(hiddenIds);
      if (chrName && normalizedHiddenIds.length) {
        hiddenByChr[chrName] = mergePositiveIntegerLists(hiddenByChr[chrName], normalizedHiddenIds);
      }
    });
  const selectedChrName = normalizeString(state?.assembly?.selectedChrName);
  const selectedHiddenIds = mergePositiveIntegerLists(
    exportState.hiddenPrimaryCtgIds,
    state?.assembly?.hiddenPrimaryCtgIds,
  );
  if (selectedChrName && selectedHiddenIds.length) {
    hiddenByChr[selectedChrName] = mergePositiveIntegerLists(hiddenByChr[selectedChrName], selectedHiddenIds);
  }
  return hiddenByChr;
}

function expandPrimaryCtgsByChrForPhasedTracks(state, primaryCtgsByChr = {}) {
  const currentProject = getCurrentProject(state);
  if (!currentProject?.phasedAssemblyEnabled) {
    return primaryCtgsByChr;
  }
  const phasedTracksByChr = getProjectExportPhasedChrTracksByChr(state);
  if (!Object.keys(phasedTracksByChr).length) {
    return primaryCtgsByChr;
  }
  const expanded = {
    ...(primaryCtgsByChr && typeof primaryCtgsByChr === "object" && !Array.isArray(primaryCtgsByChr)
      ? primaryCtgsByChr
      : {}),
  };
  Object.entries(phasedTracksByChr).forEach(([parentChrName, tracks]) => {
    const parentCtgs = Array.isArray(primaryCtgsByChr?.[parentChrName]) ? primaryCtgsByChr[parentChrName] : [];
    tracks.forEach((track) => {
      expanded[track.label] = parentCtgs;
    });
  });
  return expanded;
}

function getLabels(state) {
  const exportImage = getMessages(state, "projectPreview").exportImage;
  if (state?.locale === "en") {
    return {
      title: "Overview",
      pathOverviewTitle: "Pseudomolecule Preview",
      assemblyStatistics: "Assembly statistics",
      pathOverviewEmpty: "No Final Path available for this assembly.",
      contentChanged: "Assembly content changed while loading. Refresh after the operation finishes.",
      noProject: "Select an assembly first.",
      project: "Assembly",
      primaryDataset: "Primary dataset",
      auxiliaryDatasets: "Auxiliary datasets",
      noAuxiliaryDatasets: "Not configured",
      reference: "Reference",
      loadFailed: "Failed to load overview data.",
      loading: "Loading overview data...",
      refresh: "Refresh",
      export: "Export",
      exportAll: "All Assembly Outputs",
      exportAllHint: "Includes one PNG preview and all available assembly outputs. The refinement task bundle is separate.",
      exportImage,
      exportTsv: "Path Details",
      exportFasta: "Sequence",
      exportAgp: "Layout",
      exportAgpOnly: "Layout (AGP only)",
      exportLog: "Contig Usage",
      exportRefinementAll: "Refinement Tasks",
      refDisabled: "A Final Path in this assembly contains reference objects. Assembly statistics cannot be displayed, and Contig Usage cannot be exported. Other outputs remain available.",
      placedStats: "Placed statistics",
      countLabel: "Count",
      lengthLabel: "Length",
      primaryCount: "Used primary contig count",
      primaryLength: "Used primary contig length",
      assignment: "Primary dataset assignment",
      appended: "Appended",
      hidden: "Hidden",
      placed: "Placed",
      placedUsed: "Placed & Used",
      placedNotUsed: "Placed & Not Used",
      unassigned: "Unassigned",
      supportType: "Auxiliary contig usage",
      supportTypeOption: "Auxiliary Contig Usage",
      otherChrType: "Repeated primary contig usage",
      otherChrTypeOption: "Repeated Primary Contig Usage",
      detailTitle: "Assembly Details",
      detailType: "Type",
      detailChromosome: "Chromosome",
      detailDataset: "Dataset",
      detailOrigin: "Origin ID",
      detailStart: "Path start",
      detailEnd: "Path end",
      detailLength: "Length (bp)",
      detailUsedBy: "Used by chromosomes",
      detailFilter: "{label} filter",
      detailAscending: "Ascending",
      detailDescending: "Descending",
      detailCount: "{count} records",
      collapse: "Collapse",
      expand: "Expand",
      noRows: "No rows",
      exporting: "Exporting...",
      all: "All",
    };
  }
  return {
    title: "概览",
    pathOverviewTitle: "假分子预览",
    assemblyStatistics: "装配统计",
    pathOverviewEmpty: "当前组装暂无可用的 Final Path。",
    contentChanged: "加载期间组装内容发生变化，请在操作结束后刷新。",
    noProject: "请先选择组装。",
    project: "组装",
    primaryDataset: "主数据集",
    auxiliaryDatasets: "辅助数据集",
    noAuxiliaryDatasets: "未配置",
    reference: "参考",
    loadFailed: "概览数据加载失败。",
    loading: "正在加载概览数据...",
    refresh: "刷新",
    export: "导出",
    exportAll: "全部组装结果",
    exportAllHint: "包含可用的组装结果和一张 PNG 预览图，不含精修任务包。",
    exportImage,
    exportTsv: "路径明细",
    exportFasta: "组装序列",
    exportAgp: "组装结构",
    exportAgpOnly: "组装结构（仅 AGP）",
    exportLog: "Contig 使用统计",
    exportRefinementAll: "精修任务",
    refDisabled: "当前组装的 Final Path 包含参考序列对象，无法显示装配统计，也不能导出 Contig 使用统计。其他结果仍可导出。",
    placedStats: "已放置统计",
    countLabel: "数目",
    lengthLabel: "长度",
    primaryCount: "已使用主组装 Contig 数量",
    primaryLength: "已使用主组装 Contig 长度",
    assignment: "主数据集分配统计",
    appended: "实际追加",
    hidden: "主图已隐藏",
    placed: "已放置",
    placedUsed: "已放置且已使用",
    placedNotUsed: "已放置但未使用",
    unassigned: "未分配",
    supportType: "辅助组装 Contig 使用情况",
    supportTypeOption: "辅助组装 Contig 使用情况",
    otherChrType: "重复主组装 Contig 使用情况",
    otherChrTypeOption: "重复主组装 Contig 使用情况",
    detailTitle: "组装明细",
    detailType: "类型",
    detailChromosome: "染色体",
    detailDataset: "数据集",
    detailOrigin: "来源 ID",
    detailStart: "路径起点",
    detailEnd: "路径终点",
    detailLength: "长度 (bp)",
    detailUsedBy: "使用染色体",
    detailFilter: "{label}筛选",
    detailAscending: "升序",
    detailDescending: "降序",
    detailCount: "{count} 条记录",
    collapse: "收起",
    expand: "展开",
    noRows: "暂无记录",
    exporting: "正在导出...",
    all: "全部",
  };
}

function renderLegend(items) {
  return `
    <div class="project-export-legend" aria-hidden="true">
      ${items.map((item) => `
        <span><i class="${escapeAttr(item.swatchClass)}"></i>${escapeHtml(item.label)}</span>
      `).join("")}
    </div>
  `;
}

function getCurrentProject(state) {
  const projectId = Number(state?.session?.projectId || 0);
  if (!projectId || !Array.isArray(state?.initializer?.existingProjects)) {
    return null;
  }
  return state.initializer.existingProjects.find((project) => Number(project?.projectId || 0) === projectId) || null;
}

function getDatasetNameById(datasets, datasetId) {
  const normalizedDatasetId = Number(datasetId || 0);
  if (!normalizedDatasetId || !Array.isArray(datasets)) {
    return "";
  }
  const matched = datasets.find((dataset) => Number(dataset?.datasetId || 0) === normalizedDatasetId);
  return String(matched?.name || matched?.label || "");
}

function isDatasetFastaAvailable(datasets, datasetId) {
  const normalizedDatasetId = normalizeDatasetId(datasetId);
  if (!normalizedDatasetId || !Array.isArray(datasets)) {
    return false;
  }
  const matched = datasets.find((dataset) => Number(dataset?.datasetId || 0) === normalizedDatasetId);
  return matched ? matched.fastaAvailable !== false : true;
}

function canProjectExportFasta(state) {
  const currentProject = getCurrentProject(state);
  if (!currentProject) {
    return false;
  }
  const datasetIds = [
    normalizeDatasetId(currentProject.primaryDatasetId),
    ...(Array.isArray(currentProject.supportDatasetIds) ? currentProject.supportDatasetIds : [])
      .map((datasetId) => normalizeDatasetId(datasetId)),
  ].filter((datasetId) => datasetId !== null);
  return datasetIds.length > 0 && datasetIds.every((datasetId) =>
    isDatasetFastaAvailable(state?.initializer?.datasets || [], datasetId),
  );
}

function joinOutputPath(directoryPath, fileName) {
  const base = String(directoryPath || "").trim().replace(/[\\/]+$/, "");
  const separator = base.includes("\\") ? "\\" : "/";
  return `${base}${separator}${String(fileName || "").trim()}`;
}

function buildProjectFinalPathExportBaseName(projectName) {
  const normalizedProjectName = normalizeString(projectName) || "project";
  return `${normalizedProjectName}_project_path`;
}

function buildProjectFinalPathByChr(entries) {
  const byChr = {};
  (Array.isArray(entries) ? entries : []).forEach(({ chrName, entry }) => {
    const normalizedChrName = normalizeString(chrName || entry?.chrName);
    if (normalizedChrName && Array.isArray(entry?.segments) && entry.segments.length) {
      byChr[normalizedChrName] = {
        ...entry,
        chrName: normalizedChrName,
      };
    }
  });
  return byChr;
}

function buildProjectFinalPathTsvText(entries) {
  const rows = [
    "Chr\t#\tCtg\tOrigin ID\toverall_len\torient\tCtg_start\tCtg_end\tChr_start\tChr_end",
  ];
  (Array.isArray(entries) ? entries : []).forEach(({ chrName, entry }) => {
    let chrCursor = 1;
    const segments = Array.isArray(entry?.segments) ? entry.segments : [];
    segments.forEach((segment, index) => {
      const segmentLengthBp = Math.max(0, resolveFinalPathSegmentLengthBp(segment));
      const chrStart = chrCursor;
      const chrEnd = chrStart + segmentLengthBp - 1;
      chrCursor = chrEnd + 1;
      if (isFinalPathGapSegment(segment)) {
        rows.push([
          chrName,
          index + 1,
          "Gap",
          "NA",
          segmentLengthBp,
          "NA",
          1,
          segmentLengthBp,
          chrStart,
          chrEnd,
        ].join("\t"));
        return;
      }
      rows.push([
        chrName,
        index + 1,
        resolveFinalPathSegmentDisplayName(segment),
        normalizeString(segment?.originId),
        normalizeString(segment?.overallLen),
        Number(segment?.start) > Number(segment?.end) ? "-" : "+",
        normalizeString(segment?.start),
        normalizeString(segment?.end),
        chrStart,
        chrEnd,
      ].join("\t"));
    });
  });
  return `${rows.join("\n")}\n`;
}

function buildProjectExportDataModel(state) {
  const exportState = getScopedProjectExportState(state);
  const currentProject = getCurrentProject(state);
  const primaryDatasetName = getDatasetNameById(
    state?.initializer?.datasets || [],
    currentProject?.primaryDatasetId,
  );
  const finalPathByChr = getProjectExportFinalPathByChr(state);
  const primaryCtgsByChr = expandPrimaryCtgsByChrForPhasedTracks(
    state,
    exportState.primaryCtgsByChr || {},
  );
  return buildProjectExportStatsModel({
    chromosomes: exportState.chromosomes || state?.assembly?.chromosomes || [],
    finalPathByChr,
    primaryCtgsByChr,
    hiddenPrimaryCtgIdsByChr: getProjectExportHiddenPrimaryCtgIdsByChr(state, finalPathByChr),
    primaryDatasetName,
    unplacedCtgCount: exportState.unplacedCtgCount || state?.assembly?.unplacedCtgCount || 0,
    unplacedBp: exportState.unplacedBp || state?.assembly?.unplacedBp || 0,
  });
}

function renderRatioBar({
  appended,
  hidden,
  total,
  appendedTitle,
  hiddenTitle,
}) {
  const denominator = Math.max(0, Number(total || 0));
  const appendedValue = Math.max(0, Number(appended || 0));
  const hiddenValue = Math.max(0, Number(hidden || 0));
  if (denominator <= 0 || appendedValue + hiddenValue <= 0) {
    return `<span class="final-path-log-ratio-bar" aria-hidden="true"></span>`;
  }
  const appendedPct = Math.min(100, (appendedValue / denominator) * 100);
  const hiddenPct = Math.min(100 - appendedPct, (hiddenValue / denominator) * 100);
  return `
    <span class="final-path-log-ratio-bar" role="img" aria-label="${escapeAttr([appendedTitle, hiddenTitle].filter(Boolean).join("; "))}">
      <span class="final-path-log-ratio-segment is-appended" style="width: ${appendedPct.toFixed(3)}%" data-app-tooltip="${escapeAttr(appendedTitle || "")}"></span>
      <span class="final-path-log-ratio-segment is-log-hidden" style="width: ${hiddenPct.toFixed(3)}%" data-app-tooltip="${escapeAttr(hiddenTitle || "")}"></span>
    </span>
  `;
}

function renderUsedMetric({
  label,
  value,
  appended,
  hidden,
  total,
  appendedTitle,
  hiddenTitle,
}) {
  return `
    <div class="project-export-used-row">
      <span>${escapeHtml(label)}</span>
      ${renderRatioBar({
        appended,
        hidden,
        total,
        appendedTitle,
        hiddenTitle,
      })}
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderAssignmentValue(parts) {
  return `
    <strong class="project-export-assignment-value">
      ${parts.map((part, index) => `
        <span class="project-export-assignment-value-token">
          ${index > 0 ? `<span class="project-export-assignment-value-separator">/</span>` : ""}
          <span class="project-export-assignment-value-part" data-app-tooltip="${escapeAttr(part.title)}">${escapeHtml(part.text)}</span>
        </span>
      `).join("")}
    </strong>
  `;
}

function renderAssignmentBar({ label, values, valueParts }) {
  const total = values.reduce((sum, item) => sum + Math.max(0, Number(item.value || 0)), 0);
  return `
    <div class="project-export-assignment-row">
      <span>${escapeHtml(label)}</span>
      <span class="project-export-assignment-bar" role="img" aria-label="${escapeAttr(values.map((item) => item.title).join("; "))}">
        ${values.map((item) => {
          const value = Math.max(0, Number(item.value || 0));
          const width = total > 0 ? (value / total) * 100 : 0;
          return `<span class="project-export-assignment-segment ${escapeAttr(item.className)}" style="width: ${width.toFixed(3)}%" data-app-tooltip="${escapeAttr(item.title)}"></span>`;
        }).join("")}
      </span>
      ${renderAssignmentValue(valueParts)}
    </div>
  `;
}

function renderAssignmentStats(model, labels) {
  const usedCount = Math.max(0, Number(model.assignment.usedCount || 0));
  const placedNotUsedCount = Math.max(0, Number(model.assignment.placedNotUsedCount || 0));
  const unassignedCount = Math.max(0, Number(model.assignment.unassignedCount || 0));
  const usedBp = Math.max(0, Number(model.assignment.usedBp || 0));
  const placedNotUsedBp = Math.max(0, Number(model.assignment.placedNotUsedBp || 0));
  const unassignedBp = Math.max(0, Number(model.assignment.unassignedBp || 0));
  const placedCount = usedCount + placedNotUsedCount;
  const placedBp = usedBp + placedNotUsedBp;
  const totalCount = placedCount + unassignedCount;
  const totalBp = placedBp + unassignedBp;
  const placedItem = {
    label: labels.placed,
    count: placedCount,
    bp: placedBp,
    className: "is-placed",
    swatchClass: "project-export-swatch is-placed",
  };
  const unassignedItem = {
    label: labels.unassigned,
    count: unassignedCount,
    bp: unassignedBp,
    className: "is-unassigned",
    swatchClass: "project-export-swatch is-unassigned",
  };
  const items = [
    placedItem,
    unassignedItem,
  ];
  return `
    <div class="project-export-assignment">
      ${renderAssignmentBar({
        label: labels.countLabel,
        values: items.map((item) => ({
          value: item.count,
          className: item.className,
          title: `${item.label}: ${formatNumber(item.count)}`,
        })),
        valueParts: [
          {
            text: formatNumber(placedCount),
            title: `${labels.placed}: ${formatNumber(placedCount)}`,
          },
          {
            text: formatNumber(totalCount),
            title: `${labels.placed} + ${labels.unassigned}: ${formatNumber(totalCount)}`,
          },
        ],
      })}
      ${renderAssignmentBar({
        label: labels.lengthLabel,
        values: items.map((item) => ({
          value: item.bp,
          className: item.className,
          title: `${item.label}: ${formatNumber(item.bp)} bp`,
        })),
        valueParts: [
          {
            text: formatNumber(placedBp),
            title: `${labels.placed}: ${formatNumber(placedBp)} bp`,
          },
          {
            text: formatNumber(totalBp),
            title: `${labels.placed} + ${labels.unassigned}: ${formatNumber(totalBp)} bp`,
          },
        ],
      })}
    </div>
  `;
}

function buildDetailRows(model, labels) {
  return [
    ...(Array.isArray(model.supportRows) ? model.supportRows : []).map((row) => ({
      ...row,
      type: "support",
      typeLabel: labels.supportType,
      typeOptionLabel: labels.supportTypeOption,
      usedByChrNames: [row.chrName],
    })),
    ...(Array.isArray(model.otherChrPrimaryRows) ? model.otherChrPrimaryRows : []).map((row) => ({
      ...row,
      type: "other_chr_primary",
      typeLabel: labels.otherChrType,
      typeOptionLabel: labels.otherChrTypeOption,
    })),
  ];
}

function normalizeDetailFilterValues(value) {
  const values = Array.isArray(value) ? value : [value];
  const normalizedValues = [];
  const seen = new Set();
  values.forEach((item) => {
    const normalized = normalizeString(item);
    if (!normalized || seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    normalizedValues.push(normalized);
  });
  return normalizedValues;
}

function getProjectExportDetailFilterOptions(state, filterKey) {
  const normalizedKey = normalizeString(filterKey);
  if (!PROJECT_EXPORT_DETAIL_FILTER_KEYS.has(normalizedKey)) {
    return [];
  }
  return getDetailFilterOptions(
    buildDetailRows(buildProjectExportDataModel(state), getLabels(state)),
    normalizedKey,
  );
}

function normalizeDetailTableState(state) {
  const rawFilters = state?.projectExport?.detailTableFilters || {};
  const filters = {
    type: normalizeDetailFilterValues(rawFilters.type),
    chr: normalizeDetailFilterValues(rawFilters.chr),
    dataset: normalizeDetailFilterValues(rawFilters.dataset),
  };
  const rawSort = state?.projectExport?.detailTableSort || {};
  const direction = normalizeString(rawSort.direction).toLowerCase();
  return {
    filters,
    collapsed: state?.projectExport?.detailTableCollapsed !== false,
    sort: {
      key: normalizeString(rawSort.key) === "length_bp" ? "length_bp" : "",
      direction: direction === "asc" || direction === "desc" ? direction : "",
    },
  };
}

function getDetailFilterValue(row, filterKey) {
  if (filterKey === "type") {
    return normalizeString(row.type);
  }
  if (filterKey === "chr") {
    return normalizeString(row.chrName);
  }
  if (filterKey === "dataset") {
    return normalizeString(row.datasetName);
  }
  return "";
}

function getDetailFilterLabel(row, filterKey) {
  if (filterKey === "type") {
    return normalizeString(row.typeOptionLabel || row.typeLabel);
  }
  return getDetailFilterValue(row, filterKey);
}

function getDetailFilterOptions(rows, filterKey) {
  const byValue = new Map();
  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const value = getDetailFilterValue(row, filterKey);
    if (!value || byValue.has(value)) {
      return;
    }
    byValue.set(value, getDetailFilterLabel(row, filterKey));
  });
  return Array.from(byValue.entries())
    .map(([value, label]) => ({ value, label }))
    .sort((left, right) => left.label.localeCompare(right.label));
}

function filterDetailRows(rows, filters) {
  return (Array.isArray(rows) ? rows : []).filter((row) =>
    Array.from(PROJECT_EXPORT_DETAIL_FILTER_KEYS).every((filterKey) => {
      const selectedValues = normalizeDetailFilterValues(filters?.[filterKey]);
      if (selectedValues.includes(PROJECT_EXPORT_DETAIL_FILTER_NONE)) {
        return false;
      }
      return !selectedValues.length || selectedValues.includes(getDetailFilterValue(row, filterKey));
    }),
  );
}

function sortDetailRows(rows, sort) {
  const safeRows = Array.isArray(rows) ? [...rows] : [];
  if (sort?.key !== "length_bp" || (sort.direction !== "asc" && sort.direction !== "desc")) {
    return safeRows;
  }
  const multiplier = sort.direction === "asc" ? 1 : -1;
  return safeRows.sort((left, right) =>
    ((Number(left.lengthBp || 0) - Number(right.lengthBp || 0)) * multiplier)
    || normalizeString(left.chrName).localeCompare(normalizeString(right.chrName))
    || normalizeString(left.datasetName).localeCompare(normalizeString(right.datasetName)),
  );
}

function renderDetailFilterHeader({ label, filterKey, options, selectedValues, allLabel = "All", filterCaption = "{label} filter" }) {
  const selectedSet = new Set(normalizeDetailFilterValues(selectedValues));
  const optionValues = options.map((option) => option.value);
  const isNoneSelected = selectedSet.has(PROJECT_EXPORT_DETAIL_FILTER_NONE);
  const selectedOptionValues = optionValues.filter((value) => selectedSet.has(value));
  const isAllSelected = !isNoneSelected && (
    selectedSet.size === 0
    || (optionValues.length > 0 && selectedOptionValues.length === optionValues.length)
  );
  const isMixedSelected = !isNoneSelected && !isAllSelected && selectedOptionValues.length > 0;
  const isActive = !isAllSelected ? " is-active" : "";
  return `
    <th>
      <div class="project-export-detail-header">
        <span>${escapeHtml(label)}</span>
        <details
          class="project-export-detail-filter${isActive}"
          data-project-export-detail-filter-menu="${escapeAttr(filterKey)}"
        >
          <summary aria-label="${escapeAttr(filterCaption.replace("{label}", label))}" data-app-tooltip="${escapeAttr(filterCaption.replace("{label}", label))}"></summary>
          <div class="project-export-detail-filter-menu">
            <label>
              <input
                type="checkbox"
                data-project-export-detail-filter="${escapeAttr(filterKey)}"
                data-project-export-detail-filter-all="1"
                data-project-export-detail-filter-state="${isMixedSelected ? "mixed" : isAllSelected ? "all" : "none"}"
                value=""
                ${isAllSelected ? "checked" : ""}
              >
              <span>${escapeHtml(allLabel)}</span>
            </label>
            ${options.map((option) => `
              <label>
                <input
                  type="checkbox"
                  data-project-export-detail-filter="${escapeAttr(filterKey)}"
                  value="${escapeAttr(option.value)}"
                  ${isAllSelected || selectedSet.has(option.value) ? "checked" : ""}
                >
                <span>${escapeHtml(option.label)}</span>
              </label>
            `).join("")}
          </div>
        </details>
      </div>
    </th>
  `;
}

function renderLengthSortHeader(sort, labels) {
  const direction = sort?.key === "length_bp" ? sort.direction : "";
  const marker = direction === "asc" ? " ↑" : direction === "desc" ? " ↓" : "";
  const stateLabel = direction === "asc" ? labels.detailAscending : direction === "desc" ? labels.detailDescending : "";
  return `
    <th>
      <button
        type="button"
        class="project-export-detail-sort"
        data-project-export-detail-sort="length_bp"
        aria-label="${escapeAttr([labels.detailLength, stateLabel].filter(Boolean).join(": "))}"
      >${escapeHtml(labels.detailLength)}${escapeHtml(marker)}</button>
    </th>
  `;
}

function renderDetailRows(rows, labels) {
  const safeRows = Array.isArray(rows) ? rows : [];
  if (!safeRows.length) {
    return `<tr><td colspan="8" class="final-path-log-empty">${escapeHtml(labels.noRows)}</td></tr>`;
  }
  const rowTypeSpans = safeRows.map((row, index) => {
    const typeLabel = row.typeLabel || "";
    if (index > 0 && (safeRows[index - 1]?.typeLabel || "") === typeLabel) {
      return 0;
    }
    let span = 1;
    for (let nextIndex = index + 1; nextIndex < safeRows.length; nextIndex += 1) {
      if ((safeRows[nextIndex]?.typeLabel || "") !== typeLabel) {
        break;
      }
      span += 1;
    }
    return span;
  });
  return safeRows.map((row, index) => {
    const typeSpan = rowTypeSpans[index] || 0;
    const typeCell = typeSpan > 0
      ? `<td class="final-path-log-type-cell" rowspan="${typeSpan}"><span class="project-export-detail-type-label">${escapeHtml(row.typeLabel || "")}</span></td>`
      : "";
    return `
    <tr>
      ${typeCell}
      <td>${escapeHtml(row.chrName || "")}</td>
      <td>${escapeHtml(row.datasetName || "")}</td>
      <td>${escapeHtml(row.originId || "")}</td>
      <td>${escapeHtml(row.finalPathStart ? formatNumber(row.finalPathStart) : "")}</td>
      <td>${escapeHtml(row.finalPathEnd ? formatNumber(row.finalPathEnd) : "")}</td>
      <td>${escapeHtml(formatNumber(row.lengthBp))}</td>
      <td>${escapeHtml((row.usedByChrNames || [row.chrName]).join(", "))}</td>
    </tr>
  `;
  }).join("");
}

function renderDetailTable(model, labels, detailTableState) {
  const rows = buildDetailRows(model, labels);
  if (!rows.length) {
    return "";
  }
  const filters = detailTableState.filters || {};
  const sortedRows = sortDetailRows(filterDetailRows(rows, filters), detailTableState.sort);
  return `
    <section class="project-export-detail-section" hidden aria-labelledby="project-export-detail-title">
      <div class="project-export-detail-titlebar">
        <div class="project-export-detail-heading">
          <h4 id="project-export-detail-title">${escapeHtml(labels.detailTitle)}</h4>
          <span class="project-export-detail-count">${escapeHtml(labels.detailCount.replace("{count}", sortedRows.length === rows.length ? formatNumber(rows.length) : `${formatNumber(sortedRows.length)} / ${formatNumber(rows.length)}`))}</span>
        </div>
        <button type="button" class="project-export-detail-toggle"
          data-project-export-detail-toggle="true" aria-controls="project-export-detail-body"
          aria-expanded="${detailTableState.collapsed ? "false" : "true"}">
          ${escapeHtml(detailTableState.collapsed ? labels.expand : labels.collapse)}
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
        </button>
      </div>
      <div id="project-export-detail-body" class="final-path-log-table-wrap" tabindex="0"${detailTableState.collapsed ? " hidden" : ""}>
        <table class="final-path-log-table project-export-detail-table">
          <thead>
            <tr>
              ${renderDetailFilterHeader({
                label: labels.detailType,
                filterKey: "type",
                options: getDetailFilterOptions(rows, "type"),
                selectedValues: filters.type,
                allLabel: labels.all,
                filterCaption: labels.detailFilter,
              })}
              ${renderDetailFilterHeader({
                label: labels.detailChromosome,
                filterKey: "chr",
                options: getDetailFilterOptions(rows, "chr"),
                selectedValues: filters.chr,
                allLabel: labels.all,
                filterCaption: labels.detailFilter,
              })}
              ${renderDetailFilterHeader({
                label: labels.detailDataset,
                filterKey: "dataset",
                options: getDetailFilterOptions(rows, "dataset"),
                selectedValues: filters.dataset,
                allLabel: labels.all,
                filterCaption: labels.detailFilter,
              })}
              <th>${escapeHtml(labels.detailOrigin)}</th>
              <th>${escapeHtml(labels.detailStart)}</th>
              <th>${escapeHtml(labels.detailEnd)}</th>
              ${renderLengthSortHeader(detailTableState.sort, labels)}
              <th>${escapeHtml(labels.detailUsedBy)}</th>
            </tr>
          </thead>
          <tbody>${renderDetailRows(sortedRows, labels)}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderStats(model, labels, detailTableState = normalizeDetailTableState()) {
  if (model.statsDisabledByRef) {
    return `<p class="notice warning" hidden>${escapeHtml(labels.refDisabled)}</p>`;
  }
  return `
    <section class="project-assembly-statistics" hidden><header class="project-section-divider"><h3>${escapeHtml(labels.assemblyStatistics)}</h3></header><div class="project-export-grid">
      <article class="project-export-panel">
        <div class="project-export-panel-title">
          <h4>${escapeHtml(labels.assignment)}</h4>
          ${renderLegend([
            { label: labels.placed, swatchClass: "project-export-swatch is-placed" },
            { label: labels.unassigned, swatchClass: "project-export-swatch is-unassigned" },
          ])}
        </div>
        ${renderAssignmentStats(model, labels)}
      </article>
      <article class="project-export-panel">
        <div class="project-export-panel-title">
          <h4>${escapeHtml(labels.placedStats)}</h4>
          ${renderLegend([
            { label: labels.appended, swatchClass: "final-path-log-swatch is-appended" },
            { label: labels.hidden, swatchClass: "final-path-log-swatch is-log-hidden" },
          ])}
        </div>
        <div class="project-export-used-metrics">
          ${renderUsedMetric({
            label: labels.primaryCount,
            value: model.primaryCount.label,
            appended: model.primaryCount.appended,
            hidden: model.primaryCount.hidden,
            total: model.primaryCount.total,
            appendedTitle: `${labels.appended}: ${formatNumber(model.primaryCount.appended)}/${formatNumber(model.primaryCount.total)}`,
            hiddenTitle: `${labels.hidden}: ${formatNumber(model.primaryCount.hidden)}/${formatNumber(model.primaryCount.total)}`,
          })}
          ${renderUsedMetric({
            label: labels.primaryLength,
            value: model.primaryLength.label,
            appended: model.primaryLength.appendedBp,
            hidden: model.primaryLength.hiddenBp,
            total: model.primaryLength.totalBp,
            appendedTitle: `${labels.appended}: ${formatNumber(model.primaryLength.appendedBp)}/${formatNumber(model.primaryLength.totalBp)} bp`,
            hiddenTitle: `${labels.hidden}: ${formatNumber(model.primaryLength.hiddenBp)}/${formatNumber(model.primaryLength.totalBp)} bp`,
          })}
        </div>
      </article>
    </div></section>
    ${renderDetailTable(model, labels, detailTableState)}
  `;
}

function getFinalPathPreviewEntries(state) {
  const finalPathByChr = getProjectExportFinalPathByChr(state);
  const rawEntries = Object.entries(finalPathByChr)
    .map(([key, entry], sourceIndex) => ({
      chrName: normalizeString(entry?.chrName || key),
      parentChrName: normalizeString(entry?.chrName || key),
      phasedTrackKey: "",
      entry,
      lengthBp: Math.max(0, Number(resolveFinalPathTotalLengthBp(entry)) || 0),
      sourceIndex,
    }))
    .filter(({ chrName, entry }) => chrName && Array.isArray(entry?.segments) && entry.segments.length > 0);
  const phasedTracksByChr = getProjectExportPhasedChrTracksByChr(state);
  const phasedLabels = new Set();
  Object.values(phasedTracksByChr).forEach((tracks) => {
    (Array.isArray(tracks) ? tracks : []).forEach((track) => {
      const label = normalizeString(track?.label);
      if (label) {
        phasedLabels.add(label);
      }
    });
  });
  const chromosomeNames = [];
  const seenChromosomeNames = new Set();
  const addChromosomeName = (name) => {
    const normalizedName = normalizeString(name);
    if (!normalizedName || seenChromosomeNames.has(normalizedName)) {
      return;
    }
    seenChromosomeNames.add(normalizedName);
    chromosomeNames.push(normalizedName);
  };
  const sourceChromosomes = Array.isArray(state?.projectExport?.chromosomes)
    && state.projectExport.chromosomes.length
    ? state.projectExport.chromosomes
    : Array.isArray(state?.assembly?.chromosomes)
      ? state.assembly.chromosomes
      : [];
  sourceChromosomes.forEach((chr) => addChromosomeName(chr?.chrName));
  Object.keys(phasedTracksByChr).forEach(addChromosomeName);
  rawEntries.forEach((row) => {
    if (!phasedLabels.has(row.chrName)) {
      addChromosomeName(row.chrName);
    }
  });
  const chromosomeOrder = buildProjectExportChromosomeOrder(chromosomeNames);
  const phasedSort = new Map();
  Object.entries(phasedTracksByChr).forEach(([parentChrName, tracks]) => {
    const parentOrder = chromosomeOrder.has(parentChrName)
      ? chromosomeOrder.get(parentChrName)
      : Number.MAX_SAFE_INTEGER;
    tracks.forEach((track, index) => {
      phasedSort.set(track.label, {
        parentChrName,
        parentOrder,
        haplotypeOrder: Number.isFinite(Number(track.displayOrder)) ? Number(track.displayOrder) : index + 1,
        phasedTrackKey: track.haplotypeKey,
      });
    });
  });
  return rawEntries
    .sort((left, right) => {
      const leftPhased = phasedSort.get(left.chrName);
      const rightPhased = phasedSort.get(right.chrName);
      const leftOrder = leftPhased?.parentOrder
        ?? (chromosomeOrder.has(left.chrName) ? chromosomeOrder.get(left.chrName) : Number.MAX_SAFE_INTEGER);
      const rightOrder = rightPhased?.parentOrder
        ?? (chromosomeOrder.has(right.chrName) ? chromosomeOrder.get(right.chrName) : Number.MAX_SAFE_INTEGER);
      const leftHaplotypeOrder = leftPhased?.haplotypeOrder ?? 0;
      const rightHaplotypeOrder = rightPhased?.haplotypeOrder ?? 0;
      return leftOrder - rightOrder
        || leftHaplotypeOrder - rightHaplotypeOrder
        || left.sourceIndex - right.sourceIndex;
    })
    .map(({ sourceIndex, ...row }) => {
      const phasedInfo = phasedSort.get(row.chrName);
      if (!phasedInfo) {
        return row;
      }
      return {
        ...row,
        parentChrName: phasedInfo.parentChrName,
        phasedTrackKey: phasedInfo.phasedTrackKey,
      };
    });
}


export function renderProjectPathOverview(state) {
  return renderProjectExportPage(state, { includeExportMenu: false });
}

function projectSurfaceRoot(host) {
  const root = host?.closest?.("#route-host") || host;
  return root?.isConnected === false ? host?.ownerDocument?.querySelector?.("#route-host") || root : root;
}

function refreshProjectDataSurface(host, store) {
  const root = projectSurfaceRoot(host), state = store.getState();
  if (!root || root.isConnected === false) return;
  rerender(root, store);
}

function ensureProjectOverviewData(host, store, deps = {}) {
  const state = store.getState(), data = getScopedProjectExportState(state);
  const changed = data.mutationStamp !== projectDataMutationStamp(state);
  if (getCurrentProject(state) && !isProjectOverviewDataFresh(state) && !data.loading && (!data.error || changed)) void loadProjectExportData(host, store, deps);
}

function bindProjectDataFreshness(host, store, deps = {}) {
  const root = projectSurfaceRoot(host);
  if (!root || !store.subscribe) return;
  const current = root[PROJECT_DATA_FRESHNESS_BOUND];
  if (current?.store === store) { current.deps = { ...current.deps, ...deps }; return; }
  releaseProjectDataFreshness(root);
  const binding = { store, deps };
  root[PROJECT_DATA_FRESHNESS_BOUND] = binding;
  binding.unsubscribe = store.subscribe(() => {
    if (root.isConnected === false) { releaseProjectDataFreshness(root); return; }
    const state = binding.store.getState(), key = previewProjectKey(state);
    const surface = state.activeRoute === "importer" ? root.querySelector?.("[data-project-path-overview]")
      : state.activeRoute === "projectExport" ? root.querySelector?.("[data-overview-project]") : null;
    const scope = state.activeRoute === "importer" ? surface?.dataset?.projectPathOverview : surface?.dataset?.overviewProject;
    if (!surface || scope !== key) return;
    ensureProjectOverviewData(root, binding.store, binding.deps);
  });
}
function releaseProjectDataFreshness(host) {
  const root = host?.closest?.("#route-host") || host;
  root?.[PROJECT_DATA_FRESHNESS_BOUND]?.unsubscribe?.();
  if (root) delete root[PROJECT_DATA_FRESHNESS_BOUND];
}

export function bindProjectPathOverview(host, store, deps = {}) {
  const root = projectSurfaceRoot(host);
  if (!root?.querySelector?.("[data-project-path-overview]")) return;
  bindProjectExportPage(root, store, deps);
}

export function releaseProjectPathOverview(host) {
  releaseProjectOverviewPreview(host);
}

function resolveProjectExportJumpTarget(state, target) {
  const source = target && typeof target === "object"
    ? target
    : { selectedChrName: target };
  const explicitParentChrName = normalizeString(source?.parentChrName || "");
  const clickedChrName = normalizeString(source?.chrName || "");
  const requestedChrName = normalizeString(
    source?.selectedChrName || explicitParentChrName || clickedChrName || "",
  );
  const requestedPhasedKey = normalizeString(
    source?.activePhasedTrackKey || source?.phasedTrackKey || "",
  );
  const phasedTracksByChr = getProjectExportPhasedChrTracksByChr(state);
  if (!requestedChrName && !requestedPhasedKey) {
    return { selectedChrName: "", activePhasedTrackKey: "", activeFinalPathKey: "" };
  }
  const findPhasedTarget = (predicate) => {
    for (const [parentChrName, tracks] of Object.entries(phasedTracksByChr)) {
      const matchedTrack = tracks.find(predicate);
      if (matchedTrack) {
        const normalizedKey = normalizeString(matchedTrack?.haplotypeKey);
        return {
          selectedChrName: parentChrName,
          activePhasedTrackKey: normalizedKey,
          activeFinalPathKey: normalizedKey,
        };
      }
    }
    return null;
  };
  const labelTarget = requestedChrName
    ? findPhasedTarget((track) => normalizeString(track?.label) === requestedChrName)
    : null;
  if (labelTarget) {
    return labelTarget;
  }
  if (requestedChrName && requestedPhasedKey) {
    return {
      selectedChrName: requestedChrName,
      activePhasedTrackKey: requestedPhasedKey,
      activeFinalPathKey: requestedPhasedKey,
    };
  }
  const keyTarget = requestedPhasedKey
    ? findPhasedTarget((track) => normalizeString(track?.haplotypeKey) === requestedPhasedKey)
    : null;
  if (keyTarget) {
    return keyTarget;
  }
  return {
    selectedChrName: requestedChrName,
    activePhasedTrackKey: requestedPhasedKey,
    activeFinalPathKey: requestedPhasedKey,
  };
}

const exportLabelKeys = { agp: "exportAgp", fasta: "exportFasta", tsv: "exportTsv", log: "exportLog",
  png: "exportImage", all: "exportAll", "refinement-all": "exportRefinementAll" };

function renderProjectExportMenu({ labels, fresh, previewReady, canExportFasta, canExportLog }) {
  const item = (action, ext, attrs = "", caption = labels[exportLabelKeys[action]]) => `<button type="button" class="final-path-export-item" data-project-export-action="${action}"${attrs}>
    <span>${escapeHtml(caption)}</span>${ext ? `<span class="project-export-extension">.${ext}</span>` : ""}</button>`;
  const divider = '<div class="final-path-export-divider" role="separator"></div>';
  const pending = fresh ? "" : " disabled";
  const imagePending = previewReady ? "" : " disabled";
  const batchAttrs = fresh ? ` data-preview-required${imagePending}` : pending;
  const formats = previewImageFormats.map(format => `<button type="button" role="menuitem" class="final-path-export-item" data-preview-format="${format}" data-preview-required${imagePending}>${format.toUpperCase()}</button>`).join("");
  const label = escapeAttr(labels.export);
  return `
    <div class="final-path-export" data-project-export>
      <button type="button" class="button ghost tiny final-path-export-toggle" data-project-export-toggle="true"
        aria-label="${label}" aria-expanded="false">${projectIcon("export")}<span>${escapeHtml(labels.export)}</span></button>
      <div class="final-path-export-menu is-hidden" data-project-export-menu>
        ${item("agp", canExportFasta ? "agp + .components.fa" : "agp", pending, canExportFasta ? labels.exportAgp : labels.exportAgpOnly)}
        ${canExportFasta ? item("fasta", "fasta") : ""}
        ${item("tsv", "tsv", pending)}
        ${canExportLog ? item("log", "log") : ""}
        <div class="context-menu-submenu-group project-preview-formats" data-context-submenu-group>
          <button type="button" class="final-path-export-item context-menu-submenu-trigger" data-context-submenu-trigger aria-haspopup="menu" aria-expanded="false" data-preview-required${imagePending}>
            <span>${escapeHtml(labels.exportImage)}</span><span class="context-menu-submenu-indicator" aria-hidden="true">›</span></button>
          <div class="context-menu-submenu" data-context-submenu role="menu" aria-label="${escapeAttr(labels.exportImage)}">${formats}</div>
        </div>
        ${divider}
        ${item("all", "", `${batchAttrs} data-app-tooltip="${escapeAttr(labels.exportAllHint)}"`)}
        ${divider}
        ${item("refinement-all", "zip", pending)}
      </div>
    </div>
  `;
}

function renderProjectOverviewSummary(state) {
  const labels = getLabels(state);
  const currentProject = getCurrentProject(state);
  const exportState = getScopedProjectExportState(state);
  if (!currentProject) {
    return "";
  }
  const fresh = isProjectOverviewDataFresh(state);
  const model = fresh ? buildProjectExportDataModel(state) : null;
  return `
      <section data-overview-summary>
      ${exportState.loading || (!fresh && !exportState.error) ? `<p class="muted">${escapeHtml(labels.loading)}</p>` : ""}
      ${exportState.error ? `
        <div class="project-export-load-error" role="alert">
          <p class="error-text">${escapeHtml(labels.loadFailed)} ${escapeHtml(exportState.error)}</p>
          <button type="button" class="button ghost tiny" data-project-export-refresh="1">${escapeHtml(labels.refresh)}</button>
        </div>
      ` : ""}
      ${renderExportJobDialog({
        job: exportState.job, locale: state, scope: "project", escapeHtml,
        stepLabel: kind => labels[exportLabelKeys[kind]] || kind,
      })}
      ${renderManualRefinementExportPreviewModal(exportState.refinementExportModal, state)}
      ${fresh ? renderStats(model, labels, normalizeDetailTableState(state)) : ""}
      </section>
  `;
}

export function renderProjectGlobalExportControl(state) {
  if (!getCurrentProject(state)) {
    return "";
  }
  const labels = getLabels(state), fresh = isProjectOverviewDataFresh(state);
  return renderProjectExportMenu({
    labels,
    canExportFasta: fresh && canProjectExportFasta(state),
    canExportLog: fresh && buildProjectExportDataModel(state).canExportLog,
    fresh, previewReady: canExportPreviewImage(state),
  });
}

function renderProjectOverviewActions(state, { includeExportMenu = true } = {}) {
  return includeExportMenu ? `<div class="project-export-actions">${renderProjectGlobalExportControl(state)}</div>` : "";
}

export function renderProjectExportPage(state, { includeExportMenu = true } = {}) {
  const labels = getLabels(state);
  if (!getCurrentProject(state)) return `<section class="project-export-page project-integrated-overview" aria-label="${escapeAttr(labels.title)}"><p class="muted">${escapeHtml(labels.noProject)}</p></section>`;
  return `<section class="project-export-page project-integrated-overview" aria-label="${escapeAttr(labels.title)}" data-overview-project="${escapeAttr(previewProjectKey(state))}" data-project-path-overview="${escapeAttr(previewProjectKey(state))}">
    ${renderProjectOverviewSummary(state)}
    <header class="project-section-divider project-preview-toolbar"><h3 id="overview-preview-title">${escapeHtml(labels.pathOverviewTitle)}</h3><span data-preview-count>${renderProjectPreviewCount(state)}</span><div class="project-preview-controls" data-preview-controls>${renderProjectPreviewControls(state)}</div>${renderProjectOverviewActions(state, { includeExportMenu })}</header>
    <div data-overview-preview>${renderProjectPreviewPage(state, { embedded: true, hideHeading: true })}</div>
  </section>`;
}

function jumpToAssemblyChr(store, target) {
  const {
    selectedChrName,
    activePhasedTrackKey,
    activeFinalPathKey,
  } = resolveProjectExportJumpTarget(store.getState(), target);
  const normalizedChrName = normalizeString(selectedChrName);
  const normalizedPhasedKey = normalizeString(activePhasedTrackKey);
  const normalizedFinalPathKey = normalizeString(activeFinalPathKey);
  if (!normalizedChrName) {
    return false;
  }
  const state = store.getState();
  store.setState({
    ...state,
    activeRoute: "assembly",
    assembly: {
      ...(state.assembly || {}),
      activeTab: "assembly",
      // Queue navigation without destroying the live chromosome/session. The
      // Assembly binder owns cold loading, warm selection and error recovery.
      previewRequestedChrName: normalizedChrName,
      activePhasedTrackKey: normalizedPhasedKey,
      projectExportScrollToBottom: true,
      ...(normalizedPhasedKey
        ? {
            activePhasedTrackKeyByChr: {
              ...(state.assembly?.activePhasedTrackKeyByChr || {}),
              [normalizedChrName]: normalizedPhasedKey,
            },
          }
        : {}),
      ...(normalizedFinalPathKey
        ? {
            activeFinalPathKey: normalizedFinalPathKey,
            activeFinalPathKeyByChr: {
              ...(state.assembly?.activeFinalPathKeyByChr || {}),
              [normalizedChrName]: normalizedFinalPathKey,
            },
          }
        : {}),
    },
  });
  return true;
}

export function releaseProjectOverviewPreview(host) {
  releaseProjectDataFreshness(host);
  const previewHost = host?.querySelector?.("[data-overview-preview]");
  if (!previewHost) return;
  rememberProjectPreviewDom(previewHost);
  unbindProjectPreviewPage(previewHost);
}

function mountOverviewPreview(host, store, deps = {}) {
  const previewHost = host?.querySelector?.("[data-overview-preview]");
  if (!previewHost?.addEventListener) return;
  if (previewHost[OVERVIEW_PREVIEW_BOUND]) { restoreProjectPreviewScroll(previewHost); return; }
  previewHost[OVERVIEW_PREVIEW_BOUND] = true;
  restoreProjectPreviewDom(previewHost, store.getState());
  (deps.bindProjectPreviewPage || bindProjectPreviewPage)(previewHost, store, { ...deps.preview,
    isScrollReady: () => isProjectOverviewDataFresh(store.getState()) || Boolean(getScopedProjectExportState(store.getState()).error),
  });
}

function rerender(host, store) {
  host = projectSurfaceRoot(host);
  if (!host || host.isConnected === false) return;
  const state = store.getState();
  if (state.activeRoute && !["importer", "projectExport"].includes(state.activeRoute)) return;
  const page = host.querySelector?.("[data-overview-project]");
  const summary = page?.querySelector?.("[data-overview-summary]");
  const doc = host.ownerDocument;
  if (summary && getCurrentProject(state) && page.dataset.overviewProject === previewProjectKey(state) && doc?.createElement) {
    // Export progress/filter/statistics patches must not erase the independently
    // owned Preview component, its cache foundation, focus or pending request.
    const template = doc.createElement("template");
    template.innerHTML = renderProjectOverviewSummary(state);
    const next = template.content.querySelector("[data-overview-summary]");
    if (next) summary.replaceWith(next);
    const headerExport = host.querySelector?.(".project-header-actions [data-project-export]");
    if (headerExport) {
      const exportTpl = doc.createElement("template");
      exportTpl.innerHTML = renderProjectGlobalExportControl(state);
      const nextExport = exportTpl.content.querySelector("[data-project-export]");
      if (nextExport) headerExport.replaceWith(nextExport);
    }
    const toolbar = page.querySelector(".project-preview-toolbar .project-export-actions");
    if (toolbar && !headerExport) {
      const actions = doc.createElement("template");
      actions.innerHTML = renderProjectOverviewActions(state);
      const nextActions = actions.content.querySelector(".project-export-actions");
      if (nextActions) toolbar.replaceWith(nextActions);
    }
    const refinementNode = host.querySelector?.("#project-refinement");
    if (refinementNode) {
      const refinementTpl = doc.createElement("template");
      refinementTpl.innerHTML = renderProjectRefinementCard(state);
      const nextRefinement = refinementTpl.content.querySelector("#project-refinement");
      if (nextRefinement) refinementNode.replaceWith(nextRefinement);
    }
  } else {
    if (state.activeRoute === "importer") return;
    releaseProjectOverviewPreview(host);
    host.innerHTML = renderProjectExportPage(state);
  }
  bindProjectExportPage(host, store);
  syncProjectExportDetailFilterControls(host);
  syncProjectExportPreviewLabels(host);
}

function setProjectExportJob(host, store, nextJob, owner) {
  updateProjectExportJob(owner, nextJob);
  const state = store.getState();
  if (!ownsCurrentProjectExport(store, owner) || !isProjectExportStateForCurrentSession(state)) return;
  store.setState({
    ...state,
    projectExport: {
      ...(state.projectExport || {}),
      job: nextJob,
    },
  });
  rerender(host, store);
}

function requestCancelProjectExport(projectExport) {
  const job = projectExport?.job;
  if (!job || job.status !== "running") {
    return projectExport;
  }
  return {
    ...(projectExport || {}),
    job: {
      ...job,
      cancelRequested: true,
    },
  };
}

function closeProjectExportDialog(projectExport) {
  return {
    ...(projectExport || {}),
    job: null,
  };
}

function syncProjectExportDetailFilterControls(host) {
  if (!host?.querySelectorAll) {
    return;
  }
  host.querySelectorAll("[data-project-export-detail-filter-all]").forEach((input) => {
    input.indeterminate = input?.dataset?.projectExportDetailFilterState === "mixed";
  });
}

function syncProjectExportPreviewLabels(host) {
  const summary = host?.querySelector?.("[data-overview-summary]");
  syncFinalPathStripGeometry(summary || host);
  if (!host?.querySelectorAll) {
    return;
  }
  host.querySelectorAll(".project-export-final-path-preview-ctg").forEach((ctgNode) => {
    const labelNode = ctgNode.querySelector?.("span");
    if (!labelNode) {
      return;
    }
    ctgNode.classList?.remove?.("is-label-hidden");
    const labelWidth = Math.ceil(Number(labelNode.scrollWidth || 0));
    const visibleWidth = Math.floor(Number(labelNode.clientWidth || 0));
    if (labelWidth > 0 && visibleWidth > 0 && labelWidth > visibleWidth + 1) {
      ctgNode.classList?.add?.("is-label-hidden");
    }
  });
}

function setProjectExportDetailFilter(host, store, filterKey, value, checked = false) {
  const normalizedKey = normalizeString(filterKey);
  if (!PROJECT_EXPORT_DETAIL_FILTER_KEYS.has(normalizedKey)) {
    return false;
  }
  const state = store.getState();
  const normalizedValue = normalizeString(value);
  const availableValues = getProjectExportDetailFilterOptions(state, normalizedKey).map((option) => option.value);
  const currentFilters = normalizeDetailTableState(state).filters || {};
  const currentRawValues = normalizeDetailFilterValues(currentFilters[normalizedKey]);
  const currentIsNone = currentRawValues.includes(PROJECT_EXPORT_DETAIL_FILTER_NONE);
  const currentValues = currentRawValues
    .filter((item) => item !== PROJECT_EXPORT_DETAIL_FILTER_NONE && availableValues.includes(item));
  let nextValues = [];
  if (!normalizedValue) {
    nextValues = checked ? [] : [PROJECT_EXPORT_DETAIL_FILTER_NONE];
  } else {
    const baseValues = currentValues.length ? currentValues : currentIsNone ? [] : availableValues;
    const nextSet = new Set(baseValues);
    if (checked) {
      nextSet.add(normalizedValue);
    } else {
      nextSet.delete(normalizedValue);
    }
    nextValues = Array.from(nextSet).filter((item) => availableValues.includes(item));
    if (!nextValues.length) {
      nextValues = [PROJECT_EXPORT_DETAIL_FILTER_NONE];
    } else if (nextValues.length >= availableValues.length) {
      nextValues = [];
    }
  }
  store.setState({
    ...state,
    projectExport: {
      ...(state.projectExport || {}),
      detailTableFilters: {
        ...(state.projectExport?.detailTableFilters || {}),
        [normalizedKey]: nextValues,
      },
    },
  });
  rerender(host, store);
  const menu = Array.from(host?.querySelectorAll?.("[data-project-export-detail-filter-menu]") || [])
    .find((node) => node?.dataset?.projectExportDetailFilterMenu === normalizedKey);
  if (menu) {
    menu.open = true;
  }
  return true;
}

function clearProjectExportDetailFilterCloseTimer(detailsNode) {
  const timer = projectExportDetailFilterCloseTimers.get(detailsNode);
  if (timer) {
    clearTimeout(timer);
    projectExportDetailFilterCloseTimers.delete(detailsNode);
  }
}

function scheduleProjectExportDetailFilterClose(detailsNode) {
  if (!detailsNode?.open) {
    return;
  }
  clearProjectExportDetailFilterCloseTimer(detailsNode);
  projectExportDetailFilterCloseTimers.set(detailsNode, setTimeout(() => {
    detailsNode.open = false;
    projectExportDetailFilterCloseTimers.delete(detailsNode);
  }, FLOATING_MENU_CLOSE_DELAY_MS));
}

function toggleProjectExportDetailSort(host, store, sortKey) {
  if (normalizeString(sortKey) !== "length_bp") {
    return false;
  }
  const state = store.getState();
  const currentSort = normalizeDetailTableState(state).sort;
  const nextDirection = currentSort.key !== "length_bp"
    ? "desc"
    : currentSort.direction === "desc"
      ? "asc"
      : currentSort.direction === "asc"
        ? ""
        : "desc";
  store.setState({
    ...state,
    projectExport: {
      ...(state.projectExport || {}),
      detailTableSort: nextDirection
        ? { key: "length_bp", direction: nextDirection }
        : { key: "", direction: "" },
    },
  });
  rerender(host, store);
  return true;
}

async function loadProjectExportData(host, store, deps = {}, attempt = 0) {
  const state = store.getState();
  const currentProject = getCurrentProject(state);
  if (!currentProject || !state.session?.workspacePath || !state.session?.projectId) {
    return false;
  }
  const requestedWorkspacePath = normalizeString(state.session.workspacePath);
  const requestedProjectId = Number(state.session.projectId);
  const mutationStamp = projectDataMutationStamp(state);
  const token = {}; projectDataRequests.set(store, token);
  const isCurrent = () => projectDataRequests.get(store) === token
    && normalizeString(store.getState().session?.workspacePath) === requestedWorkspacePath
    && Number(store.getState().session?.projectId || 0) === requestedProjectId;
  const retryMutation = () => {
    if (!isCurrent()) return false;
    if (attempt < 2) return loadProjectExportData(host, store, deps, attempt + 1);
    const current = store.getState();
    store.setState({ ...current, projectExport: { ...current.projectExport,
      loading: false, loaded: false, mutationStamp: projectDataMutationStamp(current), error: getLabels(current).contentChanged } });
    refreshProjectDataSurface(host, store); return false;
  };
  const previousProjectExport = getScopedProjectExportState(state);
  store.setState({
    ...state,
    projectExport: {
      ...buildEmptyProjectExportState(),
      job: currentProjectExportJob(store) || (isProjectExportStateForCurrentSession(state) ? previousProjectExport.job : null),
      detailTableFilters: previousProjectExport.detailTableFilters,
      detailTableSort: previousProjectExport.detailTableSort,
      detailTableCollapsed: previousProjectExport.detailTableCollapsed,
      loading: true,
      loaded: false,
      mutationStamp,
      error: "",
      projectId: requestedProjectId,
      workspacePath: requestedWorkspacePath,
    },
  });
  refreshProjectDataSurface(host, store);
  try {
    const args = { workspaceRoot: requestedWorkspacePath, projectId: requestedProjectId };
    let preparedSources=null;
    if(hasPreparedOverviewSources(store,args)){
      preparedSources=await consumePreparedOverviewSources(store,args);
      if(!isCurrent())return false;
    }
    const sources = preparedSources || await (deps.getProjectOverviewSources || getProjectOverviewSources)(args);
    if (!isCurrent()) return false;
    const { ctgsByChr, primaryCtgsByChr } = groupProjectOverviewSources(sources);
    const chromosomeResult = { ...sources, items: sources.chromosomes };
    const getViewState = deps.getProjectAssemblyViewState || getProjectAssemblyViewState;
    const getGrtView = deps.getGrtProjectView || getGrtProjectView;
    const listRefinementResults = deps.listManualRefinementResults || listManualRefinementResults;
    const listRefinementExports = deps.listManualRefinementExports || listManualRefinementExports;
    const [viewState, rawGrtProjectView, manualRefinementResults, manualRefinementExports] = await Promise.all([
      getViewState(args),
      typeof deps.getGrtProjectView === "function" || typeof window !== "undefined"
        ? getGrtView(args) : store.getState().assembly?.grtProjectView || {},
      (typeof deps.listManualRefinementResults === "function" || Boolean(globalThis.window?.__TAURI__?.core?.invoke))
        ? Promise.resolve(listRefinementResults(args)).catch(() => [])
        : Promise.resolve([]),
      (typeof deps.listManualRefinementExports === "function" || Boolean(globalThis.window?.__TAURI__?.core?.invoke))
        ? Promise.resolve(listRefinementExports(args)).catch(() => null)
        : Promise.resolve(null),
    ]);
    if(preparedSources && !(await validatePreparedOverviewSources(store,args,preparedSources))) {
      return isCurrent()?retryMutation():false;
    }
    if(!isCurrent())return false;
    const grtProjectView = (deps.normalizeGrtProjectView || normalizeGrtProjectView)(rawGrtProjectView);
    const phasedChrTracksByChr = currentProject?.phasedAssemblyEnabled
      ? normalizePhasedTrackMap(sources.phasedChrTracksByChr) : {};
    if (!isCurrent()) return false;
    if (mutationStamp !== projectDataMutationStamp(store.getState())) return retryMutation();
    const mergedFinalPathByChr = canonicalizeFinalPathOverallLengths(
      mergeFinalPathByChr(
        viewState.finalPathByChr,
        store.getState().assembly?.finalPathByChr,
      ),
      grtProjectView.baselineFinalPathByChr,
    );
    const latestState = store.getState();
    if (
      !isCurrent()
    ) {
      return false;
    }
    const normalizedViewHiddenByChr =
      viewState.hiddenPrimaryCtgIdsByChr
      && typeof viewState.hiddenPrimaryCtgIdsByChr === "object"
      && !Array.isArray(viewState.hiddenPrimaryCtgIdsByChr)
        ? viewState.hiddenPrimaryCtgIdsByChr
        : {};
    store.setState({
      ...store.getState(),
      projectExport: {
        ...(store.getState().projectExport || {}),
        loading: false,
        loaded: true,
        error: "",
        projectId: requestedProjectId,
        workspacePath: requestedWorkspacePath,
        chromosomes: chromosomeResult.items || [],
        unplacedCtgCount: chromosomeResult.unplacedCtgCount || 0,
        unplacedBp: chromosomeResult.unplacedBp || 0,
        finalPathByChr: mergedFinalPathByChr,
        phasedChrTracksByChr,
        hiddenPrimaryCtgIds: normalizeHiddenPrimaryCtgIds(viewState.hiddenPrimaryCtgIds),
        hiddenPrimaryCtgIdsByChr: getProjectExportHiddenPrimaryCtgIdsByChr({
          ...store.getState(),
          projectExport: {
            ...(store.getState().projectExport || {}),
            finalPathByChr: mergedFinalPathByChr,
            hiddenPrimaryCtgIds: normalizeHiddenPrimaryCtgIds(viewState.hiddenPrimaryCtgIds),
            hiddenPrimaryCtgIdsByChr: normalizedViewHiddenByChr,
          },
        }, mergedFinalPathByChr),
        ctgsByChr,
        primaryCtgsByChr,
        grtProjectView,
        degapProjectState: viewState?.degapProjectState || {},
        manualRefinementResults: Array.isArray(manualRefinementResults) ? manualRefinementResults : [],
        manualRefinementExports: Array.isArray(manualRefinementExports)
          ? manualRefinementExports : getScopedProjectExportState(store.getState()).manualRefinementExports || [],
      },
    });
    refreshProjectDataSurface(host, store);
    return true;
  } catch (error) {
    if (isCurrent() && mutationStamp !== projectDataMutationStamp(store.getState())) return retryMutation();
    const latestState = store.getState();
    if (
      !isCurrent()
    ) {
      return false;
    }
    store.setState({
      ...latestState,
      projectExport: {
        ...(latestState.projectExport || {}),
        loading: false,
        loaded: false,
        error: String(error?.message || error || ""),
      },
    });
    refreshProjectDataSurface(host, store);
    return false;
  }
}

async function resolveProjectExportTarget({ state, kind, baseName, deps = {} }) {
  const normalizedKind = normalizeString(kind).toLowerCase();
  const pickSaveFile = deps.pickSaveFilePath || pickSaveFilePath;
  const pickDirectory = deps.pickDirectoryPath || pickDirectoryPath;
  if (normalizedKind === "tsv") {
    return pickSaveFile({
      defaultPath: `${baseName}.tsv`,
      filters: [{ name: "TSV", extensions: ["tsv"] }],
    }, state);
  }
  if (normalizedKind === "log") {
    return pickSaveFile({
      defaultPath: `${baseName}.log`,
      filters: [{ name: "LOG", extensions: ["log"] }],
    }, state);
  }
  if (normalizedKind === "agp") {
    return pickAgpExportPath(pickSaveFile, baseName, state);
  }
  if (normalizedKind === "fasta") {
    return pickSaveFile({
      defaultPath: `${baseName}.fasta`,
      filters: [{ name: "FASTA", extensions: ["fasta", "fa"] }],
    }, state);
  }
  if (normalizedKind === "all") {
    return pickDirectory(state);
  }
  return "";
}

function planProjectExportSteps({
  kind,
  baseName,
  targetPath,
  canExportFasta = true,
  canExportLog = true,
}) {
  // Keep the existing batch write order and cancellation / partial-output semantics.
  const available = ["png", "tsv", ...(canExportLog ? ["log"] : []), ...(canExportFasta ? ["fasta"] : []), "agp"];
  const action = normalizeString(kind).toLowerCase();
  const kinds = action === "all" ? available : available.filter(k => k !== "png" && k === action);
  return kinds.map(kind => ({ kind,
    outputPath: action === "all" ? joinOutputPath(targetPath, `${baseName}.${kind}`) : targetPath,
  }));
}

async function runProjectExport(host, store, kind, deps = {}) {
  const currentState = store.getState();
  if (currentProjectExportJob(store)?.status === "running") return false;
  if (
    !isProjectOverviewDataFresh(currentState)
  ) {
    const loaded = await loadProjectExportData(host, store, deps);
    if (!loaded) {
      return false;
    }
  }
  const state = store.getState();
  const currentProject = getCurrentProject(state);
  const model = buildProjectExportDataModel(state);
  const normalizedKind = normalizeString(kind).toLowerCase();
  if (!currentProject || !normalizedKind || (normalizedKind === "log" && !model.canExportLog)) {
    return false;
  }
  if (normalizedKind === "all" && !canExportPreviewImage(state)) return false;
  const entries = getFinalPathPreviewEntries(state);
  if (!entries.length) {
    return false;
  }
  const projectName = state.session?.projectName || currentProject.projectName || "project";
  const exportTimestamp = resolveExportTimestamp(deps);
  const baseName = buildTimestampedExportBaseName(
    buildProjectFinalPathExportBaseName(projectName),
    exportTimestamp,
  );
  const scope = exportJobScope(state);
  const resolveTarget = deps.resolveProjectExportTarget || resolveProjectExportTarget;
  let targetPath = await resolveTarget({
    state,
    kind: normalizedKind,
    baseName,
    deps,
  });
  if (!targetPath || exportJobScope(store.getState()) !== scope) {
    return false;
  }
  if (normalizedKind === "all" && !previewImageStillCurrent(state, store.getState())) return false;
  if (normalizedKind !== "all") {
    targetPath = appendTimestampToOutputPath(targetPath, exportTimestamp);
  }
  const steps = planProjectExportSteps({
    kind: normalizedKind,
    baseName,
    targetPath,
    canExportFasta: canProjectExportFasta(state),
    canExportLog: model.canExportLog,
  });
  if (!steps.length) {
    return false;
  }
  const job = {
    open: true,
    kind: normalizedKind,
    projectName,
    status: "running",
    currentStep: "",
    completedOutputs: [],
    error: "",
    cancelRequested: false,
    targetPath,
    steps,
  };
  const owner = beginProjectExportJob(store, state, job);
  if (!owner) return false;
  const publish = next => setProjectExportJob(host, store, next, owner);
  const readJob = () => ownsCurrentProjectExport(store, owner) && isProjectExportStateForCurrentSession(store.getState())
    ? store.getState().projectExport?.job || owner.job : owner.job;
  const writeText = deps.writeFinalPathExportTextFile || writeFinalPathExportTextFile;
  const writeBinary = deps.writeFinalPathExportBinaryFile || writeFinalPathExportBinaryFile;
  const exportFasta = deps.exportProjectFinalPathFasta || exportProjectFinalPathFasta;
  const renderPng = deps.renderProjectPreviewPng || renderProjectPreviewPng;
  const completedOutputs = [];
  try {
    // Batch jobs own frozen inputs and can finish after the user changes assembly.
    const previewSnapshot = normalizedKind === "all" ? captureProjectPreviewImage(host, state) : null;
    publish(job);
    const exportEntries = enrichProjectFinalPathEntriesForExport(entries, state);
    const finalPathByChr = buildProjectFinalPathByChr(exportEntries);
    for (const step of steps) {
      const currentJob = readJob();
      if (currentJob.cancelRequested) {
        publish({
          ...currentJob,
          status: "canceled",
          completedOutputs: [...completedOutputs],
          error: "",
        });
        return false;
      }
      publish({
        ...currentJob,
        status: "running",
        currentStep: step.kind,
        completedOutputs: [...completedOutputs],
        error: "",
      });
      if (step.kind === "tsv") {
        await writeText({
          outputPath: step.outputPath,
          text: buildProjectFinalPathTsvText(exportEntries),
          stateOrLocale: state,
        });
      } else if (step.kind === "log") {
        await writeText({
          outputPath: step.outputPath,
          text: buildProjectExportLogText(model),
          stateOrLocale: state,
        });
      } else if (step.kind === "fasta" || step.kind === "agp") {
        const exportPath = step.kind === "agp" ? (deps.exportProjectFinalPathAgp || exportProjectFinalPathAgp) : exportFasta;
        const result = await exportPath({
          workspaceRoot: state.session?.workspacePath || "",
          projectId: Number(state.session?.projectId || 0),
          finalPathByChr,
          ...(step.kind === "agp" ? { includeComponents: canProjectExportFasta(state) } : {}),
          outputPath: step.outputPath,
          stateOrLocale: state,
        });
        if (step.kind === "agp") {
          completedOutputs.push(...confirmedAgpOutputs(result, state));
          continue;
        }
      } else if (step.kind === "png") {
        const bytesBase64 = await renderPng(previewSnapshot);
        await writeBinary({
          outputPath: step.outputPath, bytesBase64,
          stateOrLocale: state,
        });
      }
      completedOutputs.push(step.outputPath);
    }
    publish({
      ...readJob(),
      status: "success",
      currentStep: "",
      completedOutputs,
      error: "",
    });
    return true;
  } catch (error) {
    publish({
      ...readJob(),
      status: "error",
      currentStep: "",
      completedOutputs,
      error: String(error?.message || error || ""),
    });
    return false;
  } finally { finishProjectExportJob(store, owner); }
}

function setProjectRefinementExportModal(host, store, modal, expectedIdentity = null) {
  const state = store.getState();
  if (expectedIdentity && !isSameRefinementExportProject(state, expectedIdentity)) {
    return false;
  }
  const scoped = getScopedProjectExportState(state);
  store.setState({
    ...state,
    projectExport: {
      ...scoped,
      projectId: Number(state.session?.projectId || 0),
      workspacePath: normalizeString(state.session?.workspacePath),
      refinementExportModal: modal,
    },
  });
  rerender(host, store);
  return true;
}

export function closeProjectRefinementExportPreview(host, store) {
  const current = store.getState().projectExport?.refinementExportModal;
  if (current?.status === "exporting") {
    return false;
  }
  return setProjectRefinementExportModal(host, store, null);
}

export async function openProjectRefinementExportPreview(host, store, deps = {}) {
  const state = store.getState();
  const currentProject = getCurrentProject(state);
  const workspaceRoot = normalizeString(state.session?.workspacePath);
  const projectId = Number(state.session?.projectId || 0);
  if (!workspaceRoot || !projectId) {
    return false;
  }
  const projectName = normalizeString(state.session?.projectName || currentProject?.projectName || projectId);
  const frozenIdentity = { workspaceRoot, projectId };
  const loadingModal = {
    open: true,
    status: "loading",
    workspaceRoot,
    workspacePath: workspaceRoot,
    projectId,
    projectName,
    loci: [],
    request: null,
    error: "",
    validationError: "",
  };
  setProjectRefinementExportModal(host, store, loadingModal, frozenIdentity);
  const isCurrent = () => store.getState().projectExport?.refinementExportModal === loadingModal
    && isSameRefinementExportProject(store.getState(), frozenIdentity);

  try {
    const modal = await prepareFrozenManualRefinementAllPreview({
      host,
      store,
      workspaceRoot,
      projectId,
      projectName,
      locale: state.locale,
      deps: {
        flushAssemblyProjectState: deps.flushAssemblyProjectState || flushAssemblyProjectState,
        ...deps,
      },
    });
    if (!modal || !isCurrent()) {
      return false;
    }
    setProjectRefinementExportModal(host, store, modal, frozenIdentity);
    return true;
  } catch (error) {
    if (!isCurrent()) {
      return false;
    }
    setProjectRefinementExportModal(host, store, {
      open: true,
      status: "error",
      workspaceRoot,
      workspacePath: workspaceRoot,
      projectId,
      projectName,
      loci: [],
      request: null,
      validationError: "",
      error: String(error?.message || error || ""),
    }, frozenIdentity);
    return false;
  }
}

export async function confirmProjectRefinementExport(host, store, deps = {}) {
  const state = store.getState();
  const modal = state.projectExport?.refinementExportModal;
  if (!modal?.open || modal.status === "exporting" || !modal.request?.loci?.length) {
    return false;
  }
  const frozenIdentity = {
    workspaceRoot: normalizeString(modal.workspaceRoot ?? modal.workspacePath),
    projectId: Number(modal.projectId || 0),
  };
  if (!isSameRefinementExportProject(state, frozenIdentity)) {
    return false;
  }

  const exportingModal = {
    ...modal,
    status: "exporting",
    error: "",
    copyFeedback: "",
  };
  setProjectRefinementExportModal(host, store, exportingModal, frozenIdentity);
  const isCurrent = () => store.getState().projectExport?.refinementExportModal === exportingModal
    && isSameRefinementExportProject(store.getState(), frozenIdentity);

  try {
    const result = await executeFrozenManualRefinementExport({
      host,
      store,
      modal,
      isCurrent,
      deps: {
        flushAssemblyProjectState: deps.flushAssemblyProjectState || flushAssemblyProjectState,
        ...deps,
      },
    });
    if (result.switched || !isCurrent()) {
      return false;
    }
    if (result.canceled) {
      setProjectRefinementExportModal(host, store, {
        ...modal,
        status: "ready",
        error: "",
      }, frozenIdentity);
      return false;
    }
    if (!result.ok) {
      setProjectRefinementExportModal(host, store, {
        ...modal,
        status: "ready",
      }, frozenIdentity);
      return false;
    }
    const latest = store.getState();
    store.setState({
      ...latest,
      projectExport: {
        ...(latest.projectExport || {}),
        manualRefinementExports: [result.receipt,
          ...(latest.projectExport?.manualRefinementExports || []).filter(row => row.batchSha256 !== result.receipt.batchSha256),
        ].slice(0, 20),
        refinementExportModal: {
          ...modal,
          status: "success",
          error: "",
          receipt: result.receipt,
        },
      },
    });
    rerender(host, store);
    return true;
  } catch (error) {
    if (!isCurrent()) {
      return false;
    }
    setProjectRefinementExportModal(host, store, {
      ...modal,
      status: "ready",
      error: String(error?.message || error || ""),
    }, frozenIdentity);
    return false;
  }
}

export function bindProjectExportPage(host, store, deps = {}) {
  if (!host) return;
  mountOverviewPreview(host, store, deps);
  syncPreviewExportActions(host, store);
  bindProjectDataFreshness(host, store, deps);
  if (host[PROJECT_EXPORT_BOUND]) {
    ensureProjectOverviewData(host, store, deps);
    syncProjectExportDetailFilterControls(host);
    syncProjectExportPreviewLabels(host);
    return;
  }
  host[PROJECT_EXPORT_BOUND] = true;
  ensureProjectOverviewData(host, store, deps);
  syncProjectExportDetailFilterControls(host);
  syncProjectExportPreviewLabels(host);
  const setExportMenuOpen = (exportRoot, shouldOpen, restoreFocus = false) => {
    const menuNode = exportRoot?.querySelector?.("[data-project-export-menu]");
    const toggleNode = exportRoot?.querySelector?.("[data-project-export-toggle]");
    if (!menuNode) {
      return;
    }
    menuNode.classList.toggle("is-hidden", !shouldOpen);
    toggleNode?.setAttribute("aria-expanded", String(shouldOpen));
    if (!shouldOpen) {
      if (restoreFocus) toggleNode?.focus();
      projectExportSubmenuBindings.get(menuNode)?.();
      projectExportSubmenuBindings.delete(menuNode);
    } else {
      projectExportSubmenuBindings.set(menuNode, bindFloatingSubmenus(menuNode, { keyboard: true }));
      menuNode.querySelector?.('[data-project-export-action="agp"]:not(:disabled)')?.focus();
    }
  };
  host.addEventListener("click", async (event) => {
    if (store.getState().activeRoute && !["importer", "projectExport"].includes(store.getState().activeRoute)) return;
    const gapsFilterBtn = event.target?.closest?.("[data-preview-filter-gaps]");
    if (gapsFilterBtn) {
      const previewHost = host.querySelector?.("[data-overview-preview]");
      const key = previewProjectKey(store.getState());
      const current = getPreviewFilterState(key);
      applyProjectPreviewFilter(previewHost, store, { gapsOnly: !current.gapsOnly });
      return;
    }
    const toggleAllBtn = event.target?.closest?.("[data-preview-toggle-all]");
    if (toggleAllBtn) {
      const previewHost = host.querySelector?.("[data-overview-preview]");
      toggleAllProjectPreviewChromosomes(previewHost, store);
      return;
    }
    const formatNode = event.target?.closest?.("[data-preview-format]");
    if (formatNode) {
      setExportMenuOpen(formatNode.closest?.("[data-project-export]"), false, true);
      await exportProjectPreviewImage(host, store, formatNode.dataset.previewFormat, deps.preview || deps);
      return;
    }
    const closeNode = event.target?.closest?.("[data-project-export-close]");
    if (closeNode) {
      const currentState = store.getState();
      const projectExport = currentState.projectExport || {};
      const nextProjectExport = projectExport.job?.status === "running"
        ? requestCancelProjectExport(projectExport)
        : closeProjectExportDialog(projectExport);
      syncCurrentProjectExportJob(store, nextProjectExport.job);
      store.setState({
        ...currentState,
        projectExport: nextProjectExport,
      });
      rerender(host, store);
      return;
    }
    const exportToggleNode = event.target?.closest?.("[data-project-export-toggle]");
    if (exportToggleNode) {
      const exportNode = exportToggleNode.closest?.("[data-project-export]");
      const menuNode = exportNode?.querySelector?.("[data-project-export-menu]");
      if (!menuNode) {
        return;
      }
      setExportMenuOpen(exportNode, menuNode.classList.contains("is-hidden"));
      return;
    }
    const detailToggle = event.target?.closest?.("[data-project-export-detail-toggle]");
    if (detailToggle) {
      const currentState = store.getState();
      store.setState({
        ...currentState,
        projectExport: {
          ...currentState.projectExport,
          detailTableCollapsed: !normalizeDetailTableState(currentState).collapsed,
        },
      });
      rerender(host, store);
      host.querySelector?.("[data-project-export-detail-toggle]")?.focus();
      return;
    }
    const sortNode = event.target?.closest?.("[data-project-export-detail-sort]");
    if (sortNode) {
      toggleProjectExportDetailSort(host, store, sortNode.dataset.projectExportDetailSort);
      return;
    }
    const chrJumpNode = event.target?.closest?.("[data-project-export-jump-chr]");
    if (chrJumpNode) {
      jumpToAssemblyChr(store, {
        parentChrName: chrJumpNode.dataset.projectExportJumpParentChr || "",
        chrName: chrJumpNode.dataset.projectExportJumpChr || "",
        activePhasedTrackKey: chrJumpNode.dataset.projectExportJumpPhasedKey || "",
      });
      return;
    }
    const refreshNode = event.target?.closest?.("[data-project-export-refresh]");
    if (refreshNode) {
      await loadProjectExportData(host, store, deps);
      return;
    }
    const cancelRefinementPreview = event.target?.closest?.("[data-refinement-export-preview-cancel]");
    if (cancelRefinementPreview) {
      closeProjectRefinementExportPreview(host, store);
      return;
    }
    const confirmRefinementPreview = event.target?.closest?.("[data-refinement-export-preview-confirm]");
    if (confirmRefinementPreview) {
      await confirmProjectRefinementExport(host, store, deps);
      return;
    }
    const copyRefinementPreview = event.target?.closest?.("[data-refinement-export-preview-copy]");
    if (copyRefinementPreview) {
      const cmd = normalizeString(copyRefinementPreview.dataset.refinementExportPreviewCopy);
      if (cmd) {
        void globalThis.navigator?.clipboard?.writeText?.(cmd).then(() => {
          const latest = store.getState();
          const modal = latest.projectExport?.refinementExportModal;
          if (!modal?.open) return;
          setProjectRefinementExportModal(host, store, {
            ...modal,
            copyFeedback: latest.locale === "en" ? "Copied Server command." : "已复制 Server 命令。",
          });
        }).catch(() => {});
      }
      return;
    }
    const actionNode = event.target?.closest?.("[data-project-export-action]");
    if (!actionNode) {
      return;
    }
    const action = normalizeString(actionNode.dataset.projectExportAction).toLowerCase();
    setExportMenuOpen(actionNode.closest?.("[data-project-export]"), false, true);
    if (action === "refinement-all") {
      await openProjectRefinementExportPreview(host, store, deps);
      return;
    }
    await runProjectExport(host, store, action, deps);
  });
  bindDelegatedDelayedFloatingClose(host, {
    rootSelector: "[data-project-export]",
    timerKey: PROJECT_EXPORT_MENU_CLOSE_TIMER,
    close: (exportRoot) => setExportMenuOpen(exportRoot, false),
  });
  host.addEventListener("input", (event) => {
    if (store.getState().activeRoute && !["importer", "projectExport"].includes(store.getState().activeRoute)) return;
    const filterInput = event.target?.closest?.("[data-preview-filter-input]");
    if (!filterInput) return;
    const previewHost = host.querySelector?.("[data-overview-preview]");
    applyProjectPreviewFilter(previewHost, store, { query: filterInput.value });
  });
  host.addEventListener("change", (event) => {
    if (store.getState().activeRoute && !["importer", "projectExport"].includes(store.getState().activeRoute)) return;
    const filterNode = event.target?.closest?.("[data-project-export-detail-filter]");
    if (!filterNode) {
      return;
    }
    setProjectExportDetailFilter(
      host,
      store,
      filterNode.dataset.projectExportDetailFilter,
      filterNode.value,
      Boolean(filterNode.checked),
    );
  });
  host.addEventListener("pointerover", (event) => {
    if (store.getState().activeRoute && !["importer", "projectExport"].includes(store.getState().activeRoute)) return;
    const detailsNode = event.target?.closest?.(".project-export-detail-filter");
    if (detailsNode) {
      clearProjectExportDetailFilterCloseTimer(detailsNode);
    }
  });
  host.addEventListener("pointerout", (event) => {
    if (store.getState().activeRoute && !["importer", "projectExport"].includes(store.getState().activeRoute)) return;
    const detailsNode = event.target?.closest?.(".project-export-detail-filter");
    if (!detailsNode || detailsNode.contains?.(event.relatedTarget)) {
      return;
    }
    scheduleProjectExportDetailFilterClose(detailsNode);
  });
  host.addEventListener("keydown", (event) => {
    if (store.getState().activeRoute && !["importer", "projectExport"].includes(store.getState().activeRoute)) return;
    if (event.key === "Escape" && store.getState().projectExport?.refinementExportModal?.open) {
      event.preventDefault();
      closeProjectRefinementExportPreview(host, store);
      return;
    }
    const menu = event.target?.closest?.("[data-project-export]");
    if (event.key === "Escape" && menu) {
      setExportMenuOpen(menu, false, true);
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    const chrJumpNode = event.target?.closest?.("[data-project-export-jump-chr]");
    if (!chrJumpNode) {
      return;
    }
    event.preventDefault();
    jumpToAssemblyChr(store, {
      parentChrName: chrJumpNode.dataset.projectExportJumpParentChr || "",
      chrName: chrJumpNode.dataset.projectExportJumpChr || "",
      activePhasedTrackKey: chrJumpNode.dataset.projectExportJumpPhasedKey || "",
    });
  });
}

export async function reloadProjectOverviewData(host, store, deps = {}) {
  return loadProjectExportData(host, store, deps);
}

export const __test = {
  buildProjectExportDataModel,
  buildProjectFinalPathByChr,
  buildProjectFinalPathTsvText,
  enrichProjectFinalPathEntriesForExport,
  getLabels,
  getFinalPathPreviewEntries,
  getProjectExportFinalPathByChr,
  getProjectExportHiddenPrimaryCtgIdsByChr,
  planProjectExportSteps,
  resolveProjectExportTarget,
  jumpToAssemblyChr,
  loadProjectExportData,
  openProjectRefinementExportPreview,
  confirmProjectRefinementExport,
  closeProjectRefinementExportPreview,
  rerender,
  runProjectExport,
  syncProjectExportDetailFilterControls,
  syncProjectExportPreviewLabels,
};
