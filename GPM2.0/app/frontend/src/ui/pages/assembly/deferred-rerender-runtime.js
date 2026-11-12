export function createDeferredRerenderCoordinator(options = {}) {
  const request = typeof options?.requestAnimationFrame === "function"
    ? options.requestAnimationFrame
    : (typeof globalThis.requestAnimationFrame === "function"
      ? globalThis.requestAnimationFrame.bind(globalThis)
      : (callback) => globalThis.setTimeout(() => callback(Date.now()), 16));
  const cancel = typeof options?.cancelAnimationFrame === "function"
    ? options.cancelAnimationFrame
    : (typeof globalThis.cancelAnimationFrame === "function"
      ? globalThis.cancelAnimationFrame.bind(globalThis)
      : (token) => globalThis.clearTimeout(token));
  const rerender = typeof options?.rerender === "function" ? options.rerender : () => {};
  const rerenderSubviewPanel =
    typeof options?.rerenderSubviewPanel === "function"
      ? options.rerenderSubviewPanel
      : rerender;
  let frameToken = null;
  let pendingHost = null;
  let pendingStore = null;
  let pendingMode = "";

  const scheduleWithMode = (host, store, mode) => {
    pendingHost = host;
    pendingStore = store;
    if (mode === "full" || !pendingMode) {
      pendingMode = mode;
    }
    if (frameToken !== null) {
      return;
    }
    frameToken = request(() => {
      frameToken = null;
      const nextHost = pendingHost;
      const nextStore = pendingStore;
      const nextMode = pendingMode;
      pendingHost = null;
      pendingStore = null;
      pendingMode = "";
      // Main's context menu may start evidence loading before a Local window
      // has a DOM host. Its scoped store is the durable owner; the panel renderer
      // resolves the current window node instead of relying on that old host.
      const scopedSubview = nextMode === "subview-panel"
        && nextStore?.localViewRootStore && nextStore?.localViewWindowId;
      if (!nextStore || (!nextHost && !scopedSubview)
        || nextStore.isLocalViewAlive?.() === false
        || (scopedSubview && nextStore.getState().activeRoute !== "assembly")) {
        return;
      }
      if (nextMode === "subview-panel") {
        rerenderSubviewPanel(nextHost, nextStore);
        return;
      }
      rerender(nextHost, nextStore);
    });
  };

  return {
    schedule(host, store) {
      scheduleWithMode(host, store, "full");
    },
    scheduleSubviewPanel(host, store) {
      scheduleWithMode(host, store, "subview-panel");
    },
    cancel() {
      if (frameToken === null) {
        pendingHost = null;
        pendingStore = null;
        pendingMode = "";
        return false;
      }
      cancel(frameToken);
      frameToken = null;
      pendingHost = null;
      pendingStore = null;
      pendingMode = "";
      return true;
    },
  };
}
