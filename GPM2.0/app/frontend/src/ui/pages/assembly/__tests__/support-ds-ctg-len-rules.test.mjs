import test from "node:test";
import assert from "node:assert/strict";
import {
  buildInitialSupportDsCtgLenRule,
  filterSupportCtgsBySupportDsCtgLenRules,
  hasAdvancedSupportDsCtgLenRules,
  normalizeSupportDsCtgLenRulesByChr,
  resolveEffectiveSupportDsCtgLenForCtg,
} from "../support-ds-ctg-len-rules.js";

test("resolveEffectiveSupportDsCtgLenForCtg uses largest non-overlapping ref coverage", () => {
  const rules = [
    { startBp: 1_000_000, endBp: 5_000_000, supportDsCtgLen: 100_000 },
    { startBp: 5_000_001, endBp: 10_000_000, supportDsCtgLen: 0 },
  ];
  const ctg = {
    hits: [
      { refStart: 1_100_000, refEnd: 1_180_000 },
      { refStart: 5_200_000, refEnd: 5_360_000 },
      { refStart: 5_250_000, refEnd: 5_400_000 },
    ],
  };

  assert.equal(resolveEffectiveSupportDsCtgLenForCtg(ctg, { rules, defaultSupportDsCtgLen: 50_000 }), 0);
});

test("resolveEffectiveSupportDsCtgLenForCtg breaks coverage ties with stricter threshold", () => {
  const rules = [
    { startBp: 1, endBp: 100, supportDsCtgLen: 10_000 },
    { startBp: 101, endBp: 200, supportDsCtgLen: 100_000 },
  ];
  const ctg = {
    hits: [
      { refStart: 1, refEnd: 50 },
      { refStart: 101, refEnd: 150 },
    ],
  };

  assert.equal(resolveEffectiveSupportDsCtgLenForCtg(ctg, { rules, defaultSupportDsCtgLen: 0 }), 100_000);
});

test("filterSupportCtgsBySupportDsCtgLenRules falls back to global threshold outside rules", () => {
  const rules = [{ startBp: 1, endBp: 100, supportDsCtgLen: 0 }];
  const ctgs = [
    { name: "in-rule", totalLength: 50, hits: [{ refStart: 10, refEnd: 20 }] },
    { name: "fallback-short", totalLength: 50, hits: [{ refStart: 200, refEnd: 250 }] },
    { name: "fallback-long", totalLength: 150, hits: [{ refStart: 200, refEnd: 250 }] },
  ];

  assert.deepEqual(
    filterSupportCtgsBySupportDsCtgLenRules(ctgs, { rules, defaultSupportDsCtgLen: 100 }).map((ctg) => ctg.name),
    ["in-rule", "fallback-long"],
  );
});

test("filterSupportCtgsBySupportDsCtgLenRules treats uncovered chr intervals as implicit zero rules", () => {
  const rules = [{ startBp: 1, endBp: 5_000_000, supportDsCtgLen: 10_000 }];
  const ctgs = [
    { name: "explicit-short", totalLength: 5_000, hits: [{ refStart: 1_000_000, refEnd: 1_020_000 }] },
    { name: "implicit-zero-short", totalLength: 5_000, hits: [{ refStart: 6_000_000, refEnd: 6_020_000 }] },
    {
      name: "implicit-zero-most-coverage",
      totalLength: 5_000,
      hits: [
        { refStart: 1_000_000, refEnd: 1_005_000 },
        { refStart: 6_000_000, refEnd: 6_020_000 },
      ],
    },
  ];

  assert.deepEqual(
    filterSupportCtgsBySupportDsCtgLenRules(ctgs, {
      rules,
      defaultSupportDsCtgLen: 100_000,
      chrLength: 10_000_000,
    }).map((ctg) => ctg.name),
    ["implicit-zero-short", "implicit-zero-most-coverage"],
  );
  assert.equal(resolveEffectiveSupportDsCtgLenForCtg(ctgs[1], {
    rules,
    defaultSupportDsCtgLen: 100_000,
    chrLength: 10_000_000,
  }), 0);
});

test("full chromosome single row is simple mode while multiple rows are advanced", () => {
  const initial = buildInitialSupportDsCtgLenRule({ chrLength: 1_000_000, supportDsCtgLen: 10_000 });
  assert.equal(hasAdvancedSupportDsCtgLenRules(initial, { chrLength: 1_000_000 }), false);
  assert.equal(
    hasAdvancedSupportDsCtgLenRules([
      { startBp: 1, endBp: 500_000, supportDsCtgLen: 10_000 },
      { startBp: 500_001, endBp: 1_000_000, supportDsCtgLen: 0 },
    ], { chrLength: 1_000_000 }),
    true,
  );
});

test("normalizeSupportDsCtgLenRulesByChr drops invalid rows and clips by chromosome length", () => {
  assert.deepEqual(
    normalizeSupportDsCtgLenRulesByChr({
      chr1: [
        { startBp: 50, endBp: 200, supportDsCtgLen: 1000 },
        { startBp: "bad", endBp: 20, supportDsCtgLen: 1000 },
      ],
    }, { chr1: 100 }),
    {
      chr1: [{ startBp: 50, endBp: 100, supportDsCtgLen: 1000 }],
    },
  );
});
