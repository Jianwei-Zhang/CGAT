import {
  DEFAULT_MAX_TICK_COUNT,
  DEFAULT_MIN_TICK_UNIT_KB,
  MAX_TICK_COUNT_OPTIONS,
  MIN_TICK_UNIT_KB_OPTIONS,
  normalizePositiveInt,
  resolveTickBpFromScale,
  resolveTrackInnerWidthFromScale,
  resolveTrackPrefs,
} from "./track-prefs.js";
import {
  isFinalPathCtgSegment,
  isFinalPathGapSegment,
  isFinalPathRefSegment,
  normalizeFinalPathViewMode,
  resolveFinalPathSegmentDisplayName,
  resolveFinalPathSegmentLengthBp,
  resolveFinalPathTotalLengthBp,
} from "./final-path-state.js";
import { buildFinalPathLogModel, canUseFinalPathLog } from "./final-path-log-state.js";

function normalizeViewMode(viewMode, hasLog = false) {
  const normalized = normalizeFinalPathViewMode(viewMode);
  if (normalized === "log" && !hasLog) {
    return "graph";
  }
  return normalized;
}

function normalizeString(value) {
  return String(value || "").trim();
}

function resolveFinalPathDisplayCtgName(segment) {
  return resolveFinalPathSegmentDisplayName(segment);
}

function stripFinalPathCtgAssignmentSuffix(name) {
  const text = String(name || "").trim();
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

function resolveFinalPathVisibleCtgName(segment) {
  if (isFinalPathGapSegment(segment) || isFinalPathRefSegment(segment)) {
    return resolveFinalPathDisplayCtgName(segment);
  }
  return stripFinalPathCtgAssignmentSuffix(resolveFinalPathDisplayCtgName(segment));
}

function buildFinalPathTableRowMetrics(segments) {
  let chrCursor = 1;
  return (Array.isArray(segments) ? segments : []).map((segment) => {
    const segmentLength = Math.max(0, resolveFinalPathSegmentLengthBp(segment));
    const chrStart = segmentLength > 0 ? chrCursor : null;
    const chrEnd = segmentLength > 0 ? (chrCursor + segmentLength - 1) : null;
    if (segmentLength > 0) {
      chrCursor = chrEnd + 1;
    }
    return {
      chrStart,
      chrEnd,
    };
  });
}

function resolveFinalPathSegmentOrient(segment) {
  if (!isFinalPathCtgSegment(segment)) {
    return "";
  }
  const start = Number(segment?.start);
  const end = Number(segment?.end);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start <= 0 || end <= 0) {
    return "";
  }
  return start > end ? "-" : "+";
}

function resolveFinalPathGraphLabelText(segment) {
  const displayCtgName = resolveFinalPathVisibleCtgName(segment);
  const orient = resolveFinalPathSegmentOrient(segment);
  if (!displayCtgName || !orient) {
    return displayCtgName;
  }
  return `${displayCtgName} (${orient})`;
}

function isCompanionFinalPathSegment(segment, primaryDatasetName) {
  const segmentDataset = normalizeString(segment?.datasetName).toLowerCase();
  const primaryDataset = normalizeString(primaryDatasetName).toLowerCase();
  if (!segmentDataset || !primaryDataset) {
    return false;
  }
  return segmentDataset !== primaryDataset;
}

function normalizeFinalPathSegments(finalPathEntry) {
  const segments = Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : [];
  return segments
    .map((segment, index) => ({
      ...segment,
      segmentId: normalizeString(segment?.segmentId) || `seg-${index + 1}`,
    }));
}

function resolveGraphSegmentsForRender(finalPathEntry, previewSegmentOrder = null) {
  const segments = normalizeFinalPathSegments(finalPathEntry);
  if (!Array.isArray(previewSegmentOrder) || !previewSegmentOrder.length) {
    return segments;
  }
  const byId = new Map(segments.map((segment) => [normalizeString(segment.segmentId), segment]));
  const ordered = previewSegmentOrder
    .map((segmentId) => byId.get(normalizeString(segmentId)))
    .filter((segment) => segment);
  const used = new Set(ordered.map((segment) => normalizeString(segment.segmentId)));
  segments.forEach((segment) => {
    const segmentId = normalizeString(segment.segmentId);
    if (!used.has(segmentId)) {
      ordered.push(segment);
    }
  });
  return ordered;
}

const FINAL_PATH_LABEL_COLUMN_WIDTH_PX = 136;
const FINAL_PATH_GRAPH_VIEWPORT_PX = 1200;
const FINAL_PATH_GRAPH_HEIGHT = 154;
const FINAL_PATH_GRAPH_RULER_Y = 24;
const FINAL_PATH_GRAPH_TICK_Y1 = 28;
const FINAL_PATH_GRAPH_TICK_Y2 = 86;
const FINAL_PATH_GRAPH_BAR_Y = 70;
const FINAL_PATH_GRAPH_BAR_HEIGHT = 14;
const FINAL_PATH_GRAPH_TEXT_OFFSET_Y = 11;
const FINAL_PATH_GRAPH_BAR_RADIUS = 4;
const FINAL_PATH_GAP_MARKER_MIN_WIDTH_PX = 8;
const FINAL_PATH_GAP_LABEL_TEXT = "GAP";
const TRACK_EDGE_LABEL_PADDING = 16;

function formatRulerTickLabel(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return "0";
  }
  if (numeric >= 1_000_000 && numeric % 1_000_000 === 0) {
    return `${(numeric / 1_000_000).toLocaleString("en-US")}M`;
  }
  if (numeric >= 1_000) {
    const kbValue = Math.round((numeric / 1_000) * 10) / 10;
    return `${kbValue.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 1 })}k`;
  }
  return numeric.toLocaleString("en-US");
}

function estimateTrackTickLabelWidth(labelText) {
  const text = String(labelText || "");
  return Math.max(12, text.length * 7);
}

function estimateTrackCtgLabelWidth(labelText) {
  const text = String(labelText || "");
  return Math.max(10, text.length * 6.2);
}

function resolveFinalPathCtgLabelPlacement({ labelText, barX, barWidth, barY, textOffsetY }) {
  return resolveFinalPathCtgLabelPlacementForBand({
    labelText,
    barX,
    barWidth,
    barY,
    textOffsetY,
  });
}

function resolveFinalPathCtgLabelPlacementForBand({
  labelText,
  barX,
  barWidth,
  barY = FINAL_PATH_GRAPH_BAR_Y,
  textOffsetY = FINAL_PATH_GRAPH_TEXT_OFFSET_Y,
}) {
  const inlineX = Number(barX || 0) + 4;
  const inlineY = Number(barY || 0) + Number(textOffsetY || 0);
  const estimatedLabelWidth = estimateTrackCtgLabelWidth(labelText);
  const fitsInsideBar = Number(barWidth || 0) >= estimatedLabelWidth + 8;
  if (fitsInsideBar) {
    return {
      x: inlineX,
      y: inlineY,
      textAnchor: "start",
      classSuffix: "",
      transformAttr: "",
      tiltAngleDeg: 0,
    };
  }

  return {
    x: inlineX,
    y: inlineY,
    textAnchor: "start",
    classSuffix: " is-hidden-label",
    transformAttr: "",
    tiltAngleDeg: 0,
    hidden: true,
  };
}

function buildTrackCtgLabelTransformAttr({
  tiltAngleDeg = 0,
  x,
  y,
}) {
  const angle = Number(tiltAngleDeg) || 0;
  if (!angle) {
    return "";
  }
  return ` transform="rotate(${angle} ${Number(x).toFixed(2)} ${Number(y).toFixed(2)})"`;
}

function resolveTrackCtgLabelRightBoundary({
  x,
  labelText,
  tiltAngleDeg = 0,
  textAnchor = "start",
}) {
  const baseX = Number(x) || 0;
  const width = estimateTrackCtgLabelWidth(labelText);
  const projectedWidth = width * Math.cos((Math.abs(Number(tiltAngleDeg) || 0) * Math.PI) / 180);
  if (textAnchor === "end") {
    return baseX;
  }
  if (textAnchor === "middle") {
    return baseX + projectedWidth / 2;
  }
  return baseX + projectedWidth;
}

function resolveTrackCtgLabelLeftBoundary({
  x,
  labelText,
  tiltAngleDeg = 0,
  textAnchor = "start",
}) {
  const baseX = Number(x) || 0;
  const width = estimateTrackCtgLabelWidth(labelText);
  const projectedWidth = width * Math.cos((Math.abs(Number(tiltAngleDeg) || 0) * Math.PI) / 180);
  if (textAnchor === "end") {
    return baseX - projectedWidth;
  }
  if (textAnchor === "middle") {
    return baseX - projectedWidth / 2;
  }
  return baseX;
}

function resolveTrackCtgLabelBounds({
  x,
  labelText,
  tiltAngleDeg = 0,
  textAnchor = "start",
}) {
  return {
    left: resolveTrackCtgLabelLeftBoundary({
      x,
      labelText,
      tiltAngleDeg,
      textAnchor,
    }),
    right: resolveTrackCtgLabelRightBoundary({
      x,
      labelText,
      tiltAngleDeg,
      textAnchor,
    }),
  };
}

function resolveFinalPathCtgLabelPlacements(
  layoutItems,
  gapMarkerLayouts,
  innerWidth,
  visualLayouts = null,
  graphMetrics = {},
) {
  const placements = Array.from({ length: layoutItems.length }, () => null);

  layoutItems.forEach((item, index, items) => {
    const { segment } = item;
    if (!isFinalPathCtgSegment(segment)) {
      return;
    }
    const graphLabelText = resolveFinalPathGraphLabelText(segment);
    if (!graphLabelText) {
      return;
    }
    const { visualStartX, barWidth } = resolveFinalPathCtgVisualLayout(
      items,
      index,
      item,
      innerWidth,
      gapMarkerLayouts,
      visualLayouts,
    );
    const preferredPlacement = resolveFinalPathCtgLabelPlacement({
      labelText: graphLabelText,
      barX: visualStartX,
      barWidth,
      barY: graphMetrics.barY,
      textOffsetY: graphMetrics.textOffsetY,
    });
    if (!preferredPlacement || preferredPlacement.hidden) {
      return;
    }
    const boundedPreferredPlacement = clampTrackCtgLabelPlacementToBounds({
      placement: preferredPlacement,
      labelText: graphLabelText,
      minVisibleX: 0,
      maxVisibleX: innerWidth,
    });
    placements[index] = boundedPreferredPlacement;
  });

  return placements;
}

function clampTrackCtgLabelPlacementToBounds({
  placement,
  labelText,
  minVisibleX = -Infinity,
  maxVisibleX = Infinity,
}) {
  if (!placement) {
    return placement;
  }
  const resolvedMinX = Number.isFinite(minVisibleX) ? Number(minVisibleX) : -Infinity;
  const resolvedMaxX = Number.isFinite(maxVisibleX) ? Number(maxVisibleX) : Infinity;
  if (!(resolvedMinX < resolvedMaxX)) {
    return placement;
  }
  const bounds = resolveTrackCtgLabelBounds({
    x: placement.x,
    labelText,
    tiltAngleDeg: placement.tiltAngleDeg,
    textAnchor: placement.textAnchor,
  });
  let shiftX = 0;
  if (bounds.left < resolvedMinX) {
    shiftX += resolvedMinX - bounds.left;
  }
  if (bounds.right + shiftX > resolvedMaxX) {
    shiftX += resolvedMaxX - (bounds.right + shiftX);
  }
  if (Math.abs(shiftX) < 0.01) {
    return placement;
  }
  const nextX = Number(placement.x) + shiftX;
  return {
    ...placement,
    x: nextX,
    transformAttr: buildTrackCtgLabelTransformAttr({
      tiltAngleDeg: placement.tiltAngleDeg,
      x: nextX,
      y: placement.y,
    }),
  };
}

function resolveFinalPathCtgVisualLayout(
  items,
  index,
  item,
  innerWidth,
  gapMarkerLayouts = [],
  visualLayouts = null,
) {
  if (Array.isArray(visualLayouts) && visualLayouts[index]) {
    const visualLayout = visualLayouts[index];
    const visualStartX = Math.max(0, Number(visualLayout.x) || 0);
    const barWidth = Math.max(0, Number(visualLayout.width) || 0);
    return {
      visualStartX,
      visualEndX: visualStartX + barWidth,
      barWidth,
    };
  }
  let visualStartX = item.x;
  let visualEndX = item.x + item.width;
  const previousItem = items[index - 1];
  if (previousItem && isFinalPathGapSegment(previousItem.segment)) {
    const previousLayout = gapMarkerLayouts[index - 1] || resolveGapMarkerLayout(previousItem, innerWidth);
    const { markerWidth: previousMarkerWidth, markerX: previousMarkerX } = previousLayout;
    visualStartX = Math.max(visualStartX, previousMarkerX + previousMarkerWidth);
  }
  const nextItem = items[index + 1];
  if (nextItem && isFinalPathGapSegment(nextItem.segment)) {
    const nextLayout = gapMarkerLayouts[index + 1] || resolveGapMarkerLayout(nextItem, innerWidth);
    const { markerX: nextMarkerX } = nextLayout;
    visualEndX = Math.min(visualEndX, nextMarkerX);
  }
  return {
    visualStartX,
    visualEndX,
    barWidth: Math.max(1, visualEndX - visualStartX),
  };
}

function resolveTrackTickLabelBounds(tick) {
  const width = estimateTrackTickLabelWidth(tick?.labelText || "");
  if (tick?.labelAnchor === "start") {
    return { left: tick.labelX, right: tick.labelX + width };
  }
  if (tick?.labelAnchor === "end") {
    return { left: tick.labelX - width, right: tick.labelX };
  }
  return {
    left: tick.labelX - width / 2,
    right: tick.labelX + width / 2,
  };
}

function isTrackTickLabelOverlap(previousTick, endTick) {
  if (!previousTick || !endTick) {
    return false;
  }
  const previousBounds = resolveTrackTickLabelBounds(previousTick);
  const endBounds = resolveTrackTickLabelBounds(endTick);
  return previousBounds.right > endBounds.left;
}

function buildTrackTickItems({ windowStart, windowEnd, tickBp, innerWidth, domainSpanBp }) {
  const ticks = [];
  const resolvedEnd = Math.max(windowStart, windowEnd);
  const firstTick = Math.max(0, Math.ceil(Math.max(0, windowStart) / tickBp) * tickBp);
  for (let bp = firstTick; bp <= resolvedEnd; bp += tickBp) {
    const x = ((Math.min(bp, resolvedEnd) - windowStart) / domainSpanBp) * innerWidth;
    ticks.push({ bp, x });
  }
  const hasEndTick = ticks.length > 0 && Number(ticks[ticks.length - 1].bp) === Number(resolvedEnd);
  if (!hasEndTick) {
    const endX = ((resolvedEnd - windowStart) / domainSpanBp) * innerWidth;
    ticks.push({ bp: resolvedEnd, x: endX });
  }
  return ticks;
}

function renderTrackNumberInput({
  escapeAttr,
  escapeHtml,
  field,
  id,
  label,
  openOptionLabel = "",
  value,
  options,
  extraComboFieldAttr = "",
  inputFieldAttr = "",
}) {
  const normalized = normalizePositiveInt(value) ?? 1;
  const menuId = `${id}-menu`;
  const optionButtons = options
    .map((optionValue) => {
      const active = Number(optionValue) === Number(normalized) ? " is-active" : "";
      const selected = Number(optionValue) === Number(normalized) ? "true" : "false";
      return `<button type="button" class="assembly-track-combo-option${active}" data-track-combo-option data-track-combo-value="${optionValue}" role="option" aria-selected="${selected}">${escapeHtml(String(optionValue))}</button>`;
    })
    .join("");
  const inputFieldMarkup = inputFieldAttr ? ` ${inputFieldAttr}="${escapeAttr(field)}"` : "";
  const extraComboFieldMarkup = extraComboFieldAttr ? ` ${extraComboFieldAttr}="${escapeAttr(field)}"` : "";
  return `
    <div class="assembly-track-combo" data-track-combo-field="${escapeAttr(field)}"${extraComboFieldMarkup}>
      <input
        id="${id}"
        class="assembly-track-combo-input"
        type="text"
        inputmode="numeric"
        pattern="[0-9]*"
        value="${escapeAttr(String(normalized))}"
        autocomplete="off"
        ${inputFieldMarkup}
        aria-controls="${escapeAttr(menuId)}"
        aria-expanded="false"
      >
      <button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="${escapeAttr(openOptionLabel || label)}" aria-expanded="false" aria-controls="${escapeAttr(menuId)}">
        <span class="assembly-track-control-marker" aria-hidden="true">▾</span>
      </button>
      <div id="${menuId}" class="assembly-track-combo-menu is-hidden" role="listbox">
        ${optionButtons}
      </div>
    </div>
  `;
}

function renderFinalPathHeadControls({
  escapeAttr,
  escapeHtml,
  ariaLabel,
  labels,
  trackControls,
  exportMenu = "",
  extraComboFieldAttr = "",
  inputFieldAttr = "",
  idPrefix = "final-path-track",
}) {
  return `
    <div class="final-path-card-head-controls">
      <div class="assembly-track-inline-controls final-path-track-inline-controls" role="group" aria-label="${escapeAttr(ariaLabel)}">
        <label class="assembly-track-inline-field">
          <span>${escapeHtml(labels.minTickUnitLabel)}</span>
          ${renderTrackNumberInput({
            escapeAttr,
            escapeHtml,
            field: "minTickUnitKb",
            id: `${idPrefix}-min-tick-unit-kb`,
            label: labels.minTickUnitLabel,
            openOptionLabel: labels.openMinTickUnitLabel,
            value: trackControls.minTickUnitKb,
            options: MIN_TICK_UNIT_KB_OPTIONS,
            extraComboFieldAttr,
            inputFieldAttr,
          })}
        </label>
        <label class="assembly-track-inline-field">
          <span>${escapeHtml(labels.maxTickCountLabel)}</span>
          ${renderTrackNumberInput({
            escapeAttr,
            escapeHtml,
            field: "maxTickCount",
            id: `${idPrefix}-max-tick-count`,
            label: labels.maxTickCountLabel,
            openOptionLabel: labels.openMaxTickCountLabel,
            value: trackControls.maxTickCount,
            options: MAX_TICK_COUNT_OPTIONS,
            extraComboFieldAttr,
            inputFieldAttr,
          })}
        </label>
      </div>
      ${exportMenu}
    </div>
  `;
}

function renderFinalPathExportMenu({
  escapeHtml,
  labels,
  canExportFasta = true,
  canExportLog = false,
  canExportDegapJobs = false,
}) {
  const fastaItem = canExportFasta
    ? `
        <button type="button" class="final-path-export-item" data-final-path-export-action="fasta">${escapeHtml(labels.finalPathExportFasta || "序列(.fasta)")}</button>`
    : "";
  const logItem = canExportLog
    ? `
        <button type="button" class="final-path-export-item" data-final-path-export-action="log">${escapeHtml(labels.finalPathExportLog || "日志(.log)")}</button>`
    : "";
  const degapJobsItem = canExportDegapJobs
    ? `
        <button type="button" class="final-path-export-item" data-final-path-export-action="degap-jobs">${escapeHtml(labels.finalPathExportDegapJobs || "DEGAP-JOBS")}</button>`
    : "";
  const degapJobsDivider = canExportDegapJobs
    ? `
        <div class="final-path-export-divider" role="separator" aria-hidden="true"></div>`
    : "";
  return `
    <div class="final-path-export" data-final-path-export>
      <button
        type="button"
        class="button ghost tiny final-path-export-toggle"
        data-final-path-export-toggle="true"
        aria-expanded="false"
      >${escapeHtml(labels.finalPathExport || "Export")}</button>
      <div class="final-path-export-menu is-hidden" data-final-path-export-menu>
        <button type="button" class="final-path-export-item" data-final-path-export-action="png">${escapeHtml(labels.finalPathExportPng || "图(.png)")}</button>
        <button type="button" class="final-path-export-item" data-final-path-export-action="tsv">${escapeHtml(labels.finalPathExportTsv || "表(.tsv)")}</button>
        ${logItem}
        ${fastaItem}
        <button type="button" class="final-path-export-item" data-final-path-export-action="all">${escapeHtml(labels.finalPathExportAll || "All")}</button>
        ${degapJobsDivider}
        ${degapJobsItem}
      </div>
    </div>
  `;
}

function formatLogNumber(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return "0";
  }
  return Math.trunc(numeric).toLocaleString("en-US");
}

function renderFinalPathLogRows({
  rows,
  escapeHtml,
  emptyText,
}) {
  const safeRows = Array.isArray(rows) ? rows : [];
  if (!safeRows.length) {
    return `<div class="muted final-path-log-empty">${escapeHtml(emptyText || "No data")}</div>`;
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
  const bodyRows = safeRows.map((row, index) => {
    const typeSpan = rowTypeSpans[index] || 0;
    const typeCell = typeSpan > 0
      ? `<td class="final-path-log-type-cell" rowspan="${typeSpan}">${escapeHtml(row.typeLabel || "")}</td>`
      : "";
    return `
      <tr>
        ${typeCell}
        <td>${escapeHtml(row.datasetName || "")}</td>
        <td>${escapeHtml(row.originId || "")}</td>
        <td>${escapeHtml(row.finalPathStart ? formatLogNumber(row.finalPathStart) : "")}</td>
        <td>${escapeHtml(row.finalPathEnd ? formatLogNumber(row.finalPathEnd) : "")}</td>
        <td>${escapeHtml(formatLogNumber(row.lengthBp))}</td>
        <td>${escapeHtml((row.usedByChrNames || []).join(", "))}</td>
      </tr>
    `;
  }).join("");
  return `
    <div class="final-path-log-table-wrap">
      <table class="final-path-log-table">
        <thead>
          <tr>
            <th>${escapeHtml("Type")}</th>
            <th>${escapeHtml("dataset")}</th>
            <th>${escapeHtml("origin_id")}</th>
            <th>${escapeHtml("start")}</th>
            <th>${escapeHtml("end")}</th>
            <th>${escapeHtml("length_bp")}</th>
            <th>${escapeHtml("used_by_chr")}</th>
          </tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  `;
}

function renderFinalPathLogRatioBar({
  appended,
  hidden,
  total,
  appendedTitle,
  hiddenTitle,
  escapeAttr,
}) {
  const denominator = Math.max(0, Number(total || 0));
  const appendedValue = Math.max(0, Number(appended || 0));
  const hiddenValue = Math.max(0, Number(hidden || 0));
  if (denominator <= 0 || appendedValue + hiddenValue <= 0) {
    return `<span class="final-path-log-ratio-bar" aria-hidden="true"></span>`;
  }
  const appendedPct = Math.min(100, (appendedValue / denominator) * 100);
  const hiddenPct = Math.min(100 - appendedPct, (hiddenValue / denominator) * 100);
  const escapeTitle = typeof escapeAttr === "function"
    ? escapeAttr
    : (value) => String(value);
  const ariaLabel = [appendedTitle, hiddenTitle].filter(Boolean).join("; ");
  return `
    <span class="final-path-log-ratio-bar" role="img" aria-label="${escapeTitle(ariaLabel)}">
      <span class="final-path-log-ratio-segment is-appended" style="width: ${appendedPct.toFixed(3)}%" title="${escapeTitle(appendedTitle || "")}"></span>
      <span class="final-path-log-ratio-segment is-log-hidden" style="width: ${hiddenPct.toFixed(3)}%" title="${escapeTitle(hiddenTitle || "")}"></span>
    </span>
  `;
}

function renderFinalPathLogStat({
  escapeHtml,
  escapeAttr,
  title,
  value,
  appended,
  hidden,
  total,
  appendedTitle,
  hiddenTitle,
}) {
  return `
    <div class="final-path-log-stat">
      <span class="final-path-log-stat-label">${escapeHtml(title)}</span>
      ${renderFinalPathLogRatioBar({
        appended,
        hidden,
        total,
        appendedTitle,
        hiddenTitle,
        escapeAttr,
      })}
      <strong class="final-path-log-stat-value">${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderFinalPathLog({
  escapeHtml,
  escapeAttr,
  labels,
  logModel,
  currentChrName = "",
}) {
  const model = logModel || buildFinalPathLogModel();
  const normalizedCurrentChrName = normalizeString(model.chrName || currentChrName);
  const supportTypeLabel = labels.finalPathLogSupportTitle || "Support ds ctgs";
  const otherChrTypeLabel = labels.finalPathLogOtherChrTitle || "Primary ds ctgs used by other chr";
  const detailRows = [
    ...(Array.isArray(model.supportRows) ? model.supportRows : []).map((row) => ({
      ...row,
      typeLabel: supportTypeLabel,
      usedByChrNames: normalizedCurrentChrName ? [normalizedCurrentChrName] : [],
    })),
    ...(Array.isArray(model.otherChrPrimaryRows) ? model.otherChrPrimaryRows : []).map((row) => ({
      ...row,
      typeLabel: otherChrTypeLabel,
    })),
  ];
  const detailSection = detailRows.length
    ? `
      <section class="final-path-log-section">
        ${renderFinalPathLogRows({
          rows: detailRows,
          escapeHtml,
          emptyText: labels.finalPathLogNoRows || "No rows",
        })}
      </section>
    `
    : "";
  return `
    <div class="final-path-log-body">
      <div class="final-path-log-summary">
        <div class="final-path-log-legend" aria-hidden="true">
          <span><i class="final-path-log-swatch is-appended"></i>${escapeHtml(labels.finalPathLogAppended || "Appended")}</span>
          <span><i class="final-path-log-swatch is-log-hidden"></i>${escapeHtml(labels.finalPathLogHidden || "Hidden")}</span>
        </div>
        ${renderFinalPathLogStat({
          escapeHtml,
          escapeAttr,
          title: labels.finalPathLogPrimaryCount || "used_primary_ds_ctg_count",
          value: `${formatLogNumber(model.primaryCount.used)}/${formatLogNumber(model.primaryCount.total)}`,
          appended: model.primaryCount.appended,
          hidden: model.primaryCount.hidden,
          total: model.primaryCount.total,
          appendedTitle: `${labels.finalPathLogAppended || "Appended"}: ${formatLogNumber(model.primaryCount.appended)}/${formatLogNumber(model.primaryCount.total)}`,
          hiddenTitle: `${labels.finalPathLogHidden || "Hidden"}: ${formatLogNumber(model.primaryCount.hidden)}/${formatLogNumber(model.primaryCount.total)}`,
        })}
        ${renderFinalPathLogStat({
          escapeHtml,
          escapeAttr,
          title: labels.finalPathLogPrimaryLength || "used_primary_ds_ctg_length",
          value: `${formatLogNumber(model.primaryLength.usedBp)}/${formatLogNumber(model.primaryLength.totalBp)}`,
          appended: model.primaryLength.appendedBp,
          hidden: model.primaryLength.hiddenBp,
          total: model.primaryLength.totalBp,
          appendedTitle: `${labels.finalPathLogAppended || "Appended"}: ${formatLogNumber(model.primaryLength.appendedBp)}/${formatLogNumber(model.primaryLength.totalBp)} bp`,
          hiddenTitle: `${labels.finalPathLogHidden || "Hidden"}: ${formatLogNumber(model.primaryLength.hiddenBp)}/${formatLogNumber(model.primaryLength.totalBp)} bp`,
        })}
      </div>
      ${detailSection}
    </div>
  `;
}

function resolveSegmentLayoutItems(segments, domainSpanBp, innerWidth) {
  let cursorBp = 0;
  return segments.map((segment) => {
    const segmentLength = resolveFinalPathSegmentLengthBp(segment);
    const startBp = cursorBp;
    const endBp = cursorBp + segmentLength;
    cursorBp = endBp;
    const x = (startBp / domainSpanBp) * innerWidth;
    const width = Math.max(0, ((endBp - startBp) / domainSpanBp) * innerWidth);
    return {
      segment,
      segmentLength,
      startBp,
      endBp,
      x,
      width,
    };
  });
}

function distributeWidthsWithMinimums(baseWidths, totalWidth, minWidths) {
  const resolvedBaseWidths = (Array.isArray(baseWidths) ? baseWidths : []).map((width) =>
    Math.max(0, Number(width) || 0),
  );
  const resolvedMinWidths = (Array.isArray(minWidths) ? minWidths : []).map((width) =>
    Math.max(0, Number(width) || 0),
  );
  const resolvedTotalWidth = Math.max(0, Number(totalWidth) || 0);
  const minWidthSum = resolvedMinWidths.reduce((sum, width) => sum + width, 0);
  if (minWidthSum >= resolvedTotalWidth) {
    const factor = minWidthSum > 0 ? resolvedTotalWidth / minWidthSum : 0;
    return resolvedMinWidths.map((width) => width * factor);
  }
  const leftoverWidth = resolvedTotalWidth - minWidthSum;
  const flexWeights = resolvedBaseWidths.map((width, index) =>
    Math.max(0, width - resolvedMinWidths[index]),
  );
  const flexWeightSum = flexWeights.reduce((sum, width) => sum + width, 0);
  if (flexWeightSum <= 0) {
    const eligibleIndexes = resolvedBaseWidths
      .map((width, index) => (width > 0 || resolvedMinWidths[index] > 0 ? index : -1))
      .filter((index) => index >= 0);
    const sharedExtraWidth = eligibleIndexes.length > 0 ? leftoverWidth / eligibleIndexes.length : 0;
    return resolvedMinWidths.map((width, index) =>
      width + (eligibleIndexes.includes(index) ? sharedExtraWidth : 0),
    );
  }
  return resolvedMinWidths.map((width, index) =>
    width + (leftoverWidth * flexWeights[index]) / flexWeightSum,
  );
}

function resolveFinalPathVisualLayouts(items, innerWidth) {
  const resolvedInnerWidth = Math.max(0, Number(innerWidth) || 0);
  const ctgItems = [];
  const gapItems = [];
  items.forEach((item, index) => {
    if (isFinalPathGapSegment(item?.segment)) {
      gapItems.push({
        index,
        baseWidth: Math.max(0, Number(item?.width) || 0),
      });
      return;
    }
    if (isFinalPathCtgSegment(item?.segment)) {
      ctgItems.push({
        index,
        baseWidth: Math.max(0, Number(item?.width) || 0),
      });
    }
  });
  const ctgMinWidths = ctgItems.map(() => 1);
  const desiredGapWidths = gapItems.map(({ baseWidth }) =>
    Math.max(FINAL_PATH_GAP_MARKER_MIN_WIDTH_PX, baseWidth),
  );
  const maxGapBudget = Math.max(
    0,
    resolvedInnerWidth - ctgMinWidths.reduce((sum, width) => sum + width, 0),
  );
  const gapWidthSum = desiredGapWidths.reduce((sum, width) => sum + width, 0);
  const gapWidths = gapWidthSum <= maxGapBudget
    ? desiredGapWidths
    : distributeWidthsWithMinimums(
      desiredGapWidths,
      maxGapBudget,
      desiredGapWidths.map(() => 1),
    );
  const ctgBudget = Math.max(0, resolvedInnerWidth - gapWidths.reduce((sum, width) => sum + width, 0));
  const ctgWidths = distributeWidthsWithMinimums(
    ctgItems.map(({ baseWidth }) => baseWidth),
    ctgBudget,
    ctgMinWidths,
  );
  const gapWidthByIndex = new Map(gapItems.map(({ index }, gapIndex) => [index, gapWidths[gapIndex] || 0]));
  const ctgWidthByIndex = new Map(ctgItems.map(({ index }, ctgIndex) => [index, ctgWidths[ctgIndex] || 0]));
  let cursorX = 0;
  return items.map((item, index) => {
    const width = gapWidthByIndex.has(index)
      ? gapWidthByIndex.get(index)
      : ctgWidthByIndex.get(index) || 0;
    const x = cursorX;
    cursorX += width;
    return {
      x,
      width,
    };
  });
}

function resolveGapMarkerBaseLayout(item, innerWidth) {
  const rawMarkerWidth = Math.max(FINAL_PATH_GAP_MARKER_MIN_WIDTH_PX, item?.width || 0);
  const markerWidth = Math.max(1, Math.min(innerWidth, rawMarkerWidth));
  const rawMarkerX = (item?.x || 0) + (item?.width || 0) / 2 - markerWidth / 2;
  return {
    markerWidth,
    rawMarkerX,
  };
}

function resolveGapMarkerLayout(item, innerWidth) {
  const { markerWidth, rawMarkerX } = resolveGapMarkerBaseLayout(item, innerWidth);
  const markerX = Math.min(Math.max(0, rawMarkerX), Math.max(0, innerWidth - markerWidth));
  return {
    markerWidth,
    markerX,
  };
}

function resolveGapMarkerLayouts(items, innerWidth, visualLayouts = null) {
  if (Array.isArray(visualLayouts) && visualLayouts.length === items.length) {
    return items.map((item, index) => {
      if (!isFinalPathGapSegment(item?.segment)) {
        return null;
      }
      const visualLayout = visualLayouts[index] || { x: 0, width: 0 };
      return {
        markerWidth: Math.max(0, Number(visualLayout.width) || 0),
        markerX: Math.max(0, Number(visualLayout.x) || 0),
      };
    });
  }
  const layouts = Array.from({ length: items.length }, () => null);
  let index = 0;
  while (index < items.length) {
    if (!isFinalPathGapSegment(items[index]?.segment)) {
      index += 1;
      continue;
    }
    let clusterEnd = index;
    while (clusterEnd + 1 < items.length && isFinalPathGapSegment(items[clusterEnd + 1]?.segment)) {
      clusterEnd += 1;
    }
    const bases = items.slice(index, clusterEnd + 1).map((item) => resolveGapMarkerBaseLayout(item, innerWidth));
    const totalWidth = bases.reduce((sum, base) => sum + base.markerWidth, 0);
    let positions = [];
    if (totalWidth >= innerWidth) {
      let cursor = 0;
      positions = bases.map((base) => {
        const currentX = cursor;
        cursor += base.markerWidth;
        return currentX;
      });
    } else {
      positions[0] = bases[0].rawMarkerX;
      for (let offset = 1; offset < bases.length; offset += 1) {
        positions[offset] = Math.max(
          bases[offset].rawMarkerX,
          positions[offset - 1] + bases[offset - 1].markerWidth,
        );
      }
      const lastIndex = positions.length - 1;
      const overflow = positions[lastIndex] + bases[lastIndex].markerWidth - innerWidth;
      if (overflow > 0) {
        positions = positions.map((value) => value - overflow);
      }
      if (positions[0] < 0) {
        let cursor = 0;
        positions = bases.map((base) => {
          const currentX = cursor;
          cursor += base.markerWidth;
          return currentX;
        });
      }
    }
    for (let offset = 0; offset < bases.length; offset += 1) {
      layouts[index + offset] = {
        markerWidth: bases[offset].markerWidth,
        markerX: positions[offset],
      };
    }
    index = clusterEnd + 1;
  }
  return layouts;
}

function resolveGapLabelLayout(markerX, markerWidth, innerWidth) {
  const markerRight = markerX + markerWidth;
  if (markerX <= 0) {
    return {
      labelX: markerX,
      labelAnchor: "start",
    };
  }
  if (markerRight >= innerWidth) {
    return {
      labelX: markerRight,
      labelAnchor: "end",
    };
  }
  return {
    labelX: markerX + markerWidth / 2,
    labelAnchor: "middle",
  };
}

function resolveGapLabelBounds({
  x,
  labelText = FINAL_PATH_GAP_LABEL_TEXT,
  textAnchor = "middle",
}) {
  const baseX = Number(x) || 0;
  const width = estimateTrackTickLabelWidth(labelText);
  if (textAnchor === "end") {
    return { left: baseX - width, right: baseX };
  }
  if (textAnchor === "start") {
    return { left: baseX, right: baseX + width };
  }
  return {
    left: baseX - width / 2,
    right: baseX + width / 2,
  };
}

function doHorizontalLabelBoundsOverlap(leftBounds, rightBounds) {
  if (!leftBounds || !rightBounds) {
    return false;
  }
  return Number(leftBounds.left) < Number(rightBounds.right)
    && Number(leftBounds.right) > Number(rightBounds.left);
}

function resolveGapLabelLayouts(items, gapMarkerLayouts, innerWidth, occupiedBounds = []) {
  const candidateLayouts = Array.from({ length: items.length }, () => null);
  let index = 0;
  while (index < items.length) {
    if (!isFinalPathGapSegment(items[index]?.segment)) {
      index += 1;
      continue;
    }
    let clusterEnd = index;
    while (clusterEnd + 1 < items.length && isFinalPathGapSegment(items[clusterEnd + 1]?.segment)) {
      clusterEnd += 1;
    }
    const firstLayout = gapMarkerLayouts[index];
    const lastLayout = gapMarkerLayouts[clusterEnd];
    if (firstLayout && lastLayout) {
      if (index === clusterEnd) {
        candidateLayouts[index] = resolveGapLabelLayout(firstLayout.markerX, firstLayout.markerWidth, innerWidth);
      } else {
        candidateLayouts[index] = {
          labelX: firstLayout.markerX,
          labelAnchor: "start",
        };
      }
    }
    index = clusterEnd + 1;
  }
  const visibleBounds = (Array.isArray(occupiedBounds) ? occupiedBounds : []).filter(Boolean);
  return candidateLayouts.map((layout) => {
    if (!layout) {
      return null;
    }
    const bounds = resolveGapLabelBounds({
      x: layout.labelX,
      textAnchor: layout.labelAnchor,
    });
    if (visibleBounds.some((occupied) => doHorizontalLabelBoundsOverlap(bounds, occupied))) {
      return null;
    }
    visibleBounds.push(bounds);
    return layout;
  });
}

export function renderFinalPathGraph({
  escapeAttr,
  escapeHtml,
  finalPathEntry,
  trackControls,
  trackViewportPx,
  primaryDatasetName = "",
  previewSegmentOrder = null,
  scaleDomainSpanBp = null,
  fitToViewport = false,
  showRuler = true,
  compact = false,
  rightLengthLabel = "",
  targetChrName = "",
  allGraphLabel = "",
}) {
  const segments = resolveGraphSegmentsForRender(finalPathEntry, previewSegmentOrder);
  const actualSpanBp = Math.max(1, normalizePositiveInt(resolveFinalPathTotalLengthBp(finalPathEntry)) ?? 1);
  const domainSpanBp = Math.max(actualSpanBp, normalizePositiveInt(scaleDomainSpanBp) ?? actualSpanBp);
  const baseViewportPx = normalizePositiveInt(trackViewportPx) ?? FINAL_PATH_GRAPH_VIEWPORT_PX;
  const resolvedTrackPrefs = resolveTrackPrefs(trackControls);
  const normalizedLengthLabel = normalizeString(rightLengthLabel);
  const lengthLabelWidth = normalizedLengthLabel ? estimateTrackTickLabelWidth(normalizedLengthLabel) + 18 : 0;
  const fallbackInnerWidth = Math.max(1, baseViewportPx - lengthLabelWidth);
  const innerWidth = fitToViewport ? fallbackInnerWidth : resolveTrackInnerWidthFromScale({
    domainSpanBp,
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    baseViewportPx,
    fallbackInnerWidth: baseViewportPx,
  });
  const graphMetrics = compact
    ? compact === "degap"
      ? {
        height: 78,
        rulerY: 14,
        tickY1: 16,
        tickY2: 58,
        barY: 42,
        barHeight: 12,
        textOffsetY: 9,
        barRadius: 2,
      }
      : {
        height: 52,
        rulerY: 10,
        tickY1: 12,
        tickY2: 38,
        barY: 22,
        barHeight: 12,
        textOffsetY: 9,
        barRadius: 2,
      }
    : {
      height: FINAL_PATH_GRAPH_HEIGHT,
      rulerY: FINAL_PATH_GRAPH_RULER_Y,
      tickY1: FINAL_PATH_GRAPH_TICK_Y1,
      tickY2: FINAL_PATH_GRAPH_TICK_Y2,
      barY: FINAL_PATH_GRAPH_BAR_Y,
      barHeight: FINAL_PATH_GRAPH_BAR_HEIGHT,
      textOffsetY: FINAL_PATH_GRAPH_TEXT_OFFSET_Y,
      barRadius: FINAL_PATH_GRAPH_BAR_RADIUS,
    };
  const tickBp = resolveTickBpFromScale({
    domainSpanBp,
    minTickUnitKb: resolvedTrackPrefs.minTickUnitKb,
    maxTickCount: resolvedTrackPrefs.maxTickCount,
    fallbackTickBp: resolvedTrackPrefs.minTickUnitKb * 1000,
  });
  const tickItems = buildTrackTickItems({
    windowStart: 0,
    windowEnd: domainSpanBp,
    tickBp,
    innerWidth,
    domainSpanBp,
  }).map((tick, index, items) => {
    const isFirst = index === 0;
    const isLast = index === items.length - 1;
    const labelText = isLast ? `${tick.bp.toLocaleString("en-US")} bp` : formatRulerTickLabel(tick.bp);
    const labelX = isFirst
      ? Math.min(innerWidth, tick.x + TRACK_EDGE_LABEL_PADDING)
      : isLast
        ? Math.max(0, tick.x - TRACK_EDGE_LABEL_PADDING)
        : tick.x;
    return {
      ...tick,
      labelText,
      labelX,
      labelAnchor: isFirst ? "start" : isLast ? "end" : "middle",
      showLabel: true,
    };
  });
  const endTick = tickItems[tickItems.length - 1];
  const previousTick = tickItems[tickItems.length - 2];
  if (isTrackTickLabelOverlap(previousTick, endTick)) {
    previousTick.showLabel = false;
  }
  const tickLines = tickItems
    .map((tick) => `<line class="track-tick-guide is-major" x1="${tick.x.toFixed(2)}" y1="${graphMetrics.tickY1.toFixed(2)}" x2="${tick.x.toFixed(2)}" y2="${graphMetrics.tickY2.toFixed(2)}" />`)
    .join("");
  const tickLabels = tickItems
    .filter((tick) => tick.showLabel)
    .map((tick) => `<text class="track-tick-label" x="${tick.labelX.toFixed(2)}" y="${(graphMetrics.rulerY - 4).toFixed(2)}" text-anchor="${tick.labelAnchor}">${escapeHtml(tick.labelText)}</text>`)
    .join("");

  const layoutItems = resolveSegmentLayoutItems(segments, domainSpanBp, innerWidth);
  const visualLayouts = fitToViewport ? null : resolveFinalPathVisualLayouts(layoutItems, innerWidth);
  const gapMarkerLayouts = resolveGapMarkerLayouts(layoutItems, innerWidth, visualLayouts);
  const ctgLabelPlacements = resolveFinalPathCtgLabelPlacements(
    layoutItems,
    gapMarkerLayouts,
    innerWidth,
    visualLayouts,
    graphMetrics,
  );
  const occupiedCtgLabelBounds = layoutItems.reduce((bounds, item, index, items) => {
    const { segment } = item;
    if (!isFinalPathCtgSegment(segment)) {
      return bounds;
    }
    const graphLabelText = resolveFinalPathGraphLabelText(segment);
    const labelPlacement = ctgLabelPlacements[index];
    if (!graphLabelText || !labelPlacement || labelPlacement.hidden) {
      return bounds;
    }
    bounds.push(resolveTrackCtgLabelBounds({
      x: labelPlacement.x,
      labelText: graphLabelText,
      tiltAngleDeg: labelPlacement.tiltAngleDeg,
      textAnchor: labelPlacement.textAnchor,
    }));
    return bounds;
  }, []);
  const gapLabelLayouts = resolveGapLabelLayouts(
    layoutItems,
    gapMarkerLayouts,
    innerWidth,
    occupiedCtgLabelBounds,
  );
  const maxLabelRight = layoutItems.reduce((layoutMax, item, index, items) => {
    const { segment } = item;
    if (!isFinalPathCtgSegment(segment)) {
      return layoutMax;
    }
    const graphLabelText = resolveFinalPathGraphLabelText(segment);
    if (!graphLabelText) {
      return layoutMax;
    }
    const labelPlacement = ctgLabelPlacements[index];
    if (!labelPlacement || labelPlacement.hidden) {
      return layoutMax;
    }
    const labelRight = resolveTrackCtgLabelRightBoundary({
      x: labelPlacement.x,
      labelText: graphLabelText,
      tiltAngleDeg: labelPlacement.tiltAngleDeg,
      textAnchor: labelPlacement.textAnchor,
    });
    return Math.max(layoutMax, labelRight);
  }, innerWidth);
  const lengthLabelX = normalizedLengthLabel
    ? Math.min(innerWidth + 8, ((actualSpanBp / domainSpanBp) * innerWidth) + 8)
    : 0;
  const lengthLabelRight = normalizedLengthLabel ? lengthLabelX + estimateTrackTickLabelWidth(normalizedLengthLabel) : 0;
  const renderInnerWidth = Math.max(
    fitToViewport ? baseViewportPx : innerWidth,
    Math.ceil(maxLabelRight),
    Math.ceil(lengthLabelRight),
  );
  const normalizedTargetChrName = normalizeString(targetChrName);
  const targetChrAttr = normalizedTargetChrName
    ? `data-final-path-target-chr-name="${escapeAttr(normalizedTargetChrName)}"`
    : "";
  const normalizedAllGraphLabel = normalizeString(allGraphLabel);

  const segmentNodes = layoutItems
    .map((item, index, items) => {
      const { segment } = item;
      const segmentId = normalizeString(segment.segmentId);
      if (isFinalPathGapSegment(segment)) {
        const { markerWidth, markerX } = gapMarkerLayouts[index] || resolveGapMarkerLayout(item, innerWidth);
        const labelLayout = gapLabelLayouts[index];
        const slotLeft = markerX;
        const slotRight = markerX + markerWidth;
        const slotMid = slotLeft + ((slotRight - slotLeft) / 2);
        const tooltipText = `GAP | len=${String(item.segmentLength || resolveFinalPathSegmentLengthBp(segment) || 0)} bp`;
        return `
          <g
            data-final-path-segment-id="${escapeAttr(segmentId)}"
            data-final-path-segment-type="gap"
           ${targetChrAttr}
            data-final-path-slot-left="${escapeAttr(slotLeft.toFixed(2))}"
            data-final-path-slot-right="${escapeAttr(slotRight.toFixed(2))}"
            data-final-path-slot-mid="${escapeAttr(slotMid.toFixed(2))}"
            class="final-path-gap-segment"
          >
            <rect
              class="final-path-gap-marker"
              x="${markerX.toFixed(2)}"
              y="${(graphMetrics.barY - 1).toFixed(2)}"
              width="${markerWidth.toFixed(2)}"
              height="${(graphMetrics.barHeight + 2).toFixed(2)}"
              rx="1"
              ry="1"
            ><title>${escapeHtml(tooltipText)}</title></rect>
            ${labelLayout
              ? `<text class="final-path-gap-label" x="${labelLayout.labelX.toFixed(2)}" y="${(graphMetrics.barY - 4).toFixed(2)}" text-anchor="${labelLayout.labelAnchor}">GAP</text>`
              : ""}
          </g>
        `;
      }
      if (!isFinalPathCtgSegment(segment)) {
        return "";
      }
      const displayCtgName = resolveFinalPathDisplayCtgName(segment);
      const graphLabelText = resolveFinalPathGraphLabelText(segment);
      if (!displayCtgName || item.segmentLength <= 0) {
        return "";
      }
      const orient = resolveFinalPathSegmentOrient(segment);
      const tooltipText = `${displayCtgName} | len=${String(segment?.overallLen || 0)} | start=${String(segment?.start || "")} | end=${String(segment?.end || "")} | orient=${orient}`;
      const isCompanion = isCompanionFinalPathSegment(segment, primaryDatasetName);
      const isRefSegment = isFinalPathRefSegment(segment);
      const toneClass = isRefSegment ? " is-ref" : (isCompanion ? " is-companion" : "");
      const groupClass = `track-ctg-group is-active${toneClass}`;
      const ctgClass = `track-ctg is-active${toneClass}`;
      const { visualStartX, barWidth } = resolveFinalPathCtgVisualLayout(
        items,
        index,
        item,
        innerWidth,
        gapMarkerLayouts,
        visualLayouts,
      );
      const slotLeft = visualStartX;
      const slotRight = visualStartX + barWidth;
      const slotMid = slotLeft + ((slotRight - slotLeft) / 2);
      const labelPlacement = ctgLabelPlacements[index];
      return `
        <g
          class="${groupClass}"
          data-final-path-segment-id="${escapeAttr(segmentId)}"
          data-final-path-segment-type="ctg"
         ${targetChrAttr}
          data-final-path-source-kind="${escapeAttr(String(segment?.sourceKind || "assembly_ctg"))}"
          data-final-path-contig-id="${escapeAttr(String(segment?.assemblyCtgId || ""))}"
          data-final-path-slot-left="${escapeAttr(slotLeft.toFixed(2))}"
          data-final-path-slot-right="${escapeAttr(slotRight.toFixed(2))}"
          data-final-path-slot-mid="${escapeAttr(slotMid.toFixed(2))}"
        >
          <rect
            class="${ctgClass}"
            x="${visualStartX.toFixed(2)}"
            y="${graphMetrics.barY}"
            width="${barWidth.toFixed(2)}"
            height="${graphMetrics.barHeight}"
            rx="${graphMetrics.barRadius}"
            ry="${graphMetrics.barRadius}"
          >
            <title>${escapeHtml(tooltipText)}</title>
          </rect>
          ${labelPlacement && !labelPlacement.hidden
            ? `<text class="track-ctg-label${toneClass}${labelPlacement.classSuffix}" x="${labelPlacement.x.toFixed(2)}" y="${labelPlacement.y.toFixed(2)}"${labelPlacement.transformAttr} text-anchor="${labelPlacement.textAnchor}">${escapeHtml(graphLabelText)}</text>`
            : ""}
        </g>
      `;
    })
    .join("");
  const lengthLabelNode = normalizedLengthLabel
    ? `<text class="final-path-length-label" x="${lengthLabelX.toFixed(2)}" y="${(graphMetrics.barY + graphMetrics.textOffsetY).toFixed(2)}">${escapeHtml(normalizedLengthLabel)}</text>`
    : "";
  const rulerNodes = showRuler
    ? `
          <line class="track-ruler-line" x1="0" y1="${graphMetrics.rulerY}" x2="${innerWidth}" y2="${graphMetrics.rulerY}" />
          ${tickLines}
          ${tickLabels}
      `
    : "";

  return `
    <div class="assembly-final-path-layout assembly-track-layout">
      <div
        class="assembly-final-path-label-spacer assembly-track-label-column"
        style="width:${FINAL_PATH_LABEL_COLUMN_WIDTH_PX}px"
        ${normalizedAllGraphLabel ? `data-final-path-all-graph-label="${escapeAttr(normalizedAllGraphLabel)}"` : "aria-hidden=\"true\""}
      >${normalizedAllGraphLabel ? `<strong>${escapeHtml(normalizedAllGraphLabel)}</strong>` : ""}</div>
      <div class="assembly-track-scroll assembly-final-path-svg-wrap" data-final-path-graph-viewport>
        <svg
          class="assembly-track-svg assembly-final-path-svg"
          data-final-path-graph-svg
         ${targetChrAttr}
          width="${renderInnerWidth}"
          height="${graphMetrics.height}"
          viewBox="0 0 ${renderInnerWidth} ${graphMetrics.height}"
          preserveAspectRatio="xMinYMin meet"
        >
          ${rulerNodes}
          ${segmentNodes}
          ${lengthLabelNode}
        </svg>
      </div>
    </div>
  `;
}

function renderFinalPathTable({
  escapeAttr,
  escapeHtml,
  finalPathEntry,
  labels,
  targetChrName = "",
  indexHeaderLabel = "",
}) {
  const segments = normalizeFinalPathSegments(finalPathEntry);
  const normalizedTargetChrName = normalizeString(targetChrName);
  const targetChrAttr = normalizedTargetChrName
    ? ` data-final-path-target-chr-name="${escapeAttr(normalizedTargetChrName)}"`
    : "";
  const firstHeaderLabel = normalizeString(indexHeaderLabel) || labels.finalPathIndexCol || "#";
  const rowMetrics = buildFinalPathTableRowMetrics(segments);
  const rows = segments.length
    ? segments.map((segment, index) => {
      const segmentId = normalizeString(segment.segmentId) || `seg-${index + 1}`;
      const isGap = isFinalPathGapSegment(segment);
      const isRefSegment = isFinalPathRefSegment(segment);
      const metrics = rowMetrics[index] || {};
      const displayName = isGap ? "Gap" : resolveFinalPathVisibleCtgName(segment);
      const fullDisplayName = isGap ? displayName : resolveFinalPathDisplayCtgName(segment);
      const originIdText = isGap ? "" : normalizeString(segment?.originId);
      const overallLenText = isGap ? "" : normalizeString(segment?.overallLen);
      const orientText = isGap ? "" : resolveFinalPathSegmentOrient(segment);
      const startValue = isGap ? "1" : normalizeString(segment?.start);
      const endValue = isGap ? "100" : normalizeString(segment?.end);
      const chrStartValue = normalizeString(metrics?.chrStart);
      const chrEndValue = normalizeString(metrics?.chrEnd);
      const orientControl = isGap
        ? `
                <select
                  data-final-path-cell="orient"
                  data-final-path-segment-id="${escapeAttr(segmentId)}"
                 ${targetChrAttr}
                  disabled
                >
                  <option value="" selected></option>
                </select>
              `
        : `
                <select
                  data-final-path-cell="orient"
                  data-final-path-segment-id="${escapeAttr(segmentId)}"
                 ${targetChrAttr}
                >
                  <option value="+" ${orientText === "+" ? "selected" : ""}>+</option>
                  <option value="-" ${orientText === "-" ? "selected" : ""}>-</option>
                </select>
              `;
      const rowTypeClass = isGap ? " is-gap" : "";
      return `
        <div data-final-path-row-id="${escapeAttr(segmentId)}"${targetChrAttr} class="final-path-sort-row${rowTypeClass}">
          <div class="final-path-row-index-cell">
            <span class="final-path-card-index">${index + 1}</span>
          </div>
          <div class="final-path-sort-card" data-final-path-card-body="${escapeAttr(segmentId)}"${targetChrAttr}>
            <div class="final-path-sort-card-grid">
              <div class="final-path-card-cell final-path-card-drag-cell">
                <button type="button" class="button ghost tiny final-path-row-drag-handle" data-final-path-row-drag-id="${escapeAttr(segmentId)}"${targetChrAttr} title="drag">↕</button>
              </div>
              <div class="final-path-card-cell">
                <input
                  type="text"
                  data-final-path-cell="ctg"
                  data-final-path-segment-id="${escapeAttr(segmentId)}"
                 ${targetChrAttr}
                  value="${escapeAttr(displayName)}"
                  title="${escapeAttr(fullDisplayName)}"
                  autocomplete="off"
                  ${isRefSegment ? "disabled" : ""}
                />
              </div>
              <div class="final-path-card-cell">
                <input
                  type="text"
                  data-final-path-cell="origin-id"
                  data-final-path-segment-id="${escapeAttr(segmentId)}"
                 ${targetChrAttr}
                  value="${escapeAttr(originIdText)}"
                  disabled
                />
              </div>
              <div class="final-path-card-cell">
                <input
                  type="text"
                  data-final-path-cell="overall-len"
                  data-final-path-segment-id="${escapeAttr(segmentId)}"
                 ${targetChrAttr}
                  value="${escapeAttr(overallLenText)}"
                  disabled
                />
              </div>
              <div class="final-path-card-cell">
                ${orientControl}
              </div>
              <div class="final-path-card-cell">
                <input
                  type="number"
                  min="1"
                  data-final-path-cell="start"
                  data-final-path-segment-id="${escapeAttr(segmentId)}"
                 ${targetChrAttr}
                  value="${escapeAttr(startValue)}"
                  ${isGap ? "disabled" : ""}
                />
              </div>
              <div class="final-path-card-cell">
                <input
                  type="number"
                  min="1"
                  data-final-path-cell="end"
                  data-final-path-segment-id="${escapeAttr(segmentId)}"
                 ${targetChrAttr}
                  value="${escapeAttr(endValue)}"
                  ${isGap ? "disabled" : ""}
                />
              </div>
              <div class="final-path-card-cell">
                <input
                  type="number"
                  min="1"
                  data-final-path-derived-cell="chr-start"
                  data-final-path-segment-id="${escapeAttr(segmentId)}"
                 ${targetChrAttr}
                  value="${escapeAttr(chrStartValue)}"
                  disabled
                />
              </div>
              <div class="final-path-card-cell">
                <input
                  type="number"
                  min="1"
                  data-final-path-derived-cell="chr-end"
                  data-final-path-segment-id="${escapeAttr(segmentId)}"
                 ${targetChrAttr}
                  value="${escapeAttr(chrEndValue)}"
                  disabled
                />
              </div>
              <div class="final-path-card-cell final-path-card-delete-cell">
                <button type="button" class="button ghost tiny danger" data-final-path-remove-row="${escapeAttr(segmentId)}"${targetChrAttr}>&#128465;</button>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join("")
    : `
        <div data-final-path-empty-row="true" class="final-path-sort-row is-empty">
          <div class="final-path-row-index-cell">
            <span class="final-path-card-index">1</span>
          </div>
          <div class="final-path-sort-card final-path-sort-card-empty">
            <div class="final-path-sort-card-grid">
              <div class="final-path-card-cell final-path-card-drag-cell"></div>
              <div class="final-path-card-cell">
                <input type="text" data-final-path-empty-cell="ctg" value="" autocomplete="off"${targetChrAttr} />
              </div>
              <div class="final-path-card-cell">
                <input type="text" data-final-path-empty-cell="origin-id"${targetChrAttr} value="" disabled />
              </div>
              <div class="final-path-card-cell">
                <input type="text" data-final-path-empty-cell="overall-len"${targetChrAttr} value="" disabled />
              </div>
              <div class="final-path-card-cell">
                <input type="text" data-final-path-empty-cell="orient"${targetChrAttr} value="" disabled />
              </div>
              <div class="final-path-card-cell">
                <input type="number" data-final-path-empty-cell="start"${targetChrAttr} value="" disabled />
              </div>
              <div class="final-path-card-cell">
                <input type="number" data-final-path-empty-cell="end"${targetChrAttr} value="" disabled />
              </div>
              <div class="final-path-card-cell">
                <input type="number" data-final-path-empty-cell="chr-start"${targetChrAttr} value="" disabled />
              </div>
              <div class="final-path-card-cell">
                <input type="number" data-final-path-empty-cell="chr-end"${targetChrAttr} value="" disabled />
              </div>
              <div class="final-path-card-cell final-path-card-delete-cell"></div>
            </div>
          </div>
        </div>
      `;
  return `
    <div class="final-path-card-table-body">
      <div class="final-path-card-list-shell">
        <div class="final-path-card-list-head" role="presentation">
          <div>${escapeHtml(firstHeaderLabel)}</div>
          <div class="final-path-card-list-head-card">
            <div aria-hidden="true"></div>
            <div>${escapeHtml(labels.finalPathCtgCol || "Ctg")}</div>
            <div>${escapeHtml(labels.finalPathOriginIdCol || "Origin ID")}</div>
            <div>${escapeHtml(labels.finalPathOverallLenCol || "overall_len")}</div>
            <div>${escapeHtml(labels.finalPathOrientCol || "orient")}</div>
            <div>${escapeHtml(labels.finalPathCtgStartCol || "Ctg_start")}</div>
            <div>${escapeHtml(labels.finalPathCtgEndCol || "Ctg_end")}</div>
            <div>${escapeHtml(labels.finalPathChrStartCol || "Chr_start")}</div>
            <div>${escapeHtml(labels.finalPathChrEndCol || "Chr_end")}</div>
            <div aria-hidden="true"></div>
          </div>
        </div>
        <div class="final-path-card-list" data-final-path-card-list${targetChrAttr}>
          ${rows}
        </div>
      </div>
      <div class="final-path-table-actions">
        <button type="button" class="button ghost final-path-add-button" data-final-path-add-row${targetChrAttr}>＋</button>
      </div>
    </div>
  `;
}

function renderPhasedFinalPathSelector({ escapeAttr, escapeHtml, labels, options = [] }) {
  const normalizedOptions = (Array.isArray(options) ? options : [])
    .map((option) => {
      const key = normalizeString(option?.key);
      const chrName = normalizeString(option?.chrName);
      if (!key || !chrName) {
        return null;
      }
      return {
        key,
        label: normalizeString(option?.label) || key,
        chrName,
        active: Boolean(option?.active),
      };
    })
    .filter(Boolean);
  if (!normalizedOptions.length) {
    return "";
  }
  const label = labels.finalPathPhasedSelector || "Haplotype path";
  const activeOption = normalizedOptions.find((option) => option.active) || normalizedOptions[0];
  return `
    <div
      class="final-path-phased-selector"
      data-phased-final-path-menu="true"
      data-phased-final-path-current-key="${escapeAttr(activeOption.key)}"
    >
      <button
        type="button"
        class="button ghost tiny final-path-phased-selector-toggle"
        data-phased-final-path-toggle="true"
        aria-label="${escapeAttr(label)}"
        aria-expanded="false"
      >${escapeHtml(activeOption.label || activeOption.key)} <span aria-hidden="true">▾</span></button>
      <div class="final-path-phased-selector-menu is-hidden" data-phased-final-path-options="true">
        ${normalizedOptions.map((option) => `
        <button
          type="button"
          class="final-path-phased-selector-option${option.active ? " is-active" : ""}"
          data-phased-final-path-key="${escapeAttr(option.key)}"
          data-phased-final-path-chr-name="${escapeAttr(option.chrName)}"
          aria-selected="${option.active ? "true" : "false"}"
          title="${escapeAttr(option.chrName)}"
        >${escapeHtml(option.label || option.key)}</button>
      `).join("")}
      </div>
    </div>
  `;
}

export function renderFinalPathCard(
  {
    projectName,
    chrName,
    finalPathEntry,
    viewMode = "graph",
    trackView = null,
    trackViewportPx = null,
    primaryDatasetName = "",
    graphPreviewSegmentOrder = null,
    degapBody = "",
    degapTrackView = null,
    canExportFasta = true,
    canExportDegapJobs = false,
    finalPathLogModel = null,
    phasedFinalPathOptions = [],
    finalPathEntries = [],
  },
  deps = {},
) {
  const escapeHtml = typeof deps.escapeHtml === "function"
    ? deps.escapeHtml
    : (value) => String(value);
  const escapeAttr = typeof deps.escapeAttr === "function"
    ? deps.escapeAttr
    : (value) => String(value);
  const i18n = deps.i18n || {};
  const labels = i18n.page || {};
  const trackLabels = i18n.trackControls || {};
  const normalizedProjectName = normalizeString(projectName) || "project";
  const normalizedChrName = normalizeString(chrName || finalPathEntry?.chrName);
  if (!normalizedChrName) {
    return "";
  }
  const displayEntries = (Array.isArray(finalPathEntries) ? finalPathEntries : [])
    .map((entry) => {
      const entryChrName = normalizeString(entry?.chrName || entry?.finalPathEntry?.chrName);
      const entryFinalPath = entry?.finalPathEntry || null;
      if (!entryChrName || !entryFinalPath) {
        return null;
      }
      return {
        key: normalizeString(entry?.key),
        label: normalizeString(entry?.label) || entryChrName,
        chrName: entryChrName,
        finalPathEntry: entryFinalPath,
        finalPathLogModel: entry?.finalPathLogModel || null,
        graphPreviewSegmentOrder: Array.isArray(entry?.graphPreviewSegmentOrder)
          ? entry.graphPreviewSegmentOrder
          : null,
      };
    })
    .filter(Boolean);
  const canLog = displayEntries.length > 1
    ? displayEntries.some((entry) => Array.isArray(entry.finalPathEntry?.segments) && entry.finalPathEntry.segments.length > 0)
      && !displayEntries.some((entry) =>
        (Array.isArray(entry.finalPathEntry?.segments) ? entry.finalPathEntry.segments : []).some((segment) =>
          isFinalPathRefSegment(segment),
        ),
      )
    : canUseFinalPathLog(finalPathEntry);
  const logModel = finalPathLogModel || buildFinalPathLogModel({
    chrName: normalizedChrName,
    finalPathEntry,
    primaryDatasetName,
  });
  const normalizedViewMode = normalizeViewMode(viewMode, canLog);
  const title = `${normalizedProjectName}_${normalizedChrName} path`;
  const graphLabel = String(labels.finalPathGraph || "Graph");
  const tableLabel = String(labels.finalPathTable || "Table");
  const degapLabel = String(labels.finalPathDegap || "DEGAP");
  const logLabel = String(labels.finalPathLog || "Log");
  const phasedSelector = renderPhasedFinalPathSelector({
    escapeAttr,
    escapeHtml,
    labels,
    options: phasedFinalPathOptions,
  });
  const exportMenu = renderFinalPathExportMenu({
    escapeHtml,
    labels,
    canExportFasta,
    canExportLog: canLog,
    canExportDegapJobs,
  });
  const trackControlLabels = {
    minTickUnitLabel: String(trackLabels.minTickUnitKb || "Min Tick Unit (kb)"),
    maxTickCountLabel: String(trackLabels.maxTickCount || "Max Tick Count"),
    openMinTickUnitLabel: String(trackLabels.openOptionCandidates || "Open {label} candidates").replace(
      "{label}",
      String(trackLabels.minTickUnitKb || "Min Tick Unit (kb)"),
    ),
    openMaxTickCountLabel: String(trackLabels.openOptionCandidates || "Open {label} candidates").replace(
      "{label}",
      String(trackLabels.maxTickCount || "Max Tick Count"),
    ),
  };
  const trackControls = resolveTrackPrefs({
    minTickUnitKb: DEFAULT_MIN_TICK_UNIT_KB,
    maxTickCount: DEFAULT_MAX_TICK_COUNT,
    ...(trackView || {}),
  });
  const degapTrackControls = resolveTrackPrefs({
    minTickUnitKb: DEFAULT_MIN_TICK_UNIT_KB,
    maxTickCount: DEFAULT_MAX_TICK_COUNT,
    ...(degapTrackView || trackView || {}),
  });
  const headControls = normalizedViewMode === "graph"
    ? renderFinalPathHeadControls({
      escapeAttr,
      escapeHtml,
      ariaLabel: `${title} controls`,
      labels: trackControlLabels,
      trackControls,
      exportMenu,
    })
    : normalizedViewMode === "degap"
      ? renderFinalPathHeadControls({
        escapeAttr,
        escapeHtml,
        ariaLabel: labels.finalPathDegapControls || `${title} DEGAP controls`,
        labels: trackControlLabels,
        trackControls: degapTrackControls,
        exportMenu,
        extraComboFieldAttr: "data-degap-scale-combo-field",
        inputFieldAttr: "data-degap-scale-field",
        idPrefix: "degap-track",
      })
    : `<div class="final-path-card-head-controls is-table-mode">${exportMenu}</div>`;

  const isAllMode = displayEntries.length > 1;
  const singleEntry = displayEntries[0] || {
    key: "",
    label: normalizedChrName,
    chrName: normalizedChrName,
    finalPathEntry,
    finalPathLogModel: logModel,
  };

  const renderSingleBody = (entry, { allMode = false } = {}) => {
    if (normalizedViewMode === "degap") {
      return normalizeString(degapBody) || renderFinalPathGraph({
        escapeAttr,
        escapeHtml,
        finalPathEntry: entry.finalPathEntry,
        trackControls,
        trackViewportPx,
        primaryDatasetName,
        previewSegmentOrder: allMode ? entry.graphPreviewSegmentOrder : graphPreviewSegmentOrder,
        targetChrName: allMode ? entry.chrName : "",
        allGraphLabel: allMode ? entry.label : "",
        compact: "degap",
      });
    }
    const entryLogModel = entry.finalPathLogModel || buildFinalPathLogModel({
      chrName: entry.chrName,
      finalPathEntry: entry.finalPathEntry,
      primaryDatasetName,
    });
    const bodyMarkup = normalizedViewMode === "log"
      ? renderFinalPathLog({
        escapeHtml,
        escapeAttr,
        labels,
        logModel: entryLogModel,
        currentChrName: entry.chrName,
      })
      : normalizedViewMode === "table"
        ? renderFinalPathTable({
          escapeAttr,
          escapeHtml,
          finalPathEntry: entry.finalPathEntry,
          labels,
          targetChrName: allMode ? entry.chrName : "",
          indexHeaderLabel: allMode ? entry.label : "",
        })
        : renderFinalPathGraph({
          escapeAttr,
          escapeHtml,
          finalPathEntry: entry.finalPathEntry,
          trackControls,
          trackViewportPx,
          primaryDatasetName,
          previewSegmentOrder: allMode ? entry.graphPreviewSegmentOrder : graphPreviewSegmentOrder,
          targetChrName: allMode ? entry.chrName : "",
          allGraphLabel: allMode ? entry.label : "",
        });
    if (!allMode) {
      return bodyMarkup;
    }
    const logTitle = normalizedViewMode === "log"
      ? `<div class="final-path-all-card-head"><strong class="final-path-all-card-title">${escapeHtml(entry.label)}</strong></div>`
      : "";
    return `
      <section class="final-path-all-card is-${escapeAttr(normalizedViewMode)}" data-final-path-all-card="${escapeAttr(entry.chrName)}" data-final-path-target-chr-name="${escapeAttr(entry.chrName)}">
        ${logTitle}
        ${bodyMarkup}
      </section>
    `;
  };

  const body = normalizedViewMode === "degap"
    ? renderSingleBody(singleEntry)
    : isAllMode
    ? `<div class="final-path-all-card-stack" data-final-path-all-stack="true">${displayEntries.map((entry) => renderSingleBody(entry, { allMode: true })).join("")}</div>`
    : renderSingleBody(singleEntry);

  return `
    <article class="card final-path-card" data-final-path-view-mode="${escapeAttr(normalizedViewMode)}" data-final-path-target-chr-name="${escapeAttr(singleEntry.chrName)}">
      <div class="assembly-members-panel-head final-path-card-head">
        <div class="final-path-card-title-row">
          <strong>${escapeHtml(title)}</strong>
          ${phasedSelector}
          <div class="final-path-card-toggle" role="tablist" aria-label="${escapeAttr(title)}">
            <button
              type="button"
              class="button ghost tiny${normalizedViewMode === "graph" ? " is-active" : ""} final-path-card-toggle-button"
              data-final-path-view-mode="graph"
            >${escapeHtml(graphLabel)}</button>
            <button
              type="button"
              class="button ghost tiny${normalizedViewMode === "table" ? " is-active" : ""} final-path-card-toggle-button"
              data-final-path-view-mode="table"
            >${escapeHtml(tableLabel)}</button>
            <button
              type="button"
              class="button ghost tiny${normalizedViewMode === "degap" ? " is-active" : ""} final-path-card-toggle-button"
              data-final-path-view-mode="degap"
            >${escapeHtml(degapLabel)}</button>
            ${canLog ? `
              <button
                type="button"
                class="button ghost tiny${normalizedViewMode === "log" ? " is-active" : ""} final-path-card-toggle-button"
                data-final-path-view-mode="log"
              >${escapeHtml(logLabel)}</button>
            ` : ""}
          </div>
        </div>
        ${headControls}
      </div>
      <div class="final-path-card-body">
        ${body}
      </div>
    </article>
  `;
}
