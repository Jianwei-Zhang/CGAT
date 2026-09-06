import {
  normalizeSubviewActiveAnchors,
  normalizeSubviewManualAnchors,
} from "./subview-anchor-state.js";

function positiveInt(value) {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

function readEndpoint(node, side) {
  const prefix = `data-subview-anchor-${side}-`;
  const endpointKey = String(node.getAttribute(`${prefix}endpoint-key`) || "").trim();
  const contigId = positiveInt(node.getAttribute(`${prefix}contig-id`));
  const cutBp = positiveInt(node.getAttribute(`${prefix}cut-bp`));
  if (!endpointKey || !contigId || !cutBp) return null;
  const lengthBp = positiveInt(node.getAttribute(`${prefix}length-bp`));
  const name = String(node.getAttribute(`${prefix}name`) || "").trim();
  const sourceLabel = String(node.getAttribute(`${prefix}source-label`) || "").trim();
  const sourceRole = String(node.getAttribute(`${prefix}source-role`) || "").trim();
  const sourceKind = String(node.getAttribute(`${prefix}source-kind`) || "").trim();
  const sourceName = String(node.getAttribute(`${prefix}source-name`) || "").trim();
  const baseCutBp = positiveInt(node.getAttribute(`${prefix}base-cut-bp`));
  const sourcePosition = positiveInt(node.getAttribute(`${prefix}source-position`));
  const lane = String(node.getAttribute(`${prefix}lane`) || "").trim();
  const baseOrientation = String(node.getAttribute(`${prefix}base-orientation`) || "").trim();
  return {
    endpointKey,
    contigId,
    cutBp,
    ...(lengthBp ? { lengthBp } : {}),
    ...(name ? { name } : {}),
    ...(sourceRole ? { sourceRole } : {}),
    ...(sourceKind ? { sourceKind } : {}),
    ...(sourceName ? { sourceName } : {}),
    ...(sourceLabel ? { sourceLabel } : {}),
    ...(baseCutBp ? { baseCutBp } : {}),
    ...(sourcePosition ? { sourcePosition } : {}),
    ...(lane === "top" || lane === "bottom" ? { lane } : {}),
    ...(baseOrientation === "+" || baseOrientation === "-" ? { baseOrientation } : {}),
  };
}

export function buildSubviewAnchorObjectId(kind, identity, edge = "") {
  const prefix = kind === "manual" ? "manual" : kind === "grt" ? "grt" : "edge";
  const normalizedIdentity = String(identity || "").trim();
  if (!normalizedIdentity) return "";
  return prefix === "manual" || prefix === "grt"
    ? `${prefix}:${normalizedIdentity}`
    : `${prefix}:${normalizedIdentity}:${String(edge || "left").trim().toLowerCase()}`;
}

export function collectSubviewAnchorScene(host) {
  return Array.from(host?.querySelectorAll?.(
    "[data-subview-anchor-kind][data-subview-anchor-object-id]",
  ) || []).map((node) => {
    const rawKind = node.getAttribute("data-subview-anchor-kind");
    const kind = rawKind === "manual" ? "manual" : rawKind === "grt" ? "grt" : "evidence";
    const objectId = String(node.getAttribute("data-subview-anchor-object-id") || "").trim();
    const top = readEndpoint(node, "top");
    const bottom = readEndpoint(node, "bottom");
    const topX = Number(node.getAttribute("data-subview-anchor-top-x"));
    const bottomX = Number(node.getAttribute("data-subview-anchor-bottom-x"));
    if (!objectId) return null;
    return {
      objectId,
      kind,
      grtOriginId: String(node.getAttribute("data-subview-anchor-grt-origin-id") || "").trim(),
      descriptor: top && bottom ? { top, bottom } : null,
      topX: Number.isFinite(topX) ? topX : null,
      bottomX: Number.isFinite(bottomX) ? bottomX : null,
      node,
    };
  }).filter(Boolean);
}

export function findSubviewAnchorDescriptor(host, hitKey, edge) {
  const objectId = buildSubviewAnchorObjectId("evidence", hitKey, edge);
  return collectSubviewAnchorScene(host).find((entry) => entry.objectId === objectId)?.descriptor || null;
}

function endpointFromManual(anchor, scene, side) {
  const sceneEndpoint = scene?.descriptor?.[side];
  if (sceneEndpoint) return sceneEndpoint;
  const endpoint = side === "top" ? anchor.endpointA : anchor.endpointB;
  return endpoint || null;
}

function endpointLabel(endpoint) {
  if (!endpoint) return "";
  return [endpoint.name || `ctg ${endpoint.contigId}`, endpoint.sourceName,
    endpoint.sourceRole, endpoint.sourceKind, endpoint.sourceLabel]
    .filter(Boolean).join(" · ");
}

export function buildSubviewAnchorObjects(subview, sceneEntries = []) {
  const sceneById = new Map((Array.isArray(sceneEntries) ? sceneEntries : [])
    .map((entry) => [entry.objectId, entry]));
  const evidence = normalizeSubviewActiveAnchors(subview?.activeAnchors).map((anchor) => {
    const objectId = buildSubviewAnchorObjectId("evidence", anchor.hitKey, anchor.edge);
    const scene = sceneById.get(objectId) || null;
    const descriptor = scene?.descriptor || anchor.descriptor || null;
    return {
      objectId,
      kind: "evidence",
      hitKey: anchor.hitKey,
      edge: anchor.edge,
      descriptor,
      endpoints: descriptor ? [descriptor.top, descriptor.bottom] : [],
      active: true,
      applicability: scene ? "applied" : "evidence-unavailable",
      reason: scene ? "" : "evidenceUnavailable",
      canLocate: Boolean(scene && Number.isFinite(scene.topX) && Number.isFinite(scene.bottomX)),
      canDelete: true,
      scene,
    };
  });
  const manual = normalizeSubviewManualAnchors(subview?.manualAnchors).map((anchor) => {
    const objectId = buildSubviewAnchorObjectId("manual", anchor.manualAnchorId);
    const scene = sceneById.get(objectId) || null;
    const endpoints = [endpointFromManual(anchor, scene, "top"), endpointFromManual(anchor, scene, "bottom")]
      .filter(Boolean);
    return {
      objectId,
      kind: "manual",
      manualAnchorId: anchor.manualAnchorId,
      direction: anchor.direction,
      offsetBp: anchor.offsetBp,
      coordinateSpace: anchor.coordinateSpace,
      origin: anchor.origin || null,
      fromGrt: anchor.origin?.kind === "grt",
      descriptor: scene?.descriptor || null,
      endpoints,
      active: true,
      applicability: scene ? "applied" : "endpoint-unavailable",
      reason: scene ? "" : "endpointUnavailable",
      canLocate: Boolean(scene && Number.isFinite(scene.topX) && Number.isFinite(scene.bottomX)),
      canDelete: true,
      scene,
    };
  });
  return [...evidence, ...manual].map((object) => ({
    ...object,
    searchText: [object.kind, object.fromGrt ? "grt" : "", object.edge, object.direction, object.offsetBp,
      ...object.endpoints.flatMap((endpoint) => [endpointLabel(endpoint), endpoint?.cutBp])]
      .filter(Boolean).join(" ").toLocaleLowerCase(),
  }));
}

export function normalizeSubviewAnchorToolsUi(value, objectIds = []) {
  const available = new Set(objectIds);
  const focusedObjectId = available.has(value?.focusedObjectId) ? value.focusedObjectId : "";
  const checkedObjectIds = Array.from(new Set(Array.isArray(value?.checkedObjectIds)
    ? value.checkedObjectIds.filter((id) => available.has(id)) : []));
  return {
    scopeKey: String(value?.scopeKey || ""),
    focusedObjectId,
    checkedObjectIds,
    query: String(value?.query || ""),
  };
}

export function filterSubviewAnchorObjects(objects, query) {
  const normalized = String(query || "").trim().toLocaleLowerCase();
  return normalized ? objects.filter((object) => object.searchText.includes(normalized)) : objects;
}

export function enrichSubviewAnchorObjectDescriptors(subview, sceneEntries = []) {
  const sceneById = new Map((Array.isArray(sceneEntries) ? sceneEntries : [])
    .filter((entry) => entry?.descriptor)
    .map((entry) => [entry.objectId, entry.descriptor]));
  let changed = false;
  const activeAnchors = normalizeSubviewActiveAnchors(subview?.activeAnchors).map((anchor) => {
    if (anchor.descriptor) return anchor;
    const descriptor = sceneById.get(buildSubviewAnchorObjectId("evidence", anchor.hitKey, anchor.edge));
    if (!descriptor) return anchor;
    changed = true;
    return { ...anchor, descriptor };
  });
  return { changed, activeAnchors: normalizeSubviewActiveAnchors(activeAnchors) };
}

export function deleteSubviewAnchorObjects(subview, objectIds) {
  const targets = new Set(Array.isArray(objectIds) ? objectIds : []);
  const activeAnchors = normalizeSubviewActiveAnchors(subview?.activeAnchors).filter((anchor) =>
    !targets.has(buildSubviewAnchorObjectId("evidence", anchor.hitKey, anchor.edge)));
  const manualAnchors = normalizeSubviewManualAnchors(subview?.manualAnchors).filter((anchor) =>
    !targets.has(buildSubviewAnchorObjectId("manual", anchor.manualAnchorId)));
  const before = normalizeSubviewActiveAnchors(subview?.activeAnchors).length
    + normalizeSubviewManualAnchors(subview?.manualAnchors).length;
  const after = activeAnchors.length + manualAnchors.length;
  return { changed: before !== after, count: before - after, activeAnchors, manualAnchors };
}

export function applySubviewAnchorFocus(host, objectId) {
  for (const node of host?.querySelectorAll?.("[data-subview-anchor-object-id]") || []) {
    node.classList.toggle("is-focused", node.getAttribute("data-subview-anchor-object-id") === objectId);
  }
}

export function locateSubviewAnchorObject(host, objectId) {
  const scene = collectSubviewAnchorScene(host).find((entry) => entry.objectId === objectId);
  const scroll = host?.querySelector?.(".subview-track-scroll");
  if (!scene || !scroll || !Number.isFinite(scene.topX) || !Number.isFinite(scene.bottomX)) return false;
  const viewBoxMinX = Number(scroll.dataset?.subviewViewboxMinX || 0);
  const center = ((scene.topX + scene.bottomX) / 2) - (Number.isFinite(viewBoxMinX) ? viewBoxMinX : 0);
  const left = Math.max(0, center - Number(scroll.clientWidth || 0) / 2);
  if (typeof scroll.scrollTo === "function") scroll.scrollTo({ left, behavior: "smooth" });
  else scroll.scrollLeft = left;
  return true;
}
