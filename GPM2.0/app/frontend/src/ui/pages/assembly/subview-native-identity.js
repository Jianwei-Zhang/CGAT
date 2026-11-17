// A popup must never operate on Main even if a WebKit configuration inherits
// its opener's Tauri initialization scripts. Validate before installing handlers
// or calling native geometry/close APIs, including failure cleanup.
export function getNativeSubviewHandle(peer, id, token) {
  const handle = peer?.__TAURI__?.window?.getCurrentWindow?.();
  if (!id || !token || handle?.label !== `local-view-${id}--${token}`)
    throw new Error("Local View native window identity mismatch");
  return handle;
}

export async function destroyNativeSubviewPeer(peer, id, token) {
  let handle;
  try { handle = getNativeSubviewHandle(peer, id, token); }
  catch { return false; } // The owner can clean up by its validated native label.
  await handle.destroy();
  return true;
}
