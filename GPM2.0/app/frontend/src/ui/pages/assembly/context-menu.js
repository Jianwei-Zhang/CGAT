import {
  buildSupportMirrorKey,
  filterPrimaryTrackSelectionCtgIds,
  normalizeDeletedCtgRecordIds,
  normalizeSupportDatasetId,
  normalizeSupportMirroredCtgs,
  normalizeTrackSelectionCtgIds,
  normalizeTrackRole,
} from "./selection-state.js";
import {
  getSubviewSelections,
  getSubviewState,
  getSubviewTrackSelections,
  normalizeSubviewTrackPairHiddenCtgs,
  normalizeSubviewTrackSource,
  resolveFilteredSubviewTrackPairSelectionsFromAssembly,
} from "./subview-state.js";
import { getAssemblyI18n, tAssembly } from "./i18n.js";

const REQUIRED_ACTION_NAMES = [
  "enterSubviewFromTrackSelections",
  "enterSubviewFromCandidates",
  "setSubviewTrackPairCtgHidden",
  "toggleSubviewContigFlip",
  "deleteSelectedSubviewTrackPairCtgs",
  "clearSubviewTrackPairHiddenCtgs",
  "setSelectedPrimaryTrackCtgsHidden",
  "deleteSelectedTrackCtgs",
  "runBatchDeleteTrackCtgs",
  "restoreSelectedDeletedCtgs",
  "canEditTrackCtg",
  "addFinalPathContigRelativeToSegment",
  "addFinalPathGapRelativeToSegment",
  "deleteFinalPathSegment",
  "flipFinalPathSegment",
  "toggleSupportTrackCtgMirror",
  "togglePrimaryTrackCtgHidden",
  "toggleSubviewAnchorEdge",
  "copySubviewAnchorWithOffset",
  "deleteSubviewManualAnchor",
  "appendTrackContigToFinalPath",
  "addTrackContigToPhasedTrack",
  "removePhasedTrackItem",
  "deletePhasedTrack",
  "importAddCtgIntoTrack",
  "setActiveHitsTrack",
  "setAssemblyActionFeedback",
  "openAssemblyContextMenuAt",
  "applyEditorAction",
  "promptForRenameCtg",
  "promptForDeleteShorterThanLength",
  "buildRenameCtgActionArgs",
  "confirm",
  "rerender",
];

function normalizeAssemblyContextMenuActions(actions) {
  const normalized = actions && typeof actions === "object" ? actions : null;
  const missing = REQUIRED_ACTION_NAMES.filter((name) => typeof normalized?.[name] !== "function");
  if (missing.length) {
    throw new Error(`buildAssemblyContextMenuItems missing required action handler(s): ${missing.join(", ")}`);
  }
  return normalized;
}

function parseNonNegativeIntegerInput(value) {
  const text = String(value ?? "").trim();
  if (!/^\d+$/.test(text)) {
    return null;
  }
  const parsed = Number(text);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    return null;
  }
  return parsed;
}

function resolvePrimaryTrackCtgLength(ctg) {
  return normalizeSupportDatasetId(ctg?.totalLength)
    ?? normalizeSupportDatasetId(ctg?.lengthBp)
    ?? normalizeSupportDatasetId(ctg?.overallLen)
    ?? normalizeSupportDatasetId(ctg?.overallLength)
    ?? 0;
}

function resolvePrimaryTrackCtgsShorterThan(assembly, thresholdBp) {
  const normalizedThreshold = parseNonNegativeIntegerInput(thresholdBp);
  if (normalizedThreshold === null) {
    return [];
  }
  const candidateIds = (Array.isArray(assembly?.chrCtgs) ? assembly.chrCtgs : [])
    .filter((ctg) => resolvePrimaryTrackCtgLength(ctg) < normalizedThreshold)
    .map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId))
    .filter((assemblyCtgId) => assemblyCtgId !== null);
  return filterPrimaryTrackSelectionCtgIds(candidateIds, assembly);
}

export function resolveAssemblyCtgContextTarget(target) {
  const trackNode = target?.closest?.("[data-track-contig-id][data-track-role]");
  if (trackNode) {
    const assemblyCtgId = normalizeSupportDatasetId(trackNode.getAttribute("data-track-contig-id"));
    const trackRole = String(trackNode.getAttribute("data-track-role") || "").trim();
    const isMirror = trackNode.getAttribute("data-track-is-mirror") === "1";
    const datasetId = normalizeSupportDatasetId(trackNode.getAttribute("data-track-dataset-id"));
    const phasedTrackId = normalizeSupportDatasetId(trackNode.getAttribute("data-track-phased-track-id"));
    const phasedTrackItemId = normalizeSupportDatasetId(trackNode.getAttribute("data-track-phased-track-item-id"));
    const phasedHaplotypeKey = String(trackNode.getAttribute("data-track-phased-haplotype-key") || "").trim();
    const sourceKind = String(trackNode.getAttribute("data-track-source-kind") || "").trim();
    const referenceChrName = String(trackNode.getAttribute("data-track-reference-chr-name") || "").trim();
    const segmentStart = normalizeSupportDatasetId(trackNode.getAttribute("data-track-segment-start"));
    const segmentEnd = normalizeSupportDatasetId(trackNode.getAttribute("data-track-segment-end"));
    const refOrient = String(trackNode.getAttribute("data-track-ref-orient") || "").trim();
    if (
      assemblyCtgId !== null &&
      (trackRole === "primary" || trackRole === "support" || trackRole === "ref" || trackRole === "phased")
    ) {
      const base = {
        assemblyCtgId,
        trackRole,
        isMirror,
        datasetId,
      };
      if (refOrient) {
        base.refOrient = refOrient;
      }
      if (trackRole === "phased") {
        base.phasedTrackId = phasedTrackId;
        base.phasedTrackItemId = phasedTrackItemId;
        base.phasedHaplotypeKey = phasedHaplotypeKey;
      }
      if (trackRole !== "ref" && sourceKind !== "ref_segment") {
        return base;
      }
      return {
        ...base,
        sourceKind,
        referenceChrName,
        segmentStart,
        segmentEnd,
      };
    }
  }

  const legacyNode = target?.closest?.("[data-assembly-ctg-id]");
  if (!legacyNode) {
    return null;
  }
  const assemblyCtgId = normalizeSupportDatasetId(legacyNode.getAttribute("data-assembly-ctg-id"));
  if (assemblyCtgId === null) {
    return null;
  }
  return {
    assemblyCtgId,
    trackRole: null,
    isMirror: false,
    datasetId: null,
  };
}

export function resolveTrackLabelContextTarget(target) {
  const labelNode = target?.closest?.("[data-track-label-role][data-track-label-selectable='1']");
  if (!labelNode) {
    return null;
  }
  const trackRole = normalizeTrackRole(labelNode.getAttribute("data-track-label-role"));
  if (!trackRole) {
    return null;
  }
  return {
    trackRole,
    source: normalizeSubviewTrackSource(labelNode.getAttribute("data-track-label-source")),
    isMirror: labelNode.getAttribute("data-track-label-is-mirror") === "1",
    datasetId: normalizeSupportDatasetId(labelNode.getAttribute("data-track-label-dataset-id")),
    phasedTrackId: normalizeSupportDatasetId(labelNode.getAttribute("data-track-label-phased-track-id")),
    phasedHaplotypeKey: String(labelNode.getAttribute("data-track-label-phased-haplotype-key") || "").trim(),
  };
}

export function resolveSubviewTrackPairContextTarget(target) {
  const trackNode = target?.closest?.(
    "[data-subview-track-pair-role][data-subview-track-pair-contig-id]",
  );
  if (!trackNode) {
    return null;
  }
  const trackRole = normalizeTrackRole(trackNode.getAttribute("data-subview-track-pair-role"));
  const assemblyCtgId = normalizeSupportDatasetId(
    trackNode.getAttribute("data-subview-track-pair-contig-id"),
  );
  if (!trackRole || !assemblyCtgId) {
    return null;
  }
  return {
    trackRole,
    assemblyCtgId,
    datasetId: normalizeSupportDatasetId(
      trackNode.getAttribute("data-subview-track-pair-dataset-id"),
    ),
    isMirror: trackNode.getAttribute("data-subview-track-pair-is-mirror") === "1",
    slot: String(trackNode.getAttribute("data-subview-track-slot") || "").trim().toLowerCase(),
    refOrient: String(trackNode.getAttribute("data-subview-track-ref-orient") || "").trim(),
    phasedTrackId: normalizeSupportDatasetId(
      trackNode.getAttribute("data-subview-track-pair-phased-track-id"),
    ),
    phasedTrackItemId: normalizeSupportDatasetId(
      trackNode.getAttribute("data-subview-track-pair-phased-track-item-id"),
    ),
    phasedHaplotypeKey: String(
      trackNode.getAttribute("data-subview-track-pair-phased-haplotype-key") || "",
    ).trim(),
  };
}

export function resolveSubviewAnchorEdgeContextTarget(target) {
  const node = target?.closest?.("[data-subview-anchor-hit-key][data-subview-anchor-edge]");
  if (!node) {
    return null;
  }
  const kind = String(node.getAttribute("data-subview-anchor-kind") || "evidence").trim();
  const manualAnchorId = String(node.getAttribute("data-subview-manual-anchor-id") || "").trim();
  if (kind === "manual" && manualAnchorId) {
    return {
      kind: "manual",
      manualAnchorId,
      active: true,
    };
  }
  const hitKey = String(node.getAttribute("data-subview-anchor-hit-key") || "").trim();
  const edge = String(node.getAttribute("data-subview-anchor-edge") || "").trim().toLowerCase();
  if (!hitKey || (edge !== "left" && edge !== "right")) {
    return null;
  }
  return {
    kind: "evidence",
    hitKey,
    edge,
    active: node.getAttribute("data-subview-anchor-active") === "1",
    topEndpointKey: String(node.getAttribute("data-subview-anchor-top-endpoint-key") || "").trim(),
    bottomEndpointKey: String(node.getAttribute("data-subview-anchor-bottom-endpoint-key") || "").trim(),
    topContigId: normalizeSupportDatasetId(node.getAttribute("data-subview-anchor-top-contig-id")),
    bottomContigId: normalizeSupportDatasetId(node.getAttribute("data-subview-anchor-bottom-contig-id")),
    topCutBp: normalizeSupportDatasetId(node.getAttribute("data-subview-anchor-top-cut-bp")),
    bottomCutBp: normalizeSupportDatasetId(node.getAttribute("data-subview-anchor-bottom-cut-bp")),
    topLengthBp: normalizeSupportDatasetId(node.getAttribute("data-subview-anchor-top-length-bp")),
    bottomLengthBp: normalizeSupportDatasetId(node.getAttribute("data-subview-anchor-bottom-length-bp")),
  };
}

export function resolveSubviewHitContextTarget(target) {
  const node = target?.closest?.("[data-subview-hit-key]");
  if (!node) {
    return null;
  }
  const hitKey = String(node.getAttribute("data-subview-hit-key") || "").trim();
  if (!hitKey) {
    return null;
  }
  return {
    hitKey,
    leftActive: node.getAttribute("data-subview-hit-left-active") === "1",
    rightActive: node.getAttribute("data-subview-hit-right-active") === "1",
  };
}

export function resolveSubviewFragmentContextTarget(target) {
  const node = target?.closest?.("[data-subview-fragment-key][data-subview-fragment-contig-id]");
  if (!node) {
    return null;
  }
  const fragmentKey = String(node.getAttribute("data-subview-fragment-key") || "").trim();
  const assemblyCtgId = normalizeSupportDatasetId(
    node.getAttribute("data-subview-fragment-contig-id"),
  );
  const trackRole = normalizeTrackRole(node.getAttribute("data-subview-fragment-role"));
  const start = normalizeSupportDatasetId(node.getAttribute("data-subview-fragment-start"));
  const end = normalizeSupportDatasetId(node.getAttribute("data-subview-fragment-end"));
  if (!fragmentKey || !assemblyCtgId || !trackRole || !start || !end) {
    return null;
  }
  return {
    fragmentKey,
    assemblyCtgId,
    slot: String(node.getAttribute("data-subview-fragment-slot") || "").trim().toLowerCase(),
    trackRole,
    start,
    end,
    ctgName: String(node.getAttribute("data-subview-fragment-ctg-name") || "").trim(),
    datasetId: normalizeSupportDatasetId(node.getAttribute("data-subview-fragment-dataset-id")),
    isMirror: node.getAttribute("data-subview-fragment-is-mirror") === "1",
    refOrient: String(node.getAttribute("data-subview-fragment-ref-orient") || "").trim(),
    sourceKind: String(node.getAttribute("data-subview-fragment-source-kind") || "").trim(),
    referenceChrId: normalizeSupportDatasetId(
      node.getAttribute("data-subview-fragment-reference-chr-id"),
    ),
    referenceChrName: String(node.getAttribute("data-subview-fragment-reference-chr-name") || "").trim(),
    segmentStartBp: normalizeSupportDatasetId(
      node.getAttribute("data-subview-fragment-segment-start-bp"),
    ),
    segmentEndBp: normalizeSupportDatasetId(
      node.getAttribute("data-subview-fragment-segment-end-bp"),
    ),
    phasedTrackId: normalizeSupportDatasetId(
      node.getAttribute("data-subview-fragment-phased-track-id"),
    ),
    phasedTrackItemId: normalizeSupportDatasetId(
      node.getAttribute("data-subview-fragment-phased-track-item-id"),
    ),
    phasedHaplotypeKey: String(
      node.getAttribute("data-subview-fragment-phased-haplotype-key") || "",
    ).trim(),
  };
}

export function resolveDeletedCtgContextTarget(target) {
  const node = target?.closest?.("[data-deleted-ctg-record-id]");
  if (!node) {
    return null;
  }
  const deletedCtgRecordId = normalizeSupportDatasetId(node.getAttribute("data-deleted-ctg-record-id"));
  if (!deletedCtgRecordId) {
    return null;
  }
  return {
    deletedCtgRecordId,
    assemblyCtgId: normalizeSupportDatasetId(node.getAttribute("data-deleted-assembly-ctg-id")),
  };
}

export function resolveFinalPathGraphSegmentContextTarget(target) {
  const graphCard = target?.closest?.(".final-path-card[data-final-path-view-mode='graph']");
  if (!graphCard) {
    return null;
  }
  const node = target?.closest?.("[data-final-path-segment-id][data-final-path-segment-type]");
  if (!node) {
    return null;
  }
  const segmentId = String(node.getAttribute("data-final-path-segment-id") || "").trim();
  const segmentType = String(node.getAttribute("data-final-path-segment-type") || "").trim().toLowerCase();
  if (!segmentId || (segmentType !== "ctg" && segmentType !== "gap")) {
    return null;
  }
  const targetChrName = String(
    node.getAttribute("data-final-path-target-chr-name")
    || node.closest?.("[data-final-path-target-chr-name]")?.getAttribute?.("data-final-path-target-chr-name")
    || "",
  ).trim();
  return {
    segmentId,
    segmentType,
    ...(targetChrName ? { targetChrName } : {}),
  };
}

export function buildAssemblyContextMenuItems({
  ctgContext,
  trackLabelContext,
  subviewTrackPairContext,
  subviewHitContext,
  subviewAnchorEdgeContext,
  subviewFragmentContext,
  deletedCtgContext,
  finalPathSegmentContext,
  memberNode,
  store,
  host,
  actions,
  contextPoint = null,
}) {
  const contextMenuActions = normalizeAssemblyContextMenuActions(actions);
  const items = [];
  const state = store.getState();
  const i18n = getAssemblyI18n(state);
  const selectedTrackCtgIds = normalizeTrackSelectionCtgIds(state.assembly.trackSelectedCtgIds);
  const primarySelectedTrackCtgIds = filterPrimaryTrackSelectionCtgIds(
    selectedTrackCtgIds,
    state.assembly,
  );
  const selectedDeletedRecordIds = normalizeDeletedCtgRecordIds(state.assembly.selectedDeletedCtgRecordIds);
  const normalizedSubview = getSubviewState(state.assembly);
  const subviewSelections = getSubviewSelections(normalizedSubview);
  const subviewTrackSelections = getSubviewTrackSelections(normalizedSubview);
  const hiddenSubviewTrackPairCtgs = normalizeSubviewTrackPairHiddenCtgs(
    normalizedSubview.trackPairHiddenCtgs,
  );
  const selectedSubviewTrackPairCtgs = resolveFilteredSubviewTrackPairSelectionsFromAssembly(
    state.assembly,
  );

  const ctgTrackRole = String(ctgContext?.trackRole || "").trim();
  const contextCtgId = normalizeSupportDatasetId(ctgContext?.assemblyCtgId);
  const isMirrorTrackContext = ctgContext?.isMirror === true;
  const contextDatasetId = normalizeSupportDatasetId(ctgContext?.datasetId);
  const fallbackSupportDatasetId = normalizeSupportDatasetId(state.assembly.supportDatasetId);
  const resolvedSupportContextDatasetId =
    ctgTrackRole === "support" ? (contextDatasetId || fallbackSupportDatasetId) : null;
  const mirroredSupportKeySet = new Set(
    normalizeSupportMirroredCtgs(state.assembly.supportMirroredCtgs).map((entry) =>
      buildSupportMirrorKey(entry.datasetId, entry.assemblyCtgId),
    ),
  );
  const isMirroredSupportCtg =
    ctgTrackRole === "support" &&
    contextCtgId !== null &&
    resolvedSupportContextDatasetId !== null &&
    mirroredSupportKeySet.has(buildSupportMirrorKey(resolvedSupportContextDatasetId, contextCtgId));
  const isPrimaryCtgContext = Boolean(ctgContext) && ctgTrackRole !== "support";
  const isRefTrackContext = ctgTrackRole === "ref" || String(ctgContext?.sourceKind || "") === "ref_segment";
  const isPhasedCtgContext = ctgTrackRole === "phased";
  const phasedChrTracks = Array.isArray(state.assembly?.phasedChrTracks) ? state.assembly.phasedChrTracks : [];
  const isCurrentChrPhased = Boolean(state.assembly?.isChrPhased && phasedChrTracks.length);
  const suppressSubviewEntry = ctgTrackRole === "support";
  const canUsePrimaryBatchSelection =
    !deletedCtgContext &&
    !subviewTrackPairContext &&
    !memberNode &&
    primarySelectedTrackCtgIds.length > 1 &&
    (
      !ctgContext ||
      (isPrimaryCtgContext && contextCtgId !== null && primarySelectedTrackCtgIds.includes(contextCtgId))
    );

  const {
    enterSubviewFromTrackSelections,
    enterSubviewFromCandidates,
    setSubviewTrackPairCtgHidden,
    toggleSubviewContigFlip,
    deleteSelectedSubviewTrackPairCtgs,
    clearSubviewTrackPairHiddenCtgs,
    setSelectedPrimaryTrackCtgsHidden,
    deleteSelectedTrackCtgs,
    runBatchDeleteTrackCtgs,
    restoreSelectedDeletedCtgs,
    canEditTrackCtg,
    addFinalPathContigRelativeToSegment,
    addFinalPathGapRelativeToSegment,
    deleteFinalPathSegment,
    flipFinalPathSegment,
    toggleSupportTrackCtgMirror,
    togglePrimaryTrackCtgHidden,
    toggleSubviewAnchorEdge,
    copySubviewAnchorWithOffset,
    deleteSubviewManualAnchor,
    appendTrackContigToFinalPath,
    addTrackContigToPhasedTrack,
    removePhasedTrackItem,
    deletePhasedTrack,
    importAddCtgIntoTrack,
    setActiveHitsTrack,
    setAssemblyActionFeedback,
    openAssemblyContextMenuAt,
    applyEditorAction,
    promptForRenameCtg,
    promptForDeleteShorterThanLength,
    buildRenameCtgActionArgs,
    confirm,
    rerender,
  } = contextMenuActions;

  const resolvePhasedAppendTargets = (targetContext, { allowAnyPhasedTarget = false } = {}) => {
    const trackRole = normalizeTrackRole(targetContext?.trackRole);
    if (!trackRole) {
      return [];
    }
    const selectedChrName = String(state.assembly?.selectedChrName || "").trim();
    const allTargets = phasedChrTracks
      .map((track) => {
        const haplotypeKey = String(track?.haplotypeKey || "").trim();
        const label = String(track?.label || "").trim();
        if (!haplotypeKey) {
          return null;
        }
        return {
          phasedTrackId: normalizeSupportDatasetId(track?.phasedTrackId),
          haplotypeKey,
          label: label || (selectedChrName ? `${selectedChrName}${haplotypeKey}` : haplotypeKey),
        };
      })
      .filter((target) => target && target.label);
    if (trackRole === "phased") {
      if (allowAnyPhasedTarget && allTargets.length) {
        return allTargets;
      }
      const phasedTrackId = normalizeSupportDatasetId(targetContext?.phasedTrackId);
      const haplotypeKey = String(targetContext?.phasedHaplotypeKey || "").trim();
      const matched = allTargets.find((target) =>
        (phasedTrackId !== null && target.phasedTrackId === phasedTrackId)
        || (haplotypeKey && target.haplotypeKey === haplotypeKey),
      );
      if (matched) {
        return [matched];
      }
      if (haplotypeKey) {
        return [{
          phasedTrackId,
          haplotypeKey,
          label: selectedChrName ? `${selectedChrName}${haplotypeKey}` : haplotypeKey,
        }];
      }
      return [];
    }
    return isCurrentChrPhased && (trackRole === "primary" || trackRole === "support")
      ? allTargets
      : [];
  };

  const pushAppendTrackContigItems = (targetContext, options = {}) => {
    const phasedTargets = resolvePhasedAppendTargets(targetContext, options);
    if (phasedTargets.length) {
      phasedTargets.forEach((phasedTarget) => {
        const { haplotypeKey } = phasedTarget;
        items.push({
          label: tAssembly(state, "contextMenu.appendToPhasedPath", { key: haplotypeKey }),
          run: async () => {
            await appendTrackContigToFinalPath(host, store, targetContext, {
              targetChrName: phasedTarget.label,
              activePhasedTrackKey: haplotypeKey,
            });
          },
        });
      });
      return;
    }
    items.push({
      label: i18n.contextMenu.appendToPath,
      run: async () => {
        await appendTrackContigToFinalPath(host, store, targetContext);
      },
    });
  };

  const attachPhasedSubviewIdentity = (targetContext, sourceContext) => {
    const phasedTrackId = normalizeSupportDatasetId(sourceContext?.phasedTrackId);
    const phasedTrackItemId = normalizeSupportDatasetId(sourceContext?.phasedTrackItemId);
    const phasedHaplotypeKey = String(sourceContext?.phasedHaplotypeKey || "").trim();
    if (phasedTrackId !== null) {
      targetContext.phasedTrackId = phasedTrackId;
    }
    if (phasedTrackItemId !== null) {
      targetContext.phasedTrackItemId = phasedTrackItemId;
    }
    if (phasedHaplotypeKey) {
      targetContext.phasedHaplotypeKey = phasedHaplotypeKey;
    }
    return targetContext;
  };

  const pushSubviewHitAnchorItems = (hitContext) => {
    if (!hitContext?.hitKey) {
      return;
    }
    items.push({
      label: hitContext.leftActive ? i18n.contextMenu.leftAnchorOff : i18n.contextMenu.leftAnchorOn,
      run: async () => {
        toggleSubviewAnchorEdge(host, store, {
          hitKey: hitContext.hitKey,
          edge: "left",
        });
      },
    });
    items.push({
      label: hitContext.rightActive ? i18n.contextMenu.rightAnchorOff : i18n.contextMenu.rightAnchorOn,
      run: async () => {
        toggleSubviewAnchorEdge(host, store, {
          hitKey: hitContext.hitKey,
          edge: "right",
        });
      },
    });
  };

  const addSubviewTrackPairActions = (targetContext, { includeAppend = true } = {}) => {
    const normalizedTrackRole = normalizeTrackRole(targetContext?.trackRole);
    const assemblyCtgId = normalizeSupportDatasetId(targetContext?.assemblyCtgId);
    if (!normalizedTrackRole || !assemblyCtgId) {
      return;
    }
    const subviewCtgContext = {
      assemblyCtgId,
      slot: String(targetContext?.slot || "").trim().toLowerCase(),
      trackRole: normalizedTrackRole,
      datasetId: normalizeSupportDatasetId(targetContext?.datasetId),
      isMirror: targetContext?.isMirror === true,
      refOrient: String(targetContext?.refOrient || "").trim(),
    };
    attachPhasedSubviewIdentity(subviewCtgContext, targetContext);
    if (includeAppend) {
      pushAppendTrackContigItems(subviewCtgContext, { allowAnyPhasedTarget: true });
    }
    if (canEditTrackCtg(subviewCtgContext, state.assembly)) {
      items.push({
        label: i18n.contextMenu.flipContig,
        run: async () => {
          toggleSubviewContigFlip(host, store, {
            slot: subviewCtgContext.slot,
            assemblyCtgId,
          });
        },
      });
    }
    if (String(normalizedSubview.summary?.mode || "") === "track-pair") {
      items.push({
        label: i18n.contextMenu.deleteLocalSubviewContig,
        run: async () => {
          setSubviewTrackPairCtgHidden(host, store, {
            trackRole: normalizedTrackRole,
            contigId: assemblyCtgId,
            hidden: true,
          });
        },
      });
    }
  };

  if (subviewAnchorEdgeContext) {
    if (subviewAnchorEdgeContext.kind === "manual") {
      items.push({
        label: i18n.contextMenu.deleteManualAnchor,
        run: async () => {
          await deleteSubviewManualAnchor(host, store, {
            manualAnchorId: subviewAnchorEdgeContext.manualAnchorId,
          });
        },
      });
      return items;
    }
    const nextActive = subviewAnchorEdgeContext.active !== true;
    items.push({
      label: nextActive ? i18n.contextMenu.anchorOn : i18n.contextMenu.anchorOff,
      run: async () => {
        await toggleSubviewAnchorEdge(host, store, {
          hitKey: subviewAnchorEdgeContext.hitKey,
          edge: subviewAnchorEdgeContext.edge,
          active: nextActive,
        });
      },
    });
    if (subviewAnchorEdgeContext.active === true) {
      items.push({
        label: i18n.contextMenu.copyAnchorWithOffset,
        run: async () => {
          await copySubviewAnchorWithOffset(host, store, subviewAnchorEdgeContext);
        },
      });
    }
    return items;
  }

  if (subviewHitContext && !subviewFragmentContext) {
    pushSubviewHitAnchorItems(subviewHitContext);
    return items;
  }

  if (subviewFragmentContext) {
    pushSubviewHitAnchorItems(subviewHitContext);
    const fragmentAppendContext = attachPhasedSubviewIdentity({
      assemblyCtgId: subviewFragmentContext.assemblyCtgId,
      slot: subviewFragmentContext.slot,
      trackRole: subviewFragmentContext.trackRole,
      datasetId: subviewFragmentContext.datasetId,
      isMirror: subviewFragmentContext.isMirror === true,
      refOrient: subviewFragmentContext.refOrient,
      start: subviewFragmentContext.start,
      end: subviewFragmentContext.end,
      sourceKind: subviewFragmentContext.sourceKind,
      referenceChrId: subviewFragmentContext.referenceChrId,
      referenceChrName: subviewFragmentContext.referenceChrName,
      segmentStartBp: subviewFragmentContext.segmentStartBp,
      segmentEndBp: subviewFragmentContext.segmentEndBp,
    }, subviewFragmentContext);
    pushAppendTrackContigItems(fragmentAppendContext, { allowAnyPhasedTarget: true });
    addSubviewTrackPairActions(
      {
        assemblyCtgId: subviewFragmentContext.assemblyCtgId,
        slot: subviewFragmentContext.slot,
        trackRole: subviewFragmentContext.trackRole,
        datasetId: subviewFragmentContext.datasetId,
        isMirror: subviewFragmentContext.isMirror === true,
        refOrient: subviewFragmentContext.refOrient,
        phasedTrackId: subviewFragmentContext.phasedTrackId,
        phasedTrackItemId: subviewFragmentContext.phasedTrackItemId,
        phasedHaplotypeKey: subviewFragmentContext.phasedHaplotypeKey,
      },
      { includeAppend: false },
    );
    return items;
  }

  if (finalPathSegmentContext) {
    const segmentId = String(finalPathSegmentContext.segmentId || "").trim();
    const segmentType = String(finalPathSegmentContext.segmentType || "").trim().toLowerCase();
    const targetChrName = String(finalPathSegmentContext.targetChrName || "").trim();
    if (!segmentId) {
      return items;
    }
    const targetArgs = targetChrName ? { targetChrName } : {};
    items.push({
      label: i18n.contextMenu.finalPathDeleteSegment,
      run: async () => {
        await deleteFinalPathSegment(host, store, { segmentId, ...targetArgs });
      },
    });
    if (segmentType === "ctg") {
      items.push({
        label: i18n.contextMenu.finalPathFlipSegment,
        run: async () => {
          await flipFinalPathSegment(host, store, { segmentId, ...targetArgs });
        },
      });
      items.push({
        label: i18n.contextMenu.finalPathAddGapLeft,
        run: async () => {
          await addFinalPathGapRelativeToSegment(host, store, { segmentId, placement: "before", ...targetArgs });
        },
      });
      items.push({
        label: i18n.contextMenu.finalPathAddGapRight,
        run: async () => {
          await addFinalPathGapRelativeToSegment(host, store, { segmentId, placement: "after", ...targetArgs });
        },
      });
      items.push({
        label: i18n.contextMenu.finalPathAddCtgLeft,
        run: async () => {
          await addFinalPathContigRelativeToSegment(host, store, { segmentId, placement: "before", ...targetArgs });
        },
      });
      items.push({
        label: i18n.contextMenu.finalPathAddCtgRight,
        run: async () => {
          await addFinalPathContigRelativeToSegment(host, store, { segmentId, placement: "after", ...targetArgs });
        },
      });
    }
    return items;
  }

  if (ctgContext && !deletedCtgContext && !memberNode && !subviewTrackPairContext) {
    if (isPhasedCtgContext) {
      const phasedTrackItemId = normalizeSupportDatasetId(ctgContext.phasedTrackItemId);
      pushAppendTrackContigItems(ctgContext, { allowAnyPhasedTarget: true });
      if (contextCtgId) {
        items.push({
          label: i18n.contextMenu.flipContig,
          run: async () => {
            await applyEditorAction(host, store, {
              action: "flip-ctg",
              args: { assemblyCtgId: contextCtgId, phasedTrackItemId },
              keepCurrentCtg: true,
              localRefresh: true,
              phasedOnlyRefresh: true,
            });
          },
        });
      }
      if (phasedTrackItemId) {
        items.push({
          label: i18n.contextMenu.removeFromPhasedTrack,
          run: async () => {
            await removePhasedTrackItem(host, store, { phasedTrackItemId });
          },
        });
      }
      return items;
    }
    if (isCurrentChrPhased && (ctgTrackRole === "primary" || ctgTrackRole === "support")) {
      const phasedTargets = phasedChrTracks
        .map((track) => {
          const haplotypeKey = String(track?.haplotypeKey || "").trim();
          if (!haplotypeKey) {
            return null;
          }
          return {
            phasedTrackId: normalizeSupportDatasetId(track?.phasedTrackId),
            haplotypeKey,
            label: String(track?.label || haplotypeKey).trim(),
          };
        })
        .filter(Boolean);
      if (ctgTrackRole === "primary") {
        phasedTargets.forEach((phasedTarget) => {
          const { haplotypeKey } = phasedTarget;
          items.push({
            label: tAssembly(state, "contextMenu.addToPhasedTrack", { key: haplotypeKey }),
            run: async () => {
              await addTrackContigToPhasedTrack(host, store, {
                ...phasedTarget,
                assemblyCtgId: ctgContext.assemblyCtgId,
              });
            },
          });
        });
      }
      phasedTargets.forEach((phasedTarget) => {
        const { haplotypeKey } = phasedTarget;
        items.push({
          label: tAssembly(state, "contextMenu.appendToPhasedPath", { key: haplotypeKey }),
          run: async () => {
            await appendTrackContigToFinalPath(host, store, ctgContext, {
              targetChrName: phasedTarget.label,
              activePhasedTrackKey: haplotypeKey,
            });
          },
        });
      });
    } else {
      items.push({
        label: i18n.contextMenu.appendToPath,
        run: async () => {
          await appendTrackContigToFinalPath(host, store, ctgContext);
        },
      });
    }
  }
  if (subviewTrackPairContext && !deletedCtgContext && !memberNode) {
    addSubviewTrackPairActions(subviewTrackPairContext);
  }
  if (
    !ctgContext &&
    !trackLabelContext &&
    !subviewTrackPairContext &&
    !deletedCtgContext &&
    !memberNode &&
    String(normalizedSubview.summary?.mode || "") === "track-pair" &&
    selectedSubviewTrackPairCtgs.length
  ) {
    items.push({
      label: tAssembly(state, "contextMenu.deleteLocalSubviewSelected", {
        count: selectedSubviewTrackPairCtgs.length,
      }),
      run: async () => {
        await deleteSelectedSubviewTrackPairCtgs(host, store, selectedSubviewTrackPairCtgs);
      },
    });
  }
  if (
    !ctgContext &&
    !trackLabelContext &&
    !subviewTrackPairContext &&
    !deletedCtgContext &&
    !memberNode &&
    String(normalizedSubview.summary?.mode || "") === "track-pair" &&
    hiddenSubviewTrackPairCtgs.length
  ) {
    items.push({
      label: tAssembly(state, "contextMenu.restoreSubviewHidden", {
        count: hiddenSubviewTrackPairCtgs.length,
      }),
      run: async () => {
        clearSubviewTrackPairHiddenCtgs(host, store);
      },
    });
  }

  if (
    !ctgContext &&
    !subviewTrackPairContext &&
    !deletedCtgContext &&
    !memberNode &&
    (trackLabelContext?.trackRole === "primary" || trackLabelContext?.trackRole === "support") &&
    trackLabelContext?.isMirror !== true
  ) {
    const currentProject = Array.isArray(state.initializer?.existingProjects)
      ? state.initializer.existingProjects.find((project) =>
        Number(project?.projectId || 0) === Number(state.session?.projectId || 0),
      )
      : null;
    const targetDatasetId = normalizeSupportDatasetId(trackLabelContext?.datasetId)
      || (trackLabelContext?.trackRole === "primary"
        ? normalizeSupportDatasetId(currentProject?.primaryDatasetId)
        : null);
    const targetChr = String(state.assembly?.selectedChrName || "").trim();
    const targetTrack = String(
      Array.isArray(state.initializer?.datasets)
        ? (() => {
          const matched = state.initializer.datasets.find((dataset) =>
            Number(dataset?.datasetId || 0) === targetDatasetId,
          );
          return matched?.name || matched?.label || "";
        })()
        : "",
    ).trim();
    if (targetChr && targetTrack) {
      items.push({
        label: i18n.contextMenu.addNewCtg,
        run: async () => {
          await importAddCtgIntoTrack(host, store, {
            targetChr,
            targetTrack,
            datasetId: targetDatasetId,
            trackRole: trackLabelContext.trackRole,
          });
        },
      });
    }
  }

  if (
    !ctgContext &&
    !subviewTrackPairContext &&
    !deletedCtgContext &&
    !memberNode &&
    trackLabelContext?.trackRole === "primary" &&
    trackLabelContext?.isMirror !== true
  ) {
    const nextHitsKey = state.assembly?.activeHitsTrackKey === "primary" ? "" : "primary";
    items.push({
      label: state.assembly?.activeHitsTrackKey === "primary"
        ? i18n.contextMenu.hideHits
        : i18n.contextMenu.showHits,
      run: async () => {
        setActiveHitsTrack(host, store, { trackKey: nextHitsKey });
      },
    });
    items.push({
      label: i18n.contextMenu.deleteShorterThanContigs,
      run: async () => {
        const rawThreshold = await promptForDeleteShorterThanLength(host, store, 100000);
        const thresholdBp = parseNonNegativeIntegerInput(rawThreshold);
        if (thresholdBp === null) {
          return;
        }
        const targetIds = resolvePrimaryTrackCtgsShorterThan(state.assembly, thresholdBp);
        if (!targetIds.length) {
          setAssemblyActionFeedback(host, store, {
            actionStatus: tAssembly(state, "contextMenu.deleteShorterThanNoMatches", {
              threshold: thresholdBp,
            }),
          });
          return;
        }
        if (!(await confirm(tAssembly(state, "contextMenu.deleteShorterThanContigsConfirm", {
          count: targetIds.length,
          threshold: thresholdBp,
        }), { host, store }))) {
          return;
        }
        await runBatchDeleteTrackCtgs(host, store, targetIds);
      },
    });
  }

  if (
    !ctgContext &&
    !subviewTrackPairContext &&
    !deletedCtgContext &&
    !memberNode &&
    trackLabelContext?.trackRole === "phased" &&
    trackLabelContext?.isMirror !== true
  ) {
    const haplotypeKey = String(trackLabelContext.phasedHaplotypeKey || "").trim();
    if (haplotypeKey) {
      items.push({
        label: state.assembly?.activeHitsTrackKey === haplotypeKey
          ? i18n.contextMenu.hideHits
          : i18n.contextMenu.showHits,
        run: async () => {
          setActiveHitsTrack(host, store, { trackKey: haplotypeKey });
        },
      });
    }
    const phasedTrackId = normalizeSupportDatasetId(trackLabelContext.phasedTrackId);
    if (phasedTrackId) {
      items.push({
        label: i18n.contextMenu.deletePhasedTrack,
        run: async () => {
          if (!(await confirm(tAssembly(state, "contextMenu.deletePhasedTrackConfirm", { key: haplotypeKey }), { host, store }))) {
            return;
          }
          await deletePhasedTrack(host, store, { phasedTrackId, haplotypeKey });
        },
      });
    }
  }

  if (canUsePrimaryBatchSelection) {
    items.push({
      label: tAssembly(state, "contextMenu.hideSelectedContigs", {
        count: primarySelectedTrackCtgIds.length,
      }),
      run: async () => {
        await setSelectedPrimaryTrackCtgsHidden(host, store, primarySelectedTrackCtgIds, true);
      },
    });
    items.push({
      label: tAssembly(state, "contextMenu.showSelectedContigs", {
        count: primarySelectedTrackCtgIds.length,
      }),
      run: async () => {
        await setSelectedPrimaryTrackCtgsHidden(host, store, primarySelectedTrackCtgIds, false);
      },
    });
    items.push({
      label: tAssembly(state, "contextMenu.deleteSelectedContigs", {
        count: primarySelectedTrackCtgIds.length,
      }),
      run: async () => {
        await deleteSelectedTrackCtgs(host, store, primarySelectedTrackCtgIds);
      },
    });
  }

  if (
    !ctgContext &&
    !subviewTrackPairContext &&
    !deletedCtgContext &&
    !memberNode &&
    primarySelectedTrackCtgIds.length &&
    !canUsePrimaryBatchSelection
  ) {
    items.push({
      label: tAssembly(state, "contextMenu.deleteSelectedContigs", {
        count: primarySelectedTrackCtgIds.length,
      }),
      run: async () => {
        await deleteSelectedTrackCtgs(host, store, primarySelectedTrackCtgIds);
      },
    });
  }

  if (!ctgContext && !subviewTrackPairContext && !deletedCtgContext && !memberNode && selectedDeletedRecordIds.length) {
    items.push({
      label: tAssembly(state, "contextMenu.restoreSelectedDeleted", {
        count: selectedDeletedRecordIds.length,
      }),
      run: async () => {
        await restoreSelectedDeletedCtgs(host, store, selectedDeletedRecordIds);
      },
    });
  }

  if (ctgContext && !canUsePrimaryBatchSelection) {
    const { assemblyCtgId: ctgId } = ctgContext;
    const isSupportTrackCtg = ctgTrackRole === "support";
    if (ctgId > 0 && isSupportTrackCtg && isMirrorTrackContext) {
      if (resolvedSupportContextDatasetId !== null && isMirroredSupportCtg) {
        items.push({
          label: i18n.contextMenu.unmirrorContig,
          run: async () => {
            await toggleSupportTrackCtgMirror(host, store, {
              datasetId: resolvedSupportContextDatasetId,
              assemblyCtgId: ctgId,
              shouldMirror: false,
            });
          },
        });
      }
    } else if (ctgId > 0 && !isRefTrackContext && canEditTrackCtg(ctgContext, state.assembly)) {
      const hiddenPrimaryCtgIds = new Set(
        filterPrimaryTrackSelectionCtgIds(state.assembly.hiddenPrimaryCtgIds, state.assembly),
      );
      const isHiddenPrimaryTrackCtg = !isSupportTrackCtg && hiddenPrimaryCtgIds.has(ctgId);
      items.push({
        label: i18n.contextMenu.flipContig,
        run: async () => {
          await applyEditorAction(host, store, {
            action: "flip-ctg",
            args: { assemblyCtgId: ctgId },
            keepCurrentCtg: true,
            localRefresh: true,
          });
        },
      });
      items.push({
        label: i18n.contextMenu.renameContig,
        run: async () => {
          const nextName = promptForRenameCtg(host, store, ctgId);
          const actionArgs = buildRenameCtgActionArgs(ctgId, nextName);
          if (!actionArgs) {
            return;
          }
          await applyEditorAction(host, store, {
            action: "rename-ctg",
            args: actionArgs,
            keepCurrentCtg: true,
          });
        },
      });
      if (isSupportTrackCtg && resolvedSupportContextDatasetId !== null) {
        items.push({
          label: isMirroredSupportCtg ? i18n.contextMenu.unmirrorContig : i18n.contextMenu.mirrorContig,
          run: async () => {
            await toggleSupportTrackCtgMirror(host, store, {
              datasetId: resolvedSupportContextDatasetId,
              assemblyCtgId: ctgId,
              shouldMirror: !isMirroredSupportCtg,
            });
          },
        });
      }
      if (!isSupportTrackCtg) {
        items.push({
          label: isHiddenPrimaryTrackCtg ? i18n.contextMenu.unhideContig : i18n.contextMenu.hideContig,
          run: async () => {
            await togglePrimaryTrackCtgHidden(host, store, ctgId, !isHiddenPrimaryTrackCtg);
          },
        });
        items.push({
          label: i18n.contextMenu.deleteContig,
          run: async () => {
            if (!(await confirm(tAssembly(state, "contextMenu.deleteContigConfirm", { assemblyCtgId: ctgId }), { host, store }))) {
              return;
            }
            await applyEditorAction(host, store, {
              action: "delete-ctg",
              args: { assemblyCtgId: ctgId },
              keepCurrentCtg: false,
            });
          },
        });
        items.push({
          label: i18n.contextMenu.moreContigActions,
          disabled: true,
          title: i18n.contextMenu.currentVersionUnavailable,
        });
      }
    }
  }

  if (memberNode) {
    const seqId = Number(memberNode.getAttribute("data-member-seq-id") || 0);
    const hidden = memberNode.getAttribute("data-member-hidden") === "1";
    if (seqId > 0) {
      items.push({
        label: i18n.contextMenu.alignmentDetails,
        disabled: true,
        title: i18n.contextMenu.currentVersionUnavailable,
      });
      items.push({
        label: i18n.contextMenu.anchorLinkage,
        disabled: true,
        title: i18n.contextMenu.currentVersionUnavailable,
      });
      items.push({
        label: tAssembly(state, "contextMenu.locateSeq", { seqId }),
        run: async () => {
          store.setState({
            assembly: {
              ...store.getState().assembly,
              selectedMemberSeqId: seqId,
            },
          });
          rerender(host, store);
        },
      });
      items.push({
        label: i18n.contextMenu.flipSequence,
        run: async () => {
          await applyEditorAction(host, store, {
            action: "flip-seq",
            args: { assemblySeqId: seqId },
            keepCurrentCtg: true,
          });
        },
      });
      items.push({
        label: hidden ? i18n.contextMenu.showSequence : i18n.contextMenu.hideSequence,
        run: async () => {
          await applyEditorAction(host, store, {
            action: hidden ? "show-seq" : "hide-seq",
            args: { assemblySeqId: seqId },
            keepCurrentCtg: true,
          });
        },
      });
    }
  }

  if (deletedCtgContext) {
    const deletedCtgRecordId = normalizeSupportDatasetId(deletedCtgContext.deletedCtgRecordId);
    const contextAssemblyCtgId = normalizeSupportDatasetId(deletedCtgContext.assemblyCtgId);
    const selected = selectedDeletedRecordIds.length
      ? selectedDeletedRecordIds
      : deletedCtgRecordId
        ? [deletedCtgRecordId]
        : [];
    if (selected.length > 1) {
      items.push({
        label: tAssembly(state, "contextMenu.restoreSelectedDeleted", {
          count: selected.length,
        }),
        run: async () => {
          await restoreSelectedDeletedCtgs(host, store, selected);
        },
      });
    } else if (deletedCtgRecordId) {
      items.push({
        label: contextAssemblyCtgId
          ? tAssembly(state, "contextMenu.restoreDeletedContig", { assemblyCtgId: contextAssemblyCtgId })
          : tAssembly(state, "contextMenu.restoreDeletedRecord", { deletedCtgRecordId }),
        run: async () => {
          await restoreSelectedDeletedCtgs(host, store, [deletedCtgRecordId]);
        },
      });
    }
  }

  return items;
}
