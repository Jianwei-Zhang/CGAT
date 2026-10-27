import { bindImmediateTooltips, hideImmediateTooltips } from "./immediate-tooltip-runtime.js";

export function bindFinalPathTooltips(host) {
  bindImmediateTooltips(host, { attribute: "data-final-path-tooltip", className: "final-path-tooltip" });
}

export function hideFinalPathTooltips(host) {
  hideImmediateTooltips(host, "data-final-path-tooltip");
}
