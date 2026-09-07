import { normalizeSubviewComposition } from "./subview-composition-state.js";
import { normalizePositiveInt, resolveTrackInnerWidthFromScale, resolveTrackPrefs } from "./track-prefs.js";

export function resolveSubviewCompositionScaleViewport(composition, {
  trackPrefs,
  viewportWidthPx = 1_200,
  centerBp,
  topPx = 0,
} = {}) {
  const { members } = normalizeSubviewComposition(composition);
  const windowStart = Math.min(0, ...members.map((member) => member.xBp));
  const windowEnd = Math.max(0, ...members.map((member) => member.xBp + member.lengthBp));
  const domainSpanBp = Math.max(1, windowEnd - windowStart);
  const viewportWidth = normalizePositiveInt(viewportWidthPx) ?? 1_200;
  const innerWidth = resolveTrackInnerWidthFromScale({
    ...resolveTrackPrefs(trackPrefs),
    domainSpanBp,
    baseViewportPx: viewportWidth,
  });
  const bpPerPx = domainSpanBp / innerWidth;
  const visibleSpanBp = viewportWidth * bpPerPx;
  const requestedLeft = Number.isFinite(centerBp) ? centerBp - visibleSpanBp / 2 : windowStart;
  return {
    bpPerPx,
    leftBp: Math.max(windowStart, Math.min(windowEnd - visibleSpanBp, requestedLeft)),
    topPx,
  };
}

export function buildSubviewCompositionLayout(composition, {
  bpPerPx = 1_000,
  viewportWidthPx = 1_200,
  leftBp = 0,
} = {}) {
  const normalized = normalizeSubviewComposition(composition);
  const scale = Number.isFinite(Number(bpPerPx)) && Number(bpPerPx) > 0 ? Number(bpPerPx) : 1_000;
  const viewportWidth = Number.isFinite(Number(viewportWidthPx)) && Number(viewportWidthPx) > 0
    ? Number(viewportWidthPx)
    : 1_200;
  const members = normalized.members.map((member) => ({
    ...member,
    x: member.xBp / scale,
    width: Math.max(1, member.lengthBp / scale),
    bpPerPx: scale,
  }));
  const minimumX = Math.min(0, leftBp / scale, ...members.map((member) => member.x));
  const maximumX = Math.max(
    viewportWidth + leftBp / scale,
    ...members.map((member) => member.x + member.width),
  );
  return {
    members,
    top: members.filter((member) => member.lane === "top"),
    bottom: members.filter((member) => member.lane === "bottom"),
    bpPerPx: scale,
    leftBp: Number.isFinite(Number(leftBp)) ? Number(leftBp) : 0,
    viewBoxMinX: Math.floor(minimumX),
    width: Math.max(viewportWidth, Math.ceil(maximumX - minimumX)),
  };
}

export function resolveSubviewCompositionXbp(layout, xPx) {
  const scale = Number(layout?.bpPerPx);
  const position = Number(xPx);
  return Number.isFinite(scale) && scale > 0 && Number.isFinite(position) ? position * scale : null;
}
