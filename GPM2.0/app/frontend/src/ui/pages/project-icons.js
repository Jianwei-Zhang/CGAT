import { ArrowRight, Check, Folder, FolderOpen, FolderInput, PackagePlus, Pencil, Trash2, X } from "lucide";

const icons = { arrow: ArrowRight, check: Check, folder: Folder, open: FolderOpen, import: FolderInput, addPackage: PackagePlus, delete: Trash2, rename: Pencil, close: X };

// Lucide's static icon nodes also render in the DOM-free page tests.
export function projectIcon(name) {
  const children = icons[name].map(([tag, attrs]) =>
    `<${tag} ${Object.entries(attrs).map(([key, value]) => `${key}="${value}"`).join(" ")}></${tag}>`,
  ).join("");
  return `<svg class="project-icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${children}</svg>`;
}
