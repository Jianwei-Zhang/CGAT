function normalizeString(value) {
  return String(value ?? "").trim();
}

function firstDefined(source, ...keys) {
  for (const key of keys) {
    if (source?.[key] !== undefined && source?.[key] !== null) {
      return source[key];
    }
  }
  return undefined;
}

function normalizeStringList(value) {
  if (typeof value === "string") {
    const text = value.trim();
    if (!text) {
      return [];
    }
    try {
      return normalizeStringList(JSON.parse(text));
    } catch {
      return [text];
    }
  }
  const seen = new Set();
  return (Array.isArray(value) ? value : [])
    .map((item) => normalizeString(item))
    .filter((item) => {
      if (!item || seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
}

function normalizePositiveInteger(value) {
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

export function normalizeGrtRecipe(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    workflow: normalizeString(source.workflow),
    schemaVersion: normalizeString(firstDefined(source, "schemaVersion", "schema_version")),
    finalPathSchemaVersion: normalizeString(
      firstDefined(source, "finalPathSchemaVersion", "final_path_schema_version"),
    ),
    recipeId: normalizeString(firstDefined(source, "recipeId", "recipe_id")),
    primaryDataset: normalizeString(firstDefined(source, "primaryDataset", "primary_dataset")),
    supportDatasets: normalizeStringList(
      firstDefined(source, "supportDatasets", "support_datasets"),
    ),
    readsQcEnabled: Boolean(firstDefined(source, "readsQcEnabled", "reads_qc_enabled")),
    donorSetId: normalizeString(firstDefined(source, "donorSetId", "donor_set_id")),
    telDonorSetId: normalizeString(firstDefined(source, "telDonorSetId", "tel_donor_set_id")),
    q0Relpath: normalizeString(firstDefined(source, "q0Relpath", "q0_relpath")),
    finalQRelpath: normalizeString(firstDefined(source, "finalQRelpath", "final_q_relpath")),
    q0ArtifactSha256: normalizeString(
      firstDefined(source, "q0ArtifactSha256", "q0_artifact_sha256"),
    ),
    q4ArtifactSha256: normalizeString(
      firstDefined(source, "q4ArtifactSha256", "q4_artifact_sha256"),
    ),
  };
}

function normalizeSourceCard(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    ...source,
    sourceCardKey: normalizeString(firstDefined(source, "sourceCardKey", "source_card_key")),
    datasetName: normalizeString(firstDefined(source, "datasetName", "dataset_name")),
    contigName: normalizeString(firstDefined(source, "contigName", "contig_name")),
    originalAssignment: normalizeString(
      firstDefined(source, "originalAssignment", "original_assignment"),
    ),
    targetChr: normalizeString(firstDefined(source, "targetChr", "target_chr")),
    placementMode: normalizeString(firstDefined(source, "placementMode", "placement_mode")),
    refAlignmentStatus: normalizeString(
      firstDefined(source, "refAlignmentStatus", "ref_alignment_status"),
    ),
    anchorStart: normalizePositiveInteger(firstDefined(source, "anchorStart", "anchor_start")),
    orientation: normalizeString(source.orientation) === "-" ? "-" : "+",
    refEvidenceIds: normalizeStringList(
      firstDefined(source, "refEvidenceIds", "ref_evidence_ids", "ref_evidence_ids_json"),
    ),
    acceptedEventIds: normalizeStringList(
      firstDefined(source, "acceptedEventIds", "accepted_event_ids", "accepted_event_ids_json"),
    ),
    finalPathSegmentIds: normalizeStringList(
      firstDefined(
        source,
        "finalPathSegmentIds",
        "final_path_segment_ids",
        "final_path_segment_ids_json",
      ),
    ),
    pairwiseEvidenceIds: normalizeStringList(
      firstDefined(
        source,
        "pairwiseEvidenceIds",
        "pairwise_evidence_ids",
        "pairwise_evidence_ids_json",
      ),
    ),
  };
}

function normalizeObjectAttempt(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    ...source,
    attemptId: normalizeString(firstDefined(source, "attemptId", "attempt_id")),
    chr: normalizeString(source.chr),
    objectId: normalizeString(firstDefined(source, "objectId", "object_id")),
    objectKind: normalizeString(firstDefined(source, "objectKind", "object_kind")),
    stage: normalizeString(source.stage),
    status: normalizeString(source.status),
    reason: normalizeString(source.reason),
    candidateCount: Number(firstDefined(source, "candidateCount", "candidate_count") || 0),
    acceptedEventId: normalizeString(
      firstDefined(source, "acceptedEventId", "accepted_event_id"),
    ),
  };
}

function findSourceCardForSegment(sourceCards, chrName, segmentId, source) {
  return sourceCards.find((card) => card.finalPathSegmentIds.includes(segmentId))
    || sourceCards.find(
      (card) => card.targetChr === chrName
        && card.datasetName === normalizeString(source?.dataset)
        && card.contigName === normalizeString(source?.contig),
    )
    || null;
}

function normalizeGrtSegment(segment, index, chrName, sourceCards) {
  const source = segment && typeof segment === "object" && !Array.isArray(segment) ? segment : {};
  const segmentId = normalizeString(firstDefined(source, "segmentId", "segment_id"))
    || `grt-${chrName}-${index + 1}`;
  const length = normalizePositiveInteger(source.length) || 1;
  const kind = normalizeString(source.kind).toLowerCase() || "source";
  const eventId = normalizeString(firstDefined(source, "eventId", "event_id"));
  const evidenceIds = normalizeStringList(firstDefined(source, "evidenceIds", "evidence_ids"));
  if (kind === "gap") {
    return {
      segmentId,
      type: "gap",
      gapSizeBp: length,
      grtKind: kind,
      eventId,
      evidenceIds,
      serverBaseline: true,
    };
  }
  const sourceLocator = source.source && typeof source.source === "object" ? source.source : {};
  const start = normalizePositiveInteger(sourceLocator.start) || 1;
  const end = normalizePositiveInteger(sourceLocator.end) || Math.max(start, length);
  const orientation = normalizeString(sourceLocator.orientation || source.orientation) === "-" ? "-" : "+";
  const sourceCard = findSourceCardForSegment(sourceCards, chrName, segmentId, sourceLocator);
  return {
    segmentId,
    type: "ctg",
    assemblyCtgId: null,
    datasetName: normalizeString(sourceLocator.dataset),
    ctgName: normalizeString(sourceLocator.contig),
    originId: normalizeString(sourceLocator.contig),
    overallLen: Math.max(start, end, length),
    orient: orientation,
    start: orientation === "-" ? Math.max(start, end) : Math.min(start, end),
    end: orientation === "-" ? Math.min(start, end) : Math.max(start, end),
    grtKind: kind,
    eventId,
    evidenceIds,
    sourceCardKey: sourceCard?.sourceCardKey || "",
    placementMode: sourceCard?.placementMode || "normal",
    refAlignmentStatus: sourceCard?.refAlignmentStatus || "",
    anchorSource: sourceCard ? "grt_final_path" : "reference_alignment",
    source: {
      dataset: normalizeString(sourceLocator.dataset),
      contig: normalizeString(sourceLocator.contig),
      start,
      end,
      orientation,
    },
    serverBaseline: true,
  };
}

export function normalizeGrtFinalPathByChr(value, sourceCards = []) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const cards = (Array.isArray(sourceCards) ? sourceCards : []).map(normalizeSourceCard);
  const result = {};
  Object.entries(source).forEach(([fallbackChrName, rawEntry]) => {
    const entry = rawEntry && typeof rawEntry === "object" && !Array.isArray(rawEntry) ? rawEntry : {};
    const chrName = normalizeString(entry.chr) || normalizeString(fallbackChrName);
    if (!chrName) {
      return;
    }
    const segments = (Array.isArray(entry.segments) ? entry.segments : [])
      .map((segment, index) => normalizeGrtSegment(segment, index, chrName, cards));
    result[chrName] = {
      mode: "segments",
      chrName,
      segments,
      totalLength: normalizePositiveInteger(firstDefined(entry, "q4Length", "q4_length"))
        || segments.reduce((total, segment) => total + (segment.type === "gap"
          ? segment.gapSizeBp
          : Math.abs(segment.end - segment.start) + 1), 0),
      updatedAt: "server-precomputed",
      q4Length: normalizePositiveInteger(firstDefined(entry, "q4Length", "q4_length")),
      q4Sha256: normalizeString(firstDefined(entry, "q4Sha256", "q4_sha256")),
      serverBaseline: true,
    };
  });
  return result;
}

export function normalizeGrtProjectView(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const sourceCards = (Array.isArray(firstDefined(source, "sourceCards", "source_cards"))
    ? firstDefined(source, "sourceCards", "source_cards")
    : []).map(normalizeSourceCard);
  const objectAttempts = (Array.isArray(firstDefined(source, "objectAttempts", "object_attempts"))
    ? firstDefined(source, "objectAttempts", "object_attempts")
    : []).map(normalizeObjectAttempt);
  const verificationSource = firstDefined(source, "verification") || {};
  return {
    recipe: normalizeGrtRecipe(source.recipe),
    baselineFinalPathByChr: normalizeGrtFinalPathByChr(
      firstDefined(source, "finalPathByChr", "final_path_by_chr"),
      sourceCards,
    ),
    objectAttempts,
    sourceCards,
    verification: {
      chromosomeCount: Number(
        firstDefined(verificationSource, "chromosomeCount", "chromosome_count") || 0,
      ),
      segmentCount: Number(
        firstDefined(verificationSource, "segmentCount", "segment_count") || 0,
      ),
      q4ArtifactSha256: normalizeString(
        firstDefined(verificationSource, "q4ArtifactSha256", "q4_artifact_sha256"),
      ),
    },
  };
}

export function buildEmptyGrtProjectView() {
  return {
    recipe: normalizeGrtRecipe({}),
    baselineFinalPathByChr: {},
    objectAttempts: [],
    sourceCards: [],
    verification: {
      chromosomeCount: 0,
      segmentCount: 0,
      q4ArtifactSha256: "",
    },
  };
}
