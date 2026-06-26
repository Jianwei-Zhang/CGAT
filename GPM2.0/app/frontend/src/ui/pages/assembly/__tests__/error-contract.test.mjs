import test from "node:test";
import assert from "node:assert/strict";

import { mapAssemblyError } from "../error-contract.js";

test("maps missing or invalid parameters to Chinese-first message", () => {
  const mapped = mapAssemblyError({
    error: {
      code: "INVALID_PARAMS",
      message: "project_id must be provided",
    },
  });

  assert.equal(mapped.code, "INVALID_PARAMS");
  assert.equal(mapped.category, "invalid-params");
  assert.match(mapped.userMessage, /参数/);
});

test("maps object not found errors to Chinese-first message", () => {
  const mapped = mapAssemblyError({
    error: {
      message: "assembly_ctg_id 42 not found",
    },
  });

  assert.equal(mapped.category, "not-found");
  assert.match(mapped.userMessage, /未找到/);
});

test("maps current chromosome contig search miss to centralized Chinese-first message", () => {
  const mapped = mapAssemblyError({
    error: {
      code: "CURRENT_CHR_NO_MATCHING_CTG",
      message: "current chromosome search miss for keyword ctg-999",
    },
  });

  assert.equal(mapped.category, "current-chr-no-matching-ctg");
  assert.match(mapped.userMessage, /当前 Chr 未找到匹配的 contig/);
});

test("maps local assembly editor validation branches to centralized Chinese-first messages", () => {
  const splitName = mapAssemblyError({
    error: {
      code: "SPLIT_CTG_NAME_REQUIRED",
      message: "split ctg requires new name",
    },
  });
  const searchKeyword = mapAssemblyError({
    error: {
      code: "CTG_SEARCH_KEYWORD_REQUIRED",
      message: "ctg search keyword is required",
    },
  });
  const joinType = mapAssemblyError({
    error: {
      code: "INVALID_JOIN_TYPE",
      message: "join type is invalid",
    },
  });
  const joinGap = mapAssemblyError({
    error: {
      code: "GAP_SIZE_REQUIRED_FOR_JOIN_GAP",
      message: "gap size is required when join type is gap",
    },
  });
  const memberAction = mapAssemblyError({
    error: {
      code: "MISSING_MEMBER_ID_FOR_MEMBER_ACTION",
      message: "member id is required for member action",
    },
  });

  assert.equal(splitName.category, "generic");
  assert.match(splitName.userMessage, /装配操作失败|Assembly action failed/);
  assert.equal(searchKeyword.category, "ctg-search-keyword-required");
  assert.match(searchKeyword.userMessage, /请输入 contig 名称或 ID/);
  assert.equal(joinType.category, "invalid-params");
  assert.match(joinType.userMessage, /参数/);
  assert.equal(joinGap.category, "invalid-params");
  assert.match(joinGap.userMessage, /参数/);
  assert.equal(memberAction.category, "invalid-params");
  assert.match(memberAction.userMessage, /参数/);
});

test("maps state conflicts to Chinese-first message", () => {
  const mapped = mapAssemblyError({
    error: {
      code: "STATE_CONFLICT",
      message: "contig is already assigned to another chromosome",
    },
  });

  assert.equal(mapped.category, "state-conflict");
  assert.match(mapped.userMessage, /状态冲突|当前状态/);
});

test("maps support ds unavailable and selection errors to Chinese-first messages", () => {
  const unavailable = mapAssemblyError({
    error: {
      message: "companion project is unavailable",
    },
  });
  const notSelected = mapAssemblyError({
    error: {
      message: "companion project not selected",
    },
  });
  const noChr = mapAssemblyError({
    error: {
      message: "no matching chromosome in companion project for chr 1",
    },
  });

  assert.equal(unavailable.category, "support-ds-unavailable");
  assert.match(unavailable.userMessage, /辅 ds/);
  assert.equal(notSelected.category, "support-ds-not-selected");
  assert.match(notSelected.userMessage, /先选择/);
  assert.equal(noChr.category, "support-ds-no-matching-chr");
  assert.match(noChr.userMessage, /匹配的染色体/);
});

test("maps runtime bridge, tauri, and dev environment errors to Chinese-first messages", () => {
  const tauri = mapAssemblyError({
    error: {
      code: "TAURI_INVOKE_ERROR",
      message: "failed to invoke command run_ctg_editor_action",
    },
  });
  const bridge = mapAssemblyError({
    error: {
      message: "dev bridge error: 500",
    },
  });
  const fetchFailure = mapAssemblyError({
    error: new TypeError("Failed to fetch"),
  });

  assert.equal(tauri.category, "runtime");
  assert.match(tauri.userMessage, /运行环境|后端/);
  assert.equal(bridge.category, "runtime");
  assert.match(bridge.userMessage, /开发环境|后端/);
  assert.equal(fetchFailure.category, "runtime");
  assert.match(fetchFailure.userMessage, /运行环境|连接/);
});

test("maps tauri-wrapped backend validation errors before runtime fallback", () => {
  const mapped = mapAssemblyError({
    error: {
      code: "TAURI_INVOKE_ERROR",
      message: "maximumExtensionLength is not a valid integer",
    },
  });

  assert.equal(mapped.category, "invalid-params");
  assert.match(mapped.userMessage, /参数/);
});
