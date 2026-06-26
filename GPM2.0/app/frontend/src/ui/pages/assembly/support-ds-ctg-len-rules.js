import { normalizeNonNegativeInt, normalizePositiveInt } from "./track-prefs.js";

export function normalizeSupportDsCtgLenRules(rules, { chrLength = null } = {}) {
  const resolvedChrLength = normalizePositiveInt(chrLength);
  if (!Array.isArray(rules)) {
    return [];
  }
  return rules
    .map((rule) => {
      const rawStart = normalizePositiveInt(rule?.startBp ?? rule?.refStartBp ?? rule?.start);
      const rawEnd = normalizePositiveInt(rule?.endBp ?? rule?.refEndBp ?? rule?.end);
      const supportDsCtgLen = normalizeNonNegativeInt(
        rule?.supportDsCtgLen ?? rule?.supportDsCtgLenBp ?? rule?.lenBp,
      );
      if (rawStart === null || rawEnd === null || supportDsCtgLen === null) {
        return null;
      }
      const startBp = Math.min(rawStart, rawEnd);
      const endBp = Math.max(rawStart, rawEnd);
      const clippedStartBp = resolvedChrLength ? Math.min(startBp, resolvedChrLength) : startBp;
      const clippedEndBp = resolvedChrLength ? Math.min(endBp, resolvedChrLength) : endBp;
      if (clippedEndBp < 1 || clippedStartBp > clippedEndBp) {
        return null;
      }
      return {
        startBp: Math.max(1, clippedStartBp),
        endBp: clippedEndBp,
        supportDsCtgLen,
      };
    })
    .filter(Boolean)
    .sort((left, right) => left.startBp - right.startBp || left.endBp - right.endBp);
}

export function normalizeSupportDsCtgLenRulesByChr(source, chrLengthsByName = {}) {
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    return {};
  }
  const result = {};
  Object.entries(source).forEach(([chrName, rules]) => {
    const normalizedChrName = String(chrName || "").trim();
    if (!normalizedChrName) {
      return;
    }
    const normalizedRules = normalizeSupportDsCtgLenRules(rules, {
      chrLength: chrLengthsByName[normalizedChrName],
    });
    if (normalizedRules.length) {
      result[normalizedChrName] = normalizedRules;
    }
  });
  return result;
}

export function buildChrLengthsByName(chromosomes) {
  const result = {};
  if (!Array.isArray(chromosomes)) {
    return result;
  }
  chromosomes.forEach((chromosome) => {
    const chrName = String(chromosome?.chrName || "").trim();
    const chrLength = normalizePositiveInt(chromosome?.chrLength ?? chromosome?.lengthBp);
    if (chrName && chrLength) {
      result[chrName] = chrLength;
    }
  });
  return result;
}

export function getSupportDsCtgLenRulesForChr(rulesByChr, chrName, { chrLength = null } = {}) {
  const normalizedChrName = String(chrName || "").trim();
  if (!normalizedChrName || !rulesByChr || typeof rulesByChr !== "object" || Array.isArray(rulesByChr)) {
    return [];
  }
  return normalizeSupportDsCtgLenRules(rulesByChr[normalizedChrName], { chrLength });
}

export function buildInitialSupportDsCtgLenRule({ chrLength, supportDsCtgLen }) {
  const resolvedChrLength = normalizePositiveInt(chrLength) ?? 1;
  return [{
    startBp: 1,
    endBp: resolvedChrLength,
    supportDsCtgLen: normalizeNonNegativeInt(supportDsCtgLen) ?? 0,
  }];
}

export function isSingleFullChrSupportDsCtgLenRule(rules, { chrLength = null } = {}) {
  const normalized = normalizeSupportDsCtgLenRules(rules, { chrLength });
  const resolvedChrLength = normalizePositiveInt(chrLength);
  if (!resolvedChrLength || normalized.length !== 1) {
    return false;
  }
  return normalized[0].startBp <= 1 && normalized[0].endBp >= resolvedChrLength;
}

export function hasAdvancedSupportDsCtgLenRules(rules, { chrLength = null } = {}) {
  const normalized = normalizeSupportDsCtgLenRules(rules, { chrLength });
  if (!normalized.length) {
    return false;
  }
  return !isSingleFullChrSupportDsCtgLenRule(normalized, { chrLength });
}

export function resolveEffectiveSupportDsCtgLenForCtg(ctg, {
  rules = [],
  defaultSupportDsCtgLen = 0,
  chrLength = null,
} = {}) {
  const fallback = Math.max(0, normalizeNonNegativeInt(defaultSupportDsCtgLen) ?? 0);
  const normalizedRules = buildResolutionSupportDsCtgLenRules(rules, { chrLength });
  if (!normalizedRules.length) {
    return fallback;
  }
  const coverageByRule = normalizedRules.map((rule) => ({
    rule,
    intervals: [],
  }));
  const hits = Array.isArray(ctg?.hits) ? ctg.hits : [];
  hits.forEach((hit) => {
    const hitStart = normalizePositiveInt(hit?.refStart ?? hit?.ref_start ?? hit?.referenceStart);
    const hitEnd = normalizePositiveInt(hit?.refEnd ?? hit?.ref_end ?? hit?.referenceEnd);
    if (hitStart === null || hitEnd === null) {
      return;
    }
    const refStart = Math.min(hitStart, hitEnd);
    const refEnd = Math.max(hitStart, hitEnd);
    coverageByRule.forEach((entry) => {
      const startBp = Math.max(refStart, entry.rule.startBp);
      const endBp = Math.min(refEnd, entry.rule.endBp);
      if (startBp <= endBp) {
        entry.intervals.push([startBp, endBp]);
      }
    });
  });
  let bestCoverage = 0;
  let bestSupportDsCtgLen = fallback;
  coverageByRule.forEach((entry) => {
    const coverage = sumMergedIntervals(entry.intervals);
    if (
      coverage > bestCoverage
      || (coverage === bestCoverage && coverage > 0 && entry.rule.supportDsCtgLen > bestSupportDsCtgLen)
    ) {
      bestCoverage = coverage;
      bestSupportDsCtgLen = entry.rule.supportDsCtgLen;
    }
  });
  return bestCoverage > 0 ? bestSupportDsCtgLen : fallback;
}

export function filterSupportCtgsBySupportDsCtgLenRules(ctgs, {
  rules = [],
  defaultSupportDsCtgLen = 0,
  chrLength = null,
} = {}) {
  const items = Array.isArray(ctgs) ? ctgs : [];
  return items.filter((ctg) => {
    const effectiveLen = resolveEffectiveSupportDsCtgLenForCtg(ctg, {
      rules,
      defaultSupportDsCtgLen,
      chrLength,
    });
    if (effectiveLen <= 0) {
      return true;
    }
    const totalLength = Math.max(0, normalizeNonNegativeInt(ctg?.totalLength ?? ctg?.lengthBp) ?? 0);
    return totalLength >= effectiveLen;
  });
}

function buildResolutionSupportDsCtgLenRules(rules, { chrLength = null } = {}) {
  const resolvedChrLength = normalizePositiveInt(chrLength);
  const normalizedRules = normalizeSupportDsCtgLenRules(rules, { chrLength: resolvedChrLength });
  if (!resolvedChrLength || !normalizedRules.length) {
    return normalizedRules;
  }
  const completed = [];
  let nextStartBp = 1;
  normalizedRules.forEach((rule) => {
    if (nextStartBp < rule.startBp) {
      completed.push({
        startBp: nextStartBp,
        endBp: rule.startBp - 1,
        supportDsCtgLen: 0,
      });
    }
    completed.push(rule);
    nextStartBp = Math.max(nextStartBp, rule.endBp + 1);
  });
  if (nextStartBp <= resolvedChrLength) {
    completed.push({
      startBp: nextStartBp,
      endBp: resolvedChrLength,
      supportDsCtgLen: 0,
    });
  }
  return completed;
}

function sumMergedIntervals(intervals) {
  if (!Array.isArray(intervals) || !intervals.length) {
    return 0;
  }
  const sorted = intervals
    .map(([start, end]) => [normalizePositiveInt(start), normalizePositiveInt(end)])
    .filter(([start, end]) => start !== null && end !== null)
    .map(([start, end]) => [Math.min(start, end), Math.max(start, end)])
    .sort((left, right) => left[0] - right[0] || left[1] - right[1]);
  let total = 0;
  let currentStart = null;
  let currentEnd = null;
  sorted.forEach(([start, end]) => {
    if (currentStart === null) {
      currentStart = start;
      currentEnd = end;
      return;
    }
    if (start <= currentEnd + 1) {
      currentEnd = Math.max(currentEnd, end);
      return;
    }
    total += currentEnd - currentStart + 1;
    currentStart = start;
    currentEnd = end;
  });
  if (currentStart !== null) {
    total += currentEnd - currentStart + 1;
  }
  return total;
}
