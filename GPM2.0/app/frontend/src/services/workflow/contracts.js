const SUPPORTED_CTG_EDITOR_ACTIONS = new Set([
  "rename-ctg",
  "flip-ctg",
  "delete-ctg",
  "restore-deleted-ctg",
  "flip-seq",
  "hide-seq",
  "show-seq",
  "set-end-type",
]);

export function normalizeSupportedCtgEditorAction(action) {
  const normalized = String(action || "").trim().toLowerCase();
  if (SUPPORTED_CTG_EDITOR_ACTIONS.has(normalized)) {
    return normalized;
  }
  throw new Error(`unsupported ctg editor action: ${normalized || "<empty>"}`);
}

export function normalizeFinalPathViewMode(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "log" || normalized === "degap" || normalized === "table") {
    return normalized;
  }
  return "graph";
}

export function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function normalizeWorkflowError(error, defaults = {}) {
  const baseError =
    error && typeof error === "object" ? error : new Error(String(error || "workflow error"));
  const message =
    String(
      baseError.message
        || baseError.data?.message
        || defaults.message
        || "workflow error",
    ) || "workflow error";
  const normalized = new Error(message);
  normalized.name = baseError.name || "Error";
  normalized.code = String(
    baseError.code
      || baseError.data?.code
      || defaults.code
      || "WORKFLOW_ERROR",
  );
  normalized.source = baseError.source || defaults.source || "workflow";
  normalized.operation = baseError.operation || defaults.operation || "";
  normalized.detail = baseError.detail || baseError.data?.detail || defaults.detail || null;
  normalized.data = baseError.data || defaults.data || null;
  normalized.cause = baseError;
  return normalized;
}

export function applyListLimit(items, limit) {
  const normalizedItems = Array.isArray(items) ? items : [];
  const normalizedLimit = Number(limit);
  if (!Number.isFinite(normalizedLimit) || normalizedLimit < 0) {
    return normalizedItems;
  }
  return normalizedItems.slice(0, normalizedLimit);
}
