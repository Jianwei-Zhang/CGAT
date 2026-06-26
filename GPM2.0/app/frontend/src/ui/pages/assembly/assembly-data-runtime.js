function normalizeFinalPathViewMode(value) {
  return normalizeFinalPathViewModeState(value);
}

function normalizeMembersCardCollapsed(value) {
  return value === false ? false : true;
}

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizeOrient(value) {
  return normalizeString(value) === "-" ? "-" : "+";
}

function backfillFinalPathOriginIds(finalPathByChr, chrName, primaryCtgs, supportCtgs) {
  const source = finalPathByChr && typeof finalPathByChr === "object" && !Array.isArray(finalPathByChr)
    ? finalPathByChr
    : {};
  const normalizedChrName = normalizeString(chrName);
  if (!normalizedChrName) {
    return source;
  }
  const entry = source[normalizedChrName];
  if (!entry || !Array.isArray(entry.segments) || !entry.segments.length) {
    return source;
  }

  const originByCtgId = new Map();
  [...(Array.isArray(primaryCtgs) ? primaryCtgs : []), ...(Array.isArray(supportCtgs) ? supportCtgs : [])]
    .forEach((ctg) => {
      const ctgId = Number(ctg?.assemblyCtgId || 0);
      const originId = normalizeString(ctg?.originId);
      if (ctgId > 0 && originId) {
        originByCtgId.set(ctgId, originId);
      }
    });

  let changed = false;
  const nextSegments = entry.segments.map((segment) => {
    if (normalizeString(segment?.type).toLowerCase() === "gap") {
      return segment;
    }
    if (normalizeString(segment?.originId)) {
      return segment;
    }
    const ctgId = Number(segment?.assemblyCtgId || 0);
    const originId = ctgId > 0 ? originByCtgId.get(ctgId) || "" : "";
    if (!originId) {
      return segment;
    }
    changed = true;
    return {
      ...segment,
      originId,
    };
  });

  if (!changed) {
    return source;
  }
  return {
    ...source,
    [normalizedChrName]: {
      ...entry,
      segments: nextSegments,
    },
  };
}

function resolveSelectedChrName(chromosomes, currentChrName, keepCurrentChr) {
  if (!chromosomes.length) {
    return "";
  }
  if (
    keepCurrentChr
    && currentChrName
    && chromosomes.some((item) => item.chrName === currentChrName)
  ) {
    return currentChrName;
  }
  return chromosomes[0].chrName;
}

function resolveSelectedCtgId(ctgs, currentCtgId, keepCurrentCtg) {
  if (!ctgs.length) {
    return null;
  }
  if (
    keepCurrentCtg
    && currentCtgId
    && ctgs.some((item) => item.assemblyCtgId === currentCtgId)
  ) {
    return currentCtgId;
  }
  return ctgs[0].assemblyCtgId;
}

function resolveSelectedMemberSeqId(detail, previousSeqId) {
  const members = detail?.members || [];
  if (!members.length) {
    return null;
  }
  if (previousSeqId && members.some((item) => item.assemblySeqId === previousSeqId)) {
    return previousSeqId;
  }
  return members[0].assemblySeqId;
}

function containsAssemblyCtgId(primaryCtgs, supportCtgs, assemblyCtgId) {
  const targetId = Number(assemblyCtgId || 0);
  if (!targetId) {
    return false;
  }
  return [...(Array.isArray(primaryCtgs) ? primaryCtgs : []), ...(Array.isArray(supportCtgs) ? supportCtgs : [])]
    .some((ctg) => Number(ctg?.assemblyCtgId || 0) === targetId);
}

function containsDeletedCtgRecordId(deletedCtgs, deletedCtgRecordId) {
  const targetId = Number(deletedCtgRecordId || 0);
  if (!targetId) {
    return false;
  }
  return (Array.isArray(deletedCtgs) ? deletedCtgs : []).some(
    (ctg) => Number(ctg?.deletedCtgRecordId || 0) === targetId,
  );
}

function createEmptySideData() {
  return {
    detail: null,
    candidates: {
      moveTargetCtgs: [],
      addSeqCandidates: [],
    },
  };
}

function buildReferenceTrackMemberRuntimeId(item, index) {
  const existingId = Number(item?.assemblyCtgId || 0);
  if (Number.isFinite(existingId) && existingId > 0) {
    return Math.trunc(existingId);
  }
  const referenceChrId = Math.max(1, Number(item?.referenceChrId || 1));
  const segmentOrder = Math.max(1, Number(item?.segmentOrder || index + 1));
  return Math.trunc(2_000_000_000 + referenceChrId * 100_000 + segmentOrder);
}

function normalizeReferenceTrackMembers(items) {
  return (Array.isArray(items) ? items : []).map((item, index) => {
    const segmentStartBp = Math.max(1, Number(item?.segmentStartBp || item?.anchorStart || 1));
    const segmentEndBp = Math.max(
      segmentStartBp,
      Number(item?.segmentEndBp || (segmentStartBp + Math.max(1, Number(item?.totalLength || 1)) - 1)),
    );
    return {
      ...item,
      sourceKind: String(item?.sourceKind || "ref_segment"),
      assemblyCtgId: buildReferenceTrackMemberRuntimeId(item, index),
      anchorStart: segmentStartBp,
      segmentStartBp,
      segmentEndBp,
      totalLength: Math.max(1, Number(item?.totalLength || (segmentEndBp - segmentStartBp + 1))),
      lengthBp: Math.max(1, Number(item?.lengthBp || item?.totalLength || (segmentEndBp - segmentStartBp + 1))),
      startBp: segmentStartBp,
      endBp: segmentEndBp,
      hits: Array.isArray(item?.hits) ? item.hits.map((hit) => ({ ...hit })) : [],
    };
  });
}

function normalizePhasedChrTracks(tracks, chrCtgs) {
  const ctgById = new Map(
    (Array.isArray(chrCtgs) ? chrCtgs : [])
      .map((ctg) => [Number(ctg?.assemblyCtgId || 0), ctg])
      .filter(([ctgId]) => ctgId > 0),
  );
  return (Array.isArray(tracks) ? tracks : [])
    .map((track) => ({
      ...track,
      phasedTrackId: Number(track?.phasedTrackId || 0),
      displayOrder: Number(track?.displayOrder || 0),
      haplotypeKey: normalizeString(track?.haplotypeKey),
      label: normalizeString(track?.label),
      items: (Array.isArray(track?.items) ? track.items : [])
        .map((item) => {
          const assemblyCtgId = Number(item?.assemblyCtgId || 0);
          const sourceCtg = ctgById.get(assemblyCtgId) || null;
          return {
            ...item,
            itemId: Number(item?.itemId || item?.phasedTrackItemId || 0),
            phasedTrackId: Number(item?.phasedTrackId || track?.phasedTrackId || 0),
            assemblyCtgId,
            displayOrder: Number(item?.displayOrder || 0),
            gapBeforePx: Number(item?.gapBeforePx ?? 20),
            orient: normalizeOrient(item?.orient ?? sourceCtg?.orient ?? sourceCtg?.refOrient),
            sourceCtg,
            missingSourceCtg: !sourceCtg,
          };
        })
        .sort((left, right) => left.displayOrder - right.displayOrder || left.itemId - right.itemId),
    }))
    .filter((track) => track.phasedTrackId > 0 && track.haplotypeKey)
    .sort((left, right) => left.displayOrder - right.displayOrder || left.phasedTrackId - right.phasedTrackId);
}

async function loadPhasedChrTracksForAssembly(deps, {
  state,
  currentProject,
  selectedChrName,
  chrCtgs,
}) {
  if (
    !currentProject?.phasedAssemblyEnabled
    || !selectedChrName
    || typeof deps?.listPhasedChrTracks !== "function"
  ) {
    return [];
  }
  const result = await deps.listPhasedChrTracks({
    workspaceRoot: state.session.workspacePath,
    projectId: state.session.projectId,
    parentChrName: selectedChrName,
  });
  return normalizePhasedChrTracks(result?.tracks, chrCtgs);
}

function resolveActivePhasedTrackKey(activeKeyByChr, selectedChrName, phasedChrTracks) {
  const availableKeys = new Set(phasedChrTracks.map((track) => track.haplotypeKey));
  const requested = normalizeString(activeKeyByChr?.[selectedChrName]);
  if (requested && availableKeys.has(requested)) {
    return requested;
  }
  return phasedChrTracks[0]?.haplotypeKey || "";
}

function resolveActiveHitsTrackKey(activeKeyByChr, selectedChrName, phasedChrTracks) {
  const requested = normalizeString(activeKeyByChr?.[selectedChrName]);
  if (requested === "__none") {
    return "";
  }
  if (requested === "primary") {
    return "primary";
  }
  if (requested && phasedChrTracks.some((track) => track.haplotypeKey === requested)) {
    return requested;
  }
  return "primary";
}

async function listReferenceTrackMembersOrEmpty(deps, args) {
  if (typeof deps?.listReferenceTrackMembers !== "function") {
    return { items: [] };
  }
  try {
    const result = await deps.listReferenceTrackMembers(args);
    return {
      items: normalizeReferenceTrackMembers(result?.items),
    };
  } catch {
    return { items: [] };
  }
}

function assertDataRuntimeDeps(deps, requirements) {
  const functionNames = Array.isArray(requirements) ? requirements : (requirements?.functions || []);
  const valueNames = Array.isArray(requirements) ? [] : (requirements?.values || []);
  const missingFunctions = functionNames.filter((name) => typeof deps?.[name] !== "function");
  const missingValues = valueNames.filter((name) => deps?.[name] == null);
  const missing = [...missingFunctions, ...missingValues];
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing assembly data runtime deps: ${missing.join(", ")}`);
}

export async function handleNewSequenceRowAction(host, store, payload, deps) {
  assertDataRuntimeDeps(deps, [
    "rerender",
    "setAssemblyActionFeedback",
  ]);
  const { action, assemblySeqId, seqName } = payload || {};
  if (action === "locate-seq") {
    const state = store.getState();
    if (!state.session.workspacePath || !state.session.projectId) {
      deps.setAssemblyActionFeedback(host, store, {
        actionError: tAssembly(state, "runtime.locateSeqMissingSession"),
        actionStatus: "",
      });
      return;
    }
    store.setState({
      assembly: {
        ...state.assembly,
        activeTab: "assembly",
        selectedMemberSeqId: assemblySeqId,
        actionError: "",
        actionStatus: tAssembly(state, "runtime.locatedSeqActionStatus", {
          seqLabel: seqName || assemblySeqId,
        }),
        summary: tAssembly(state, "runtime.locatedSeqSummary", {
          seqLabel: seqName || assemblySeqId,
        }),
      },
    });
    deps.rerender(host, store);
  }
}

export async function loadAssemblyView(host, store, options, deps) {
  assertDataRuntimeDeps(deps, {
    functions: [
      "buildClearedSubviewState",
      "buildSubviewTrackPairHiddenCtgKey",
      "buildSubviewTrackPairPoolsFromAssembly",
      "filterPrimaryTrackSelectionCtgIds",
      "filterSubviewTrackDragOffsetsBySummary",
      "filterSubviewTrackPairHiddenCtgs",
      "filterSubviewTrackPairSelectionCtgs",
      "filterTrackDragOffsets",
      "getCurrentProject",
      "getProjectAssemblyViewState",
      "getSupportDatasetOptions",
      "listChrViewCtgs",
      "listProjectChromosomes",
      "loadDatasetChrCtgs",
      "loadDeletedCtgsForChr",
      "loadSideDataForCtg",
      "mapAssemblyError",
      "normalizeDeletedCtgRecordIds",
      "normalizeSupportDatasetId",
      "normalizeSupportMirroredCtgs",
      "normalizeTrackSelectionCtgIds",
      "rerender",
    ],
    values: [],
  });
  const { keepCurrentChr, keepCurrentCtg } = options || {};
  const renderLoading = options?.renderLoading !== false;
  const state = store.getState();
  if (!state.session.workspacePath || !state.session.projectId) {
    return;
  }
  if (renderLoading) {
    store.setState({
      assembly: {
        ...state.assembly,
        loading: true,
        error: "",
        summary: tAssembly(state, "status.loadingChromosomes"),
      },
    });
    deps.rerender(host, store);
  }

  try {
    const normalizeFinalPathByChrImpl = deps.normalizeFinalPathByChr || normalizeFinalPathByChr;
    const currentProject = deps.getCurrentProject(state);
    const primaryDatasetId = deps.normalizeSupportDatasetId(currentProject?.primaryDatasetId);
    const supportDatasetOptions = deps.getSupportDatasetOptions(state, currentProject);
    const projectAssemblyViewState = await deps.getProjectAssemblyViewState({
      workspaceRoot: state.session.workspacePath,
      projectId: state.session.projectId,
    });
    const persistedSupportMirroredCtgs = deps.normalizeSupportMirroredCtgs(
      projectAssemblyViewState?.supportMirroredCtgs,
    );
    const persistedSupportDsCtgLenRulesByChr =
      projectAssemblyViewState?.supportDsCtgLenRulesByChr
      && typeof projectAssemblyViewState.supportDsCtgLenRulesByChr === "object"
      && !Array.isArray(projectAssemblyViewState.supportDsCtgLenRulesByChr)
        ? projectAssemblyViewState.supportDsCtgLenRulesByChr
        : {};
    const persistedSupportDatasetId = deps.normalizeSupportDatasetId(
      projectAssemblyViewState?.supportDatasetId,
    );
    const persistedFinalPathByChr = normalizeFinalPathByChrImpl(
      projectAssemblyViewState?.finalPathByChr,
    );
    const persistedHiddenPrimaryCtgIdsByChr = normalizeHiddenPrimaryCtgIdsByChr(
      projectAssemblyViewState?.hiddenPrimaryCtgIdsByChr,
    );
    const persistedFinalPathViewMode = normalizeFinalPathViewMode(
      projectAssemblyViewState?.finalPathViewMode,
    );
    const persistedMembersCardCollapsed = normalizeMembersCardCollapsed(
      projectAssemblyViewState?.membersCardCollapsed,
    );
    const persistedDegapProjectState = normalizeDegapProjectState(
      projectAssemblyViewState?.degapProjectState,
    );
    const persistedTrackView = projectAssemblyViewState?.trackView || state.assembly.trackView;
    const persistedTrackScrollState = projectAssemblyViewState?.trackScrollState
      || state.assembly.trackScrollState;
    const persistedSubviewTrackScrollState = projectAssemblyViewState?.subviewTrackScrollState
      || state.assembly.subviewTrackScrollState;
    const persistedFinalPathTrackScrollState = projectAssemblyViewState?.finalPathTrackScrollState
      || state.assembly.finalPathTrackScrollState;
    const currentSupportDatasetId = deps.normalizeSupportDatasetId(state.assembly.supportDatasetId);
    const supportDatasetId = supportDatasetOptions.some(
      (item) => item.datasetId === persistedSupportDatasetId,
    )
      ? persistedSupportDatasetId
      : supportDatasetOptions.some((item) => item.datasetId === currentSupportDatasetId)
        ? currentSupportDatasetId
        : supportDatasetOptions[0]?.datasetId || null;
    const shouldResetSubview = supportDatasetId !== currentSupportDatasetId;
    const nextSubview = shouldResetSubview
      ? deps.buildClearedSubviewState(state.assembly)
      : state.assembly.subview;

    const chromosomeResult = await deps.listProjectChromosomes({
      workspaceRoot: state.session.workspacePath,
      projectId: state.session.projectId,
    });
    const selectedChrName = resolveSelectedChrName(
      chromosomeResult.items,
      state.assembly.selectedChrName,
      keepCurrentChr,
    );

    const chrCtgResult = selectedChrName
      ? await deps.listChrViewCtgs({
          workspaceRoot: state.session.workspacePath,
          projectId: state.session.projectId,
          chrName: selectedChrName,
          datasetId: primaryDatasetId,
        })
      : { items: [] };
    const phasedChrTracks = await loadPhasedChrTracksForAssembly(deps, {
      state,
      currentProject,
      selectedChrName,
      chrCtgs: chrCtgResult.items,
    });
    const isChrPhased = Boolean(currentProject?.phasedAssemblyEnabled && phasedChrTracks.length);
    const activePhasedTrackKey = resolveActivePhasedTrackKey(
      state.assembly.activePhasedTrackKeyByChr,
      selectedChrName,
      phasedChrTracks,
    );
    const activeHitsTrackKey = resolveActiveHitsTrackKey(
      state.assembly.activeHitsTrackKeyByChr,
      selectedChrName,
      phasedChrTracks,
    );
    const refTrackMemberResult = selectedChrName
      ? await listReferenceTrackMembersOrEmpty(deps, {
          workspaceRoot: state.session.workspacePath,
          projectId: state.session.projectId,
          chrName: selectedChrName,
        })
      : { items: [] };
    const supportChrCtgs =
      selectedChrName && supportDatasetId
        ? await deps.loadDatasetChrCtgs(
            state.session.workspacePath,
            state.session.projectId,
            selectedChrName,
            supportDatasetId,
          )
        : [];
    const hydratedFinalPathByChr = backfillFinalPathOriginIds(
      persistedFinalPathByChr,
      selectedChrName,
      chrCtgResult.items,
      supportChrCtgs,
    );
    const persistedTrackDragOffsets = deps.filterTrackDragOffsets(
      projectAssemblyViewState?.trackDragOffsets,
      {
        ...state.assembly,
        chrCtgs: chrCtgResult.items,
        phasedChrTracks,
        refTrackMembers: refTrackMemberResult.items,
        supportChrCtgs,
      },
      { preserveUnmatchedSupportOffsets: true },
    );
    const persistedSubviewTrackDragOffsets = deps.filterSubviewTrackDragOffsetsBySummary(
      projectAssemblyViewState?.subviewTrackDragOffsets,
      nextSubview.summary,
    );
    const deletedCtgs = selectedChrName
      ? await deps.loadDeletedCtgsForChr(
          state.session.workspacePath,
          state.session.projectId,
          selectedChrName,
          primaryDatasetId,
        )
      : [];
    const selectedCtgId = resolveSelectedCtgId(
      chrCtgResult.items,
      state.assembly.selectedCtgId,
      keepCurrentCtg,
    );

    const sideData = await deps.loadSideDataForCtg(
      state.session.workspacePath,
      state.session.projectId,
      selectedCtgId,
    );
    const selectedMemberSeqId = resolveSelectedMemberSeqId(
      sideData.detail,
      state.assembly.selectedMemberSeqId,
    );
    const filteredTrackSelections = deps.normalizeTrackSelectionCtgIds(state.assembly.trackSelectedCtgIds).filter((ctgId) =>
      containsAssemblyCtgId(chrCtgResult.items, [], ctgId),
    );
    const persistedHiddenPrimaryCtgIds = deps.filterPrimaryTrackSelectionCtgIds(
      persistedHiddenPrimaryCtgIdsByChr[selectedChrName]
        || hydratedFinalPathByChr[selectedChrName]?.hiddenPrimaryCtgIds
        || projectAssemblyViewState?.hiddenPrimaryCtgIds,
      {
        ...state.assembly,
        chrCtgs: chrCtgResult.items,
      },
    );
    const filteredTrackDragOffsets = persistedTrackDragOffsets;
    const filteredSubviewTrackDragOffsets = persistedSubviewTrackDragOffsets;
    const subviewTrackPairPools = deps.buildSubviewTrackPairPoolsFromAssembly({
      ...state.assembly,
      chrCtgs: chrCtgResult.items,
      refTrackMembers: refTrackMemberResult.items,
      supportChrCtgs,
      selectedChrName,
    });
    const filteredSubviewTrackPairHiddenCtgs = deps.filterSubviewTrackPairHiddenCtgs(
      nextSubview.trackPairHiddenCtgs,
      subviewTrackPairPools,
    );
    const filteredSubviewTrackPairHiddenKeySet = new Set(
      filteredSubviewTrackPairHiddenCtgs.map((entry) =>
        deps.buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
      ),
    );
    const filteredSubviewTrackPairSelections = deps.filterSubviewTrackPairSelectionCtgs(
      nextSubview.trackPairSelectedCtgs,
      subviewTrackPairPools,
    ).filter(
      (entry) => !filteredSubviewTrackPairHiddenKeySet.has(
        deps.buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
      ),
    );
    const filteredDeletedSelections = deps.normalizeDeletedCtgRecordIds(
      state.assembly.selectedDeletedCtgRecordIds,
    ).filter((recordId) => containsDeletedCtgRecordId(deletedCtgs, recordId));

    store.setState({
      assembly: {
        ...store.getState().assembly,
        loading: false,
        referenceGenomeId: chromosomeResult.referenceGenomeId || 0,
        unplacedCtgCount: chromosomeResult.unplacedCtgCount || 0,
        unplacedBp: chromosomeResult.unplacedBp || 0,
        chromosomes: chromosomeResult.items,
        chrPickerOpen: false,
        selectedChrName,
        chrCtgs: chrCtgResult.items,
        phasedChrTracks,
        isChrPhased,
        activePhasedTrackKey,
        activeHitsTrackKey,
        refTrackMembers: refTrackMemberResult.items,
        supportDatasetId,
        trackView: persistedTrackView,
        supportDsCtgLenRulesByChr: persistedSupportDsCtgLenRulesByChr,
        supportDsCtgLenRulesDialogOpen: false,
        supportChrCtgs,
        deletedCtgs,
        selectedDeletedCtgRecordIds: filteredDeletedSelections,
        trackSelectedCtgIds: filteredTrackSelections,
        supportMirroredCtgs: persistedSupportMirroredCtgs,
        finalPathByChr: hydratedFinalPathByChr,
        finalPathViewMode: persistedFinalPathViewMode,
        degapProjectState: persistedDegapProjectState,
        degap: {
          ...store.getState().assembly.degap,
          jobs: persistedDegapProjectState.jobs,
          settingsPanelDismissed: persistedDegapProjectState.settingsPanelDismissed,
        },
        membersCardCollapsed: persistedMembersCardCollapsed,
        hiddenPrimaryCtgIds: persistedHiddenPrimaryCtgIds,
        hiddenPrimaryCtgIdsByChr: persistedHiddenPrimaryCtgIdsByChr,
        trackDragOffsets: filteredTrackDragOffsets,
        subviewTrackDragOffsets: filteredSubviewTrackDragOffsets,
        trackScrollState: persistedTrackScrollState,
        subviewTrackScrollState: persistedSubviewTrackScrollState,
        finalPathTrackScrollState: persistedFinalPathTrackScrollState,
        selectedCtgId,
        ctgDetail: sideData.detail,
        editCandidates: sideData.candidates,
        selectedMemberSeqId,
        subview: {
          ...nextSubview,
          trackPairHiddenCtgs: filteredSubviewTrackPairHiddenCtgs,
          trackPairSelectedCtgs: filteredSubviewTrackPairSelections,
        },
        summary: tAssembly(state, "runtime.loadViewLoadedSummary", {
          count: chromosomeResult.items.length,
        }),
      },
    });
  } catch (error) {
    const mappedError = deps.mapAssemblyError({ error, stateOrLocale: store.getState() });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        loading: false,
        supportChrCtgs: [],
        refTrackMembers: [],
        phasedChrTracks: [],
        isChrPhased: false,
        deletedCtgs: [],
        selectedDeletedCtgRecordIds: [],
        error: mappedError.userMessage,
        summary: tAssembly(store.getState(), "status.assemblyLoadFailed"),
      },
    });
  }

  deps.rerender(host, store);
}

export async function selectChromosome(host, store, chrName, deps) {
  assertDataRuntimeDeps(deps, [
    "buildClearedSubviewState",
    "getCurrentProject",
    "listChrViewCtgs",
    "loadDatasetChrCtgs",
    "loadDeletedCtgsForChr",
    "loadSideDataForCtg",
    "mapAssemblyError",
    "normalizeSupportDatasetId",
    "rerender",
  ]);
  const state = store.getState();
  if (!state.session.workspacePath || !state.session.projectId) {
    return;
  }
  const hiddenPrimaryCtgIdsByChr = normalizeHiddenPrimaryCtgIdsByChr(
    state.assembly.hiddenPrimaryCtgIdsByChr,
  );

  store.setState({
    assembly: {
      ...state.assembly,
      loading: true,
      chrPickerOpen: false,
      selectedChrName: chrName,
      chrCtgs: [],
      refTrackMembers: [],
      phasedChrTracks: [],
      isChrPhased: false,
      activePhasedTrackKey: "",
      activeHitsTrackKey: "primary",
      supportChrCtgs: [],
      deletedCtgs: [],
      selectedDeletedCtgRecordIds: [],
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: hiddenPrimaryCtgIdsByChr[chrName] || [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedCtgId: null,
      selectedMemberSeqId: null,
      ctgDetail: null,
      editCandidates: createEmptySideData().candidates,
      subview: deps.buildClearedSubviewState(state.assembly),
      summary: tAssembly(state, "runtime.loadChrSummary", { chrName }),
    },
  });
  deps.rerender(host, store);

  try {
    const currentProject = deps.getCurrentProject(state);
    const primaryDatasetId = deps.normalizeSupportDatasetId(currentProject?.primaryDatasetId);
    const supportDatasetId = deps.normalizeSupportDatasetId(state.assembly.supportDatasetId);
    const chrCtgResult = await deps.listChrViewCtgs({
      workspaceRoot: state.session.workspacePath,
      projectId: state.session.projectId,
      chrName,
      datasetId: primaryDatasetId,
    });
    const phasedChrTracks = await loadPhasedChrTracksForAssembly(deps, {
      state,
      currentProject,
      selectedChrName: chrName,
      chrCtgs: chrCtgResult.items,
    });
    const isChrPhased = Boolean(currentProject?.phasedAssemblyEnabled && phasedChrTracks.length);
    const activePhasedTrackKey = resolveActivePhasedTrackKey(
      state.assembly.activePhasedTrackKeyByChr,
      chrName,
      phasedChrTracks,
    );
    const activeHitsTrackKey = resolveActiveHitsTrackKey(
      state.assembly.activeHitsTrackKeyByChr,
      chrName,
      phasedChrTracks,
    );
    const refTrackMemberResult = await listReferenceTrackMembersOrEmpty(deps, {
      workspaceRoot: state.session.workspacePath,
      projectId: state.session.projectId,
      chrName,
    });
    const supportChrCtgs =
      supportDatasetId !== null
        ? await deps.loadDatasetChrCtgs(
            state.session.workspacePath,
            state.session.projectId,
            chrName,
            supportDatasetId,
          )
        : [];
    const deletedCtgs = await deps.loadDeletedCtgsForChr(
      state.session.workspacePath,
      state.session.projectId,
      chrName,
      primaryDatasetId,
    );
    const selectedCtgId = resolveSelectedCtgId(chrCtgResult.items, null, false);
    const filterPrimaryHiddenIds = typeof deps.filterPrimaryTrackSelectionCtgIds === "function"
      ? deps.filterPrimaryTrackSelectionCtgIds
      : (values) => values;
    const filteredHiddenPrimaryCtgIds = filterPrimaryHiddenIds(
      hiddenPrimaryCtgIdsByChr[chrName]
        || state.assembly.finalPathByChr?.[chrName]?.hiddenPrimaryCtgIds
        || [],
      {
        ...state.assembly,
        chrCtgs: chrCtgResult.items,
      },
    );
    const sideData = await deps.loadSideDataForCtg(
      state.session.workspacePath,
      state.session.projectId,
      selectedCtgId,
    );
    if (store.getState().assembly.selectedChrName !== chrName) {
      return;
    }

    store.setState({
      assembly: {
        ...store.getState().assembly,
        loading: false,
        chrCtgs: chrCtgResult.items,
        phasedChrTracks,
        isChrPhased,
        activePhasedTrackKey,
        activeHitsTrackKey,
        refTrackMembers: refTrackMemberResult.items,
        supportChrCtgs,
        deletedCtgs,
        selectedDeletedCtgRecordIds: [],
        trackSelectedCtgIds: [],
        hiddenPrimaryCtgIds: filteredHiddenPrimaryCtgIds,
        hiddenPrimaryCtgIdsByChr,
        trackDragOffsets: [],
        subviewTrackDragOffsets: [],
        selectedCtgId,
        ctgDetail: sideData.detail,
        editCandidates: sideData.candidates,
        selectedMemberSeqId: resolveSelectedMemberSeqId(sideData.detail, null),
        subview: deps.buildClearedSubviewState(state.assembly),
        summary: tAssembly(store.getState(), "runtime.chrLoadedSummary", { chrName }),
      },
    });
  } catch (error) {
    if (store.getState().assembly.selectedChrName !== chrName) {
      return;
    }
    const mappedError = deps.mapAssemblyError({ error, stateOrLocale: store.getState() });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        loading: false,
        supportChrCtgs: [],
        refTrackMembers: [],
        phasedChrTracks: [],
        isChrPhased: false,
        deletedCtgs: [],
        selectedDeletedCtgRecordIds: [],
        error: mappedError.userMessage,
        summary: tAssembly(store.getState(), "runtime.chrLoadFailedSummary", { chrName }),
      },
    });
  }

  deps.rerender(host, store);
}

export async function selectCtg(host, store, assemblyCtgId, options = {}, deps) {
  assertDataRuntimeDeps(deps, [
    "loadSideDataForCtg",
    "mapAssemblyError",
    "normalizeTrackFocusMode",
    "rerender",
    "setPendingTrackAutoFocusMode",
  ]);
  const state = store.getState();
  if (!state.session.workspacePath || !state.session.projectId) {
    return;
  }
  deps.setPendingTrackAutoFocusMode(
    options?.preserveViewport === true
      ? null
      : deps.normalizeTrackFocusMode(options.focusMode),
  );
  store.setState({
    assembly: {
      ...state.assembly,
      loading: true,
      selectedCtgId: assemblyCtgId,
      trackSelectedCtgIds: [],
      selectedDeletedCtgRecordIds: [],
      summary: tAssembly(state, "runtime.loadCtgDetailSummary", { assemblyCtgId }),
    },
  });
  deps.rerender(host, store);

  try {
    const sideData = await deps.loadSideDataForCtg(
      state.session.workspacePath,
      state.session.projectId,
      assemblyCtgId,
    );
    store.setState({
      assembly: {
        ...store.getState().assembly,
        loading: false,
        ctgDetail: sideData.detail,
        editCandidates: sideData.candidates,
        selectedMemberSeqId: resolveSelectedMemberSeqId(sideData.detail, null),
        summary: tAssembly(store.getState(), "runtime.ctgDetailLoadedSummary", { assemblyCtgId }),
      },
    });
  } catch (error) {
    const mappedError = deps.mapAssemblyError({ error, stateOrLocale: store.getState() });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        loading: false,
        error: mappedError.userMessage,
        summary: tAssembly(store.getState(), "runtime.ctgDetailLoadFailedSummary", { assemblyCtgId }),
      },
    });
  }

  deps.rerender(host, store);
}

export async function runCtgSearch(host, store, rawKeyword, deps) {
  assertDataRuntimeDeps(deps, [
    "mapAssemblyError",
    "rerender",
    "selectCtg",
  ]);
  const keyword = String(rawKeyword || "").trim();
  if (!keyword) {
    const mappedError = deps.mapAssemblyError({
      error: {
        code: "CTG_SEARCH_KEYWORD_REQUIRED",
        message: "ctg search keyword is required",
      },
      stateOrLocale: store.getState(),
    });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        actionError: "",
        actionStatus: mappedError.userMessage,
      },
    });
    deps.rerender(host, store);
    return;
  }
  const state = store.getState();
  const keywordLower = keyword.toLowerCase();
  const numericId = Number(keyword);
  const matched = state.assembly.chrCtgs.find((ctg) => {
    if (Number.isFinite(numericId) && numericId > 0 && ctg.assemblyCtgId === Math.trunc(numericId)) {
      return true;
    }
    return String(ctg.name || "").toLowerCase().includes(keywordLower);
  });
  if (!matched) {
    const mappedError = deps.mapAssemblyError({
      error: {
        code: "CURRENT_CHR_NO_MATCHING_CTG",
        message: `current chromosome search miss for keyword ${keyword}`,
      },
      stateOrLocale: state,
    });
    store.setState({
      assembly: {
        ...state.assembly,
        actionStatus: "",
        actionError: mappedError.userMessage,
      },
    });
    deps.rerender(host, store);
    return;
  }
  await deps.selectCtg(host, store, matched.assemblyCtgId);
}

export async function loadSideDataForCtg(workspaceRoot, projectId, assemblyCtgId, deps) {
  assertDataRuntimeDeps(deps, [
    "getCtgDetail",
    "listCtgEditCandidates",
  ]);
  if (!assemblyCtgId) {
    return createEmptySideData();
  }

  const detail = await deps.getCtgDetail({
    workspaceRoot,
    projectId,
    assemblyCtgId,
  });

  try {
    const candidates = await deps.listCtgEditCandidates({
      workspaceRoot,
      projectId,
      assemblyCtgId,
    });
    return { detail, candidates };
  } catch {
    return {
      detail,
      candidates: createEmptySideData().candidates,
    };
  }
}

export async function loadDatasetChrCtgs(workspaceRoot, projectId, chrName, datasetId, deps) {
  assertDataRuntimeDeps(deps, [
    "listChrViewCtgs",
    "normalizeSupportDatasetId",
  ]);
  const normalizedDatasetId = deps.normalizeSupportDatasetId(datasetId);
  const normalizedChrName = String(chrName || "").trim();
  if (!workspaceRoot || !projectId || !normalizedChrName || normalizedDatasetId === null) {
    return [];
  }
  try {
    const result = await deps.listChrViewCtgs({
      workspaceRoot,
      projectId,
      chrName: normalizedChrName,
      datasetId: normalizedDatasetId,
    });
    return Array.isArray(result?.items) ? result.items : [];
  } catch {
    return [];
  }
}

export async function loadDeletedCtgsForChr(workspaceRoot, projectId, chrName, datasetId = null, deps) {
  assertDataRuntimeDeps(deps, [
    "listDeletedCtgs",
  ]);
  const normalizedChrName = String(chrName || "").trim();
  if (!workspaceRoot || !projectId || !normalizedChrName) {
    return [];
  }
  try {
    const result = await deps.listDeletedCtgs({
      workspaceRoot,
      projectId,
      chrName: normalizedChrName,
      datasetId,
    });
    return Array.isArray(result?.items) ? result.items : [];
  } catch {
    return [];
  }
}
import {
  normalizeFinalPathByChr,
  normalizeFinalPathViewMode as normalizeFinalPathViewModeState,
} from "./final-path-state.js";
import { normalizeDegapProjectState } from "./degap-state.js";
import { tAssembly } from "./i18n.js";
import { normalizeHiddenPrimaryCtgIdsByChr } from "./selection-state.js";
