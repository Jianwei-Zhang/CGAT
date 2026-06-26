import { tAssembly } from "./i18n.js";

const MODE_TWO = "2-contig";

export function validateSubviewSelection(input) {
  const normalized = normalizeInput(input);
  const stateOrLocale = input?.stateOrLocale || "zh";
  if (!normalized) {
    return { ok: false, error: tAssembly(stateOrLocale, "subview.invalidMode") };
  }

  for (const slot of ["A", "B"]) {
    if (!normalized.selections[slot]?.contigId) {
      return {
        ok: false,
        error: tAssembly(stateOrLocale, "subview.dualContigNeedsBothSlots"),
      };
    }
  }

  const slotA = normalized.selections.A;
  const slotB = normalized.selections.B;
  const primaryId = normalized.primaryDatasetId;
  const supportId = normalized.supportDatasetId;

  if (!primaryId || !supportId) {
    return { ok: false, error: tAssembly(stateOrLocale, "subview.requiresPrimaryAndSupport") };
  }

  const aIsPrimary = slotA?.datasetId === primaryId;
  const bIsSupport = slotB?.datasetId === supportId;
  if (!aIsPrimary || !bIsSupport) {
    return { ok: false, error: tAssembly(stateOrLocale, "subview.slotDatasetRule") };
  }

  if (primaryId === supportId) {
    return { ok: false, error: tAssembly(stateOrLocale, "subview.crossDatasetOnly") };
  }

  return {
    ok: true,
    value: {
      mode: normalized.mode,
      primaryDatasetId: primaryId,
      supportDatasetId: supportId,
      selections: normalized.selections,
      graphPairs: buildGraphPairs(),
    },
  };
}

export function buildSubviewRenderModel(input) {
  const validation = validateSubviewSelection(input);
  if (!validation.ok) {
    return validation;
  }

  const { mode, selections, primaryDatasetId, supportDatasetId, graphPairs } = validation.value;
  return {
    ok: true,
    value: {
      mode,
      primaryDatasetId,
      supportDatasetId,
      slots: {
        A: buildSlotSummary("A", selections.A, "primary"),
        B: buildSlotSummary("B", selections.B, "support"),
      },
      graphPairs: graphPairs.map((pair) => ({
        ...pair,
        leftContig: selections[pair.leftSlot],
        rightContig: selections[pair.rightSlot],
      })),
    },
  };
}

function normalizeInput(input) {
  const mode = String(input?.mode || "").trim();
  if (mode !== MODE_TWO) {
    return null;
  }

  return {
    mode,
    primaryDatasetId: normalizeId(input?.primaryDatasetId),
    supportDatasetId: normalizeId(input?.supportDatasetId),
    selections: {
      A: normalizeSelection(input?.selections?.A),
      B: normalizeSelection(input?.selections?.B),
    },
  };
}

function normalizeSelection(selection) {
  const contigId = normalizeId(selection?.contigId);
  const datasetId = normalizeId(selection?.datasetId);
  if (!contigId || !datasetId) {
    return null;
  }
  return {
    contigId,
    datasetId,
    contigName: String(selection?.contigName || `Ctg${contigId}`),
  };
}

function normalizeId(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return Math.trunc(parsed);
}

function buildGraphPairs() {
  return [
    {
      pairId: "AB",
      leftSlot: "A",
      rightSlot: "B",
      boundaryOnB: "left",
      renderable: true,
    },
  ];
}

function buildSlotSummary(slot, selection, datasetRole) {
  return {
    slot,
    datasetRole,
    contigId: selection.contigId,
    contigName: selection.contigName,
  };
}
