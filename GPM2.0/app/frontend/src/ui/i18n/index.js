import { zh as shellZh, en as shellEn } from "./messages/shell.js";
import { zh as importerZh, en as importerEn } from "./messages/importer.js";
import { zh as workspaceZh, en as workspaceEn } from "./messages/workspace.js";
import { zh as assemblyZh, en as assemblyEn } from "./messages/assembly.js";

const catalogs = {
  zh: {
    shell: shellZh,
    importer: importerZh,
    workspace: workspaceZh,
    assembly: assemblyZh,
  },
  en: {
    shell: shellEn,
    importer: importerEn,
    workspace: workspaceEn,
    assembly: assemblyEn,
  },
};

function resolveCatalog(locale) {
  return catalogs[getLocale(locale)];
}

function resolveMessage(locale, path) {
  const segments = String(path || "").split(".").filter(Boolean);
  let current = resolveCatalog(locale);
  for (const segment of segments) {
    current = current?.[segment];
  }
  if (current === undefined) {
    throw new Error(`Missing i18n message for path "${path}" in locale "${getLocale(locale)}"`);
  }
  return current;
}

function interpolate(template, vars = {}) {
  return String(template).replaceAll(/\{([a-zA-Z0-9_]+)\}/g, (match, key) => (
    Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : match
  ));
}

function getIntlLocale(stateOrLocale) {
  return getLocale(stateOrLocale) === "en" ? "en-US" : "zh-CN";
}

function normalizeDateValue(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  if (value instanceof Date) {
    return value;
  }
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }
  const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function getLocale(stateOrLocale) {
  if (stateOrLocale === "en" || stateOrLocale === "zh") {
    return stateOrLocale;
  }
  if (stateOrLocale?.locale === "en" || stateOrLocale?.locale === "zh") {
    return stateOrLocale.locale;
  }
  return "zh";
}

export function getMessages(stateOrLocale, domain) {
  const messages = resolveCatalog(stateOrLocale)?.[domain];
  if (!messages) {
    throw new Error(`Missing i18n domain "${domain}" for locale "${getLocale(stateOrLocale)}"`);
  }
  return messages;
}

export function t(stateOrLocale, path, vars = {}) {
  const message = resolveMessage(stateOrLocale, path);
  if (typeof message !== "string") {
    throw new Error(`I18n message at path "${path}" is not a string`);
  }
  return interpolate(message, vars);
}

export function formatNumber(stateOrLocale, value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "-";
  }
  return new Intl.NumberFormat(getIntlLocale(stateOrLocale)).format(number);
}

export function formatDateTime(stateOrLocale, value) {
  const date = normalizeDateValue(value);
  if (!date) {
    return String(value || "");
  }
  return new Intl.DateTimeFormat(getIntlLocale(stateOrLocale), {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}
