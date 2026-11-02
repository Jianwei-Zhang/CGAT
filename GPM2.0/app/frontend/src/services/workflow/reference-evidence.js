// Lossless immutable Ref evidence. Metadata and packed bytes are cloneable;
// expanded hit objects are a derived cache, never persisted project state.
const materialized = new WeakMap();
const decodedBytes = new WeakMap();
const V1 = "reference-hits-v1", V2 = "reference-hits-v2";

export function referenceHitsUnloaded(member) {
  return member?.referenceEvidence?.encoding === "reference-hits-unloaded";
}
export function hasDeferredReferenceHits(member) {
  return referenceHitsUnloaded(member) || member?.referenceEvidence?.encoding === V1 || member?.referenceEvidence?.encoding === V2;
}

export function deferReferenceMember(member, encoding) {
  const { hitGroups, hitRows, hitData, hitCount, ...metadata } = member;
  if (encoding !== V1 && encoding !== V2) throw Error("Unsupported reference evidence encoding");
  return { ...metadata, referenceEvidence: { encoding, hitGroups,
    ...(encoding === V1 ? { hitRows } : { hitData, hitCount }) } };
}

function invalid() { throw Error("Invalid or unsafe reference evidence payload"); }
function integer(value) { if (!Number.isSafeInteger(value)) invalid(); return value; }
function groupAt(groups, index, checked) {
  if (!Number.isSafeInteger(index) || index < 0 || index >= groups.length) invalid();
  if (checked[index]) return checked[index];
  const group = groups[index];
  if (!Array.isArray(group) || group.length !== 6) invalid();
  for (const field of [0, 1, 2, 5]) integer(group[field]);
  if (group[4] !== null && !Number.isFinite(group[4])) invalid();
  checked[index] = group;
  return group;
}
function hitObject(group, row) {
  const [hitId, datasetId, sourceSeqId, strand, identityPct, mapq] = group;
  const [queryStart, queryEnd, refStart, refEnd, matchLength, blockLength, ctgStart, ctgEnd] = row;
  return { hitId, datasetId, sourceSeqId, strand, queryStart, queryEnd,
    refStart, refEnd, matchLength, blockLength, identityPct, mapq, ctgStart, ctgEnd };
}

// Most values fit the fast numeric path. BigInt is used only for extreme but
// still lossless deltas; reject coordinates that JS cannot represent exactly.
function unsigned(cursor) {
  let value = 0, factor = 1;
  const start = cursor.offset;
  for (let n = 0; n < 10; n++, factor *= 128) {
    if (cursor.offset >= cursor.bytes.length) invalid();
    const byte = cursor.bytes[cursor.offset++], part = (byte & 127) * factor;
    if (part > Number.MAX_SAFE_INTEGER - value) {
      let big = 0n;
      for (let i = start; i < cursor.offset; i++) big |= BigInt(cursor.bytes[i] & 127) << BigInt(7 * (i - start));
      let last = byte;
      while (last & 128) {
        if (cursor.offset - start >= 10 || cursor.offset >= cursor.bytes.length) invalid();
        last = cursor.bytes[cursor.offset++];
        big |= BigInt(last & 127) << BigInt(7 * (cursor.offset - start - 1));
      }
      return big;
    }
    value += part;
    if (!(byte & 128)) return value;
  }
  invalid();
}
function signed(value) {
  return typeof value === "bigint" ? ((value & 1n) ? -(value / 2n) - 1n : value / 2n)
    : value % 2 ? -(value + 1) / 2 : value / 2;
}

export function* iterateReferenceHitEntries(member, {
  datasetId = member?.referenceDatasetId ?? null, acceptRow = null,
} = {}) {
  if (referenceHitsUnloaded(member)) throw Error("Reference evidence is not loaded");
  let hitIndex = 0;
  const evidence = member?.referenceEvidence;
  if (!hasDeferredReferenceHits(member)) {
    for (const hit of Array.isArray(member?.hits) ? member.hits : []) if (datasetId == null || Number(hit.datasetId) === datasetId) {
      yield { index: hitIndex++, hit };
    }
    return;
  }
  const groups = evidence.hitGroups, checked = [];
  if (!Array.isArray(groups)) invalid();
  if (evidence.encoding === V1) {
    if (!Array.isArray(evidence.hitRows)) invalid();
    for (const [index, ...row] of evidence.hitRows) {
      const group = groupAt(groups, index, checked);
      if (row.length !== 8 || row.some(value => !Number.isSafeInteger(value))) invalid();
      if (datasetId == null || group[1] === datasetId) {
        const index = hitIndex++;
        if (!acceptRow || acceptRow(group, row, index)) yield { index, hit: hitObject(group, row) };
      }
    }
    return;
  }
  if (typeof evidence.hitData !== "string" || !Number.isSafeInteger(evidence.hitCount) || evidence.hitCount < 0) invalid();
  // Decode once per explicit reader, never during Main rendering/metadata work.
  let bytes = decodedBytes.get(evidence);
  if (!bytes) {
    const binary = atob(evidence.hitData);
    bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    decodedBytes.set(evidence, bytes);
  }
  if (evidence.hitCount > bytes.length / 9) invalid();
  const cursor = { bytes, offset: 0 }, previous = groups.map(() => Array(8).fill(0));
  let count = 0;
  while (cursor.offset < bytes.length) {
    if (++count > evidence.hitCount) invalid();
    const index = unsigned(cursor), group = groupAt(groups, index, checked), row = previous[index];
    if (datasetId != null && group[1] !== datasetId) {
      // Excluded groups never become selected later in this view. Their row
      // boundaries must still validate, but their numeric state is irrelevant.
      for (let column = 0; column < 8; column++) {
        let length = 0, byte;
        do {
          if (++length > 10 || cursor.offset >= bytes.length) invalid();
          byte = bytes[cursor.offset++];
        } while (byte & 128);
      }
      continue;
    }
    for (let column = 0; column < 8; column++) {
      const delta = signed(unsigned(cursor));
      row[column] = integer(typeof delta === "bigint" ? Number(BigInt(row[column]) + delta) : row[column] + delta);
    }
    if (datasetId == null || group[1] === datasetId) {
      const index = hitIndex++;
      if (!acceptRow || acceptRow(group, row, index)) yield { index, hit: hitObject(group, row) };
    }
  }
  if (count !== evidence.hitCount) invalid();
}

export function* iterateReferenceHits(member, options) {
  for (const entry of iterateReferenceHitEntries(member, options)) yield entry.hit;
}

export function readReferenceHits(member, { datasetId = member?.referenceDatasetId ?? null } = {}) {
  if (referenceHitsUnloaded(member)) throw Error("Reference evidence is not loaded");
  if (!hasDeferredReferenceHits(member)) {
    const hits = Array.isArray(member?.hits) ? member.hits : [];
    return datasetId == null ? hits : hits.filter(hit => Number(hit?.datasetId) === datasetId);
  }
  const evidence = member.referenceEvidence;
  let cache = materialized.get(evidence);
  if (!cache) { cache = new Map(); materialized.set(evidence, cache); }
  if (!cache.has(datasetId)) {
    cache.set(datasetId, Object.freeze(Array.from(iterateReferenceHits(member, { datasetId }), Object.freeze)));
  }
  return cache.get(datasetId);
}
