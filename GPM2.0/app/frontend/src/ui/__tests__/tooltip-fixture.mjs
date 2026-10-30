// Small, dependency-free DOM for event ownership tests. It is not visual/native acceptance.
import { bindAppTooltips } from "../app-tooltip-runtime.js";

export function tooltipFixture() {
  const events = new Map(), windowEvents = new Map(), windowOptions = new Map();
  const listen = (map, type, fn) => map.set(type, [...(map.get(type) || []), fn]);
  const unlisten = (map, type, fn) => map.set(type, (map.get(type) || []).filter(value => value !== fn));
  let callback;
  class Node {
    constructor(tag, attrs = {}, computed = {}, svg = false) {
      this.tagName = tag; this.nodeType = 1; this.attrs = { ...attrs }; this.children = []; this.parentElement = null;
      this.ownerDocument = doc; this.namespaceURI = svg ? "http://www.w3.org/2000/svg" : "http://www.w3.org/1999/xhtml";
      this.computed = computed; this.style = { getPropertyValue: key => this.style[key] || "" };
      this.box = { left: 20, top: 20, right: 120, bottom: 50 }; this.offsetWidth = 240; this.offsetHeight = 100;
      this.classList = { contains: key => this.className.split(/\s+/).includes(key),
        add: key => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), key])].join(" "); },
        remove: key => { this.className = this.className.split(/\s+/).filter(value => value !== key).join(" "); } };
    }
    get className() { return this.attrs.class || ""; } set className(value) { this.attrs.class = value; }
    get id() { return this.attrs.id; } set id(value) { this.attrs.id = value; }
    get isConnected() { return this._connected !== false && (this._root || this.parentElement?.isConnected || false); }
    set isConnected(value) { this._connected = value; }
    get open() { return this.hasAttribute("open"); }
    get childNodes() { return this.children; }
    get textContent() { return (this._text || "") + this.children.map(child => child.textContent).join(""); }
    set textContent(value) { this._text = String(value); this.replaceChildren(); }
    setAttribute(key, value) { this.attrs[key] = String(value); }
    getAttribute(key) { return this.attrs[key] ?? null; }
    removeAttribute(key) { delete this.attrs[key]; }
    hasAttribute(key) { return key in this.attrs; }
    contains(node) { for (let current = node; current; current = current.parentElement) if (current === this) return true; return false; }
    append(...nodes) { for (const node of nodes) { node.remove(); this.children.push(node); node.parentElement = this; } }
    remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(child => child !== this); this.parentElement = null; }
    replaceChildren(...nodes) { for (const child of this.children) child.parentElement = null; this.children = []; this.append(...nodes); }
    matches(selector) {
      if (selector.includes(",")) return selector.split(",").some(part => this.matches(part.trim()));
      if (selector.includes(":not([open])")) return this.tagName === "dialog" && !this.open;
      const tag = selector.match(/^[a-z]+/i)?.[0];
      if (tag && tag.toLowerCase() !== this.tagName.toLowerCase()) return false;
      for (const [, key] of selector.matchAll(/\.([\w-]+)/g)) if (!this.classList.contains(key)) return false;
      for (const [, key, value] of selector.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)) if (!this.hasAttribute(key) || value !== undefined && this.getAttribute(key) !== value) return false;
      return true;
    }
    closest(selector) { for (let current = this; current; current = current.parentElement) if (current.matches(selector)) return current; return null; }
    querySelectorAll(selector) {
      if (selector.startsWith(":scope > ")) {
        let nodes = [this];
        for (const part of selector.slice(9).split(" > ")) nodes = nodes.flatMap(node => node.children.filter(child => child.matches(part)));
        return nodes;
      }
      const all = []; const walk = node => { for (const child of node.children) { if (child.matches(selector)) all.push(child); walk(child); } };
      walk(this); return all;
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    getBoundingClientRect() { const left = parseFloat(this.style.left), top = parseFloat(this.style.top);
      return Number.isFinite(left) ? { left, top, right: left + this.offsetWidth, bottom: top + this.offsetHeight } : this.box; }
    cloneNode(deep) { const copy = new Node(this.tagName, this.attrs, this.computed, this.namespaceURI.includes("svg"));
      copy._text = this._text; if (deep) copy.append(...this.children.map(child => child.cloneNode(true))); return copy; }
    get outerHTML() { return `<${this.tagName}>${this._text || ""}${this.children.map(child => child.outerHTML).join("")}</${this.tagName}>`; }
  }
  const win = { innerWidth: 900, innerHeight: 600,
    getComputedStyle(node) { return { opacity: "1", fillOpacity: "1", strokeOpacity: "1", ...node.computed,
      getPropertyValue: key => node.computed[key] || node.style[key] || "" }; },
    addEventListener: (type, fn, capture) => { listen(windowEvents, type, fn); windowOptions.set(type, capture); }, removeEventListener: (type, fn) => unlisten(windowEvents, type, fn),
    setTimeout() { throw new Error("Tooltip must not schedule a delay"); },
    MutationObserver: class { constructor(fn) { callback = fn; } observe() {} disconnect() { callback = null; } },
  };
  const doc = { nodeType: 9, defaultView: win, createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag, {}, {}, true),
    addEventListener: (type, fn) => listen(events, type, fn), removeEventListener: (type, fn) => unlisten(events, type, fn) };
  doc.documentElement = new Node("html"); doc.documentElement._root = true;
  doc.body = new Node("body"); doc.documentElement.append(doc.body);
  doc.querySelectorAll = selector => doc.documentElement.querySelectorAll(selector);
  const create = (tag = "button", attrs = {}, computed = {}, svg = false) => { const node = new Node(tag, attrs, computed, svg); doc.body.append(node); return node; };
  const host = create("main", { id: "route-host" }); host.dataset = {};
  const owner = bindAppTooltips(host);
  const fire = (type, target, extra = {}) => { const event = { type, target, clientX: 30, clientY: 30, buttons: 0, ...extra };
    for (const fn of events.get(type) || []) fn(event); return event; };
  return { create, host, doc, win, events, windowEvents, windowOptions, owner, panel: owner.panel, fire,
    mutate: records => callback?.(records), windowFire: type => (windowEvents.get(type) || []).forEach(fn => fn({ type })) };
}
