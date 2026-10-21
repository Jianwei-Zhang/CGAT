import { isFinalPathRefSegment } from "./final-path-state.js";

// Stable track colors, shared by Main/Local View, Final Path and project exports.
// Keep these headless-export fallbacks in sync with the :root tokens in base.css.
export const DEFAULT_CONTIG_PALETTE = Object.freeze({
  primary: Object.freeze({ fill: "#d2dfef", stroke: "#6d85a1", text: "#243a54" }),
  companion: Object.freeze({ fill: "#e7dec4", stroke: "#8a7551", text: "#5c492a" }),
  ref: Object.freeze({ fill: "#cfcfcf", stroke: "#8e8e8e", text: "#4f4f4f" }),
});

export function getContigPalette() {
  const root = globalThis.document?.documentElement;
  const styles = root && typeof globalThis.getComputedStyle === "function"
    ? globalThis.getComputedStyle(root)
    : null;
  return Object.fromEntries(Object.entries(DEFAULT_CONTIG_PALETTE).map(([role, colors]) => [
    role,
    Object.fromEntries(Object.entries(colors).map(([property, fallback]) => [
      property,
      styles?.getPropertyValue?.(`--ctg-${role}-${property}`)?.trim() || fallback,
    ])),
  ]));
}

function normalizeDataset(value) {
  const name = String(value || "").trim().toLowerCase();
  return name === "-" ? "" : name;
}

export function createContigColorResolver({ primaryDatasetName = "", primaryCtgs = [], supportCtgs = [] } = {}) {
  const primaryDataset = normalizeDataset(primaryDatasetName);
  const rolesById = new Map();
  for (const [role, ctgs] of [["companion", supportCtgs], ["primary", primaryCtgs]]) {
    for (const ctg of Array.isArray(ctgs) ? ctgs : []) {
      const id = Number(ctg?.assemblyCtgId);
      if (Number.isSafeInteger(id) && id > 0) rolesById.set(id, role);
    }
  }
  return (segment) => {
    if (isFinalPathRefSegment(segment)) return "ref";
    // Actual track membership wins for derived ctgs assigned to the primary lane.
    // Split/cross-chr copies keep their own IDs; never infer identity from a label.
    for (const id of [segment?.splitFragmentCtgId, segment?.assemblyCtgId]) {
      const role = rolesById.get(Number(id));
      if (role) return role;
    }
    const dataset = normalizeDataset(segment?.source?.dataset || segment?.datasetName);
    return dataset && primaryDataset && dataset !== primaryDataset ? "companion" : "primary";
  };
}
