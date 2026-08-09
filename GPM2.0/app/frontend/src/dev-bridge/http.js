export class DevBridgeError extends Error {
  constructor(code, message, { status = 500, operation = "", data = null, cause } = {}) {
    super(message, cause ? { cause } : undefined);
    this.name = "DevBridgeError";
    this.code = code;
    this.status = status;
    this.operation = operation;
    this.data = data;
  }
}

export function createBackendBridgeMiddleware({ backendExe, routes }) {
  return async function backendBridgeMiddleware(req, res) {
    const method = String(req.method || "GET").toUpperCase();
    const url = new URL(req.url || "", "http://localhost");
    const operation = `${method} ${url.pathname}`;

    try {
      if (method === "GET" && url.pathname === "/ping") {
        sendJson(res, 200, { ok: true, backendExe });
        return;
      }

      const route = routes.get(operation);
      if (!route) {
        const knownPath = Array.from(routes.values()).some(
          (candidate) => candidate.pathname === url.pathname,
        );
        throw new DevBridgeError(
          knownPath ? "DEV_BRIDGE_METHOD_NOT_ALLOWED" : "DEV_BRIDGE_NOT_FOUND",
          knownPath
            ? `method ${method} is not allowed for ${url.pathname}`
            : `unknown dev bridge route: ${url.pathname}`,
          {
            status: knownPath ? 405 : 404,
            operation,
            data: { method, path: url.pathname },
          },
        );
      }

      const payload = await readJsonBody(req, operation);
      const result = await route.handler(payload);
      sendJson(res, 200, result);
    } catch (error) {
      const normalized = normalizeDevBridgeError(error, operation);
      sendJson(res, normalized.status, {
        error: normalized.message,
        code: normalized.code,
        message: normalized.message,
        operation: normalized.operation,
        data: normalized.data,
      });
    }
  };
}

export function readJsonBody(req, operation = "") {
  return new Promise((resolve, reject) => {
    let text = "";
    req.on("data", (chunk) => {
      text += chunk.toString();
    });
    req.on("end", () => {
      if (!text) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(text));
      } catch (error) {
        reject(
          new DevBridgeError("INVALID_JSON_BODY", `invalid json body: ${error.message}`, {
            status: 400,
            operation,
            cause: error,
          }),
        );
      }
    });
    req.on("error", (error) => {
      reject(
        new DevBridgeError("DEV_BRIDGE_REQUEST_ERROR", String(error?.message || error), {
          status: 400,
          operation,
          cause: error,
        }),
      );
    });
  });
}

export function sendJson(res, status, body) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.end(JSON.stringify(body));
}

export function normalizeDevBridgeError(error, operation = "") {
  if (error instanceof DevBridgeError) {
    return error;
  }
  return new DevBridgeError(
    typeof error?.code === "string" && error.code ? error.code : "RUNTIME_ERROR",
    String(error?.message || error || "dev bridge runtime error"),
    {
      status: Number.isInteger(error?.status) ? error.status : 500,
      operation,
      data: error?.data ?? null,
      cause: error,
    },
  );
}
