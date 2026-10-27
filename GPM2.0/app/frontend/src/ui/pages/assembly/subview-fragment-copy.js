export const localFragmentCopy = {
  zh: {
    split: "分割 Contig", splitFragment: "分割当前片段", localSplit: "仅在当前局部视图分割…", mainSplit: "分割并同步主视图…",
    merge: "撤销分割", mergeLeft: "撤销左侧分割", mergeRight: "撤销右侧分割",
    mergeUnavailable: "该侧没有同源、同向且源区间连续的片段或删除记录；仅作用于局部视图",
    delete: "删除 Contig", deleteFragment: "删除当前片段", localDelete: "仅从当前局部视图删除", mainDelete: "同步从主视图删除…",
    syncUnavailable: "该对象不属于当前主数据集的可编辑实体，不能同步修改主视图",
    stale: "局部视图或片段已变化，请重新打开菜单。", localDone: "已更新当前局部视图；主视图未改变。",
    syncDone: "已同步修改主视图与当前局部视图；可分别使用各自的撤销／重做。",
    syncRefreshFailed: "主视图操作已提交，但刷新或保存局部视图失败；请重新加载，不要重复执行。",
    syncPending: "同步片段编辑尚不可用。", splitUnavailable: "当前片段只有 1 bp，无法继续分割",
  },
  en: {
    split: "Split contig", splitFragment: "Split current fragment", localSplit: "Split only in current Local View…", mainSplit: "Split and synchronize Main View…",
    merge: "Undo split", mergeLeft: "Undo left split", mergeRight: "Undo right split",
    mergeUnavailable: "No same-source, same-orientation adjacent fragment or deletion record on this side; Local View only",
    delete: "Delete contig", deleteFragment: "Delete current fragment", localDelete: "Delete only from current Local View", mainDelete: "Synchronize deletion to Main View…",
    syncUnavailable: "This object is not an editable entity of the current primary dataset",
    stale: "Local View or fragment changed. Reopen the menu.", localDone: "Current Local View updated; Main View unchanged.",
    syncDone: "Main View and current Local View updated; their undo/redo histories remain independent.",
    syncRefreshFailed: "Main View committed, but Local View refresh or save failed. Reload instead of repeating the operation.",
    syncPending: "Synchronized fragment editing is not available yet.", splitUnavailable: "A 1 bp fragment cannot be split further",
  },
};
