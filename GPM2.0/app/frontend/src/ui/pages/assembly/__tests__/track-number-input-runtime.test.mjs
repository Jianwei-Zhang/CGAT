import test from "node:test";
import assert from "node:assert/strict";
import { bindTrackNumberInput, TRACK_NUMBER_INPUT_IDLE_MS } from "../track-number-input-runtime.js";

class Events {
  handlers = new Map();
  addEventListener(type, handler) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type).add(handler);
  }
  removeEventListener(type, handler) { this.handlers.get(type)?.delete(handler); }
  emit(type, details = {}) {
    const event = { target: this, preventDefault() { this.defaultPrevented = true; }, ...details };
    [...this.handlers.get(type) || []].forEach(handler => handler(event));
    return event;
  }
}

function createClock() {
  let now = 0;
  let id = 0;
  const jobs = new Map();
  return {
    setTimeout(fn, delay) { jobs.set(++id, { fn, at: now + delay }); return id; },
    clearTimeout(key) { jobs.delete(key); },
    tick(ms) {
      const end = now + ms;
      for (;;) {
        const next = [...jobs].filter(([, job]) => job.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!next) break;
        now = next[1].at; jobs.delete(next[0]); next[1].fn();
      }
      now = end;
    },
  };
}

function setup({ field = "alignmentLength", initial = 10000 } = {}) {
  const doc = new Events();
  const nodes = new Map();
  doc.getElementById = id => nodes.get(id);
  const clock = createClock();
  const registry = new Map();
  const commits = [];
  let value = initial;
  let current = true;
  let onCommit = () => {};
  const makeInput = (id = "test-input") => {
    const input = new Events();
    const toggle = new Events();
    const option = new Events();
    option.dataset = { trackComboValue: "50000" };
    const combo = {
      contains: node => [input, toggle, option].includes(node),
      querySelector: () => toggle,
      querySelectorAll: () => [option],
    };
    Object.assign(input, { id, ownerDocument: doc, value: String(value), isConnected: true,
      selectionStart: 0, selectionEnd: 0, selectionDirection: "none", attributes: {},
      closest: () => combo,
      setAttribute(key, val) { this.attributes[key] = val; },
      setCustomValidity(message) { this.validityMessage = message; },
      setSelectionRange(start, end, direction = "none") {
        this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction;
      },
      focus() {
        if (doc.activeElement === this) return;
        const previous = doc.activeElement;
        doc.activeElement = this;
        previous?.emit("blur"); this.emit("focus");
      },
      blur() {
        if (doc.activeElement !== this) return;
        doc.activeElement = null; this.emit("blur");
      },
    });
    nodes.set(id, input);
    return { input, toggle, option };
  };
  const bind = input => bindTrackNumberInput({ input, field, key: field, registry,
    timerApi: clock, isCurrentScope: () => current, readValue: () => value,
    commitValue(next) { value = next; commits.push(next); onCommit(); },
    setMenuOpen(open, target) { target.menuOpen = open; },
    closeOtherMenus() {}, isMenuOpen: target => target.menuOpen,
  });
  const controls = makeInput();
  bind(controls.input);
  const edit = (draft, input = controls.input) => {
    input.emit("beforeinput", { data: null });
    input.value = draft; input.setSelectionRange(draft.length, draft.length); input.emit("input");
  };
  const replace = () => {
    controls.input.isConnected = false;
    const next = makeInput().input;
    bind(next);
    return next;
  };
  return { ...controls, clock, doc, registry, commits, edit, bind, replace, makeInput,
    setCurrent(next) { current = next; }, setOnCommit(fn) { onCommit = fn; },
  };
}

test("idle application restarts on editing, arrow keys and actual caret/selection changes", () => {
  const h = setup(); h.input.focus(); h.edit("20000");
  h.clock.tick(500); h.input.emit("keydown", { key: "ArrowLeft" });
  h.clock.tick(500);
  h.input.setSelectionRange(2, 2); h.doc.emit("selectionchange");
  h.clock.tick(500);
  h.input.setSelectionRange(1, 3); h.doc.emit("selectionchange");
  h.clock.tick(TRACK_NUMBER_INPUT_IDLE_MS - 1);
  assert.deepEqual(h.commits, []);
  h.clock.tick(1); assert.deepEqual(h.commits, [20000]);
  h.input.emit("select"); h.clock.tick(2000);
  assert.deepEqual(h.commits, [20000]);
});

test("Enter, change and blur consume a draft only once; Escape discards it", () => {
  const h = setup(); h.input.focus(); h.edit("20000");
  h.input.emit("keydown", { key: "Enter" });
  h.input.emit("change"); h.input.blur(); h.clock.tick(2000);
  assert.deepEqual(h.commits, [20000]);
  h.input.focus(); h.edit("30000"); h.input.emit("keydown", { key: "Escape" });
  h.clock.tick(2000); assert.equal(h.input.value, "20000");
  assert.deepEqual(h.commits, [20000]);
});

test("holding the pointer while selecting text pauses auto-apply until release", () => {
  const h = setup(); h.input.focus(); h.edit("20000");
  h.doc.emit("pointerdown", { target: h.input });
  h.input.setSelectionRange(1, 4); h.doc.emit("selectionchange");
  h.clock.tick(2000); assert.deepEqual(h.commits, []);
  h.doc.emit("pointerup", { target: h.input });
  h.clock.tick(TRACK_NUMBER_INPUT_IDLE_MS - 1); assert.deepEqual(h.commits, []);
  h.clock.tick(1); assert.deepEqual(h.commits, [20000]);
});

test("outside pointer gestures commit after the clicked action even when it prevents blur", () => {
  const h = setup(); h.input.focus(); h.edit("20000");
  const outside = {};
  h.doc.emit("pointerdown", { target: outside });
  h.clock.tick(2000); assert.deepEqual(h.commits, []);
  h.doc.emit("pointerup", { target: outside }); h.doc.emit("click", { target: outside });
  assert.deepEqual(h.commits, [], "the clicked action runs before the refresh");
  h.clock.tick(0); assert.deepEqual(h.commits, [20000]);
  assert.notEqual(h.doc.activeElement, h.input);
});

test("Tab/blur applies without Enter and restores focus and draft in the next refreshed input", () => {
  const h = setup(); h.input.focus(); h.edit("20000");
  const second = h.makeInput("second").input;
  second.value = "123"; second.setSelectionRange(1, 2);
  h.setOnCommit(() => {
    h.replace(); h.makeInput("second");
  });
  second.focus(); h.clock.tick(0);
  assert.deepEqual(h.commits, [20000]);
  assert.equal(h.doc.activeElement.id, "second");
  assert.equal(h.doc.activeElement.value, "123");
  assert.equal(h.doc.activeElement.selectionStart, 1);
  assert.equal(h.doc.activeElement.selectionEnd, 2);
});

test("auto-apply retains focused input and caret across a synchronous toolbar replacement", () => {
  const h = setup(); h.input.focus(); h.edit("20000"); h.input.setSelectionRange(2, 4, "backward");
  h.setOnCommit(() => h.replace()); h.clock.tick(TRACK_NUMBER_INPUT_IDLE_MS);
  assert.deepEqual(h.commits, [20000]);
  assert.notEqual(h.doc.activeElement, h.input);
  assert.equal(h.doc.activeElement.value, "20000");
  assert.equal(h.doc.activeElement.selectionStart, 2);
  assert.equal(h.doc.activeElement.selectionEnd, 4);
  assert.equal(h.doc.activeElement.selectionDirection, "backward");
});

test("dropdown pointer selection replaces the draft and does not double-apply", () => {
  const h = setup(); h.input.focus(); h.edit("20000");
  h.option.emit("pointerdown"); h.clock.tick(2000);
  assert.deepEqual(h.commits, [50000]);
  assert.equal(h.input.value, "50000"); assert.equal(h.input.menuOpen, false);
});

test("reject invalid typing and paste as whole tokens, including fallback input events", () => {
  const h = setup(); h.input.focus();
  assert.equal(h.input.emit("beforeinput", { data: "e" }).defaultPrevented, true);
  assert.equal(h.input.emit("paste", { clipboardData: { getData: () => "12bp" } }).defaultPrevented, true);
  h.edit("100e2"); assert.equal(h.input.value, "10000");
  h.clock.tick(2000); assert.deepEqual(h.commits, []);
});

test("empty, unsafe and range-invalid drafts stay uncommitted and restore on explicit submission", () => {
  for (const [field, invalid] of [["alignmentLength", ""], ["maxTickCount", "0"], ["mapq", "256"], ["minTickUnitKb", "9007199254740992"]]) {
    const h = setup({ field, initial: 10 }); h.input.focus(); h.edit(invalid);
    h.clock.tick(2000); assert.deepEqual(h.commits, []);
    assert.equal(h.input.attributes["aria-invalid"], "true");
    h.input.blur(); h.clock.tick(0);
    assert.equal(h.input.value, "10"); assert.equal(h.input.attributes["aria-invalid"], "false");
    assert.deepEqual(h.commits, []);
  }
});

test("IME drafts never commit during composition and nonnumeric composition is rejected", () => {
  const h = setup(); h.input.focus();
  h.input.emit("compositionstart"); h.edit("20000");
  h.input.emit("keydown", { key: "Enter", isComposing: true });
  h.clock.tick(2000); assert.deepEqual(h.commits, []);
  h.input.emit("compositionend"); h.clock.tick(TRACK_NUMBER_INPUT_IDLE_MS);
  assert.deepEqual(h.commits, [20000]);
  h.input.emit("compositionstart"); h.input.value = "中文"; h.input.emit("input");
  h.input.emit("beforeinput", { data: "文", isComposing: true });
  h.input.value = "中文字符"; h.input.emit("input");
  h.input.emit("compositionend"); assert.equal(h.input.value, "20000");
});

test("rebind and scope disposal cancel stale idle drafts; read-only controls remain inert", () => {
  const h = setup(); h.input.focus(); h.edit("20000");
  const next = h.replace(); h.clock.tick(2000); assert.deepEqual(h.commits, []);
  next.focus(); h.edit("30000", next); h.setCurrent(false);
  h.clock.tick(2000); assert.deepEqual(h.commits, []);
  const readonly = h.makeInput().input; readonly.readOnly = true; h.bind(readonly);
  readonly.focus(); h.edit("40000", readonly); h.clock.tick(2000);
  assert.equal(h.registry.size, 0); assert.deepEqual(h.commits, []);
});

test("a pending outside-click draft survives same-scope refresh but is dropped on scope change", () => {
  for (const changeScope of [false, true]) {
    const h = setup(); h.input.focus(); h.edit("20000");
    h.doc.emit("click", { target: {} });
    h.replace(); if (changeScope) h.setCurrent(false);
    h.clock.tick(2000);
    assert.deepEqual(h.commits, changeScope ? [] : [20000]);
  }
});

test("destroy cancels both idle and pending blur callbacks", () => {
  const h = setup(); h.input.focus(); h.edit("20000"); h.input.blur();
  h.registry.get("alignmentLength").destroy(); h.clock.tick(2000);
  assert.deepEqual(h.commits, []); assert.equal(h.registry.size, 0);
});
