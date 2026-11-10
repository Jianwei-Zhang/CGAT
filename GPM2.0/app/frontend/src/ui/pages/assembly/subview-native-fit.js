// Initial native geometry is a view preference, never project/genome state.
// Measure the natural panel, not the flex container stretched to the old 560px.
export function measureNativeSubviewHeight(node) {
  const panel = node?.querySelector?.("[data-subview-panel]");
  if (!panel) return null;
  const panelRect = panel.getBoundingClientRect();
  const rootRect = node.getBoundingClientRect();
  if (!(panelRect.height > 0) || !Number.isFinite(panelRect.bottom - rootRect.top)) return null;
  const scrollTop = Number(node.querySelector(".subview-window-content")?.scrollTop || 0);
  return Math.ceil(panelRect.bottom - rootRect.top + scrollTop + 6);
}

export function resolveNativeSubviewFit({ height, innerSize, outerSize, position, scale, area }) {
  if (!(Number.isFinite(height) && height > 0 && Number.isFinite(scale) && scale > 0)) return null;
  const frameWidth = Math.max(0, outerSize.width - innerSize.width);
  const frameHeight = Math.max(0, outerSize.height - innerSize.height);
  const margin = Math.round(16 * scale);
  const widthLimit = Math.max(480 * scale, area.size.width - frameWidth - margin * 2);
  const heightLimit = Math.max(220 * scale, area.size.height - frameHeight - margin * 2);
  const width = Math.round(Math.min(innerSize.width, widthLimit));
  const fittedHeight = Math.ceil(Math.min(Math.max(220 * scale, height * scale), heightLimit));
  const x = Math.round(Math.max(area.position.x + margin,
    Math.min(position.x, area.position.x + area.size.width - width - frameWidth - margin)));
  const y = Math.round(Math.max(area.position.y + margin,
    Math.min(position.y, area.position.y + area.size.height - fittedHeight - frameHeight - margin)));
  return { width, height: fittedHeight, x, y };
}

export async function fitNativeSubviewWindow(node, handle, canFit = () => true) {
  const peer = node.ownerDocument.defaultView;
  const monitorApi = peer.__TAURI__.window;
  const [innerSize, outerSize, position, scale, monitor] = await Promise.all([
    handle.innerSize(), handle.outerSize(), handle.outerPosition(), handle.scaleFactor(),
    monitorApi.currentMonitor?.().catch(() => null),
  ]);
  if (!canFit()) return null;
  const screen = peer.screen;
  const area = monitor?.workArea || (monitor && { position: monitor.position, size: monitor.size }) || {
    position: { x: (screen?.availLeft || 0) * scale, y: (screen?.availTop || 0) * scale },
    size: { width: (screen?.availWidth || 1280) * scale, height: (screen?.availHeight || 800) * scale },
  };
  const options = { innerSize, outerSize, position, scale, area };
  let fit = resolveNativeSubviewFit({ ...options, height: measureNativeSubviewHeight(node) });
  if (!fit) return null;
  if (fit.width !== innerSize.width) {
    // A narrower screen can wrap controls. Apply width first, then measure the
    // resulting rows; a hidden WebView need not deliver requestAnimationFrame.
    await handle.setSize(new peer.__TAURI__.dpi.PhysicalSize(fit.width, innerSize.height));
    await new Promise(resolve => peer.setTimeout(resolve, 0));
    if (!canFit()) return null;
    fit = resolveNativeSubviewFit({ ...options, height: measureNativeSubviewHeight(node) });
    if (!fit) return null;
  }
  if (!canFit()) return null;
  if (fit.width !== innerSize.width || fit.height !== innerSize.height)
    await handle.setSize(new peer.__TAURI__.dpi.PhysicalSize(fit.width, fit.height));
  if (!canFit()) return null;
  if (fit.x !== position.x || fit.y !== position.y)
    await handle.setPosition(new peer.__TAURI__.dpi.PhysicalPosition(fit.x, fit.y));
  return fit;
}
