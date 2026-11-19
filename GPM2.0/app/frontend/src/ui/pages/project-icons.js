import { ArrowRight, ShieldCheck, ChevronsDownUp, ChevronsUpDown, ChevronRight, ExternalLink, FileBox, FolderPlus, Inbox, MoreHorizontal, Check, Copy, Folder, FolderOpen, FolderInput, ImageDown, PackagePlus, Pencil, Plus, RefreshCw, Search, Sun, Moon, Trash2, X } from "lucide";

const icons = { validate: ShieldCheck, collapse: ChevronsDownUp, expand: ChevronsUpDown, chevron: ChevronRight, externalLink: ExternalLink, project: FileBox, newPartition: FolderPlus, inbox: Inbox, more: MoreHorizontal, arrow: ArrowRight, check: Check, copy: Copy, folder: Folder, open: FolderOpen, import: FolderInput, addPackage: PackagePlus, delete: Trash2, rename: Pencil, plus: Plus, close: X, refresh: RefreshCw, search: Search, imageDownload: ImageDown, sun: Sun, moon: Moon };

// Lucide's static icon nodes also render in the DOM-free page tests.
export function projectIcon(name, extraClass = "") {
  const children = icons[name].map(([tag, attrs]) =>
    `<${tag} ${Object.entries(attrs).map(([key, value]) => `${key}="${value}"`).join(" ")}></${tag}>`,
  ).join("");
  const cls = extraClass ? `project-icon ${extraClass}` : "project-icon";
  return `<svg class="${cls}" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${children}</svg>`;
}
