import { buildDualTrackModel } from "./track-layout.js";
import {
  ALIGNMENT_LENGTH_OPTIONS,
  MAPQ_OPTIONS,
  MAX_TICK_COUNT_OPTIONS,
  MIN_TICK_UNIT_KB_OPTIONS,
  SUPPORT_DS_CTG_LEN_BP_OPTIONS,
  normalizeNonNegativeInt,
  normalizePositiveInt,
  resolveTrackInnerWidthFromScale,
  resolveTickBpFromScale,
  resolveTrackPrefs,
} from "./track-prefs.js";
import {
  buildSubviewTrackDragOffsetKey,
  buildTrackDragOffsetKey,
  filterPrimaryTrackSelectionCtgIds,
  normalizeDeletedCtgRecordIds,
  normalizeSupportDatasetId,
  normalizeSupportMirroredCtgs,
  normalizeTrackDragOffsets,
  normalizeTrackRole,
  normalizeTrackSelectionCtgIds,
  normalizeSubviewTrackDragOffsets,
} from "./selection-state.js";
import {
  buildSupportSubviewCtgPool,
  buildPhasedSubviewCtgPool,
  buildPhasedSubviewCtgHits,
  getSubviewState as getSubviewStateImpl,
  getSubviewTrackSelections,
  resolveSubviewCtgOrientValue,
  normalizeSubviewTrackSelectionItem,
  normalizeSubviewTrackSource,
} from "./subview-state.js";
import {
  filterSupportCtgsBySupportDsCtgLenRules,
  getSupportDsCtgLenRulesForChr,
  hasAdvancedSupportDsCtgLenRules,
} from "./support-ds-ctg-len-rules.js";
import { renderAssemblyFinalPathCard as renderAssemblyFinalPathCardImpl } from "./render-final-path.js";
import {
  buildTrackCtgHoverTitle,
  resolveBoundedTrackCtgLabelPlacement,
  resolveTrackCtgDisplayName,
  resolveTrackCtgLabelLeftBoundary,
  resolveTrackCtgLabelText,
  resolveTrackCtgLabelRightBoundary,
  resolveTrackCtgOrient,
  resolveTrackCtgVisibleName,
} from "./track-label-geometry.js";
import {
  buildEmptyTrackModelLike,
  buildCollinearityBandPoints,
  buildTrackBpX,
  buildTrackHitRect,
  buildTrackHitRectWithinCtgDisplay,
  buildTrackRect,
  buildTrackRectsWithMinGap,
  buildTrackReferenceWidth,
  buildTrackTickItems,
  isTrackTickLabelOverlap,
  resolveHitMapq,
  resolveMaxTrackEndBp,
  roundTrackMetric,
  sortTrackEntriesForRender,
} from "./track-render-geometry.js";
import {
  createAssemblySubviewRenderer,
  getCachedFilteredRefSubviewCtgs,
  getSubviewSlotToken,
} from "./render-subview.js";
import { buildGrtResultPlan, resolveGrtResultContext } from "./grt-result-state.js";
import { buildGrtResultScene } from "./grt-result-render.js";

export {
  SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS,
  __testBuildFilteredRefSubviewCtgs,
  __testPairRefSubviewSegmentsWithCache,
} from "./render-subview.js";
export { roundTrackMetric } from "./track-render-geometry.js";

function escapeSourceTagHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const DEFAULT_TRACK_VIEWPORT_PX = 1200;

function resolveTrackCtgOrientValue(ctg) {
  return resolveSubviewCtgOrientValue(ctg);
}

function resolveDerivedSourceLabel(ctg) {
  const source = String(ctg?.derivedSource || "").trim();
  return source || (ctg?.derivedTargetDatasetId ? "derived" : "");
}

function resolveDerivedSourceClass(sourceLabel) {
  const normalized = String(sourceLabel || "").trim().toLowerCase();
  if (normalized === "gapfiller") return " is-source-gapfiller";
  if (normalized === "telseeker") return " is-source-telseeker";
  return " is-source-derived";
}

function resolveDerivedSourceColor(sourceLabel) {
  const normalized = String(sourceLabel || "").trim().toLowerCase();
  if (normalized === "gapfiller" || normalized === "telseeker" || normalized === "derived") {
    return "";
  }
  if (!normalized) {
    return "";
  }
  let hash = 0;
  for (let index = 0; index < normalized.length; index += 1) {
    hash = (hash * 31 + normalized.charCodeAt(index)) >>> 0;
  }
  const hue = hash % 360;
  return `hsl(${hue}, 72%, 32%)`;
}

function renderDerivedSourceSvgTag(ctg) {
  const sourceLabel = resolveDerivedSourceLabel(ctg);
  if (!sourceLabel) {
    return "";
  }
  const color = resolveDerivedSourceColor(sourceLabel);
  const styleAttr = color ? ` style="fill:${escapeSourceTagHtml(color)}"` : "";
  return `<tspan class="track-ctg-source-tag${resolveDerivedSourceClass(sourceLabel)}"${styleAttr}> [${escapeSourceTagHtml(sourceLabel)}]</tspan>`;
}

function renderDerivedSourceHtmlTag(ctg) {
  const sourceLabel = resolveDerivedSourceLabel(ctg);
  if (!sourceLabel) {
    return "";
  }
  const color = resolveDerivedSourceColor(sourceLabel);
  const styleAttr = color ? ` style="color:${escapeSourceTagHtml(color)}"` : "";
  return `<span class="ctg-chip-source-tag${resolveDerivedSourceClass(sourceLabel)}"${styleAttr}>[${escapeSourceTagHtml(sourceLabel)}]</span>`;
}



function createRenderTracksRenderer(deps = {}) {
  const {
    escapeAttr,
    escapeHtml,
    formatBp,
    getAssemblyI18n,
    getCurrentProject,
    getDatasetNameById,
    getMeasuredTrackViewportPx: getMeasuredTrackViewportPxImpl,
    getSupportDatasetOptions,
  } = deps;
  if (
    typeof escapeAttr !== "function"
    || typeof escapeHtml !== "function"
    || typeof formatBp !== "function"
    || typeof getAssemblyI18n !== "function"
    || typeof getCurrentProject !== "function"
    || typeof getDatasetNameById !== "function"
    || typeof getSupportDatasetOptions !== "function"
  ) {
    throw new Error("render-tracks.js missing required render dependencies");
  }

  function getMeasuredTrackViewportPx(role = "primary") {
    const value = Number(getMeasuredTrackViewportPxImpl?.(role));
    return Number.isFinite(value) && value > 0 ? value : DEFAULT_TRACK_VIEWPORT_PX;
  }

  const {
    renderSubviewSelectionPanel,
    renderTrackBandCanvasLayer,
    resolveTrackHitDisplayReversed,
    resolveTrackRenderableHits,
  } = createAssemblySubviewRenderer({
    escapeAttr,
    escapeHtml,
    formatBpInterval,
    getMeasuredTrackViewportPx,
    renderTrackNumberInput,
    resolveSubviewTrackDragOffsetPx,
    resolveSubviewTrackSelectionLabel,
    resolveTrackToneClass,
  });

  function getSelectedChromosome(assembly) {
    const selectedChrName = String(assembly?.selectedChrName || "").trim();
    if (!selectedChrName || !Array.isArray(assembly?.chromosomes)) {
      return null;
    }
    return (
      assembly.chromosomes.find((chromosome) => String(chromosome?.chrName || "").trim() === selectedChrName) ||
      null
    );
  }

  function resolveTelomereRuleClass(ruleId) {
    const text = String(ruleId || "");
    let hash = 0;
    for (let index = 0; index < text.length; index += 1) {
      hash = ((hash * 31) + text.charCodeAt(index)) % 9973;
    }
    return `is-rule-${(Math.abs(hash) % 6) + 1}`;
  }

  function resolveVisibleTelomereMarkerRect(markerRect, ctgRect) {
    const minimumMarkerWidth = 6;
    const ctgLeft = Number(ctgRect?.x);
    const ctgWidth = Number(ctgRect?.width);
    if (!Number.isFinite(ctgLeft) || !Number.isFinite(ctgWidth) || ctgWidth <= 0) {
      return null;
    }
    const markerCenterX = Number.isFinite(markerRect?.centerX)
      ? markerRect.centerX
      : Number(markerRect?.x || 0) + Number(markerRect?.width || 0) / 2;
    const markerWidth = Math.min(
      ctgWidth,
      Math.max(minimumMarkerWidth, Number(markerRect?.width || 0)),
    );
    const minX = ctgLeft;
    const maxX = ctgLeft + ctgWidth - markerWidth;
    const x = Math.max(minX, Math.min(maxX, markerCenterX - markerWidth / 2));
    return {
      x,
      width: markerWidth,
      centerX: x + markerWidth / 2,
    };
  }

  function renderTelomereMarkersForTrackCtg({ ctg, rect, y, barHeight, role, isMirror }) {
    if (role !== "primary" || isMirror || !Array.isArray(ctg?.telomereMarks) || ctg.telomereMarks.length === 0) {
      return "";
    }
    return ctg.telomereMarks
      .map((mark) => {
        const ctgStart = normalizePositiveInt(mark?.ctgStart ?? mark?.ctg_start ?? mark?.startBp ?? mark?.start_bp);
        const ctgEnd = normalizePositiveInt(mark?.ctgEnd ?? mark?.ctg_end ?? mark?.endBp ?? mark?.end_bp);
        const markerRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: rect,
          ctgLengthBp: ctg.lengthBp,
          ctgStartOffset: Number(ctgStart),
          ctgEndOffset: Number(ctgEnd),
        });
        if (!Number.isFinite(markerRect.x) || !Number.isFinite(markerRect.width) || markerRect.width <= 0) {
          return "";
        }
        const visibleMarkerRect = resolveVisibleTelomereMarkerRect(markerRect, rect);
        if (!visibleMarkerRect) {
          return "";
        }
        const ruleId = String(mark?.ruleId ?? mark?.rule_id ?? "");
        const motif = String(mark?.motif ?? "");
        const strand = String(mark?.strand ?? "");
        const repeatCount = normalizePositiveInt(mark?.repeatCount ?? mark?.repeat_count) ?? "";
        const tooltip = [
          motif || ruleId || "tel",
          repeatCount ? `repeat=${repeatCount}` : "",
          ctgStart && ctgEnd ? `range=${ctgStart}-${ctgEnd}` : "",
          strand ? `strand=${strand}` : "",
        ].filter(Boolean).join("|");
        return `<rect
              class="track-telomere-marker ${resolveTelomereRuleClass(ruleId)}"
              data-telomere-marker="1"
              data-telomere-rule-id="${escapeAttr(ruleId)}"
              data-telomere-motif="${escapeAttr(motif)}"
              data-telomere-contig-id="${escapeAttr(String(ctg.assemblyCtgId))}"
              data-telomere-ctg-start="${escapeAttr(String(ctgStart ?? ""))}"
              data-telomere-ctg-end="${escapeAttr(String(ctgEnd ?? ""))}"
              data-telomere-strand="${escapeAttr(strand)}"
              x="${visibleMarkerRect.x.toFixed(2)}"
              y="${(y + 1).toFixed(2)}"
              width="${visibleMarkerRect.width.toFixed(2)}"
              height="${Math.max(1, barHeight - 2)}"
              rx="1.5"
              ry="1.5"
            ><title>${escapeHtml(tooltip)}</title></rect>`;
      })
      .filter(Boolean)
      .join("");
  }

  function renderCentromereMarkersForTrackCtg({ ctg, rect, y, barHeight, role, isMirror }) {
    if (
      role !== "primary"
      || isMirror
      || !Array.isArray(ctg?.centromereMarks)
      || ctg.centromereMarks.length === 0
    ) {
      return "";
    }
    return ctg.centromereMarks
      .map((mark) => {
        const ctgStart = normalizePositiveInt(mark?.ctgStart ?? mark?.ctg_start ?? mark?.startBp ?? mark?.start_bp);
        const ctgEnd = normalizePositiveInt(mark?.ctgEnd ?? mark?.ctg_end ?? mark?.endBp ?? mark?.end_bp);
        const markerRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: rect,
          ctgLengthBp: ctg.lengthBp,
          ctgStartOffset: Number(ctgStart),
          ctgEndOffset: Number(ctgEnd),
        });
        if (!Number.isFinite(markerRect.x) || !Number.isFinite(markerRect.width) || markerRect.width <= 0) {
          return "";
        }
        const visibleMarkerRect = resolveVisibleTelomereMarkerRect(markerRect, rect);
        if (!visibleMarkerRect) {
          return "";
        }
        const cenId = String(mark?.cenId ?? mark?.cen_id ?? "cen");
        const queryName = String(mark?.queryName ?? mark?.query_name ?? "");
        const strand = String(mark?.strand ?? "");
        const identityValue = Number(mark?.identity);
        const identity = Number.isFinite(identityValue) ? String(identityValue) : String(mark?.identity ?? "");
        const tooltip = [
          cenId || "cen",
          ctgStart && ctgEnd ? `range=${ctgStart}-${ctgEnd}` : "",
          identity ? `identity=${identity}` : "",
          strand ? `strand=${strand}` : "",
        ].filter(Boolean).join("|");
        return `<rect
              class="track-centromere-marker"
              data-centromere-marker="1"
              data-centromere-cen-id="${escapeAttr(cenId)}"
              data-centromere-query-name="${escapeAttr(queryName)}"
              data-centromere-contig-id="${escapeAttr(String(ctg.assemblyCtgId))}"
              data-centromere-ctg-start="${escapeAttr(String(ctgStart ?? ""))}"
              data-centromere-ctg-end="${escapeAttr(String(ctgEnd ?? ""))}"
              data-centromere-strand="${escapeAttr(strand)}"
              x="${visibleMarkerRect.x.toFixed(2)}"
              y="${(y + 1).toFixed(2)}"
              width="${visibleMarkerRect.width.toFixed(2)}"
              height="${Math.max(1, barHeight - 2)}"
              rx="1.5"
              ry="1.5"
            ><title>${escapeHtml(tooltip)}</title></rect>`;
      })
      .filter(Boolean)
      .join("");
  }

  function renderNRegionMarkersForTrackCtg({ ctg, rect, y, barHeight, isMirror }) {
    if (isMirror || !Array.isArray(ctg?.nRegions) || ctg.nRegions.length === 0) {
      return "";
    }
    return ctg.nRegions
      .map((region) => {
        const ctgStart = normalizePositiveInt(region?.ctgStart ?? region?.ctg_start ?? region?.startBp ?? region?.start_bp);
        const ctgEnd = normalizePositiveInt(region?.ctgEnd ?? region?.ctg_end ?? region?.endBp ?? region?.end_bp);
        const markerRect = buildTrackHitRectWithinCtgDisplay({
          ctgRect: rect,
          ctgLengthBp: ctg.lengthBp,
          ctgStartOffset: Number(ctgStart),
          ctgEndOffset: Number(ctgEnd),
        });
        if (!Number.isFinite(markerRect.x) || !Number.isFinite(markerRect.width) || markerRect.width <= 0) {
          return "";
        }
        const visibleMarkerRect = resolveVisibleTelomereMarkerRect(markerRect, rect);
        if (!visibleMarkerRect) {
          return "";
        }
        const lengthValue = normalizePositiveInt(region?.lengthBp ?? region?.length_bp)
          ?? (ctgStart && ctgEnd ? Math.abs(ctgEnd - ctgStart) + 1 : null);
        const tooltip = [
          "N",
          ctgStart && ctgEnd ? `${ctgStart}-${ctgEnd}` : "",
          lengthValue ? String(lengthValue) : "",
        ].filter(Boolean).join("\t");
        return `<rect
              class="track-n-region-marker"
              data-n-region-marker="1"
              data-n-region-contig-id="${escapeAttr(String(ctg.assemblyCtgId))}"
              data-n-region-ctg-start="${escapeAttr(String(ctgStart ?? ""))}"
              data-n-region-ctg-end="${escapeAttr(String(ctgEnd ?? ""))}"
              data-n-region-length="${escapeAttr(String(lengthValue ?? ""))}"
              x="${visibleMarkerRect.x.toFixed(2)}"
              y="${(y + 1).toFixed(2)}"
              width="${visibleMarkerRect.width.toFixed(2)}"
              height="${Math.max(1, barHeight - 2)}"
              rx="1.5"
              ry="1.5"
            ><title>${escapeHtml(tooltip)}</title></rect>`;
      })
      .filter(Boolean)
      .join("");
  }

  function resolveReferenceTrackLabel(selectedChrName) {
    if (!selectedChrName) {
      return "ref_chr1";
    }
    const lowered = String(selectedChrName).trim().toLowerCase();
    let suffix = lowered.startsWith("chr") ? lowered.slice(3) : lowered;
    suffix = suffix.replace(/^[_\-\s]+/, "");
    if (/^\d+$/.test(suffix)) {
      suffix = String(Number(suffix));
    }
    return suffix ? `ref_chr${suffix}` : "ref_chr1";
  }


  function buildDeletedCtgChips(items, selectedRecordIds = new Set(), i18n) {
    const list = Array.isArray(items) ? items : [];
    if (!list.length) {
      return "";
    }
    const selectedSet = selectedRecordIds instanceof Set
      ? selectedRecordIds
      : new Set(normalizeDeletedCtgRecordIds(Array.from(selectedRecordIds || [])));
    const chips = list
      .map((item) => {
        const deletedCtgRecordId = normalizeSupportDatasetId(item?.deletedCtgRecordId);
        if (!deletedCtgRecordId) {
          return "";
        }
        const assemblyCtgId = normalizeSupportDatasetId(item?.assemblyCtgId) || "-";
        const totalLength = normalizePositiveInt(item?.totalLength) ?? 0;
        const fullName = resolveTrackCtgDisplayName(item, assemblyCtgId);
        const visibleName = resolveTrackCtgVisibleName(item, assemblyCtgId);
        const selectedClass = selectedSet.has(deletedCtgRecordId) ? "is-multi-selected" : "";
        return `
        <button
          type="button"
          class="ctg-chip ${selectedClass}"
          data-deleted-ctg-record-id="${deletedCtgRecordId}"
          data-deleted-assembly-ctg-id="${escapeAttr(String(assemblyCtgId))}"
          title="${escapeAttr(fullName)}"
        >
          <strong>${escapeHtml(visibleName)}</strong>
          <span class="ctg-chip-meta">${formatBp(totalLength)}</span>
        </button>
      `;
      })
      .filter((item) => item)
      .join("");
    if (!chips) {
      return "";
    }
    return `<div class="assembly-members-panel-head chip-group-separator">
      <span class="assembly-members-panel-title-inline">
        <strong>${escapeHtml(i18n.page.deletedMembersTitle)}</strong>
        <button
          type="button"
          class="assembly-members-icon-action"
          data-restore-all-deleted-ctgs="1"
          aria-label="${escapeAttr(i18n.page.restoreAllDeletedMembers)}"
          title="${escapeAttr(i18n.page.restoreAllDeletedMembers)}"
        >
          ↶
        </button>
      </span>
    </div>${chips}`;
  }

  function renderAssemblyStatusToast(assembly) {
    const parts = [];
    if (assembly?.actionStatus) {
      parts.push(`<p class="muted">${escapeHtml(assembly.actionStatus)}</p>`);
    }
    if (assembly?.actionError) {
      parts.push(`<p class="error-text">${escapeHtml(assembly.actionError)}</p>`);
    }
    if (!parts.length) {
      return "";
    }
    return `
    <div class="assembly-status-toast-wrap" aria-live="polite">
      ${parts.join("")}
    </div>
  `;
  }

  function formatBpInterval(start, end) {
    const resolvedStart = Number(start || 0).toLocaleString("en-US");
    const resolvedEnd = Number(end || 0).toLocaleString("en-US");
    return `${resolvedStart}-${resolvedEnd} bp`;
  }

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

  function resolveSupportDatasetLabelById(supportContext, datasetId) {
    const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
    const selectedSupportDatasetId = normalizeSupportDatasetId(supportContext?.supportDatasetId);
    const selectedSupportName = String(supportContext?.supportDatasetName || "").trim();
    if (
      normalizedDatasetId !== null
      && selectedSupportDatasetId !== null
      && normalizedDatasetId === selectedSupportDatasetId
      && selectedSupportName
    ) {
      return selectedSupportName;
    }
    const optionLabel = (Array.isArray(supportContext?.supportDatasetOptions) ? supportContext.supportDatasetOptions : [])
      .find((item) => normalizeSupportDatasetId(item?.datasetId) === normalizedDatasetId)?.label || "";
    if (optionLabel) {
      return String(optionLabel);
    }
    const mirrorDatasetName = (Array.isArray(supportContext?.supportMirrorCtgs) ? supportContext.supportMirrorCtgs : [])
      .find((entry) => normalizeSupportDatasetId(entry?.datasetId) === normalizedDatasetId)?.datasetName || "";
    if (mirrorDatasetName) {
      return String(mirrorDatasetName);
    }
    if (normalizedDatasetId !== null) {
      return `ds-${normalizedDatasetId}`;
    }
    return selectedSupportName;
  }

  function resolveSubviewTrackSelectionLabel(trackSelection, supportContext, i18n) {
    const normalizedSelection = normalizeSubviewTrackSelectionItem(trackSelection);
    if (!normalizedSelection) {
      return "";
    }
    if (normalizedSelection.role === "ref") {
      return String(supportContext?.refTrackLabel || "ref");
    }
    if (normalizedSelection.role === "phased") {
      const track = (Array.isArray(supportContext?.phasedChrTracks) ? supportContext.phasedChrTracks : [])
        .find((item) =>
          normalizeSupportDatasetId(item?.phasedTrackId) === normalizeSupportDatasetId(normalizedSelection.phasedTrackId),
        );
      const key = String(track?.label || normalizedSelection.haplotypeKey || normalizedSelection.phasedTrackId || "phased");
      return i18n.trackControls.phasedTrackLabel.replace("{key}", key);
    }
    if (normalizedSelection.role !== "support") {
      const primaryName = String(supportContext?.primaryDatasetName || "").trim();
      return primaryName
        ? i18n.trackControls.primaryTrackLabelWithName.replace("{name}", primaryName)
        : i18n.trackControls.primaryTrackLabel;
    }
    const supportName = resolveSupportDatasetLabelById(supportContext, normalizedSelection.datasetId);
    if (normalizedSelection.source === "mirror" || normalizedSelection.isMirror) {
      return supportName
        ? i18n.trackControls.mirrorTrackLabelWithName.replace("{name}", supportName)
        : i18n.trackControls.mirrorTrackLabel;
    }
    return supportName
      ? i18n.trackControls.supportTrackLabelWithName.replace("{name}", supportName)
      : i18n.trackControls.supportTrackLabel;
  }

  function resolveTrackToneClass(role) {
    const normalizedRole = normalizeTrackRole(role);
    if (normalizedRole === "support") {
      return " is-companion";
    }
    if (normalizedRole === "ref") {
      return " is-ref";
    }
    return "";
  }

  function getSubviewState(assembly) {
    return getSubviewStateImpl(assembly);
  }

  function renderAssemblyLoadingCurtain(assembly, i18n) {
    const loadingText = String(assembly?.summary || i18n.status?.loadingChromosomes || "Loading...");
    return `
      <div class="assembly-loading-curtain" data-assembly-loading-curtain="1" aria-busy="true" aria-live="polite">
        <div class="assembly-loading-panel">
          <div class="assembly-loading-spinner" aria-hidden="true"></div>
          <p class="assembly-loading-text">${escapeHtml(loadingText)}</p>
        </div>
      </div>
    `;
  }


  function renderAssemblyMainTab(state, options = {}) {
  const assembly = state.assembly;
  const session = state.session || {};
  const i18n = getAssemblyI18n(state);
  if (assembly.loading) {
    const projectLabel = String(session.projectName || session.projectId || "Project");
    const currentChrLabel = String(assembly.selectedChrName || "current-chr");
    const membersCardTitle = i18n.page.membersCardTitle
      .replace("{projectLabel}", projectLabel)
      .replace("{currentChrLabel}", currentChrLabel);
    const membersCardCollapsed = assembly?.membersCardCollapsed !== false;
    const membersCardToggleLabel = membersCardCollapsed
      ? i18n.page.expandMembersCard
      : i18n.page.collapseMembersCard;
    return `
      <div class="chr-strip has-members-panel">
        <div class="chr-title-wrap">
          <div class="chr-title-and-picker">
            <div class="chr-title">${
              assembly.selectedChrName
                ? `${i18n.chrTitle} ${escapeHtml(assembly.selectedChrName)}`
                : i18n.mainViewTitle
            }</div>
            <div class="chr-picker-inline">
              <button
                id="assembly-chr-picker-toggle"
                class="button ghost tiny"
                title="${escapeAttr(i18n.page.selectChromosomeTitle)}"
                aria-expanded="false"
                disabled
              >
                ▾
              </button>
            </div>
          </div>
        </div>
        <article class="card assembly-members-panel assembly-members-panel-inline is-collapsed">
          <div class="assembly-members-panel-head">
            <strong>${escapeHtml(membersCardTitle)}</strong>
            <button
              type="button"
              class="button ghost tiny"
              data-members-card-toggle="1"
              aria-expanded="${membersCardCollapsed ? "false" : "true"}"
              aria-label="${escapeAttr(membersCardToggleLabel)}"
              title="${escapeAttr(membersCardToggleLabel)}"
              disabled
            >
              ${membersCardCollapsed ? "▾" : "▴"}
            </button>
          </div>
        </article>
      </div>
      <section class="assembly-track-content-stack is-loading">
        <section class="assembly-main-view">
          ${renderAssemblyStatusToast(assembly)}
          <div class="assembly-track-unified assembly-track-panel assembly-track-loading-shell" aria-hidden="true"></div>
        </section>
        ${renderAssemblyLoadingCurtain(assembly, i18n)}
      </section>
    `;
  }
  const currentProject = getCurrentProject(state);
  const selectedChromosome = getSelectedChromosome(assembly);
  const supportDatasetOptions = getSupportDatasetOptions(state, currentProject);
  const supportDatasetId = normalizeSupportDatasetId(assembly.supportDatasetId);
  const primaryDatasetName = getDatasetNameById(
    state.initializer?.datasets || [],
    currentProject?.primaryDatasetId,
  );
  const selectedSupportDataset =
    supportDatasetOptions.find((item) => item.datasetId === supportDatasetId) || null;
  const trackPrefs = resolveTrackPrefs(assembly.trackView);
  const subviewTrackPrefs = resolveTrackPrefs(assembly.subviewTrackView || assembly.trackView);
  const subview = getSubviewStateImpl(assembly);
  const grtResultContext = resolveGrtResultContext(assembly);
  const grtResultPlan = grtResultContext.available
    ? buildGrtResultPlan(grtResultContext.baselineEntry)
    : null;
  const supportDsCtgLenBp = Math.max(0, normalizeNonNegativeInt(trackPrefs.supportDsCtgLen) ?? 0);
  const selectedChrName = String(assembly.selectedChrName || "").trim();
  const supportDsCtgLenRules = getSupportDsCtgLenRulesForChr(
    assembly.supportDsCtgLenRulesByChr,
    selectedChrName,
    { chrLength: selectedChromosome?.chrLength },
  );
  const supportTrackCtgs = supportDatasetId
    ? filterSupportCtgsBySupportDsCtgLenRules(assembly.supportChrCtgs || [], {
        rules: supportDsCtgLenRules,
        defaultSupportDsCtgLen: supportDsCtgLenBp,
        chrLength: selectedChromosome?.chrLength,
      })
    : [];
  const trackModel = buildDualTrackModel({
    primaryCtgs: assembly.chrCtgs,
    companionCtgs: supportTrackCtgs,
    selectedPrimaryCtgId: assembly.selectedCtgId,
    selectedCompanionCtgId: assembly.selectedCtgId,
    prefs: trackPrefs,
    preserveInputOrder: true,
  });
  const supportMirroredCtgs = buildSupportMirroredCtgsForRender({
    supportMirroredCtgs: assembly.supportMirroredCtgs,
    selectedChrName,
    supportDatasetId,
    supportDatasetName: selectedSupportDataset?.label || "",
    supportModelCtgs: trackModel.companion?.ctgs || [],
    supportDatasetOptions,
  });
  const subviewPanel = options.includeSubview === false
    ? ""
    : (() => {
      const supportSubviewCtgs = buildSupportSubviewCtgPool({
        supportChrCtgs: supportTrackCtgs,
        supportMirroredCtgs,
        selectedChrName,
        deletedCtgs: assembly.deletedCtgs,
        minSupportLengthBp: supportDsCtgLenBp,
        supportDsCtgLenRules,
      });
      const phasedSubviewCtgs = buildPhasedSubviewCtgPool({
        phasedChrTracks: assembly.phasedChrTracks || [],
        primaryCtgs: assembly.chrCtgs || [],
        deletedCtgs: assembly.deletedCtgs,
      });
      const refSubviewCtgs = getCachedFilteredRefSubviewCtgs({
        refTrackMembers: assembly.refTrackMembers || [],
        subview,
        supportContext: {
          primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
          supportDatasetId,
          selectedChrName,
          refTrackLabel: resolveReferenceTrackLabel(assembly.selectedChrName),
          primaryCtgs: assembly.chrCtgs,
          supportCtgs: supportSubviewCtgs,
          supportMirrorCtgs: normalizeSupportMirroredCtgs(supportMirroredCtgs),
          phasedCtgs: phasedSubviewCtgs,
        },
      });
      return renderSubviewSelectionPanel(
        assembly,
        {
          supportDatasetId,
          supportDatasetOptions,
          supportDatasetName: selectedSupportDataset?.label || "",
          primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
          primaryDatasetName,
          primaryCtgs: assembly.chrCtgs,
          supportCtgs: supportSubviewCtgs,
          supportMirrorCtgs: normalizeSupportMirroredCtgs(supportMirroredCtgs),
          phasedCtgs: phasedSubviewCtgs,
          phasedChrTracks: assembly.phasedChrTracks || [],
          refCtgs: refSubviewCtgs,
          refTrackLabel: resolveReferenceTrackLabel(assembly.selectedChrName),
        },
        subviewTrackPrefs,
        i18n,
      );
    })();
  const chromosomeOptions = assembly.chromosomes.length
    ? assembly.chromosomes
        .map((chr) => {
          const active = chr.chrName === assembly.selectedChrName ? "is-active" : "";
          return `<button class="chr-picker-option ${active}" data-chr-name="${escapeAttr(chr.chrName)}">
            <strong>${escapeHtml(chr.chrName)}</strong>
            <span>${chr.ctgCount} Contigs · ${formatBp(chr.placedBp)}</span>
          </button>`;
        })
        .join("")
    : `<div class="muted">${escapeHtml(i18n.page.noChromosomeData)}</div>`;
  const selectedDeletedRecordIds = new Set(
    normalizeDeletedCtgRecordIds(assembly.selectedDeletedCtgRecordIds),
  );
  const hiddenPrimaryCtgIdSet = new Set(
    filterPrimaryTrackSelectionCtgIds(assembly.hiddenPrimaryCtgIds, assembly),
  );
  const selectedPrimaryTrackCtgIdSet = new Set(
    filterPrimaryTrackSelectionCtgIds(assembly.trackSelectedCtgIds, assembly),
  );
  const historyHighlightCtgId = normalizeSupportDatasetId(assembly.historyHighlightCtgId);
  const ctgChips = assembly.chrCtgs.length
    ? assembly.chrCtgs
        .map((ctg) => {
          const active = ctg.assemblyCtgId === assembly.selectedCtgId ? "is-active" : "";
          const selectedClass = selectedPrimaryTrackCtgIdSet.has(Number(ctg.assemblyCtgId)) ? " is-multi-selected" : "";
          const hiddenClass = hiddenPrimaryCtgIdSet.has(Number(ctg.assemblyCtgId)) ? " is-hidden-contig" : "";
          const historyHighlightClass = historyHighlightCtgId === Number(ctg.assemblyCtgId)
            ? " is-history-highlighted"
            : "";
          const hiddenTag = hiddenClass
            ? ` <span class="ctg-chip-hidden-tag">${escapeHtml(i18n.page.deletedHiddenTag)}</span>`
            : "";
          const fullName = resolveTrackCtgDisplayName(ctg, ctg.assemblyCtgId);
          const visibleName = resolveTrackCtgVisibleName(ctg, ctg.assemblyCtgId);
          const sourceTagMarkup = renderDerivedSourceHtmlTag(ctg);
          const grtStatusMarkup = ctg.grtSourceCardKey
            ? `<span class="grt-status-badge is-${escapeAttr(ctg.grtPlacementMode || "normal")}" title="${escapeAttr(`${i18n.grt.refStatus}: ${ctg.grtRefAlignmentStatus || "-"}; ${i18n.grt.anchorSource}: ${i18n.grt.grtFinalPathAnchor}`)}">${escapeHtml(ctg.grtPlacementMode || "normal")}</span>`
            : "";
          const coAssignedChrNames = Array.isArray(ctg.coAssignedChrNames)
            ? ctg.coAssignedChrNames
                .map((chrName) => String(chrName || "").trim())
                .filter(Boolean)
            : [];
          const coAssignedTooltip = coAssignedChrNames.length
            ? i18n.page.coAssignedChrTooltip.replace("{chrNames}", coAssignedChrNames.join(", "))
            : "";
          if (coAssignedTooltip) {
            const nameTitle = `${escapeAttr(fullName)}&#10;${escapeAttr(coAssignedTooltip)}`;
            return `<button class="ctg-chip ${active}${selectedClass}${hiddenClass}${historyHighlightClass}" data-assembly-ctg-id="${ctg.assemblyCtgId}" data-track-focus-mode="start">
              <strong><span class="ctg-chip-name is-coassigned" title="${nameTitle}">${escapeHtml(visibleName)}</span>${sourceTagMarkup}${grtStatusMarkup}${hiddenTag}</strong>
              <span class="ctg-chip-meta">${formatBp(ctg.totalLength)}</span>
            </button>`;
          }
          const nameTitle = escapeAttr(fullName);
          return `<button class="ctg-chip ${active}${selectedClass}${hiddenClass}${historyHighlightClass}" data-assembly-ctg-id="${ctg.assemblyCtgId}" data-track-focus-mode="start" title="${nameTitle}">
            <strong>${escapeHtml(visibleName)}${sourceTagMarkup}${grtStatusMarkup}${hiddenTag}</strong>
            <span class="ctg-chip-meta">${formatBp(ctg.totalLength)}</span>
          </button>`;
        })
        .join("")
    : `<div class="muted">${escapeHtml(i18n.noContigsInChr)}</div>`;
  const deletedCtgChips = buildDeletedCtgChips(assembly.deletedCtgs, selectedDeletedRecordIds, i18n);
  const combinedMemberChips = `${ctgChips}${deletedCtgChips}`;
  const projectLabel = String(session.projectName || session.projectId || "Project");
  const currentChrLabel = String(assembly.selectedChrName || "current-chr");
  const membersCardTitle = i18n.page.membersCardTitle
    .replace("{projectLabel}", projectLabel)
    .replace("{currentChrLabel}", currentChrLabel);
  const membersCardCollapsed = assembly?.membersCardCollapsed !== false;
  const membersCardToggleLabel = membersCardCollapsed
    ? i18n.page.expandMembersCard
    : i18n.page.collapseMembersCard;
  const membersPanelClassName = membersCardCollapsed
    ? "card assembly-members-panel assembly-members-panel-inline is-collapsed"
    : "card assembly-members-panel assembly-members-panel-inline";
  const finalPathCard = options.includeFinalPath === false
    ? ""
    : renderAssemblyFinalPathCardImpl(state, deps);
  return `
      <div class="chr-strip has-members-panel">
        <div class="chr-title-wrap">
          <div class="chr-title-and-picker">
            <div class="chr-title">${
              assembly.selectedChrName
                ? `${i18n.chrTitle} ${escapeHtml(assembly.selectedChrName)}`
                : i18n.mainViewTitle
            }</div>
            <div class="chr-picker-inline">
              <button
                id="assembly-chr-picker-toggle"
                class="button ghost tiny"
                title="${escapeAttr(i18n.page.selectChromosomeTitle)}"
                aria-expanded="${assembly.chrPickerOpen ? "true" : "false"}"
                ${assembly.chromosomes.length ? "" : "disabled"}
              >
                ${assembly.chrPickerOpen ? "▴" : "▾"}
              </button>
              ${
                assembly.chrPickerOpen
                  ? `<div class="chr-picker-menu ${assembly.chromosomes.length ? "" : "muted"}">
                      ${chromosomeOptions}
                    </div>`
                  : ""
              }
            </div>
          </div>
        </div>
        <article class="${membersPanelClassName}">
          <div class="assembly-members-panel-head">
            <span class="assembly-members-panel-title-inline">
              <strong>${escapeHtml(membersCardTitle)}</strong>
              <button
                type="button"
                class="assembly-members-icon-action"
                data-reset-members-state="1"
                aria-label="${escapeAttr(i18n.page.resetMembersState)}"
                title="${escapeAttr(i18n.page.resetMembersState)}"
              >
                ↺
              </button>
            </span>
            <button
              type="button"
              class="button ghost tiny"
              data-members-card-toggle="1"
              aria-expanded="${membersCardCollapsed ? "false" : "true"}"
              aria-label="${escapeAttr(membersCardToggleLabel)}"
              title="${escapeAttr(membersCardToggleLabel)}"
            >
              ${membersCardCollapsed ? "▾" : "▴"}
            </button>
          </div>
          ${
            membersCardCollapsed
              ? ""
              : `<div class="ctg-chip-grid assembly-member-chip-region">${combinedMemberChips}</div>`
          }
        </article>
      </div>
      <section class="assembly-track-content-stack">
        <section class="assembly-main-view">
          ${renderAssemblyStatusToast(assembly)}
          ${renderAssemblyTracks({
            model: trackModel,
            hasPrimaryData: assembly.chrCtgs.length > 0,
            hasSupportTrack: supportDatasetId !== null,
            primaryDatasetName,
            supportDatasetName: selectedSupportDataset?.label || "",
            supportDatasetOptions,
            supportDatasetId,
            hasSupportDatasetOptions: supportDatasetOptions.length > 0,
            selectedChrName: assembly.selectedChrName,
            chrLength: normalizePositiveInt(selectedChromosome?.chrLength),
            supportDsCtgLenRules,
            supportDsCtgLenRulesDialogOpen: assembly.supportDsCtgLenRulesDialogOpen === true,
            refTrackMembers: assembly.refTrackMembers,
            trackPrefs,
            subview,
            selectionCtgIds: assembly.trackSelectedCtgIds,
            hiddenPrimaryCtgIds: assembly.hiddenPrimaryCtgIds,
            dragOffsets: assembly.trackDragOffsets,
            supportMirroredCtgs,
            activeHitsTrackKey: assembly.activeHitsTrackKey,
            phasedAssemblyEnabled: Boolean(currentProject?.phasedAssemblyEnabled),
            phasedChrTracks: assembly.phasedChrTracks,
            grtResultContext,
            grtResultPlan,
            grtResultToast: assembly.grtResultToast,
            mainViewHistory: assembly.mainViewHistory,
            historyHighlightCtgId,
            i18n,
          })}
          ${subviewPanel}
        </section>
        ${finalPathCard}
      </section>
  `;
}

  function renderAssemblySubviewPanel(state) {
    const assembly = state.assembly;
    const i18n = getAssemblyI18n(state);
    const currentProject = getCurrentProject(state);
    const supportDatasetOptions = getSupportDatasetOptions(state, currentProject);
    const supportDatasetId = normalizeSupportDatasetId(assembly.supportDatasetId);
    const primaryDatasetName = getDatasetNameById(
      state.initializer?.datasets || [],
      currentProject?.primaryDatasetId,
    );
    const selectedSupportDataset =
      supportDatasetOptions.find((item) => item.datasetId === supportDatasetId) || null;
    const selectedChromosome = getSelectedChromosome(assembly);
    const trackPrefs = resolveTrackPrefs(assembly.trackView);
    const subviewTrackPrefs = resolveTrackPrefs(assembly.subviewTrackView || assembly.trackView);
    const subview = getSubviewStateImpl(assembly);
    const supportDsCtgLenBp = Math.max(0, normalizeNonNegativeInt(trackPrefs.supportDsCtgLen) ?? 0);
    const selectedChrName = String(assembly.selectedChrName || "").trim();
    const supportDsCtgLenRules = getSupportDsCtgLenRulesForChr(
      assembly.supportDsCtgLenRulesByChr,
      selectedChrName,
      { chrLength: selectedChromosome?.chrLength },
    );
    const supportTrackCtgs = supportDatasetId
      ? filterSupportCtgsBySupportDsCtgLenRules(assembly.supportChrCtgs || [], {
          rules: supportDsCtgLenRules,
          defaultSupportDsCtgLen: supportDsCtgLenBp,
          chrLength: selectedChromosome?.chrLength,
        })
      : [];
    const trackModel = buildDualTrackModel({
      primaryCtgs: assembly.chrCtgs,
      companionCtgs: supportTrackCtgs,
      selectedPrimaryCtgId: assembly.selectedCtgId,
      selectedCompanionCtgId: assembly.selectedCtgId,
      prefs: trackPrefs,
      preserveInputOrder: true,
    });
    const supportMirroredCtgs = buildSupportMirroredCtgsForRender({
      supportMirroredCtgs: assembly.supportMirroredCtgs,
      selectedChrName,
      supportDatasetId,
      supportDatasetName: selectedSupportDataset?.label || "",
      supportModelCtgs: trackModel.companion?.ctgs || [],
      supportDatasetOptions,
    });
    const supportSubviewCtgs = buildSupportSubviewCtgPool({
      supportChrCtgs: supportTrackCtgs,
      supportMirroredCtgs,
      selectedChrName,
      deletedCtgs: assembly.deletedCtgs,
      minSupportLengthBp: supportDsCtgLenBp,
      supportDsCtgLenRules,
    });
    const phasedSubviewCtgs = buildPhasedSubviewCtgPool({
      phasedChrTracks: assembly.phasedChrTracks || [],
      primaryCtgs: assembly.chrCtgs || [],
      deletedCtgs: assembly.deletedCtgs,
    });
    const supportContext = {
      supportDatasetId,
      supportDatasetOptions,
      supportDatasetName: selectedSupportDataset?.label || "",
      primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
      primaryDatasetName,
      primaryCtgs: assembly.chrCtgs,
      supportCtgs: supportSubviewCtgs,
      supportMirrorCtgs: normalizeSupportMirroredCtgs(supportMirroredCtgs),
      phasedCtgs: phasedSubviewCtgs,
      phasedChrTracks: assembly.phasedChrTracks || [],
      refCtgs: getCachedFilteredRefSubviewCtgs({
        refTrackMembers: assembly.refTrackMembers || [],
        subview,
        supportContext: {
          primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
          supportDatasetId,
          selectedChrName,
          refTrackLabel: resolveReferenceTrackLabel(assembly.selectedChrName),
          primaryCtgs: assembly.chrCtgs,
          supportCtgs: supportSubviewCtgs,
          supportMirrorCtgs: normalizeSupportMirroredCtgs(supportMirroredCtgs),
          phasedCtgs: phasedSubviewCtgs,
        },
      }),
      refTrackLabel: resolveReferenceTrackLabel(assembly.selectedChrName),
    };
    return renderSubviewSelectionPanel(assembly, supportContext, subviewTrackPrefs, i18n);
  }

function renderAssemblyTrackControls({
  trackPrefs,
  supportDsCtgLenRules = [],
  chrLength = null,
  supportDatasetOptions,
  supportDatasetId,
  i18n,
}) {
  const supportOptions = supportDatasetOptions.length
    ? supportDatasetOptions
        .map((dataset) => {
          const active = dataset.datasetId === supportDatasetId ? "selected" : "";
          return `<option value="${dataset.datasetId}" ${active}>${escapeHtml(dataset.label)}</option>`;
        })
        .join("")
    : "";
  const supportDatasetSelect = supportDatasetOptions.length
    ? renderFixedTrackSelect({
        id: "assembly-support-dataset-id",
        shellClassName: "assembly-track-select-shell is-support",
        optionsHtml: supportOptions,
      })
    : "";
  const minTickUnitInput = renderTrackNumberInput({
    field: "minTickUnitKb",
    id: "assembly-track-min-tick-unit-kb",
    label: i18n.trackControls.minTickUnitKb,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.minTickUnitKb),
    value: trackPrefs.minTickUnitKb,
    options: MIN_TICK_UNIT_KB_OPTIONS,
  });
  const supportDsCtgLenInput = renderSupportDsCtgLenControl({
    field: "supportDsCtgLen",
    id: "assembly-track-support-ds-ctg-len",
    label: i18n.trackControls.supportDatasetLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.supportDatasetLengthBp),
    value: trackPrefs.supportDsCtgLen,
    options: SUPPORT_DS_CTG_LEN_BP_OPTIONS,
    supportDsCtgLenRules,
    chrLength,
    i18n,
  });
  const maxTickCountInput = renderTrackNumberInput({
    field: "maxTickCount",
    id: "assembly-track-max-tick-count",
    label: i18n.trackControls.maxTickCount,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.maxTickCount),
    value: trackPrefs.maxTickCount,
    options: MAX_TICK_COUNT_OPTIONS,
  });
  const alignmentInput = renderTrackNumberInput({
    field: "alignmentLength",
    id: "assembly-track-alignment-length",
    label: i18n.trackControls.alignmentLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.alignmentLengthBp),
    value: trackPrefs.alignmentLength,
    options: ALIGNMENT_LENGTH_OPTIONS,
  });
  const mapqInput = renderTrackNumberInput({
    field: "mapq",
    id: "assembly-track-mapq",
    label: i18n.trackControls.mapq,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.mapq),
    value: trackPrefs.mapq,
    options: MAPQ_OPTIONS,
    allowZero: true,
  });
  return `
    <div class="assembly-v1-control-grid">
      <div class="assembly-v1-control-item assembly-v1-control-item-wide">
        <label>${escapeHtml(i18n.trackControls.supportDataset)}</label>
        ${
          supportDatasetOptions.length
            ? supportDatasetSelect
            : `<div class="muted assembly-v1-control-note">${escapeHtml(i18n.trackControls.noSupportDatasetConfigured)}</div>`
        }
      </div>
      <div class="assembly-v1-control-item">
        <label>${renderSupportDsCtgLenLabel(i18n)}</label>
        ${supportDsCtgLenInput}
      </div>
      <div class="assembly-v1-control-item">
        <label>${escapeHtml(i18n.trackControls.minTickUnitKb)}</label>
        ${minTickUnitInput}
      </div>
      <div class="assembly-v1-control-item">
        <label>${escapeHtml(i18n.trackControls.maxTickCount)}</label>
        ${maxTickCountInput}
      </div>
      <div class="assembly-v1-control-item">
        <label>${escapeHtml(i18n.trackControls.alignmentLengthBp)}</label>
        ${alignmentInput}
      </div>
      <div class="assembly-v1-control-item">
        <label>${escapeHtml(i18n.trackControls.mapq)}</label>
        ${mapqInput}
      </div>
    </div>
  `;
}

function renderAssemblyTrackInlineControls({
  trackPrefs,
  supportDsCtgLenRules = [],
  chrLength = null,
  supportDatasetOptions,
  supportDatasetId,
  selectedChrName,
  mainViewHistory,
  i18n,
}) {
  const supportOptions = supportDatasetOptions.length
    ? supportDatasetOptions
        .map((dataset) => {
          const active = dataset.datasetId === supportDatasetId ? "selected" : "";
          return `<option value="${dataset.datasetId}" ${active}>${escapeHtml(dataset.label)}</option>`;
        })
        .join("")
    : "";
  const supportDatasetSelect = supportDatasetOptions.length
    ? renderFixedTrackSelect({
        id: "assembly-support-dataset-id",
        shellClassName: "assembly-track-select-shell is-support",
        optionsHtml: supportOptions,
      })
    : "";
  const minTickUnitInput = renderTrackNumberInput({
    field: "minTickUnitKb",
    id: "assembly-track-min-tick-unit-kb",
    label: i18n.trackControls.minTickUnitKb,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.minTickUnitKb),
    value: trackPrefs.minTickUnitKb,
    options: MIN_TICK_UNIT_KB_OPTIONS,
  });
  const supportDsCtgLenInput = renderSupportDsCtgLenControl({
    field: "supportDsCtgLen",
    id: "assembly-track-support-ds-ctg-len",
    label: i18n.trackControls.supportDatasetLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.supportDatasetLengthBp),
    value: trackPrefs.supportDsCtgLen,
    options: SUPPORT_DS_CTG_LEN_BP_OPTIONS,
    supportDsCtgLenRules,
    chrLength,
    i18n,
  });
  const maxTickCountInput = renderTrackNumberInput({
    field: "maxTickCount",
    id: "assembly-track-max-tick-count",
    label: i18n.trackControls.maxTickCount,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.maxTickCount),
    value: trackPrefs.maxTickCount,
    options: MAX_TICK_COUNT_OPTIONS,
  });
  const alignmentInput = renderTrackNumberInput({
    field: "alignmentLength",
    id: "assembly-track-alignment-length",
    label: i18n.trackControls.alignmentLengthBp,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.alignmentLengthBp),
    value: trackPrefs.alignmentLength,
    options: ALIGNMENT_LENGTH_OPTIONS,
  });
  const mapqInput = renderTrackNumberInput({
    field: "mapq",
    id: "assembly-track-mapq",
    label: i18n.trackControls.mapq,
    openOptionLabel: i18n.trackControls.openOptionCandidates.replace("{label}", i18n.trackControls.mapq),
    value: trackPrefs.mapq,
    options: MAPQ_OPTIONS,
    allowZero: true,
  });
  const mainViewHistoryControls = renderMainViewHistoryControls({
    selectedChrName,
    history: mainViewHistory,
    i18n,
  });
  return `
    <div class="assembly-track-inline-controls" data-main-track-inline-controls role="group" aria-label="${escapeAttr(i18n.page.primaryAlignmentViewControlsAria)}">
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.supportDataset)}</span>
        ${
          supportDatasetOptions.length
            ? supportDatasetSelect
            : `<span class="muted">${escapeHtml(i18n.trackControls.unconfigured)}</span>`
        }
      </label>
      <label class="assembly-track-inline-field">
        ${renderSupportDsCtgLenLabel(i18n)}
        ${supportDsCtgLenInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.minTickUnitKb)}</span>
        ${minTickUnitInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.maxTickCount)}</span>
        ${maxTickCountInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.alignmentLengthBp)}</span>
        ${alignmentInput}
      </label>
      <label class="assembly-track-inline-field">
        <span>${escapeHtml(i18n.trackControls.mapq)}</span>
        ${mapqInput}
      </label>
      ${mainViewHistoryControls}
    </div>
  `;
}

function replaceMainHistoryTokens(template, values = {}) {
  return Object.entries(values).reduce(
    (text, [key, value]) => String(text).replaceAll(`{${key}}`, String(value ?? "")),
    String(template || ""),
  );
}

function describeMainViewHistoryOperation(operation, i18n) {
  const kind = String(operation?.kind || "").trim().toLowerCase();
  const targetCount = Math.max(0, Math.trunc(Number(operation?.targetCount || 0)));
  const targetName = String(operation?.targetName || "").trim()
    || i18n.mainHistory.targetFallback;
  const template = i18n.mainHistory.operations?.[kind]
    || i18n.mainHistory.operationFallback;
  return replaceMainHistoryTokens(template, {
    count: targetCount,
    target: targetName,
  });
}

function renderMainViewHistoryControls({ selectedChrName, history, i18n }) {
  const chrName = String(selectedChrName || "").trim();
  if (!chrName || chrName.toLowerCase() === "unplaced") {
    return "";
  }
  const inFlight = history?.inFlight === true;
  const undoDisabled = inFlight || history?.canUndo !== true;
  const redoDisabled = inFlight || history?.canRedo !== true;
  const resetDisabled = inFlight || history?.canReset !== true;
  const undoTitle = undoDisabled
    ? i18n.mainHistory.undoUnavailable
    : replaceMainHistoryTokens(i18n.mainHistory.undoAction, {
      operation: describeMainViewHistoryOperation(history.undoOperation, i18n),
    });
  const redoTitle = redoDisabled
    ? i18n.mainHistory.redoUnavailable
    : replaceMainHistoryTokens(i18n.mainHistory.redoAction, {
      operation: describeMainViewHistoryOperation(history.redoOperation, i18n),
    });
  const resetTitle = resetDisabled
    ? i18n.mainHistory.resetUnavailable
    : replaceMainHistoryTokens(i18n.mainHistory.resetAction, {
      chrName,
      count: Math.max(0, Math.trunc(Number(history?.appliedOperationCount || 0))),
    });
  return `
    <div class="main-view-history-controls" role="group" aria-label="${escapeAttr(i18n.mainHistory.controlsAria)}">
      <button type="button" class="main-view-history-button" data-main-history-action="undo" aria-label="${escapeAttr(undoTitle)}" title="${escapeAttr(undoTitle)}" ${undoDisabled ? "disabled" : ""}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.2 6.3 3.5 12l5.7 5.7M4 12h9.2a6.8 6.8 0 0 1 6.8 6.8" /></svg>
      </button>
      <button type="button" class="main-view-history-button" data-main-history-action="redo" aria-label="${escapeAttr(redoTitle)}" title="${escapeAttr(redoTitle)}" ${redoDisabled ? "disabled" : ""}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14.8 6.3 5.7 5.7-5.7 5.7M20 12h-9.2A6.8 6.8 0 0 0 4 18.8" /></svg>
      </button>
      <span class="main-view-history-separator" aria-hidden="true"></span>
      <button type="button" class="main-view-history-button is-reset" data-main-history-action="reset" aria-label="${escapeAttr(resetTitle)}" title="${escapeAttr(resetTitle)}" ${resetDisabled ? "disabled" : ""}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.6 8.2V3.8m0 4.4H9M5 8a8 8 0 1 1-1 6.2" /></svg>
      </button>
    </div>
  `;
}

function renderCreatePhasedTrackButton({ phasedAssemblyEnabled, phasedTrackCount = 0, i18n }) {
  if (!phasedAssemblyEnabled) {
    return "";
  }
  const disabled = Number(phasedTrackCount) >= 26 ? "disabled" : "";
  const label = i18n.trackControls.createPhasedTrack;
  return `<button type="button" class="button ghost tiny" data-create-phased-track="1" ${disabled}>${escapeHtml(label)}</button>`;
}

function renderFixedTrackSelect({ id, shellClassName = "assembly-track-select-shell", optionsHtml }) {
  return `
    <div class="${shellClassName}">
      <select id="${id}" class="assembly-track-fixed-select">${optionsHtml}</select>
      <span class="assembly-track-control-marker" aria-hidden="true">▾</span>
    </div>
  `;
}

function renderSupportDsCtgLenControl({
  field,
  id,
  label,
  openOptionLabel = "",
  value,
  options,
  supportDsCtgLenRules = [],
  chrLength = null,
  i18n,
}) {
  const advancedActive = hasAdvancedSupportDsCtgLenRules(supportDsCtgLenRules, { chrLength });
  const inputHtml = advancedActive
    ? `
      <div class="assembly-track-combo is-readonly-summary" data-track-combo-field="${escapeAttr(field)}">
        <input
          id="${id}"
          class="assembly-track-combo-input"
          type="text"
          value="${escapeAttr((i18n.trackControls.supportDatasetLengthAdvancedSummary || "Advanced({count})").replace("{count}", String(supportDsCtgLenRules.length)))}"
          readonly
          aria-readonly="true"
          title="${escapeAttr((i18n.trackControls.supportDatasetLengthAdvancedTitle || "Current chromosome uses {count} region rules").replace("{count}", String(supportDsCtgLenRules.length)))}"
        >
      </div>
    `
    : renderTrackNumberInput({
      field,
      id,
      label,
      openOptionLabel,
      value,
      options,
      allowZero: true,
    });
  return inputHtml;
}

function renderSupportDsCtgLenLabel(i18n) {
  const label = i18n.trackControls.supportDatasetLengthBp;
  const settingsLabel = i18n.trackControls.supportDatasetLengthRulesSettings || "Advanced rules";
  return `
    <span class="assembly-support-ds-len-label">
      ${escapeHtml(label)}
      <button
        type="button"
        class="assembly-support-ds-len-settings-button"
        data-support-ds-ctg-len-settings="1"
        aria-label="${escapeAttr(settingsLabel)}"
        title="${escapeAttr(settingsLabel)}"
      >⚙</button>
    </span>
  `;
}

function renderTrackNumberInput({ field, id, label, openOptionLabel = "", value, options, allowZero = false }) {
  const normalizedRaw = allowZero ? normalizeNonNegativeInt(value) : normalizePositiveInt(value);
  const normalized = normalizedRaw ?? (allowZero ? 0 : 1);
  const menuId = `${id}-menu`;
  const optionButtons = options
    .map((optionValue) => {
      const active = Number(optionValue) === Number(normalized) ? " is-active" : "";
      const selected = Number(optionValue) === Number(normalized) ? "true" : "false";
      return `<button type="button" class="assembly-track-combo-option${active}" data-track-combo-option data-track-combo-value="${optionValue}" role="option" aria-selected="${selected}">${escapeHtml(String(optionValue))}</button>`;
    })
    .join("");
  return `
    <div class="assembly-track-combo" data-track-combo-field="${escapeAttr(field)}">
      <input
        id="${id}"
        class="assembly-track-combo-input"
        type="text"
        inputmode="numeric"
        pattern="[0-9]*"
        value="${escapeAttr(String(normalized))}"
        autocomplete="off"
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

function renderAssemblyTracks({
  model,
  hasPrimaryData,
  hasSupportTrack,
  primaryDatasetName,
  supportDatasetName,
  supportDatasetOptions,
  supportDatasetId,
  hasSupportDatasetOptions,
  selectedChrName,
  chrLength,
  supportDsCtgLenRules = [],
  supportDsCtgLenRulesDialogOpen = false,
  refTrackMembers = [],
  trackPrefs,
  subview,
  selectionCtgIds = [],
  hiddenPrimaryCtgIds = [],
  dragOffsets = [],
  supportMirroredCtgs = [],
  activeHitsTrackKey = "primary",
  phasedAssemblyEnabled = false,
  phasedChrTracks = [],
  grtResultContext = null,
  grtResultPlan = null,
  grtResultToast = null,
  mainViewHistory = null,
  historyHighlightCtgId = null,
  i18n,
}) {
  const TRACK_HEIGHT_SCALE = 2;
  const TRACK_LANE_HEIGHT = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_GAP = 18 * TRACK_HEIGHT_SCALE;
  const TRACK_MIRROR_ROW_GAP = 10;
  const TRACK_BAR_HEIGHT = 14;
  const TRACK_ROW_PADDING_TOP = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_ROW_EXTRA_HEIGHT = 22 * TRACK_HEIGHT_SCALE;
  const REF_ROW_HEIGHT = 34 * TRACK_HEIGHT_SCALE;
  const TRACK_TAIL_PADDING = 10 * TRACK_HEIGHT_SCALE;
  const TRACK_LABEL_OFFSET_Y = 2 * TRACK_HEIGHT_SCALE;
  const TRACK_EDGE_LABEL_PADDING = 8 * TRACK_HEIGHT_SCALE;
  const TRACK_TEXT_OFFSET_Y = 11;
  const TRACK_MIN_ADJACENT_GAP_PX = 20;
  const TRACK_LABEL_ROW_HEIGHT = 18;
  const TRACK_LABEL_ALIGN_OFFSET = Math.max(
    0,
    Math.round((TRACK_LABEL_ROW_HEIGHT - TRACK_BAR_HEIGHT) / 2),
  );
  const LABEL_COLUMN_WIDTH_PX = 136;
  const blockLength = Math.max(1, normalizePositiveInt(trackPrefs?.alignmentLength) ?? 1);
  const minMapq = Math.max(0, normalizeNonNegativeInt(trackPrefs?.mapq) ?? 0);
  const resolvedChrLength = normalizePositiveInt(chrLength);
  const hasResolvedChrLength = resolvedChrLength !== null;
  const maxPrimaryEndBp = resolveMaxTrackEndBp(model?.primary?.ctgs || []);
  const maxCompanionEndBp = resolveMaxTrackEndBp(model?.companion?.ctgs || []);
  const mirrorRows = buildSupportMirrorTrackRows(supportMirroredCtgs, i18n);
  const maxMirrorEndBp = resolveMaxTrackEndBp(
    mirrorRows.flatMap((row) => (Array.isArray(row.trackModel?.ctgs) ? row.trackModel.ctgs : [])),
  );
  const maxTrackEndBp = Math.max(maxPrimaryEndBp, maxCompanionEndBp, maxMirrorEndBp);
  const visualWindowStart = hasResolvedChrLength
    ? Math.min(0, model.primary.windowStart)
    : model.primary.windowStart;
  const visualDomainSpanBp = hasResolvedChrLength
    ? Math.max(
        1,
        resolvedChrLength - visualWindowStart,
        maxTrackEndBp - visualWindowStart + 1,
      )
    : Math.max(1, model.primary.domainSpanBp);
  const innerWidth = resolveTrackInnerWidthFromScale({
    domainSpanBp: visualDomainSpanBp,
    minTickUnitKb: trackPrefs?.minTickUnitKb,
    maxTickCount: trackPrefs?.maxTickCount,
    baseViewportPx: getMeasuredTrackViewportPx("primary"),
    fallbackInnerWidth: model.primary.innerWidth,
  });
  const tickBp = resolveTickBpFromScale({
    domainSpanBp: visualDomainSpanBp,
    minTickUnitKb: trackPrefs?.minTickUnitKb,
    maxTickCount: trackPrefs?.maxTickCount,
    fallbackTickBp: trackPrefs?.tickBp,
  });
  const visualWindowEnd = visualWindowStart + visualDomainSpanBp;
  const trackRows = [];
  if (hasSupportTrack) {
    trackRows.push({
      id: "support",
      role: "support",
      interactiveRole: "support",
      dragRole: "support",
      label: supportDatasetName
        ? i18n.trackControls.supportTrackLabelWithName.replace("{name}", supportDatasetName)
        : i18n.trackControls.supportTrackLabel,
      trackModel: model.companion,
      selectable: true,
      emptyMessage: i18n.trackControls.supportTrackEmpty,
      className: "is-companion",
      connectorDirection: "down",
      includeBands: true,
      datasetId: supportDatasetId,
    });
  } else if (hasSupportDatasetOptions) {
    trackRows.push({
      id: "support",
      role: "support",
      interactiveRole: "support",
      dragRole: "support",
      label: i18n.trackControls.supportTrackLabelUnselected,
      trackModel: { ...model.companion, ctgs: [], laneCount: 1 },
      selectable: false,
      emptyMessage: i18n.trackControls.supportTrackSelectFirst,
      className: "is-companion",
      connectorDirection: "down",
      includeBands: true,
      datasetId: null,
    });
  }
  trackRows.push({
    id: "primary",
    role: "primary",
    interactiveRole: "primary",
    dragRole: "primary",
    label: primaryDatasetName
      ? i18n.trackControls.primaryTrackLabelWithName.replace("{name}", primaryDatasetName)
      : i18n.trackControls.primaryTrackLabel,
    trackModel: model.primary,
    selectable: true,
    emptyMessage: hasPrimaryData ? i18n.trackControls.primaryTrackEmpty : i18n.noContigsInChr,
    className: "",
    connectorDirection: "up",
    includeBands: String(activeHitsTrackKey) === "primary",
    datasetId: null,
  });
  const phasedRows = buildPhasedTrackRows({
    phasedChrTracks,
    primaryModel: model.primary,
    activeHitsTrackKey,
    i18n,
  });
  trackRows.push(...phasedRows);
  const normalizedSupportDatasetId = normalizeSupportDatasetId(supportDatasetId);
  trackRows.push(
    ...mirrorRows.map((row) => ({
      ...row,
      alignWithSupport:
        hasSupportTrack
        && normalizedSupportDatasetId !== null
        && normalizeSupportDatasetId(row.datasetId) === normalizedSupportDatasetId,
    })),
  );

  const rulerTop = 24 * TRACK_HEIGHT_SCALE;
  let cursorY = 44 * TRACK_HEIGHT_SCALE;
  const rowLayouts = [];
  const refLabel = resolveReferenceTrackLabel(selectedChrName);
  const refRowLayout = {
    id: "ref",
    role: "ref",
    interactiveRole: "ref",
    label: refLabel,
    selectable: true,
    barY: 0,
    labelY: 0,
    labelTop: 0,
    rowTop: 0,
    rowBottom: 0,
  };
  const appendRowLayout = (row, gapAfter = TRACK_ROW_GAP) => {
    const laneCount = Math.max(1, row.trackModel?.laneCount || 1);
    const rowHeight = laneCount * TRACK_LANE_HEIGHT + TRACK_ROW_EXTRA_HEIGHT;
    const layout = {
      ...row,
      laneCount,
      rowTop: cursorY,
      laneTop: cursorY + TRACK_ROW_PADDING_TOP,
      labelY: cursorY - TRACK_LABEL_OFFSET_Y,
      labelTop: cursorY + TRACK_ROW_PADDING_TOP - TRACK_LABEL_ALIGN_OFFSET,
      rowBottom: cursorY + rowHeight,
    };
    rowLayouts.push(layout);
    cursorY += rowHeight + Math.max(0, Number(gapAfter) || 0);
    return layout;
  };
  const supportRow = trackRows.find((row) => row.id === "support");
  const supportLayout = supportRow ? appendRowLayout(supportRow) : null;
  refRowLayout.rowTop = cursorY;
  refRowLayout.barY = cursorY + TRACK_ROW_PADDING_TOP;
  refRowLayout.labelY = cursorY - TRACK_LABEL_OFFSET_Y;
  refRowLayout.labelTop = refRowLayout.barY - TRACK_LABEL_ALIGN_OFFSET;
  refRowLayout.rowBottom = cursorY + REF_ROW_HEIGHT;
  cursorY += REF_ROW_HEIGHT + TRACK_ROW_GAP;

  const rowsAfterRef = trackRows.filter((row) => row.id !== "support");
  const hasMirrorRows = rowsAfterRef.some((row) => row.isMirror);
  const hasPhasedRows = rowsAfterRef.some((row) => row.role === "phased");
  if (!hasMirrorRows && !hasPhasedRows) {
    rowsAfterRef.forEach((row, index) => {
      const isLast = index === rowsAfterRef.length - 1;
      appendRowLayout(row, isLast ? 0 : TRACK_ROW_GAP);
    });
  } else {
    rowsAfterRef.forEach((row, index) => {
      const laneCount = Math.max(1, row.trackModel?.laneCount || 1);
      const barInsetPx = row.isMirror ? 0 : TRACK_ROW_PADDING_TOP;
      const rowHeight = laneCount * TRACK_LANE_HEIGHT + TRACK_ROW_EXTRA_HEIGHT;
      const layout = {
        ...row,
        laneCount,
        rowTop: cursorY,
        laneTop: cursorY + barInsetPx,
        labelY: cursorY - TRACK_LABEL_OFFSET_Y,
        labelTop: cursorY + barInsetPx - TRACK_LABEL_ALIGN_OFFSET,
        rowBottom: cursorY + rowHeight,
      };
      rowLayouts.push(layout);
      const lastLaneBottom = layout.laneTop + (laneCount - 1) * TRACK_LANE_HEIGHT + TRACK_BAR_HEIGHT;
      const nextRow = rowsAfterRef[index + 1] || null;
      if (!nextRow) {
        cursorY = lastLaneBottom;
        return;
      }
      const nextInset = nextRow.isMirror ? 0 : TRACK_ROW_PADDING_TOP;
      const usesCompactPhasedGap = row.role === "phased" || nextRow.role === "phased";
      const gapBetweenBars = nextRow.isMirror || row.isMirror || usesCompactPhasedGap
        ? TRACK_MIRROR_ROW_GAP
        : TRACK_ROW_GAP;
      cursorY = lastLaneBottom + gapBetweenBars - nextInset;
    });
  }
  const firstTrackLayout = supportLayout || rowLayouts.find((layout) => layout.id !== "ref") || null;
  const topTrackGapToRuler = firstTrackLayout
    ? Math.max(0, roundTrackMetric(firstTrackLayout.laneTop - rulerTop))
    : TRACK_TAIL_PADDING;
  const tailPadding = hasMirrorRows ? topTrackGapToRuler : TRACK_TAIL_PADDING;
  cursorY += tailPadding;

  const contentBottom = cursorY;
  const buildTrackRectsByLayoutId = (resolvedInnerWidth) =>
    new Map(
      rowLayouts.map((layout) => [
        layout.id,
        buildTrackRectsWithMinGap(layout.trackModel.ctgs, {
          windowStart: visualWindowStart,
          domainSpanBp: visualDomainSpanBp,
          innerWidth: resolvedInnerWidth,
          minGapPx: TRACK_MIN_ADJACENT_GAP_PX,
        }),
      ]),
    );

  const trackRectsByLayoutId = buildTrackRectsByLayoutId(innerWidth);
  const buildBaseRectByCtgId = (layout) => {
    if (!layout) {
      return new Map();
    }
    const rects = trackRectsByLayoutId.get(layout.id) || [];
    return new Map(
      (Array.isArray(layout.trackModel?.ctgs) ? layout.trackModel.ctgs : [])
        .map((ctg, index) => {
          const ctgId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
          if (ctgId === null) {
            return null;
          }
          const baseRect = rects[index] ?? buildTrackRect(ctg, {
            windowStart: visualWindowStart,
            domainSpanBp: visualDomainSpanBp,
            innerWidth,
          });
          return [ctgId, baseRect];
        })
        .filter((item) => item !== null),
    );
  };
  const primaryLayout = rowLayouts.find((layout) => layout.role === "primary") || null;
  const primaryRectByCtgId = buildBaseRectByCtgId(primaryLayout);
  const trackDragOffsetMap = new Map(
    normalizeTrackDragOffsets(dragOffsets).map((item) => [
      buildTrackDragOffsetKey(item.trackRole, item.assemblyCtgId, item),
      item,
    ]),
  );
  const resolveTrackCtgHorizontalOffset = (layoutRole, assemblyCtgId, scope = {}) => {
    const item = trackDragOffsetMap.get(buildTrackDragOffsetKey(layoutRole, assemblyCtgId, scope))
      || trackDragOffsetMap.get(buildTrackDragOffsetKey(layoutRole, assemblyCtgId));
    if (!item) {
      return 0;
    }
    if (isFiniteTrackMetric(item.offsetBp)) {
      return convertTrackOffsetBpToPx(item.offsetBp, {
        domainSpanBp: visualDomainSpanBp,
        innerWidth,
      });
    }
    return isFiniteTrackMetric(item.offsetPx) ? roundTrackMetric(item.offsetPx) : 0;
  };
  const applyTrackRectHorizontalOffset = (rect, offsetPx) => {
    if (!Number.isFinite(offsetPx) || Math.abs(offsetPx) < 0.01) {
      return rect;
    }
    const x = roundTrackMetric(rect.x + offsetPx);
    const centerX = roundTrackMetric((Number.isFinite(rect.centerX) ? rect.centerX : rect.x + rect.width / 2) + offsetPx);
    return {
      ...rect,
      x,
      centerX,
    };
  };
  const rawRefTrackMembers = Array.isArray(refTrackMembers)
    ? refTrackMembers
    : [];
  const resolvedRefTrackMembers = (rawRefTrackMembers.length
    ? rawRefTrackMembers
    : (() => {
        const fallbackLength = Math.max(1, resolvedChrLength ?? model.primary.domainSpanBp);
        return [{
          sourceKind: "ref_segment",
          name: `${refLabel}:1-${fallbackLength}`,
          segmentStartBp: 1,
          segmentEndBp: fallbackLength,
          anchorStart: 1,
          totalLength: fallbackLength,
          refOrient: "+",
          hits: [],
        }];
      })())
    .map((item, index) => {
      const segmentStartBp = Math.max(1, normalizePositiveInt(item?.segmentStartBp ?? item?.anchorStart) ?? 1);
      const segmentEndBp = Math.max(
        segmentStartBp,
        normalizePositiveInt(item?.segmentEndBp)
          ?? (segmentStartBp + Math.max(1, normalizePositiveInt(item?.totalLength) ?? 1) - 1),
      );
      return {
        ...item,
        assemblyCtgId: normalizeSupportDatasetId(item?.assemblyCtgId) ?? (2_100_000_000 + index + 1),
        segmentOrder: Number.isFinite(Number(item?.segmentOrder)) ? Number(item.segmentOrder) : index + 1,
        segmentStartBp,
        segmentEndBp,
        totalLength: Math.max(1, normalizePositiveInt(item?.totalLength) ?? (segmentEndBp - segmentStartBp + 1)),
        name: String(item?.name || "").trim() || `${refLabel}:${segmentStartBp}-${segmentEndBp}`,
        referenceChrName: String(item?.referenceChrName || selectedChrName || "").trim(),
        refOrient: resolveTrackCtgOrient(item),
      };
    })
    .sort((left, right) => {
      if (left.segmentStartBp !== right.segmentStartBp) {
        return left.segmentStartBp - right.segmentStartBp;
      }
      return left.segmentEndBp - right.segmentEndBp;
    });
  const refMemberLayoutCtgs = resolvedRefTrackMembers.map((member) => ({
    ...member,
    startBp: member.segmentStartBp,
    lengthBp: Math.max(1, member.segmentEndBp - member.segmentStartBp + 1),
    laneIndex: 0,
  }));
  const refMemberRects = buildTrackRectsWithMinGap(refMemberLayoutCtgs, {
    windowStart: visualWindowStart,
    domainSpanBp: visualDomainSpanBp,
    innerWidth,
    minGapPx: 15,
  });
  const refMemberRectByCtgId = new Map(
    refMemberLayoutCtgs.map((member, index) => [member.assemblyCtgId, refMemberRects[index]]),
  );
  const refMemberBlocks = resolvedRefTrackMembers
    .map((member) => {
      const rect = refMemberRectByCtgId.get(member.assemblyCtgId) || buildTrackHitRect({
        ctgStartBp: member.segmentStartBp,
        ctgEndBp: member.segmentEndBp,
        windowStart: visualWindowStart,
        domainSpanBp: visualDomainSpanBp,
        innerWidth,
      });
      const refLabelX = rect.x + 4;
      const refLabelY = refRowLayout.barY + TRACK_TEXT_OFFSET_Y;
      const slotToken = getSubviewSlotToken(subview, "ref", member.assemblyCtgId);
      const slotClass = slotToken ? " is-subview-selected" : "";
      return `
        <g
          class="track-ctg-group${slotClass}"
          data-track-contig-id="${member.assemblyCtgId}"
          data-track-role="ref"
          data-track-is-mirror="0"
          data-track-dataset-id="0"
          data-track-source-kind="${escapeAttr(String(member.sourceKind || "ref_segment"))}"
          data-track-reference-chr-name="${escapeAttr(String(member.referenceChrName || selectedChrName || ""))}"
          data-track-segment-start="${member.segmentStartBp}"
          data-track-segment-end="${member.segmentEndBp}"
          data-track-contig-name="${escapeAttr(member.name)}"
        >
          <rect
            class="track-reference-member${slotClass}"
            x="${rect.x.toFixed(2)}"
            y="${refRowLayout.barY.toFixed(2)}"
            width="${rect.width.toFixed(2)}"
            height="${TRACK_BAR_HEIGHT}"
            rx="${TRACK_HEIGHT_SCALE * 2}"
            ry="${TRACK_HEIGHT_SCALE * 2}"
            data-ref-member-name="${escapeAttr(member.name)}"
            data-ref-member-start-bp="${member.segmentStartBp}"
            data-ref-member-end-bp="${member.segmentEndBp}"
          >
            <title>${escapeHtml(member.name)} | start=${member.segmentStartBp} | end=${member.segmentEndBp}</title>
          </rect>
          <text
            class="track-ctg-label track-reference-member-label is-ref"
            x="${refLabelX.toFixed(2)}"
            y="${refLabelY.toFixed(2)}"
            text-anchor="start"
            data-track-label-for-contig-id="${member.assemblyCtgId}"
            data-track-label-role="ref"
            data-track-label-is-mirror="0"
          >${escapeHtml(
            `${member.name} (${member.refOrient})`,
          )}</text>
          ${
            slotToken
              ? `<text class="track-slot-badge" x="${(rect.x + rect.width - 8).toFixed(2)}" y="${(refRowLayout.barY + TRACK_TEXT_OFFSET_Y).toFixed(2)}">${escapeHtml(slotToken)}</text>`
              : ""
          }
        </g>
      `;
    })
    .join("");
  const resolveReferenceTrackHitRect = (refStartBp, refEndBp) => {
    const hitStartBp = Math.min(refStartBp, refEndBp);
    const hitEndBp = Math.max(refStartBp, refEndBp);
    const containingMember = resolvedRefTrackMembers.find((member) =>
      hitStartBp >= member.segmentStartBp && hitEndBp <= member.segmentEndBp,
    );
    if (containingMember) {
      const containingRect = refMemberRectByCtgId.get(containingMember.assemblyCtgId);
      if (containingRect) {
        return buildTrackHitRectWithinCtgDisplay({
          ctgRect: containingRect,
          ctgLengthBp: containingMember.totalLength,
          ctgStartOffset: hitStartBp - containingMember.segmentStartBp + 1,
          ctgEndOffset: hitEndBp - containingMember.segmentStartBp + 1,
        });
      }
    }
    return buildTrackHitRect({
      ctgStartBp: refStartBp,
      ctgEndBp: refEndBp,
      windowStart: visualWindowStart,
      domainSpanBp: visualDomainSpanBp,
      innerWidth,
    });
  };
  const supportRectByCtgId = buildBaseRectByCtgId(supportLayout);
  const resolveTrackCtgBaseRect = (layout, ctg, index) => {
    if (layout?.alignWithPrimary) {
      const primaryRect = primaryRectByCtgId.get(normalizeSupportDatasetId(ctg?.assemblyCtgId));
      if (primaryRect) {
        return primaryRect;
      }
    }
    if (layout?.isMirror && layout?.alignWithSupport) {
      const supportRect = supportRectByCtgId.get(normalizeSupportDatasetId(ctg?.assemblyCtgId));
      if (supportRect) {
        return supportRect;
      }
    }
    const rects = trackRectsByLayoutId.get(layout.id) || [];
    return rects[index] ?? buildTrackRect(ctg, {
      windowStart: visualWindowStart,
      domainSpanBp: visualDomainSpanBp,
      innerWidth,
    });
  };
  const resolveTrackCtgDisplayRect = (layout, ctg, index) =>
    applyTrackRectHorizontalOffset(
      resolveTrackCtgBaseRect(layout, ctg, index),
      resolveTrackCtgHorizontalOffset(layout.dragRole || layout.role, ctg.assemblyCtgId, {
        datasetId: layout.datasetId || ctg.datasetId,
        phasedTrackId: layout.phasedTrackId || ctg.phasedTrackId,
        phasedTrackItemId: ctg.phasedTrackItemId,
      }),
    );
  const maxRectRight = Math.max(
    innerWidth,
    ...rowLayouts
      .flatMap((layout) => layout.trackModel.ctgs.map((ctg, index) => ({ layout, ctg, index })))
      .map(({ layout, ctg, index }) => {
        const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
        return Number(rect.x) + Number(rect.width);
      })
      .filter((value) => Number.isFinite(value)),
  );
  const minRectLeft = Math.min(
    0,
    ...rowLayouts
      .flatMap((layout) => layout.trackModel.ctgs.map((ctg, index) => ({ layout, ctg, index })))
      .map(({ layout, ctg, index }) => {
        const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
        return Number(rect.x);
      })
      .filter((value) => Number.isFinite(value)),
  );
  const labelVisibleMinX = Math.floor(Math.min(0, minRectLeft));
  const labelVisibleMaxX = Math.ceil(Math.max(innerWidth, maxRectRight));
  const maxLabelRight = rowLayouts.reduce((layoutMax, layout) => {
    return layout.trackModel.ctgs.reduce((ctgMax, ctg, index) => {
      const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
      const barY = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT;
      const labelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
      const placement = resolveBoundedTrackCtgLabelPlacement({
        ctgName: labelText,
        role: layout.role,
        rect,
        barY,
        barHeight: TRACK_BAR_HEIGHT,
        inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
        outsideLabelAnchor: "bar-middle",
        hideOutsideLabel: true,
        minVisibleX: labelVisibleMinX,
        maxVisibleX: labelVisibleMaxX,
      });
      if (placement.hidden) {
        return ctgMax;
      }
      const labelRight = resolveTrackCtgLabelRightBoundary({
        x: placement.x,
        labelText,
        tiltAngleDeg: placement.tiltAngleDeg,
        textAnchor: placement.textAnchor,
      });
      return Math.max(ctgMax, labelRight);
    }, layoutMax);
  }, innerWidth);
  const minLabelLeft = rowLayouts.reduce((layoutMin, layout) => {
    return layout.trackModel.ctgs.reduce((ctgMin, ctg, index) => {
      const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
      const barY = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT;
      const labelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
      const placement = resolveBoundedTrackCtgLabelPlacement({
        ctgName: labelText,
        role: layout.role,
        rect,
        barY,
        barHeight: TRACK_BAR_HEIGHT,
        inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
        outsideLabelAnchor: "bar-middle",
        hideOutsideLabel: true,
        minVisibleX: labelVisibleMinX,
        maxVisibleX: labelVisibleMaxX,
      });
      if (placement.hidden) {
        return ctgMin;
      }
      const labelLeft = resolveTrackCtgLabelLeftBoundary({
        x: placement.x,
        labelText,
        tiltAngleDeg: placement.tiltAngleDeg,
        textAnchor: placement.textAnchor,
      });
      return Math.min(ctgMin, labelLeft);
    }, layoutMin);
  }, 0);
  const renderMinX = Math.floor(Math.min(0, minRectLeft, minLabelLeft));
  const renderMaxX = Math.ceil(Math.max(innerWidth, maxRectRight, maxLabelRight));
  const renderInnerWidth = Math.max(innerWidth, renderMaxX - renderMinX);
  const renderViewBoxMinX = renderMinX;
  const focusCtg = model.primary.ctgs.find((ctg) => ctg.isSelected) || model.primary.ctgs[0] || null;
  const primaryRects = trackRectsByLayoutId.get("primary") || [];
  const focusCtgIndex = focusCtg
    ? model.primary.ctgs.findIndex((ctg) => Number(ctg.assemblyCtgId) === Number(focusCtg.assemblyCtgId))
    : -1;
  const focusOffsetPx = focusCtg
    ? resolveTrackCtgHorizontalOffset("primary", focusCtg.assemblyCtgId)
    : 0;
  const focusRect = focusCtgIndex >= 0 && primaryRects[focusCtgIndex]
    ? applyTrackRectHorizontalOffset(primaryRects[focusCtgIndex], focusOffsetPx)
    : null;
  const fallbackFocusRect = focusCtg
    ? buildTrackRect(focusCtg, {
        windowStart: visualWindowStart,
        domainSpanBp: visualDomainSpanBp,
        innerWidth,
      })
    : null;
  const shiftedFallbackFocusRect = fallbackFocusRect
    ? applyTrackRectHorizontalOffset(fallbackFocusRect, focusOffsetPx)
    : null;
  const focusCenterX = focusCtg
    ? (focusRect
      ? focusRect.centerX
      : shiftedFallbackFocusRect?.centerX ?? 0)
    : 0;
  const focusStartX = focusCtg
    ? (focusRect
      ? focusRect.x
      : shiftedFallbackFocusRect?.x ?? 0)
    : 0;
  const focusCenterContentX = focusCenterX - renderViewBoxMinX;
  const focusStartContentX = focusStartX - renderViewBoxMinX;
  const refTrackX = buildTrackBpX({
    bp: 0,
    windowStart: visualWindowStart,
    domainSpanBp: visualDomainSpanBp,
    innerWidth,
  });
  const refTrackWidth = buildTrackReferenceWidth(resolvedChrLength, visualDomainSpanBp, innerWidth);
  const refWindowEnd = hasResolvedChrLength
    ? resolvedChrLength
    : visualWindowEnd;
  const rulerWindowEnd = Math.max(0, Math.min(visualWindowEnd, refWindowEnd));
  const tickItems = buildTrackTickItems({
    windowStart: visualWindowStart,
    windowEnd: rulerWindowEnd,
    tickBp,
    innerWidth,
    domainSpanBp: visualDomainSpanBp,
  });
  const tickRenderItems = tickItems.map((tick, index) => {
      const isFirst = index === 0;
      const isLast = index === tickItems.length - 1;
      const isSingle = isFirst && isLast;
      const labelAnchor = isSingle ? "middle" : isFirst ? "start" : isLast ? "end" : "middle";
      const labelX = isSingle
        ? tick.x
        : isFirst
          ? Math.min(innerWidth, tick.x + TRACK_EDGE_LABEL_PADDING)
          : isLast
            ? Math.max(0, tick.x - TRACK_EDGE_LABEL_PADDING)
            : tick.x;
      return {
        ...tick,
        labelAnchor,
        labelX,
        bp: tick.bp,
        labelText: isLast ? formatBp(tick.bp) : formatRulerTickLabel(tick.bp),
        hideLabel: false,
      };
    });

  if (tickRenderItems.length >= 2) {
    const endTick = tickRenderItems[tickRenderItems.length - 1];
    const previousTick = tickRenderItems[tickRenderItems.length - 2];
    if (isTrackTickLabelOverlap(previousTick, endTick)) {
      previousTick.hideLabel = true;
    }
  }

  const tickLines = tickRenderItems
    .map((tick) => `<g class="track-tick">
        <line class="track-tick-guide is-major" x1="${tick.x.toFixed(2)}" y1="${rulerTop + TRACK_LABEL_OFFSET_Y}" x2="${tick.x.toFixed(2)}" y2="${(contentBottom - 3 * TRACK_HEIGHT_SCALE).toFixed(2)}" />
        ${
          tick.hideLabel
            ? ""
            : `<text class="track-tick-label" x="${tick.labelX.toFixed(2)}" y="${rulerTop - TRACK_LABEL_OFFSET_Y}" text-anchor="${tick.labelAnchor}">${escapeHtml(
                tick.labelText,
              )}</text>`
        }
      </g>`)
    .join("");

  const hiddenPrimaryCtgIdSet = new Set(normalizeTrackSelectionCtgIds(hiddenPrimaryCtgIds));
  const resolveTrackCtgVerticalOffset = (layoutRole, assemblyCtgId) =>
    layoutRole === "primary" && hiddenPrimaryCtgIdSet.has(Number(assemblyCtgId)) ? -30 : 0;
  const grtResultEntries = rowLayouts
    .filter((layout) => layout.role === "primary" || layout.role === "support" || layout.isMirror)
    .flatMap((layout) => layout.trackModel.ctgs.map((ctg, index) => {
      if (layout.role === "primary" && hiddenPrimaryCtgIdSet.has(Number(ctg.assemblyCtgId))) {
        return null;
      }
      const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
      return {
        key: `${layout.id}:${ctg.assemblyCtgId}:${index}`,
        ctg: { ...ctg, orient: resolveTrackCtgOrient(ctg) },
        rect,
        y: layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT,
        height: TRACK_BAR_HEIGHT,
        isMirror: layout.isMirror === true,
      };
    }).filter(Boolean));
  const grtResultScene = grtResultContext?.available
    ? buildGrtResultScene({
      plan: grtResultPlan,
      entries: grtResultEntries,
      maskVisibleCtgs: true,
      escapeHtml,
      gapLabel: i18n.grtResult.gapLabel,
    })
    : { hasVisibleResult: false, overlaysByKey: new Map(), junctionMarkup: "" };

  const subviewTrackSelections = getSubviewTrackSelections(subview);
  const isSubviewTrackLabelSelected = (layout, trackLabelRole) => {
    if (!trackLabelRole) {
      return false;
    }
    const labelSource = layout?.isMirror ? "mirror" : "mother";
    const labelDatasetId = normalizeSupportDatasetId(layout?.datasetId);
    return subviewTrackSelections.some((selection) => {
      if (selection?.role !== trackLabelRole) {
        return false;
      }
      if (trackLabelRole === "phased") {
        const selectionPhasedTrackId = normalizeSupportDatasetId(selection?.phasedTrackId);
        const labelPhasedTrackId = normalizeSupportDatasetId(layout?.phasedTrackId);
        return selectionPhasedTrackId !== null && selectionPhasedTrackId === labelPhasedTrackId;
      }
      if (trackLabelRole !== "support") {
        return true;
      }
      const selectionDatasetId = normalizeSupportDatasetId(selection?.datasetId);
      if (selectionDatasetId !== null && selectionDatasetId !== labelDatasetId) {
        return false;
      }
      const selectionSource = selection?.isMirror === true
        ? "mirror"
        : normalizeSubviewTrackSource(selection?.source);
      return selectionSource === labelSource;
    });
  };
  const labelRows = [supportLayout, refRowLayout, ...rowLayouts.filter((layout) => layout.id !== "support")]
    .filter((layout) => Boolean(layout))
    .map((layout) => {
      const trackLabelRole = normalizeTrackRole(layout.interactiveRole || layout.role);
      const selectableTrackLabel = trackLabelRole && layout.selectable !== false;
      const isSelectedTrackLabel = selectableTrackLabel && isSubviewTrackLabelSelected(layout, trackLabelRole);
      const roleClass =
        `${layout.id === "ref" ? " is-ref" : layout.className ? ` ${layout.className}` : ""}`
        + `${selectableTrackLabel ? " is-track-selectable" : ""}`
        + `${isSelectedTrackLabel ? " is-subview-track-selected" : ""}`;
      const labelTop = Number.isFinite(layout.labelTop) ? layout.labelTop : layout.rowTop;
      const trackLabelDatasetId = normalizeSupportDatasetId(layout.datasetId);
      const trackLabelIsMirror = layout.isMirror ? "1" : "0";
      const trackLabelSource = layout.isMirror ? "mirror" : "mother";
      const phasedTrackId = normalizeSupportDatasetId(layout.phasedTrackId);
      const phasedHaplotypeKey = String(layout.phasedHaplotypeKey || "").trim();
      const phasedTrackAttrs = trackLabelRole === "phased"
        ? ` data-track-label-phased-track-id="${phasedTrackId || 0}" data-track-label-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey)}"`
        : "";
      const trackLabelAttrs = selectableTrackLabel
        ? ` data-track-label-role="${trackLabelRole}" data-track-label-selectable="1" data-track-label-source="${trackLabelSource}" data-track-label-is-mirror="${trackLabelIsMirror}" data-track-label-dataset-id="${trackLabelDatasetId || 0}"${phasedTrackAttrs}`
        : "";
      return `<div class="assembly-track-label-row${roleClass}" style="top:${labelTop}px"${trackLabelAttrs} title="${escapeAttr(layout.label)}">
        <span>${escapeHtml(layout.label)}</span>
      </div>`;
    })
    .join("");

  const collinearityBandItems = rowLayouts
    .flatMap((layout) => {
      if (!layout.includeBands) {
        return [];
      }
      if (!layout.trackModel.ctgs.length) {
        return [];
      }
      return layout.trackModel.ctgs.flatMap((ctg, ctgIndex) => {
        const isHiddenPrimaryCtg =
          layout.role === "primary" && hiddenPrimaryCtgIdSet.has(Number(ctg.assemblyCtgId));
        if (isHiddenPrimaryCtg) {
          return [];
        }
        const hits = resolveTrackRenderableHits(ctg);
        if (!hits.length) {
          return [];
        }
        const ctgDisplayRect = resolveTrackCtgDisplayRect(layout, ctg, ctgIndex);
        return hits.flatMap((hit) => {
          const hitBlockLength = normalizePositiveInt(hit?.blockLength ?? hit?.block_length) ?? 0;
          if (hitBlockLength < blockLength) {
            return [];
          }
          const hitMapq = resolveHitMapq(hit);
          if (hitMapq < minMapq) {
            return [];
          }
          const hitStartOffset = Number(hit?.ctgStart ?? hit?.ctg_start);
          const hitEndOffset = Number(hit?.ctgEnd ?? hit?.ctg_end);
          const refStartBp = Number(hit?.refStart ?? hit?.ref_start);
          const refEndBp = Number(hit?.refEnd ?? hit?.ref_end);
          if (
            !Number.isFinite(hitStartOffset) ||
            !Number.isFinite(hitEndOffset) ||
            !Number.isFinite(refStartBp) ||
            !Number.isFinite(refEndBp)
          ) {
            return [];
          }
          const ctgRect = buildTrackHitRectWithinCtgDisplay({
            ctgRect: ctgDisplayRect,
            ctgLengthBp: ctg.lengthBp,
            ctgStartOffset: hitStartOffset,
            ctgEndOffset: hitEndOffset,
          });
          const refRect = resolveReferenceTrackHitRect(refStartBp, refEndBp);
          const ctgVerticalOffset = resolveTrackCtgVerticalOffset(layout.role, ctg.assemblyCtgId);
          const ctgLaneTop = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT + ctgVerticalOffset;
          const bandPoints = buildCollinearityBandPoints({
            ctgRect,
            refRect,
            refLeftClamp: refTrackX,
            refRightClamp: refTrackX + refTrackWidth,
            refTop: refRowLayout.barY,
            refBottom: refRowLayout.barY + TRACK_BAR_HEIGHT,
            ctgTop: ctgLaneTop,
            ctgBottom: ctgLaneTop + TRACK_BAR_HEIGHT,
            direction: layout.connectorDirection,
            reversed: resolveTrackHitDisplayReversed(ctg, hit),
          });
          const trackRole = layout.interactiveRole || layout.role;
          const phasedTrackId = trackRole === "phased"
            ? normalizeSupportDatasetId(layout.phasedTrackId ?? ctg.phasedTrackId)
            : null;
          const phasedTrackItemId = trackRole === "phased"
            ? normalizeSupportDatasetId(ctg.phasedTrackItemId)
            : null;
          return {
            className: layout.className ? ` ${layout.className}` : "",
            tone: trackRole === "support" ? "companion" : "primary",
            trackRole,
            contigId: ctg.assemblyCtgId,
            phasedTrackId,
            phasedTrackItemId,
            phasedHaplotypeKey: trackRole === "phased"
              ? String(layout.phasedHaplotypeKey || ctg.phasedHaplotypeKey || "").trim()
              : "",
            points: bandPoints,
          };
        });
      });
    })
    .filter(Boolean);
  const collinearityBands = collinearityBandItems
    .map((band) => {
      const phasedBandAttrs = band.trackRole === "phased"
        ? ` data-band-phased-track-id="${band.phasedTrackId || 0}" data-band-phased-track-item-id="${band.phasedTrackItemId || 0}" data-band-phased-haplotype-key="${escapeAttr(band.phasedHaplotypeKey || "")}"`
        : "";
      return `<polygon class="track-collinearity-band${band.className}" data-band-track-role="${escapeAttr(
          band.trackRole,
        )}" data-band-contig-id="${band.contigId}"${phasedBandAttrs} data-track-band-proxy="1" points="${band.points}" />`;
    })
    .join("");

  const rowBlocks = rowLayouts
    .map((layout) => {
      const rowBgClass = layout.className ? ` ${layout.className}` : "";
      if (!layout.trackModel.ctgs.length) {
        return `<text class="track-row-empty-label" x="12" y="${(layout.laneTop + TRACK_TEXT_OFFSET_Y).toFixed(2)}">${escapeHtml(
            layout.emptyMessage,
          )}</text>`;
      }
      const selectedTrackCtgIds = new Set(normalizeTrackSelectionCtgIds(selectionCtgIds));
      const renderEntries = layout.trackModel.ctgs
        .map((ctg, index) => {
          const rect = resolveTrackCtgDisplayRect(layout, ctg, index);
          const ctgVerticalOffset = resolveTrackCtgVerticalOffset(layout.role, ctg.assemblyCtgId);
          const y = layout.laneTop + ctg.laneIndex * TRACK_LANE_HEIGHT + ctgVerticalOffset;
          const baseLabelText = resolveTrackCtgLabelText(ctg, ctg.assemblyCtgId);
          const grtPlacementMode = String(ctg?.grtPlacementMode || "").trim();
          const labelText = grtPlacementMode && grtPlacementMode !== "normal"
            ? `${baseLabelText} [${grtPlacementMode}]`
            : baseLabelText;
          const labelPlacement = resolveBoundedTrackCtgLabelPlacement({
            ctgName: labelText,
            role: layout.interactiveRole || layout.role,
            rect,
            barY: y,
            barHeight: TRACK_BAR_HEIGHT,
            inlineTextOffsetY: TRACK_TEXT_OFFSET_Y,
            outsideLabelAnchor: "bar-middle",
            hideOutsideLabel: true,
            minVisibleX: labelVisibleMinX,
            maxVisibleX: labelVisibleMaxX,
          });
          const slotToken = getSubviewSlotToken(
            subview,
            layout.interactiveRole || layout.role,
            ctg.assemblyCtgId,
          );
          const activeClass = ctg.isSelected ? " is-active" : "";
          const slotClass = slotToken ? " is-subview-selected" : "";
          const multiSelectedClass = selectedTrackCtgIds.has(Number(ctg.assemblyCtgId)) ? " is-multi-selected" : "";
          const hiddenClass = ctgVerticalOffset < 0 ? " is-hidden-contig" : "";
          const mirrorClass = layout.isMirror ? " is-mirror" : "";
          const historyHighlightClass = layout.role === "primary"
            && Number(historyHighlightCtgId) === Number(ctg.assemblyCtgId)
            ? " is-history-highlighted"
            : "";
          const groupClass = `track-ctg-group${activeClass}${slotClass}${multiSelectedClass}${hiddenClass}${mirrorClass}${rowBgClass}${historyHighlightClass}`;
          const rectMetricsAttrs = `data-track-rect-x="${rect.x.toFixed(2)}" data-track-rect-y="${y.toFixed(2)}" data-track-rect-width="${rect.width.toFixed(2)}" data-track-rect-height="${TRACK_BAR_HEIGHT}"`;
          const phasedTrackId = normalizeSupportDatasetId(layout.phasedTrackId);
          const phasedTrackItemId = normalizeSupportDatasetId(ctg.phasedTrackItemId);
          const phasedHaplotypeKey = String(layout.phasedHaplotypeKey || ctg.phasedHaplotypeKey || "").trim();
          const phasedAttrs = (layout.interactiveRole || layout.role) === "phased"
            ? ` data-track-phased-track-id="${phasedTrackId || 0}" data-track-phased-track-item-id="${phasedTrackItemId || 0}" data-track-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey)}"`
            : "";
          const phasedLabelAttrs = (layout.interactiveRole || layout.role) === "phased"
            ? ` data-track-label-phased-track-id="${phasedTrackId || 0}" data-track-label-phased-track-item-id="${phasedTrackItemId || 0}" data-track-label-phased-haplotype-key="${escapeAttr(phasedHaplotypeKey)}"`
            : "";
          const groupAttrs = layout.selectable
            ? `data-track-contig-id="${ctg.assemblyCtgId}" data-track-role="${layout.interactiveRole || layout.role}" data-track-contig-name="${escapeAttr(ctg.name)}" data-track-is-mirror="${layout.isMirror ? "1" : "0"}" data-track-dataset-id="${Number(layout.datasetId || 0)}" data-track-ref-orient="${escapeAttr(resolveTrackCtgOrient(ctg))}"${phasedAttrs} ${rectMetricsAttrs}`
            : "";
          const labelAttrs = layout.selectable
            ? ` data-track-label-for-contig-id="${ctg.assemblyCtgId}" data-track-label-role="${escapeAttr(layout.interactiveRole || layout.role)}" data-track-label-is-mirror="${layout.isMirror ? "1" : "0"}"${phasedLabelAttrs}`
            : "";
          const sourceTagMarkup = renderDerivedSourceSvgTag(ctg);
          const labelMarkup = labelPlacement.hidden
            ? ""
            : `<text class="track-ctg-label${mirrorClass}${rowBgClass}${labelPlacement.classSuffix}" x="${labelPlacement.x.toFixed(2)}" y="${labelPlacement.y.toFixed(2)}"${labelPlacement.transformAttr} text-anchor="${labelPlacement.textAnchor}"${labelAttrs}>${escapeHtml(
              labelText,
            )}${sourceTagMarkup}</text>`;
          const telomereMarkerMarkup = renderTelomereMarkersForTrackCtg({
            ctg,
            rect,
            y,
            barHeight: TRACK_BAR_HEIGHT,
            role: layout.interactiveRole || layout.role,
            isMirror: layout.isMirror,
          });
          const centromereMarkerMarkup = renderCentromereMarkersForTrackCtg({
            ctg,
            rect,
            y,
            barHeight: TRACK_BAR_HEIGHT,
            role: layout.interactiveRole || layout.role,
            isMirror: layout.isMirror,
          });
          const nRegionMarkerMarkup = renderNRegionMarkersForTrackCtg({
            ctg,
            rect,
            y,
            barHeight: TRACK_BAR_HEIGHT,
            role: layout.interactiveRole || layout.role,
            isMirror: layout.isMirror,
          });
          const grtOverlayKey = `${layout.id}:${ctg.assemblyCtgId}:${index}`;
          const grtOverlayMarkup = grtResultContext?.mainEnabled
            ? grtResultScene.overlaysByKey.get(grtOverlayKey) || ""
            : "";
          return {
            ctg,
            rect,
            markup: `<g class="${groupClass}" ${groupAttrs} data-grt-result-entry-key="${escapeAttr(grtOverlayKey)}">
            <rect
              class="track-ctg${activeClass}${slotClass}${multiSelectedClass}${hiddenClass}${mirrorClass}${rowBgClass}"
              data-track-focus="${ctg.isSelected ? "true" : "false"}"
              x="${rect.x.toFixed(2)}"
              y="${y.toFixed(2)}"
              width="${rect.width.toFixed(2)}"
              height="${TRACK_BAR_HEIGHT}"
              rx="${TRACK_HEIGHT_SCALE * 2}"
              ry="${TRACK_HEIGHT_SCALE * 2}"
            >
              <title>${escapeHtml(ctg.name)} | start=${ctg.startBp} | len=${ctg.lengthBp}</title>
            </rect>
            ${grtOverlayMarkup}
            ${telomereMarkerMarkup}
            ${centromereMarkerMarkup}
            ${nRegionMarkerMarkup}
            ${labelMarkup}
            ${
              slotToken
                ? `<text class="track-slot-badge" x="${(rect.x + rect.width - 8).toFixed(2)}" y="${(y + TRACK_TEXT_OFFSET_Y).toFixed(2)}">${escapeHtml(slotToken)}</text>`
                : ""
            }
          </g>`,
          };
        })
        .filter((entry) => entry && entry.markup);
      const blocks = sortTrackEntriesForRender(renderEntries)
        .map((entry) => entry.markup)
        .join("");
      return blocks;
    })
    .join("");

  const refBaseBar = resolvedRefTrackMembers.length <= 1
    ? `
    <rect
      class="track-reference-bar"
      x="${refTrackX.toFixed(2)}"
      y="${refRowLayout.barY.toFixed(2)}"
      width="${refTrackWidth.toFixed(2)}"
      height="${TRACK_BAR_HEIGHT}"
      rx="0"
      ry="0"
      data-ref-span-bp="${resolvedChrLength ?? model.primary.domainSpanBp}"
    ></rect>`
    : "";
  const refRow = `
    ${refBaseBar}
    ${refMemberBlocks}
  `;

  const inlineControls = renderAssemblyTrackInlineControls({
    trackPrefs,
    supportDsCtgLenRules,
    chrLength,
    supportDatasetOptions,
    supportDatasetId,
    selectedChrName,
    mainViewHistory,
    i18n,
  });
  const createPhasedTrackButton = renderCreatePhasedTrackButton({
    phasedAssemblyEnabled,
    phasedTrackCount: phasedChrTracks.length,
    i18n,
  });
  const grtResultSwitch = grtResultContext?.available
    ? `<label class="grt-result-switch">
        <input type="checkbox" data-grt-result-toggle="main" ${grtResultContext.mainEnabled ? "checked" : ""} />
        <span>${escapeHtml(i18n.grtResult.showResult)}</span>
      </label>`
    : "";
  const grtResultToastMarkup = grtResultToast?.scope === "main"
    && grtResultToast?.chrName === selectedChrName
    ? `<div class="grt-result-toast" role="status">${escapeHtml(i18n.grtResult.noMainIntervals)}</div>`
    : "";
  const supportDsCtgLenRulesDialog = supportDsCtgLenRulesDialogOpen
    ? renderSupportDsCtgLenRulesDialog({
      rules: supportDsCtgLenRules,
      chrLength: resolvedChrLength,
      supportDsCtgLen: trackPrefs.supportDsCtgLen,
      i18n,
    })
    : "";
  return `
    <div class="assembly-track-unified assembly-track-panel">
      <div class="assembly-track-panel-head" data-main-track-control-layout="auto" data-grt-result-card="main" data-grt-result-scene-visible="${grtResultScene.hasVisibleResult ? "1" : "0"}">
        <strong data-main-track-control-title>${escapeHtml(i18n.page.primaryAlignmentViewSingleCardTitle)}</strong>
        <div class="assembly-track-panel-actions" data-main-track-control-actions>
          <div class="assembly-track-panel-quick-actions" data-main-track-quick-actions>${grtResultSwitch}${createPhasedTrackButton}</div>
          ${inlineControls}
        </div>
      </div>
      ${grtResultToastMarkup}
      <div class="assembly-track-layout">
        <div class="assembly-track-label-column" style="width:${LABEL_COLUMN_WIDTH_PX}px;height:${contentBottom}px">
          ${labelRows}
        </div>
        <div
          class="assembly-track-scroll"
          data-track-role="primary"
          data-focus-center="${focusCenterContentX}"
          data-focus-start="${focusStartContentX}"
          data-track-window-start-bp="${visualWindowStart}"
          data-track-domain-span-bp="${visualDomainSpanBp}"
          data-track-inner-width="${innerWidth}"
          data-track-viewbox-min-x="${renderViewBoxMinX}"
        >
          ${renderTrackBandCanvasLayer({
            sceneKind: "main-track",
            width: renderInnerWidth,
            height: contentBottom,
            viewBoxMinX: renderViewBoxMinX,
            bands: collinearityBandItems,
          })}
          <svg class="assembly-track-svg" data-track-band-svg-overlay="1" width="${renderInnerWidth}" height="${contentBottom}" viewBox="${renderViewBoxMinX} 0 ${renderInnerWidth} ${contentBottom}" preserveAspectRatio="xMinYMin meet">
            <line class="track-ruler-line" x1="${refTrackX.toFixed(2)}" y1="${rulerTop}" x2="${(refTrackX + refTrackWidth).toFixed(2)}" y2="${rulerTop}" />
            ${tickLines}
            ${collinearityBands}
            ${grtResultContext?.mainEnabled ? grtResultScene.junctionMarkup : ""}
            ${rowBlocks}
            ${refRow}
          </svg>
        </div>
      </div>
      ${supportDsCtgLenRulesDialog}
    </div>
  `;
}

function renderSupportDsCtgLenRulesDialog({ rules = [], chrLength = null, supportDsCtgLen = 0, i18n }) {
  const resolvedChrLength = normalizePositiveInt(chrLength) ?? 1;
  const rows = normalizeSupportRulesForDialog(rules, {
    chrLength: resolvedChrLength,
    supportDsCtgLen,
  });
  const labels = i18n.trackControls;
  const rowHtml = rows.map((rule, index) => renderSupportDsCtgLenRulesDialogRow(rule, index, labels)).join("");
  const baseline = JSON.stringify(rows.map((rule) => ({
    startMb: formatRuleMbValue(rule.startBp <= 1 ? 0 : rule.startBp / 1_000_000),
    endMb: formatRuleMbValue(rule.endBp / 1_000_000),
    supportDsCtgLen: String(rule.supportDsCtgLen),
  })));
  return `
    <div class="modal-overlay assembly-support-ds-len-rules-overlay" data-support-ds-ctg-len-rules-overlay="1">
      <article
        class="card modal-dialog assembly-support-ds-len-rules-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="${escapeAttr(labels.supportDatasetLengthRulesTitle)}"
        data-support-ds-ctg-len-rules-dialog="1"
        data-support-ds-ctg-len-rules-chr-length="${resolvedChrLength}"
        data-support-ds-ctg-len-rules-delete-label="${escapeAttr(labels.supportDatasetLengthRulesDelete)}"
        data-support-ds-ctg-len-rules-baseline="${escapeAttr(baseline)}"
        data-support-ds-ctg-len-rules-unsaved-message="${escapeAttr(labels.supportDatasetLengthRulesUnsavedClose)}"
      >
        <div class="assembly-support-ds-len-rules-head">
          <h4>${escapeHtml(labels.supportDatasetLengthRulesTitle)}</h4>
          <button
            type="button"
            class="button ghost tiny assembly-support-ds-len-rules-close"
            data-support-ds-ctg-len-rules-close="1"
            aria-label="${escapeAttr(labels.supportDatasetLengthRulesClose)}"
            title="${escapeAttr(labels.supportDatasetLengthRulesClose)}"
          >X</button>
        </div>
        <div class="assembly-support-ds-len-rules-body">
          <table class="records-table assembly-support-ds-len-rules-table">
            <thead>
              <tr>
                <th>${escapeHtml(labels.supportDatasetLengthRulesStartMb)}</th>
                <th>${escapeHtml(labels.supportDatasetLengthRulesEndMb)}</th>
                <th>${escapeHtml(labels.supportDatasetLengthRulesLenBp)}</th>
                <th>${escapeHtml(labels.supportDatasetLengthRulesDelete)}</th>
              </tr>
            </thead>
            <tbody data-support-ds-ctg-len-rules-body="1">${rowHtml}</tbody>
          </table>
        </div>
        <div class="assembly-support-ds-len-rules-foot">
          <button type="button" class="button ghost tiny" data-support-ds-ctg-len-rules-add="1">${escapeHtml(labels.supportDatasetLengthRulesAdd)}</button>
          <div class="assembly-support-ds-len-rules-actions">
            <button type="button" class="button ghost tiny" data-support-ds-ctg-len-rules-reset="1">${escapeHtml(labels.supportDatasetLengthRulesReset)}</button>
            <button type="button" class="button primary tiny" data-support-ds-ctg-len-rules-save="1">${escapeHtml(labels.supportDatasetLengthRulesSave)}</button>
          </div>
        </div>
      </article>
    </div>
  `;
}

function renderSupportDsCtgLenRulesDialogRow(rule, index, labels) {
  return `
    <tr data-support-ds-ctg-len-rules-row="1">
      <td><input type="number" step="0.001" min="0" value="${escapeAttr(formatRuleMbValue(rule.startBp <= 1 ? 0 : rule.startBp / 1_000_000))}" data-support-ds-rule-field="startMb" aria-label="${escapeAttr(labels.supportDatasetLengthRulesStartMb)}"></td>
      <td><input type="number" step="0.001" min="0" value="${escapeAttr(formatRuleMbValue(rule.endBp / 1_000_000))}" data-support-ds-rule-field="endMb" aria-label="${escapeAttr(labels.supportDatasetLengthRulesEndMb)}"></td>
      <td><input type="text" inputmode="numeric" pattern="[0-9]*" value="${escapeAttr(String(rule.supportDsCtgLen))}" data-support-ds-rule-field="supportDsCtgLen" aria-label="${escapeAttr(labels.supportDatasetLengthRulesLenBp)}"></td>
      <td><button type="button" class="button ghost tiny" data-support-ds-ctg-len-rules-delete="1" aria-label="${escapeAttr(labels.supportDatasetLengthRulesDelete)} ${index + 1}">${escapeHtml(labels.supportDatasetLengthRulesDelete)}</button></td>
    </tr>
  `;
}

function normalizeSupportRulesForDialog(rules, { chrLength, supportDsCtgLen }) {
  const normalized = getSupportDsCtgLenRulesForChr({ current: rules }, "current", { chrLength });
  if (normalized.length) {
    return normalized;
  }
  return [{
    startBp: 1,
    endBp: normalizePositiveInt(chrLength) ?? 1,
    supportDsCtgLen: normalizeNonNegativeInt(supportDsCtgLen) ?? 0,
  }];
}

function formatRuleMbValue(value) {
  const normalized = Number(value);
  if (!Number.isFinite(normalized)) {
    return "0";
  }
  return normalized.toFixed(6).replace(/\.?0+$/, "");
}


  return {
    renderAssemblyMainTab,
    renderAssemblyStatusToast,
    renderAssemblySubviewPanel,
  };
}

export function renderAssemblyFinalPathCard(state, deps = {}) {
  return renderAssemblyFinalPathCardImpl(state, deps);
}

export function renderAssemblyMainTab(state, deps = {}) {
  return createRenderTracksRenderer(deps).renderAssemblyMainTab(state);
}

export function renderAssemblyMainTrackSections(state, deps = {}) {
  return createRenderTracksRenderer(deps).renderAssemblyMainTab(state, {
    includeFinalPath: false,
    includeSubview: false,
  });
}

export function renderAssemblySubviewPanel(state, deps = {}) {
  return createRenderTracksRenderer(deps).renderAssemblySubviewPanel(state);
}

export function renderAssemblyStatusToast(state, deps = {}) {
  return createRenderTracksRenderer(deps).renderAssemblyStatusToast(state?.assembly);
}

function isFiniteTrackMetric(value) {
  return Number.isFinite(Number(value));
}

function resolveTrackBpPerPixel({ domainSpanBp, innerWidth } = {}) {
  const domain = Number(domainSpanBp);
  const width = Number(innerWidth);
  if (!Number.isFinite(domain) || !Number.isFinite(width) || domain <= 0 || width <= 0) {
    return 0;
  }
  return domain / width;
}

export function convertTrackOffsetPxToBp(offsetPx, scaleContext) {
  const offset = Number(offsetPx);
  const bpPerPixel = resolveTrackBpPerPixel(scaleContext);
  if (!Number.isFinite(offset) || bpPerPixel <= 0) {
    return 0;
  }
  return roundTrackMetric(offset * bpPerPixel);
}

function convertTrackOffsetBpToPx(offsetBp, scaleContext) {
  const offset = Number(offsetBp);
  const bpPerPixel = resolveTrackBpPerPixel(scaleContext);
  if (!Number.isFinite(offset) || bpPerPixel <= 0) {
    return 0;
  }
  return roundTrackMetric(offset / bpPerPixel);
}

function buildSupportMirroredCtgsForRender({
  supportMirroredCtgs,
  selectedChrName,
  supportDatasetId,
  supportDatasetName,
  supportModelCtgs,
  supportDatasetOptions,
}) {
  const currentDatasetId = normalizeSupportDatasetId(supportDatasetId);
  const currentDatasetName = String(supportDatasetName || "");
  const selectedChr = String(selectedChrName || "").trim();
  const liveSupportById = new Map(
    (Array.isArray(supportModelCtgs) ? supportModelCtgs : []).map((ctg) => [
      normalizeSupportDatasetId(ctg?.assemblyCtgId),
      ctg,
    ]),
  );
  return normalizeSupportMirroredCtgs(supportMirroredCtgs)
    .filter((entry) => !selectedChr || !entry.chrName || entry.chrName === selectedChr)
    .map((entry) => {
      const optionLabel = (Array.isArray(supportDatasetOptions) ? supportDatasetOptions : []).find(
        (item) => normalizeSupportDatasetId(item?.datasetId) === entry.datasetId,
      )?.label || "";
      const fallbackDatasetName = currentDatasetId === entry.datasetId ? currentDatasetName : optionLabel;
      const liveCtg = currentDatasetId === entry.datasetId
        ? liveSupportById.get(entry.assemblyCtgId) || null
        : null;
      if (!liveCtg) {
        return {
          ...entry,
          datasetName: entry.datasetName || fallbackDatasetName || `ds-${entry.datasetId}`,
          hits: Array.isArray(entry?.hits) ? entry.hits.map((hit) => ({ ...hit })) : [],
        };
      }
      const liveLength = Math.max(
        1,
        normalizePositiveInt(liveCtg?.lengthBp ?? liveCtg?.totalLength ?? entry.lengthBp) ?? entry.lengthBp,
      );
      const liveStart = Math.max(0, normalizeNonNegativeInt(liveCtg?.startBp ?? entry.startBp) ?? entry.startBp);
      return {
        ...entry,
        datasetName: entry.datasetName || fallbackDatasetName || `ds-${entry.datasetId}`,
        name: String(liveCtg?.name || entry.name || `Ctg${entry.assemblyCtgId}`),
        totalLength: Math.max(
          1,
          normalizePositiveInt(liveCtg?.totalLength ?? liveCtg?.lengthBp ?? entry.totalLength) ?? entry.totalLength,
        ),
        anchorStart: normalizeNonNegativeInt(liveCtg?.anchorStart ?? entry.anchorStart),
        lengthBp: liveLength,
        startBp: liveStart,
        endBp: Math.max(
          1,
          normalizePositiveInt(liveCtg?.endBp) ?? (liveStart + liveLength - 1),
        ),
        laneIndex: Math.max(0, normalizeNonNegativeInt(liveCtg?.laneIndex ?? entry.laneIndex) ?? entry.laneIndex),
        orient: resolveTrackCtgOrientValue(liveCtg),
        hits: Array.isArray(liveCtg?.hits)
          ? liveCtg.hits.map((hit) => ({ ...hit }))
        : (Array.isArray(entry?.hits) ? entry.hits.map((hit) => ({ ...hit })) : []),
      };
  });
}

function buildPhasedTrackItemHits(sourceCtg, totalLength, itemOrient) {
  return buildPhasedSubviewCtgHits({ sourceCtg, totalLength, itemOrient });
}

function buildPhasedTrackRows({ phasedChrTracks = [], primaryModel, activeHitsTrackKey = "primary", i18n }) {
  const primaryCtgs = Array.isArray(primaryModel?.ctgs) ? primaryModel.ctgs : [];
  const primaryById = new Map(
    primaryCtgs
      .map((ctg) => [normalizeSupportDatasetId(ctg?.assemblyCtgId), ctg])
      .filter(([ctgId]) => ctgId !== null),
  );
  return (Array.isArray(phasedChrTracks) ? phasedChrTracks : [])
    .map((track) => {
      const haplotypeKey = String(track?.haplotypeKey || "").trim();
      const label = String(track?.label || "").trim();
      if (!haplotypeKey) {
        return null;
      }
      const ctgs = (Array.isArray(track?.items) ? track.items : [])
        .map((item, index) => {
          const assemblyCtgId = normalizeSupportDatasetId(item?.assemblyCtgId);
          const sourceCtg = primaryById.get(assemblyCtgId) || item?.sourceCtg || null;
          if (!sourceCtg || assemblyCtgId === null) {
            return null;
          }
          const totalLength = Math.max(
            1,
            normalizePositiveInt(sourceCtg.totalLength ?? sourceCtg.lengthBp) ?? 1,
          );
          const startBp = Math.max(
            0,
            normalizeNonNegativeInt(sourceCtg.startBp ?? sourceCtg.anchorStart) ?? 0,
          );
          const rawItemOrient = String(item?.orient || "").trim();
          const itemOrient = rawItemOrient === "-" || rawItemOrient === "+"
            ? rawItemOrient
            : resolveTrackCtgOrientValue(sourceCtg);
          return {
            ...sourceCtg,
            assemblyCtgId,
            orient: itemOrient,
            refOrient: itemOrient,
            ref_orient: itemOrient,
            phasedTrackId: Number(track?.phasedTrackId || 0),
            phasedTrackItemId: Number(item?.itemId || item?.phasedTrackItemId || 0),
            phasedHaplotypeKey: haplotypeKey,
            phasedInstanceKey: `${track?.phasedTrackId || haplotypeKey}:${item?.itemId || index}`,
            startBp,
            lengthBp: totalLength,
            totalLength,
            endBp: Math.max(1, startBp + totalLength - 1),
            laneIndex: 0,
            hits: buildPhasedTrackItemHits(sourceCtg, totalLength, itemOrient),
            isSelected: false,
          };
        })
        .filter(Boolean);
      const trackLabel = i18n.trackControls.phasedTrackLabel.replace(
        "{key}",
        label || haplotypeKey,
      );
      return {
        id: `phased-${haplotypeKey}`,
        role: "phased",
        interactiveRole: "phased",
        dragRole: "phased",
        label: trackLabel,
        trackModel: {
          ...(primaryModel || buildEmptyTrackModelLike()),
          ctgs,
          laneCount: 1,
        },
        selectable: true,
        emptyMessage: i18n.trackControls.phasedTrackEmpty,
        className: "is-phased-track",
        connectorDirection: "up",
        includeBands: String(activeHitsTrackKey) === haplotypeKey,
        datasetId: null,
        alignWithPrimary: true,
        phasedTrackId: Number(track?.phasedTrackId || 0),
        phasedHaplotypeKey: haplotypeKey,
      };
    })
    .filter(Boolean);
}

function buildSupportMirrorTrackRows(supportMirroredCtgs, i18n) {
  const grouped = new Map();
  normalizeSupportMirroredCtgs(supportMirroredCtgs).forEach((entry) => {
    const bucket = grouped.get(entry.datasetId) || [];
    bucket.push(entry);
    grouped.set(entry.datasetId, bucket);
  });
  return Array.from(grouped.entries())
    .map(([datasetId, ctgs]) => {
      const normalizedCtgs = ctgs
        .slice()
        .sort((left, right) => {
          if (left.startBp !== right.startBp) {
            return left.startBp - right.startBp;
          }
          if (left.lengthBp !== right.lengthBp) {
            return right.lengthBp - left.lengthBp;
          }
          return left.assemblyCtgId - right.assemblyCtgId;
        })
        .map((ctg) => ({
          ...ctg,
          laneIndex: Math.max(0, normalizeNonNegativeInt(ctg.laneIndex) ?? 0),
          lengthBp: Math.max(1, normalizePositiveInt(ctg.lengthBp ?? ctg.totalLength) ?? 1),
          startBp: Math.max(0, normalizeNonNegativeInt(ctg.startBp) ?? 0),
          endBp: Math.max(
            1,
            normalizePositiveInt(ctg.endBp)
              ?? (Math.max(0, normalizeNonNegativeInt(ctg.startBp) ?? 0)
                + Math.max(1, normalizePositiveInt(ctg.lengthBp ?? ctg.totalLength) ?? 1)
                - 1),
          ),
          hits: Array.isArray(ctg?.hits) ? ctg.hits.map((hit) => ({ ...hit })) : [],
          isSelected: false,
        }));
      const laneCount = normalizedCtgs.length
        ? Math.max(...normalizedCtgs.map((ctg) => Math.max(0, Number(ctg.laneIndex || 0)))) + 1
        : 1;
      const datasetName = String(
        ctgs.find((item) => String(item.datasetName || "").trim())?.datasetName
          || `ds-${datasetId}`,
      );
      return {
        id: `support-mirror-${datasetId}`,
        role: "support",
        interactiveRole: "support",
        dragRole: "support",
        label: i18n.trackControls.mirrorTrackLabelWithName.replace("{name}", datasetName),
        trackModel: {
          ...buildEmptyTrackModelLike(),
          ctgs: normalizedCtgs,
          laneCount,
        },
        selectable: true,
        emptyMessage: i18n.trackControls.mirrorTrackEmpty,
        className: "is-companion is-mirror-track",
        connectorDirection: "down",
        includeBands: false,
        datasetId,
        isMirror: true,
      };
    });
}

function resolveTrackDragOffsetPx(offsets, trackRole, assemblyCtgId, scaleContext = {}) {
  const targetKey = buildTrackDragOffsetKey(trackRole, assemblyCtgId, scaleContext);
  const legacyKey = buildTrackDragOffsetKey(trackRole, assemblyCtgId);
  const item = normalizeTrackDragOffsets(offsets).find(
    (entry) => {
      const entryKey = buildTrackDragOffsetKey(entry.trackRole, entry.assemblyCtgId, entry);
      return entryKey === targetKey || entryKey === legacyKey;
    },
  );
  if (!item) {
    return 0;
  }
  if (Number.isFinite(Number(item.offsetBp))) {
    return convertTrackOffsetBpToPx(item.offsetBp, scaleContext);
  }
  return Number.isFinite(Number(item.offsetPx)) ? Math.round(Number(item.offsetPx) * 100) / 100 : 0;
}

export function resolveTrackDragOffsetBp(offsets, trackRole, assemblyCtgId, scaleContext = {}) {
  const targetKey = buildTrackDragOffsetKey(trackRole, assemblyCtgId, scaleContext);
  const legacyKey = buildTrackDragOffsetKey(trackRole, assemblyCtgId);
  const item = normalizeTrackDragOffsets(offsets).find(
    (entry) => {
      const entryKey = buildTrackDragOffsetKey(entry.trackRole, entry.assemblyCtgId, entry);
      return entryKey === targetKey || entryKey === legacyKey;
    },
  );
  if (!item) {
    return 0;
  }
  if (Number.isFinite(Number(item.offsetBp))) {
    return Math.round(Number(item.offsetBp) * 100) / 100;
  }
  if (Number.isFinite(Number(item.offsetPx))) {
    return convertTrackOffsetPxToBp(item.offsetPx, scaleContext);
  }
  return 0;
}

function resolveSubviewTrackDragOffsetPx(offsets, slot, contigId, scaleContext = {}) {
  const targetKey = buildSubviewTrackDragOffsetKey(slot, contigId);
  const item = normalizeSubviewTrackDragOffsets(offsets).find(
    (entry) => buildSubviewTrackDragOffsetKey(entry.slot, entry.contigId) === targetKey,
  );
  if (!item) {
    return 0;
  }
  if (Number.isFinite(Number(item.offsetBp))) {
    return convertTrackOffsetBpToPx(item.offsetBp, scaleContext);
  }
  return Number.isFinite(Number(item.offsetPx)) ? Math.round(Number(item.offsetPx) * 100) / 100 : 0;
}

export function resolveSubviewTrackDragOffsetBp(offsets, slot, contigId, scaleContext = {}) {
  const targetKey = buildSubviewTrackDragOffsetKey(slot, contigId);
  const item = normalizeSubviewTrackDragOffsets(offsets).find(
    (entry) => buildSubviewTrackDragOffsetKey(entry.slot, entry.contigId) === targetKey,
  );
  if (!item) {
    return 0;
  }
  if (Number.isFinite(Number(item.offsetBp))) {
    return Math.round(Number(item.offsetBp) * 100) / 100;
  }
  if (Number.isFinite(Number(item.offsetPx))) {
    return convertTrackOffsetPxToBp(item.offsetPx, scaleContext);
  }
  return 0;
}
