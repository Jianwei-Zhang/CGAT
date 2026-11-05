import { buildSubviewRenderDelta, SUBVIEW_RENDER_BATCH_SIZE } from "./subview-render-packet.js";

export function yieldSubviewRender() {
  if (typeof globalThis.scheduler?.postTask === "function") return globalThis.scheduler.postTask(() => {}, { priority: "user-visible" });
  if (typeof document === "undefined" || typeof MessageChannel !== "function") return new Promise(resolve => setTimeout(resolve, 0));
  return new Promise(resolve => {
    const channel = new MessageChannel();
    channel.port1.onmessage = () => { channel.port1.close(); channel.port2.close(); resolve(); };
    channel.port2.postMessage(null);
  });
}
export function disposeSubviewRenderPacket(packet) {
  for (const raster of packet?.rasters || []) raster.bitmap?.close?.();
}
export function createSubviewBackgroundRenderer({
  createWorker = () => new Worker(new URL("./subview-render-worker.js", import.meta.url), { type: "module" }),
  yieldTask = yieldSubviewRender,
} = {}) {
  let worker = null, lastState = null, current = null, nextId = 0;
  const cancel = () => {
    if (current) { current.cancelled = true; current.resolve?.(null); current = null; }
    worker?.terminate(); worker = null; lastState = null;
  };
  async function render(state, options, isCurrent) {
    // A newer local edit invalidates the old worker, including queued replies.
    if (current) cancel();
    const job = { id: ++nextId, cancelled: false };
    current = job;
    const valid = () => current === job && !job.cancelled && isCurrent();
    try {
      await yieldTask(); // pointerup returns before cloning or worker startup
      if (!valid()) return null;
      if (!worker) worker = createWorker();
      const response = new Promise((resolve, reject) => {
        job.resolve = resolve;
        worker.onmessage = event => {
          if (event.data?.id !== job.id || !valid()) { disposeSubviewRenderPacket(event.data?.packet); if (!valid()) resolve(null); return; }
          if (event.data.error) reject(new Error(event.data.error));
          else resolve(event.data.packet);
        };
        worker.onerror = event => { event.preventDefault?.(); reject(new Error(event.message || "Subview render worker failed")); };
        worker.onmessageerror = () => reject(new Error("Invalid subview render worker response"));
      });
      worker.postMessage({ id: job.id, delta: buildSubviewRenderDelta(state, lastState), ...options });
      lastState = state;
      const packet = await response;
      if (!valid()) { disposeSubviewRenderPacket(packet); return null; }
      return packet;
    } catch (error) {
      if (!valid()) return null;
      cancel(); throw error;
    } finally {
      if (current === job) current = null;
    }
  }
  return { render, cancel };
}

// Parsing each bounded batch yields to input, timers and the rest of the App.
// A sparse cover preserves the released plot while the new live SVG hydrates.
export async function prepareSubviewRenderPacket(document, packet, isCurrent, { yieldTask = yieldSubviewRender, onSkeleton = null } = {}) {
  if (!isCurrent()) return null;
  const template = document.createElement("template");
  template.innerHTML = packet.skeleton;
  const content = template.content;
  const slots = [...content.querySelectorAll("[data-subview-render-batch]")];
  if (slots.length !== packet.batches.length) throw new Error("Incomplete subview render packet");
  onSkeleton?.(content);
  for (let i = 0; i < slots.length; i++) {
    await yieldTask();
    if (!isCurrent()) return null;
    if (Number(slots[i].getAttribute("data-subview-render-batch")) !== i) throw new Error("Out-of-order subview render packet");
    slots[i].innerHTML = packet.batches[i];
    // Keep the identity <g> rather than reparenting every dense child a second
    // time. It changes neither coordinate systems nor endpoint ownership.
  }
  return isCurrent() ? content : null;
}

// Once the pointer gesture has ended, invisible inactive proxies can be
// retired in bounded tasks. The Canvas, bars and every active endpoint remain
// on screen; source evidence/history are never changed by this operation.
export async function retireSubviewDragProxies(scroll, isCurrent, { yieldTask = yieldSubviewRender, batchSize = SUBVIEW_RENDER_BATCH_SIZE } = {}) {
  const nodes = [...scroll.querySelectorAll(".track-collinearity-band, .subview-anchor-hit-zone:not(.is-active), .subview-anchor-line[stroke='transparent']:not(.is-active)")];
  for (let i = 0; i < nodes.length; i += batchSize) {
    await yieldTask();
    if (!isCurrent()) return false;
    for (const node of nodes.slice(i, i + batchSize)) node.remove();
  }
  return true;
}
