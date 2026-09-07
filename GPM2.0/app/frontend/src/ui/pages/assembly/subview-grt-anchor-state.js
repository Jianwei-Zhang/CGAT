import {
  buildGrtResultPlan,
  projectGrtSourcePositionToCtg,
} from "./grt-result-state.js";
import { normalizeSubviewManualAnchors } from "./subview-anchor-state.js";

function positiveInt(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
}

function orientation(value) {
  return String(value || "").trim() === "-" ? "-" : "+";
}

function hashText(value) {
  let left = 0x811c9dc5;
  let right = 0x9e3779b9;
  for (const character of String(value || "")) {
    const code = character.codePointAt(0);
    left = Math.imul(left ^ code, 0x01000193) >>> 0;
    right = Math.imul(right ^ code, 0x85ebca6b) >>> 0;
  }
  return `${left.toString(36)}${right.toString(36)}`;
}

function endpointSource(interval, sourcePosition) {
  return {
    assemblyCtgId: positiveInt(interval?.assemblyCtgId),
    sourcePosition: positiveInt(sourcePosition),
    segmentId: String(interval?.segmentId || "").trim(),
    pathOrder: Number(interval?.pathOrder),
    datasetName: String(interval?.datasetName || "").trim(),
    contigName: String(interval?.contigName || "").trim(),
    assemblySourceStart: positiveInt(interval?.assemblySourceStart),
    assemblySourceEnd: positiveInt(interval?.assemblySourceEnd),
    sourceStart: positiveInt(interval?.sourceStart),
    sourceEnd: positiveInt(interval?.sourceEnd),
    orientation: orientation(interval?.orientation),
  };
}

function canonicalPlan(plan) {
  return (Array.isArray(plan?.junctions) ? plan.junctions : []).map((junction) => ({
    kind: junction.kind,
    gapSizeBp: Number(junction.gapSizeBp || 0),
    left: endpointSource(junction.left, junction.left?.exitSourcePosition),
    right: endpointSource(junction.right, junction.right?.entrySourcePosition),
  }));
}

export function buildSubviewGrtBaselineKey(chrName, plan) {
  return hashText(JSON.stringify({ chrName: String(chrName || "").trim(), junctions: canonicalPlan(plan) }));
}

export function buildSubviewGrtAnchorOriginId(chrName, baselineKey, junction) {
  const source = [
    String(chrName || "").trim(),
    String(baselineKey || "").trim(),
    junction?.kind,
    junction?.left?.segmentId,
    junction?.left?.pathOrder,
    junction?.right?.segmentId,
    junction?.right?.pathOrder,
  ].join("|");
  return `${encodeURIComponent(String(chrName || "").trim())}:${baselineKey}:${hashText(source)}`;
}

export function buildSubviewGrtAnchorObjectId(originId) {
  const normalized = String(originId || "").trim();
  return normalized ? `grt:${normalized}` : "";
}

function currentEntryForInterval(interval, entries) {
  const assemblyCtgId = positiveInt(interval?.assemblyCtgId);
  if (!assemblyCtgId) return null;
  const matches = (Array.isArray(entries) ? entries : []).filter((entry) =>
    positiveInt(entry?.ctg?.assemblyCtgId ?? entry?.assemblyCtgId) === assemblyCtgId
    && String(entry?.sourceRole || "") !== "ref");
  return matches.length === 1 ? matches[0] : null;
}

function projectEndpoint(interval, sourcePosition, entries) {
  const entry = currentEntryForInterval(interval, entries);
  if (!entry) return null;
  const lengthBp = positiveInt(entry?.ctg?.lengthBp ?? entry?.ctg?.totalLength ?? entry?.lengthBp);
  const endpointKey = String(entry?.endpointKey || "").trim();
  const lane = String(entry?.lane || "").trim() === "bottom" ? "bottom" : "top";
  const baseOrientation = orientation(entry?.baseOrientation ?? entry?.ctg?.orient);
  const baseCutBp = projectGrtSourcePositionToCtg(sourcePosition, interval, baseOrientation);
  const locallyFlipped = entry?.locallyFlipped === true;
  const displayCutBp = baseCutBp && lengthBp
    ? (locallyFlipped ? lengthBp - baseCutBp + 1 : baseCutBp)
    : null;
  const x = Number(entry?.rect?.x);
  const width = Number(entry?.rect?.width);
  const y = Number(entry?.y);
  const height = Number(entry?.height);
  if (
    !lengthBp || !endpointKey || !baseCutBp || !displayCutBp
    || displayCutBp > lengthBp || !Number.isFinite(x) || !Number.isFinite(width)
    || !Number.isFinite(y) || !Number.isFinite(height)
  ) return null;
  return {
    lane,
    x: x + ((displayCutBp - 1) / lengthBp) * width,
    y: lane === "top" ? y + height : y,
    endpoint: {
      endpointKey,
      contigId: positiveInt(entry?.ctg?.assemblyCtgId ?? entry?.assemblyCtgId),
      cutBp: displayCutBp,
      baseCutBp,
      lengthBp,
      baseOrientation,
      locallyFlipped,
      name: String(entry?.name || entry?.ctg?.name || "").trim(),
      sourceRole: String(entry?.sourceRole || "").trim(),
      sourceKind: String(entry?.sourceKind || "").trim(),
      sourceName: String(entry?.sourceName || entry?.datasetName || "").trim(),
      sourcePosition: positiveInt(sourcePosition),
      lane,
    },
  };
}

function attr(value, escapeAttr) {
  return escapeAttr(String(value ?? ""));
}

function endpointAttrs(side, projected, escapeAttr) {
  const endpoint = projected.endpoint;
  return `data-subview-anchor-${side}-endpoint-key="${attr(endpoint.endpointKey, escapeAttr)}"
    data-subview-anchor-${side}-contig-id="${endpoint.contigId}"
    data-subview-anchor-${side}-cut-bp="${endpoint.cutBp}"
    data-subview-anchor-${side}-base-cut-bp="${endpoint.baseCutBp}"
    data-subview-anchor-${side}-length-bp="${endpoint.lengthBp}"
    data-subview-anchor-${side}-base-orientation="${endpoint.baseOrientation}"
    data-subview-anchor-${side}-lane="${endpoint.lane}"
    data-subview-anchor-${side}-source-position="${endpoint.sourcePosition}"
    data-subview-anchor-${side}-name="${attr(endpoint.name, escapeAttr)}"
    data-subview-anchor-${side}-source-role="${attr(endpoint.sourceRole, escapeAttr)}"
    data-subview-anchor-${side}-source-kind="${attr(endpoint.sourceKind, escapeAttr)}"
    data-subview-anchor-${side}-source-name="${attr(endpoint.sourceName, escapeAttr)}"`;
}

export function buildSubviewGrtAnchorScene({
  chrName,
  plan,
  entries = [],
  escapeAttr = (value) => String(value ?? ""),
} = {}) {
  const baselineKey = buildSubviewGrtBaselineKey(chrName, plan);
  const markup = (Array.isArray(plan?.junctions) ? plan.junctions : []).map((junction) => {
    const left = projectEndpoint(junction.left, junction.left?.exitSourcePosition, entries);
    const right = projectEndpoint(junction.right, junction.right?.entrySourcePosition, entries);
    if (!left || !right) return "";
    const ordered = left.lane === "bottom" && right.lane === "top" ? [right, left] : [left, right];
    const [top, bottom] = ordered;
    const originId = buildSubviewGrtAnchorOriginId(chrName, baselineKey, junction);
    const objectId = buildSubviewGrtAnchorObjectId(originId);
    return `<line class="subview-anchor-line subview-grt-anchor-reference" x1="${top.x.toFixed(2)}" y1="${top.y.toFixed(2)}"
      x2="${bottom.x.toFixed(2)}" y2="${bottom.y.toFixed(2)}" stroke="transparent" stroke-width="4"
      pointer-events="none" data-subview-anchor-kind="grt" data-subview-anchor-object-id="${attr(objectId, escapeAttr)}"
      data-subview-anchor-grt-origin-id="${attr(originId, escapeAttr)}"
      data-subview-anchor-top-x="${top.x.toFixed(4)}" data-subview-anchor-bottom-x="${bottom.x.toFixed(4)}"
      ${endpointAttrs("top", top, escapeAttr)} ${endpointAttrs("bottom", bottom, escapeAttr)} />`;
  }).join("");
  return { baselineKey, markup };
}

function rawEndpoint(source) {
  return {
    contigId: source.assemblyCtgId,
    name: source.contigName || `ctg ${source.assemblyCtgId || "?"}`,
    sourceName: source.datasetName,
    sourceRole: "grt",
    sourcePosition: source.sourcePosition,
  };
}

export function buildSubviewGrtAnchorReferences(assembly, sceneEntries = []) {
  const chrName = String(assembly?.selectedChrName || "").trim();
  const baselineEntry = assembly?.grtProjectView?.baselineFinalPathByChr?.[chrName] || null;
  const plan = buildGrtResultPlan(baselineEntry);
  const baselineKey = buildSubviewGrtBaselineKey(chrName, plan);
  const sceneById = new Map((Array.isArray(sceneEntries) ? sceneEntries : [])
    .filter((scene) => scene?.kind === "grt")
    .map((scene) => [scene.objectId, scene]));
  return (Array.isArray(plan?.junctions) ? plan.junctions : []).map((junction) => {
    const endpointSources = [
      endpointSource(junction.left, junction.left?.exitSourcePosition),
      endpointSource(junction.right, junction.right?.entrySourcePosition),
    ];
    const originId = buildSubviewGrtAnchorOriginId(chrName, baselineKey, junction);
    const objectId = buildSubviewGrtAnchorObjectId(originId);
    const scene = sceneById.get(objectId) || null;
    const descriptor = scene?.descriptor || null;
    const sameLane = Boolean(descriptor && descriptor.top?.lane === descriptor.bottom?.lane);
    const canLocate = Boolean(scene && Number.isFinite(scene.topX) && Number.isFinite(scene.bottomX));
    const canCopy = Boolean(
      descriptor && !sameLane
      && positiveInt(descriptor.top?.baseCutBp) && positiveInt(descriptor.bottom?.baseCutBp),
    );
    const endpoints = descriptor
      ? [descriptor.top, descriptor.bottom]
      : endpointSources.map(rawEndpoint);
    const origin = {
      kind: "grt",
      originId,
      baselineKey,
      chrName,
      connectionKind: junction.kind === "gap" ? "gap" : "link",
      endpointSources,
    };
    return {
      objectId,
      kind: "grt",
      originId,
      origin,
      connectionKind: origin.connectionKind,
      gapSizeBp: junction.kind === "gap" ? Number(junction.gapSizeBp || 0) : 0,
      endpoints,
      endpointSources,
      scene,
      readOnly: true,
      canDelete: false,
      canLocate,
      canCopy,
      applicability: !descriptor ? "endpoint-unavailable" : sameLane ? "same-lane" : "applied",
      reason: !descriptor ? "grtEndpointUnavailable" : sameLane ? "grtSameLane" : "",
      searchText: ["grt", origin.connectionKind, junction.gapSizeBp,
        ...endpointSources.flatMap((endpoint) => [
          endpoint.datasetName, endpoint.contigName, endpoint.sourcePosition,
        ])].filter(Boolean).join(" ").toLocaleLowerCase(),
    };
  }).filter((reference) => Boolean(reference.scene));
}

export function findSubviewGrtAnchorReference(assembly, sceneEntries, originId) {
  const normalized = String(originId || "").trim();
  return buildSubviewGrtAnchorReferences(assembly, sceneEntries)
    .find((reference) => reference.originId === normalized) || null;
}

export function findSubviewManualAnchorByGrtOrigin(manualAnchors, originId) {
  const normalized = String(originId || "").trim();
  return normalizeSubviewManualAnchors(manualAnchors)
    .find((anchor) => anchor.origin?.kind === "grt" && anchor.origin.originId === normalized) || null;
}

export function createSubviewManualAnchorFromGrt(reference) {
  if (!reference?.canCopy || !reference?.scene?.descriptor) {
    return { ok: false, reason: reference?.reason || "grtEndpointUnavailable", anchor: null };
  }
  const toStoredEndpoint = (endpoint) => ({
    endpointKey: endpoint.endpointKey,
    contigId: endpoint.contigId,
    cutBp: endpoint.baseCutBp,
    lengthBp: endpoint.lengthBp,
    baseOrientation: endpoint.baseOrientation,
    name: endpoint.name,
    sourceRole: endpoint.sourceRole,
    sourceKind: endpoint.sourceKind,
    sourceName: endpoint.sourceName,
  });
  const anchor = normalizeSubviewManualAnchors([{
    manualAnchorId: `grt-copy:${reference.originId}`,
    coordinateSpace: "assembly",
    origin: reference.origin,
    sourceHitKey: "",
    sourceEdge: "",
    direction: "",
    offsetBp: null,
    endpointA: toStoredEndpoint(reference.scene.descriptor.top),
    endpointB: toStoredEndpoint(reference.scene.descriptor.bottom),
  }])[0] || null;
  return anchor
    ? { ok: true, reason: "", anchor }
    : { ok: false, reason: "grtEndpointUnavailable", anchor: null };
}
