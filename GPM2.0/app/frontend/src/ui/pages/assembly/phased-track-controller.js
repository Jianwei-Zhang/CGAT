import { tAssembly } from "./i18n.js";
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
  rerenderAssemblyMainTab,
  setAssemblyActionFeedbackInMainTab,
}) {
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

  async function refreshPhasedTracksForCurrentChr(host, store) {
    const state = store.getState();
    const workspaceRoot = state.session?.workspacePath;
    const projectId = state.session?.projectId;
    const parentChrName = String(state.assembly?.selectedChrName || "").trim();
    if (!workspaceRoot || !projectId || !parentChrName) {
      return [];
    }
    const result = await listPhasedChrTracks({
      workspaceRoot,
      projectId,
      parentChrName,
    });
    const phasedChrTracks = hydratePhasedTracksForCurrentAssembly(
      result?.tracks,
      store.getState().assembly,
    );
    const nextActiveKey = phasedChrTracks.some((track) =>
      track.haplotypeKey === store.getState().assembly?.activePhasedTrackKey,
    )
      ? store.getState().assembly.activePhasedTrackKey
      : (phasedChrTracks[0]?.haplotypeKey || "");
    store.setState({
      assembly: {
        ...store.getState().assembly,
        phasedChrTracks,
        isChrPhased: Boolean(phasedChrTracks.length),
        activePhasedTrackKey: nextActiveKey,
        activePhasedTrackKeyByChr: {
          ...(store.getState().assembly?.activePhasedTrackKeyByChr || {}),
          [parentChrName]: nextActiveKey,
        },
      },
    });
    rerenderAssemblyMainTab(host, store);
    return phasedChrTracks;
  }

  async function createPhasedChrTrack(host, store) {
    const state = store.getState();
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
      const phasedChrTracks = await refreshPhasedTracksForCurrentChr(host, store);
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
      await refreshPhasedTracksForCurrentChr(host, store);
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
      const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: mappedError.userMessage,
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemAddFailed"),
      });
    }
  }

  async function removePhasedTrackItem(host, store, { phasedTrackItemId }) {
    const state = store.getState();
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
      await refreshPhasedTracksForCurrentChr(host, store);
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: "",
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemRemoved"),
      });
    } catch (error) {
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
      const nextFinalPathByChr = compactFinalPathByDeletedPhasedTrack(
        state.assembly?.finalPathByChr,
        {
          parentChrName,
          tracksBefore,
          deletedPhasedTrackId: normalizedTrackId,
        },
      );
      store.setState({
        assembly: {
          ...store.getState().assembly,
          finalPathByChr: nextFinalPathByChr,
        },
      });
      const tracksAfter = await refreshPhasedTracksForCurrentChr(host, store);
      const nextActiveKey = resolveActivePhasedKeyAfterDelete({
        currentKey: state.assembly?.activePhasedTrackKey,
        tracksAfter,
        deletedKey: normalizedKey,
      });
      store.setState({
        assembly: {
          ...store.getState().assembly,
          activePhasedTrackKey: nextActiveKey,
          activePhasedTrackKeyByChr: {
            ...(store.getState().assembly?.activePhasedTrackKeyByChr || {}),
            [parentChrName]: nextActiveKey,
          },
        },
      });
      rerenderAssemblyMainTab(host, store);
      await persistMainTrackViewState(host, store);
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: "",
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackDeleted", {
          key: normalizedKey,
        }),
      });
    } catch (error) {
      const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
      setAssemblyActionFeedbackInMainTab(host, store, {
        actionError: mappedError.userMessage,
        actionStatus: tAssembly(store.getState(), "runtime.phasedTrackDeleteFailed"),
      });
    }
  }

  return {
    addTrackContigToPhasedTrack,
    createPhasedChrTrack,
    deletePhasedTrack,
    inheritPrimaryTrackDragOffsetForPhasedItem,
    refreshPhasedTracksForCurrentChr,
    removePhasedTrackItem,
  };
}
