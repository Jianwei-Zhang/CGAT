import test from "node:test";
import assert from "node:assert/strict";

import { importExtractedBundle, importZipBundle } from "../workflow-api.js";

test("workflow-api mock import stages and summaries use english copy when locale is en", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {};

    const zipStages = [];
    const zipResult = await importZipBundle({
      zipPath: "D:/drop/input.zip",
      workspaceRoot: "D:/ws/demo",
      onStage: (stage) => zipStages.push(stage),
      stateOrLocale: { locale: "en" },
    });

    assert.deepEqual(zipStages, [
      "Validate ZIP path and project area parameters",
      "Extract the bundle and inspect the gpm_server delivery structure",
      "Create the project area and generate project.sqlite",
    ]);
    assert.equal(
      zipResult.message,
      "Import completed (browser preview mock): D:/drop/input.zip -> D:/ws/demo.",
    );

    const extractedStages = [];
    const extractedResult = await importExtractedBundle({
      extractedPath: "D:/drops/gpm_server",
      onStage: (stage) => extractedStages.push(stage),
      stateOrLocale: "en",
    });

    assert.deepEqual(extractedStages, [
      "Validate the extracted bundle structure",
      "Locate gpm_server and use it as the project area root",
    ]);
    assert.equal(
      extractedResult.message,
      "Import completed (browser preview mock): D:/drops/gpm_server",
    );
  } finally {
    globalThis.window = previousWindow;
  }
});
