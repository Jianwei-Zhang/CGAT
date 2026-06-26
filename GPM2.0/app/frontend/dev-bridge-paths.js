import path from "node:path";
import { fileURLToPath } from "node:url";

export function resolveRootDirFromFileUrl(fileUrl, pathModule = path) {
  const pathname = decodeURIComponent(new URL(fileUrl).pathname);
  if (pathModule.sep === "\\" && /^\/[A-Za-z]:/.test(pathname)) {
    return pathModule.normalize(pathModule.dirname(pathname.slice(1)));
  }
  return pathModule.normalize(pathModule.dirname(fileURLToPath(fileUrl)));
}

export function resolveDefaultBackendExe(rootDir, pathModule = path) {
  return pathModule.resolve(rootDir, "../backend/target/debug/gpm_next_backend.exe");
}
