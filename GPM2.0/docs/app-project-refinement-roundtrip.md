# 项目级精修任务：导出、执行和回导

状态：已确认的实施协议（分支源码开发中；本文不宣称已完成真实环境联调或最终验收）。这里描述 App 对指定 Gap/Tel 的二次精修，与 `run_all.sh` 发布的整套精修项目分开；后者仍可按 [Server 精修包协议](server-refinement-app-contract-20261122.md) 导入为独立项目。

## 用户流程

1. **选位点和导出。** 在 Assembly / Final Path 把 Gap 或左、右端粒加入当前项目的「精修任务」清单；每个 Gap 任务**单选**一个 GapFiller（默认 DEGAP，也可单选 LR_Gapcloser / TGS-GapCloser / quarTeT；新任务包每个位点仅提交 1 个工具，后端拒绝新多工具请求，旧多工具包继续兼容读取）；Tel 固定使用 DEGAP TelSeeker（`telseeker_ctg`）。导出分两条清晰路径：Assembly 保留当前染色体已选的快捷导出（与「旧版 DEGAP-JOBS（脚本包）」明确区分）；全项目总导出主入口位于项目页右侧「染色体预览 → 导出下拉 → 导出全部精修任务」（与路径文件「全部」为两个独立选项，入口不放在「精修」卡），点击后先打开按染色体分组的任务预览确认弹窗，核对列表后点击「确认导出」才弹出系统保存框并写入 `refinement_tasks.zip`（Assembly 内若触发全项目导出亦转入同一预览确认弹窗，不直接保存）。全项目导出仅汇总本项目各染色体已登记位点，不扫描未选位点、不跨项目、不跟随轨道。用户不用选目标轨道。HiFi 和 ONT 分开：优先保留此项目用户设置（显式清空也算编辑），否则从已验证的精修包提取原始 Server reads，包含用户提供但某个工具没用到的输入，不用转换后的临时文件。没有记录就留空，仍能选位点和导出。端粒 motif 沿用可核实的项目设置并允许更改。
2. **在 Server 执行。** 导出一个 ZIP，包含任务清单、运行说明和一条可复制命令（默认在对应的 CGAT Server 工作区根目录执行 `python .lib/tools/refine.py refinement_tasks.zip`，全局入口 `~/bin/refine.py` 同样适用）。执行自动写入 `08_refinement_jobs/02_manual/<batch_id>/` 并同步更新总报告 `06_report/report.html`，不让用户逐任务填输出目录或工具二进制。工作区运行时（新项目 `.lib/`，旧项目兼容 `.prepare_lib/`）安装的锁定工具和 `gapfill.toml` 是参数来源，不在 App 另设一套 DEGAP GapFiller 数值预设。已有 reads 路径按 Server 路径使用；换机器、缺 reads 或需替换输入时，执行时按需传 `--hifi`/`--ont` 覆盖对应技术 reads。文件存在、摘要匹配和工具的 reads 要求在 Server 检查；不上传 reads，不让 App 当本地文件探测，不根据后缀猜测技术类型。旧自定义工具路径不继承到新协议。
3. **把结果导回原项目。** Server 自动收集批次结果为一个 ZIP。Project 页选中的具体项目右侧有「精修」子卡片，可导入结果并查看进度和历史。在这张卡选包本身就是应用意图；校验通过即更新该项目 Final Path，不弹第二次确认。包不属于该项目即停止，不自动切换项目。打开其他项目、染色体或轨道不会改变已启动导入的目标。

## Server 工作区与 `08_refinement_jobs`

新版编号工作区增加顶层 `08_refinement_jobs/`，用于快速定位全部精修任务；`07_delivery/` 仍是可导入 App 的整项目交付包，`08_refinement_jobs/` 仅作精修任务导航与过程区：

- `.lib/`：新项目工作区运行时目录（含 `.lib/tools/refine.py` 及锁定工具/脚本）；旧项目 `.prepare_lib/` 作为兼容读取/迁移路径。
- `08_refinement_jobs/01_automatic/<tool>/`：收录自动精修的任务状态、报告入口与交付包入口，**不复制或移动** `04_refinement/`、`05_final/`、`06_report/`、`07_delivery/` 中的科学产物。
- `08_refinement_jobs/02_manual/<batch_id>/{01_inputs,02_jobs,03_report,04_delivery}`：存放 App 导出的项目级手动任务输入、运行与质检记录、批次报告及待导回结果包；手动精修完成后同步更新总报告 `06_report/report.html`，但手动结果在导回 App 前不得写入或冒充自动精修 `05_final/`。
- `08_refinement_jobs/` 下的任务索引必须由发布/完成 receipt 生成，不能仅凭裸目录存在判定任务成功。

```text
<server_workspace>/
├── .lib/                             # 新项目运行时与工具（含 tools/refine.py；旧项目兼容 .prepare_lib/）
├── 04_refinement/                    # 自动精修中间产物
├── 05_final/<tool>/                  # 自动精修已发布 accepted result（不含未导回 App 的手动结果）
├── 06_report/                        # 整项目总报告（report.html，含自动与手动精修视图）
├── 07_delivery/                      # 可导入的整项目交付包
└── 08_refinement_jobs/               # 精修任务导航与过程区（由 receipt 生成索引）
    ├── 01_automatic/<tool>/          # 自动精修状态、报告入口、交付包入口
    └── 02_manual/<batch_id>/         # App 导出的手动精修批次
        ├── 01_inputs/                # 任务清单与内容绑定局部种子
        ├── 02_jobs/                  # 工具执行与质检记录
        ├── 03_report/                # 批次报告（summary.json）
        └── 04_delivery/              # 导回原项目的手动结果 ZIP（refinement_results.zip）
```

**用户怎么找：**
1. 导入整套 Server 项目，看 `07_delivery/`。
2. 查自动精修的状态、报告和交付入口，看 `08_refinement_jobs/01_automatic/<tool>/`；总览自动与手动精修状态看 `06_report/report.html`。
3. 查 App 导出的手动精修任务、日志和待导回结果包，看 `08_refinement_jobs/02_manual/<batch_id>/`。

## 任务与结果的绑定

- 每个导出批次绑定 App 工作区内的项目、导出记录和 Server 项目来源；不能用同名项目、同名染色体、数据库数字 ID 或绝对路径单独判定归属。定位依据是导出任务凭据、当前位置唯一可重定位的来源和证据摘要。一个逻辑位点可有多个工具任务，分别记录工具、锁定版本、实际输入、参数和结果。
- 执行以 **App 导出时的 Final Path** 为准，而不是复用 Server 冻结的 LGZ 基线。当 App 已编辑过，按已验证的来源、区间、方向重建局部种子。Gap 记录原有 N 区间和两侧锚点，Tel 记录端点和外向方向。两侧 scaffold 工具使用原始 N 占位长度；不能凭空猜一个缺口长度，输入证据不足则显示不适用。可复用自动精修的运行时、工具适配和质检代码，不能输入未经证明的源片段，也不能改写自动精修发布物或主 LGZ 来源表。
- 结果包包含任务身份、原位点/边界、可验证的原序列与新序列摘要、准确的替换范围/方向、候选片段、执行和质检记录。只接纳通过校验的局部替换，不用整个工具输出 scaffold 替换染色体。区分已闭合、部分填补、端粒延伸、无候选、质检未通过、缺 reads、失败和未完成；一项失败不拖住其他可应用项。相同证据的重复导入不再应用；不能以相同任务 ID 覆盖已签收的不同结果。
- 私有输入路径仅用于项目设置和任务执行，默认不显示在卡片摘要或对外报告；包里没有原始 reads。保留 Full/Light 的正常区别：Light 不保证本地序列可用。已有资料不足以校验的结果不得自动落到路径上；不能把未校验的 FASTA 当作补丁。

## 应用、对比与撤销

| 情况 | 默认行为 |
| --- | --- |
| 同一未填 Gap 有多个合格的完全闭合结果（仅用于兼容旧多工具包；新任务每个 Gap 单选 1 个工具） | 选用顺序 **DEGAP → LR_Gapcloser → TGS-GapCloser → quarTeT GapFiller**（仅适用于旧多工具包兼容读取）。证明的是选用顺序，不是工具或序列准确性排名。替换范围和序列完全一致时合并展示但保留全部来源；其他结果仍可对比。 |
| Gap 没完全闭合或候选未过质检 | 不自动写入；清楚显示是部分填补、无候选还是质检失败。仅有可校验候选才展示序列。 |
| TelSeeker 验证通过且确有端粒延伸 | 可与 Gap 同批自动应用；标「端粒延伸」，独立计数。左、右端分别校验，不能覆盖无关的染色体序列。 |
| 已编辑了其他位点 | 若目标位点及必要边界在当前路径上仍能按身份、序列和方向唯一核对，可重定位并应用，而不是因整条染色体的坐标偏移而拒绝。 |
| 位点/边界已变、匹配不唯一、不同位点的实际替换有冲突 | 跳过受影响的任务、报告原因，其他有效位点照常应用。提交时在当前项目修订上重新验证，不按失效坐标硬套。 |
| 晚到的另一工具结果（包括优先级更高） | 不静默覆盖已填位点。保留候选，显示可切换；最终再次验证该位点和边界再执行。 |
| 撤销或切换 | 以位点为单位；记下采用前后的区段和来源。若落盘片段及必要边界仍未被后续修改，可撤销或切换到合格候选。不得恢复整个染色体快照覆盖其他编辑。 |
| 旧 `degap_results.zip` | 仍从项目卡片导入。只有旧记录能够同样证明精确替换范围、来源和质检结果时才允许自动应用；否则作为候选或保留已验证的状态信息，不把旧候选当已填补。旧包原有归属及完整性校验仍有效。 |

导入成功的验收不是显示一个 badge：采用的片段必须成为实际 Final Path 来源，保留原 Gap/端点、工具和版本、批次与原区间。每次变更同步其后续片段的坐标，用同一个已持久化的项目修订刷新 Final Path、Project 预览和 FASTA 导出输入。项目修订、应用历史与导入结果必须一起对用户可见；损坏包、事务失败、取消不能留下负载和路径各自只写了一半的状态。逻辑上的逐项跳过（可校验包中的不适用任务）不同于格式、身份或摘要错误（整个包拒绝）。

## 界面和交付验收

- **自动与手动的共享语义与边界：** 自动精修与手动精修共享展示语义，但来源、证据链和撤销边界不同。自动精修的 Final Path 仍必须来自 `05_final/<tool>` 已发布的 accepted result，沿用整项目发布证据，不按手动位点回滚；手动精修以导出凭据、局部种子和质检记录为证据，应用后才改变该项目自己的 Final Path，并支持按位点撤销或切换。
- **Project 页「精修」卡片：** 属于选中的具体项目，统一按来源区分「自动精修」与「手动精修」，显示状态、工具、已闭合 Gap、端粒延伸、未应用/失败原因及报告/交付入口；展开可按染色体/Gap/端点查看采纳、备选、原因与批次并定位到 Final Path。手动导回严格归属该具体项目，不能归到当前轨道，也不自动为每个工具建轨道。
- **Final Path 标记与真实性约束：** Final Path 图与列表统一使用一个轻量「精修」/「Refined」标记（轨道细描边、列表短标，不按 Gap/Tel 或工具名做大色块/长标签）；自动/手动来源、tool、版本/修订、run/batch、位点与可撤销/切换细节放在 Tooltip、Final Path Log 贡献表与项目精修卡。没有实际 accepted edit（仅 zero accepted、失败或候选）时不得标记为已精修，也不得把 LGZ 副本冒充精修结果。
- **验收范围：** 界面布局和前端样式交由 agy CLI / Gemini 4 Neon，和现有 App 设计对齐；不改变本文协议。开发期间只跑涉及到的轻量检查，最后统一验证：跨项目拒绝；旧多工具包兼容优先级、相同结果合并、较高优先级迟到、重复导入；部分填补和拒绝的局部补丁；左右端粒、冲突和不相干编辑；按位点撤销/切换、重启恢复、旧包；已填后的 FASTA 逐序列一致；新旧 Server 工作区、Full/Light、已有 reads 预填及缺失时只在执行前提示。最后才做 App 构建和真实任务闭环验证。

### 界面交接（agy / Gemini 4 Neon）

- 「精修」放在选中项目右侧详情的数据集与染色体预览之间；复用 `.project-section-divider`、`--border-subtle`、`--font-small`，窄窗允许换行，键盘可达。
- 顶栏保留一个「导入精修结果」动作；卡片内按自动/手动分区呈现摘要、报告/交付入口与位点详情，提供定位和安全时的手动位点撤销/切换（不弹第二个确认框，不归到当前轨道，不新建轨道；旧 `degap_results.zip` 仅记为「旧版候选 · 未应用」，不提供定位/撤销/切换）。
- Final Path 主标记统一轻量「精修」/「Refined」，自动/手动与工具细节放在 Tooltip、Final Path Log 贡献表与项目精修卡。导出表单的预填状态只提示「沿用项目 reads」，Gap 工具单选（默认 DEGAP），Tel 工具只读；不在摘要重复路径、报告正文或同一状态。

## v1：任务包与 Server 输入边界

- 任务 ZIP 的协议入口为根目录 `refinement_tasks.json`（`cgat.app-refinement-tasks.v1`，UTF-8），可带 `README.txt`。不运行归档内代码。`export_id` 是单次导出的不透明标识；以**原始 JSON 字节** SHA-256 作为 `batch_sha256`。App 在本项目同一工作区的私有凭据中登记项目 ID 和原清单，后续以登记内容而不是 ZIP 文件名或当前界面判断归属。
- 清单顶层为 `schema`、`export_id`、`origin_fasta_sha256`、`reads`、`loci`。`origin_fasta_sha256` 来自 App 导入时已校验的整套 Server 交付；Server 以对应项目的 LGZ 或已发布精修 FASTA 验证它。此摘要只证明原交付归属，**不是手动位点输入**。`reads.hifi` / `reads.ont` 为 `{path, sha256}` 数组，未带摘要用 `null`，允许空数组。同一文件不得同时属于两种技术。App 显式提交空数组时，不用导入提示覆盖。
- 每个 `loci` 项有 `id/chr/kind/target/tools/witnesses/seed_plans`，Gap 另有 `gap_bp`，Tel 另有 `motif`。`kind` 为 `gap`、`tel_left` 或 `tel_right`。`target` 是选中段的 `segmentId`；位点 ID 以染色体、类型和该 ID 派生，不含坐标和工具；工具编码复用 `degap/lrgapcloser/tgsgapcloser/quartet`。新任务每个 Gap 的 `tools` 数组仅含 1 个工具（后端拒绝新多工具请求；旧多工具包仍兼容读取），Tel 只接受 `degap`。浏览器/前端只提交选择和可选设置，后端从落盘的项目 Final Path 取区段，不能提交任意种子去替换项目路径。
- `witnesses` 记录导出时需要保持的相邻路径段（稳定 ID、来源、区段、方向）；不可把序列位置的变化当成另一个位点。Gap 种子 label 为 `seqleft/seqright`，Tel 为 `endpoint`，使用现有内容绑定的种子计划（明确源名称、正向 1-based 闭区间、源长度、完整源文件或所用区间 SHA-256；最终按 `start/end` 定向）。种子使用当前路径的左右立即相邻来源或实际端点；编辑过的项目仍以其保存的路径为准。无正长度 N、缺直接端点/侧翼、不可定位来源或无内容证据，明确报该位点不可导出/准备，不能跳过相邻缺口拼成另一个缺口。
- Server 在已准备好的对应工作区启动；不接受 ZIP 提供输出目录或 Server 可执行路径。校验原交付归属后，在工作区自己的编号任务目录，用已准备工具解析内容绑定计划。Gap 局部输入是正向 `left + N*gap_bp + right`，Tel 局部输入只有定向端点；证据与局部 FASTA 一起保存。输入准备不修改 LGZ/自动精修已发布文件，也不是任务已完成的证据。
- 后续结果包按本次 `batch_sha256` 和 `locus_id × tool` 关联回导，不能以一次归档定义取代本地导出凭据。补丁必须绑定目标和实际替换区间、前后序列摘要及 Server 质量判定。没有足够证据验证的提案不得生成自动应用操作。该段不改变旧 DEGAP-JOBS 完整性和回导边界。

## v1：手动执行与结果包

- **执行入口与运行时解析**：手动精修入口脚本为 `refine.py`。用户从对应的 Server 工作区根目录直接执行 `python .lib/tools/refine.py refinement_tasks.zip`（直接在项目锁下完成校验、准备与执行）；`--hifi`/`--ont` 为可选参数，可重复传入以覆盖对应技术 reads，不再将 `--server-dir`、`--tasks`、`--run` 作为普通用户必需参数。新项目运行时目录为 `.lib/`，旧项目 `.prepare_lib/` 作为兼容读取/迁移路径。全局 `~/bin/refine.py` 也可作为入口，但运行时解析严格遵循“当前 Server 工作区 `.lib/` 优先、旧 `.prepare_lib/` 其次”，禁止混用不匹配的运行时与工作区。
- **批次产物与总报告更新**：批次位于 `08_refinement_jobs/02_manual/<batch_sha256>/`，其中 `02_jobs/<locus_id>/<tool>/<attempt_id>/` 记录固定版本、输入与原生输出；锁定工具、原生证据与项目归属校验照旧。手动精修完成后，除输出批次 `03_report/summary.json` 与 `04_delivery/refinement_results.zip` 外，还必须更新总报告 `06_report/report.html`，清晰呈现批次标识、工具版本、实际使用的 reads、每个位点的状态与候选结果，并明确区分「等待导回 App」与「已导回 App」状态；手动结果在导回 App 前仅属于批次待回导产物，不得写入或冒充自动精修 `05_final/`。
- **结果包清单**：`refinement_results.zip` 根清单为 `refinement_results.json`（schema `cgat.app-refinement-results.v1`），以 `batch_sha256` 绑定原始导出清单。`results` 每行含 `locus_id`、`tool`、`status`、`reason`、`patch`，可带 `version`/`revision` 等运行信息；允许失败与未完成，不用失败文件冒充补丁。
- **补丁约束**：`patch` 包含 `operation`（`replace_gap`/`prepend_tel`/`append_tel`）、`original_length`、`original_sha256`、`path`、`length`、`sha256`；序列为 `patches/` 下无换行的大写 ASCII IUPAC 文本。Gap 仅替换已导出的一整段 `N`，空序列只用于明确通过验证的 Gap 删除；带 `N` 属 `partial`，需要更改非 `N` 侧翼的候选标为 `rejected`，不作为自动补丁。Tel 必须有真实延伸且原端点完整，不替换已有端点的序列。
