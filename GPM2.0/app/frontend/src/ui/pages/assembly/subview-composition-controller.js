import { buildSubviewCompositionCandidates } from "./subview-composition-candidates.js";
import {
  addSubviewCompositionMembers,
  applySubviewComposition,
  compactSubviewCompositionLayout,
  getSubviewComposition,
  moveSubviewCompositionMembers,
  normalizeSubviewComposition,
  normalizeSubviewCompositionMember,
  removeSubviewCompositionMembers,
} from "./subview-composition-state.js";
import { commitSubviewCompositionHistoryOperation } from "./subview-history-state.js";
import {
  buildSubviewTrackPairHiddenCtgKey,
  buildSubviewTrackPairPoolsFromAssembly,
  getSubviewState,
  normalizeSubviewTrackPairHiddenCtgs,
  normalizeSubviewSummarySelection,
  normalizeSubviewTrackSummary,
  resolveSubviewSelectionCtg,
  resolveSubviewTrackSummaryCtgs,
} from "./subview-state.js";
import { normalizeSupportDatasetId } from "./selection-state.js";
import { renderSubviewCompositionPanel } from "./render-subview-composition.js";
import { resolveSubviewCompositionScaleViewport } from "./subview-composition-layout.js";

function defaultUi(scopeKey = "") {
  return {
    scopeKey,
    view: "members",
    targetLane: "top",
    query: "",
    source: "all",
    checkedKeys: [],
    focusedEntityKey: "",
    loading: false,
    error: "",
    requestKey: "",
    draggedEntityKey: "",
  };
}

function resolvePrimaryDatasetId(state) {
  const explicit = normalizeSupportDatasetId(state?.assembly?.primaryDatasetId);
  if (explicit) return explicit;
  const projectId = normalizeSupportDatasetId(state?.session?.projectId);
  const projects = Array.isArray(state?.initializer?.existingProjects)
    ? state.initializer.existingProjects
    : [];
  return normalizeSupportDatasetId(
    projects.find((project) => normalizeSupportDatasetId(project?.projectId) === projectId)
      ?.primaryDatasetId,
  );
}

function readCurrentRectPositions(host, fallbackGapBp) {
  const scroll = host?.querySelector?.(".subview-track-scroll");
  const domainSpanBp = Number(scroll?.dataset?.subviewDomainSpanBp);
  const innerWidth = Number(scroll?.dataset?.subviewInnerWidth);
  const windowStartBp = Number(scroll?.dataset?.subviewWindowStartBp);
  const bpPerPx = Number.isFinite(domainSpanBp) && domainSpanBp > 0
    && Number.isFinite(innerWidth) && innerWidth > 0
    ? domainSpanBp / innerWidth
    : Math.max(1, fallbackGapBp / 20);
  const positions = new Map();
  for (const node of host?.querySelectorAll?.(
    "[data-subview-track-slot][data-subview-contig-id][data-subview-rect-x]",
  ) || []) {
    const slot = String(node.getAttribute("data-subview-track-slot") || "").trim();
    const contigId = normalizeSupportDatasetId(node.getAttribute("data-subview-contig-id"));
    const x = Number(node.getAttribute("data-subview-rect-x"));
    const rawWorldStartBp = node.getAttribute("data-subview-world-start-bp");
    const worldStartBp = rawWorldStartBp === null ? Number.NaN : Number(rawWorldStartBp);
    if (contigId && Number.isFinite(worldStartBp)) {
      positions.set(`${slot}:${contigId}`, worldStartBp);
    } else if (contigId && Number.isFinite(x)) {
      positions.set(
        `${slot}:${contigId}`,
        (Number.isFinite(windowStartBp) ? windowStartBp : 0) + x * bpPerPx,
      );
    }
  }
  return { positions, bpPerPx };
}

function sourceFromSelection(selection, ctg) {
  const role = String(selection?.role || "support").trim();
  return {
    role,
    datasetId: normalizeSupportDatasetId(ctg?.datasetId ?? selection?.datasetId),
    datasetName: String(ctg?.datasetName || "").trim(),
    sourceType: role === "phased"
      ? "phased"
      : role === "ref"
        ? "ref_segment"
        : selection?.source === "mirror" || selection?.isMirror ? "mirror" : "mother",
    phasedTrackId: normalizeSupportDatasetId(ctg?.phasedTrackId ?? selection?.phasedTrackId),
    phasedItemId: normalizeSupportDatasetId(ctg?.phasedTrackItemId ?? selection?.phasedTrackItemId),
    hap: String(ctg?.phasedHaplotypeKey || selection?.haplotypeKey
      || selection?.phasedHaplotypeKey || "").trim(),
    mirrored: selection?.source === "mirror" || selection?.isMirror === true,
  };
}

function memberFromCtg(
  ctg,
  selection,
  lane,
  index,
  positions,
  flippedKeys,
  cursorByLane,
  layoutGapBp,
) {
  const contigId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
  if (!contigId) return null;
  const lengthBp = Math.max(1, Number(ctg?.lengthBp ?? ctg?.totalLength ?? 1));
  const savedPosition = positions.get(`${lane}:${contigId}`);
  const xBp = Number.isFinite(savedPosition) ? savedPosition : cursorByLane[lane];
  cursorByLane[lane] = Math.max(cursorByLane[lane], xBp + lengthBp + layoutGapBp);
  return normalizeSubviewCompositionMember({
    assemblyCtgId: contigId,
    source: sourceFromSelection(selection, ctg),
    reference: selection?.role === "ref" ? {
      chrName: ctg?.referenceChrName || ctg?.chrName,
      startBp: ctg?.segmentStartBp ?? ctg?.startBp,
      endBp: ctg?.segmentEndBp ?? ctg?.endBp,
    } : null,
    label: ctg?.name,
    lengthBp,
    baseOrientation: ctg?.orient ?? ctg?.refOrient,
    lane,
    xBp,
    flipped: flippedKeys.has(`${lane}:${contigId}`),
    order: index,
  }, index);
}

export function projectCurrentSubviewToComposition(state, host) {
  const currentSubview = getSubviewState(state?.assembly || {});
  const existing = getSubviewComposition(currentSubview);
  if (existing) return existing;
  const summary = currentSubview.summary;
  if (!summary) return normalizeSubviewComposition({
    activeAnchors: currentSubview.activeAnchors,
    manualAnchors: currentSubview.manualAnchors,
  });
  const pools = buildSubviewTrackPairPoolsFromAssembly(state?.assembly || {});
  const { positions, bpPerPx } = readCurrentRectPositions(host, 20_000);
  const layoutGapBp = Math.max(0, 20 * bpPerPx);
  const flippedKeys = new Set((currentSubview.flippedCtgs || [])
    .map((entry) => `${entry.slot}:${entry.contigId}`));
  const hiddenTrackPairKeys = new Set(
    normalizeSubviewTrackPairHiddenCtgs(currentSubview.trackPairHiddenCtgs).map((entry) =>
      buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
    ),
  );
  const cursorByLane = { top: 0, bottom: 0 };
  const entries = [];
  if (String(summary.mode || "") === "track-pair") {
    for (const [lane, track] of [["top", summary.topTrack], ["bottom", summary.bottomTrack]]) {
      const selection = normalizeSubviewTrackSummary(track);
      resolveSubviewTrackSummaryCtgs(selection, pools)
        .filter((ctg) => !hiddenTrackPairKeys.has(
          buildSubviewTrackPairHiddenCtgKey(selection?.role, ctg?.assemblyCtgId),
        ))
        .forEach((ctg) => entries.push({ lane, selection, ctg }));
    }
  } else {
    for (const [lane, selected] of [["top", summary.top], ["bottom", summary.bottom]]) {
      const selection = normalizeSubviewSummarySelection(selected);
      const ctg = resolveSubviewSelectionCtg(selection, pools);
      if (selection && ctg) entries.push({ lane, selection, ctg });
    }
  }
  return normalizeSubviewComposition({
    members: entries.map((entry, index) => memberFromCtg(
      entry.ctg,
      entry.selection,
      entry.lane,
      index,
      positions,
      flippedKeys,
      cursorByLane,
      layoutGapBp,
    )).filter(Boolean),
    layoutGapBp,
    activeAnchors: currentSubview.activeAnchors,
    manualAnchors: currentSubview.manualAnchors,
  });
}

export function resolveCurrentSubviewCompositionViewport(state, host) {
  const saved = state?.assembly?.subviewCompositionViewport;
  const currentSubview = getSubviewState(state?.assembly || {});
  if (String(currentSubview?.summary?.mode || "") === "composition"
    && Number(saved?.bpPerPx) > 0) {
    return {
      bpPerPx: Number(saved.bpPerPx),
      leftBp: Number.isFinite(Number(saved.leftBp)) ? Number(saved.leftBp) : 0,
      topPx: Number.isFinite(Number(saved.topPx)) ? Number(saved.topPx) : 0,
    };
  }
  const scroll = host?.querySelector?.(".subview-track-scroll");
  const { bpPerPx } = readCurrentRectPositions(host, 20_000);
  const viewBoxMinX = Number(scroll?.dataset?.subviewViewboxMinX || 0);
  return {
    bpPerPx,
    leftBp: (Math.max(0, Number(scroll?.scrollLeft || 0))
      + (Number.isFinite(viewBoxMinX) ? viewBoxMinX : 0)) * bpPerPx,
    topPx: 0,
  };
}

function focusCompositionMember(host, entityKey) {
  for (const node of host?.querySelectorAll?.("[data-subview-composition-entity-key]") || []) {
    node.classList.toggle("is-composition-focused",
      node.getAttribute("data-subview-composition-entity-key") === entityKey);
  }
}

function locateCompositionMember(host, entityKey) {
  const node = Array.from(host?.querySelectorAll?.("[data-subview-composition-entity-key]") || [])
    .find((entry) => entry.getAttribute("data-subview-composition-entity-key") === entityKey);
  const scroll = host?.querySelector?.(".subview-track-scroll");
  if (!node || !scroll) return false;
  const x = Number(node.getAttribute("data-subview-rect-x"));
  const width = Number(node.getAttribute("data-subview-rect-width"));
  const minX = Number(scroll.dataset?.subviewViewboxMinX || 0);
  if (!Number.isFinite(x) || !Number.isFinite(width)) return false;
  const left = Math.max(0, x + width / 2 - minX - Number(scroll.clientWidth || 0) / 2);
  scroll.scrollTo?.({ left, behavior: "smooth" });
  if (typeof scroll.scrollTo !== "function") scroll.scrollLeft = left;
  return true;
}

function resolveContextCompositionMember(composition, memberContext) {
  const members = Array.isArray(composition?.members) ? composition.members : [];
  const entityKey = String(
    memberContext?.entityKey || memberContext?.compositionEntityKey || "",
  ).trim();
  if (entityKey) {
    return members.find((entry) => entry.entityKey === entityKey) || null;
  }
  const assemblyCtgId = normalizeSupportDatasetId(memberContext?.assemblyCtgId);
  if (!assemblyCtgId) return null;
  const lane = String(memberContext?.slot || memberContext?.lane || "").trim().toLowerCase();
  const role = String(memberContext?.trackRole || memberContext?.role || "").trim();
  const datasetId = normalizeSupportDatasetId(memberContext?.datasetId);
  const phasedTrackId = normalizeSupportDatasetId(memberContext?.phasedTrackId);
  const phasedItemId = normalizeSupportDatasetId(
    memberContext?.phasedTrackItemId ?? memberContext?.phasedItemId,
  );
  const candidates = members.filter((entry) => entry.assemblyCtgId === assemblyCtgId);
  return candidates.find((entry) => {
    if (lane && entry.lane !== lane) return false;
    if (role && entry.source?.role !== role) return false;
    if (datasetId && entry.source?.datasetId !== datasetId) return false;
    if (phasedTrackId && entry.source?.phasedTrackId !== phasedTrackId) return false;
    if (phasedItemId && entry.source?.phasedItemId !== phasedItemId) return false;
    return true;
  }) || (candidates.length === 1 ? candidates[0] : null);
}

export function createSubviewCompositionController({
  session,
  getMeasuredTrackViewportPx,
  listChrViewCtgs,
  persistProjectAssemblyViewStateFromStore,
  rerenderSubviewPanel,
  refreshSubviewPairwiseEvidence,
  anchorController,
}) {
  function ui(scopeKey) {
    const current = session.subviewCompositionToolsState || defaultUi(scopeKey);
    if (current.scopeKey !== scopeKey) session.subviewCompositionToolsState = defaultUi(scopeKey);
    return session.subviewCompositionToolsState;
  }

  function updateUi(patch, sync) {
    session.subviewCompositionToolsState = { ...session.subviewCompositionToolsState, ...patch };
    sync?.();
  }

  function renderContent(context) {
    if (context.tab === "anchors") return anchorController.renderContent(context);
    const currentUi = ui(context.scopeKey);
    return renderSubviewCompositionPanel({
      composition: projectCurrentSubviewToComposition(context.state, context.host),
      candidates: context.state?.assembly?.subviewCompositionCandidates || [],
      candidatesLoaded: context.state?.assembly?.subviewCompositionCandidatesLoaded === true,
      ui: currentUi,
      labels: context.labels.compositionManager,
    }, context);
  }

  function resetScope(scopeKey) {
    anchorController.resetScope(scopeKey);
    session.subviewCompositionToolsState = defaultUi(scopeKey);
  }

  async function loadCandidates(host, store, sync) {
    const state = store.getState();
    const scopeKey = [state.session?.workspacePath, state.session?.projectId,
      state.assembly?.selectedChrName].join("|");
    const currentUi = session.subviewCompositionToolsState || defaultUi();
    const assembly = state.assembly || {};
    if (!scopeKey.replaceAll("|", "") || currentUi.loading
      || (currentUi.requestKey === scopeKey
        && (assembly.subviewCompositionCandidatesLoaded || currentUi.error))) return;
    updateUi({ loading: true, error: "", requestKey: scopeKey }, sync);
    try {
      const result = await listChrViewCtgs({
        workspaceRoot: state.session.workspacePath,
        projectId: state.session.projectId,
        chrName: state.assembly.selectedChrName,
        datasetId: null,
      });
      const latest = store.getState();
      const latestKey = [latest.session?.workspacePath, latest.session?.projectId,
        latest.assembly?.selectedChrName].join("|");
      if (latestKey !== scopeKey) return;
      const pools = buildSubviewTrackPairPoolsFromAssembly(latest.assembly);
      const candidates = buildSubviewCompositionCandidates({
        allChrCtgs: result?.items,
        supportMirroredCtgs: pools.supportMirrorCtgs,
        phasedCtgs: pools.phasedCtgs,
        refCtgs: pools.refCtgs,
        primaryDatasetId: resolvePrimaryDatasetId(latest),
        selectedChrName: latest.assembly.selectedChrName,
        deletedCtgs: latest.assembly.deletedCtgs,
      });
      store.setState({
        assembly: {
          ...latest.assembly,
          subviewCompositionCandidates: candidates,
          subviewCompositionCandidatesLoaded: true,
        },
      });
      updateUi({ loading: false, error: "" }, sync);
    } catch (error) {
      const latest = store.getState();
      store.setState({
        assembly: {
          ...latest.assembly,
          subviewCompositionCandidatesLoaded: false,
        },
      });
      updateUi({
        loading: false,
        error: String(error?.message || error || ""),
      }, sync);
    }
  }

  async function commit(host, store, composition, operation, sync) {
    const state = store.getState();
    const viewport = host?.querySelector?.(".subview-track-scroll")
      ? resolveCurrentSubviewCompositionViewport(state, host)
      : resolveSubviewCompositionScaleViewport(composition, {
        trackPrefs: state.assembly?.subviewTrackView,
        viewportWidthPx: getMeasuredTrackViewportPx?.("subview"),
      });
    const nextSubview = applySubviewComposition(getSubviewState(state.assembly), composition);
    const result = commitSubviewCompositionHistoryOperation(state.assembly, {
      nextSubview,
      operation,
      viewport,
      stateOrLocale: state,
    });
    if (!result.changed) return false;
    store.setState({ assembly: result.assembly });
    rerenderSubviewPanel(host, store);
    sync?.();
    refreshSubviewPairwiseEvidence(host, store);
    await persistProjectAssemblyViewStateFromStore(host, store);
    return true;
  }

  function focus(host, entityKey, sync) {
    updateUi({ focusedEntityKey: entityKey }, sync);
    focusCompositionMember(host, entityKey);
  }

  function onAction(event, context) {
    const host = event.target?.closest?.("#route-host") || context.host;
    const addLane = event.target.closest?.("[data-subview-composition-add]")?.dataset.subviewCompositionAdd;
    if (addLane) {
      updateUi({ view: "picker", targetLane: addLane, query: "", source: "all", checkedKeys: [] }, context.sync);
      void loadCandidates(host, context.store, context.sync);
      return;
    }
    if (event.target.closest?.("[data-subview-composition-back]")) {
      updateUi({ view: "members", checkedKeys: [] }, context.sync);
      return;
    }
    if (event.target.closest?.("[data-subview-composition-retry]")) {
      updateUi({ error: "", requestKey: "" }, context.sync);
      void loadCandidates(host, context.store, context.sync);
      return;
    }
    const candidateInput = event.target.closest?.("[data-subview-composition-candidate]");
    if (candidateInput) {
      const key = candidateInput.dataset.subviewCompositionCandidate;
      const checked = new Set(ui(context.scopeKey).checkedKeys);
      if (candidateInput.checked) checked.add(key); else checked.delete(key);
      updateUi({ checkedKeys: [...checked] }, context.sync);
      return;
    }
    if (event.target.closest?.("[data-subview-composition-confirm-add]")) {
      const state = context.store.getState();
      const currentUi = ui(context.scopeKey);
      const selected = (state.assembly.subviewCompositionCandidates || [])
        .filter((candidate) => currentUi.checkedKeys.includes(candidate.candidateKey));
      const result = addSubviewCompositionMembers(
        projectCurrentSubviewToComposition(state, host),
        selected,
        currentUi.targetLane,
      );
      void commit(host, context.store, result.composition, {
        kind: "add-members",
        count: result.addedCount + result.movedCount,
      }, context.sync).then((changed) => {
        if (changed) updateUi({ view: "members", checkedKeys: [] }, context.sync);
      });
      return;
    }
    const removeKey = event.target.closest?.("[data-subview-composition-remove]")
      ?.dataset.subviewCompositionRemove;
    if (removeKey) {
      const result = removeSubviewCompositionMembers(
        projectCurrentSubviewToComposition(context.store.getState(), host),
        [removeKey],
      );
      void commit(host, context.store, result.composition,
        { kind: "remove-members", count: result.removedCount }, context.sync);
      return;
    }
    const moveButton = event.target.closest?.("[data-subview-composition-move]");
    if (moveButton) {
      const result = moveSubviewCompositionMembers(
        projectCurrentSubviewToComposition(context.store.getState(), host),
        [moveButton.dataset.subviewCompositionMove],
        moveButton.dataset.subviewCompositionTargetLane,
      );
      void commit(host, context.store, result.composition,
        { kind: "move-members", count: result.movedCount }, context.sync);
      return;
    }
    if (event.target.closest?.("[data-subview-composition-compact]")) {
      const result = compactSubviewCompositionLayout(
        projectCurrentSubviewToComposition(context.store.getState(), host),
      );
      void commit(host, context.store, result.composition,
        { kind: "compact-layout" }, context.sync);
      return;
    }
    const focusKey = event.target.closest?.("[data-subview-composition-focus]")
      ?.dataset.subviewCompositionFocus;
    if (focusKey) {
      focus(host, focusKey, context.sync);
      return;
    }
    anchorController.onAction(event, context);
  }

  function onInput(event, context) {
    if (event.target.matches?.("[data-subview-composition-search]")) {
      updateUi({ query: event.target.value }, context.sync);
      return;
    }
    if (event.target.matches?.("[data-subview-composition-source]")) {
      updateUi({ source: event.target.value }, context.sync);
      return;
    }
    anchorController.onInput(event, context);
  }

  function onPointerOver(event, context) {
    anchorController.onPointerOver?.(event, context);
  }

  function onPointerOut(event, context) {
    anchorController.onPointerOut?.(event, context);
  }

  function onDoubleClick(event, context) {
    const key = event.target.closest?.("[data-subview-composition-member]")
      ?.dataset.subviewCompositionMember;
    if (key && !event.target.closest("button")) {
      locateCompositionMember(event.target.closest?.("#route-host") || context.host, key);
      return;
    }
    anchorController.onDoubleClick(event, context);
  }

  function onContentKeyDown(event, context) {
    const key = event.target.closest?.("[data-subview-composition-member]")
      ?.dataset.subviewCompositionMember;
    if (key && event.key === "Enter") {
      event.preventDefault();
      locateCompositionMember(event.target.closest?.("#route-host") || context.host, key);
      return;
    }
    anchorController.onContentKeyDown(event, context);
  }

  function onDragStart(event, context) {
    const key = event.target.closest?.("[data-subview-composition-member]")
      ?.dataset.subviewCompositionMember;
    if (!key) return;
    event.dataTransfer?.setData("text/plain", key);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
    updateUi({ draggedEntityKey: key }, context.sync);
  }

  function onDragOver(event) {
    if (!event.target.closest?.("[data-subview-composition-drop-lane]")) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  }

  function onDrop(event, context) {
    const lane = event.target.closest?.("[data-subview-composition-drop-lane]")
      ?.dataset.subviewCompositionDropLane;
    const key = session.subviewCompositionToolsState?.draggedEntityKey
      || event.dataTransfer?.getData("text/plain");
    if (!lane || !key) return;
    event.preventDefault();
    const host = event.target.closest?.("#route-host") || context.host;
    const result = moveSubviewCompositionMembers(
      projectCurrentSubviewToComposition(context.store.getState(), host),
      [key],
      lane,
    );
    updateUi({ draggedEntityKey: "" }, context.sync);
    void commit(host, context.store, result.composition,
      { kind: "move-members", count: result.movedCount }, context.sync);
  }

  function onDragEnd(_event, context) {
    updateUi({ draggedEntityKey: "" }, context.sync);
  }

  function afterRender(context) {
    anchorController.afterRender(context);
    focusCompositionMember(context.host, session.subviewCompositionToolsState?.focusedEntityKey || "");
    if (context.tab === "composition") void loadCandidates(context.host, context.store, context.sync);
  }

  async function addContextCtgToComposition(host, store, ctgContext, lane) {
    const state = store.getState();
    if (!(state.assembly?.subviewCompositionCandidates || []).length) {
      updateUi({ error: "", requestKey: "" });
      await loadCandidates(host, store);
    }
    const latest = store.getState();
    const assemblyCtgId = normalizeSupportDatasetId(ctgContext?.assemblyCtgId);
    const role = String(ctgContext?.trackRole || "").trim();
    const candidates = latest.assembly?.subviewCompositionCandidates || [];
    const selectedIds = (Array.isArray(latest.assembly?.trackSelectedCtgIds)
      ? latest.assembly.trackSelectedCtgIds : [])
      .map(normalizeSupportDatasetId)
      .filter(Boolean);
    const targetIds = role === "primary" && selectedIds.includes(assemblyCtgId)
      ? Array.from(new Set(selectedIds))
      : [assemblyCtgId].filter(Boolean);
    const selectedCandidates = targetIds.map((targetId) =>
      candidates.find((entry) => entry.assemblyCtgId === targetId
        && (!role || entry.source?.role === role))
      || candidates.find((entry) => entry.assemblyCtgId === targetId))
      .filter(Boolean);
    if (!selectedCandidates.length) return false;
    const result = addSubviewCompositionMembers(
      projectCurrentSubviewToComposition(latest, host),
      selectedCandidates,
      lane,
    );
    return commit(host, store, result.composition, {
      kind: "add-members",
      count: result.addedCount + result.movedCount,
    });
  }

  async function moveContextSubviewMemberToOtherLane(host, store, memberContext) {
    const state = store.getState();
    const composition = projectCurrentSubviewToComposition(state, host);
    const member = resolveContextCompositionMember(composition, memberContext);
    if (!member) return false;
    const result = moveSubviewCompositionMembers(
      composition,
      [member.entityKey],
      member.lane === "top" ? "bottom" : "top",
    );
    if (!result.changed) return false;
    return commit(host, store, result.composition, {
      kind: "move-members",
      count: result.movedCount,
    });
  }

  async function removeContextSubviewMember(host, store, memberContext) {
    const state = store.getState();
    const composition = projectCurrentSubviewToComposition(state, host);
    const member = resolveContextCompositionMember(composition, memberContext);
    if (!member) return false;
    const result = removeSubviewCompositionMembers(composition, [member.entityKey]);
    if (!result.changed) return false;
    return commit(host, store, result.composition, {
      kind: "remove-members",
      count: result.removedCount,
    });
  }

  return {
    addContextCtgToComposition,
    moveContextSubviewMemberToOtherLane,
    removeContextSubviewMember,
    renderContent,
    resetScope,
    onAction,
    onInput,
    onPointerOver,
    onPointerOut,
    onDoubleClick,
    onContentKeyDown,
    onDragStart,
    onDragOver,
    onDrop,
    onDragEnd,
    afterRender,
  };
}
