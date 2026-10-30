import test from "node:test";
import assert from "node:assert/strict";
import { LGZ_NAME, LGZ_FULL_NAME } from "../../algorithm-names.js";
import { getMessages } from "../index.js";

function strings(value) {
  return Object.values(value).flatMap(item => typeof item === "string" ? [item] : strings(item));
}

test("LGZ has the exact public abbreviation and full name", () => {
  assert.equal(LGZ_NAME, "LGZ");
  assert.equal(LGZ_FULL_NAME, "Linking Inter-assembly Units for Genome Zipping");
});

for (const locale of ["en", "zh"]) {
  test(`${locale} public copy does not expose the retired name`, () => {
    for (const domain of ["assembly", "importer", "workspace", "shell", "projectPreview"]) {
      for (const text of strings(getMessages(locale, domain))) assert.doesNotMatch(text, /\bGRT\b/);
    }
  });

  test(`${locale} algorithm tooltips use the full name while compact source labels use LGZ`, () => {
    const copy = getMessages(locale, "assembly");
    const hints = [copy.page.finalPathRestoreGrtBaselineHint, copy.page.finalPathRestoreGrtBaselineCurrent,
      copy.grtResult.showResultHint, copy.subview.tools.anchorManager.grtReadOnly];
    for (const text of hints) {
      assert.equal(typeof text, "string");
      assert.ok(text.includes(LGZ_FULL_NAME), text);
      assert.doesNotMatch(text, /\bLGZ\b/);
    }
    assert.equal(copy.subview.tools.anchorManager.sourceGrt, LGZ_NAME);
  });
}
