import { bindAppTooltips, hideAppTooltips } from "../../app-tooltip-runtime.js";

export function bindImmediateTooltips(host) { return bindAppTooltips(host); }
export function hideImmediateTooltips(host) { hideAppTooltips(host); }
// Route teardown must not destroy the document owner used by other pages/dialogs.
export function destroyImmediateTooltips(host) { hideAppTooltips(host); }
