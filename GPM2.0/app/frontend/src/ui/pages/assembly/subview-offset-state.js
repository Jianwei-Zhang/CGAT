export function resolveSubviewAutoTrackOffsets({
  topLengthBp,
  bottomLengthBp,
  domainEnd,
  segmentPairs,
}) {
  if (topLengthBp === bottomLengthBp) {
    return { topOffsetBp: 0, bottomOffsetBp: 0 };
  }
  const shorterTrack = topLengthBp < bottomLengthBp ? "top" : "bottom";
  const shorterLengthBp = shorterTrack === "top" ? topLengthBp : bottomLengthBp;
  const maxOffsetBp = Math.max(0, domainEnd - shorterLengthBp);
  if (!Array.isArray(segmentPairs) || !segmentPairs.length || maxOffsetBp <= 0) {
    return { topOffsetBp: 0, bottomOffsetBp: 0 };
  }
  const offsetCandidates = segmentPairs
    .map(({ topSegment, bottomSegment }) => {
      const topMid = (Number(topSegment?.ctgStart) + Number(topSegment?.ctgEnd)) / 2;
      const bottomMid = (Number(bottomSegment?.ctgStart) + Number(bottomSegment?.ctgEnd)) / 2;
      if (!Number.isFinite(topMid) || !Number.isFinite(bottomMid)) {
        return null;
      }
      const rawOffsetBp = shorterTrack === "top" ? bottomMid - topMid : topMid - bottomMid;
      return clampSubviewTrackOffsetBp(rawOffsetBp, maxOffsetBp);
    })
    .filter((value) => Number.isFinite(value));
  if (!offsetCandidates.length) {
    return { topOffsetBp: 0, bottomOffsetBp: 0 };
  }
  const resolvedOffsetBp = resolveMedianNumber(offsetCandidates);
  return shorterTrack === "top"
    ? { topOffsetBp: resolvedOffsetBp, bottomOffsetBp: 0 }
    : { topOffsetBp: 0, bottomOffsetBp: resolvedOffsetBp };
}

function clampSubviewTrackOffsetBp(value, maxOffsetBp) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.min(Math.max(0, numeric), Math.max(0, Number(maxOffsetBp) || 0));
}

function resolveMedianNumber(values) {
  const sorted = [...values].sort((left, right) => left - right);
  const middleIndex = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[middleIndex];
  }
  return (sorted[middleIndex - 1] + sorted[middleIndex]) / 2;
}
