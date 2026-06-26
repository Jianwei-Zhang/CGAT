import { getAssemblyI18n } from "./i18n.js";

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
  const normalizedCode = code.toLowerCase();

  if (normalizedCode === "current_chr_no_matching_ctg") {
    return { code, category: "current-chr-no-matching-ctg", rawMessage: message };
  }

  if (normalizedCode === "ctg_search_keyword_required") {
    return { code, category: "ctg-search-keyword-required", rawMessage: message };
  }

  if (
    normalizedCode.includes("invalid") ||
    normalizedCode.includes("missing") ||
    /must be (provided|present|a positive integer|non-empty|not be blank)|missing|required|invalid param|invalid argument|invalid .+ id|not a valid (integer|number)/.test(
      normalizedMessage,
    )
  ) {
    return { code, category: "invalid-params", rawMessage: message };
  }

  if (/does not exist|not found|未找到|不存在/.test(normalizedMessage)) {
    return { code, category: "not-found", rawMessage: message };
  }

  if (
    normalizedCode.includes("conflict") ||
    /state conflict|already |only allow|only allowed|cannot |entered assembly/.test(normalizedMessage)
  ) {
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
    normalizedCode.startsWith("tauri") ||
    normalizedCode.includes("runtime") ||
    /当前为浏览器预览，无法调用后端命令|failed to invoke command|dev bridge error|failed to fetch|networkerror|load failed|tauri/.test(
      normalizedMessage,
    )
  ) {
    return { code, category: "runtime", rawMessage: message };
  }

  return {
    code,
    category: "generic",
    rawMessage: message || getAssemblyI18n("zh").errors.generic,
  };
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
