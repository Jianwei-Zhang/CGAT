import { projectGrtSourcePositionToRect } from "./grt-result-state.js";

function normalizePositiveInteger(value) {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

function escapeFallback(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;");
}

function intervalsForEntry(plan, entry) {
  const contigId = normalizePositiveInteger(entry?.ctg?.assemblyCtgId);
  return (Array.isArray(plan?.visualIntervals) ? plan.visualIntervals : [])
    .filter((interval) => interval.assemblyCtgId === contigId);
}

function renderIntervalOverlay(interval, entry, escapeHtml) {
  const firstX = projectGrtSourcePositionToRect(
    interval.sourceStart,
    interval,
    entry.ctg,
    entry.rect,
  );
  const secondX = projectGrtSourcePositionToRect(
    interval.sourceEnd,
    interval,
    entry.ctg,
    entry.rect,
  );
  if (!Number.isFinite(firstX) || !Number.isFinite(secondX)) return "";
  const x = Math.min(firstX, secondX);
  const ctgLength = normalizePositiveInteger(entry?.ctg?.lengthBp ?? entry?.ctg?.totalLength) || 1;
  const baseWidth = Math.max(0, Number(entry?.rect?.width) || 0) / ctgLength;
  const width = Math.max(2, Math.abs(secondX - firstX) + baseWidth);
  const count = Math.max(1, interval.occurrences?.length || 1);
  const rangeList = (interval.occurrences || [interval])
    .map((occurrence) => `${occurrence.sourceStart}-${occurrence.sourceEnd} (${occurrence.orientation})`)
    .join("; ");
  const title = `GRT result · ${interval.datasetName}:${interval.contigName} · ${rangeList}`;
  const countMarkup = count > 1
    ? `<text class="grt-result-repeat-count" x="${(x + width / 2).toFixed(2)}" y="${(entry.y - 3).toFixed(2)}" text-anchor="middle">×${count}</text>`
    : "";
  return `<g class="grt-result-interval-group" data-grt-result-interval="1">
    <rect class="grt-result-interval" x="${x.toFixed(2)}" y="${entry.y.toFixed(2)}" width="${width.toFixed(2)}" height="${entry.height.toFixed(2)}" rx="3" ry="3" pointer-events="none" />
    <rect class="grt-result-hover-proxy" x="${x.toFixed(2)}" y="${entry.y.toFixed(2)}" width="${width.toFixed(2)}" height="${entry.height.toFixed(2)}" fill="transparent" pointer-events="all"><title>${escapeHtml(title)}</title></rect>
    ${countMarkup}
  </g>`;
}

function chooseEndpointEntry(endpoint, entries) {
  const candidates = entries.filter(
    (entry) => normalizePositiveInteger(entry?.ctg?.assemblyCtgId) === endpoint.assemblyCtgId,
  );
  return candidates.find((entry) => entry.isMirror !== true) || candidates[0] || null;
}

function buildEndpoint(endpoint, sourcePosition, entries) {
  const entry = chooseEndpointEntry(endpoint, entries);
  if (!entry) return null;
  const x = projectGrtSourcePositionToRect(sourcePosition, endpoint, entry.ctg, entry.rect);
  if (!Number.isFinite(x)) return null;
  return { entry, x };
}

function renderJunction(junction, entries, escapeHtml, gapLabel) {
  const left = buildEndpoint(junction.left, junction.left.exitSourcePosition, entries);
  const right = buildEndpoint(junction.right, junction.right.entrySourcePosition, entries);
  if (!left || !right) return "";
  const leftEntryKey = String(left.entry?.key || "");
  const rightEntryKey = String(right.entry?.key || "");
  const endpointAttrs = `data-grt-result-junction-left-entry-key="${escapeHtml(leftEntryKey)}" data-grt-result-junction-right-entry-key="${escapeHtml(rightEntryKey)}"`;
  const sameEntry = left.entry === right.entry;
  const leftCenterY = left.entry.y + left.entry.height / 2;
  const rightCenterY = right.entry.y + right.entry.height / 2;
  const title = junction.kind === "gap"
    ? `${gapLabel} · ${junction.gapSizeBp} bp`
    : `GRT result · ${junction.left.datasetName}:${junction.left.contigName} → ${junction.right.datasetName}:${junction.right.contigName}`;
  const cssClass = junction.kind === "gap" ? " is-gap" : "";
  if (sameEntry) {
    const controlY = Math.max(3, left.entry.y - 24);
    const path = `M ${left.x.toFixed(2)} ${leftCenterY.toFixed(2)} Q ${((left.x + right.x) / 2).toFixed(2)} ${controlY.toFixed(2)} ${right.x.toFixed(2)} ${rightCenterY.toFixed(2)}`;
    const label = junction.kind === "gap"
      ? `<text class="grt-result-gap-label" x="${((left.x + right.x) / 2).toFixed(2)}" y="${Math.max(10, controlY - 2).toFixed(2)}" text-anchor="middle">${escapeHtml(title)}</text>`
      : "";
    return `<g class="grt-result-junction-group${cssClass}" data-grt-result-junction="${junction.kind}" ${endpointAttrs}>
      <path class="grt-result-junction${cssClass}" d="${path}" pointer-events="none" />
      <path class="grt-result-hover-proxy" d="${path}" fill="none" stroke="transparent" stroke-width="8" pointer-events="stroke"><title>${escapeHtml(title)}</title></path>
      ${label}
    </g>`;
  }
  const fromTop = leftCenterY <= rightCenterY;
  const y1 = fromTop ? left.entry.y + left.entry.height : left.entry.y;
  const y2 = fromTop ? right.entry.y : right.entry.y + right.entry.height;
  const label = junction.kind === "gap"
    ? `<text class="grt-result-gap-label" data-grt-result-junction-label="1" x="${((left.x + right.x) / 2).toFixed(2)}" y="${((y1 + y2) / 2 - 4).toFixed(2)}" text-anchor="middle">${escapeHtml(title)}</text>`
    : "";
  return `<g class="grt-result-junction-group${cssClass}" data-grt-result-junction="${junction.kind}" ${endpointAttrs}>
    <line class="grt-result-junction${cssClass}" data-grt-result-junction-line="1" x1="${left.x.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${right.x.toFixed(2)}" y2="${y2.toFixed(2)}" pointer-events="none" />
    <line class="grt-result-hover-proxy" data-grt-result-junction-line="1" x1="${left.x.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${right.x.toFixed(2)}" y2="${y2.toFixed(2)}" stroke="transparent" stroke-width="8" pointer-events="stroke"><title>${escapeHtml(title)}</title></line>
    ${label}
  </g>`;
}

function renderDisplayEvidence(evidence, entries, escapeHtml) {
  const source = evidence?.source;
  const target = evidence?.target;
  if (!source || !target) return "";
  const sourceFirstPosition = source.orientation === "-" ? source.end : source.start;
  const sourceSecondPosition = source.orientation === "-" ? source.start : source.end;
  const targetFirstPosition = target.orientation === "-" ? target.end : target.start;
  const targetSecondPosition = target.orientation === "-" ? target.start : target.end;
  const sourceFirst = buildEndpoint(source, sourceFirstPosition, entries);
  const sourceSecond = buildEndpoint(source, sourceSecondPosition, entries);
  const targetFirst = buildEndpoint(target, targetFirstPosition, entries);
  const targetSecond = buildEndpoint(target, targetSecondPosition, entries);
  if (!sourceFirst || !sourceSecond || !targetFirst || !targetSecond) return "";
  if (sourceFirst.entry === targetFirst.entry) return "";
  const sourceAbove = sourceFirst.entry.y <= targetFirst.entry.y;
  const sourceY = sourceAbove
    ? sourceFirst.entry.y + sourceFirst.entry.height
    : sourceFirst.entry.y;
  const targetY = sourceAbove
    ? targetFirst.entry.y
    : targetFirst.entry.y + targetFirst.entry.height;
  const tool = String(evidence.tool || "").toLowerCase();
  const association = String(evidence.association || "").toLowerCase();
  const roleLabel = String(evidence.role || "").replaceAll("_", " ");
  const identity = Number(evidence.identity);
  const identityText = Number.isFinite(identity) ? `${(identity * 100).toFixed(2)}%` : "—";
  const mapqText = evidence.mapq === null || evidence.mapq === undefined
    ? ""
    : ` · MAPQ ${Number(evidence.mapq)}`;
  const associationText = association === "supporting_precursor"
    ? " · structural precursor"
    : "";
  const title = `GRT local evidence · ${tool === "mummer" ? "MUMmer" : "minimap2"} · ${roleLabel} · identity ${identityText}${mapqText}${associationText}`;
  const points = [
    `${sourceFirst.x.toFixed(2)},${sourceY.toFixed(2)}`,
    `${sourceSecond.x.toFixed(2)},${sourceY.toFixed(2)}`,
    `${targetSecond.x.toFixed(2)},${targetY.toFixed(2)}`,
    `${targetFirst.x.toFixed(2)},${targetY.toFixed(2)}`,
  ].join(" ");
  const classNames = [
    "grt-display-evidence-band",
    tool === "mummer" ? "is-mummer" : "is-minimap2",
    association === "supporting_precursor" ? "is-supporting-precursor" : "",
  ].filter(Boolean).join(" ");
  const sourceEntryKey = String(sourceFirst.entry?.key || "");
  const targetEntryKey = String(targetFirst.entry?.key || "");
  return `<polygon class="${classNames}" points="${points}" pointer-events="visibleFill" data-grt-display-evidence="${escapeHtml(evidence.evidenceId || "")}" data-grt-display-evidence-source-entry-key="${escapeHtml(sourceEntryKey)}" data-grt-display-evidence-target-entry-key="${escapeHtml(targetEntryKey)}"><title>${escapeHtml(title)}</title></polygon>`;
}

export function buildGrtResultScene({
  plan,
  entries = [],
  maskVisibleCtgs = false,
  layers = {},
  escapeHtml = escapeFallback,
  gapLabel = "GRT gap",
} = {}) {
  const allEntries = Array.isArray(entries) ? entries : [];
  const resultPathVisible = layers?.resultPath !== false;
  const alignmentEvidenceVisible = layers?.alignmentEvidence !== false;
  const visibleEntries = allEntries.filter(
    (entry) => intervalsForEntry(plan, entry).length > 0,
  );
  const evidenceMarkup = alignmentEvidenceVisible
    ? (Array.isArray(plan?.displayEvidence) ? plan.displayEvidence : [])
      .map((evidence) => renderDisplayEvidence(evidence, allEntries, escapeHtml))
      .join("")
    : "";
  if ((!resultPathVisible || !visibleEntries.length) && !evidenceMarkup) {
    return {
      hasVisibleResult: false,
      hasVisibleJunction: false,
      overlaysByKey: new Map(),
      junctionMarkup: "",
    };
  }
  const overlaysByKey = new Map();
  if (resultPathVisible) {
    visibleEntries.forEach((entry) => {
      const maskMarkup = maskVisibleCtgs
        ? `<rect class="grt-result-mask" x="${entry.rect.x.toFixed(2)}" y="${entry.y.toFixed(2)}" width="${entry.rect.width.toFixed(2)}" height="${entry.height.toFixed(2)}" rx="3" ry="3" pointer-events="none" />`
        : "";
      const intervalsMarkup = intervalsForEntry(plan, entry)
        .map((interval) => renderIntervalOverlay(interval, entry, escapeHtml))
        .join("");
      overlaysByKey.set(entry.key, `${maskMarkup}${intervalsMarkup}`);
    });
  }
  const pathJunctionMarkup = resultPathVisible
    ? (Array.isArray(plan?.junctions) ? plan.junctions : [])
      .map((junction) => renderJunction(junction, visibleEntries, escapeHtml, gapLabel))
      .join("")
    : "";
  const junctionMarkup = `${evidenceMarkup}${pathJunctionMarkup}`;
  return {
    hasVisibleResult: true,
    hasVisibleJunction: Boolean(junctionMarkup),
    overlaysByKey,
    junctionMarkup,
  };
}
