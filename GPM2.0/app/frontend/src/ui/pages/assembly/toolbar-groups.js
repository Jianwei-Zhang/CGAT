// Presentation-only groups; parameter fields retain their existing owners and IDs.
const COPY = {
  zh: {
    display: ["显示", "选择辅助组装，以及显示的结果和标记"],
    localDisplay: ["显示", "选择局部视图中显示的预计算结果图层"],
    filter: ["筛选", "按 Contig 长度、比对长度和一致性筛选显示内容"],
    localFilter: ["筛选", "按比对长度和一致性筛选局部视图的显示内容"],
    edit: ["编辑", "创建分相轨道，以及撤销、重做或重置当前视图的操作"],
    localEdit: ["编辑", "撤销、重做或重置当前局部视图的操作"],
  },
  en: {
    display: ["Display", "Choose the auxiliary assembly, result layers and markers to display"],
    localDisplay: ["Display", "Choose the precomputed result layers shown in this Local View"],
    filter: ["Filter", "Filter displayed content by contig length, alignment length and identity"],
    localFilter: ["Filter", "Filter Local View alignments by length and identity"],
    edit: ["Edit", "Create phased tracks, or undo, redo and reset operations in this view"],
    localEdit: ["Edit", "Undo, redo and reset operations in this Local View"],
  },
};
const escape = value => String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

export function renderToolbarGroup(kind, content, i18n, { local = false } = {}) {
  if (!content.trim()) return "";
  const locale = /[\u4e00-\u9fff]/.test(i18n.trackControls.identityPct) ? "zh" : "en";
  const key = local ? `local${kind[0].toUpperCase()}${kind.slice(1)}` : kind;
  const [label, hint] = COPY[locale][key];
  return `<div class="assembly-toolbar-group" data-toolbar-group="${kind}" role="group" aria-label="${label}">
    <span class="assembly-toolbar-group-label" tabindex="0" data-app-tooltip="${escape(hint)}" aria-description="${escape(hint)}">${label}</span>
    <div class="assembly-toolbar-group-content" data-toolbar-group-content>${content}</div>
  </div>`;
}
