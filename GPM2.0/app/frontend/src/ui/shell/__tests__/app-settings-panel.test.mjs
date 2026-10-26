import test from "node:test";
import assert from "node:assert/strict";
import { APP_SETTINGS_COPY, renderSettingsContent } from "../app-settings-panel.js";
import { DEFAULT_APP_SETTINGS } from "../../../services/app-settings.js";

for (const locale of ["zh", "en"]) {
  test(`settings expose and select system/light/dark themes in ${locale}`, () => {
    for (const theme of ["system", "light", "dark"]) {
      const output = renderSettingsContent(locale, {...DEFAULT_APP_SETTINGS, theme});
      assert.match(output, /label for="settings-theme"/);
      assert.match(output, new RegExp(`<option value="${theme}" selected>`));
      assert.match(output, /name="theme"/);
    }
  });
}

for (const locale of ["zh", "en"]) {
  test(`history capacity defaults to unlimited in ${locale}`, () => {
    const output = renderSettingsContent(locale, DEFAULT_APP_SETTINGS);
    assert.match(output, /id="settings-history-input"[^>]+value="(?:不限步数|Unlimited)"/);
    assert.match(output, /<div id="settings-history-option-0" role="option" aria-selected="true" data-history-option="0">/);
    assert.match(output, /data-history-option="0">(?:不限步数|Unlimited)</);
    assert.match(output, /data-history-option="50">50 (?:步|steps)/);
  });

  test(`restoring defaults describes unlimited history in ${locale}`, () => {
    const copy = APP_SETTINGS_COPY[locale];
    assert.match(copy.restoreConfirm, locale === "zh" ? /恢复为不限步数/ : /return to unlimited/);
    assert.doesNotMatch(copy.restoreConfirm, locale === "zh" ? /恢复为 50 步/ : /return to 50 steps/);
  });
}
