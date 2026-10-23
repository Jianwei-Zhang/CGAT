// Intentionally process-memory only: restarting the app restores confirmations.
// Explicit action keys prevent consent for one operation bypassing another.
const skipped = new Set();
export const confirmationSkipped = (key) => Boolean(key && skipped.has(key));
export function rememberConfirmation(key) { if (key) skipped.add(key); }
export const confirmationSessionLabel = (locale) => locale === "en"
  ? "Do not ask again for this operation during this session"
  : "本次运行不再询问此类操作";
