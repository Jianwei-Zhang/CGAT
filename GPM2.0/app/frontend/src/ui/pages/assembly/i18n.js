import { getLocale, getMessages, t } from "../../i18n/index.js";

export const assemblyLabelsZh = getMessages("zh", "assembly");
export const assemblyLabelsEn = getMessages("en", "assembly");

export function getAssemblyLocale(state) {
  if (state?.locale === "en" || state?.locale === "zh") {
    return state.locale;
  }
  if (state?.assembly?.locale === "en" || state?.assembly?.locale === "zh") {
    return state.assembly.locale;
  }
  return getLocale(state);
}

export function getAssemblyI18n(state) {
  return getMessages(getAssemblyLocale(state), "assembly");
}

export function tAssembly(stateOrLocale, path, vars = {}) {
  return t(stateOrLocale, `assembly.${path}`, vars);
}
