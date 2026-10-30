import { bindAppTooltips } from "../../app-tooltip-runtime.js";

// Main/Local, Canvas proxies and patched LGZ evidence all use the same owner.
export function bindAlignmentTooltips(host) { return bindAppTooltips(host); }
