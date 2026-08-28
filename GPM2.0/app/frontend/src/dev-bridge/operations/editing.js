import {
  normalizeToken,
  parseKeyValueLines,
  requireNumber,
  requireString,
} from "../contracts.js";

export function createEditingOperations(runtime) {
  const { runBackend } = runtime;

async function listDeletedCtgs(payload) {
  const { workspaceRoot, projectId, chrName, datasetId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);

  const args = ["list-deleted-ctgs", workspaceRoot, String(projectId)];
  if (typeof chrName === "string" && chrName.trim()) {
    args.push("--chr-name", chrName.trim());
  }
  if (Number.isFinite(Number(datasetId)) && Number(datasetId) > 0) {
    args.push("--dataset-id", String(Math.trunc(Number(datasetId))));
  }
  const output = await runBackend(args);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const items = [];
  for (const line of lines) {
    const match = line.match(
      /^deleted_ctg record_id=(\d+) ctg_id=(\d+) name=(.*?) chr=(.*?) chr_order=(\S+) anchor_start=(\S+) ref_orient=(\S+) mode=(\S+) members=(\d+) bp=(\d+) deleted_at=(\S+)$/,
    );
    if (!match) {
      continue;
    }
    items.push({
      deletedCtgRecordId: Number(match[1]),
      assemblyCtgId: Number(match[2]),
      name: match[3],
      assignedChrName: normalizeToken(match[4]),
      chrOrder: normalizeToken(match[5]),
      anchorStart: normalizeToken(match[6]),
      refOrient: normalizeToken(match[7]),
      placementMode: match[8],
      memberCount: Number(match[9]),
      totalLength: Number(match[10]),
      deletedAt: match[11],
    });
  }
  return { items };
}

async function getCtgDetail(payload) {
  const { workspaceRoot, projectId, assemblyCtgId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("assemblyCtgId", assemblyCtgId);

  const output = await runBackend([
    "get-ctg-detail",
    workspaceRoot,
    String(projectId),
    String(assemblyCtgId),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const head = lines.find((line) => line.startsWith("ctg id="));
  if (!head) {
    throw new Error("missing ctg detail head");
  }
  const headMatch = head.match(
    /^ctg id=(\d+) name=(.*?) chr=(.*?) chr_order=(\S+) anchor_start=(\S+) ref_orient=(\S+) mode=(\S+)$/,
  );
  if (!headMatch) {
    throw new Error(`invalid ctg detail head: ${head}`);
  }
  const members = [];
  for (const line of lines) {
    const nextFormat = line.match(
      /^member id=(\d+) order=(\d+) assembly_seq_id=(\d+) dataset=(.*?) seq=(.*?) len=(\d+) orient=(\S+) range=(\d+)\.\.(\d+) left_end_type=(\S+) right_end_type=(\S+) hidden=(\w+) join_prev=(\S+) gap_prev=(\S+)$/,
    );
    if (nextFormat) {
      members.push({
        assemblyCtgMemberId: Number(nextFormat[1]),
        memberOrder: Number(nextFormat[2]),
        assemblySeqId: Number(nextFormat[3]),
        datasetName: nextFormat[4],
        seqName: nextFormat[5],
        seqLength: Number(nextFormat[6]),
        orient: nextFormat[7],
        sourceStart: Number(nextFormat[8]),
        sourceEnd: Number(nextFormat[9]),
        leftEndType: nextFormat[10],
        rightEndType: nextFormat[11],
        hidden: nextFormat[12] === "true",
        joinTypeToPrev: nextFormat[13],
        gapSizeToPrev: normalizeToken(nextFormat[14]),
      });
      continue;
    }

    const oldFormat = line.match(
      /^member order=(\d+) assembly_seq_id=(\d+) dataset=(.*?) seq=(.*?) len=(\d+) orient=(\S+) range=(\d+)\.\.(\d+) hidden=(\w+) join_prev=(\S+) gap_prev=(\S+)$/,
    );
    if (!oldFormat) {
      continue;
    }
    members.push({
      assemblyCtgMemberId: null,
      memberOrder: Number(oldFormat[1]),
      assemblySeqId: Number(oldFormat[2]),
      datasetName: oldFormat[3],
      seqName: oldFormat[4],
      seqLength: Number(oldFormat[5]),
      orient: oldFormat[6],
      sourceStart: Number(oldFormat[7]),
      sourceEnd: Number(oldFormat[8]),
      leftEndType: "normal",
      rightEndType: "normal",
      hidden: oldFormat[9] === "true",
      joinTypeToPrev: oldFormat[10],
      gapSizeToPrev: normalizeToken(oldFormat[11]),
    });
  }

  return {
    assemblyCtgId: Number(headMatch[1]),
    name: headMatch[2],
    assignedChrName: normalizeToken(headMatch[3]),
    chrOrder: normalizeToken(headMatch[4]),
    anchorStart: normalizeToken(headMatch[5]),
    refOrient: normalizeToken(headMatch[6]),
    placementMode: headMatch[7],
    members,
  };
}

async function listCtgEditCandidates(payload) {
  const { workspaceRoot, projectId, assemblyCtgId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("assemblyCtgId", assemblyCtgId);

  const output = await runBackend([
    "list-ctg-edit-candidates",
    workspaceRoot,
    String(projectId),
    String(assemblyCtgId),
  ]);
  const lines = output.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const moveTargetCtgs = [];
  const addSeqCandidates = [];

  for (const line of lines) {
    const moveMatch = line.match(/^move_target id=(\d+) name=(.*?) chr=(.*?) chr_order=(\S+)$/);
    if (moveMatch) {
      moveTargetCtgs.push({
        assemblyCtgId: Number(moveMatch[1]),
        name: moveMatch[2],
        assignedChrName: normalizeToken(moveMatch[3]),
        chrOrder: normalizeToken(moveMatch[4]),
      });
      continue;
    }
    const addMatch = line.match(
      /^add_seq assembly_seq_id=(\d+) dataset=(.*?) seq=(.*?) len=(\d+) hidden=(\w+)$/,
    );
    if (addMatch) {
      addSeqCandidates.push({
        assemblySeqId: Number(addMatch[1]),
        datasetName: addMatch[2],
        seqName: addMatch[3],
        seqLength: Number(addMatch[4]),
        hidden: addMatch[5] === "true",
      });
    }
  }
  return {
    moveTargetCtgs,
    addSeqCandidates,
  };
}

async function restoreDeletedCtg(payload) {
  const { workspaceRoot, projectId, deletedCtgRecordId } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireNumber("deletedCtgRecordId", deletedCtgRecordId);

  const output = await runBackend([
    "restore-deleted-ctg",
    workspaceRoot,
    String(projectId),
    String(deletedCtgRecordId),
  ]);
  const record = parseKeyValueLines(output.stdout);
  return {
    projectId: Number(record.project_id || projectId),
    deletedCtgRecordId: Number(record.deleted_ctg_record_id || deletedCtgRecordId),
    assemblyCtgId: Number(record.assembly_ctg_id || 0),
    restoredMemberCount: Number(record.restored_member_count || 0),
    refreshedChrCount: Number(record.refreshed_chr_count || 0),
  };
}

async function runCtgEditorAction(payload) {
  const { workspaceRoot, projectId, action, args } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("action", action);
  const normalized = action.trim().toLowerCase();
  const commandArgs = buildCtgEditorCommandArgs(normalized, workspaceRoot, projectId, args || {});
  const output = await runBackend(commandArgs);
  const record = parseKeyValueLines(output.stdout);
  return {
    action: normalized,
    ...record,
  };
}

function parseResultJson(output) {
  const record = parseKeyValueLines(output.stdout);
  const raw = String(record.result_json || "").trim();
  if (!raw) {
    throw new Error("missing main-view history result_json");
  }
  return JSON.parse(raw);
}

async function getMainViewHistoryStatus(payload) {
  const { workspaceRoot, projectId, chrName } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("chrName", chrName);
  return parseResultJson(await runBackend([
    "main-view-history-status",
    workspaceRoot,
    String(projectId),
    chrName,
  ]));
}

async function inspectMainViewDelete(payload) {
  const { workspaceRoot, projectId, chrName, assemblyCtgIds } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("chrName", chrName);
  const ids = normalizePositiveIdList("assemblyCtgIds", assemblyCtgIds);
  return parseResultJson(await runBackend([
    "inspect-main-view-delete",
    workspaceRoot,
    String(projectId),
    chrName,
    ids.join(","),
  ]));
}

async function runMainViewEditorAction(payload) {
  const { workspaceRoot, projectId, chrName, action, args = {} } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("chrName", chrName);
  requireString("action", action);
  return parseResultJson(await runBackend([
    "run-main-view-editor-action",
    workspaceRoot,
    String(projectId),
    chrName,
    action,
    JSON.stringify(args),
  ]));
}

async function runMainViewBatchDelete(payload) {
  const { workspaceRoot, projectId, chrName, assemblyCtgIds } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("chrName", chrName);
  const ids = normalizePositiveIdList("assemblyCtgIds", assemblyCtgIds);
  return parseResultJson(await runBackend([
    "run-main-view-batch-delete",
    workspaceRoot,
    String(projectId),
    chrName,
    ids.join(","),
  ]));
}

async function executeMainViewHistoryAction(payload) {
  const { workspaceRoot, projectId, chrName, action } = payload || {};
  requireString("workspaceRoot", workspaceRoot);
  requireNumber("projectId", projectId);
  requireString("chrName", chrName);
  const commands = {
    undo: "undo-main-view-history",
    redo: "redo-main-view-history",
    reset: "reset-main-view-history",
  };
  const command = commands[String(action || "").trim().toLowerCase()];
  if (!command) {
    throw new Error(`unsupported main-view history action: ${action || "<empty>"}`);
  }
  return parseResultJson(await runBackend([
    command,
    workspaceRoot,
    String(projectId),
    chrName,
  ]));
}

function normalizePositiveIdList(name, values) {
  if (!Array.isArray(values) || !values.length) {
    throw new Error(`${name} must be a non-empty array`);
  }
  return values.map((value) => {
    requireNumber(name, value);
    const normalized = Math.trunc(Number(value));
    if (normalized <= 0) {
      throw new Error(`${name} must contain positive integers`);
    }
    return normalized;
  });
}

function buildCtgEditorCommandArgs(action, workspaceRoot, projectId, args) {
  const base = [workspaceRoot, String(projectId)];
  switch (action) {
    case "rename-ctg":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      requireString("args.newName", args.newName);
      return ["rename-ctg", ...base, String(args.assemblyCtgId), args.newName];
    case "flip-ctg":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      return ["flip-ctg", ...base, String(args.assemblyCtgId)];
    case "delete-ctg":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      return ["delete-ctg", ...base, String(args.assemblyCtgId)];
    case "restore-deleted-ctg":
      requireNumber("args.deletedCtgRecordId", args.deletedCtgRecordId);
      return ["restore-deleted-ctg", ...base, String(args.deletedCtgRecordId)];
    case "reorder-members":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      if (!Array.isArray(args.assemblySeqIds) || args.assemblySeqIds.length === 0) {
        throw new Error("args.assemblySeqIds must be a non-empty array");
      }
      return [
        "reorder-members",
        ...base,
        String(args.assemblyCtgId),
        args.assemblySeqIds.map((value) => String(value)).join(","),
      ];
    case "add-seq-to-ctg":
      requireNumber("args.targetAssemblyCtgId", args.targetAssemblyCtgId);
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      return [
        "add-seq-to-ctg",
        ...base,
        String(args.targetAssemblyCtgId),
        String(args.assemblySeqId),
      ];
    case "append-ctg":
      requireNumber("args.targetAssemblyCtgId", args.targetAssemblyCtgId);
      requireNumber("args.sourceAssemblyCtgId", args.sourceAssemblyCtgId);
      return [
        "append-ctg",
        ...base,
        String(args.targetAssemblyCtgId),
        String(args.sourceAssemblyCtgId),
      ];
    case "split-ctg":
      requireNumber("args.assemblyCtgId", args.assemblyCtgId);
      requireNumber("args.breakAfterMemberId", args.breakAfterMemberId);
      requireString("args.newName", args.newName);
      return [
        "split-ctg",
        ...base,
        String(args.assemblyCtgId),
        String(args.breakAfterMemberId),
        args.newName,
      ];
    case "remove-seq-from-ctg":
      requireNumber("args.assemblyCtgMemberId", args.assemblyCtgMemberId);
      return ["remove-seq-from-ctg", ...base, String(args.assemblyCtgMemberId)];
    case "set-join-type-to-prev":
      requireNumber("args.assemblyCtgMemberId", args.assemblyCtgMemberId);
      requireString("args.joinTypeToPrev", args.joinTypeToPrev);
      if (args.gapSizeToPrev !== undefined && args.gapSizeToPrev !== null) {
        requireNumber("args.gapSizeToPrev", args.gapSizeToPrev);
      }
      return args.gapSizeToPrev === undefined || args.gapSizeToPrev === null
        ? [
            "set-join-type-to-prev",
            ...base,
            String(args.assemblyCtgMemberId),
            args.joinTypeToPrev,
          ]
        : [
            "set-join-type-to-prev",
            ...base,
            String(args.assemblyCtgMemberId),
            args.joinTypeToPrev,
            "--gap-size-to-prev",
            String(args.gapSizeToPrev),
          ];
    case "set-gap-size-to-prev":
      requireNumber("args.assemblyCtgMemberId", args.assemblyCtgMemberId);
      requireNumber("args.gapSizeToPrev", args.gapSizeToPrev);
      return [
        "set-gap-size-to-prev",
        ...base,
        String(args.assemblyCtgMemberId),
        String(args.gapSizeToPrev),
      ];
    case "flip-seq":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      return ["flip-seq", ...base, String(args.assemblySeqId)];
    case "hide-seq":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      return ["hide-seq", ...base, String(args.assemblySeqId)];
    case "show-seq":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      return ["show-seq", ...base, String(args.assemblySeqId)];
    case "set-seq-range":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      requireNumber("args.sourceStart", args.sourceStart);
      requireNumber("args.sourceEnd", args.sourceEnd);
      return [
        "set-seq-range",
        ...base,
        String(args.assemblySeqId),
        String(args.sourceStart),
        String(args.sourceEnd),
      ];
    case "set-end-type":
      requireNumber("args.assemblySeqId", args.assemblySeqId);
      requireString("args.leftEndType", args.leftEndType);
      requireString("args.rightEndType", args.rightEndType);
      return [
        "set-end-type",
        ...base,
        String(args.assemblySeqId),
        args.leftEndType,
        args.rightEndType,
      ];
    default:
      throw new Error(`unsupported ctg editor action: ${action}`);
  }
}

  return {
    listDeletedCtgs,
    getCtgDetail,
    listCtgEditCandidates,
    restoreDeletedCtg,
    runCtgEditorAction,
    getMainViewHistoryStatus,
    inspectMainViewDelete,
    runMainViewEditorAction,
    runMainViewBatchDelete,
    executeMainViewHistoryAction,
  };
}
