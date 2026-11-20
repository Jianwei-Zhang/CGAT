// Local tasks minimize into the app task strip, not the OS iconic window state.
// Serialize hide/restore so delayed native calls cannot win over the last click.
export function createNativeSubviewVisibility({ handle, isCurrent, isMinimized, onError }) {
  let requested, sequence = 0, updating = false, pending = Promise.resolve(false);
  return {
    sync(force = false) {
      const minimized = Boolean(isMinimized());
      if (!isCurrent() || (requested === minimized && (!force || updating))) return pending;
      requested = minimized; updating = true;
      const request = ++sequence;
      const current = () => isCurrent() && request === sequence
        && Boolean(isMinimized()) === minimized;
      pending = pending.then(async () => {
        if (!current()) return false;
        if (minimized) {
          await handle.hide();
        } else {
          // Also recover a window minimized externally by the OS.
          await handle.unminimize();
          if (!current()) return false;
          await handle.show();
        }
        return current();
      }).catch(error => { if (current()) onError(error); return false; })
        .finally(() => { if (request === sequence) updating = false; });
      return pending;
    },
  };
}
