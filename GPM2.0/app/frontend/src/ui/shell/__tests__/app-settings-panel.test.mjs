import test from "node:test";
import assert from "node:assert/strict";
import { renderSettingsContent } from "../app-settings-panel.js";
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
