import { normalizeNonNegativeInt, normalizePositiveInt, resolveTrackPrefs } from "./track-prefs.js";
import { normalizeDeletedCtgRecordIds, normalizeSupportDatasetId } from "./selection-state.js";
import {
  isSingleFullChrSupportDsCtgLenRule,
  normalizeSupportDsCtgLenRules,
  normalizeSupportDsCtgLenRulesByChr,
} from "./support-ds-ctg-len-rules.js";
import { bindFinalPathCardDrag } from "./final-path-card-drag-runtime.js";
import { bindFinalPathExport } from "./final-path-export-runtime.js";
import { bindFinalPathGraphDrag } from "./final-path-graph-drag-runtime.js";
import { normalizeFinalPathViewMode } from "./final-path-state.js";
import {
  buildFinalPathTrackViewportKey,
  normalizeViewportScrollState,
} from "./scroll-position-state.js";
import { shouldRefetchSubviewPairwiseEvidence } from "./subview-pairwise-evidence-state.js";

const ASSEMBLY_TRACK_COMBO_BOUND = Symbol("assemblyTrackComboBound");
const ASSEMBLY_DROPDOWN_CLOSE_DELAY_MS = 400;
const REQUIRED_BINDING_DEPS = [
  "appendFinalPathRow",
  "applySupportDatasetSelection",
  "bindBandCanvasRuntime",
  "cancelSubviewPairwiseEvidence",
  "bindAssemblyActionFeedbackDismiss",
  "bindAssemblyContextMenu",
  "bindCtgActions",
  "bindDeletedMemberChipBoxSelection",
  "bindSeqActions",
  "bindStickyCtgLabels",
  "bindSubviewBandTooltips",
  "bindSubviewTrackContigDrag",
  "bindTrackBoxSelection",
  "bindTrackContigDrag",
  "bindTrackScrollSync",
  "bindTrackSelectionHotkeys",
  "bindTrackViewportResize",
  "handleNewSequenceRowAction",
  "handleSubviewCandidateRemoval",
  "handleSubviewSwapTrackOrder",
  "handleSubviewTrackSelectionRemoval",
  "handleTrackSubviewCandidateSelection",
  "handleTrackSubviewTrackSelection",
  "loadAssemblyView",
  "loadNewSequencesTab",
  "markNextTrackAutoFocusSuppressed",
  "persistMainTrackViewState",
  "rememberTrackViewportAnchor",
  "normalizeTrackFocusMode",
  "rerender",
  "resolveTrackContigClickAction",
  "removeFinalPathRow",
  "runCtgSearch",
  "selectChromosome",
  "selectCtg",
  "setAssemblyActionFeedback",
  "shouldSuppressTrackContigClick",
  "syncSupportDatasetSelection",
  "togglePrimaryTrackSelection",
  "moveFinalPathRow",
  "updateFinalPathRow",
  "updateDeletedCtgSelection",
];

function assertAssemblyBindingDeps(deps) {
  const missingDeps = REQUIRED_BINDING_DEPS.filter((key) => typeof deps?.[key] !== "function");
  if (!missingDeps.length) {
    return;
  }
  throw new TypeError(`Missing assembly binding deps: ${missingDeps.join(", ")}`);
}

function captureFinalPathTrackScrollState(host, nextState) {
  const finalPathScrollEl =
    host?.querySelector?.("[data-final-path-graph-viewport]")
    || host?.querySelector?.(".assembly-final-path-svg-wrap");
  if (!finalPathScrollEl) {
    return normalizeViewportScrollState(nextState?.assembly?.finalPathTrackScrollState);
  }
  return normalizeViewportScrollState({
    viewportKey: buildFinalPathTrackViewportKey(nextState),
    scrollLeft: Number(finalPathScrollEl.scrollLeft || 0),
  });
}

function setTrackComboOpenState(comboNode, isOpen) {
  if (!comboNode) {
    return;
  }
  const input = comboNode.querySelector(".assembly-track-combo-input");
  const toggle = comboNode.querySelector("[data-track-combo-toggle]");
  const menu = comboNode.querySelector(".assembly-track-combo-menu");
  comboNode.classList.toggle("is-open", isOpen);
  input?.setAttribute("aria-expanded", isOpen ? "true" : "false");
  toggle?.setAttribute("aria-expanded", isOpen ? "true" : "false");
  if (menu) {
    menu.classList.toggle("is-hidden", !isOpen);
    if (isOpen) {
      syncTrackComboMenuPlacement(comboNode);
    } else {
      menu.style.top = "";
      menu.style.bottom = "";
      menu.style.maxHeight = "";
      menu.style.overflowY = "";
    }
  }
}

function syncTrackComboMenuPlacement(comboNode) {
  if (!comboNode || typeof comboNode.getBoundingClientRect !== "function") {
    return;
  }
  const menu = comboNode.querySelector(".assembly-track-combo-menu");
  if (!menu || typeof menu.getBoundingClientRect !== "function") {
    return;
  }
  const viewportHeight =
    Number(globalThis.window?.innerHeight)
    || Number(globalThis.document?.documentElement?.clientHeight)
    || 0;
  if (!Number.isFinite(viewportHeight) || viewportHeight <= 0) {
    return;
  }
  const comboRect = comboNode.getBoundingClientRect();
  const menuRect = menu.getBoundingClientRect();
  const offset = 2;
  const margin = 8;
  const spaceBelow = Math.max(0, viewportHeight - Number(comboRect?.bottom || 0) - offset - margin);
  const spaceAbove = Math.max(0, Number(comboRect?.top || 0) - offset - margin);
  const menuHeight = Math.max(0, Number(menuRect?.height || menu.scrollHeight || 0));
  const shouldOpenUpward = menuHeight > spaceBelow && spaceAbove > spaceBelow;
  if (shouldOpenUpward) {
    menu.style.top = "auto";
    menu.style.bottom = "calc(100% + 2px)";
    menu.style.maxHeight = `${spaceAbove}px`;
  } else {
    menu.style.top = "calc(100% + 2px)";
    menu.style.bottom = "auto";
    menu.style.maxHeight = `${spaceBelow}px`;
  }
  menu.style.overflowY = "auto";
}

function closeTrackComboMenus(host, keepNode = null) {
  host.querySelectorAll?.("[data-track-combo-field]")?.forEach((comboNode) => {
    if (keepNode && comboNode === keepNode) {
      return;
    }
    setTrackComboOpenState(comboNode, false);
  });
}

function keepFinalPathCardVisible(host) {
  const windowObject = globalThis.window;
  const cardNode = host.querySelector?.(".final-path-card");
  if (!cardNode || typeof cardNode.getBoundingClientRect !== "function" || typeof windowObject?.scrollBy !== "function") {
    return;
  }
  const rect = cardNode.getBoundingClientRect();
  const viewportHeight =
    Number(windowObject.innerHeight)
    || Number(globalThis.document?.documentElement?.clientHeight)
    || 0;
  if (!Number.isFinite(viewportHeight) || viewportHeight <= 0 || !Number.isFinite(rect?.top) || !Number.isFinite(rect?.bottom)) {
    return;
  }
  const margin = 16;
  const maxVisibleHeight = Math.max(0, viewportHeight - margin * 2);
  let deltaY = 0;
  if (rect.height <= maxVisibleHeight) {
    if (rect.top < margin) {
      deltaY = rect.top - margin;
    } else if (rect.bottom > viewportHeight - margin) {
      deltaY = rect.bottom - (viewportHeight - margin);
    }
  } else if (rect.top < margin) {
    deltaY = rect.top - margin;
  }
  if (Math.abs(deltaY) < 1) {
    return;
  }
  windowObject.scrollBy({
    left: 0,
    top: deltaY,
    behavior: "auto",
  });
}

function keepFinalPathNodeBottomVisible(node) {
  const windowObject = globalThis.window;
  if (!node || typeof node.getBoundingClientRect !== "function" || typeof windowObject?.scrollBy !== "function") {
    return;
  }
  const viewportHeight =
    Number(windowObject.innerHeight)
    || Number(globalThis.document?.documentElement?.clientHeight)
    || 0;
  if (!Number.isFinite(viewportHeight) || viewportHeight <= 0) {
    return;
  }
  const rect = node.getBoundingClientRect();
  if (!Number.isFinite(rect?.bottom)) {
    return;
  }
  const margin = 16;
  const deltaY = rect.bottom - (viewportHeight - margin);
  if (!Number.isFinite(deltaY) || deltaY <= 0) {
    return;
  }
  windowObject.scrollBy({
    left: 0,
    top: deltaY,
    behavior: "auto",
  });
}

function scrollFinalPathTableToBottom(host) {
  const listNode = host.querySelector?.("[data-final-path-card-list]");
  if (listNode) {
    const nextScrollTop = Number(listNode.scrollHeight || 0);
    if (Number.isFinite(nextScrollTop) && nextScrollTop >= 0) {
      listNode.scrollTop = nextScrollTop;
    }
  }
  const addButtonNode = host.querySelector?.("[data-final-path-add-row]");
  if (addButtonNode) {
    keepFinalPathNodeBottomVisible(addButtonNode);
    return;
  }
  keepFinalPathNodeBottomVisible(host.querySelector?.(".final-path-card"));
}

function resolveFinalPathTargetChrName(node) {
  return String(
    node?.dataset?.finalPathTargetChrName
    || node?.closest?.("[data-final-path-target-chr-name]")?.dataset?.finalPathTargetChrName
    || "",
  ).trim();
}

function withFinalPathTarget(payload, node) {
  const targetChrName = resolveFinalPathTargetChrName(node);
  return targetChrName ? { ...payload, targetChrName } : payload;
}

function captureScrollableRegionState(host, selector) {
  const region = host.querySelector?.(selector);
  if (!region) {
    return () => {};
  }
  const scrollTop = Number(region.scrollTop || 0);
  const scrollLeft = Number(region.scrollLeft || 0);
  return () => {
    const nextRegion = host.querySelector?.(selector);
    if (!nextRegion) {
      return;
    }
    nextRegion.scrollTop = scrollTop;
    nextRegion.scrollLeft = scrollLeft;
  };
}

function syncTrackComboSelection(comboNode, selectedValue) {
  if (!comboNode) {
    return;
  }
  comboNode.querySelectorAll("[data-track-combo-option]").forEach((optionNode) => {
    const active = Number(optionNode.dataset.trackComboValue || 0) === Number(selectedValue);
    optionNode.classList.toggle("is-active", active);
    optionNode.setAttribute("aria-selected", active ? "true" : "false");
  });
}

function resolveTrackPrefValue(trackPrefs, field) {
  if (field === "supportDsCtgLen") {
    return trackPrefs.supportDsCtgLen;
  }
  if (field === "minTickUnitKb") {
    return trackPrefs.minTickUnitKb;
  }
  if (field === "maxTickCount") {
    return trackPrefs.maxTickCount;
  }
  if (field === "mapq") {
    return trackPrefs.mapq;
  }
  return trackPrefs.alignmentLength;
}

function normalizeTrackPrefInputValue(field, rawValue) {
  if (field === "mapq" || field === "supportDsCtgLen") {
    return normalizeNonNegativeInt(rawValue);
  }
  return normalizePositiveInt(rawValue);
}

function getCurrentChrLength(assembly) {
  const selectedChrName = String(assembly?.selectedChrName || "").trim();
  const chromosome = (Array.isArray(assembly?.chromosomes) ? assembly.chromosomes : [])
    .find((item) => String(item?.chrName || "").trim() === selectedChrName);
  return normalizePositiveInt(chromosome?.chrLength ?? chromosome?.lengthBp) ?? 1;
}

function collectSupportDsCtgLenRuleRows(dialog) {
  const chrLength = normalizePositiveInt(dialog?.dataset?.supportDsCtgLenRulesChrLength) ?? 1;
  const rows = Array.from(dialog?.querySelectorAll?.("[data-support-ds-ctg-len-rules-row]") || []);
  return normalizeSupportDsCtgLenRules(rows.map((row) => {
    const startMb = Number(row.querySelector("[data-support-ds-rule-field='startMb']")?.value ?? 0);
    const endMb = Number(row.querySelector("[data-support-ds-rule-field='endMb']")?.value ?? 0);
    return {
      startBp: startMb <= 0 ? 1 : Math.round(startMb * 1_000_000),
      endBp: Math.max(1, Math.round(endMb * 1_000_000)),
      supportDsCtgLen: row.querySelector("[data-support-ds-rule-field='supportDsCtgLen']")?.value,
    };
  }), { chrLength });
}

function collectSupportDsCtgLenRuleDraftRows(dialog) {
  const rows = Array.from(dialog?.querySelectorAll?.("[data-support-ds-ctg-len-rules-row]") || []);
  return rows.map((row) => ({
    startMb: String(row.querySelector("[data-support-ds-rule-field='startMb']")?.value ?? ""),
    endMb: String(row.querySelector("[data-support-ds-rule-field='endMb']")?.value ?? ""),
    supportDsCtgLen: String(row.querySelector("[data-support-ds-rule-field='supportDsCtgLen']")?.value ?? ""),
  }));
}

function hasDirtySupportDsCtgLenRuleDraft(dialog) {
  const baseline = String(dialog?.dataset?.supportDsCtgLenRulesBaseline || "[]");
  return JSON.stringify(collectSupportDsCtgLenRuleDraftRows(dialog)) !== baseline;
}

function formatRuleMbValue(value) {
  const normalized = Number(value);
  if (!Number.isFinite(normalized)) {
    return "0";
  }
  return normalized.toFixed(6).replace(/\.?0+$/, "");
}

function appendSupportDsCtgLenRuleRow(dialog) {
  const body = dialog?.querySelector?.("[data-support-ds-ctg-len-rules-body]");
  if (!body) {
    return;
  }
  const chrLength = normalizePositiveInt(dialog.dataset.supportDsCtgLenRulesChrLength) ?? 1;
  const deleteLabel = String(dialog.dataset.supportDsCtgLenRulesDeleteLabel || "Delete");
  const existing = collectSupportDsCtgLenRuleRows(dialog);
  const lastEnd = existing.length ? Math.max(...existing.map((rule) => rule.endBp)) : 0;
  const startBp = Math.min(chrLength, lastEnd + 1);
  const endBp = chrLength;
  const row = dialog.ownerDocument.createElement("tr");
  row.dataset.supportDsCtgLenRulesRow = "1";
  row.innerHTML = `
    <td><input type="number" step="0.001" min="0" value="${formatRuleMbValue(startBp <= 1 ? 0 : startBp / 1_000_000)}" data-support-ds-rule-field="startMb"></td>
    <td><input type="number" step="0.001" min="0" value="${formatRuleMbValue(endBp / 1_000_000)}" data-support-ds-rule-field="endMb"></td>
    <td><input type="text" inputmode="numeric" pattern="[0-9]*" value="0" data-support-ds-rule-field="supportDsCtgLen"></td>
    <td><button type="button" class="button ghost tiny" data-support-ds-ctg-len-rules-delete="1">${deleteLabel}</button></td>
  `;
  body.appendChild(row);
}

function bindTrackComboDismiss(host) {
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (host[ASSEMBLY_TRACK_COMBO_BOUND]) {
    return;
  }
  host.addEventListener(
    "pointerdown",
    (event) => {
      const insideCombo = event.target?.closest?.("[data-track-combo-field]");
      if (insideCombo) {
        return;
      }
      closeTrackComboMenus(host);
    },
    true,
  );
  host[ASSEMBLY_TRACK_COMBO_BOUND] = true;
}

function getCreateEmptyFinalPathRow(deps) {
  if (typeof deps?.createEmptyFinalPathRow === "function") {
    return deps.createEmptyFinalPathRow;
  }
  return async () => null;
}

export function bindAssemblyPage(host, store, deps) {
  assertAssemblyBindingDeps(deps);
  const {
    appendFinalPathRow,
    applySupportDatasetSelection,
    cancelSubviewPairwiseEvidence,
    bindAssemblyActionFeedbackDismiss,
    bindAssemblyContextMenu,
    bindCtgActions,
    bindDeletedMemberChipBoxSelection,
    bindSeqActions,
    bindStickyCtgLabels,
    bindBandCanvasRuntime,
    bindSubviewBandTooltips,
    bindSubviewTrackContigDrag,
    bindTrackBoxSelection,
    bindTrackContigDrag,
    bindTrackScrollSync,
    bindTrackSelectionHotkeys,
    bindTrackViewportResize,
    createPhasedChrTrack = async () => {},
    handleNewSequenceRowAction,
    handleSubviewCandidateRemoval,
    handleSubviewSwapTrackOrder,
    handleSubviewTrackSelectionRemoval,
    handleTrackSubviewCandidateSelection,
    handleTrackSubviewTrackSelection,
    loadAssemblyView,
    loadNewSequencesTab,
    markNextTrackAutoFocusSuppressed,
    persistMainTrackViewState,
    refreshSubviewPairwiseEvidence = () => {},
    rememberTrackViewportAnchor,
    requestAssemblyConfirm = async () => true,
    normalizeTrackFocusMode,
    rerender,
    rerenderAssemblyMainTab = rerender,
    resolveTrackContigClickAction,
    removeFinalPathRow,
    resolveAssemblyConfirmDialog = () => {},
    restoreSelectedDeletedCtgs = async () => {},
    runCtgSearch,
    selectChromosome,
    selectCtg,
    setAssemblyActionFeedback,
    setActivePhasedFinalPathTrack = () => {},
    shouldSuppressTrackContigClick,
    syncSupportDatasetSelection,
    togglePrimaryTrackSelection,
    moveFinalPathRow,
    updateFinalPathRow,
    updateDeletedCtgSelection,
  } = deps;

  bindTrackComboDismiss(host);
  bindAssemblyActionFeedbackDismiss(host, store);
  const initialState = store.getState();
  const supportDatasetSync = syncSupportDatasetSelection(store);
  if (supportDatasetSync.changed) {
    void applySupportDatasetSelection(host, store, supportDatasetSync.supportDatasetId);
    return;
  }

  const queryHost = typeof host.querySelector === "function"
    ? host.querySelector.bind(host)
    : () => null;
  const queryHostAll = typeof host.querySelectorAll === "function"
    ? host.querySelectorAll.bind(host)
    : () => [];
  const searchButton = queryHost("#assembly-search-button");
  const searchInput = queryHost("#assembly-search-seq-input");
  const tabButtons = queryHostAll(".tab[data-tab]");
  const printViewButton = queryHost("#assembly-print-view-button");
  const exportChrCtgPmoButton = queryHost("#assembly-export-chr-ctg-pmolecule-button");
  const exportAgpButton = queryHost("#assembly-export-agp-button");
  const chrPickerToggleButton = queryHost("#assembly-chr-picker-toggle");
  const chrPickerInline = chrPickerToggleButton?.closest?.(".chr-picker-inline");
  const quickActionButtons = queryHostAll("[data-assembly-quick-action]");
  const chrPickerButtons = queryHostAll(".chr-picker-option[data-chr-name]");
  const ctgButtons = queryHostAll("[data-assembly-ctg-id]");
  const deletedCtgButtons = queryHostAll("[data-deleted-ctg-record-id]");
  const trackCtgTargets = queryHostAll("[data-track-contig-id][data-track-role]");
  const trackLabelTargets = queryHostAll("[data-track-label-role][data-track-label-selectable='1']");
  const subviewRemoveTargets = queryHostAll("[data-subview-remove-type][data-subview-remove-role]");
  const subviewActionTargets = queryHostAll("[data-subview-action]");
  const newSequenceActionButtons = queryHostAll(
    "[data-new-seq-action][data-assembly-seq-id]",
  );
  const memberSelect = queryHost("#member-select");
  const supportDatasetSelect = queryHost("#assembly-support-dataset-id");
  const trackMinTickUnitKbInput = queryHost("#assembly-track-min-tick-unit-kb");
  const trackSupportDsCtgLenInput = queryHost("#assembly-track-support-ds-ctg-len");
  const trackMaxTickCountInput = queryHost("#assembly-track-max-tick-count");
  const trackAlignmentLengthInput = queryHost("#assembly-track-alignment-length");
  const trackMapqInput = queryHost("#assembly-track-mapq");
  const createPhasedTrackButton = queryHost("[data-create-phased-track='1']");
  const subviewTrackMinTickUnitKbInput = queryHost("#subview-track-min-tick-unit-kb");
  const subviewTrackMaxTickCountInput = queryHost("#subview-track-max-tick-count");
  const subviewTrackAlignmentLengthInput = queryHost("#subview-track-alignment-length");
  const subviewTrackMapqInput = queryHost("#subview-track-mapq");
  const finalPathTrackMinTickUnitKbInput = queryHost("#final-path-track-min-tick-unit-kb");
  const finalPathTrackMaxTickCountInput = queryHost("#final-path-track-max-tick-count");
  const membersCardToggleButton = queryHost("[data-members-card-toggle='1']");
  const restoreAllDeletedCtgsButton = queryHost("[data-restore-all-deleted-ctgs='1']");
  const resetMembersStateButton = queryHost("[data-reset-members-state='1']");
  const assemblyConfirmButtons = queryHostAll("[data-assembly-confirm-action][data-assembly-confirm-id]");
  const addCtgImportCloseButton = queryHost("[data-add-ctg-import-close='1']");
  const finalPathViewModeButtons = queryHostAll("button[data-final-path-view-mode]");
  const phasedFinalPathButtons = queryHostAll("button[data-phased-final-path-key]");
  const phasedFinalPathMenus = queryHostAll("[data-phased-final-path-menu='true']");
  const finalPathAddButtons = queryHostAll("[data-final-path-add-row]");
  const finalPathRemoveButtons = queryHostAll("[data-final-path-remove-row]");
  const finalPathCellInputs = queryHostAll("[data-final-path-cell][data-final-path-segment-id]");
  const finalPathEmptyCellInputs = queryHostAll("[data-final-path-empty-cell]");
  const subviewPairwiseCancelButtons = queryHostAll("[data-subview-pairwise-cancel='1']");

  const openSupportDsCtgLenRulesDialog = () => {
    const state = store.getState();
    store.setState({
      ...state,
      assembly: {
        ...state.assembly,
        supportDsCtgLenRulesDialogOpen: true,
      },
    });
    rerenderAssemblyMainTab(host, store);
  };
  queryHostAll("[data-support-ds-ctg-len-settings]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      openSupportDsCtgLenRulesDialog();
    });
  });
  if (trackSupportDsCtgLenInput?.readOnly) {
    trackSupportDsCtgLenInput.addEventListener("click", openSupportDsCtgLenRulesDialog);
  }
  const rulesDialog = queryHost("[data-support-ds-ctg-len-rules-dialog]");
  const closeSupportDsCtgLenRulesDialog = () => {
    const state = store.getState();
    store.setState({
      ...state,
      assembly: {
        ...state.assembly,
        supportDsCtgLenRulesDialogOpen: false,
      },
    });
    rerenderAssemblyMainTab(host, store);
  };
  rulesDialog?.querySelector("[data-support-ds-ctg-len-rules-close]")?.addEventListener("click", async (event) => {
    event.preventDefault();
    if (hasDirtySupportDsCtgLenRuleDraft(rulesDialog)) {
      const message = String(
        rulesDialog.dataset.supportDsCtgLenRulesUnsavedMessage
          || "Close without saving changes?",
      );
      const confirmed = await requestAssemblyConfirm(host, store, message);
      if (!confirmed) {
        return;
      }
    }
    closeSupportDsCtgLenRulesDialog();
  });
  rulesDialog?.querySelector("[data-support-ds-ctg-len-rules-add]")?.addEventListener("click", (event) => {
    event.preventDefault();
    appendSupportDsCtgLenRuleRow(rulesDialog);
  });
  rulesDialog?.addEventListener("click", (event) => {
    const deleteButton = event.target?.closest?.("[data-support-ds-ctg-len-rules-delete]");
    if (!deleteButton) {
      return;
    }
    event.preventDefault();
    deleteButton.closest("[data-support-ds-ctg-len-rules-row]")?.remove();
  });
  rulesDialog?.querySelector("[data-support-ds-ctg-len-rules-reset]")?.addEventListener("click", async (event) => {
    event.preventDefault();
    const state = store.getState();
    const selectedChrName = String(state.assembly?.selectedChrName || "").trim();
    const nextRulesByChr = {
      ...normalizeSupportDsCtgLenRulesByChr(state.assembly?.supportDsCtgLenRulesByChr),
    };
    if (selectedChrName) {
      delete nextRulesByChr[selectedChrName];
    }
    store.setState({
      ...state,
      assembly: {
        ...state.assembly,
        supportDsCtgLenRulesByChr: nextRulesByChr,
        supportDsCtgLenRulesDialogOpen: true,
        trackSelectedCtgIds: [],
      },
    });
    rerenderAssemblyMainTab(host, store);
    await persistMainTrackViewState(host, store);
  });
  rulesDialog?.querySelector("[data-support-ds-ctg-len-rules-save]")?.addEventListener("click", async (event) => {
    event.preventDefault();
    const state = store.getState();
    const selectedChrName = String(state.assembly?.selectedChrName || "").trim();
    if (!selectedChrName) {
      return;
    }
    const chrLength = getCurrentChrLength(state.assembly);
    const rules = collectSupportDsCtgLenRuleRows(rulesDialog);
    const nextRulesByChr = {
      ...normalizeSupportDsCtgLenRulesByChr(state.assembly?.supportDsCtgLenRulesByChr),
    };
    let nextTrackView = state.assembly.trackView;
    if (isSingleFullChrSupportDsCtgLenRule(rules, { chrLength })) {
      delete nextRulesByChr[selectedChrName];
      nextTrackView = resolveTrackPrefs({
        ...state.assembly.trackView,
        supportDsCtgLen: rules[0]?.supportDsCtgLen ?? state.assembly.trackView?.supportDsCtgLen,
      });
    } else if (rules.length) {
      nextRulesByChr[selectedChrName] = rules;
    } else {
      delete nextRulesByChr[selectedChrName];
    }
    store.setState({
      ...state,
      assembly: {
        ...state.assembly,
        trackView: nextTrackView,
        supportDsCtgLenRulesByChr: nextRulesByChr,
        supportDsCtgLenRulesDialogOpen: true,
        trackSelectedCtgIds: [],
      },
    });
    rerenderAssemblyMainTab(host, store);
    await persistMainTrackViewState(host, store);
  });

  searchButton?.addEventListener("click", async () => {
    await runCtgSearch(host, store, searchInput?.value || "");
  });
  assemblyConfirmButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const input = Array.from(queryHostAll("[data-assembly-confirm-input]")).find(
        (node) => node.dataset.assemblyConfirmInput === button.dataset.assemblyConfirmId,
      );
      const directionInput = Array.from(queryHostAll("[data-assembly-anchor-offset-direction]")).find(
        (node) => node.dataset.assemblyAnchorOffsetDirection === button.dataset.assemblyConfirmId
          && node.checked,
      );
      const value = directionInput
        ? {
          direction: directionInput.value || "",
          offsetBp: input?.value ?? "",
        }
        : input?.value ?? "";
      resolveAssemblyConfirmDialog(host, store, {
        id: button.dataset.assemblyConfirmId,
        confirmed: button.dataset.assemblyConfirmAction === "confirm",
        value,
      });
    });
  });
  addCtgImportCloseButton?.addEventListener("click", (event) => {
    event.preventDefault();
    const state = store.getState();
    store.setState({
      ...state,
      assembly: {
        ...state.assembly,
        addCtgImportProgress: null,
      },
    });
    rerender(host, store);
  });
  searchInput?.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    await runCtgSearch(host, store, searchInput?.value || "");
  });
  printViewButton?.addEventListener("click", () => {
    if (typeof window.print === "function") {
      window.print();
      setAssemblyActionFeedback(host, store, {
        actionError: "",
        actionStatus: tAssembly(store.getState(), "runtime.printDialogOpened"),
      });
      return;
    }
    setAssemblyActionFeedback(host, store, {
      actionError: tAssembly(store.getState(), "runtime.printUnsupported"),
      actionStatus: tAssembly(store.getState(), "runtime.printFailed"),
    });
  });
  exportChrCtgPmoButton?.addEventListener("click", () => {
    setAssemblyActionFeedback(host, store, {
      actionError: tAssembly(store.getState(), "runtime.exportChrCtgPmoUnavailable"),
      actionStatus: "",
    });
  });
  exportAgpButton?.addEventListener("click", () => {
    setAssemblyActionFeedback(host, store, {
      actionError: tAssembly(store.getState(), "runtime.exportAgpUnavailable"),
      actionStatus: "",
    });
  });
  createPhasedTrackButton?.addEventListener("click", async (event) => {
    event.preventDefault();
    if (createPhasedTrackButton.disabled) {
      return;
    }
    await createPhasedChrTrack(host, store);
  });
  quickActionButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const quickAction = String(button.dataset.assemblyQuickAction || "").trim();
      if (quickAction === "focus-search") {
        searchInput?.focus();
        searchInput?.select?.();
        return;
      }
      if (quickAction === "toggle-chr-picker") {
        if (!chrPickerToggleButton || chrPickerToggleButton.disabled) {
          return;
        }
        chrPickerToggleButton.click();
      }
    });
  });

  tabButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const nextTab = button.dataset.tab || "assembly";
      if (nextTab !== "assembly") {
        cancelSubviewPairwiseEvidence(host, store, { rerenderAfter: false });
      }
      store.setState({
        assembly: {
          ...store.getState().assembly,
          activeTab: nextTab,
        },
      });
      rerender(host, store);
      if (nextTab === "check-new-sequences") {
        await loadNewSequencesTab(host, store);
      }
    });
  });
  finalPathViewModeButtons.forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const nextViewMode = normalizeFinalPathViewMode(button.dataset.finalPathViewMode);
      const state = store.getState();
      if (String(state.assembly?.finalPathViewMode || "graph").trim() === nextViewMode) {
        return;
      }
      store.setState({
        ...state,
        assembly: {
          ...state.assembly,
          finalPathViewMode: nextViewMode,
        },
      });
      rerender(host, store);
      keepFinalPathCardVisible(host);
      await persistMainTrackViewState(host, store);
    });
  });
  phasedFinalPathButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const trackKey = String(button.dataset.phasedFinalPathKey || "").trim();
      if (!trackKey) {
        return;
      }
      setActivePhasedFinalPathTrack(host, store, {
        trackKey,
        chrName: String(button.dataset.phasedFinalPathChrName || "").trim(),
      });
      const menu = button.closest?.("[data-phased-final-path-menu='true']");
      menu?.querySelector?.("[data-phased-final-path-options='true']")?.classList?.add?.("is-hidden");
      menu?.querySelector?.("[data-phased-final-path-toggle='true']")?.setAttribute?.("aria-expanded", "false");
    });
  });
  phasedFinalPathMenus.forEach((menu) => {
    const toggle = menu.querySelector?.("[data-phased-final-path-toggle='true']");
    const options = menu.querySelector?.("[data-phased-final-path-options='true']");
    let closeTimer = null;
    const close = () => {
      options?.classList?.add?.("is-hidden");
      toggle?.setAttribute?.("aria-expanded", "false");
    };
    const cancelClose = () => {
      if (closeTimer !== null) {
        clearTimeout(closeTimer);
        closeTimer = null;
      }
    };
    toggle?.addEventListener("click", (event) => {
      event.preventDefault();
      cancelClose();
      const isHidden = options?.classList?.contains?.("is-hidden") !== false;
      options?.classList?.toggle?.("is-hidden", !isHidden);
      toggle.setAttribute("aria-expanded", isHidden ? "true" : "false");
    });
    menu.addEventListener?.("pointerenter", cancelClose);
    menu.addEventListener?.("pointerleave", () => {
      cancelClose();
      closeTimer = setTimeout(close, ASSEMBLY_DROPDOWN_CLOSE_DELAY_MS);
    });
  });
  membersCardToggleButton?.addEventListener("click", async (event) => {
    event.preventDefault();
    const state = store.getState();
    const membersCardCollapsed = state.assembly?.membersCardCollapsed !== false;
    store.setState({
      ...state,
      assembly: {
        ...state.assembly,
        membersCardCollapsed: !membersCardCollapsed,
      },
    });
    rerender(host, store);
    await persistMainTrackViewState(host, store);
  });
  restoreAllDeletedCtgsButton?.addEventListener("click", async (event) => {
    event.preventDefault();
    const state = store.getState();
    const selectedRecordIds = normalizeDeletedCtgRecordIds(
      (Array.isArray(state.assembly?.deletedCtgs) ? state.assembly.deletedCtgs : [])
        .map((ctg) => ctg?.deletedCtgRecordId),
    );
    if (!selectedRecordIds.length) {
      return;
    }
    await restoreSelectedDeletedCtgs(host, store, selectedRecordIds);
  });
  resetMembersStateButton?.addEventListener("click", async (event) => {
    event.preventDefault();
    const state = store.getState();
    const selectedRecordIds = normalizeDeletedCtgRecordIds(
      (Array.isArray(state.assembly?.deletedCtgs) ? state.assembly.deletedCtgs : [])
        .map((ctg) => ctg?.deletedCtgRecordId),
    );
    const hiddenPrimaryCtgIds = normalizeDeletedCtgRecordIds(state.assembly?.hiddenPrimaryCtgIds);
    if (!selectedRecordIds.length && !hiddenPrimaryCtgIds.length) {
      return;
    }
    if (hiddenPrimaryCtgIds.length) {
      store.setState({
        ...state,
        assembly: {
          ...state.assembly,
          hiddenPrimaryCtgIds: [],
          hiddenPrimaryCtgIdsByChr: {
            ...(state.assembly.hiddenPrimaryCtgIdsByChr || {}),
            [String(state.assembly.selectedChrName || "").trim()]: [],
          },
          actionError: "",
        },
      });
      rerenderAssemblyMainTab(host, store);
      await persistMainTrackViewState(host, store);
    }
    if (selectedRecordIds.length) {
      await restoreSelectedDeletedCtgs(host, store, selectedRecordIds);
    }
  });
  finalPathAddButtons.forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      await appendFinalPathRow(host, store, withFinalPathTarget({}, button));
      scrollFinalPathTableToBottom(host);
    });
  });
  finalPathRemoveButtons.forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const segmentId = String(button.dataset.finalPathRemoveRow || "").trim();
      if (!segmentId) {
        return;
      }
      await removeFinalPathRow(host, store, withFinalPathTarget({
        segmentId,
      }, button));
    });
  });
  finalPathCellInputs.forEach((input) => {
    const commit = async () => {
      const field = String(input.dataset.finalPathCell || "").trim().toLowerCase();
      const segmentId = String(input.dataset.finalPathSegmentId || "").trim();
      if (!field || !segmentId) {
        return;
      }
      await updateFinalPathRow(host, store, withFinalPathTarget({
        segmentId,
        field,
        value: input.value,
      }, input));
    };
    input.addEventListener("change", () => {
      void commit();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") {
        return;
      }
      event.preventDefault();
      void commit();
    });
  });
  finalPathEmptyCellInputs.forEach((input) => {
    const commit = async () => {
      const field = String(input.dataset.finalPathEmptyCell || "").trim().toLowerCase();
      if (!field) {
        return;
      }
      await getCreateEmptyFinalPathRow(deps)(host, store, withFinalPathTarget({
        field,
        value: input.value,
      }, input));
    };
    input.addEventListener("change", () => {
      void commit();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") {
        return;
      }
      event.preventDefault();
      void commit();
    });
  });
  bindFinalPathCardDrag(host, store, {
    moveFinalPathRow,
  });
  (deps.bindFinalPathGraphDrag || bindFinalPathGraphDrag)(host, store, {
    moveFinalPathRow,
    rerender,
  });
  (deps.bindFinalPathExport || bindFinalPathExport)(host, store, deps);
  deps.bindDegapCard?.(host, store);

  if (initialState.assembly.activeTab === "check-new-sequences") {
    void loadNewSequencesTab(host, store);
  }

  chrPickerToggleButton?.addEventListener("click", () => {
    const state = store.getState();
    store.setState({
      assembly: {
        ...state.assembly,
        chrPickerOpen: !state.assembly.chrPickerOpen,
      },
    });
    rerender(host, store);
  });

  if (chrPickerInline) {
    let closeTimer = null;
    const close = () => {
      closeTimer = null;
      const state = store.getState();
      if (!state.assembly?.chrPickerOpen) {
        return;
      }
      store.setState({
        assembly: {
          ...state.assembly,
          chrPickerOpen: false,
        },
      });
      rerender(host, store);
    };
    const cancelClose = () => {
      if (closeTimer !== null) {
        clearTimeout(closeTimer);
        closeTimer = null;
      }
    };
    chrPickerInline.addEventListener?.("pointerenter", cancelClose);
    chrPickerInline.addEventListener?.("pointerleave", () => {
      cancelClose();
      closeTimer = setTimeout(close, ASSEMBLY_DROPDOWN_CLOSE_DELAY_MS);
    });
  }

  chrPickerButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const chrName = button.dataset.chrName || "";
      await selectChromosome(host, store, chrName);
    });
  });

  ctgButtons.forEach((button) => {
    button.addEventListener("click", async (event) => {
      const assemblyCtgId = Number(button.dataset.assemblyCtgId || 0);
      if (!assemblyCtgId) {
        return;
      }
      const isMemberChip = Boolean(button.closest?.(".assembly-member-chip-region"));
      const restoreMemberChipScroll = isMemberChip
        ? captureScrollableRegionState(host, ".assembly-member-chip-region")
        : () => {};
      if (isMemberChip && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        togglePrimaryTrackSelection(host, store, assemblyCtgId);
        restoreMemberChipScroll();
        return;
      }
      updateDeletedCtgSelection(host, store, []);
      await selectCtg(host, store, assemblyCtgId, {
        focusMode: normalizeTrackFocusMode(button.dataset.trackFocusMode),
      });
      restoreMemberChipScroll();
    });
  });
  deletedCtgButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      const deletedCtgRecordId = normalizeSupportDatasetId(button.dataset.deletedCtgRecordId);
      if (!deletedCtgRecordId) {
        return;
      }
      const restoreMemberChipScroll = captureScrollableRegionState(host, ".assembly-member-chip-region");
      const state = store.getState();
      const current = normalizeDeletedCtgRecordIds(state.assembly.selectedDeletedCtgRecordIds);
      let next = [deletedCtgRecordId];
      if (event.ctrlKey || event.metaKey) {
        const nextSet = new Set(current);
        if (nextSet.has(deletedCtgRecordId)) {
          nextSet.delete(deletedCtgRecordId);
        } else {
          nextSet.add(deletedCtgRecordId);
        }
        next = Array.from(nextSet.values());
      }
      updateDeletedCtgSelection(host, store, next);
      restoreMemberChipScroll();
    });
  });
  trackCtgTargets.forEach((target) => {
    target.addEventListener("click", async (event) => {
      if (shouldSuppressTrackContigClick()) {
        return;
      }
      const action = resolveTrackContigClickAction({
        trackRole: target.dataset.trackRole,
        contigId: target.dataset.trackContigId,
        phasedTrackId: target.dataset.trackPhasedTrackId,
        phasedTrackItemId: target.dataset.trackPhasedTrackItemId,
        phasedHaplotypeKey: target.dataset.trackPhasedHaplotypeKey,
        ctrlKey: event.ctrlKey,
        metaKey: event.metaKey,
      });
      if (action.type === "select-subview-candidate") {
        event.preventDefault();
        flushPendingMainTrackInputs();
        handleTrackSubviewCandidateSelection(host, store, {
          trackRole: action.trackRole,
          contigId: action.contigId,
          phasedTrackId: action.phasedTrackId,
          phasedTrackItemId: action.phasedTrackItemId,
          phasedHaplotypeKey: action.phasedHaplotypeKey,
        });
        return;
      }
      if (action.type === "select-ctg") {
        event.preventDefault();
        markNextTrackAutoFocusSuppressed();
        await selectCtg(host, store, action.contigId, {
          preserveViewport: true,
        });
        return;
      }
    });
  });
  trackLabelTargets.forEach((target) => {
    target.addEventListener("click", (event) => {
      event.preventDefault();
      const trackRole = target.dataset.trackLabelRole;
      if (!trackRole) {
        return;
      }
      flushPendingMainTrackInputs();
      handleTrackSubviewTrackSelection(host, store, {
        trackRole,
        source: target.dataset.trackLabelSource || "mother",
        datasetId: target.dataset.trackLabelDatasetId || null,
        isMirror: target.dataset.trackLabelIsMirror === "1",
        phasedTrackId: target.dataset.trackLabelPhasedTrackId || null,
        haplotypeKey: target.dataset.trackLabelPhasedHaplotypeKey || "",
      });
    });
  });
  subviewRemoveTargets.forEach((target) => {
    target.addEventListener("click", (event) => {
      event.preventDefault();
      const removeType = String(target.dataset.subviewRemoveType || "").trim();
      if (removeType === "candidate") {
        handleSubviewCandidateRemoval(host, store, {
          trackRole: target.dataset.subviewRemoveRole,
          contigId: target.dataset.subviewRemoveContigId,
          phasedTrackId: target.dataset.subviewRemovePhasedTrackId,
          phasedTrackItemId: target.dataset.subviewRemovePhasedTrackItemId,
          phasedHaplotypeKey: target.dataset.subviewRemovePhasedHaplotypeKey,
        });
        return;
      }
      if (removeType === "track") {
        handleSubviewTrackSelectionRemoval(host, store, {
          trackRole: target.dataset.subviewRemoveRole,
          source: target.dataset.subviewRemoveSource,
          datasetId: target.dataset.subviewRemoveDatasetId,
          isMirror: target.dataset.subviewRemoveIsMirror === "1",
        });
      }
    });
  });
  subviewActionTargets.forEach((target) => {
    target.addEventListener("click", (event) => {
      event.preventDefault();
      const action = String(target.dataset.subviewAction || "").trim();
      if (action === "swap-track-order") {
        handleSubviewSwapTrackOrder(host, store);
      }
    });
  });
  subviewPairwiseCancelButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      cancelSubviewPairwiseEvidence(host, store);
    });
  });
  newSequenceActionButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const action = String(button.dataset.newSeqAction || "").trim();
      const assemblySeqId = Number(button.dataset.assemblySeqId || 0);
      if (!action || !assemblySeqId) {
        return;
      }
      await handleNewSequenceRowAction(host, store, {
        action,
        assemblySeqId,
        seqName: button.dataset.seqName || "",
      });
    });
  });

  memberSelect?.addEventListener("change", () => {
    const seqId = Number(memberSelect.value || 0) || null;
    store.setState({
      assembly: {
        ...store.getState().assembly,
        selectedMemberSeqId: seqId,
      },
    });
    rerender(host, store);
  });

  const commitTrackInput = (field, inputElement, viewKey = "trackView") => {
    if (!inputElement) {
      return;
    }
    if (inputElement.readOnly) {
      return;
    }
    const state = store.getState();
    const current = state.assembly;
    const currentTrackView = current?.[viewKey] || {};
    const prefs = resolveTrackPrefs(currentTrackView);
    const normalizedInput = normalizeTrackPrefInputValue(field, inputElement.value);
    const previousValue = resolveTrackPrefValue(prefs, field);
    if (normalizedInput === null) {
      inputElement.value = String(previousValue);
      return;
    }
    const nextPrefs = resolveTrackPrefs({
      ...currentTrackView,
      [field]: normalizedInput,
    });
    const nextValue = resolveTrackPrefValue(nextPrefs, field);
    inputElement.value = String(nextValue);
    if (nextValue === previousValue) {
      return;
    }
    if (viewKey === "trackView" || viewKey === "subviewTrackView") {
      rememberTrackViewportAnchor(host, viewKey);
      markNextTrackAutoFocusSuppressed();
    }
    store.setState({
      ...state,
      assembly: {
        ...current,
        [viewKey]: nextPrefs,
        finalPathTrackScrollState:
          viewKey === "finalPathTrackView"
            ? captureFinalPathTrackScrollState(host, {
              ...state,
              assembly: {
                ...current,
                [viewKey]: nextPrefs,
              },
            })
            : current.finalPathTrackScrollState,
        trackSelectedCtgIds:
          viewKey === "trackView" && field === "supportDsCtgLen"
            ? []
            : current.trackSelectedCtgIds,
      },
    });
    rerender(host, store);
    if (viewKey === "trackView") {
      void persistMainTrackViewState(host, store);
    }
    if (
      viewKey === "subviewTrackView"
      && (field === "alignmentLength" || field === "mapq")
      && shouldRefetchSubviewPairwiseEvidence({
        summary: current?.subview?.summary,
        trackPrefs: nextPrefs,
        evidence: current?.subview?.pairwiseEvidence,
      })
    ) {
      refreshSubviewPairwiseEvidence(host, store);
    }
  };

  const commitTrackComboInput = (field, inputElement, viewKey = "trackView") => {
    if (!inputElement) {
      return;
    }
    commitTrackInput(field, inputElement, viewKey);
    syncTrackComboSelection(inputElement.closest("[data-track-combo-field]"), inputElement.value);
  };

  const flushPendingMainTrackInputs = () => {
    commitTrackComboInput("supportDsCtgLen", trackSupportDsCtgLenInput, "trackView");
    commitTrackComboInput("minTickUnitKb", trackMinTickUnitKbInput, "trackView");
    commitTrackComboInput("maxTickCount", trackMaxTickCountInput, "trackView");
    commitTrackComboInput("alignmentLength", trackAlignmentLengthInput, "trackView");
    commitTrackComboInput("mapq", trackMapqInput, "trackView");
  };

  const bindTrackNumberInput = (field, inputElement, viewKey = "trackView") => {
    if (!inputElement) {
      return;
    }
    if (inputElement.readOnly) {
      return;
    }
    const comboNode = inputElement.closest("[data-track-combo-field]");
    const toggleButton = comboNode?.querySelector("[data-track-combo-toggle]");
    const optionButtons = comboNode?.querySelectorAll("[data-track-combo-option]") || [];
    const commit = () => {
      commitTrackComboInput(field, inputElement, viewKey);
    };
    inputElement.addEventListener("change", commit);
    inputElement.addEventListener("focus", () => {
      closeTrackComboMenus(host, comboNode);
      setTrackComboOpenState(comboNode, true);
    });
    inputElement.addEventListener("blur", () => {
      window.setTimeout(() => {
        if (comboNode?.contains(document.activeElement)) {
          return;
        }
        commit();
        setTrackComboOpenState(comboNode, false);
      }, 0);
    });
    inputElement.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        closeTrackComboMenus(host, comboNode);
        setTrackComboOpenState(comboNode, true);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setTrackComboOpenState(comboNode, false);
        return;
      }
      if (event.key !== "Enter") {
        return;
      }
      event.preventDefault();
      commit();
      setTrackComboOpenState(comboNode, false);
    });
    toggleButton?.addEventListener("pointerdown", (event) => {
      event.preventDefault();
    });
    toggleButton?.addEventListener("click", (event) => {
      event.preventDefault();
      const isOpen = comboNode?.classList.contains("is-open");
      closeTrackComboMenus(host, isOpen ? null : comboNode);
      setTrackComboOpenState(comboNode, !isOpen);
      inputElement.focus();
    });
    optionButtons.forEach((optionButton) => {
      optionButton.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        const nextValue = optionButton.dataset.trackComboValue || "";
        inputElement.value = nextValue;
        commit();
        setTrackComboOpenState(comboNode, false);
        inputElement.focus();
      });
    });
  };

  bindTrackNumberInput("supportDsCtgLen", trackSupportDsCtgLenInput, "trackView");
  bindTrackNumberInput("minTickUnitKb", trackMinTickUnitKbInput, "trackView");
  bindTrackNumberInput("maxTickCount", trackMaxTickCountInput, "trackView");
  bindTrackNumberInput("alignmentLength", trackAlignmentLengthInput, "trackView");
  bindTrackNumberInput("mapq", trackMapqInput, "trackView");
  bindTrackNumberInput("minTickUnitKb", subviewTrackMinTickUnitKbInput, "subviewTrackView");
  bindTrackNumberInput("maxTickCount", subviewTrackMaxTickCountInput, "subviewTrackView");
  bindTrackNumberInput("alignmentLength", subviewTrackAlignmentLengthInput, "subviewTrackView");
  bindTrackNumberInput("mapq", subviewTrackMapqInput, "subviewTrackView");
  bindTrackNumberInput("minTickUnitKb", finalPathTrackMinTickUnitKbInput, "finalPathTrackView");
  bindTrackNumberInput("maxTickCount", finalPathTrackMaxTickCountInput, "finalPathTrackView");
  supportDatasetSelect?.addEventListener("change", async () => {
    await applySupportDatasetSelection(host, store, supportDatasetSelect.value);
  });

  bindCtgActions(host, store);
  bindSeqActions(host, store);
  bindAssemblyContextMenu(host, store);
  bindDeletedMemberChipBoxSelection(host, store);
  bindBandCanvasRuntime(host);
  bindSubviewBandTooltips(host);
  bindTrackViewportResize(host, store);
  bindTrackContigDrag(host, store);
  bindSubviewTrackContigDrag(host, store);
  bindTrackBoxSelection(host, store);
  bindTrackSelectionHotkeys(host, store);

  const viewportChanged = bindTrackScrollSync(host, store);
  if (viewportChanged) {
    rerender(host, store);
    return;
  }
  bindStickyCtgLabels(host);

  const state = store.getState();
  if (
    state.session?.workspacePath &&
    state.session?.projectId &&
    state.assembly.chromosomes.length === 0 &&
    !state.assembly.loading
  ) {
    void loadAssemblyView(host, store, {
      keepCurrentChr: Boolean(state.assembly?.projectExportScrollToBottom),
      keepCurrentCtg: false,
    });
  }
}
import { tAssembly } from "./i18n.js";
