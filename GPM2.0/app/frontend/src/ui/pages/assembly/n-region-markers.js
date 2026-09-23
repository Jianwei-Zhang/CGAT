import { normalizePositiveInt } from "./track-prefs.js";
import { buildTrackHitRectWithinCtgDisplay } from "./track-render-geometry.js";

function resolveVisibleNRegionMarkerRect(markerRect, ctgRect) {
  const minimumMarkerWidth = 6;
  const ctgLeft = Number(ctgRect?.x);
  const ctgWidth = Number(ctgRect?.width);
  if (!Number.isFinite(ctgLeft) || !Number.isFinite(ctgWidth) || ctgWidth <= 0) {
    return null;
  }
  const markerCenterX = Number.isFinite(markerRect?.centerX)
    ? markerRect.centerX
    : Number(markerRect?.x || 0) + Number(markerRect?.width || 0) / 2;
  const markerWidth = Math.min(
    ctgWidth,
    Math.max(minimumMarkerWidth, Number(markerRect?.width || 0)),
  );
  const minX = ctgLeft;
  const maxX = ctgLeft + ctgWidth - markerWidth;
  const x = Math.max(minX, Math.min(maxX, markerCenterX - markerWidth / 2));
  return {
    x,
    width: markerWidth,
    centerX: x + markerWidth / 2,
  };
}

export function renderNRegionMarkersForTrackCtg({
  ctg, rect, y, barHeight, isMirror = false, flipped = false, escapeAttr, escapeHtml,
}) {
  if (isMirror || !Array.isArray(ctg?.nRegions) || ctg.nRegions.length === 0) {
    return "";
  }
  return ctg.nRegions
    .map((region) => {
      const ctgStart = normalizePositiveInt(region?.ctgStart ?? region?.ctg_start ?? region?.startBp ?? region?.start_bp);
      const ctgEnd = normalizePositiveInt(region?.ctgEnd ?? region?.ctg_end ?? region?.endBp ?? region?.end_bp);
      const length = normalizePositiveInt(ctg.lengthBp ?? ctg.totalLength);
      if (!ctgStart || !ctgEnd || !length) return "";
      const markerRect = buildTrackHitRectWithinCtgDisplay({
        ctgRect: rect,
        ctgLengthBp: length,
        ctgStartOffset: flipped ? length - ctgEnd + 1 : ctgStart,
        ctgEndOffset: flipped ? length - ctgStart + 1 : ctgEnd,
      });
      if (!Number.isFinite(markerRect.x) || !Number.isFinite(markerRect.width) || markerRect.width <= 0) {
        return "";
      }
      const visibleMarkerRect = resolveVisibleNRegionMarkerRect(markerRect, rect);
      if (!visibleMarkerRect) {
        return "";
      }
      const lengthValue = normalizePositiveInt(region?.lengthBp ?? region?.length_bp)
        ?? (ctgStart && ctgEnd ? Math.abs(ctgEnd - ctgStart) + 1 : null);
      const tooltip = [
        "N",
        ctgStart && ctgEnd ? `${ctgStart}-${ctgEnd}` : "",
        lengthValue ? String(lengthValue) : "",
      ].filter(Boolean).join("\t");
      return `<rect
            class="track-n-region-marker"
            data-n-region-marker="1"
            data-n-region-contig-id="${escapeAttr(String(ctg.assemblyCtgId))}"
            data-n-region-ctg-start="${escapeAttr(String(ctgStart ?? ""))}"
            data-n-region-ctg-end="${escapeAttr(String(ctgEnd ?? ""))}"
            data-n-region-length="${escapeAttr(String(lengthValue ?? ""))}"
            x="${visibleMarkerRect.x.toFixed(2)}"
            y="${(y + 1).toFixed(2)}"
            width="${visibleMarkerRect.width.toFixed(2)}"
            height="${Math.max(1, barHeight - 2)}"
            rx="1.5"
            ry="1.5"
          ><title>${escapeHtml(tooltip)}</title></rect>`;
    })
    .filter(Boolean)
    .join("");
}
