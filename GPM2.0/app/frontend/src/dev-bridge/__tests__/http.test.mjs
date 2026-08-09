import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";

import { createBackendBridgeMiddleware } from "../http.js";
import {
  createBackendBridgeRoutes,
  listBackendBridgeRouteGroups,
} from "../route-registry.js";

function createHandlers(overrides = {}) {
  return new Proxy(overrides, {
    get(target, property) {
      return target[property] || (async (payload) => ({ payload }));
    },
  });
}

function createRequest({ method = "POST", url = "/open-workspace", body } = {}) {
  const request = new EventEmitter();
  request.method = method;
  request.url = url;
  request.body = body;
  return request;
}

function createResponse() {
  let resolveEnded;
  const ended = new Promise((resolve) => {
    resolveEnded = resolve;
  });
  return {
    statusCode: 0,
    headers: {},
    body: "",
    ended,
    setHeader(name, value) {
      this.headers[name] = value;
    },
    end(body) {
      this.body = body;
      resolveEnded();
    },
  };
}

async function invokeMiddleware(middleware, requestOptions = {}) {
  const request = createRequest(requestOptions);
  const response = createResponse();
  const pending = middleware(request, response);
  if (requestOptions.body !== undefined) {
    request.emit("data", requestOptions.body);
  }
  request.emit("end");
  await pending;
  await response.ended;
  return {
    status: response.statusCode,
    headers: response.headers,
    body: JSON.parse(response.body),
  };
}

test("route registry exposes all dev bridge operations by functional domain", () => {
  const groups = listBackendBridgeRouteGroups();
  const routes = createBackendBridgeRoutes(createHandlers());

  assert.deepEqual(Object.keys(groups), ["imports", "workspace", "assembly", "audit", "runtime"]);
  assert.equal(routes.size, 36);
  assert.deepEqual(groups.imports, [
    "/import-zip",
    "/import-extracted",
    "/import-add-dataset-package",
  ]);
  assert.ok(groups.assembly.includes("/ctg-editor-action"));
  assert.equal(routes.get("POST /export-degap-jobs").group, "runtime");
});

test("middleware responds to ping without reading a request body", async () => {
  const middleware = createBackendBridgeMiddleware({
    backendExe: "C:/gpm/gpm_next_backend.exe",
    routes: createBackendBridgeRoutes(createHandlers()),
  });

  const response = await invokeMiddleware(middleware, { method: "GET", url: "/ping" });

  assert.equal(response.status, 200);
  assert.deepEqual(response.body, {
    ok: true,
    backendExe: "C:/gpm/gpm_next_backend.exe",
  });
});

test("middleware parses JSON and dispatches the matching route", async () => {
  let received = null;
  const routes = createBackendBridgeRoutes(
    createHandlers({
      openWorkspace: async (payload) => {
        received = payload;
        return { workspaceRoot: payload.workspaceRoot };
      },
    }),
  );
  const middleware = createBackendBridgeMiddleware({ backendExe: "backend.exe", routes });

  const response = await invokeMiddleware(middleware, {
    url: "/open-workspace",
    body: JSON.stringify({ workspaceRoot: "D:/workspace" }),
  });

  assert.equal(response.status, 200);
  assert.deepEqual(received, { workspaceRoot: "D:/workspace" });
  assert.deepEqual(response.body, { workspaceRoot: "D:/workspace" });
});

test("middleware returns stable envelopes for route and method misses", async () => {
  const middleware = createBackendBridgeMiddleware({
    backendExe: "backend.exe",
    routes: createBackendBridgeRoutes(createHandlers()),
  });

  const unknown = await invokeMiddleware(middleware, {
    url: "/does-not-exist",
    body: "{}",
  });
  const wrongMethod = await invokeMiddleware(middleware, {
    method: "GET",
    url: "/open-workspace",
  });

  assert.equal(unknown.status, 404);
  assert.equal(unknown.body.code, "DEV_BRIDGE_NOT_FOUND");
  assert.equal(unknown.body.operation, "POST /does-not-exist");
  assert.equal(wrongMethod.status, 405);
  assert.equal(wrongMethod.body.code, "DEV_BRIDGE_METHOD_NOT_ALLOWED");
  assert.equal(wrongMethod.body.error, wrongMethod.body.message);
});

test("middleware distinguishes malformed JSON from handler failures", async () => {
  const middleware = createBackendBridgeMiddleware({
    backendExe: "backend.exe",
    routes: createBackendBridgeRoutes(
      createHandlers({
        openWorkspace: async () => {
          throw new Error("backend unavailable");
        },
      }),
    ),
  });

  const malformed = await invokeMiddleware(middleware, {
    url: "/open-workspace",
    body: "{",
  });
  const failed = await invokeMiddleware(middleware, {
    url: "/open-workspace",
    body: "{}",
  });

  assert.equal(malformed.status, 400);
  assert.equal(malformed.body.code, "INVALID_JSON_BODY");
  assert.equal(failed.status, 500);
  assert.equal(failed.body.code, "RUNTIME_ERROR");
  assert.equal(failed.body.message, "backend unavailable");
});
