export function classifyBridgeErrorCode(message, fallback = "RUNTIME_ERROR") {
  const text = String(message || "");
  const prefixedCode = text
    .split(/\s+/)
    .map((token) => token.replace(/:$/, ""))
    .find((token) =>
      token.includes("_") && /^[A-Z][A-Z0-9_]+$/.test(token));
  if (prefixedCode) {
    return prefixedCode;
  }

  const normalized = text.toLowerCase();
  if (normalized.includes("does not exist") || normalized.includes("not found")) {
    return "NOT_FOUND";
  }
  if (
    normalized.includes("already")
    || normalized.includes("conflict")
    || normalized.includes("cannot")
    || normalized.includes("only allow")
    || normalized.includes("entered assembly")
  ) {
    return "STATE_CONFLICT";
  }
  if (
    normalized.includes("invalid")
    || normalized.includes("missing")
    || normalized.includes("must ")
    || normalized.includes("required")
  ) {
    return "INVALID_REQUEST";
  }
  return fallback;
}

function invalidRequest(message) {
  const error = new Error(message);
  error.code = "INVALID_REQUEST";
  error.status = 400;
  return error;
}

export function requireString(name, value) {
  if (typeof value !== "string" || value.trim() === "") {
    throw invalidRequest(`missing required field: ${name}`);
  }
}

export function requireNumber(name, value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw invalidRequest(`missing required number field: ${name}`);
  }
}

export function normalizeNull(value) {
  return value === "NULL" ? null : value;
}

export function normalizeToken(value) {
  if (value === "NULL") {
    return null;
  }
  if (/^-?\d+$/.test(value)) {
    return Number(value);
  }
  return value;
}

export function applyListLimit(items, limit) {
  const normalizedItems = Array.isArray(items) ? items : [];
  const normalizedLimit = Number(limit);
  if (!Number.isFinite(normalizedLimit) || normalizedLimit < 0) {
    return normalizedItems;
  }
  return normalizedItems.slice(0, normalizedLimit);
}

export function parseKeyValueLines(stdout) {
  const record = {};
  const lines = stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (const line of lines) {
    if (line.startsWith("stage=")) {
      continue;
    }
    const keyPattern = /([A-Za-z0-9_]+)=/g;
    const matches = Array.from(line.matchAll(keyPattern));
    for (let index = 0; index < matches.length; index += 1) {
      const current = matches[index];
      const next = matches[index + 1];
      const key = current[1];
      const valueStart = current.index + current[0].length;
      const valueEnd = next ? next.index : line.length;
      record[key] = line.slice(valueStart, valueEnd).trim();
    }
  }
  return record;
}

export function parseJsonObject(value) {
  try {
    const parsed = JSON.parse(String(value || "{}"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export function parseJsonLine(stdout, key) {
  const prefix = `${key}=`;
  const line = stdout
    .split(/\r?\n/)
    .map((item) => item.trim())
    .find((item) => item.startsWith(prefix));
  if (!line) {
    throw new Error(`backend output missing ${key}`);
  }
  try {
    return JSON.parse(line.slice(prefix.length));
  } catch (error) {
    throw new Error(`backend output contains invalid ${key}: ${error.message}`);
  }
}

export function parseIdList(value) {
  return String(value || "")
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item) && item > 0);
}

export function mapGrtRecipeToApi(recipe) {
  return {
    workflow: recipe.workflow || "",
    schemaVersion: recipe.schema_version || "",
    finalPathSchemaVersion: recipe.final_path_schema_version || "",
    recipeId: recipe.recipe_id || "",
    primaryDataset: recipe.primary_dataset || "",
    supportDatasets: Array.isArray(recipe.support_datasets) ? recipe.support_datasets : [],
    readsQcEnabled: Boolean(recipe.reads_qc_enabled),
    donorSetId: recipe.donor_set_id || "",
    telDonorSetId: recipe.tel_donor_set_id || "",
    q0Relpath: recipe.q0_relpath || "",
    finalQRelpath: recipe.final_q_relpath || "",
    q0ArtifactSha256: recipe.q0_artifact_sha256 || "",
    q4ArtifactSha256: recipe.q4_artifact_sha256 || "",
  };
}

export function normalizeNullableText(value) {
  return value === "NULL" ? null : value;
}
