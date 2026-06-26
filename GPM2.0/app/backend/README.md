# Backend

本目录用于承载 `gpm_next` 的 Rust 后端实现。

当前已落地（Phase 2 ~ Phase 7）：

- 导入器骨架（zip 导入 / 已解压目录导入）
- 导入阶段反馈模型（stage + detail）
- 项目初始化（候选项读取 / create project / bootstrap assembly layer）
- 主工作台读取（chr 导航 / chr 主视图 / ctg detail / 编辑候选）
- 自动 chr 分配（基于 `runs/*_vs_ref/result.paf` 的 `auto-assign-chr`）
- 自动方向矫正（基于 1.0 规则的 `auto-orient-contigs`）
- 手工编辑完整闭环（对齐 1.0 无物理图谱路线）
- Junction Inspection（`get-junction-inspection`）：
  - 同 dataset：读取 `result.paf + result.paf.idx.tsv`
  - 跨 dataset：读取服务器预计算 `runs/<left_dataset>_vs_<right_dataset>/result.paf(.idx.tsv)`
  - 禁止本地 `blastn` 与 fallback
- CLI 调试命令：
  - `inspect-bundle-root`
  - `import-extracted`
  - `import-zip`
  - `list-project-initializer-options`
  - `initialize-project`
  - `bootstrap-project-assembly`
  - `list-project-chromosomes`
  - `list-chr-view-ctgs`
  - `get-ctg-detail`
  - `list-ctg-edit-candidates`
  - `auto-assign-chr`
  - `auto-orient-contigs`
  - `rename-ctg`
  - `flip-ctg`
  - `flip-seq`
  - `set-seq-range`
  - `set-end-type`
  - `hide-seq`
  - `show-seq`
  - `reorder-members`
  - `set-join-type-to-prev`
  - `set-gap-size-to-prev`
  - `remove-seq-from-ctg`
  - `add-seq-to-ctg`
  - `split-ctg`
  - `append-ctg`
  - `delete-ctg`
  - `get-junction-inspection`

计划模块：

- workspace/importer
- project_initializer
- chr_assignment
- orientation
- ctg_editor
- junction_inspection
- exporter
- audit
- settings
