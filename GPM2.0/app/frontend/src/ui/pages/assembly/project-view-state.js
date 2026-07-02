import {
  getProjectAssemblyViewState as getProjectAssemblyViewStateApi,
  setProjectAssemblyViewState as setProjectAssemblyViewStateApi,
} from "../../../services/workflow-api.js";
import { normalizeViewportScrollState } from "./scroll-position-state.js";
import {
  normalizeHiddenPrimaryCtgIds,
  normalizeHiddenPrimaryCtgIdsByChr,
  normalizeSubviewTrackDragOffsets,
  normalizeSupportDatasetId,
  normalizeSupportMirroredCtgs,
  normalizeTrackDragOffsets,
} from "./selection-state.js";
import { normalizeFinalPathByChr, normalizeFinalPathViewMode as normalizeFinalPathViewModeState } from "./final-path-state.js";
import { normalizeDegapProjectState } from "./degap-state.js";
import { resolveTrackPrefs } from "./track-prefs.js";
import {
  normalizeSupportDsCtgLenRulesByChr,
} from "./support-ds-ctg-len-rules.js";
import {
  normalizeSubviewAnchorStateByKey,
} from "./subview-anchor-state.js";

function normalizeFinalPathViewMode(value) {
  return normalizeFinalPathViewModeState(value);
}

function normalizeMembersCardCollapsed(value) {
  return value === false ? false : true;
}

export async function loadProjectAssemblyViewState({ workspaceRoot, projectId }, deps = {}) {
  const getProjectAssemblyViewState =
    deps.getProjectAssemblyViewState || getProjectAssemblyViewStateApi;
  const normalizeSupportId = deps.normalizeSupportDatasetId || normalizeSupportDatasetId;
  const normalizeTrackView = deps.resolveTrackPrefs || resolveTrackPrefs;
  const normalizeMirrors = deps.normalizeSupportMirroredCtgs || normalizeSupportMirroredCtgs;
  const normalizeHiddenIds = deps.normalizeHiddenPrimaryCtgIds || normalizeHiddenPrimaryCtgIds;
  const normalizeTrackOffsets = deps.normalizeTrackDragOffsets || normalizeTrackDragOffsets;
  const normalizeSubviewOffsets =
    deps.normalizeSubviewTrackDragOffsets || normalizeSubviewTrackDragOffsets;
  const normalizeTrackScrollState =
    deps.normalizeViewportScrollState || normalizeViewportScrollState;
  const normalizeFinalPath = deps.normalizeFinalPathByChr || normalizeFinalPathByChr;
  const normalizeViewMode = deps.normalizeFinalPathViewMode || normalizeFinalPathViewMode;
  const normalizeMembersCollapsed =
    deps.normalizeMembersCardCollapsed || normalizeMembersCardCollapsed;
  if (!workspaceRoot || !projectId) {
    return {
      supportDatasetId: null,
      trackView: normalizeTrackView({}),
      supportMirroredCtgs: [],
      supportDsCtgLenRulesByChr: {},
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: {},
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {},
      trackScrollState: normalizeTrackScrollState({}),
      subviewTrackScrollState: normalizeTrackScrollState({}),
      finalPathTrackScrollState: normalizeTrackScrollState({}),
      membersCardCollapsed: normalizeMembersCollapsed(true),
      finalPathViewMode: normalizeViewMode("graph"),
      finalPathByChr: normalizeFinalPath({}),
      degapProjectState: normalizeDegapProjectState({}),
    };
  }
  const result = await getProjectAssemblyViewState({ workspaceRoot, projectId });
  return {
    supportDatasetId: normalizeSupportId(result?.supportDatasetId),
    trackView: normalizeTrackView(result?.trackView),
    supportMirroredCtgs: normalizeMirrors(result?.supportMirroredCtgs),
    supportDsCtgLenRulesByChr: normalizeSupportDsCtgLenRulesByChr(result?.supportDsCtgLenRulesByChr),
    hiddenPrimaryCtgIds: normalizeHiddenIds(result?.hiddenPrimaryCtgIds),
    hiddenPrimaryCtgIdsByChr: normalizeHiddenPrimaryCtgIdsByChr(result?.hiddenPrimaryCtgIdsByChr),
    trackDragOffsets: normalizeTrackOffsets(result?.trackDragOffsets),
    subviewTrackDragOffsets: normalizeSubviewOffsets(result?.subviewTrackDragOffsets),
    subviewAnchorStateByKey: normalizeSubviewAnchorStateByKey(result?.subviewAnchorStateByKey),
    trackScrollState: normalizeTrackScrollState(result?.trackScrollState),
    subviewTrackScrollState: normalizeTrackScrollState(result?.subviewTrackScrollState),
    finalPathTrackScrollState: normalizeTrackScrollState(result?.finalPathTrackScrollState),
    membersCardCollapsed: normalizeMembersCollapsed(result?.membersCardCollapsed),
    finalPathViewMode: normalizeViewMode(result?.finalPathViewMode),
    finalPathByChr: normalizeFinalPath(result?.finalPathByChr),
    degapProjectState: normalizeDegapProjectState(result?.degapProjectState),
  };
}

export async function persistProjectAssemblyViewState(
  {
    workspaceRoot,
    projectId,
    supportDatasetId = null,
    trackView = {},
    supportMirroredCtgs = [],
    supportDsCtgLenRulesByChr = {},
    hiddenPrimaryCtgIds = [],
    hiddenPrimaryCtgIdsByChr = {},
    trackDragOffsets = [],
    subviewTrackDragOffsets = [],
    subviewAnchorStateByKey = {},
    trackScrollState = {},
    subviewTrackScrollState = {},
    finalPathTrackScrollState = {},
    membersCardCollapsed = true,
    finalPathViewMode = "graph",
    finalPathByChr = {},
    degapProjectState = {},
  },
  deps = {},
) {
  const setProjectAssemblyViewState =
    deps.setProjectAssemblyViewState || setProjectAssemblyViewStateApi;
  const normalizeSupportId = deps.normalizeSupportDatasetId || normalizeSupportDatasetId;
  const normalizeTrackView = deps.resolveTrackPrefs || resolveTrackPrefs;
  const normalizeMirrors = deps.normalizeSupportMirroredCtgs || normalizeSupportMirroredCtgs;
  const normalizeHiddenIds = deps.normalizeHiddenPrimaryCtgIds || normalizeHiddenPrimaryCtgIds;
  const normalizeTrackOffsets = deps.normalizeTrackDragOffsets || normalizeTrackDragOffsets;
  const normalizeSubviewOffsets =
    deps.normalizeSubviewTrackDragOffsets || normalizeSubviewTrackDragOffsets;
  const normalizeTrackScrollState =
    deps.normalizeViewportScrollState || normalizeViewportScrollState;
  const normalizeFinalPath = deps.normalizeFinalPathByChr || normalizeFinalPathByChr;
  const normalizeViewMode = deps.normalizeFinalPathViewMode || normalizeFinalPathViewMode;
  const normalizeMembersCollapsed =
    deps.normalizeMembersCardCollapsed || normalizeMembersCardCollapsed;
  const normalizedSupportDatasetId = normalizeSupportId(supportDatasetId);
  const normalizedTrackView = normalizeTrackView(trackView);
  const normalizedMirrors = normalizeMirrors(supportMirroredCtgs);
  const normalizedSupportDsCtgLenRulesByChr =
    normalizeSupportDsCtgLenRulesByChr(supportDsCtgLenRulesByChr);
  const normalizedHiddenIds = normalizeHiddenIds(hiddenPrimaryCtgIds);
  const normalizedHiddenIdsByChr = normalizeHiddenPrimaryCtgIdsByChr(hiddenPrimaryCtgIdsByChr);
  const normalizedTrackOffsets = normalizeTrackOffsets(trackDragOffsets);
  const normalizedSubviewOffsets = normalizeSubviewOffsets(subviewTrackDragOffsets);
  const normalizedSubviewAnchorStateByKey = normalizeSubviewAnchorStateByKey(subviewAnchorStateByKey);
  const normalizedTrackScrollState = normalizeTrackScrollState(trackScrollState);
  const normalizedSubviewTrackScrollState = normalizeTrackScrollState(subviewTrackScrollState);
  const normalizedFinalPathTrackScrollState = normalizeTrackScrollState(finalPathTrackScrollState);
  const normalizedMembersCardCollapsed = normalizeMembersCollapsed(membersCardCollapsed);
  const normalizedFinalPathViewMode = normalizeViewMode(finalPathViewMode);
  const normalizedFinalPathByChr = normalizeFinalPath(finalPathByChr);
  const normalizedDegapProjectState = normalizeDegapProjectState(degapProjectState);
  if (!workspaceRoot || !projectId) {
    return {
      supportDatasetId: normalizedSupportDatasetId,
      trackView: normalizedTrackView,
      supportMirroredCtgs: normalizedMirrors,
      supportDsCtgLenRulesByChr: normalizedSupportDsCtgLenRulesByChr,
      hiddenPrimaryCtgIds: normalizedHiddenIds,
      hiddenPrimaryCtgIdsByChr: normalizedHiddenIdsByChr,
      trackDragOffsets: normalizedTrackOffsets,
      subviewTrackDragOffsets: normalizedSubviewOffsets,
      subviewAnchorStateByKey: normalizedSubviewAnchorStateByKey,
      trackScrollState: normalizedTrackScrollState,
      subviewTrackScrollState: normalizedSubviewTrackScrollState,
      finalPathTrackScrollState: normalizedFinalPathTrackScrollState,
      membersCardCollapsed: normalizedMembersCardCollapsed,
      finalPathViewMode: normalizedFinalPathViewMode,
      finalPathByChr: normalizedFinalPathByChr,
      degapProjectState: normalizedDegapProjectState,
    };
  }
  const result = await setProjectAssemblyViewState({
    workspaceRoot,
    projectId,
    supportDatasetId: normalizedSupportDatasetId,
    trackView: normalizedTrackView,
    supportDsCtgLenRulesByChr: normalizedSupportDsCtgLenRulesByChr,
    supportMirroredCtgs: normalizedMirrors,
    hiddenPrimaryCtgIds: normalizedHiddenIds,
    hiddenPrimaryCtgIdsByChr: normalizedHiddenIdsByChr,
    trackDragOffsets: normalizedTrackOffsets,
    subviewTrackDragOffsets: normalizedSubviewOffsets,
    subviewAnchorStateByKey: normalizedSubviewAnchorStateByKey,
    trackScrollState: normalizedTrackScrollState,
    subviewTrackScrollState: normalizedSubviewTrackScrollState,
    finalPathTrackScrollState: normalizedFinalPathTrackScrollState,
    membersCardCollapsed: normalizedMembersCardCollapsed,
    finalPathViewMode: normalizedFinalPathViewMode,
    finalPathByChr: normalizedFinalPathByChr,
    degapProjectState: normalizedDegapProjectState,
  });
  return {
    supportDatasetId: normalizeSupportId(result?.supportDatasetId ?? normalizedSupportDatasetId),
    trackView: normalizeTrackView(result?.trackView ?? normalizedTrackView),
    supportMirroredCtgs: normalizeMirrors(result?.supportMirroredCtgs ?? normalizedMirrors),
    supportDsCtgLenRulesByChr: normalizeSupportDsCtgLenRulesByChr(
      result?.supportDsCtgLenRulesByChr ?? normalizedSupportDsCtgLenRulesByChr,
    ),
    hiddenPrimaryCtgIds: normalizeHiddenIds(result?.hiddenPrimaryCtgIds ?? normalizedHiddenIds),
    hiddenPrimaryCtgIdsByChr: normalizeHiddenPrimaryCtgIdsByChr(
      result?.hiddenPrimaryCtgIdsByChr ?? normalizedHiddenIdsByChr,
    ),
    trackDragOffsets: normalizeTrackOffsets(result?.trackDragOffsets ?? normalizedTrackOffsets),
    subviewTrackDragOffsets: normalizeSubviewOffsets(
      result?.subviewTrackDragOffsets ?? normalizedSubviewOffsets,
    ),
    subviewAnchorStateByKey: normalizeSubviewAnchorStateByKey(
      result?.subviewAnchorStateByKey ?? normalizedSubviewAnchorStateByKey,
    ),
    trackScrollState: normalizeTrackScrollState(
      result?.trackScrollState ?? normalizedTrackScrollState,
    ),
    subviewTrackScrollState: normalizeTrackScrollState(
      result?.subviewTrackScrollState ?? normalizedSubviewTrackScrollState,
    ),
    finalPathTrackScrollState: normalizeTrackScrollState(
      result?.finalPathTrackScrollState ?? normalizedFinalPathTrackScrollState,
    ),
    membersCardCollapsed: normalizeMembersCollapsed(
      result?.membersCardCollapsed ?? normalizedMembersCardCollapsed,
    ),
    finalPathViewMode: normalizeViewMode(
      result?.finalPathViewMode ?? normalizedFinalPathViewMode,
    ),
    finalPathByChr: normalizeFinalPath(result?.finalPathByChr ?? normalizedFinalPathByChr),
    degapProjectState: normalizeDegapProjectState(result?.degapProjectState ?? normalizedDegapProjectState),
  };
}
