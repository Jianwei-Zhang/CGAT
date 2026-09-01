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
    sourceCardKey: normalizeString(firstDefined(source, "sourceCardKey", "source_card_key")),
    datasetName: normalizeString(firstDefined(source, "datasetName", "dataset_name")),
    contigName: normalizeString(firstDefined(source, "contigName", "contig_name")),
    targetChr: normalizeString(firstDefined(source, "targetChr", "target_chr")),
    placementMode: normalizeString(firstDefined(source, "placementMode", "placement_mode")),
    refAlignmentStatus: normalizeString(
      firstDefined(source, "refAlignmentStatus", "ref_alignment_status"),
    ),
  };
}

function normalizeGrtSegment(segment, index, chrName) {
  const source = segment && typeof segment === "object" && !Array.isArray(segment) ? segment : {};
  const segmentId = normalizeString(firstDefined(source, "segmentId", "segment_id"))
    || `grt-${chrName}-${index + 1}`;
  const length = normalizePositiveInteger(source.length) || 1;
  const kind = normalizeString(source.kind).toLowerCase() || "source";
  if (kind === "gap") {
    return {
      segmentId,
      type: "gap",
      gapSizeBp: length,
      serverBaseline: true,
    };
  }
  const sourceLocator = source.source && typeof source.source === "object" ? source.source : {};
  const start = normalizePositiveInteger(sourceLocator.start) || 1;
  const end = normalizePositiveInteger(sourceLocator.end) || Math.max(start, length);
  const sourceLength = normalizePositiveInteger(
    firstDefined(source, "sourceLength", "source_length"),
  );
  if (!sourceLength || start > sourceLength || end > sourceLength) {
    throw new TypeError(
      `Invalid GRT source_length for ${chrName}:${segmentId}: ${String(sourceLength || "missing")}`,
    );
  }
  const orientation = normalizeString(sourceLocator.orientation || source.orientation) === "-" ? "-" : "+";
  const assemblyCtgId = normalizePositiveInteger(
    firstDefined(source, "assemblyCtgId", "assembly_ctg_id"),
  );
  const assemblySourceStart = normalizePositiveInteger(
    firstDefined(source, "assemblySourceStart", "assembly_source_start"),
  );
  const assemblySourceEnd = normalizePositiveInteger(
    firstDefined(source, "assemblySourceEnd", "assembly_source_end"),
  );
  return {
    segmentId,
    type: "ctg",
    assemblyCtgId,
    ...(assemblySourceStart ? { assemblySourceStart } : {}),
    ...(assemblySourceEnd ? { assemblySourceEnd } : {}),
    datasetName: normalizeString(sourceLocator.dataset),
    ctgName: normalizeString(sourceLocator.contig),
    originId: normalizeString(sourceLocator.contig),
    overallLen: sourceLength,
    orient: orientation,
    start: orientation === "-" ? Math.max(start, end) : Math.min(start, end),
    end: orientation === "-" ? Math.min(start, end) : Math.max(start, end),
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

function normalizeGrtEvidenceEndpoint(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const start = normalizePositiveInteger(source.start);
  const end = normalizePositiveInteger(source.end);
  const assemblyCtgId = normalizePositiveInteger(
    firstDefined(source, "assemblyCtgId", "assembly_ctg_id"),
  );
  const assemblySourceStart = normalizePositiveInteger(
    firstDefined(source, "assemblySourceStart", "assembly_source_start"),
  );
  const assemblySourceEnd = normalizePositiveInteger(
    firstDefined(source, "assemblySourceEnd", "assembly_source_end"),
  );
  if (!start || !end || !assemblyCtgId || !assemblySourceStart || !assemblySourceEnd) {
    return null;
  }
  return {
    datasetName: normalizeString(source.dataset),
    contigName: normalizeString(source.contig),
    start: Math.min(start, end),
    end: Math.max(start, end),
    orientation: normalizeString(source.orientation) === "-" ? "-" : "+",
    assemblyCtgId,
    assemblySourceStart,
    assemblySourceEnd,
  };
}

function normalizeGrtDisplayEvidence(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const sourceEndpoint = normalizeGrtEvidenceEndpoint(source.source);
  const targetEndpoint = normalizeGrtEvidenceEndpoint(source.target);
  const alignedLength = normalizePositiveInteger(
    firstDefined(source, "alignedLength", "aligned_length"),
  );
  const identity = Number(source.identity);
  if (!sourceEndpoint || !targetEndpoint || !alignedLength || !Number.isFinite(identity)) {
    return null;
  }
  return {
    evidenceId: normalizeString(firstDefined(source, "evidenceId", "evidence_id")),
    eventId: normalizeString(firstDefined(source, "eventId", "event_id")),
    finalPathSegmentId: normalizeString(
      firstDefined(source, "finalPathSegmentId", "final_path_segment_id"),
    ),
    supportingEventId: normalizeString(
      firstDefined(source, "supportingEventId", "supporting_event_id"),
    ),
    stage: normalizeString(source.stage),
    action: normalizeString(source.action),
    association: normalizeString(source.association),
    tool: normalizeString(source.tool),
    preset: normalizeString(source.preset),
    role: normalizeString(source.role),
    alignedLength,
    identity,
    mapq: source.mapq === null || source.mapq === undefined ? null : Number(source.mapq),
    source: sourceEndpoint,
    target: targetEndpoint,
  };
}

export function normalizeGrtFinalPathByChr(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const result = {};
  Object.entries(source).forEach(([fallbackChrName, rawEntry]) => {
    const entry = rawEntry && typeof rawEntry === "object" && !Array.isArray(rawEntry) ? rawEntry : {};
    const chrName = normalizeString(entry.chr) || normalizeString(fallbackChrName);
    if (!chrName) {
      return;
    }
    const segments = (Array.isArray(entry.segments) ? entry.segments : [])
      .map((segment, index) => normalizeGrtSegment(segment, index, chrName));
    const displayEvidence = (
      Array.isArray(firstDefined(entry, "displayEvidence", "display_evidence"))
        ? firstDefined(entry, "displayEvidence", "display_evidence")
        : []
    )
      .map(normalizeGrtDisplayEvidence)
      .filter(Boolean);
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
      grtDisplayAvailable: firstDefined(
        entry,
        "grtDisplayAvailable",
        "grt_display_available",
      ) === true,
      displayEvidence,
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
  const verificationSource = firstDefined(source, "verification") || {};
  return {
    recipe: normalizeGrtRecipe(source.recipe),
    baselineFinalPathByChr: normalizeGrtFinalPathByChr(
      firstDefined(source, "finalPathByChr", "final_path_by_chr"),
    ),
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
    sourceCards: [],
    verification: {
      chromosomeCount: 0,
      segmentCount: 0,
      q4ArtifactSha256: "",
    },
  };
}
