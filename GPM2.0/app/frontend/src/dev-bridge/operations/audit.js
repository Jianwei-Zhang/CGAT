import {
  normalizeNullableText,
  normalizeToken,
  parseKeyValueLines,
  requireNumber,
  requireString,
} from "../contracts.js";

export function createAuditOperations(runtime) {
  const { runBackend } = runtime;

async function listExportRecords(payload) {
  const { workspaceRoot, projectId, limit } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  const resolvedLimit = Number.isFinite(limit) ? Math.trunc(limit) : 50;
  const output = await runBackend([
    "list-export-records",
    workspaceRoot,
    String(projectId),
    "--limit",
    String(Math.max(1, resolvedLimit)),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items = [];
  for (const line of lines) {
    const match = line.match(
      /^record id=(\d+) project_id=(\d+) export_type=(\S+) reference_chr_id=(\S+) assembly_ctg_id=(\S+) output_path=(\S+) created_at=(\S+) note=(.*)$/,
    );
    if (!match) {
      continue;
    }
    items.push({
      id: Number(match[1]),
      projectId: Number(match[2]),
      exportType: match[3],
      referenceChrId: normalizeToken(match[4]),
      assemblyCtgId: normalizeToken(match[5]),
      outputPath: match[6],
      createdAt: match[7],
      note: normalizeToken(match[8]),
    });
  }
  return { items };
}

async function listEditAuditLogs(payload) {
  const { workspaceRoot, projectId, limit } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  const resolvedLimit = Number.isFinite(limit) ? Math.trunc(limit) : 200;
  const output = await runBackend([
    "list-edit-audit-logs",
    workspaceRoot,
    String(projectId),
    "--limit",
    String(Math.max(1, resolvedLimit)),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items = [];
  for (const line of lines) {
    const match = line.match(
      /^log id=(\d+) project_id=(\d+) category=(\S+) action=(.*?) detail=(.*?) created_at=(\S+)$/,
    );
    if (!match) {
      continue;
    }
    items.push({
      id: Number(match[1]),
      projectId: Number(match[2]),
      category: match[3],
      action: match[4],
      detail: normalizeNullableText(match[5]),
      createdAt: match[6],
    });
  }
  return { items };
}

async function appendEditAuditLog(payload) {
  const { workspaceRoot, projectId, category, action, detail } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("category", category);
  requireString("action", action);
  const args = [
    "append-edit-audit-log",
    workspaceRoot,
    String(projectId),
    category,
    action,
  ];
  if (typeof detail === "string" && detail.trim() !== "") {
    args.push("--detail", detail.trim());
  }
  const output = await runBackend(args);
  const record = parseKeyValueLines(output.stdout);
  return {
    id: Number(record.id || 0),
    projectId: Number(record.project_id || projectId),
    category: record.category || category,
    action: record.action || action,
    detail: typeof detail === "string" && detail.trim() ? detail.trim() : null,
    createdAt: record.created_at || "",
  };
}

async function clearEditAuditLogs(payload) {
  const { workspaceRoot, projectId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  const output = await runBackend([
    "clear-edit-audit-logs",
    workspaceRoot,
    String(projectId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    deletedCount: Number(record.deleted_count || 0),
  };
}

  return {
    listExportRecords,
    listEditAuditLogs,
    appendEditAuditLog,
    clearEditAuditLogs,
  };
}
