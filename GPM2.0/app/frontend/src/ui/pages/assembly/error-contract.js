import { getAssemblyI18n } from "./i18n.js";

const LEGACY_MESSAGE_FALLBACK_CODES = new Set([
  "ASSEMBLY_ERROR",
  "WORKFLOW_ERROR",
  "TAURI_INVOKE_ERROR",
  "DEV_BRIDGE_ERROR",
]);
const INVALID_PARAM_CODES = new Set([
  "INVALID_REQUEST",
  "INVALID_PARAMS",
  "GAP_SIZE_REQUIRED_FOR_JOIN_GAP",
  "MISSING_MEMBER_ID_FOR_MEMBER_ACTION",
]);

export function mapAssemblyError({ error, fallbackMessage, stateOrLocale = "zh" } = {}) {
  const i18n = getAssemblyI18n(stateOrLocale);
  const resolvedFallbackMessage = fallbackMessage || i18n.errors.generic;
  const details = normalizeAssemblyError(error);
  return {
    ...details,
    userMessage: resolveUserMessage(details.category, resolvedFallbackMessage, i18n),
  };
}

function normalizeAssemblyError(error) {
  const message = extractMessage(error);
  const normalizedMessage = message.toLowerCase();
  const code = extractCode(error);
  const normalizedCode = code.toUpperCase();
  const stableCategory = classifyStableCode(normalizedCode);
  if (stableCategory) {
    return { code, category: stableCategory, rawMessage: message };
  }

  // Remove this branch after every persisted/mock/third-party error producer emits a stable code.
  if (LEGACY_MESSAGE_FALLBACK_CODES.has(normalizedCode)) {
    return classifyLegacyMessage(code, message, normalizedMessage);
  }

  return {
    code,
    category: "generic",
    rawMessage: message || getAssemblyI18n("zh").errors.generic,
  };
}

function classifyStableCode(code) {
  if (code === "CURRENT_CHR_NO_MATCHING_CTG") {
    return "current-chr-no-matching-ctg";
  }
  if (code === "CTG_SEARCH_KEYWORD_REQUIRED") {
    return "ctg-search-keyword-required";
  }
  if (
    INVALID_PARAM_CODES.has(code)
    || code.includes("INVALID")
    || code.includes("MISSING")
  ) {
    return "invalid-params";
  }
  if (code === "NOT_FOUND" || code.endsWith("_NOT_FOUND")) {
    return "not-found";
  }
  if (code === "STATE_CONFLICT" || code.includes("CONFLICT")) {
    return "state-conflict";
  }
  if (code === "SUPPORT_DS_NOT_SELECTED") {
    return "support-ds-not-selected";
  }
  if (code === "SUPPORT_DS_NO_MATCHING_CHR") {
    return "support-ds-no-matching-chr";
  }
  if (code === "SUPPORT_DS_UNAVAILABLE") {
    return "support-ds-unavailable";
  }
  if (
    code === "RUNTIME_ERROR"
    || code.endsWith("_RUNTIME_ERROR")
    || code === "BROWSER_EXPORT_UNAVAILABLE"
  ) {
    return "runtime";
  }
  return "";
}

function classifyLegacyMessage(code, message, normalizedMessage) {
  if (
    /must be (provided|present|a positive integer|non-empty|not be blank)|missing|required|invalid param|invalid argument|invalid .+ id|not a valid (integer|number)/.test(
      normalizedMessage,
    )
  ) {
    return { code, category: "invalid-params", rawMessage: message };
  }

  if (/does not exist|not found|未找到|不存在/.test(normalizedMessage)) {
    return { code, category: "not-found", rawMessage: message };
  }

  if (/state conflict|already |only allow|only allowed|cannot |entered assembly/.test(normalizedMessage)) {
    return { code, category: "state-conflict", rawMessage: message };
  }

  if (/companion project not selected|support ds not selected|未选择.*对照|未选择.*辅 ds|请先选择辅 ds/.test(normalizedMessage)) {
    return { code, category: "support-ds-not-selected", rawMessage: message };
  }

  if (
    /no matching chromosome in companion project|no matching chromosome in support ds|companion.+no matching.+chr|support ds.+no matching.+chr|对照.*匹配.*染色体|辅 ds.*匹配.*染色体/.test(
      normalizedMessage,
    )
  ) {
    return { code, category: "support-ds-no-matching-chr", rawMessage: message };
  }

  if (/companion|support ds|辅 ds/.test(normalizedMessage)) {
    return { code, category: "support-ds-unavailable", rawMessage: message };
  }

  if (
    /当前为浏览器预览，无法调用后端命令|failed to invoke command|dev bridge error|failed to fetch|networkerror|load failed|tauri/.test(
      normalizedMessage,
    )
  ) {
    return { code, category: "runtime", rawMessage: message };
  }

  return { code, category: "generic", rawMessage: message };
}

function resolveUserMessage(category, fallbackMessage, i18n) {
  switch (category) {
    case "invalid-params":
      return i18n.errors.invalidParams;
    case "not-found":
      return i18n.errors.notFound;
    case "ctg-search-keyword-required":
      return i18n.errors.ctgSearchKeywordRequired;
    case "current-chr-no-matching-ctg":
      return i18n.errors.currentChrNoMatchingCtg;
    case "state-conflict":
      return i18n.errors.stateConflict;
    case "support-ds-unavailable":
      return i18n.errors.supportDsUnavailable;
    case "support-ds-not-selected":
      return i18n.errors.supportDsNotSelected;
    case "support-ds-no-matching-chr":
      return i18n.errors.supportDsNoMatchingChr;
    case "runtime":
      return i18n.errors.runtime;
    default:
      return fallbackMessage;
  }
}

function extractCode(error) {
  const code = error?.code ?? error?.data?.code ?? error?.cause?.code ?? "";
  return String(code || "").trim() || "ASSEMBLY_ERROR";
}

function extractMessage(error) {
  if (typeof error === "string") {
    return error;
  }
  const message = error?.message ?? error?.data?.message ?? error?.cause?.message ?? "";
  return String(message || "").trim() || getAssemblyI18n("zh").errors.generic;
}
