import { pickDirectoryPath, pickSaveFilePath } from "../../services/backend-api.js";
import {
  exportProjectFinalPathFasta,
  getProjectAssemblyViewState,
  listChrViewCtgs,
  listPhasedChrTracks,
  listProjectChromosomes,
  writeFinalPathExportBinaryFile,
  writeFinalPathExportTextFile,
} from "../../services/workflow-api.js";
import {
  appendTimestampToOutputPath,
  buildTimestampedExportBaseName,
  renderFinalPathViewportPng,
  resolveExportTimestamp,
} from "./assembly/final-path-export-runtime.js";
import { bindDelegatedDelayedFloatingClose } from "./floating-menu-runtime.js";
import {
  normalizeFinalPathByChr,
  isFinalPathCtgSegment,
  isFinalPathGapSegment,
  isFinalPathRefSegment,
  resolveFinalPathSegmentDisplayName,
  resolveFinalPathSegmentLengthBp,
  resolveFinalPathTotalLengthBp,
} from "./assembly/final-path-state.js";
import { normalizeHiddenPrimaryCtgIds } from "./assembly/selection-state.js";
import { buildProjectExportLogText, buildProjectExportStatsModel } from "./project-export-state.js";
import { buildEmptyProjectExportState } from "../shell/session-switchers.js";

const PROJECT_EXPORT_BOUND = Symbol("projectExportBound");
const PROJECT_EXPORT_RESIZE_BOUND = Symbol("projectExportResizeBound");
const PROJECT_EXPORT_MENU_CLOSE_TIMER = "__projectExportMenuCloseTimer";
const PROJECT_EXPORT_DETAIL_FILTER_KEYS = new Set(["type", "chr", "dataset"]);
const PROJECT_EXPORT_DETAIL_FILTER_NONE = "__project_export_filter_none__";
const PROJECT_EXPORT_DETAIL_FILTER_CLOSE_DELAY_MS = 400;
const projectExportDetailFilterCloseTimers = new WeakMap();

function normalizeString(value) {
  return String(value || "").trim();
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

function stripFinalPathCtgAssignmentSuffix(name) {
  const text = normalizeString(name);
  const atIndex = text.lastIndexOf("@");
  if (atIndex <= 0 || atIndex >= text.length - 1) {
    return text;
  }
  const suffix = text.slice(atIndex + 1);
  if (!suffix || /\s/.test(suffix)) {
    return text;
  }
  return text.slice(0, atIndex);
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

function resolveFinalPathPreviewCtgLabel(segment) {
  if (isFinalPathGapSegment(segment) || isFinalPathRefSegment(segment)) {
    return resolveFinalPathSegmentDisplayName(segment);
  }
  const displayName = stripFinalPathCtgAssignmentSuffix(resolveFinalPathSegmentDisplayName(segment));
  const start = Number(segment?.start);
  const end = Number(segment?.end);
  if (!displayName || !Number.isFinite(start) || !Number.isFinite(end)) {
    return displayName;
  }
  return `${displayName} (${start > end ? "-" : "+"})`;
}

function isCompanionFinalPathSegment(segment, primaryDatasetName = "") {
  const segmentDataset = normalizeString(segment?.datasetName).toLowerCase();
  const primaryDataset = normalizeString(primaryDatasetName).toLowerCase();
  return Boolean(segmentDataset && primaryDataset && segmentDataset !== primaryDataset);
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
  if (state?.locale === "en") {
    return {
      title: "Project Export",
      noProject: "Select a project first.",
      project: "Project",
      primaryDataset: "Primary ds",
      loadFailed: "Failed to load project export data.",
      loading: "Loading project export data...",
      refresh: "Refresh",
      export: "Export",
      exportAll: "All",
      exportPng: "Graph (.png)",
      exportTsv: "Table (.tsv)",
      exportFasta: "Sequence (.fasta)",
      exportLog: "Log (.log)",
      exportDialogTitle: "Exporting final path",
      exportRunning: "Running: {step}",
      refDisabled: "A final path in this project contains ref objects. Statistics and log export are disabled; export functions remain available.",
      placedStats: "Placed statistics",
      countLabel: "Count",
      lengthLabel: "Length",
      primaryCount: "used_primary_ds_ctg_count",
      primaryLength: "used_primary_ds_ctg_length",
      assignment: "Primary ds assignment",
      appended: "Appended",
      hidden: "Hidden",
      placed: "placed",
      placedUsed: "placed & used",
      placedNotUsed: "placed & not used",
      unassigned: "unassigned",
      supportType: "Support ds_ctg usage",
      otherChrType: "Repeated primary ds_ctg usage",
      noRows: "No rows",
      exporting: "Exporting...",
      completed: "Export completed",
      failed: "Export failed",
      canceled: "Canceled. Already exported files were kept.",
      all: "All",
    };
  }
  return {
    title: "项目导出",
    noProject: "请先选择项目。",
    project: "项目",
    primaryDataset: "主 ds",
    loadFailed: "项目导出数据加载失败。",
    loading: "正在加载项目导出数据...",
    refresh: "刷新",
    export: "Export",
    exportAll: "All",
    exportPng: "图(.png)",
    exportTsv: "表(.tsv)",
    exportFasta: "序列(.fasta)",
    exportLog: "日志(.log)",
    exportDialogTitle: "正在导出 final path",
    exportRunning: "正在执行：{step}",
    refDisabled: "检测到项目内某个 chr 的 final path 包含 ref 对象，本页只保留导出功能，项目统计和 log 导出已关闭。",
    placedStats: "placed统计",
    countLabel: "数目",
    lengthLabel: "长度",
    primaryCount: "used_主ds_ctg数目",
    primaryLength: "used_主ds_ctg长度",
    assignment: "主 ds 分配统计",
    appended: "实际 append",
    hidden: "主图 hidden",
    placed: "placed",
    placedUsed: "placed & used",
    placedNotUsed: "placed & not used",
    unassigned: "unplaced",
    supportType: "辅助 ds_ctg使用情况",
    otherChrType: "重复主ds_ctg使用情况",
    noRows: "暂无记录",
    exporting: "正在导出...",
    completed: "已完成导出",
    failed: "导出失败",
    canceled: "已终止，已保留已导出的文件",
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

function buildProjectFinalPathSvgSnapshot({ entries, projectName, primaryDatasetName }) {
  const rows = Array.isArray(entries) ? entries : [];
  const width = 1200;
  const labelWidth = 132;
  const rightPadding = 116;
  const trackX = labelWidth;
  const trackWidth = width - labelWidth - rightPadding;
  const rowHeight = 52;
  const topPadding = 32;
  const height = Math.max(96, topPadding + rows.length * rowHeight + 20);
  const maxLengthBp = Math.max(1, ...rows.map((row) => Math.max(0, Number(row.lengthBp || 0))));
  const rowMarkup = rows.map(({ chrName, entry, lengthBp }, rowIndex) => {
    const y = topPadding + rowIndex * rowHeight;
    let cursorBp = 0;
    const segments = Array.isArray(entry?.segments) ? entry.segments : [];
    const segmentMarkup = segments.map((segment) => {
      const segmentLengthBp = Math.max(0, resolveFinalPathSegmentLengthBp(segment));
      if (segmentLengthBp <= 0) {
        return "";
      }
      const x = trackX + (cursorBp / maxLengthBp) * trackWidth;
      const segmentWidth = Math.max(1, (segmentLengthBp / maxLengthBp) * trackWidth);
      cursorBp += segmentLengthBp;
      if (isFinalPathGapSegment(segment)) {
        return `
          <rect x="${x.toFixed(2)}" y="${(y + 19).toFixed(2)}" width="${segmentWidth.toFixed(2)}" height="10" fill="#ffffff" stroke="#1b1b1b" stroke-width="1" />
        `;
      }
      const isRef = isFinalPathRefSegment(segment);
      const isCompanion = isCompanionFinalPathSegment(segment, primaryDatasetName);
      const fill = isRef ? "#cfcfcf" : isCompanion ? "#e7dec4" : "#d2dfef";
      const stroke = isRef ? "#8e8e8e" : isCompanion ? "#8a7551" : "#6d85a1";
      return `
        <rect x="${x.toFixed(2)}" y="${(y + 17).toFixed(2)}" width="${segmentWidth.toFixed(2)}" height="14" rx="3" fill="${fill}" stroke="${stroke}" stroke-width="1" />
      `;
    }).join("");
    return `
      <g>
        <text x="0" y="${(y + 28).toFixed(2)}" fill="#333" font-size="13" font-weight="700">${escapeHtml(chrName)}</text>
        <line x1="${trackX}" y1="${(y + 24).toFixed(2)}" x2="${(trackX + trackWidth).toFixed(2)}" y2="${(y + 24).toFixed(2)}" stroke="#d7d7d7" stroke-width="1" />
        ${segmentMarkup}
        <text x="${(trackX + trackWidth + 12).toFixed(2)}" y="${(y + 28).toFixed(2)}" fill="#666" font-size="11">${escapeHtml(`${formatNumber(lengthBp)} bp`)}</text>
      </g>
    `;
  }).join("");
  const svgMarkup = `
    <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="${width}" height="${height}" fill="#fff" />
      <text x="0" y="18" fill="#333" font-size="14" font-weight="700">${escapeHtml(projectName || "project")}</text>
      ${rowMarkup}
    </svg>
  `;
  return {
    width,
    height,
    scrollLeft: 0,
    scrollTop: 0,
    svgMarkup,
  };
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
      <span class="final-path-log-ratio-segment is-appended" style="width: ${appendedPct.toFixed(3)}%" title="${escapeAttr(appendedTitle || "")}"></span>
      <span class="final-path-log-ratio-segment is-log-hidden" style="width: ${hiddenPct.toFixed(3)}%" title="${escapeAttr(hiddenTitle || "")}"></span>
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
          <span class="project-export-assignment-value-part" title="${escapeAttr(part.title)}">${escapeHtml(part.text)}</span>
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
          return `<span class="project-export-assignment-segment ${escapeAttr(item.className)}" style="width: ${width.toFixed(3)}%" title="${escapeAttr(item.title)}"></span>`;
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
      usedByChrNames: [row.chrName],
    })),
    ...(Array.isArray(model.otherChrPrimaryRows) ? model.otherChrPrimaryRows : []).map((row) => ({
      ...row,
      type: "other_chr_primary",
      typeLabel: labels.otherChrType,
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
    return normalizeString(row.typeLabel);
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

function renderDetailFilterHeader({ label, filterKey, options, selectedValues, allLabel = "All" }) {
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
          <summary aria-label="${escapeAttr(label)} filter" title="${escapeAttr(label)} filter"></summary>
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

function renderLengthSortHeader(sort) {
  const direction = sort?.key === "length_bp" ? sort.direction : "";
  const marker = direction === "asc" ? " asc" : direction === "desc" ? " desc" : "";
  return `
    <th>
      <button
        type="button"
        class="project-export-detail-sort"
        data-project-export-detail-sort="length_bp"
        aria-label="length_bp"
      >length_bp${escapeHtml(marker)}</button>
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
      ? `<td class="final-path-log-type-cell" rowspan="${typeSpan}">${escapeHtml(row.typeLabel || "")}</td>`
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
    <section class="project-export-detail-section">
      <div class="final-path-log-table-wrap">
        <table class="final-path-log-table project-export-detail-table">
          <thead>
            <tr>
              ${renderDetailFilterHeader({
                label: "Type",
                filterKey: "type",
                options: getDetailFilterOptions(rows, "type"),
                selectedValues: filters.type,
                allLabel: labels.all,
              })}
              ${renderDetailFilterHeader({
                label: "chr",
                filterKey: "chr",
                options: getDetailFilterOptions(rows, "chr"),
                selectedValues: filters.chr,
                allLabel: labels.all,
              })}
              ${renderDetailFilterHeader({
                label: "dataset",
                filterKey: "dataset",
                options: getDetailFilterOptions(rows, "dataset"),
                selectedValues: filters.dataset,
                allLabel: labels.all,
              })}
              <th>origin_id</th>
              <th>start</th>
              <th>end</th>
              ${renderLengthSortHeader(detailTableState.sort)}
              <th>used_by_chr</th>
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
    return `<p class="notice warning">${escapeHtml(labels.refDisabled)}</p>`;
  }
  return `
    <section class="project-export-grid">
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
    </section>
    ${renderDetailTable(model, labels, detailTableState)}
  `;
}

function getFinalPathPreviewEntries(state) {
  const finalPathByChr = getProjectExportFinalPathByChr(state);
  const chromosomeOrder = new Map(
    (Array.isArray(state.projectExport?.chromosomes) ? state.projectExport.chromosomes : [])
      .map((chr, index) => [normalizeString(chr?.chrName), index]),
  );
  const phasedSort = new Map();
  Object.entries(getProjectExportPhasedChrTracksByChr(state)).forEach(([parentChrName, tracks]) => {
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
  return Object.entries(finalPathByChr)
    .map(([key, entry]) => ({
      chrName: normalizeString(entry?.chrName || key),
      parentChrName: normalizeString(entry?.chrName || key),
      phasedTrackKey: "",
      entry,
      lengthBp: Math.max(0, Number(resolveFinalPathTotalLengthBp(entry)) || 0),
    }))
    .filter(({ chrName, entry }) => chrName && Array.isArray(entry?.segments) && entry.segments.length > 0)
    .sort((left, right) => {
      const leftPhased = phasedSort.get(left.chrName);
      const rightPhased = phasedSort.get(right.chrName);
      const leftOrder = leftPhased?.parentOrder
        ?? (chromosomeOrder.has(left.chrName) ? chromosomeOrder.get(left.chrName) : Number.MAX_SAFE_INTEGER);
      const rightOrder = rightPhased?.parentOrder
        ?? (chromosomeOrder.has(right.chrName) ? chromosomeOrder.get(right.chrName) : Number.MAX_SAFE_INTEGER);
      const leftHaplotypeOrder = leftPhased?.haplotypeOrder ?? 0;
      const rightHaplotypeOrder = rightPhased?.haplotypeOrder ?? 0;
      return leftOrder - rightOrder || leftHaplotypeOrder - rightHaplotypeOrder || left.chrName.localeCompare(right.chrName);
    })
    .map((row) => {
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

function renderFinalPathPreviewTrack({ entry, lengthBp, maxLengthBp, primaryDatasetName }) {
  const segments = Array.isArray(entry?.segments) ? entry.segments : [];
  const domainBp = Math.max(1, Number(maxLengthBp || 0), Number(lengthBp || 0));
  let cursorBp = 0;
  const segmentNodes = segments.map((segment, index) => {
    const segmentLengthBp = Math.max(0, resolveFinalPathSegmentLengthBp(segment));
    if (segmentLengthBp <= 0) {
      return "";
    }
    const startPct = Math.max(0, Math.min(100, (cursorBp / domainBp) * 100));
    const endPct = Math.max(startPct, Math.min(100, ((cursorBp + segmentLengthBp) / domainBp) * 100));
    const widthPct = Math.max(0, endPct - startPct);
    cursorBp += segmentLengthBp;
    if (isFinalPathGapSegment(segment)) {
      return `
        <span
          class="project-export-final-path-preview-gap"
          style="left: clamp(0px, calc(${endPct.toFixed(4)}% - 4px), calc(100% - 8px));"
          title="GAP ${formatNumber(segmentLengthBp)} bp"
        ></span>
        <span class="project-export-final-path-preview-gap-label" style="left: clamp(14px, ${endPct.toFixed(4)}%, calc(100% - 14px));">GAP</span>
      `;
    }
    if (!isFinalPathCtgSegment(segment)) {
      return "";
    }
    const label = resolveFinalPathPreviewCtgLabel(segment);
    const isRef = isFinalPathRefSegment(segment);
    const isCompanion = isCompanionFinalPathSegment(segment, primaryDatasetName);
    const afterGapClass = index > 0 && isFinalPathGapSegment(segments[index - 1]) ? " is-after-gap" : "";
    const toneClass = `${isRef ? " is-ref" : isCompanion ? " is-companion" : ""}${afterGapClass}`;
    const title = `${resolveFinalPathSegmentDisplayName(segment)} | ${formatNumber(segmentLengthBp)} bp`;
    return `
      <span
        class="project-export-final-path-preview-ctg${toneClass}"
        style="left: ${startPct.toFixed(4)}%; width: ${widthPct.toFixed(4)}%;"
        title="${escapeAttr(title)}"
      >
        <span>${escapeHtml(label)}</span>
      </span>
    `;
  }).join("");
  return `
    <div class="project-export-final-path-preview-track" aria-hidden="true">
      ${segmentNodes}
    </div>
  `;
}

function renderFinalPathPreviewRows(state, { primaryDatasetName }) {
  const rows = getFinalPathPreviewEntries(state);
  if (!rows.length) {
    return "";
  }
  const maxLengthBp = Math.max(1, ...rows.map((row) => Math.max(0, Number(row.lengthBp || 0))));
  return `
    <section class="project-export-final-path-list" aria-label="final path">
      ${rows.map(({ chrName, parentChrName, phasedTrackKey, entry, lengthBp }) => `
        <div
          class="project-export-final-path-row"
          role="button"
          tabindex="0"
          data-project-export-jump-parent-chr="${escapeAttr(parentChrName || chrName)}"
          data-project-export-jump-phased-key="${escapeAttr(phasedTrackKey || "")}"
          data-project-export-jump-chr="${escapeAttr(chrName)}"
          title="${escapeAttr(chrName)}"
        >
          <strong class="project-export-final-path-row-label">${escapeHtml(chrName)}</strong>
          <div class="project-export-final-path-row-graph" aria-hidden="true">
            ${renderFinalPathPreviewTrack({
              entry,
              lengthBp,
              maxLengthBp,
              primaryDatasetName,
            })}
            <span class="project-export-final-path-preview-length">${escapeHtml(`${formatNumber(lengthBp)} bp`)}</span>
          </div>
        </div>
      `).join("")}
    </section>
  `;
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

function resolveProjectExportKindLabel(job, labels) {
  const kind = normalizeString(job?.kind).toLowerCase();
  if (kind === "png") {
    return labels.exportPng || "图(.png)";
  }
  if (kind === "tsv") {
    return labels.exportTsv || "表(.tsv)";
  }
  if (kind === "fasta") {
    return labels.exportFasta || "序列(.fasta)";
  }
  if (kind === "log") {
    return labels.exportLog || "日志(.log)";
  }
  if (kind === "all") {
    return labels.exportAll || "All";
  }
  return kind || (labels.export || "Export");
}

function resolveProjectExportStatusText(job, labels) {
  if (job?.status === "success") {
    return labels.completed || "已完成导出";
  }
  if (job?.status === "error") {
    return labels.failed || "导出失败";
  }
  if (job?.status === "canceled") {
    return labels.canceled || "已终止，已保留已导出的文件";
  }
  const template = labels.exportRunning || "正在执行：{step}";
  return template.replace("{step}", normalizeString(job?.currentStep));
}

function renderProjectExportStepIcon(status) {
  if (status === "running") {
    return `<span class="pipeline-spinner" aria-hidden="true"></span>`;
  }
  if (status === "done") {
    return `<span class="pipeline-done" aria-hidden="true">&#10003;</span>`;
  }
  if (status === "error") {
    return `<span class="pipeline-error" aria-hidden="true">&#10007;</span>`;
  }
  if (status === "skipped") {
    return `<span class="pipeline-skipped" aria-hidden="true">-</span>`;
  }
  return `<span class="pipeline-pending" aria-hidden="true">&#9675;</span>`;
}

function resolveProjectExportStepStatus(job, step) {
  const completedOutputs = Array.isArray(job?.completedOutputs) ? job.completedOutputs : [];
  const currentStep = normalizeString(job?.currentStep);
  const stepLabel = normalizeString(step?.label);
  if (completedOutputs.includes(step?.outputPath)) {
    return "done";
  }
  if (job?.status === "running" && currentStep && stepLabel && currentStep.includes(stepLabel)) {
    return "running";
  }
  if (job?.status === "error" && currentStep && stepLabel && currentStep.includes(stepLabel)) {
    return "error";
  }
  if (job?.status === "canceled") {
    return "skipped";
  }
  return "pending";
}

function renderProjectExportSteps(job) {
  const steps = Array.isArray(job?.steps) ? job.steps : [];
  if (!steps.length) {
    return "";
  }
  return `
    <div class="assembly-final-path-export-steps">
      ${steps.map((step) => {
        const stepStatus = resolveProjectExportStepStatus(job, step);
        return `
          <div
            class="pipeline-step-row assembly-final-path-export-step ${escapeAttr(stepStatus)}"
            data-project-export-step-status="${escapeAttr(stepStatus)}"
          >
            <span class="pipeline-step-label">${escapeHtml(String(step?.label || ""))}</span>
            <span class="pipeline-step-icon">${renderProjectExportStepIcon(stepStatus)}</span>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderProjectExportCompletedOutputs(job) {
  const outputs = Array.isArray(job?.completedOutputs) ? job.completedOutputs : [];
  if (!outputs.length) {
    return "";
  }
  return `
    <ul class="assembly-final-path-export-output-list">
      ${outputs.map((outputPath) => `<li>${escapeHtml(String(outputPath || ""))}</li>`).join("")}
    </ul>
  `;
}

function renderProjectExportJobModal(job, labels) {
  if (!job?.open) {
    return "";
  }
  const kindLabel = resolveProjectExportKindLabel(job, labels);
  const statusText = resolveProjectExportStatusText(job, labels);
  const statusClass = job?.status === "success" ? "success" : "";
  return `
    <div class="modal-overlay assembly-final-path-export-overlay" data-project-export-overlay="true">
      <article
        class="card modal-dialog assembly-final-path-export-dialog"
        data-project-export-modal="true"
        role="dialog"
        aria-modal="true"
        aria-label="${escapeAttr(labels.exportDialogTitle || "正在导出 final path")}"
      >
        <button
          type="button"
          class="button ghost tiny assembly-final-path-export-close"
          data-project-export-close="true"
        >x</button>
        <div class="assembly-final-path-export-body">
          <header class="assembly-final-path-export-head">
            <h4>${escapeHtml(labels.exportDialogTitle || "正在导出 final path")}</h4>
            <p class="muted">${escapeHtml(`${normalizeString(job?.projectName)} · ${kindLabel}`)}</p>
          </header>
          ${renderProjectExportSteps(job)}
          <p class="muted assembly-final-path-export-status ${escapeAttr(statusClass)}">${escapeHtml(statusText)}</p>
          ${job?.error ? `<p class="error-text">${escapeHtml(String(job.error || ""))}</p>` : ""}
          ${renderProjectExportCompletedOutputs(job)}
        </div>
      </article>
    </div>
  `;
}

function renderProjectExportMenu({ labels, canExportFasta = true, canExportLog = true }) {
  const fastaItem = canExportFasta
    ? `<button type="button" class="final-path-export-item" data-project-export-action="fasta">${escapeHtml(labels.exportFasta)}</button>`
    : "";
  const logItem = canExportLog
    ? `<button type="button" class="final-path-export-item" data-project-export-action="log">${escapeHtml(labels.exportLog)}</button>`
    : "";
  return `
    <div class="final-path-export" data-project-export>
      <button
        type="button"
        class="button ghost tiny final-path-export-toggle"
        data-project-export-toggle="true"
        aria-expanded="false"
      >${escapeHtml(labels.export)}</button>
      <div class="final-path-export-menu is-hidden" data-project-export-menu>
        <button type="button" class="final-path-export-item" data-project-export-action="png">${escapeHtml(labels.exportPng)}</button>
        <button type="button" class="final-path-export-item" data-project-export-action="tsv">${escapeHtml(labels.exportTsv)}</button>
        ${logItem}
        ${fastaItem}
        <button type="button" class="final-path-export-item" data-project-export-action="all">${escapeHtml(labels.exportAll)}</button>
      </div>
    </div>
  `;
}

export function renderProjectExportPage(state) {
  const labels = getLabels(state);
  const currentProject = getCurrentProject(state);
  const exportState = getScopedProjectExportState(state);
  if (!currentProject) {
    return `<section class="page project-export-page"><h3>${escapeHtml(labels.title)}</h3><p class="muted">${escapeHtml(labels.noProject)}</p></section>`;
  }
  const model = buildProjectExportDataModel(state);
  const primaryDatasetName = model.primaryDatasetName || "-";
  const summaryLine = model.refChrNames.length
    ? `<div class="project-export-summary-line"><span>ref: <strong>${escapeHtml(model.refChrNames.join(", "))}</strong></span></div>`
    : "";
  return `
    <section class="page project-export-page">
      <div class="project-export-head">
        <div class="project-export-title-row">
          <h3>${escapeHtml(labels.title)}</h3>
          <p class="muted">${escapeHtml(labels.project)}: ${escapeHtml(state.session?.projectName || currentProject.projectName || "-")} · ${escapeHtml(labels.primaryDataset)}: ${escapeHtml(primaryDatasetName)}</p>
        </div>
        ${renderProjectExportMenu({
          labels,
          canExportFasta: canProjectExportFasta(state),
          canExportLog: model.canExportLog,
        })}
      </div>
      ${exportState.loading ? `<p class="muted">${escapeHtml(labels.loading)}</p>` : ""}
      ${exportState.error ? `<p class="error-text">${escapeHtml(labels.loadFailed)} ${escapeHtml(exportState.error)}</p>` : ""}
      ${summaryLine}
      ${renderProjectExportJobModal(exportState.job, labels)}
      ${renderStats(model, labels, normalizeDetailTableState(state))}
      ${renderFinalPathPreviewRows(state, { primaryDatasetName })}
    </section>
  `;
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
      loading: false,
      chromosomes: [],
      selectedChrName: normalizedChrName,
      activePhasedTrackKey: normalizedPhasedKey,
      chrCtgs: [],
      refTrackMembers: [],
      supportChrCtgs: [],
      deletedCtgs: [],
      selectedDeletedCtgRecordIds: [],
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedCtgId: null,
      selectedMemberSeqId: null,
      ctgDetail: null,
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

function rerender(host, store) {
  host.innerHTML = renderProjectExportPage(store.getState());
  bindProjectExportPage(host, store);
  syncProjectExportDetailFilterControls(host);
  syncProjectExportPreviewLabels(host);
}

function setProjectExportJob(host, store, nextJob) {
  const state = store.getState();
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
  }, PROJECT_EXPORT_DETAIL_FILTER_CLOSE_DELAY_MS));
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

async function loadProjectExportData(host, store, deps = {}) {
  const state = store.getState();
  const currentProject = getCurrentProject(state);
  if (!currentProject || !state.session?.workspacePath || !state.session?.projectId) {
    return false;
  }
  const requestedWorkspacePath = normalizeString(state.session.workspacePath);
  const requestedProjectId = Number(state.session.projectId);
  const previousProjectExport = state.projectExport || {};
  store.setState({
    ...state,
    projectExport: {
      ...buildEmptyProjectExportState(),
      detailTableFilters: previousProjectExport.detailTableFilters,
      detailTableSort: previousProjectExport.detailTableSort,
      loading: true,
      loaded: false,
      error: "",
      projectId: requestedProjectId,
      workspacePath: requestedWorkspacePath,
    },
  });
  rerender(host, store);
  try {
    const listChromosomes = deps.listProjectChromosomes || listProjectChromosomes;
    const listCtgs = deps.listChrViewCtgs || listChrViewCtgs;
    const listPhasedTracks = deps.listPhasedChrTracks || listPhasedChrTracks;
    const getViewState = deps.getProjectAssemblyViewState || getProjectAssemblyViewState;
    const chromosomeResult = await listChromosomes({
      workspaceRoot: requestedWorkspacePath,
      projectId: requestedProjectId,
    });
    const viewState = await getViewState({
      workspaceRoot: requestedWorkspacePath,
      projectId: requestedProjectId,
    });
    const primaryDatasetId = normalizeDatasetId(currentProject.primaryDatasetId);
    const primaryCtgsByChr = {};
    const ctgsByChr = {};
    const phasedChrTracksByChr = {};
    for (const chr of chromosomeResult.items || []) {
      const chrName = normalizeString(chr?.chrName);
      if (!chrName) {
        continue;
      }
      const allResult = await listCtgs({
        workspaceRoot: requestedWorkspacePath,
        projectId: requestedProjectId,
        chrName,
        datasetId: null,
      });
      ctgsByChr[chrName] = allResult.items || [];
      const result = await listCtgs({
        workspaceRoot: requestedWorkspacePath,
        projectId: requestedProjectId,
        chrName,
        datasetId: primaryDatasetId,
      });
      primaryCtgsByChr[chrName] = result.items || [];
      if (currentProject?.phasedAssemblyEnabled && typeof listPhasedTracks === "function") {
        const phasedResult = await listPhasedTracks({
          workspaceRoot: requestedWorkspacePath,
          projectId: requestedProjectId,
          parentChrName: chrName,
        });
        const tracks = normalizePhasedTrackMap({ [chrName]: phasedResult?.tracks || [] })[chrName] || [];
        if (tracks.length) {
          phasedChrTracksByChr[chrName] = tracks;
        }
      }
    }
    const mergedFinalPathByChr = mergeFinalPathByChr(
      viewState.finalPathByChr,
      store.getState().assembly?.finalPathByChr,
    );
    const latestState = store.getState();
    if (
      normalizeString(latestState.session?.workspacePath) !== requestedWorkspacePath
      || Number(latestState.session?.projectId || 0) !== requestedProjectId
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
      },
    });
    rerender(host, store);
    return true;
  } catch (error) {
    const latestState = store.getState();
    if (
      normalizeString(latestState.session?.workspacePath) !== requestedWorkspacePath
      || Number(latestState.session?.projectId || 0) !== requestedProjectId
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
    rerender(host, store);
    return false;
  }
}

async function resolveProjectExportTarget({ state, kind, baseName, deps = {} }) {
  const normalizedKind = normalizeString(kind).toLowerCase();
  const pickSaveFile = deps.pickSaveFilePath || pickSaveFilePath;
  const pickDirectory = deps.pickDirectoryPath || pickDirectoryPath;
  if (normalizedKind === "png") {
    return pickSaveFile({
      defaultPath: `${baseName}.png`,
      filters: [{ name: "PNG", extensions: ["png"] }],
    }, state);
  }
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
  const normalizedKind = normalizeString(kind).toLowerCase();
  const buildStep = (stepKind, label, extension) => ({
    kind: stepKind,
    label,
    outputPath: normalizedKind === "all"
      ? joinOutputPath(targetPath, `${baseName}.${extension}`)
      : targetPath,
  });
  if (normalizedKind === "png") {
    return [buildStep("png", "图(.png)", "png")];
  }
  if (normalizedKind === "tsv") {
    return [buildStep("tsv", "表(.tsv)", "tsv")];
  }
  if (normalizedKind === "log") {
    return canExportLog ? [buildStep("log", "日志(.log)", "log")] : [];
  }
  if (normalizedKind === "fasta") {
    return canExportFasta ? [buildStep("fasta", "序列(.fasta)", "fasta")] : [];
  }
  if (normalizedKind === "all") {
    const steps = [
      buildStep("png", "图(.png)", "png"),
      buildStep("tsv", "表(.tsv)", "tsv"),
    ];
    if (canExportLog) {
      steps.push(buildStep("log", "日志(.log)", "log"));
    }
    if (canExportFasta) {
      steps.push(buildStep("fasta", "序列(.fasta)", "fasta"));
    }
    return steps;
  }
  return [];
}

async function runProjectExport(host, store, kind, deps = {}) {
  const currentState = store.getState();
  if (
    !currentState.projectExport?.projectId
    || Number(currentState.projectExport.projectId) !== Number(currentState.session?.projectId || 0)
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
  const resolveTarget = deps.resolveProjectExportTarget || resolveProjectExportTarget;
  let targetPath = await resolveTarget({
    state,
    kind: normalizedKind,
    baseName,
    deps,
  });
  if (!targetPath) {
    return false;
  }
  if (normalizedKind !== "all") {
    targetPath = appendTimestampToOutputPath(targetPath, exportTimestamp);
  }
  const primaryDatasetName = model.primaryDatasetName;
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
  setProjectExportJob(host, store, job);
  const writeText = deps.writeFinalPathExportTextFile || writeFinalPathExportTextFile;
  const writeBinary = deps.writeFinalPathExportBinaryFile || writeFinalPathExportBinaryFile;
  const exportFasta = deps.exportProjectFinalPathFasta || exportProjectFinalPathFasta;
  const renderPng = deps.renderFinalPathViewportPng || renderFinalPathViewportPng;
  const completedOutputs = [];
  try {
    const exportEntries = enrichProjectFinalPathEntriesForExport(entries, state);
    const finalPathByChr = buildProjectFinalPathByChr(exportEntries);
    for (const step of steps) {
      let currentJob = store.getState().projectExport?.job || job;
      if (currentJob.cancelRequested) {
        setProjectExportJob(host, store, {
          ...currentJob,
          status: "canceled",
          completedOutputs: [...completedOutputs],
          error: "",
        });
        return false;
      }
      setProjectExportJob(host, store, {
        ...currentJob,
        status: "running",
        currentStep: step.label || step.kind,
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
      } else if (step.kind === "fasta") {
        await exportFasta({
          workspaceRoot: state.session?.workspacePath || "",
          projectId: Number(state.session?.projectId || 0),
          finalPathByChr,
          outputPath: step.outputPath,
          stateOrLocale: state,
        });
      } else if (step.kind === "png") {
        await writeBinary({
          outputPath: step.outputPath,
          bytesBase64: await renderPng(buildProjectFinalPathSvgSnapshot({
            entries: exportEntries,
            projectName,
            primaryDatasetName,
          })),
          stateOrLocale: state,
        });
      }
      completedOutputs.push(step.outputPath);
      currentJob = store.getState().projectExport?.job || job;
      if (currentJob.cancelRequested) {
        setProjectExportJob(host, store, {
          ...currentJob,
          status: "canceled",
          completedOutputs: [...completedOutputs],
          error: "",
        });
        return false;
      }
    }
    setProjectExportJob(host, store, {
      ...(store.getState().projectExport?.job || job),
      status: "success",
      currentStep: "",
      completedOutputs,
      error: "",
    });
    return true;
  } catch (error) {
    setProjectExportJob(host, store, {
      ...(store.getState().projectExport?.job || job),
      status: "error",
      currentStep: "",
      completedOutputs,
      error: String(error?.message || error || ""),
    });
    return false;
  }
}

export function bindProjectExportPage(host, store, deps = {}) {
  if (!host || host[PROJECT_EXPORT_BOUND]) {
    syncProjectExportDetailFilterControls(host);
    syncProjectExportPreviewLabels(host);
    return;
  }
  host[PROJECT_EXPORT_BOUND] = true;
  syncProjectExportDetailFilterControls(host);
  syncProjectExportPreviewLabels(host);
  if (!host[PROJECT_EXPORT_RESIZE_BOUND] && typeof window !== "undefined" && window?.addEventListener) {
    host[PROJECT_EXPORT_RESIZE_BOUND] = true;
    window.addEventListener("resize", () => syncProjectExportPreviewLabels(host));
  }
  const state = store.getState();
  if (
    state.session?.projectId
    && (!state.projectExport?.projectId || Number(state.projectExport.projectId) !== Number(state.session.projectId))
    && !(isProjectExportStateForCurrentSession(state) && state.projectExport?.loading)
  ) {
    void loadProjectExportData(host, store, deps);
  }
  const setExportMenuOpen = (exportRoot, shouldOpen) => {
    const menuNode = exportRoot?.querySelector?.("[data-project-export-menu]");
    const toggleNode = exportRoot?.querySelector?.("[data-project-export-toggle]");
    if (!menuNode) {
      return;
    }
    menuNode.classList.toggle("is-hidden", !shouldOpen);
    if (toggleNode) {
      toggleNode.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
    }
  };
  host.addEventListener("click", async (event) => {
    const closeNode = event.target?.closest?.("[data-project-export-close]");
    if (closeNode) {
      const currentState = store.getState();
      const projectExport = currentState.projectExport || {};
      const nextProjectExport = projectExport.job?.status === "running"
        ? requestCancelProjectExport(projectExport)
        : closeProjectExportDialog(projectExport);
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
    const actionNode = event.target?.closest?.("[data-project-export-action]");
    if (!actionNode) {
      return;
    }
    setExportMenuOpen(actionNode.closest?.("[data-project-export]"), false);
    await runProjectExport(host, store, actionNode.dataset.projectExportAction, deps);
  });
  bindDelegatedDelayedFloatingClose(host, {
    rootSelector: "[data-project-export]",
    timerKey: PROJECT_EXPORT_MENU_CLOSE_TIMER,
    close: (exportRoot) => setExportMenuOpen(exportRoot, false),
  });
  host.addEventListener("change", (event) => {
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
    const detailsNode = event.target?.closest?.(".project-export-detail-filter");
    if (detailsNode) {
      clearProjectExportDetailFilterCloseTimer(detailsNode);
    }
  });
  host.addEventListener("pointerout", (event) => {
    const detailsNode = event.target?.closest?.(".project-export-detail-filter");
    if (!detailsNode || detailsNode.contains?.(event.relatedTarget)) {
      return;
    }
    scheduleProjectExportDetailFilterClose(detailsNode);
  });
  host.addEventListener("keydown", (event) => {
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

export const __test = {
  buildProjectExportDataModel,
  buildProjectFinalPathByChr,
  buildProjectFinalPathTsvText,
  buildProjectFinalPathSvgSnapshot,
  enrichProjectFinalPathEntriesForExport,
  getLabels,
  getFinalPathPreviewEntries,
  getProjectExportFinalPathByChr,
  getProjectExportHiddenPrimaryCtgIdsByChr,
  planProjectExportSteps,
  resolveProjectExportTarget,
  jumpToAssemblyChr,
  loadProjectExportData,
  runProjectExport,
  syncProjectExportDetailFilterControls,
  syncProjectExportPreviewLabels,
};
