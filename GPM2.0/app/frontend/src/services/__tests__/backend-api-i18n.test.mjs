import test from "node:test";
import assert from "node:assert/strict";

import {
  invokeCommand,
  pickSaveFilePath,
  pickDirectoryPath,
  pickZipFilePath,
} from "../backend-api.js";

test("backend-api preview fails closed without a DOM and keeps localized errors", async () => {
  const previousWindow = globalThis.window;
  const prompts = [];
  try {
    globalThis.window = {
      prompt(message) {
        prompts.push(message);
        throw new Error("Browser native prompts must not be used");
      },
    };

    await assert.rejects(invokeCommand("import_zip", {}, { locale: "en" }), (error) => {
      assert.match(error.message, /Browser preview cannot invoke backend command: import_zip/);
      assert.equal(error.code, "RUNTIME_ERROR");
      assert.equal(error.operation, "import_zip");
      return true;
    });
    assert.equal(await pickZipFilePath({ locale: "en" }), "");
    assert.equal(await pickDirectoryPath({ locale: "en" }), "");
    assert.equal(
      await pickSaveFilePath({
        defaultPath: "project1_Chr01_path.tsv",
      }, { locale: "en" }),
      "",
    );
    assert.deepEqual(prompts, []);
  } finally {
    globalThis.window = previousWindow;
  }
});
