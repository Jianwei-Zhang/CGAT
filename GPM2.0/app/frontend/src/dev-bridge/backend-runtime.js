import { spawn } from "node:child_process";
import path from "node:path";

import { resolveDefaultBackendExe, resolveRootDirFromFileUrl } from "../../dev-bridge-paths.js";

export function resolveBackendRuntime({
  fileUrl = import.meta.url,
  backendExe = process.env.GPM_NEXT_BACKEND_EXE,
  spawnProcess = spawn,
} = {}) {
  const sourceDir = resolveRootDirFromFileUrl(fileUrl);
  const frontendRoot = path.resolve(sourceDir, "../..");
  const resolvedBackendExe = backendExe || resolveDefaultBackendExe(frontendRoot);

  return {
    backendExe: resolvedBackendExe,
    runBackend(args) {
      return runBackendCommand({
        args,
        backendExe: resolvedBackendExe,
        cwd: path.resolve(frontendRoot, ".."),
        spawnProcess,
      });
    },
  };
}

export function runBackendCommand({ args, backendExe, cwd, spawnProcess = spawn, env = process.env }) {
  return new Promise((resolve, reject) => {
    const child = spawnProcess(backendExe, args, {
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...env },
    });
    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(
            `backend command failed (code=${code})\nargs=${args.join(" ")}\n${stderr || stdout}`,
          ),
        );
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}
