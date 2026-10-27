import { currentAssemblyViewRequest } from "./assembly-view-request.js";
import { tAssembly } from "./i18n.js";
import { FINAL_PATH_ALL_KEY } from "./final-path-state.js";
import {
  areTrackDragOffsetsEqual,
  buildTrackDragOffsetKey,
  normalizeSupportDatasetId,
  normalizeTrackDragOffsets,
  setTrackDragOffset,
} from "./selection-state.js";

export function compactFinalPathByDeletedPhasedTrack(finalPathByChr, {
  parentChrName,
  tracksBefore,
  deletedPhasedTrackId,
}) {
  const source = finalPathByChr && typeof finalPathByChr === "object" ? finalPathByChr : {};
  const orderedTracks = (Array.isArray(tracksBefore) ? tracksBefore : [])
    .slice()
    .sort((left, right) =>
      Number(left?.displayOrder || 0) - Number(right?.displayOrder || 0)
      || Number(left?.phasedTrackId || 0) - Number(right?.phasedTrackId || 0),
    );
  const deletedIndex = orderedTracks.findIndex(
    (track) => normalizeSupportDatasetId(track?.phasedTrackId) === deletedPhasedTrackId,
  );
  if (deletedIndex < 0) {
    return { ...source };
  }
  const next = { ...source };
  const deletedLabel = String(orderedTracks[deletedIndex]?.label || "").trim();
  if (deletedLabel) {
    delete next[deletedLabel];
  }
  orderedTracks.slice(deletedIndex + 1).forEach((track, index) => {
    const oldLabel = String(track?.label || "").trim();
    const nextKey = String.fromCharCode("A".charCodeAt(0) + deletedIndex + index);
    const nextLabel = `${parentChrName}${nextKey}`;
    if (!oldLabel || oldLabel === nextLabel || !Object.prototype.hasOwnProperty.call(next, oldLabel)) {
      return;
    }
    next[nextLabel] = {
      ...next[oldLabel],
      chrName: nextLabel,
    };
    delete next[oldLabel];
  });
  return next;
}

export function createPhasedTrackController({
  addCtgToPhasedChrTrack,
  createPhasedChrTrack: createPhasedChrTrackApi,
  deletePhasedChrTrack,
  listPhasedChrTracks,
  mapAssemblyError,
  persistMainTrackViewState,
  persistTrackDragOffsets,
  removePhasedChrTrackItem,
  requestAssemblyNotice = () => Promise.resolve(true),
  runSerializedProjectViewMutation = (_store, task) => task(() => true),
  rerenderAssemblyMainTab,
  rerenderFinalPathCard,
  setAssemblyActionFeedbackInMainTab,
}) {
  const refreshRequests = new WeakMap();

  function isCurrentProject(store, expected) {
    const current = store.getState();
    return current.session?.workspacePath === expected.session?.workspacePath
      && current.session?.projectId === expected.session?.projectId;
  }

  function isCurrentScope(store, expected, viewRequest) {
    return currentAssemblyViewRequest(store) === viewRequest
      && isCurrentProject(store, expected)
      && store.getState().assembly?.selectedChrName === expected.assembly?.selectedChrName;
  }

  function serialized(action) {
    return (host, store, payload) => runSerializedProjectViewMutation(store, () => {
      // Any earlier list belongs to the pre-mutation topology, even if its
      // response arrives before this mutation starts the replacement refresh.
      refreshRequests.set(store, {});
      return action(host, store, payload);
    });
  }

  function retainedTrackKey(previousTracks, tracks, key) {
    const previous = previousTracks.find((track) => track.haplotypeKey === key);
    if (previous) {
      return tracks.find((track) => track.phasedTrackId === previous.phasedTrackId)?.haplotypeKey || "";
    }
    return tracks.some((track) => track.haplotypeKey === key) ? key : "";
  }

  function reconcileTrackState(current, previousTracks, tracks, parentChrName, {
    deletedKey = "", fallback = current,
  } = {}) {
    const visible = current.selectedChrName === parentChrName;
    const mainKey = current.activePhasedTrackKeyByChr?.[parentChrName]
      || (visible ? current.activePhasedTrackKey : fallback.activePhasedTrackKey) || "";
    const nextActiveKey = retainedTrackKey(previousTracks, tracks, mainKey)
      || (deletedKey ? resolveActivePhasedKeyAfterDelete({
        currentKey: "", tracksAfter: tracks, deletedKey,
      }) : tracks[0]?.haplotypeKey || "");
    const finalKey = String(current.activeFinalPathKeyByChr?.[parentChrName]
      || (visible ? current.activeFinalPathKey : fallback.activeFinalPathKey) || "").trim();
    const nextFinalKey = !tracks.length ? ""
      : (finalKey === FINAL_PATH_ALL_KEY ? FINAL_PATH_ALL_KEY
        : retainedTrackKey(previousTracks, tracks, finalKey) || FINAL_PATH_ALL_KEY);
    return {
      ...(visible ? { phasedChrTracks: tracks, isChrPhased: Boolean(tracks.length),
        activePhasedTrackKey: nextActiveKey, activeFinalPathKey: nextFinalKey } : {}),
      activePhasedTrackKeyByChr: { ...(current.activePhasedTrackKeyByChr || {}), [parentChrName]: nextActiveKey },
      activeFinalPathKeyByChr: { ...(current.activeFinalPathKeyByChr || {}), [parentChrName]: nextFinalKey },
    };
  }

  function topologyAfterDelete(tracks, deletedId, parentChrName) {
    return tracks.filter((track) => normalizeSupportDatasetId(track.phasedTrackId) !== deletedId)
      .slice().sort((a, b) => Number(a.displayOrder) - Number(b.displayOrder)
        || Number(a.phasedTrackId) - Number(b.phasedTrackId))
      .map((track, index) => {
        const key = String.fromCharCode("A".charCodeAt(0) + index);
        return { ...track, displayOrder: index, haplotypeKey: key, label: `${parentChrName}${key}` };
      });
  }

  function hydratePhasedTracksForCurrentAssembly(tracks, assembly) {
    const primaryById = new Map(
      (Array.isArray(assembly?.chrCtgs) ? assembly.chrCtgs : [])
        .map((ctg) => [normalizeSupportDatasetId(ctg?.assemblyCtgId), ctg])
        .filter(([ctgId]) => ctgId !== null),
    );
    return (Array.isArray(tracks) ? tracks : [])
      .map((track) => ({
        ...track,
        phasedTrackId: normalizeSupportDatasetId(track?.phasedTrackId),
        displayOrder: Number(track?.displayOrder || 0),
        haplotypeKey: String(track?.haplotypeKey || "").trim(),
        label: String(track?.label || "").trim(),
        items: (Array.isArray(track?.items) ? track.items : [])
          .slice()
          .sort((left, right) =>
            Number(left?.displayOrder || 0) - Number(right?.displayOrder || 0)
            || Number(left?.itemId || left?.phasedTrackItemId || 0)
              - Number(right?.itemId || right?.phasedTrackItemId || 0),
          )
          .map((item) => ({
            ...item,
            itemId: normalizeSupportDatasetId(item?.itemId ?? item?.phasedTrackItemId),
            phasedTrackId: normalizeSupportDatasetId(item?.phasedTrackId ?? track?.phasedTrackId),
            assemblyCtgId: normalizeSupportDatasetId(item?.assemblyCtgId),
            sourceCtg: primaryById.get(normalizeSupportDatasetId(item?.assemblyCtgId))
              || item?.sourceCtg
              || null,
          })),
      }))
      .filter((track) => track.phasedTrackId && track.haplotypeKey)
      .sort((left, right) =>
        left.displayOrder - right.displayOrder || left.phasedTrackId - right.phasedTrackId,
      );
  }

  function resolvePrimaryTrackDragOffsetForCtg(assembly, assemblyCtgId) {
    const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
    if (!normalizedCtgId) {
      return null;
    }
    const targetKey = buildTrackDragOffsetKey("primary", normalizedCtgId);
    return normalizeTrackDragOffsets(assembly?.trackDragOffsets).find(
      (entry) => buildTrackDragOffsetKey(entry.trackRole, entry.assemblyCtgId, entry) === targetKey,
    ) || null;
  }

  function inheritPrimaryTrackDragOffsetForPhasedItem(store, {
    assemblyCtgId,
    phasedTrackId,
    phasedTrackItemId,
  }) {
    const state = store.getState();
    const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
    const normalizedTrackId = normalizeSupportDatasetId(phasedTrackId);
    const normalizedItemId = normalizeSupportDatasetId(phasedTrackItemId);
    if (!normalizedCtgId || !normalizedTrackId || !normalizedItemId) {
      return false;
    }
    const sourceOffset = resolvePrimaryTrackDragOffsetForCtg(state.assembly, normalizedCtgId);
    if (!sourceOffset) {
      return false;
    }
    const nextOffset = {
      trackRole: "phased",
      assemblyCtgId: normalizedCtgId,
      phasedTrackId: normalizedTrackId,
      phasedTrackItemId: normalizedItemId,
      ...(Number.isFinite(Number(sourceOffset.offsetBp))
        ? { offsetBp: sourceOffset.offsetBp }
        : { offsetPx: sourceOffset.offsetPx }),
    };
    const currentOffsets = normalizeTrackDragOffsets(state.assembly?.trackDragOffsets);
    const nextOffsets = setTrackDragOffset(currentOffsets, nextOffset);
    if (areTrackDragOffsetsEqual(currentOffsets, nextOffsets)) {
      return false;
    }
    store.setState({
      assembly: {
        ...state.assembly,
        trackDragOffsets: nextOffsets,
      },
    });
    return true;
  }

  async function refreshPhasedTracksForCurrentChr(host, store, { deletedKey = "", forceFinalPathRefresh = false } = {}) {
    const state = store.getState();
    const viewRequest = currentAssemblyViewRequest(store);
    const workspaceRoot = state.session?.workspacePath;
    const projectId = state.session?.projectId;
    const parentChrName = String(state.assembly?.selectedChrName || "").trim();
    if (!workspaceRoot || !projectId || !parentChrName) {
      return null;
    }
    const request = {};
    refreshRequests.set(store, request);
    const result = await listPhasedChrTracks({ workspaceRoot, projectId, parentChrName });
    if (refreshRequests.get(store) !== request || !isCurrentScope(store, state, viewRequest)) {
      return null;
    }
    const current = store.getState().assembly;
    const previousTracks = Array.isArray(current.phasedChrTracks) ? current.phasedChrTracks : [];
    const phasedChrTracks = hydratePhasedTracksForCurrentAssembly(result?.tracks, current);
    const currentFinalKey = String(current.activeFinalPathKeyByChr?.[parentChrName]
      || current.activeFinalPathKey || "").trim();
    const patch = reconcileTrackState(current, previousTracks, phasedChrTracks, parentChrName, { deletedKey });
    store.setState({ assembly: { ...current, ...patch } });
    // Main patches exclude Final Path. Refresh it for changed track topology or
    // path context, but keep item-only edits from needlessly rebuilding the card.
    const topologyChanged = previousTracks.length !== phasedChrTracks.length
      || previousTracks.some((track, index) => {
        const next = phasedChrTracks[index];
        return normalizeSupportDatasetId(track.phasedTrackId) !== next?.phasedTrackId
          || track.haplotypeKey !== next?.haplotypeKey || track.label !== next?.label;
      });
    const previousFinalKey = previousTracks.length ? currentFinalKey || FINAL_PATH_ALL_KEY : "";
    rerenderAssemblyMainTab(host, store);
    if (forceFinalPathRefresh || topologyChanged || previousFinalKey !== patch.activeFinalPathKey) {
      rerenderFinalPathCard(host, store);
    }
    return phasedChrTracks;
  }

  async function createPhasedChrTrack(host, store) {
    const state = store.getState();
    const viewRequest = currentAssemblyViewRequest(store);
    const workspaceRoot = state.session?.workspacePath;
    const projectId = state.session?.projectId;
    const parentChrName = String(state.assembly?.selectedChrName || "").trim();
    if (!workspaceRoot || !projectId || !parentChrName) {
      return;
    }
    const hadPhasedTracks = Array.isArray(state.assembly?.phasedChrTracks)
      && state.assembly.phasedChrTracks.length > 0;
    try {
      await createPhasedChrTrackApi({
        workspaceRoot,
        projectId,
        parentChrName,
      });
      if (!isCurrentScope(store, state, viewRequest)) return;
      const phasedChrTracks = await refreshPhasedTracksForCurrentChr(host, store);
      if (!phasedChrTracks) return;
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: "",
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackCreated"),
      });
      if (!hadPhasedTracks && phasedChrTracks.length > 0) {
        void requestAssemblyNotice(host, store, {
          title: tAssembly(store.getState(), "page.phasedTrackGrtNoticeTitle"),
          message: tAssembly(store.getState(), "page.phasedTrackGrtNoticeMessage"),
          confirmLabel: tAssembly(store.getState(), "page.phasedTrackGrtNoticeConfirm"),
        });
      }
    } catch (error) {
      if (!isCurrentScope(store, state, viewRequest)) return;
      const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: mappedError.userMessage,
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackCreateFailed"),
      });
    }
  }

  async function addTrackContigToPhasedTrack(
    host,
    store,
    { phasedTrackId, assemblyCtgId, haplotypeKey = "" },
  ) {
    const state = store.getState();
    const viewRequest = currentAssemblyViewRequest(store);
    const workspaceRoot = state.session?.workspacePath;
    const projectId = state.session?.projectId;
    const normalizedTrackId = normalizeSupportDatasetId(phasedTrackId);
    const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
    const normalizedKey = String(haplotypeKey || "").trim();
    if (!workspaceRoot || !projectId || !normalizedTrackId || !normalizedCtgId) {
      return;
    }
    try {
      const addedResult = await addCtgToPhasedChrTrack({
        workspaceRoot,
        projectId,
        phasedTrackId: normalizedTrackId,
        assemblyCtgId: normalizedCtgId,
      });
      if (!isCurrentScope(store, state, viewRequest)) return;
      const inheritedDragOffset = inheritPrimaryTrackDragOffsetForPhasedItem(store, {
        assemblyCtgId: normalizedCtgId,
        phasedTrackId: normalizedTrackId,
        phasedTrackItemId: addedResult?.item?.itemId ?? addedResult?.item?.phasedTrackItemId,
      });
      if (state.assembly?.selectedChrName && normalizedKey) {
        store.setState({
          assembly: {
            ...store.getState().assembly,
            activePhasedTrackKey: normalizedKey,
            activePhasedTrackKeyByChr: {
              ...(store.getState().assembly?.activePhasedTrackKeyByChr || {}),
              [state.assembly.selectedChrName]: normalizedKey,
            },
          },
        });
      }
      if (!await refreshPhasedTracksForCurrentChr(host, store)) return;
      if (inheritedDragOffset) {
        void persistTrackDragOffsets(host, store);
      }
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: "",
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemAdded", {
          key: normalizedKey,
        }),
      });
    } catch (error) {
      if (!isCurrentScope(store, state, viewRequest)) return;
      const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: mappedError.userMessage,
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemAddFailed"),
      });
    }
  }

  async function removePhasedTrackItem(host, store, { phasedTrackItemId }) {
    const state = store.getState();
    const viewRequest = currentAssemblyViewRequest(store);
    const workspaceRoot = state.session?.workspacePath;
    const projectId = state.session?.projectId;
    const normalizedItemId = normalizeSupportDatasetId(phasedTrackItemId);
    if (!workspaceRoot || !projectId || !normalizedItemId) {
      return;
    }
    try {
      await removePhasedChrTrackItem({
        workspaceRoot,
        projectId,
        phasedTrackItemId: normalizedItemId,
      });
      if (!isCurrentScope(store, state, viewRequest)) return;
      if (!await refreshPhasedTracksForCurrentChr(host, store)) return;
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: "",
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemRemoved"),
      });
    } catch (error) {
      if (!isCurrentScope(store, state, viewRequest)) return;
      const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: mappedError.userMessage,
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemRemoveFailed"),
      });
    }
  }

  function resolveActivePhasedKeyAfterDelete({ currentKey, tracksAfter, deletedKey }) {
    const keys = (Array.isArray(tracksAfter) ? tracksAfter : [])
      .map((track) => String(track?.haplotypeKey || "").trim())
      .filter(Boolean);
    if (!keys.length) {
      return "";
    }
    if (currentKey && currentKey !== deletedKey && keys.includes(currentKey)) {
      return currentKey;
    }
    if (deletedKey && keys.includes(deletedKey)) {
      return deletedKey;
    }
    return keys[Math.max(0, keys.length - 1)] || "";
  }

  async function deletePhasedTrack(host, store, { phasedTrackId, haplotypeKey = "" }) {
    const state = store.getState();
    const viewRequest = currentAssemblyViewRequest(store);
    const workspaceRoot = state.session?.workspacePath;
    const projectId = state.session?.projectId;
    const parentChrName = String(state.assembly?.selectedChrName || "").trim();
    const normalizedTrackId = normalizeSupportDatasetId(phasedTrackId);
    const normalizedKey = String(haplotypeKey || "").trim();
    if (!workspaceRoot || !projectId || !parentChrName || !normalizedTrackId) {
      return;
    }
    const tracksBefore = Array.isArray(state.assembly?.phasedChrTracks)
      ? state.assembly.phasedChrTracks
      : [];
    try {
      await deletePhasedChrTrack({
        workspaceRoot,
        projectId,
        phasedTrackId: normalizedTrackId,
      });
      if (!isCurrentProject(store, state)) return;
      const nextFinalPathByChr = compactFinalPathByDeletedPhasedTrack(
        store.getState().assembly?.finalPathByChr,
        {
          parentChrName,
          tracksBefore,
          deletedPhasedTrackId: normalizedTrackId,
        },
      );
      store.setState({
        assembly: {
          ...store.getState().assembly,
          ...reconcileTrackState(store.getState().assembly, tracksBefore,
            topologyAfterDelete(tracksBefore, normalizedTrackId, parentChrName), parentChrName,
            { deletedKey: normalizedKey, fallback: state.assembly }),
          finalPathByChr: nextFinalPathByChr,
        },
      });
      let refreshed = null;
      try {
        if (isCurrentScope(store, state, viewRequest)) {
          refreshed = await refreshPhasedTracksForCurrentChr(host, store, {
            deletedKey: normalizedKey, forceFinalPathRefresh: true,
          });
        }
      } catch (error) {
        // Listing failure cannot undo a committed deletion. Paint the reliable
        // locally compacted topology before reporting the refresh error.
        if (isCurrentScope(store, state, viewRequest)) {
          rerenderAssemblyMainTab(host, store);
          rerenderFinalPathCard(host, store);
        }
        throw error;
      } finally {
        // The backend deletion has committed. Its original-chromosome path
        // cleanup must be saved even if navigation supersedes the UI refresh.
        // Production wraps this entire mutation in the project coordinator;
        // project-switch flushes drain it before replacing the owning session.
        if (isCurrentProject(store, state)) await persistMainTrackViewState(host, store);
      }
      if (!isCurrentScope(store, state, viewRequest)) return;
      // A newer item-only list can supersede our response after the model was
      // compacted. It cannot see the consumed topology change, so the committed
      // deletion still owes the mounted Final Path card a redraw.
      if (!refreshed) rerenderFinalPathCard(host, store);
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: "",
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackDeleted", {
          key: normalizedKey,
        }),
      });
    } catch (error) {
      if (!isCurrentScope(store, state, viewRequest)) return;
      const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: mappedError.userMessage,
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackDeleteFailed"),
      });
    }
  }

  return {
    addTrackContigToPhasedTrack: serialized(addTrackContigToPhasedTrack),
    createPhasedChrTrack: serialized(createPhasedChrTrack),
    deletePhasedTrack: serialized(deletePhasedTrack),
    inheritPrimaryTrackDragOffsetForPhasedItem,
    refreshPhasedTracksForCurrentChr,
    removePhasedTrackItem: serialized(removePhasedTrackItem),
  };
}
