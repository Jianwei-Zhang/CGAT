import {
  normalizeToken,
  parseKeyValueLines,
  requireNumber,
  requireString,
} from "../contracts.js";

export function createInspectionOperations(runtime) {
  const { runBackend } = runtime;

async function getJunctionInspection(payload) {
  const {
    workspaceRoot,
    projectId,
    leftAssemblyCtgId,
    rightAssemblyCtgId,
    minAlignmentLength,
    minMapq,
  } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("leftAssemblyCtgId", leftAssemblyCtgId);
  requireNumber("rightAssemblyCtgId", rightAssemblyCtgId);

  const args = [
    "get-junction-inspection",
    workspaceRoot,
    String(projectId),
    String(leftAssemblyCtgId),
    String(rightAssemblyCtgId),
  ];
  if (Number.isFinite(Number(minAlignmentLength)) && Number(minAlignmentLength) > 0) {
    args.push("--min-align-length", String(Math.trunc(Number(minAlignmentLength))));
  }
  if (Number.isFinite(Number(minMapq)) && Number(minMapq) > 0) {
    args.push("--min-mapq", String(Math.trunc(Number(minMapq))));
  }
  const output = await runBackend(args);
  return parseJunctionInspection(output.stdout);
}

function parseJunctionInspection(stdout) {
  const lines = stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const record = parseKeyValueLines(stdout);
  const report = {
    projectId: Number(record.project_id || 0),
    assignedChrName: normalizeToken(record.assigned_chr_name),
    placementRelation: record.placement_relation || "unknown",
    overlapBp: normalizeToken(record.overlap_bp),
    gapBp: normalizeToken(record.gap_bp),
    sameDataset: record.same_dataset === "true",
    evidenceSource: record.evidence_source || "unknown",
    evidenceHitCount: Number(record.evidence_hit_count || 0),
    left: {
      assemblyCtgId: Number(record.left_ctg_id || 0),
      name: normalizeToken(record.left_name),
      anchorStart: normalizeToken(record.left_anchor),
      anchorEnd: normalizeToken(record.left_end),
      spanLength: Number(record.left_span || 0),
    },
    right: {
      assemblyCtgId: Number(record.right_ctg_id || 0),
      name: normalizeToken(record.right_name),
      anchorStart: normalizeToken(record.right_anchor),
      anchorEnd: normalizeToken(record.right_end),
      spanLength: Number(record.right_span || 0),
    },
    hits: [],
  };

  for (const line of lines) {
    const hit = line.match(
      /^hit query_ctg_id=(\d+) query_id=(\d+) query_name=(.*?) subject_ctg_id=(\d+) subject_id=(\d+) subject_name=(.*?) strand=(\S+) q=(\d+)\.\.(\d+) s=(\d+)\.\.(\d+) mapq=(\d+) identity_pct=([0-9.]+) align_length=(\d+) mismatch_count=(\S+) gap_open_count=(\S+) evalue=(\S+) bit_score=(\S+) origin=(\S+)$/,
    );
    if (hit) {
      report.hits.push({
        queryAssemblyCtgId: Number(hit[1]),
        querySourceSeqId: Number(hit[2]),
        querySourceSeqName: hit[3],
        subjectAssemblyCtgId: Number(hit[4]),
        subjectSourceSeqId: Number(hit[5]),
        subjectSourceSeqName: hit[6],
        strand: hit[7],
        queryStart: Number(hit[8]),
        queryEnd: Number(hit[9]),
        subjectStart: Number(hit[10]),
        subjectEnd: Number(hit[11]),
        mapq: Number(hit[12]),
        identityPct: Number(hit[13]),
        alignLength: Number(hit[14]),
        mismatchCount: normalizeToken(hit[15]),
        gapOpenCount: normalizeToken(hit[16]),
        evalue: normalizeToken(hit[17]),
        bitScore: normalizeToken(hit[18]),
        evidenceOrigin: hit[19],
      });
      continue;
    }
    const legacyHit = line.match(
      /^hit query_id=(\d+) query_name=(.*?) subject_id=(\d+) subject_name=(.*?) strand=(\S+) q=(\d+)\.\.(\d+) s=(\d+)\.\.(\d+) identity_pct=([0-9.]+) align_length=(\d+) mismatch_count=(\S+) gap_open_count=(\S+) evalue=(\S+) bit_score=(\S+) origin=(\S+)$/,
    );
    if (!legacyHit) {
      continue;
    }
    report.hits.push({
      querySourceSeqId: Number(legacyHit[1]),
      querySourceSeqName: legacyHit[2],
      subjectSourceSeqId: Number(legacyHit[3]),
      subjectSourceSeqName: legacyHit[4],
      strand: legacyHit[5],
      queryStart: Number(legacyHit[6]),
      queryEnd: Number(legacyHit[7]),
      subjectStart: Number(legacyHit[8]),
      subjectEnd: Number(legacyHit[9]),
      identityPct: Number(legacyHit[10]),
      alignLength: Number(legacyHit[11]),
      mismatchCount: normalizeToken(legacyHit[12]),
      gapOpenCount: normalizeToken(legacyHit[13]),
      evalue: normalizeToken(legacyHit[14]),
      bitScore: normalizeToken(legacyHit[15]),
      evidenceOrigin: legacyHit[16],
    });
  }
  return report;
}

  return { getJunctionInspection };
}
