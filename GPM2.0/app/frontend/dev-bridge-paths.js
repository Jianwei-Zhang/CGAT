import path from "node:path";
import { fileURLToPath } from "node:url";

export function resolveRootDirFromFileUrl(fileUrl, pathModule = path) {
  const filePath = fileURLToPath(fileUrl, { windows: pathModule.sep === "\\" });
  return pathModule.normalize(pathModule.dirname(filePath));
}

export function resolveDefaultBackendExe(rootDir, pathModule = path) {
  return pathModule.resolve(rootDir, "../backend/target/debug/gpm_next_backend.exe");
}
