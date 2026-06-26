import test from "node:test";
import assert from "node:assert/strict";

import {
  invokeCommand,
  pickSaveFilePath,
  pickDirectoryPath,
  pickZipFilePath,
} from "../backend-api.js";

test("backend-api preview prompts and errors use english copy when locale is en", async () => {
  const previousWindow = globalThis.window;
  const prompts = [];
  try {
    globalThis.window = {
      prompt(message) {
        prompts.push(message);
        return "D:/tmp/input";
      },
    };

    await assert.rejects(
      invokeCommand("import_zip", {}, { locale: "en" }),
      /Browser preview cannot invoke backend command: import_zip/,
    );
    assert.equal(await pickZipFilePath({ locale: "en" }), "D:/tmp/input");
    assert.equal(await pickDirectoryPath({ locale: "en" }), "D:/tmp/input");
    assert.equal(
      await pickSaveFilePath({
        defaultPath: "project1_Chr01_path.tsv",
      }, { locale: "en" }),
      "D:/tmp/input",
    );
    assert.deepEqual(prompts, [
      "Enter the ZIP file path",
      "Enter the directory path",
      "project1_Chr01_path.tsv",
    ]);
  } finally {
    globalThis.window = previousWindow;
  }
});
