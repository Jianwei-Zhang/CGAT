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
