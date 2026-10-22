const BOUND = Symbol("supportDatasetPickerBound");

// Keep the existing select/change data contract; only the visible popup is custom.
export function bindSupportDatasetPicker({ select, setOpen, closeOthers }) {
  const combo = select?.closest?.('[data-track-combo-field="supportDatasetId"]');
  const toggle = combo?.querySelector("[data-track-combo-toggle]");
  const options = [...(combo?.querySelectorAll("[data-support-dataset-option]") || [])];
  if (!toggle || !options.length || combo[BOUND]) return;
  combo[BOUND] = true;
  const isOpen = () => combo.classList.contains("is-open");
  const activeIndex = () => Math.max(0, options.findIndex(option => option.dataset.supportDatasetOption === select.value));
  const sync = () => {
    const selected = options[activeIndex()];
    toggle.textContent = selected.textContent;
    toggle.title = selected.textContent;
    toggle.setAttribute("aria-label", `${toggle.dataset.supportDatasetLabel}: ${selected.textContent}`);
    options.forEach(option => {
      const active = option === selected;
      option.classList.toggle("is-active", active);
      option.setAttribute("aria-selected", String(active));
    });
  };
  const close = (restoreFocus = false) => {
    setOpen(combo, false);
    if (restoreFocus) toggle.focus();
  };
  const open = (index = activeIndex()) => {
    closeOthers(combo);
    setOpen(combo, true);
    options[index].focus();
  };
  toggle.addEventListener("click", event => {
    event.preventDefault();
    if (isOpen()) close();
    else open();
  });
  toggle.addEventListener("keydown", event => {
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      open(event.key === "Home" ? 0 : event.key === "End" ? options.length - 1 : activeIndex());
    } else if (event.key === "Escape") {
      event.preventDefault(); close();
    }
    // Enter/Space use the button's normal click behavior.
  });
  options.forEach((option, index) => {
    option.addEventListener("click", event => {
      event.preventDefault();
      const value = option.dataset.supportDatasetOption;
      const changed = select.value !== value;
      select.value = value;
      sync();
      close(true);
      if (changed) {
        const EventClass = select.ownerDocument?.defaultView?.Event || globalThis.Event;
        select.dispatchEvent(new EventClass("change", { bubbles: true }));
      }
    });
    option.addEventListener("keydown", event => {
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1
          : (index + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
        options[next].focus();
      } else if (event.key === "Escape") {
        event.preventDefault(); event.stopPropagation(); close(true);
      } else if (event.key === "Tab") {
        // Resume normal tab order at the trigger rather than inside a hidden list.
        close(true);
      }
    });
  });
  combo.addEventListener("focusout", event => {
    if (!combo.contains(event.relatedTarget)) close();
  });
  select.addEventListener("change", sync);
  sync();
}
