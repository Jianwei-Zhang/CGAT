import { normalizeTrackPrefInputValue } from "./track-prefs.js";

export const TRACK_NUMBER_INPUT_IDLE_MS = 600;

export function bindTrackNumberInput({
  input, field, key, registry, isCurrentScope, readValue, commitValue,
  setMenuOpen, closeOtherMenus, isMenuOpen,
  timerApi = globalThis.window || globalThis,
}) {
  if (!input) return;
  registry.get(key)?.destroy({ preserveExplicit: !input.readOnly });
  if (input.readOnly) { registry.delete(key); return; }
  const doc = input.ownerDocument || globalThis.document;
  const combo = input.closest("[data-track-combo-field]");
  const listeners = [];
  const documentListeners = [];
  let idleTimer = null;
  let explicitTimer = null;
  let composing = false;
  let pointerHeld = false;
  let pointerOutside = false;
  let disposed = false;
  let acceptedDraft = input.value;
  let acceptedSelection = [input.selectionStart, input.selectionEnd, input.selectionDirection];
  let selectionKey = "";
  const liveInput = () => (input.id && doc?.getElementById?.(input.id)) || input;
  const insideCombo = (target) => target === input || combo?.contains?.(target);
  const connected = () => input.isConnected !== false;
  const editable = () => isCurrentScope() && !input.readOnly && !input.disabled;
  const clearIdle = () => { if (idleTimer !== null) timerApi.clearTimeout(idleTimer); idleTimer = null; };
  const clearExplicit = () => { if (explicitTimer !== null) timerApi.clearTimeout(explicitTimer); explicitTimer = null; };
  const listen = (target, type, handler, options, bucket = listeners) => {
    target?.addEventListener?.(type, handler, options);
    bucket.push(() => target?.removeEventListener?.(type, handler, options));
  };
  const detachDocument = () => { documentListeners.splice(0).forEach(remove => remove()); };
  const validate = () => {
    const value = normalizeTrackPrefInputValue(field, input.value);
    input.setAttribute?.("aria-invalid", value === null ? "true" : "false");
    return value;
  };
  const rememberDraft = () => {
    acceptedDraft = input.value;
    acceptedSelection = [input.selectionStart, input.selectionEnd, input.selectionDirection];
  };
  const restoreSelection = (target, selection) => {
    if (!Number.isInteger(selection[0])) return;
    const length = target.value.length;
    target.setSelectionRange?.(Math.min(selection[0], length), Math.min(selection[1], length), selection[2]);
  };
  const apply = (reason, raw = input.value) => {
    clearIdle();
    clearExplicit();
    if (!editable() || composing) return;
    const value = normalizeTrackPrefInputValue(field, raw);
    if (reason === "idle" && value === null) return;
    const active = doc?.activeElement;
    const focus = active?.id && typeof active.value === "string" ? {
      id: active.id, value: active.value,
      selection: [active.selectionStart, active.selectionEnd, active.selectionDirection],
    } : null;
    const target = liveInput();
    target.value = String(value ?? readValue());
    target.setAttribute?.("aria-invalid", "false");
    if (value !== null && value !== readValue()) commitValue(value, target);
    // Scoped graph refreshes replace the toolbar too. Keep editing at the caret,
    // or preserve the other input the user just reached with Tab/a mouse click.
    if (focus) {
      const next = doc?.getElementById?.(focus.id);
      if (next && next !== active && !next.readOnly && !next.disabled) {
        if (focus.id !== input.id) next.value = focus.value;
        next.focus({ preventScroll: true });
        restoreSelection(next, focus.selection);
      }
    }
    if (reason !== "idle") setMenuOpen(false, liveInput());
    if (!disposed) { rememberDraft(); validate(); }
  };
  const activity = () => {
    clearIdle();
    if (disposed || !connected() || !editable() || composing || pointerHeld || pointerOutside) return;
    const value = validate();
    if (value === null || value === readValue()) return;
    idleTimer = timerApi.setTimeout(() => {
      idleTimer = null;
      if (!connected() || disposed || !editable()) { destroy(); return; }
      apply("idle");
    }, TRACK_NUMBER_INPUT_IDLE_MS);
  };
  const queueExplicit = () => {
    clearIdle();
    if (composing || pointerOutside || !editable()) return;
    clearExplicit();
    const draft = input.value;
    const previous = readValue();
    explicitTimer = timerApi.setTimeout(() => {
      explicitTimer = null;
      // A click may replace the control before this task runs. Consume only the
      // draft from that gesture, never overwrite a newer canonical value/scope.
      if (!editable() || readValue() !== previous) return;
      if (doc?.activeElement === input) input.blur?.();
      apply("blur", draft);
      detachDocument();
    }, 0);
  };
  const watchDocument = () => {
    if (documentListeners.length) return;
    listen(doc, "selectionchange", () => {
      if (doc.activeElement !== input) return;
      const next = JSON.stringify([input.value, input.selectionStart, input.selectionEnd, input.selectionDirection]);
      if (next === selectionKey) return;
      selectionKey = next;
      if (/^[0-9]*$/.test(input.value)) rememberDraft();
      activity();
    }, undefined, documentListeners);
    listen(doc, "pointerdown", event => {
      clearIdle();
      pointerHeld = true;
      pointerOutside = !insideCombo(event.target);
    }, true, documentListeners);
    listen(doc, "pointerup", () => {
      pointerHeld = false;
      if (pointerOutside) { pointerOutside = false; queueExplicit(); }
      else activity();
    }, true, documentListeners);
    listen(doc, "pointercancel", () => {
      pointerHeld = false;
      if (pointerOutside) { pointerOutside = false; queueExplicit(); }
      else activity();
    }, true, documentListeners);
    listen(doc, "click", event => {
      if (!insideCombo(event.target)) { pointerOutside = false; queueExplicit(); }
    }, true, documentListeners);
  };
  function destroy({ preserveExplicit = false } = {}) {
    disposed = true;
    clearIdle();
    if (!preserveExplicit) clearExplicit();
    detachDocument();
    listeners.splice(0).forEach(remove => remove());
    if (registry.get(key)?.destroy === destroy) registry.delete(key);
  }
  registry.set(key, { destroy });
  listen(input, "focus", () => {
    clearExplicit();
    pointerHeld = false;
    pointerOutside = false;
    watchDocument();
    closeOtherMenus(input);
    setMenuOpen(true, input);
    activity();
  });
  listen(input, "beforeinput", event => {
    if (composing || event.isComposing) return;
    rememberDraft();
    if (typeof event.data === "string" && /[^0-9]/.test(event.data)) {
      event.preventDefault();
      activity();
    }
  });
  listen(input, "paste", event => {
    const text = event.clipboardData?.getData("text");
    if (typeof text === "string" && /[^0-9]/.test(text)) { event.preventDefault(); activity(); }
  });
  const onInput = () => {
    if (composing) return;
    if (!/^[0-9]*$/.test(input.value)) {
      input.value = acceptedDraft;
      restoreSelection(input, acceptedSelection);
    } else rememberDraft();
    activity();
  };
  listen(input, "input", onInput);
  listen(input, "compositionstart", () => { rememberDraft(); composing = true; clearIdle(); });
  listen(input, "compositionend", () => { composing = false; onInput(); });
  listen(input, "select", activity);
  listen(input, "click", activity);
  listen(input, "change", queueExplicit);
  listen(input, "blur", () => {
    clearIdle();
    if (insideCombo(doc?.activeElement)) return;
    queueExplicit();
  });
  listen(input, "keydown", event => {
    if (composing || event.isComposing) return;
    if (event.key === "Enter") {
      event.preventDefault();
      apply("enter");
    } else if (event.key === "Escape") {
      event.preventDefault();
      clearIdle(); clearExplicit();
      input.value = String(readValue());
      rememberDraft(); validate();
      setMenuOpen(false, input);
    } else {
      if (event.key === "ArrowDown") {
        event.preventDefault(); closeOtherMenus(input); setMenuOpen(true, input);
      }
      activity();
    }
  });
  const toggle = combo?.querySelector("[data-track-combo-toggle]");
  listen(toggle, "pointerdown", event => event.preventDefault());
  listen(toggle, "click", event => {
    event.preventDefault();
    const open = !isMenuOpen(input);
    input.focus(); closeOtherMenus(input); setMenuOpen(open, input);
    activity();
  });
  combo?.querySelectorAll("[data-track-combo-option]").forEach(option => {
    listen(option, "pointerdown", event => {
      event.preventDefault();
      apply("option", option.dataset.trackComboValue);
      liveInput().focus(); setMenuOpen(false, liveInput());
    });
  });
  return { destroy };
}
