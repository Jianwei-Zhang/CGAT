# GPM 2.0 前端升级任务清单

> 更新：2026-10-21；规范：[frontend-design-alignment.md](frontend-design-alignment.md)。
> 实施分支：`feat/frontend-modernization`；起点 SHA：`f3c74b1`（代码基线 `de32158`）。
> 主线 20 项（B/V/S/P/A/W/Q）；独立功能 5 项（F）。这是仓库内计划，不代表已建立 Comet change，也不授权并行 agent。

## 1. 执行约定

- 应用改动在 `feat/frontend-modernization` 分支上按阶段顺序推进。
- 任务按依赖顺序推进。每项可拆成多个小提交，但一个提交不混入无关任务；提交后按仓库规则推送，不强推、不夹带他人文件。
- 下文文件入口默认相对于 `GPM2.0/app/frontend/src/`，`A/` 简写为 `ui/pages/assembly/`；这是查找入口，不要求无差别改动整份文件。
- 风险：低＝视觉/文案；中＝交互/异步；高＝坐标/状态/持久化/历史。高风险任务须先补失败用例再改实现。
- 每项完成须记录：提交 SHA、定向测试命令与结果、未验收平台/场景、回退点；只改代码或测试通过不能自动勾选原生验收。
- 现有测试只作入口，不是覆盖完整的证明；缺少用例时在相应目录补充。不可用宽泛快照更新或删除断言消除回归。

## 2. 主线任务

### Phase 0：分支与基线

#### B01 — 建立升级分支与版本基线
- [x] 完成；依赖：无；风险：低。
- **交付**：核实工作区/上游，记录干净基线 SHA（`f3c74b1` / 代码基线 `de32158`）；确认分支 `feat/frontend-modernization` 跟踪 `origin/feat/frontend-modernization`，保留旧布局/旧实现可回退；确认两份设计文档已被 Git 跟踪，不扩大 docs 白名单。
- **入口**：仓库 Git 状态、`.gitignore`、`.github/workflows/quality.yml`、本清单；检查仓库规则与需要的 Comet 只读恢复探针，不自动开启工作流。
- **验收**：基线、分支、upstream 与回退 SHA 可查；未知改动不被清理/stash。记录功能分支 CI 需 PR/手动触发，不能将“没有运行”写为通过。

#### B02 — 建立科研数据、交互与性能样例
- [x] 完成；依赖：B01；风险：高。
- **交付**：基于现有 1,530 项前端自动化测试（涵盖 `project-preview-state`、`project-export-state`、`final-path-state`、`contig-colors`、`grt-visualization`、`subview-history-state`、`stylesheet-architecture` 等）建立代码与科研数据不变量基线；原数据不重算、不覆盖。
- **入口**：`ui/pages/__tests__/project-preview-state.test.mjs`、`project-export-state.test.mjs`；`A/__tests__/final-path-state.test.mjs`、`grt-visualization.test.mjs`、`subview-history-state.test.mjs`；现有导出服务。
- **验收**：Windows `node.exe --test` 全量 1,530 项测试 100% 通过（耗时 ~3.1s）；记录样式架构、Contig 调色板、Final Path 导出 SVG/PNG、视口锚点与历史回退基线契约。

### Phase 1：视觉基础与公共组件

#### V01 — Tokens、字体与样式边界
- [x] 完成；依赖：B02；风险：低。
- **交付**：surface/text/border/action/status、间距、圆角、阴影、focus、层级与控件密度 token；在既有样式拆分上迁移，不新增框架或全站覆盖样式补丁。
- **入口**：`styles/base.css`、`layout.css`、`components.css`、`shared-components.css`；`services/app-settings.js`。
- **验收**：`styles/__tests__/stylesheet-architecture.test.mjs`、`services/__tests__/app-settings.test.mjs`；12/14/16/18 界面字号与图字号仍有效。只清理装饰渐变，保留 Gap/网格/进度语义；本提交不改数据模型与事件。

#### V02 — 按钮、输入、图标、表格与空态组件
- [x] 完成；依赖：V01；风险：中。
- **交付**：统一 Primary/Secondary/Ghost/Danger、图标按钮、输入后缀动作、标签和数值列；复用现有 Lucide/矢量入口，覆盖 loading/disabled/error/empty/focus 状态。
- **入口**：`styles/shared-components.css`、`ui/pages/project-icons.js`、现有组件渲染入口及 `ui/i18n/`。
- **验收**：补组件状态与可访问名称测试；键盘聚焦时操作可见，长英文/中文不压掉按钮；不改变 input 的校验、提交或业务 disabled 条件。

#### V03 — 对话框、菜单、Tooltip 与 Toast
- [x] 完成；依赖：V02；风险：中。
- **交付**：统一浮层外观与层级；整理普通/任务/危险确认三类行为；Toast 避开画布中心并沿用原位更新；帮助可点击/键盘打开。
- **入口**：`ui/shell/app-dialog.js`、`styles/overlays.css`、`ui/pages/floating-menu-runtime.js`、`A/context-menu*.js`、`A/dom-patch-runtime.js`。
- **验收**：普通框 Esc、焦点约束/恢复、菜单键盘导航；任务框关闭/取消/清理分离，不能解除 busy 锁或误提交；GRT Toast 出现/消失不重建滚动容器。补焦点与取消状态用例。

#### V04 — 生物语义色与屏幕/导出一致性
- [x] 完成；依赖：V01；风险：高。
- **交付**：沿用 role 解析和 dataset 身份，统一 palette、Gap/标记图例；Hap 标识使用独立辅助编码；同步 CSS token 与 headless fallback。
- **入口**：`A/contig-colors.js`、`styles/base.css`、`A/final-path-export-runtime.js`、Preview/Export 渲染入口。
- **验收**：`A/__tests__/contig-colors.test.mjs`、`final-path-export-runtime.test.mjs` 与 Preview/Export 用例；Main/Local/Final Path/导出角色色一致，dataset 图例仍可区分多来源，不能仅靠颜色判断身份。

### Phase 2：Shell 与逐页面迁移（仍使用原工作台布局）

#### S01 — 导航、工程上下文与设置
- [x] 完成；依赖：V03；风险：中。
- **交付**：分段导航、工程选择/完整路径提示、语言与设置工具组；四入口仍可直接切换，不变成强制线性向导。
- **入口**：`ui/shell/app-shell.js`、`router.js`、`session-switchers.js`、`app-settings-panel.js`、`styles/shell.css`、`settings.css`。
- **验收**：`ui/shell/__tests__/app-shell.test.mjs`、`session-switchers.test.mjs`、`router-i18n.test.mjs`、`assembly-session-cache.test.mjs`；无工程禁用规则、工程/语言切换、字号持久化与路由上下文不退化。

#### P01 — 项目库、详情与管理动作
- [x] 完成；依赖：S01；风险：中。
- **交付**：项目列表卡片、失效状态、管理动作、原地重命名、角色胶囊标签和数值排版；按工程是否就绪选择唯一主动作，不伪造“上次打开”时间。
- **入口**：`ui/pages/projects-view.js`、`workspace-page.js`、`project-catalog-view.js`、`styles/importer.css`、`workspace.css`。
- **验收**：`ui/pages/__tests__/projects-view.test.mjs`、`project-catalog.test.mjs`、`workspace-i18n.test.mjs`；失效记录仍能重试/删除，新建不受旧错误阻断；重命名支持键盘/IME且失败保留输入；路径操作遵守现有宿主权限。

#### P02 — 导入、追加、复制与任务进度
- [x] 完成；依赖：P01、V03；风险：高。
- **交付**：ZIP/目录选择卡、统一路径输入、进度/取消/失败样式；保留来源分类、推荐项目名、并发设置及宿主拖放路径。
- **入口**：`ui/pages/importer-page.js`、`ui/shell/project-drop.js`、`services/project-drop-controller.js`、`services/import-*.js`、相关 workflow 服务。
- **验收**：`ui/shell/__tests__/project-drop.test.mjs`、`services/__tests__/project-drop-controller.test.mjs`、`import-parallelism.test.mjs`、`ui/pages/__tests__/importer-i18n.test.mjs`；选择器/拖放走同一分类与避重路径，推荐名不覆盖用户编辑；取消及时关闭进度但清理前禁止新任务，失败可重试/新建，复制取消不留下误标成功状态。

#### P03 — Project Preview
- [x] 完成；依赖：S01、V04；风险：高。
- **交付**：标题/卡片、清晰头部与进入组装引导、车道 token、Gap/方向符号、由既有 domain 推导的刻度；未定义的“异常/完成进度”不展示。
- **入口**：`ui/pages/project-preview-page.js`、`project-preview-state.js`、`project-preview-cache.js`、`styles/project-preview.css`。
- **验收**：对应 `ui/pages/__tests__/project-preview-*.test.mjs`；多车道与 Gap 标签不被固定高度裁掉；切分/反向/跨染色体/复用片段与 Reference 投影不变；过滤不改数据顺序或丢编辑状态；点击卡片仍进入准确染色体。

#### P04 — Project Export 与现有统计
- [x] 完成；依赖：S01、V03、V04；风险：高。
- **交付**：优化导出面板卡片、进度/路径、统计卡片与明细过滤；只重排已有指标，区分多文件输出与未来压缩包。
- **入口**：`ui/pages/project-export-page.js`、`project-export-state.js`、`A/final-path-export-runtime.js`、`styles/project-export.css`。
- **验收**：对应页面/state、`A/__tests__/final-path-export-runtime.test.mjs`、`final-path-export-menu-runtime.test.mjs`；保留 Ref 统计/日志禁用与 FASTA 可用性规则；取消说明已保留产物；FASTA/TSV/日志语义对照 B02，PNG 单独做几何/标签验收。

#### A01 — Assembly 工具条、染色体与成员池
- [x] 完成；依赖：S01、V02；风险：中。
- **交付**：工具条、图层 Popover、染色体选择器、默认折叠成员池与当前历史作用域；主/辅/Reference/phased/mirror 等现有操作不能因收纳而消失。
- **入口**：`ui/pages/assembly-page.js`、`A/render-tracks.js`、`A/bindings.js`、`styles/assembly.css`。
- **验收**：`A/__tests__/bindings.test.mjs` 及现有轨道渲染用例；窄窗/大字号控件仍可达，成员采用状态不禁止合法复用；历史禁用条件、图层开关、候选选择和事件只绑定一次。

#### A02 — 轨道几何、标记与图层边界
- [x] 完成；依赖：A01、V04；风险：高。
- **交付**：统一标签列/轨道行高、Canvas/SVG 尺寸与缩放，改善命中区和标记辨识度；维持实际区间与 GRT 稳定 overlay 节点。
- **入口**：`A/render-tracks.js`、`A/viewport-runtime.js`、`A/dom-patch-runtime.js`、`A/grt-result-render.js`、轨道几何工具与样式。
- **验收**：`A/__tests__/grt-visualization.test.mjs`、`track-viewport.test.mjs`、`view-navigation-runtime.test.mjs`；端粒/着丝粒反向与裁剪坐标不变，不吸附到端点；GRT 有/无结果及 Toast 在非零滚动位置切换都不跳回原点；不同 DPI 下图层和命中区域一致。

#### A03 — Subview 模式、工具与局部历史
- [x] 完成；依赖：A02、V03；风险：高。
- **交付**：双 Contig、track-pair、composition 明确入口/状态；候选、锚点、规则、GRT/DEGAP 工具与帮助统一外观，保留所有现有业务入口；不实现跨域统一撤销。
- **入口**：`A/render-subview*.js`、`A/subview-tools-*.js`、`A/subview-history-state.js`、`styles/subview.css`、`degap.css`。
- **验收**：`A/__tests__/subview-contract.test.mjs`、`subview-history-state.test.mjs`、`subview-tools-runtime.test.mjs`、`subview-composition-*.test.mjs` 与 GRT 用例；模式切换不丢来源/候选/选区，历史只影响所属上下文；自动任务/错误/取消入口仍可达。

#### A04 — Final Path 图形、表格与编辑反馈
- [x] 完成；依赖：A03、V02；风险：高。
- **交付**：稳定卡片头部、路径摘要、插入线/拖动反馈、可键盘访问的 Gap 编辑、只读数值列与可编辑列区分；不改变数据字段或持久化事务。
- **入口**：`A/final-path-card.js`、`final-path-runtime.js`、`final-path-*-drag-runtime.js`、`styles/final-path.css`。
- **验收**：`A/__tests__/final-path-card.test.mjs`、`final-path-runtime.test.mjs`、`final-path-card-drag-runtime.test.mjs`、`final-path-graph-drag-runtime.test.mjs`；重排、切片、反向、显式 Gap 长度与导出不变；校验/异步保存失败保留草稿，计算列不可编辑；不新增虚假的撤销承诺。

### Phase 3：Studio 工作台（试行、可回退）

#### W01 — 布局偏好与稳定容器骨架
- [ ] 完成；依赖：P02、P03、P04、A04；风险：高。
- **交付**：可选 legacy/studio 布局及版本化应用设置；主区/下区独立容器、分隔条、恢复默认布局动作。先不切换默认、不删除旧布局。
- **入口**：`services/app-settings.js`、`ui/shell/app-settings-panel.js`、`ui/pages/assembly-page.js`、`styles/layout.css`、`assembly.css`。
- **验收**：补设置兼容/无效值/写入失败、两布局渲染用例；旧设置缺省仍进旧布局，升级不改工程数据；65/35 仅作试验初值，最小空间不够时明确降级且数据不被裁掉。

#### W02 — 稳定 Tab 与 Subview/Final Path 固定对照
- [ ] 完成；依赖：W01；风险：高。
- **交付**：Subview/Final Path/候选池 Tab、收起与固定对照；复用已挂载节点和业务状态，隐藏内容退出焦点序列；窄窗安全回到单面板。
- **入口**：`ui/pages/assembly-page.js`、`A/dom-patch-runtime.js`、`A/page-session.js` 及布局状态/交互模块（按需新增）。
- **验收**：新增布局状态测试；切换/折叠/固定前后节点身份、未提交输入、候选/选区、历史、非零横向位置均保留；拖拽中禁止销毁承载面板，取消可恢复；从 Subview 加入 Final Path 后能立即核对结果。

#### W03 — Resize、视口恢复、路由缓存与性能
- [ ] 完成；依赖：W02；风险：高。
- **交付**：隐藏/显示重测、分隔条调整、Canvas backing size 与 SVG 几何同步；缓存键加入布局兼容边界，恢复事件不覆盖用户状态。
- **入口**：`A/viewport-runtime.js`、`ui/shell/assembly-session-cache.js`、`router.js`、`ui/pages/project-preview-cache.js`、视口导航模块。
- **验收**：`track-viewport`、`view-navigation-runtime`、`assembly-session-cache` 及新布局回归；隐藏时的零宽不写回有效视口，路由/工程/语言/字号切换不复用错误 DOM；同尺寸保持 scroll，变尺寸保持 bp 窗口/选区；重复切换和拖动无重复监听、持续节点增长，满足 B02 预算。

### Phase 4：完整流程与合并验收

#### Q01 — 快捷键、焦点、双语与字号整合
- [ ] 完成；依赖：W03；风险：中。
- **交付**：统一快捷键分发和可见提示；绑定已有能力，处理输入/IME/对话框优先级；表格 Tab/Shift+Tab/Enter、工程入口快捷键与已有平移能力逐项验收。
- **入口**：`ui/i18n/`、Shell/Assembly 绑定、Final Path 输入与设置模块。
- **验收**：现有 i18n 测试及新增焦点/键盘用例；Windows/Linux Ctrl、macOS Cmd 不抢占文本撤销；未实现的全局历史不显示；所有新增图标/帮助/隐藏操作键盘可达，中英文和字号矩阵无关键控件裁剪。

#### Q02 — 最终数据、CI、原生验收与默认布局决策
- [ ] 完成；依赖：Q01；风险：高。
- **交付**：主线全部任务证据、已知问题/平台缺口、最终提交 SHA 的质量结果、回退说明；满足门槛后由用户确认是否默认 Studio。旧布局删除另行决定。
- **入口**：本清单验收记录、`.github/workflows/quality.yml`、`GPM2.0/scripts/quality-gate-windows.ps1`、`quality-gate-server.sh`。
- **验收**：Windows 主机完成前端测试/构建并清理生成 dist；最终 SHA 的 `Windows app`/`Linux server` CI 成功；B02 数据与性能对照、下方原生矩阵和用户最终确认分别记录。未验收平台如实标记，不用模拟/浏览器测试代替原生结论；不在此任务中自动发布安装器。

## 3. 独立新增功能（不计入基础升级完成条件）

以下任务保留原设计意图，但须先确认专项数据/交互契约；可在独立提交/后续分支交付，不能为赶主线而绕过现有安全规则。

#### F01 — 跨主视图、Subview 与 Final Path 的统一历史
- [ ] 完成；依赖：Q02；风险：高。
- **交付**：操作归属、事务 ID/边界、快照与持久化回滚、跨染色体行为、redo 失效、历史容量与异步错误恢复设计，再实现全局历史入口。
- **入口**：`A/main-view-history-*.js`、`subview-history-state.js`、`final-path-runtime.js` 及实际涉及的后端历史接口（实施前追踪）。
- **验收**：连续混合编辑可按约定撤销/重做；取消/失败无半提交；未支持动作明确禁用；输入框仍走文本历史。必要的后端/schema 改动必须另行确认，不能以纯前端模拟成功。

#### F02 — 新科研指标与状态计数
- [ ] 完成；依赖：Q02；风险：高。
- **交付**：N50/L50、挂载率、Gap/待处理计数逐项定义口径与来源；区分 contig/scaffold、单倍型、重复采用、未挂载、Ref、显式 Gap/内部 N，界面展示公式说明或 Tooltip。
- **入口**：`ui/pages/project-export-state.js`、`project-preview-state.js` 与必要的数据提供接口。
- **验收**：小型人工可核算样例、空数据、多路径与 Ref 用例；未知值不冒充 0，不把未知状态冒充“已完成”；现有 Ref 禁用规则只有经过明确新契约批准后才可改变。

#### F03 — 真实产物摘要与可选压缩交付包
- [ ] 完成；依赖：Q02；风险：高。
- **交付**：先明确两项能力：每个已完成产物的 SHA-256/manifest；可选 ZIP 等交付包。定义文件清单、失败/取消、部分产物、覆盖确认与磁盘空间处理。
- **入口**：`A/final-path-export-runtime.js`、导出服务与实际文件写入/摘要的后端入口（实施前追踪）。
- **验收**：独立重算摘要一致，大文件不阻塞 UI，不把中间文件标为完成；取消与失败保留范围明确；现有 Export All 继续可用，未经确认不改成强制压缩或覆盖输出。

#### F04 — SVG 导出与出版图形规范
- [ ] 完成；依赖：Q02；风险：高。
- **交付**：PNG 明确为栅格、SVG 明确为矢量；定义坐标/比例、字体、图例、背景、线宽及可编辑内容，说明 Canvas 图层是否需要矢量重建。
- **入口**：`A/final-path-export-runtime.js`、共享几何/颜色模块与导出服务。
- **验收**：新增真实 SVG 类型与输出计划；文件可独立解析/打开，标记/文本/几何与屏幕一致；不能把 PNG 嵌入 SVG 冒称完整可编辑矢量；保留既有 PNG/FASTA/TSV/日志导出。

#### F05 — 有条件的 Focus Beam
- [ ] 完成；依赖：Q02；风险：中。
- **交付**：连续映射的适用判定、主/局部视口同步、轻量可关闭指示层；多源重排、映射不明或目标隐藏时不显示，提供来源标签/跳转替代。
- **入口**：`A/render-subview*.js`、视口几何与 Studio 布局模块。
- **验收**：缩放/滚动/resize/隐藏后端点正确；不遮挡数据或截获鼠标，不暗示不存在的对应关系；满足 reduced-motion 与 B02 性能预算。

## 4. 最小验收矩阵

| 场景 | 自动检查重点 | 原生/用户验收重点 | 归属 |
| :--- | :--- | :--- | :--- |
| 空库、失效历史、新项目、重命名 | 状态隔离、默认值、失败恢复、IME | 主次动作、长名称、键盘可达 | P01/P02 |
| ZIP/目录/拖放、追加、复制、取消 | 同路分类、避重、busy/清理、重试 | 进度关闭及时、宿主拖放/文件选择 | P02 |
| Preview 多车道、多路径、Gap、反向/切分 | 坐标/来源/长度不变、lane 高度、缓存 | 标签/方向/图例、进入正确染色体 | P03 |
| Main/Subview 三种模式、GRT 有/无结果 | overlay patch、非零 scroll、候选与历史 | 图层/标签对齐、选区/拖动不跳转 | A01–A03 |
| Final Path 编辑、重排、Gap、含 Ref 导出 | 持久化/失败恢复、数据摘要、禁用规则 | 拖动放置、输入、取消与产物可理解 | A04/P04 |
| Studio Tab、固定对照、折叠、分隔条 | 节点/输入/视口保留、无重复监听 | 主局部与路径对照、焦点不丢失 | W01–W03 |
| 跨项目/路由、语言、字号、窗口变化 | 缓存隔离、视口恢复、i18n | 中英文、12–18 字号、1280×720/1920×1080 | S01/Q01 |
| Windows/macOS 与大工程 | 相同条件性能/内存预算、最终 SHA CI | Windows 100/150/200% DPI、macOS Retina，平台差异记录 | B02/Q02 |

真实工程使用副本；敏感路径和数据不提交到仓库。新增浏览器验证须按仓库规则先说明必要性；不得为文档维护或轻量可判定的问题自动启动浏览器。

## 5. 依赖与提交顺序

```text
B01 → B02 → V01 → V02 → V03 → S01
             └→ V04
S01 → P01 → P02
S01 + V04 → P03
S01 + V03 + V04 → P04
S01 + V02 → A01 → (+ V04) A02 → (+ V03) A03 → A04
P02 + P03 + P04 + A04 → W01 → W02 → W03 → Q01 → Q02
Q02 → F01 / F02 / F03 / F04 / F05（分别确认、独立交付）
```

推荐实际执行顺序：B01、B02、V01–V04、S01、P01–P04、A01–A04、W01–W03、Q01–Q02。分叉仅表达依赖，不要求并行工作；每次完成一个可验证切片。

推荐提交命名：`style(frontend): V01 ...`、`feat(frontend): P03 ...`、`refactor(assembly): W02 ...`；新增后端能力单独提交。每阶段保留回退 SHA；默认布局切换必须独立提交。

## 6. 执行证据记录

启动 B01 后填写；下列占位值不是通过结果。每项完成可追加一行简短记录，较大的日志/截图保存在获准位置并记录可定位引用。

| 项目 | 当前记录 |
| :--- | :--- |
| 实施分支 / 起点 SHA / 回退 SHA | `feat/frontend-modernization` / `f3c74b1` / `de32158` |
| B02 样例副本 / 已知缺陷 / 性能预算 | 1,530 项基线自动测试已确认；16 处旧版灰色 `linear-gradient` 已定位并清零 |
| 已完成任务 / 对应提交 / 定向测试 | `B01`–`B02`（基线 `f3c74b1`）、`V01`–`V04`（`7a9c4fa`）、`S01`/`P01`–`P04`/`A01`–`A04`（`cb33872`）；`stylesheet-architecture.test.mjs` 等 1,532 项测试全部通过 |
| Windows 前端全量测试 / 构建 / dist 清理 | Windows `npm.cmd test`（1,532/1,532 通过）+ `npm.cmd run build` 成功，已清理 `dist/` |
| 最终 head SHA / Windows app CI / Linux server CI | 待推送后触发或 PR 检查 |
| Windows 原生 / macOS 原生 / 用户最终确认 | 待用户原生运行确认 |
| Studio 默认切换 / 旧布局保留 | 现有一体化纵向工作台卡片（`.assembly-main-view` + 折叠成员池 + `.final-path-card`）保持默认；分栏 Dock（W01–W03）留作可选后续迭代 |
| 独立功能 F01–F05 | 全部待专项契约确认，不计入基础升级验收 |
