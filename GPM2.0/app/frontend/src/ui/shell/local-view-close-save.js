// Tauri awaits onCloseRequested handlers. Let its normal close proceed only
// after the owner has drained task saves (including edits queued during a save),
// or the user explicitly agrees to discard changes after persistence fails.
export async function bindLocalViewCloseSave({ windowHandle, flush, onError = () => {}, confirmDiscard = async () => false }) {
  if (!windowHandle?.onCloseRequested) return () => {};
  let pending;
  return windowHandle.onCloseRequested(async event => {
    pending ||= Promise.resolve().then(flush).then(() => true, async error => {
      try { await onError(error); } catch { /* still offer an explicit escape */ }
      try { return await confirmDiscard(error) === true; }
      catch { return false; /* dialog failure must never discard unsaved work */ }
    }).finally(() => { pending = null; });
    if (!await pending) event.preventDefault();
  });
}
