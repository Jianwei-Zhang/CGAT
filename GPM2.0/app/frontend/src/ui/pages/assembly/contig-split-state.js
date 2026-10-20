// Split cuts are source-coordinate boundaries after base k, never reference coordinates.
export function parseSplitCuts(text, source) {
  const tokens = String(text ?? "").trim().split(/[\s,;，；]+/).filter(Boolean);
  if (!tokens.length || tokens.length > 32 || tokens.some((v) => !/^\d+$/.test(v))) {
    throw new Error("invalid-cuts");
  }
  const cuts = tokens.map(Number).sort((a, b) => a - b);
  if (new Set(cuts).size !== cuts.length || cuts.some((k) => !Number.isSafeInteger(k)
    || k < source.sourceStart || k >= source.sourceEnd)) throw new Error("invalid-cuts");
  return cuts;
}

export function splitCutFraction(source, cut) {
  const fraction = (cut - source.sourceStart + 1) / (source.sourceEnd - source.sourceStart + 1);
  return source.orient === "-" ? 1 - fraction : fraction;
}

export function splitCutFromFraction(source, fraction) {
  const bounded = Math.max(0, Math.min(1, fraction));
  const forward = source.orient === "-" ? 1 - bounded : bounded;
  return Math.max(source.sourceStart, Math.min(source.sourceEnd - 1,
    Math.round(source.sourceStart - 1 + forward * (source.sourceEnd - source.sourceStart + 1))));
}

export function splitBoundaryCuts(hit, source) {
  return [Number(hit.queryStart) - 1, Number(hit.queryEnd)]
    .filter((k) => Number.isSafeInteger(k) && k >= source.sourceStart && k < source.sourceEnd);
}

export function defaultSplitAssignments(preview, previous = new Map()) {
  return preview.parts.map((part) => {
    const key = `${part.sourceStart}:${part.sourceEnd}`;
    const choices = new Set([null, preview.source.assignedChrName, ...part.candidates.map((c) => c.chrName)]);
    if (previous.has(key) && choices.has(previous.get(key))) return previous.get(key);
    // Evidence is a recommendation, not automatic adoption in Final Path.
    const best = part.candidates[0];
    const runnerUp = part.candidates[1];
    return best?.highQualityCoveragePercent >= 60
      && (!runnerUp || best.highQualityCoveragePercent - runnerUp.highQualityCoveragePercent >= 10)
      ? best.chrName : null;
  });
}

export const splitCopy = {
  zh: {
    title: "ctg 分段与染色体归组", manual: "手动分段", boundary: "按 Ref 比对边界", recommended: "推荐分段",
    source: "原始序列区间", direction: "显示方向", cuts: "在原始坐标之后切开（多个切点用逗号分隔）",
    preview: "更新预览", cancel: "取消", confirm: "确认分段与归组", loading: "正在读取比对证据…",
    invalid: "请输入区间内部、不重复的整数切点（最多 32 个）。", noRecommendation: "没有达到推荐条件的跨 chr 断点；仍可手动或按比对边界分段。",
    hint: "点击或拖动画布设置切线；点击比对端点快捷选择边界。所有坐标均为原始序列 1-based 坐标。",
    reverse: "当前反向显示：画面左端是原始序列高坐标端。", unplaced: "未归组", fragment: "片段",
    group: "加入 chr 组", coverage: "片段覆盖率", identity: "比对块加权一致性", target: "参考区间",
    approximate: "近似端点投影（缺少 CIGAR）", boundaryStart: "比对起点前", boundaryEnd: "比对终点后",
    overlap: "比对重叠区：切点不唯一", unaligned: "未比对区：可单独保留中间片段", boundaryRegion: "染色体支持转换边界",
    pathNotice: "已有 Final Path 引用：{count}。只拆分来源引用，保持路径序列与顺序不变；归组不会自动加入目标 Final Path。",
    undoNotice: "此操作由当前 chr 的主视图历史统一撤销，恢复所有受影响片段；目标 chr 后续编辑会受到冲突保护。",
    noHits: "此片段没有参考比对证据。", stale: "项目或预览已变化，请重新打开分段窗口。", done: "分段完成；片段已按选择归组，Final Path 序列保持不变。",
    quality: "高质量覆盖", mapq: "最低 MAPQ", choose: "采用此候选", before: "起点前", after: "终点后",
  },
  en: {
    title: "Split contig and assign fragments", manual: "Manual cut", boundary: "Ref alignment boundary", recommended: "Recommended cuts",
    source: "Original source interval", direction: "Display orientation", cuts: "Cut after source base (comma-separated for multiple cuts)",
    preview: "Update preview", cancel: "Cancel", confirm: "Confirm split and assignment", loading: "Reading alignment evidence…",
    invalid: "Enter distinct integer cuts inside the interval (up to 32).", noRecommendation: "No cross-chromosome breakpoint meets recommendation criteria. Manual and alignment-boundary cuts remain available.",
    hint: "Click or drag the canvas to position a cut; click an alignment endpoint for a boundary cut. Coordinates are 1-based original source coordinates.",
    reverse: "Reverse display: the left side is the high-coordinate end of the source.", unplaced: "Unplaced", fragment: "Fragment",
    group: "Assign to chromosome", coverage: "Fragment coverage", identity: "Weighted whole-hit identity", target: "Reference interval",
    approximate: "Approximate endpoint projection (no CIGAR)", boundaryStart: "Before alignment start", boundaryEnd: "After alignment end",
    overlap: "Overlapping alignments: no unique breakpoint", unaligned: "Unaligned interval: may be retained as a separate fragment", boundaryRegion: "Chromosome-support transition",
    pathNotice: "Existing Final Path references: {count}. Source references are partitioned without changing path DNA or order. Assignment does not adopt a fragment into the destination Final Path.",
    undoNotice: "Undo from the current chromosome main-view history restores all affected fragments atomically; later destination edits are protected by conflict checks.",
    noHits: "No reference evidence for this fragment.", stale: "Project or preview changed. Reopen the split dialog.", done: "Split complete. Fragments assigned; Final Path DNA preserved.",
    quality: "High-quality coverage", mapq: "Minimum MAPQ", choose: "Use this candidate", before: "Before start", after: "After end",
  },
};
