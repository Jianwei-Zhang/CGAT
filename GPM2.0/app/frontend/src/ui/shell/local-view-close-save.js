// Tauri awaits onCloseRequested handlers. Let its normal close proceed only
// after the owner has drained task saves, including edits queued during a save.
export async function bindLocalViewCloseSave({ windowHandle, flush, onError = () => {} }) {
  if (!windowHandle?.onCloseRequested) return () => {};
  let pending;
  return windowHandle.onCloseRequested(async event => {
    pending ||= Promise.resolve().then(flush).then(() => true, async error => {
      try { await onError(error); } catch { /* save failure still keeps the window open */ }
      return false;
    }).finally(() => { pending = null; });
    if (!await pending) event.preventDefault();
  });
}
