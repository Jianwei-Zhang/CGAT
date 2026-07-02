function normalizeEdge(value) {
  return String(value || "").trim().toLowerCase() === "right" ? "right" : "left";
}

function normalizePositiveInt(value) {
  const numeric = Number(value);
  if (!Number.isInteger(numeric) || numeric <= 0) {
    return null;
  }
  return numeric;
}

function normalizeHitKey(value) {
  return String(value || "").trim();
}

function normalizeIdPart(value) {
  return String(value ?? "").trim().replaceAll("|", "/").replaceAll(":", "-");
}

function normalizeDirection(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "right" || normalized === "r" || normalized === "右") {
    return "right";
  }
  if (normalized === "left" || normalized === "l" || normalized === "左") {
    return "left";
  }
  return "";
}

function normalizeEndpoint(endpoint) {
  const endpointKey = String(endpoint?.endpointKey || endpoint?.key || "").trim();
  const contigId = normalizePositiveInt(endpoint?.contigId);
  const cutBp = normalizePositiveInt(endpoint?.cutBp);
  const lengthBp = normalizePositiveInt(endpoint?.lengthBp);
  if (!endpointKey || !contigId || !cutBp) {
    return null;
  }
  return {
    endpointKey,
    contigId,
    cutBp,
    ...(lengthBp ? { lengthBp } : {}),
  };
}

function sortEndpoints(left, right) {
  return String(left?.endpointKey || "").localeCompare(String(right?.endpointKey || ""));
}

function normalizeManualAnchorId(value, endpointA, endpointB) {
  const existing = String(value || "").trim();
  if (existing) {
    return existing;
  }
  return [
    "manual",
    endpointA?.endpointKey,
    endpointA?.cutBp,
    endpointB?.endpointKey,
    endpointB?.cutBp,
  ].map(normalizeIdPart).join(":");
}

export function normalizeSubviewActiveAnchors(values) {
  const normalized = new Map();
  (Array.isArray(values) ? values : []).forEach((entry) => {
    const hitKey = normalizeHitKey(entry?.hitKey);
    if (!hitKey) {
      return;
    }
    const edge = normalizeEdge(entry?.edge);
    normalized.set(`${hitKey}:${edge}`, { hitKey, edge });
  });
  return Array.from(normalized.values()).sort((left, right) =>
    `${left.hitKey}:${left.edge}`.localeCompare(`${right.hitKey}:${right.edge}`),
  );
}

export function buildSubviewAnchorEndpointKey(value) {
  const role = normalizeIdPart(value?.role || value?.trackRole || "");
  const contigId = normalizePositiveInt(value?.contigId ?? value?.assemblyCtgId);
  if (!role || !contigId) {
    return "";
  }
  const parts = [
    `role:${role}`,
    `ctg:${contigId}`,
  ];
  const datasetId = normalizePositiveInt(value?.datasetId);
  if (datasetId) {
    parts.push(`ds:${datasetId}`);
  }
  const source = normalizeIdPart(value?.source || value?.sourceKind || "");
  if (source) {
    parts.push(`src:${source}`);
  }
  const phasedTrackId = normalizePositiveInt(value?.phasedTrackId);
  const phasedTrackItemId = normalizePositiveInt(value?.phasedTrackItemId);
  const phasedHaplotypeKey = normalizeIdPart(value?.phasedHaplotypeKey || value?.haplotypeKey || "");
  if (phasedTrackId) {
    parts.push(`phasedTrack:${phasedTrackId}`);
  }
  if (phasedTrackItemId) {
    parts.push(`phasedItem:${phasedTrackItemId}`);
  }
  if (phasedHaplotypeKey) {
    parts.push(`hap:${phasedHaplotypeKey}`);
  }
  if (value?.isMirror === true) {
    parts.push("mirror:1");
  }
  return parts.join(":");
}

function buildSubviewTrackAnchorKey(track) {
  const role = normalizeIdPart(track?.role || "");
  if (!role) {
    return "";
  }
  const parts = [`role:${role}`];
  const source = normalizeIdPart(track?.source || "");
  if (source) {
    parts.push(`src:${source}`);
  }
  const datasetId = normalizePositiveInt(track?.datasetId);
  if (datasetId) {
    parts.push(`ds:${datasetId}`);
  }
  const phasedTrackId = normalizePositiveInt(track?.phasedTrackId);
  if (phasedTrackId) {
    parts.push(`phasedTrack:${phasedTrackId}`);
  }
  const haplotypeKey = normalizeIdPart(track?.haplotypeKey || track?.phasedHaplotypeKey || "");
  if (haplotypeKey) {
    parts.push(`hap:${haplotypeKey}`);
  }
  if (track?.isMirror === true) {
    parts.push("mirror:1");
  }
  return parts.join(":");
}

export function buildSubviewAnchorStateKey(summary, chrName = "") {
  const mode = String(summary?.mode || "").trim();
  const chrPart = `chr:${normalizeIdPart(chrName)}`;
  if (mode === "2-contig") {
    const topKey = buildSubviewAnchorEndpointKey({
      ...(summary?.top || {}),
      role: summary?.top?.role,
      contigId: summary?.top?.contigId,
    });
    const bottomKey = buildSubviewAnchorEndpointKey({
      ...(summary?.bottom || {}),
      role: summary?.bottom?.role,
      contigId: summary?.bottom?.contigId,
    });
    if (!topKey || !bottomKey) {
      return "";
    }
    return ["2-contig", chrPart, ...[topKey, bottomKey].sort()].join("|");
  }
  if (mode === "track-pair") {
    const topKey = buildSubviewTrackAnchorKey(summary?.topTrack);
    const bottomKey = buildSubviewTrackAnchorKey(summary?.bottomTrack);
    if (!topKey || !bottomKey) {
      return "";
    }
    return ["track-pair", chrPart, ...[topKey, bottomKey].sort()].join("|");
  }
  return "";
}

export function normalizeSubviewManualAnchors(values) {
  const normalized = new Map();
  (Array.isArray(values) ? values : []).forEach((entry) => {
    const endpointA = normalizeEndpoint(entry?.endpointA || entry?.top || entry?.left);
    const endpointB = normalizeEndpoint(entry?.endpointB || entry?.bottom || entry?.right);
    if (!endpointA || !endpointB || endpointA.endpointKey === endpointB.endpointKey) {
      return;
    }
    const [firstEndpoint, secondEndpoint] = [endpointA, endpointB].sort(sortEndpoints);
    const manualAnchorId = normalizeManualAnchorId(
      entry?.manualAnchorId,
      firstEndpoint,
      secondEndpoint,
    );
    normalized.set(manualAnchorId, {
      manualAnchorId,
      sourceHitKey: normalizeHitKey(entry?.sourceHitKey),
      sourceEdge: normalizeEdge(entry?.sourceEdge),
      direction: normalizeDirection(entry?.direction),
      offsetBp: normalizePositiveInt(entry?.offsetBp) || null,
      endpointA: firstEndpoint,
      endpointB: secondEndpoint,
    });
  });
  return Array.from(normalized.values()).sort((left, right) =>
    String(left.manualAnchorId).localeCompare(String(right.manualAnchorId)),
  );
}

export function normalizeSubviewAnchorState(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    activeAnchors: normalizeSubviewActiveAnchors(source.activeAnchors),
    manualAnchors: normalizeSubviewManualAnchors(source.manualAnchors),
  };
}

export function normalizeSubviewAnchorStateByKey(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return Object.fromEntries(
    Object.entries(source)
      .map(([key, state]) => [String(key || "").trim(), normalizeSubviewAnchorState(state)])
      .filter(([key, state]) => key && (state.activeAnchors.length || state.manualAnchors.length)),
  );
}

export function resolveSubviewAnchorStateForSummary(anchorStateByKey, summary, chrName = "") {
  const key = buildSubviewAnchorStateKey(summary, chrName);
  if (!key) {
    return normalizeSubviewAnchorState({});
  }
  return normalizeSubviewAnchorState(
    normalizeSubviewAnchorStateByKey(anchorStateByKey)[key],
  );
}

export function setSubviewAnchorStateForSummary(anchorStateByKey, summary, chrName, anchorState) {
  const key = buildSubviewAnchorStateKey(summary, chrName);
  const current = normalizeSubviewAnchorStateByKey(anchorStateByKey);
  if (!key) {
    return current;
  }
  const normalized = normalizeSubviewAnchorState(anchorState);
  if (!normalized.activeAnchors.length && !normalized.manualAnchors.length) {
    const { [key]: _removed, ...rest } = current;
    return rest;
  }
  return {
    ...current,
    [key]: normalized,
  };
}

export function toggleSubviewAnchorEdge(activeAnchors, { hitKey, edge }) {
  const normalizedHitKey = normalizeHitKey(hitKey);
  if (!normalizedHitKey) {
    return normalizeSubviewActiveAnchors(activeAnchors);
  }
  const normalizedEdge = normalizeEdge(edge);
  const normalized = normalizeSubviewActiveAnchors(activeAnchors);
  const existingIndex = normalized.findIndex(
    (entry) => entry.hitKey === normalizedHitKey && entry.edge === normalizedEdge,
  );
  if (existingIndex >= 0) {
    normalized.splice(existingIndex, 1);
    return normalized;
  }
  normalized.push({
    hitKey: normalizedHitKey,
    edge: normalizedEdge,
  });
  return normalizeSubviewActiveAnchors(normalized);
}

export function createOffsetSubviewManualAnchor(sourceEdge, { direction, offsetBp }) {
  const normalizedDirection = normalizeDirection(direction);
  const normalizedOffsetBp = normalizePositiveInt(offsetBp);
  if (!normalizedDirection || !normalizedOffsetBp) {
    return {
      ok: false,
      reason: "invalid-offset",
      anchor: null,
    };
  }
  const topEndpointKey = String(sourceEdge?.topEndpointKey || "").trim();
  const bottomEndpointKey = String(sourceEdge?.bottomEndpointKey || "").trim();
  const topContigId = normalizePositiveInt(sourceEdge?.topContigId);
  const bottomContigId = normalizePositiveInt(sourceEdge?.bottomContigId);
  const topCutBp = normalizePositiveInt(sourceEdge?.topCutBp);
  const bottomCutBp = normalizePositiveInt(sourceEdge?.bottomCutBp);
  const topLengthBp = normalizePositiveInt(sourceEdge?.topLengthBp);
  const bottomLengthBp = normalizePositiveInt(sourceEdge?.bottomLengthBp);
  if (!topEndpointKey || !bottomEndpointKey || !topContigId || !bottomContigId || !topCutBp || !bottomCutBp) {
    return {
      ok: false,
      reason: "invalid-anchor",
      anchor: null,
    };
  }
  const signedOffset = normalizedDirection === "right" ? normalizedOffsetBp : -normalizedOffsetBp;
  const nextTopCutBp = topCutBp + signedOffset;
  const nextBottomCutBp = bottomCutBp + signedOffset;
  if (
    nextTopCutBp <= 0
    || nextBottomCutBp <= 0
    || (topLengthBp && nextTopCutBp > topLengthBp)
    || (bottomLengthBp && nextBottomCutBp > bottomLengthBp)
  ) {
    return {
      ok: false,
      reason: "out-of-range",
      anchor: null,
    };
  }
  const endpointA = {
    endpointKey: topEndpointKey,
    contigId: topContigId,
    cutBp: nextTopCutBp,
    ...(topLengthBp ? { lengthBp: topLengthBp } : {}),
  };
  const endpointB = {
    endpointKey: bottomEndpointKey,
    contigId: bottomContigId,
    cutBp: nextBottomCutBp,
    ...(bottomLengthBp ? { lengthBp: bottomLengthBp } : {}),
  };
  const [firstEndpoint, secondEndpoint] = [endpointA, endpointB].sort(sortEndpoints);
  const manualAnchorId = normalizeManualAnchorId("", firstEndpoint, secondEndpoint);
  return {
    ok: true,
    reason: "",
    anchor: {
      manualAnchorId,
      sourceHitKey: normalizeHitKey(sourceEdge?.hitKey),
      sourceEdge: normalizeEdge(sourceEdge?.edge),
      direction: normalizedDirection,
      offsetBp: normalizedOffsetBp,
      endpointA: firstEndpoint,
      endpointB: secondEndpoint,
    },
  };
}

export function removeSubviewManualAnchor(manualAnchors, manualAnchorId) {
  const targetId = String(manualAnchorId || "").trim();
  if (!targetId) {
    return normalizeSubviewManualAnchors(manualAnchors);
  }
  return normalizeSubviewManualAnchors(manualAnchors)
    .filter((anchor) => anchor.manualAnchorId !== targetId);
}

export function upsertSubviewManualAnchor(manualAnchors, manualAnchor) {
  return normalizeSubviewManualAnchors([
    ...normalizeSubviewManualAnchors(manualAnchors),
    manualAnchor,
  ]);
}

export function deriveSubviewHitEdgeAnchors({ hitKey, top, bottom }) {
  const normalizedHitKey = normalizeHitKey(hitKey);
  if (!normalizedHitKey) {
    return [];
  }
  const topContigId = normalizePositiveInt(top?.contigId);
  const bottomContigId = normalizePositiveInt(bottom?.contigId);
  if (!topContigId || !bottomContigId) {
    return [];
  }
  return [
    {
      hitKey: normalizedHitKey,
      edge: "left",
      topContigId,
      topCutBp: normalizePositiveInt(top?.start),
      bottomContigId,
      bottomCutBp: normalizePositiveInt(bottom?.start),
    },
    {
      hitKey: normalizedHitKey,
      edge: "right",
      topContigId,
      topCutBp: normalizePositiveInt(top?.end),
      bottomContigId,
      bottomCutBp: normalizePositiveInt(bottom?.end),
    },
  ];
}

export function deriveSubviewContigFragments({ contig, anchorCuts }) {
  const assemblyCtgId = normalizePositiveInt(contig?.assemblyCtgId);
  const role = String(contig?.role || "").trim();
  const lengthBp = normalizePositiveInt(contig?.lengthBp);
  if (!assemblyCtgId || !role || !lengthBp) {
    return [];
  }
  const sortedCuts = [...new Set(
    (Array.isArray(anchorCuts) ? anchorCuts : [])
      .map((value) => normalizePositiveInt(value))
      .filter((value) => value !== null && value <= lengthBp),
  )].sort((left, right) => left - right);
  const boundaries = [1, ...sortedCuts, lengthBp + 1];
  return boundaries.slice(0, -1).flatMap((start, index) => {
    const end = boundaries[index + 1] - 1;
    if (end < start) {
      return [];
    }
    return [{
      fragmentKey: `${assemblyCtgId}:${start}-${end}`,
      assemblyCtgId,
      role,
      start,
      end,
    }];
  });
}
