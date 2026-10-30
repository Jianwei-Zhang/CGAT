import { bindImmediateTooltips, hideImmediateTooltips } from "./immediate-tooltip-runtime.js";

export function bindFinalPathTooltips(host) {
  bindImmediateTooltips(host);
}

export function hideFinalPathTooltips(host) {
  hideImmediateTooltips(host);
}
