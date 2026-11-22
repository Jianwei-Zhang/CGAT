# LGZ 后精修实施记录

本记录对应 [已确认设计](server-post-lgz-refinement-design-20261121.md)。目标仍是四工具、编号工作区、真正的精修 Final Path 与 App 完整交付；不能以迁移基础设施或额外 FASTA 替代目标。

## 验证节奏（用户补充，2026-11-21）

中间开发仅做必要的语法、diff 和最小针对性检查；四工具、布局、Final Path、报告与 App 链路贯通后，再统一进行完整回归和 A01–A18 验收。前文阶段测试保留为历史证据，后续不重复按小改动运行同样套件。

## 2026-11-21：布局与迁移事务基础

### 已实现

- `server/tools/workspace_layout.py`：严格识别旧布局和编号布局，集中转换持久化逻辑路径；固定工具目录编号、q0/q1/q2/q3 文件及其 sidecar 的阶段位置。旧工作区无标记时保持原路径。
- `server/tools/workspace_migration.py`：只读清单与迁移预览；迁移事务绑定内容校验、原文件权限和路径映射；改写脚本保留原件。普通文件以重命名搬移，避免复制大 FASTA。
- 迁移事务支持搬移中断、改写暂存不完整、校验失败、布局标记已写但提交中断的恢复/回滚；保留独立事务记录，回滚后可以重新迁移。
- 内部/外部相对文件链接按新位置重定位；不使用根目录兼容软链接。目录链接、目标冲突、变化的输入和异常路径在预览或应用阶段明确拒绝，不覆盖用户文件。
- 新建迁移目录采用限制性权限；原文件 mode 保留。没有实现替用户重设共享 ACL/组权限的功能。
- 普通执行拒绝未完成迁移和缺少布局标记的已提交迁移。迁移恢复入口使用原工作区锁；远端 owner、未知 owner 和空锁目录不能被当作无活动任务自动接管。
- `run_all_runner.py` 的计划读取、锁路径，以及 `run_resources.py` 的预算读取/更新接入布局解析。
- `workspace_layout.py` 纳入 LGZ 引擎内容指纹；重新生成并检查 reference recovery 的源码 hash 清单。清单同时刷新分支基线已提交的 q0 源码 hash，未修改这些 q0 算法文件。
- 兼容性回归发现分支基线缺少 `grt_core/q0_query_windows.py`，补充与其他模块相同的转发文件；不复制或修改规范实现。

### 重要边界

这不是用户可直接应用到真实项目的一键迁移。当前公开入口只有只读检查：

```bash
python3 "$SERVER/tools/workspace_migration.py" --server-dir /path/to/old_workspace
```

应用事务是内部 API，必须由版本化适配器提供脚本/回执改写和完整目标契约验证。测试中的适配器只校验受控夹具；不能据此认定真实旧项目已经可迁移。

尚未修改 `prepare.sh` 默认布局，也未开放会搬移用户数据的 `run.sh` 参数。未对客户或远端工作区执行迁移。

### 本阶段测试

测试文件：`server/tests/test_workspace_layout.py`，涵盖映射、预览只读、碰撞、文件身份、锁、实际重命名、权限、链接、故障注入、回滚再迁移、计划读取及资源预算。

回归入口（工作目录为 `GPM2.0`）：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=server/tests python3 -B -m unittest \
  test_workspace_layout test_run_resources test_run_orchestration \
  test_server_run test_run_all_runner test_workspace_runtime_update \
  test_post_lgz_degap -v
```

上述主回归 **112 项通过**（125.997 秒）。补充源码指纹和旧接口兼容性后，`test_lgz_compatibility + test_workspace_runtime_update` **39 项通过**（110.039 秒）。迁移锁校验最终补充后，`test_workspace_layout` **29 项通过**（1.394 秒）。`test_sync_server_runtime` **5 项通过**（19.433 秒），生成运行库的 41 个文件检查一致。这些组存在覆盖重叠，不相加宣称独立用例总数。本机为 Linux x86_64 / Python 3.12.3，新模块另通过 Python 3.11 语法解析检查；这不等于已在目标环境运行。所有本阶段测试均为本地受控测试，不是原生四工具、真实基因组、ARM64 或 App 验收。

### 下一步，不能跳过

1. 为准备脚本、生成的 shell、LGZ 读写、报告、打包和 runtime updater 接入实际编号路径；不能只改 runner 的入口路径。
2. 编写真实旧工作区迁移适配器：保留冻结科学证据，明确转换运行路径和完成检查点；用代表性旧工作区验证不重跑 LGZ。没有适配器前不得开放应用迁移 CLI。
3. 新工作区从准备开始写入编号布局，并完成新/旧两种路径的完整 Server 回归。
4. 实现精修来源、局部修改和可重建 Final Path；接入四个固定版本工具、reads 分配与环境检查。
5. 接入追加任务、独立失败/恢复、每工具最终结果/报告/交付，再完成 App 协议和序列导出闭环。
6. 完成 A01–A18 全部验收与中英文用户指南，不把本阶段结果标记为整体完成。

### 当前验收状态

| 范围 | 状态 |
| --- | --- |
| A01 分支隔离 | 本阶段在指定独立 worktree 开发；提交/推送后核实远端 SHA |
| A11、A12 布局与迁移 | 基础解析、物理事务和故障测试已实现；真实运行路径、适配器及端到端迁移未完成 |
| A02–A10、A13–A17 | 整体功能未完成；旧功能回归仅证明本阶段未破坏被测旧路径 |
| A18 文档与交付 | 设计与阶段记录已写；最终用户指南、完整验收与功能交付未完成 |


## 2026-11-21：精修 Final Path 核心及 DEGAP 接纳适配器

### 已实现（内部 API，尚未切换默认运行入口）

- 新增 `refinement_path.py`：从冻结 LGZ 来源路径出发投影已接纳改动，保留未改来源、负链区间、切分父片段、原始 gap ID 和坐标位移；由该路径流式重建最终 FASTA，而不是复制 LGZ 或原生整合 FASTA。
- 支持正长度桥接、部分修复、邻近 gap 联合替换、无正长度桥接的重叠闭合。残余 N 保留真实候选来源；联合修复中不能逐 gap 定位的残余 N 显式保留联合归属，不虚构一对一对应。
- 原始路径重建校验和、基线 FASTA 染色体序列、最终重建校验和分别检查；原始来源不改名为精修来源。交叉/重复候选全部拒绝，不按输入顺序任意择一。
- `refinement_admission.py` 根据 DEGAP 原生坐标和精确左右锚点归一化候选，支持锚点重叠导致的删除；保留明确拒绝原因。精确锚点仅证明修改位置可解释，不宣称生物学准确性验证。
- `refinement_sources.py` 用私有 FASTA 索引、有界读取和内容身份登记原始/新增序列；`refinement_degap.py` 校验固定 DEGAP revision 与逐文件源码 hash，记录 reads、配方、命令、原生证据和失败状态。
- 实际精修源只保存插入/替换片段；原生完整候选独立保留。成功候选进入私有待发布目录，产出 `assembly.fa`、`final_path.json`、`sources.tsv`、`remaining_gaps.tsv`、`provenance.json`。
- `refinement_publication.py` 要求成功且绑定基线的原生执行回执；零接纳与失败分开。失败不会生成“成功 LGZ 副本”。当前仅完成待发布构建，**尚未做最终目录、报告与 App 包的联合原子发布**。
- 补充编号布局的初始化/内部路径工具及受控 shell 模板重定位；q0/q1 的临时文件与命令脚本不能被错误映射到 q3 目录。

### 本轮必要轻量证据

- 7 个纯序列/来源测试通过：部分修复、负链切分、重叠删除、联合 gap、零改动、冲突和内容变化、有界跨块读取。
- 4 个纯原生坐标/接纳测试通过：重叠删除、联合 gap、无信息候选和冲突拒绝。
- 2 个受控 DEGAP 适配器测试通过：使用真实 samtools 索引，但原生 DEGAP 执行为受控替身；验证候选确实改变 Final Path/FASTA、保留原 LGZ 文件，以及原生失败不产出成功副本。
- 未运行真实 reads 精修、完整回归、前端/桌面构建或发布流程。这些结果不等于四工具集成或 App 序列一致性已经验收。

### 后续必需工作

提交时 recovery hash 清单按暂存区源码快照再生成，避免把工作区中尚未提交的路径适配 hash 混入本批提交。

完成编号布局的默认启动/升级入口与旧工作区适配器；将精修适配器接入共同调度、补跑、缓存和发布事务；实现另外三个原生适配器与固定环境；完成坐标证据重建、完整/轻量 App 新协议和可导航报告。联合修复中可证明未改变的内部来源片段还需进一步细分保留。最后统一完成设计 A01–A18 验收，不能以本阶段模块或测试代替全部目标。


## 2026-11-21：四工具固定配方、环境定义与 reads 派生输入

- 新增 `contracts/refinement-tools.lock.json`、`refinement_tools.py`：固定 DEGAP 2.0 源码、TGS-GapCloser 1.2.1、quarTeT 1.3.1、LR_Gapcloser 1.0；按平台固定原生分发 build/SHA，并校验环境实际文件。`env.sh` 安装/检查同一共享环境，不在任务运行中下载。
- x86_64 / aarch64 规格同步新增 TGS、LR、BWA、Racon；原来未固定的 DEGAP Python 库和 GNU parallel 也固定到本地受控环境已共存且上游有对应平台分发的版本。尚未把“有分发件”当作新规格已求解或 ARM64 已运行。
- 实际 Python 3.11 核查发现 quarTeT 1.3.1 的一处 f-string 引号语法不兼容。加了一条 before/after hash 约束的纯引号补丁，临时安装后的真实 Python 3.11 `GapFiller --help` 通过；未更换共享环境的 Python 版本。
- 新增 `refinement_recipes.py`、`refinement_reads.py`：统一工具选择/默认规则、一次执行的 reads 选择、原生参数、FASTQ/FASTA/gzip 转换及内容绑定复用、可逆 read ID 对照。不要求用户证明 reads 已纠错。
- 避免 quarTeT 的真实 basename 缓存冲突：HiFi/ONT 派生文件名不同，命令层还显式拒绝相同 basename。TGS ONT 原生 Racon、quarTeT 关闭实验 join、LR 三轮/单 tag 分区等参数都写入配方。
- DEGAP 待发布适配器现在使用锁定运行环境构建命令，并要求原生整合 FASTA 完整；报告 JSON、候选和原生整合 FASTA 都进入内容回执，原生/CGAT 接纳差异有独立序列摘要。
- 14 个针对安装/固定配方/小 reads 转换/受控 DEGAP 的最小测试通过（4.560 秒）；另一个“原生退出 0 但缺少整合 FASTA 必须失败”的小测试通过（2.544 秒）；没有跑完整回归，没有修改现有 conda 环境。新增配方记录明确 LR 提前迭代完成、quarTeT 无候选非零退出等尚待公共适配层处理的边界。

本阶段仍未接通三个新增工具的原生接纳、完整 run_all 衔接、最终发布和 App 协议。下一步优先完成共同执行与结果接纳，再处理完整交付，不把“工具版本已锁定”当作四工具已集成完成。


补充实际分发件核查：已校验下载的 TGS-GapCloser Bioconda build 4 archive SHA，并对照实际 driver 与源 tag。分发件来自 `1.2.1_ml`，有原生 1 Mb PAF 起点过滤，且部分 fatal 参数分支返回 0。已把这些区别写入工具锁和配方记录；后续公共执行器必须验全输出，不能把退出 0 当作成功。没有因此改写上游算法或声称原生运行验证通过。


## 2026-11-21：另外三工具原生适配与内部批次恢复

### 本轮实现（仍未切换公共入口）

- `refinement_native_formats.py` 解析锁定工具的真实 TGS scaffold/detail、quarTeT AGP/detail 和 LR 每轮 `info_filter2`，从真实候选/read 片段建立来源，不把整个原生染色体冒充新来源。
- `refinement_native_trace.py` 逐轮验证原生 FASTA、处理负链、重叠闭合、局部扩展和联合修改，保留可唯一定位的原始内部岛；有歧义的来源拒绝接纳。DEGAP 同样补上联合候选内部原始来源保留。
- `refinement_native.py` 建立独立 attempt、日志和内容回执，明确区别原生失败、缺产物、无候选、无适用缺口及成功；LR 提前结束必须确实没有剩余 N。完成标记绑定完整 provenance SHA。
- `refinement_batch.py` 依次运行所选工具，隔离各工具失败，保持共享基线/reads 内容不变；返回所有成功待发布结果和聚合非零状态。
- `refinement_cache.py` 只复用来源、原始 reads、工具/适配器、原生证据和全部最终文件均匹配的完整结果。仅修改线程数不会重跑完成结果，回执保留实际旧线程数。**原生子任务部分复用、发布事务恢复尚未完成。**
- 输入转换带 FAI、UTF-8 原始 ID 可逆映射；运行时按所选工具校验依赖，环境检查仍覆盖全部工具。quarTeT 与 LR 的精确集成补丁和已知边界已同步配方文档。

### 轻量验证记录

- 原生 trace 及三个工具的受控来源重建、LR 染色体别名：选定 9 项通过；批次隔离、基线篡改、线程变化缓存复用/篡改失效：3 项通过。
- 选定运行时依赖隔离、DEGAP 联合候选岛、UTF-8/FAI：3 项通过。LR driver 的 `255` 日志路径及原始驱动篡改拒绝：1 项通过。
- 实际固定 TGS splitter/writer 和 LR Perl sequence writer 仅执行微型构造输入；quarTeT 使用真实 Python 3.11 与模拟空 PAF 的 aligner，确认两类输入均尝试。它们不等于真实 reads 原生端到端验收。
- 开发过程中一处 LR 夹具误把 Bash 的 `-o pipefail` 当成工具输出参数，已修复夹具并清理其两份已知临时输出；未删除其他工作区内容。
- 未求解或升级真实共享环境，未运行浏览器、App 构建或全量测试。最终统一验收仍待完成。

下一步优先接通编号布局的公共入口、精修后的原子发布/报告/交付和 App 协议，而不是把内部 staging 当成用户可用的最终结果。整体 A01–A18 未完成。


## 2026-11-22：编号布局进入实际读写与 LGZ-only 交付

### 已接入的运行路径

- 准备脚本和生成的 shell 通过同一布局解析器定位输入、参考/染色体比对、q0–q3、metadata、logs 与私有命令；q0 多物理目录发布有回滚保护。冻结证据中的逻辑 artifact 名称仍按原身份解释，不重写旧科学回执来伪造新引擎完成记录。
- `run_all.sh` 可从 `.runtime/prepared` 启动，且先验证布局 manifest；未知/不完整布局不退回旧 runtime。代码更新及其备份/回滚、进程检查使用同一物理目录。没有在本轮实际更新任何用户安装或项目。
- 注释库快照、分组、增量工具和 TSV FASTA 导出补齐布局解析；生成的增量 staging 副本也按编号路径读写。增量全回归仍留到最终统一检查。
- LGZ 过程报告位于 `06_report/01_lgz/report.html`，给 `06_report/report.html` 的总体入口留出独立位置，避免旧报告渲染覆盖后续精修总览。**总体报告与精修比较页尚未接通。**
- 已标记编号工作区的 LGZ-only 归档输出改到 `07_delivery/00_lgz/`，归档 staging 在 `.runtime/delivery_staging/00_lgz/`。只打包明确 staging，不递归归档整个工作区。
- LGZ-only App 投影明确从编号物理路径还原原有逻辑包路径，避免把 `01_inputs`/`02_alignments` 意外当成 App 协议升级；不把内部转换的原始 reads 随包交付。精修 App 新协议仍是后续独立工作，不能用本项兼容性代替精修导入验收。

### 必要轻量检查

- 前序实现已跑过受控真实 MUMmer q0→q3 的新旧布局序列一致性与完成阶段复用，本轮不重复运行该组。
- 编号 launcher 及非法 manifest 拒绝、编号 runtime 更新/回滚保持原始科学文件：选定 2 项通过（2.960 秒）。
- 实际 `prepare.sh` 在预先标记的空编号工作区完成输入准备、脚本生成、注释库冻结和 LGZ 报告；选定 1 项通过（32.445 秒）。仅准备，不运行全流程。首次使用系统旧 MUMmer 被能力检查拒绝；改用已有 `cgat-server/bin` 中的 MUMmer4 后通过，没有安装或升级环境。
- 现有 LGZ 夹具在新旧布局分别投影 full/light App 包，逐文件字节一致；编号工作区中的私有 reads 不随包进入。选定 1 项通过（15.185 秒）。这是 Server 打包侧兼容性，不是 App GUI 验收。
- 新增小归档检查覆盖 `--out/07_delivery/00_lgz` 物理位置、私有 staging 和不递归打包工作区。
- 本轮还修复了测试模块导入路径；未以跳过依赖检查或降低源码/输出完整性验证的方式让测试通过。后续仍统一执行完整测试，不把这些选定检查累加宣称独立全量验收。

### 仍未开放的边界

新工作区默认初始化、真实旧项目迁移适配器、公共 reads/tools 追加与执行入口、每工具 Final Path/报告/App 包联合发布、原生部分任务恢复、App 导入/导出和双架构原生验收均未完成。当前代码支持显式编号的受控准备与 LGZ-only 打包；不据此宣布整体用户流程可用。master、远端作业及现有工作区保持不变。


### 同日补充：参考比对恢复运行库同步

编号路径接入后，运行库生成器的严格 hook 检查正确拒绝了仍按旧路径声明的 `prepare.sh` fragment。没有放宽或跳过该检查：canonical 实验源的精确 hook 同步为布局解析调用，并补齐参考恢复中的目录、metadata、私有 attempt 及 journal 路径检查。编号布局仍只允许 adapter 自有的 `*_vs_ref/.long-cigar-attempt-*` 输出；独立原型不得向准备工作区写入。

共享 `workspace_binding.py` 复用 Server 的实际布局解析器，不复制第二份目录映射；旧无 marker 夹具保持原路径，带 marker 的项目缺少解析器或 manifest 无效时明确失败。参考映射不再因为找不到旧 `metadata/prepare_options.tsv` 而静默落回默认参数。

选定的 3 项纯路径/配置/权限范围检查通过（0.047 秒），不执行比对。生成的 runtime 和两个内容 profile 按 canonical 源重新生成，最终统一回归前仍不宣称真实参考恢复全流程或旧项目迁移验收完成。


## 2026-11-22：精修报告、比较分母与联合发布事务

### 已实现并接入内部批次

- `refinement_reports.py` 为成功及失败 attempt 生成静态、可搬移的报告；成功报告逐页列出全部原始 gap、原生 job/日志、候选与接纳决定，列出原生和 CGAT 最终序列的长度、N 数及逐染色体 hash 差异，不评选“最佳工具”。每页最多 200 个原始 gap。
- DEGAP 的原生 gap ID、job 配置和执行结果映射回共同原始 gap。日志与 JSON/AGP/detail 诊断按内容校验后随报告保存；原始 reads、完整原生基因组不复制进报告。诊断附件上限明确列出，超限仅显示 Server 路径文本及 hash，不生成失效链接。
- 原生 HTML 本阶段保留为可阅读的原文附件，不执行上游 CDN 脚本；CGAT 主报告完全静态、离线可读。该检查不证明上游交互式可视化已离线化，也不是浏览器验收。
- `refinement_overview.py` 由内部批次生成 `06_report/report.html` 和 `06_report/03_comparison/<batch_id>/` 的 JSON/TSV 比较。全部工具失败时，直接对冻结 LGZ FASTA 做有界扫描并核对逐染色体长度/hash，保留所有原始缺口；失败工具的单元格标为 `tool_failed`，不移出分母，不算作成功零填补。
- 总览仅在当前 attempt 与经过验证的完整发布回执一致时链接最终 FASTA/Final Path；目录存在、原生成功或 staging 完成都不等于发布完成。失败 attempt 有独立诊断报告，不生成最终序列。
- 原生执行回执新增 UTC 起止信息、原生 wall time 和发布前阶段耗时，保留实际线程预算；未测量的峰值 RSS 明确标为未知，不虚构资源数字。
- DEGAP 在顶层退出 0 后还必须提供完整子任务 summary/config，逐项核对 job 集合和计数。非零 child exit、异常或超时不能伪装成功；原版对 exit-zero 未解决任务使用的特定 `failed` 标签单独识别为未填补，不误当作计算崩溃。原生日志和 summary 纳入内容证据。

### 联合发布机制（尚待真实 App 打包器接入）

`refinement_commit.py` 在持有实际 workspace lock 时，将同一工具的 `05_final/`、`06_report/02_refinement/`、`07_delivery/` 作为一组发布。目录交换前设置 publishing fence，完整校验后写入唯一 committed 回执；读取方不得凭目录存在推断完成。旧成功目录保存在事务历史中，不覆盖无归属目录。普通错误回滚；中断可回滚未完成交换，或补写已验证结果的提交回执，不重跑原生工具。

发布要求调用方提供真正的、版本化的 App 完整包/轻量包校验器，证明两包的 Final Path 与逐染色体序列身份对应当前接纳结果。**当前只有事务 API 和受控夹具校验器测试；没有生产 App 校验器，没有用夹具结果开放公共发布入口。** 详见 `server-refinement-publication-contract-20261122.md`。

### 本轮必要轻量证据

- 静态报告：4 项通过（0.187 秒），覆盖搬移后逐链接/锚点存在、完整缺口分母、原生/接纳差异、转义、改写拒绝及附件大小边界。首次测试暴露模块不必要地依赖原生执行模块，已改为使用独立 orchestration 原语。
- 发布事务：5 项通过（0.624 秒），覆盖三目录提交、旧结果回滚、中断后 fence、补写提交回执、无归属目录保护及真实锁要求。这里的 full/light 文件是**事务夹具，不是 App 包验收**。
- 总览/失败报告 2 项及完整缓存复用的选定集成项通过（同组另一次误写测试类名的加载错误已纠正）；后续 DEGAP 子任务失败分类及候选来源重建 2 项通过（1.781 秒）。没有运行原生真实 reads、浏览器、App 构建或全量回归。

### 接下来优先完成的纵向链路

下一步直接落实真实 App 精修包生成/校验和 App 导入/导出，再接公共 `--gapfill-tools`、LGZ-only 追加、默认编号初始化及迁移适配器，把上述执行/报告/发布 API 串起来。不要继续把内部模块测试当作用户流程完成。原生部分任务复用、两架构固定环境/原生小样例及 A01–A18 最终统一验收仍待完成。


## 2026-11-22：真实精修 App 包、源序列校验与导入/导出

### 这轮推进的是纵向链路

- 新增 App 包 schema **5** / App Final Path schema **4**。旧 schema 2/3/4 保持原解释；旧 App 不会把新包部分导入为 LGZ 路径。新包同时保留精修 Server 路径原文和 App 投影，工具、run、baseline、来源、父片段、坐标 lift 均有明确绑定。
- `refinement_bundle.py` 从已验证 LGZ 与实际接纳结果构建完整包，再派生轻量包；补入的是实际 bridge 片段来源，不把整条精修染色体改名为单个新来源。FASTA 由来源重建，与已接纳 Server 最终结果校验一致。
- `refinement_bundle_validate.py` 验证完整文件清单、Server/App 路径投影、来源边界与负链，并在完整包中从源序列重建所有染色体。轻量包保留来源索引和 provenance，但明确无序列，不能假装可导出。
- `refinement_delivery.py` 生成真正的 ZIP/tar.gz 完整/轻量档案并安全解包校验；不使用 fixture-validator 冒充真实校验。`refinement_batch.publish_batch()` 已把它接到三目录发布事务，成功报告/最终结果/两类 App 包可在受控工作区一起发布。
- App Rust reader 在修改数据库之前校验新协议与源重建；现有项目模型持久化的是精修路径，能建立 `placement_mode=refinement` 的真实片段卡，并由现有导出器输出正确序列。这里的定位明确是相邻 LGZ 来源上下文，不伪造参考比对命中或 chr_assignment。
- 前端补上 schema-4 显示支持、精修卡样式/上下文说明，并在可编辑 Final Path 状态中保留父片段、改动/gap 关联和残余 N 来源。恢复预计算路径的文案不再误称总是恢复到 LGZ，而是恢复导入包实际携带的预计算结果。

### 发现并修正的真实路径问题

真实 prepare 写出的 locator 可能是编号路径，分区 FASTA 也可能与完整数据集 FAI 的 header/换行/offset 不同。打包器现在显式投影到可搬移 App 路径，并为每个 source locator 生成自己的 FAI；完整和轻量包均保留该索引。Python/Rust 的重建都使用分区自身的 byte offsets，只以完整数据集 FAI 作长度 catalog。

新受控夹具特意使用编号 locator、带描述的 header 和 47 bp 分区换行，避免仅在旧式单 FASTA 夹具上通过。旧冻结 q0 回执保持原文：q0 验证器仅对逻辑/物理路径拼写做同一 workspace role 比较，仍检查原始文件 hash，不比较“相似序列”来放行，也不改冻结科学证据。

精修 payload 另按实际 source/reference locators 收敛 sequence 白名单，剔除无关 attempt 的 accepted/native 数据和 reads；构建该视图时不先递归复制旧 DEGAP accepted 目录再丢弃，旧 LGZ-only 打包行为仍保留默认兼容；各工具的压缩包使用独立工具名根目录。精修最终 FASTA 改为 60 bp 换行，避免导入器为一个未换行染色体分配整行内存，序列内容、来源和坐标不变。

### 本轮检查边界

- 使用真正冻结的 LGZ scientific fixture，做显式受控 `GTNNAC` 部分接纳；没有执行真实精修工具。新 Python 包用例已验证完整/轻量路径一致、负链/残余 N 来源、篡改 bridge 后即使重封 manifest 仍拒绝、Server 投影篡改拒绝。
- 真实 ZIP full/light + 发布事务定向检查通过，含 archive root/白名单、源重建、发布后的最终报告状态；另覆盖不安全归档路径、重复 member 拒绝。不是原生工具/客户数据验收。
- Windows Cargo 的新协议定向用例验证实际 App 导入、来源卡初始化、再次导出与 Server 按染色体序列一致，以及轻量序列不可用。首轮暴露新 patch 不能伪装 chr_assignment 的 ordering 项，已改为由来源卡初始化建立，不弱化原有 assignment 校验。
- Windows Node 选定 4 项通过：新精修 lineage/残余 N 状态保留、无关 trace 不升级，以及旧 LGZ 投影和可编辑路径 round-trip。未运行生产构建或浏览器。
- 编号 locator/不同分区 offset 的 Python serializer 专项 3 项通过（0.972 秒）；真实 ZIP full/light → 校验 → 三目录发布的选定集成项通过（3.259 秒）。冻结科学回执原文保留也纳入用例。
- Windows Rust 新协议 4 项通过（0.27 秒），另选定 ZIP 入口用例通过（0.51 秒，内部覆盖 full/light 两模式）。ZIP 导入器在验证前写自己的 `cache/import.log`：只将这一个固定的运行期日志排除在 archive payload 清单之外；其他未知文件、数据库或改动仍拒绝。用例确认已有项目的人工 note 和数据库不被重复导入覆盖。
- 真实 tar.gz 读取另有 1 项微型检查通过（0.003 秒），确认不仅 tar member 正常，还会读到 gzip trailer 并拒绝损坏 CRC；未启动完整 tar.gz 原生/交付矩阵。
- 首次 Rust 编译暴露错误消息泛型边界已修复；中途两次检查命令使用了错误 cwd，修正路径后完成定向检查。未运行全量回归、升级真实环境或更动 master。

### 整体仍未完成

当前是真实包/校验/模型级闭环，不等于公共 `run_all.sh` 已支持本轮完整新流程。公共 reads/tools 配置和 LGZ-only 追加、默认编号 prepare、真实旧工作区迁移、原生部分子任务恢复、受影响新片段注释/比对与完整报告导航、四工具真实固定环境及两架构原生验收、A01–A18 最终统一回归仍继续实施。


## 2026-11-22：公共精修入口、默认编号目录与 LGZ-only 追加

### 本轮接入

- 新建 `run.sh` / `prepare.sh` 工作区默认使用实际编号布局。`--out` 包含输入、LGZ、精修、最终结果、报告和 App 交付；完整/轻量包不再散落到工作区父目录。已有未标记旧目录不被静默重新 prepare。
- 公共 `run_all.sh` 接受 `--hifi`、`--ont`、`--gapfill-tools` 和运行线程预算。固定顺序的 `refinement` 单元位于 `finalize_evidence` 后、LGZ 基线打包前；不再使用旧的 LGZ Step3 后立即插入、尚未终结科学证据的 `degap_gapfill` 单元。
- 新增 `refinement_config.py` 的保存配置、不可变配置快照和每次请求记录。reads/tool 属于下游设置，不被纳入 LGZ immutable 输入身份；增加/更换 reads 或工具不要求重新 prepare，也不将 typed reads 转成旧 QC 输入。初次准备前即保存配置，中断后仅 `-o` 可恢复 reads 选择。
- 未提供任何 typed reads 则复用保存配置；提供任一组则替换全部组，未提供的技术置空。无选择时有 reads 默认 DEGAP；显式 `none` 仅禁用本次执行、保留保存选择和历史。直接 prepare 的 `none` 是保存禁用配置。单技术工具不消耗未选择的数据或因其不可读失败。
- 新增公共 `post_lgz_refinement.py`，校验原始 LGZ 科学证明，再顺序执行/复用精修、建立报告、用真实 App 校验器发布。生成命令核对活父 runner 的 PID/start identity、主机、工作区和 run ID 后借用锁；独立执行持有自己的锁并使用独立 worker 进程组。
- 精修失败不会阻止后续 LGZ 基线交付，成功精修工具的发布仍保留；整次运行返回非零。中断不继续后续步骤；精修原生孙进程即使忽略 TERM、将输出重定向到文件，也不能在释放锁后继续写入。普通 LGZ 并行调度路径不因此改为另一套调度器。
- 新增 `lgz_final.py`，将真实且按来源核对的 LGZ-only 基线发布为 `05_final/00_lgz/`，有独立来源清单、残余缺口和明确 `refinement_applied=false` 的证明；发布使用持久化指针/暂存/恢复，不让基线冒用精修工具名。
- `refinement` 零退出还必须通过当前请求、batch、完整发布、LGZ 基线和总览/比较文件 hash 验证。只有退出码 0、目录存在或历史成功结果不算本次成功。
- 总览分别链接 LGZ 基线、各工具精修 FASTA/Final Path/来源及完整/轻量 App 包。终端末尾把 LGZ 包明确标为 **baseline / not refined**，不把它们显示为精修最终交付。具体入口与路径见 `server-refinement-launch-contract-20261122.md`。

### 检查边界

- 按用户要求，中间只做必要定向检查，没有运行完整回归、生产构建或浏览器。
- 配置/plan/活父锁/下游失败与假零退出/独立精修中断的初始 9 项轻量检查通过（11.530 秒）；后续仅选定重跑配置持久化、初次准备失败后 `-o` 恢复及真实 LGZ-only worker，3 项通过（3.743 秒）。修正了测试异常类型与一次检查命令 cwd，不修改生产校验以迁就测试。
- 新增真实 runner 的取消检查通过（1.230 秒）：原生孙进程忽略 TERM 且重定向输出，runner 返回 143，孙进程停止，锁释放，后续单元仍 pending；不执行任何精修工具。
- 实际 `prepare.sh` 的新目录检查通过（44.802 秒，使用本机已有 MUMmer4 能力检查），覆盖默认编号、保存脚本、计划顺序和独立 LGZ 报告。没有运行整个 LGZ/精修流水线。
- 独立 LGZ-only worker 使用冻结的真实 LGZ scientific fixture，完成实际来源索引、基线发布、总览和回执；确认原有输入/科学证明未改，最终 FASTA 或总览篡改后不能声明完成。最后选定重跑该 worker 和真实 full/light → 校验 → 发布用例，2 项通过（6.147 秒），覆盖总览最终 FASTA/两类 App 包链接。精修发布使用受控接纳片段和实际档案，不冒充真实原生工具验收。

### 下一步与未完成项

公共入口已接入上述生产模块，但整个新建/续跑用户流程仍需要最终统一验收。优先继续实际旧工作区迁移适配器与 CLI、安全复用原始已完成 LGZ 证明；然后补原生部分子任务恢复、受影响新片段比对/注释和离线原生可视报告。四工具的固定环境安装及 x86_64/ARM64 原生小样例、完整文档与 A01–A18 统一检查尚未完成。没有升级现有环境、触碰客户目录/远端作业或修改 master。


## 2026-11-22：完成 LGZ 的旧工作区显式迁移与原引擎冻结续跑

### 本轮纵向接入

- 新增 `tools/migrate_workspace.py`，可从新版已安装 Server 对旧目录执行只读 preview、持摘要确认的 apply，以及同事务 resume/rollback；不依赖旧工作区脚本理解新参数。操作命令和边界见 `server-refinement-migration-contract-20261122.md`。
- preview 绑定物理文件清单、被替换的生成脚本、运行库增补及真实 LGZ contract；apply 获取 legacy 独占锁后重新核对批准摘要。还检查本机独立脚本/原生阶段进程；活跃、外地主机或不明 owner 不被抢锁。跨节点和排队作业由操作者核实后显式 `--confirm-idle`，不是用本机缺少 PID 推断空闲；本轮没有连接任何远端或自动检查调度器。
- `MigrationTransaction` 增加带内容/权限绑定的 additions 和 adapter metadata，覆盖旧运行库没有的新模块/回执。所有新文件先进入持久化 staging，再以同文件系统原子 rename 安装，避免 live 目录里出现半份复制。中断可按已记录操作恢复，回滚仅移除仍与事务清单一致的新增文件，不删被修改的内容。
- 增加持锁、限当前进程作用域的 destination validation view。迁移仍处于 `validating` 时，真实 LGZ validator 能检查编号目录；普通 launcher、子进程和其他工作区不会因此获准运行。校验通过后才提交 layout marker；缺失迁移 journal 不能假装新建编号工作区。
- 新增 `migrated_lgz.py`：保存并核对原科学 stage receipts、完整执行计划和科学文件绑定。迁移时观察到的旧 runtime 另有快照/备份，不把“可能已升级的运行库”虚称为实际生产该 LGZ 结果的精确引擎源码。原科学回执保持原文，不生成新引擎 cache/checkpoint 来替代。
- 续跑时认证原 LGZ 基线后，reference handoff 与科学前缀不再执行。Runner/过程报告使用独立的 `SKIP_MIGRATED_LGZ` / `frozen_original_lgz` 标识，区别于本次计算和缓存命中；精修及真实 full/light 交付仍走共同入口。失败的冻结证明必须停止，不能退回新引擎重新计算；修改 LGZ 科学参数需新目录。
- 迁移事务安装新 launcher、打包/导出模板及运行库，更新 mutable launch/typed-reads 路径配置，保存被替换脚本原文。无正式 SOURCE 元数据的开发源码生成明确 unreleased runtime 记录，不沿用旧 Release 标识冒充新版正式来源。已冻结的旧科学命令明确阻止直接重跑，而不是重新创建根目录 data/grt 等影子树。用户 notes/无关文件不被覆盖。

### 必要定向证据

- additions 安装后中断/恢复、只回滚未修改的 owned additions、destination view 作用域与子进程隔离、原有移动/备份用例共 4 项通过（1.169 秒）。这不是全部故障注入矩阵。
- 初次纵向检查已完成真实迁移、升级后的 public run_all、原引擎前缀跳过及完整/轻量基线包，在用例最后恢复删掉的回执时因测试未还原原文件 mode 而失败；修正测试恢复动作，没有放宽生产校验。
- 其后 public migration preview/apply → public run_all 受控链路通过（25.651 秒），确认原 data/metadata/grt 科学字节保持、旧 runtime 备份、无旧命令执行、无 reference handoff、报告明确冻结执行、两个实际 ZIP 基线交付、没有新引擎 reference checkpoint，删去回执/改动基线拒绝复用。之后补齐完整 plan 绑定和原子 staging 安装；最后串行运行迁移新增文件恢复/回滚、validation view、旧移动恢复、普通 reads 追加入口与 public 迁移链路共 6 项定向检查，通过（33.756 秒）。额外断言在 plan 后追加科学步骤也必须拒绝，而不是重新计算 LGZ。

- reference handoff 的原引擎冻结判断同时更新生产入口和 canonical overlay，严格 runtime profile 同步通过（42 文件；production_ready=false，未改正式发布）。没有绕过 overlay/哈希校验。

### 仍需继续

当前适配器只认证 **完整且真实 contract 已通过的 LGZ 基线**；未完成旧阶段的版本/内容安全迁移与部分原生子任务恢复仍未完成，不以现有完整基线适配器代替。真实四工具固定环境与双架构原生验收、新片段比对/注释、离线原生可视报告和 A01–A18 最终统一检查仍保留。没有升级用户环境、触碰 master/客户目录/远端作业或执行真实精修工具。


## 2026-11-22：原生完成回执、重新接纳恢复与原始任务报告

### 本轮接入

- 新增 `refinement_native_checkpoint.py`，把四种工具的原生执行/完成校验与 CGAT 接纳拆成两个可恢复阶段。完成后先以实际输入、固定运行时、命令/参数、原始染色体输出及子任务/迭代状态写入独立内容回执，再进行候选接纳、来源重建与最终 staging。
- Native key 绑定真实数据和命令，归一化显式 attempt-local 路径及线程预算，不把接纳适配器代码 hash 当成原生程序输入。接纳修复或下游失败后可用新 attempt 重新解析同一原生证据；无原生重算，也不复制/改名原生历史目录。完成校验器修订另行记录，新版本须重验原封存字节/清单，不能盲信旧校验或仅因日志代码改动重跑原生工具。
- DEGAP 顶层退出 0 仍检查所有配置子任务状态；失败子进程不会生成 native checkpoint。LR 检查连续迭代、必需行记录和提前终止时确实无剩余 N。TGS/quarTeT 缺失声明产物、空/异常染色体仍不算完成；quarTeT 只接受固定代码中明确的无候选/无有效 flank 终止。
- Native 复用保留原始 producer run、命令、线程/耗时和校验来源；本次 `native_executed=false`、`native_reused=true`，本次原生耗时为零，requested budget 与历史实际线程分开。重新接纳仍从来源真正重建 Final Path，而不是搬运原生/旧 LGZ 的整条染色体。
- 成功/失败报告都能沿 `native_origin` 读到旧任务、child jobs、日志和原生 gap 报告；不把旧任务伪装成新 run 的 native 目录。接纳失败显示 `phase=admission` 且 native 已成功，仍不声明最终结果。原生诊断文件变化不会被报告重新 hash 覆盖而伪装成原证据。
- 补齐 TGS 名称/结构明细、quarTeT detail、LR `info_filter2` 等已知文本协议的离线查看。FASTA/二进制仍不当作报告资产复制；原生驱动脚本保留 Server 来源/hash 并明确标为 server-only。
- DEGAP 无剩余缺口时记录明确 no-op，不扫描/hash 未使用的大 reads。另将迁移 staging 的权限设定移到 fsync 之前，保证记录的 mode 与已刷新的 inode 元数据一致。
- 完成边界/路径/资源语义见 `server-refinement-native-resume-contract-20261122.md`。旧的未封存 native 文件夹没有被默认为可复用结果。

### 必要定向检查

- 三工具真实解析/来源重建、TGS 零退出缺产物拒绝和 DEGAP 候选重建共 3 项选定检查通过（5.365 秒），使用受控 producer 协议夹具，没有执行实际原生工具。
- 新 checkpoint 用例初始 5 项通过（15.878 秒），内部覆盖三个新增工具和 DEGAP 的原生完成后接纳失败恢复、只执行一次 producer、保持历史文件、reads/runtime/证据/回执变化拒绝复用、子进程失败拒绝完成，以及批次/失败报告阶段归属。
- 无 gap 不读 raw reads、完整结果缓存复用和新增文件 mode/恢复用例通过。同期旧 quarTeT 无候选用例因此前已引入的 60 bp FASTA 换行而把相同序列误判为变化；修正为校验 header 与 DNA 序列，不改生产换行策略。
- 最后选定运行校验器升级重验、三个新增工具的恢复/离线文本资产、DEGAP 子任务恢复/原报告和 quarTeT 显式无候选，共 4 项通过（9.160 秒）。新校验器对同一封存字节重验后，producer 仍只调用一次。没有启动全量回归、App 构建、真实四工具环境或远端作业。报告资产策略另有 1 项微型检查通过（0.001 秒）：已知原生文本可嵌入，FASTA 与驱动源码保持 server-only 并准确标注。

### 剩余工作

原生程序内部尚未完成的子任务/迭代恢复仍待实现，不能把本轮“已完成原生阶段再接纳”当作内部断点续跑全部完成。未完成旧 LGZ 阶段迁移、新片段比对/注释、真正的离线原生可视报告、真实固定环境和双架构原生验收及 A01–A18 统一检查仍保留。另外需核对同一科学 run_id 下报告/交付生成器更新的发布版本：当前 `publish_batch` 仅凭 run_id 相同跳过已有发布，会漏刷新报告/包，后续应按各产物绑定处理，而不是重新跑原生或科学接纳。master、现有环境和客户/远端任务未操作。


## 2026-11-22：科学结果复用与报告/交付刷新解耦

- 修复 `publish_batch` 同一 run_id 直接沿用旧发布的问题。新的交付 generation 单独绑定接纳证明、报告 manifest、压缩格式与序列化/校验 helper 源码；科学结果未变但报告或打包器变化时，只刷新对应产物和发布回执。
- 两种 App 档案都检查报告自身文件清单与来源绑定，再与当前发布的报告 SHA 核对。相同 DNA/run_id 不能使旧档案和新报告混搭通过；验证缓存同时绑定完整交付声明、当前 provenance 和校验器源码，不让旧缓存隐藏声明变化。
- 发布 journal 区分 unchanged 区域；报告/打包器单独更新时，`05_final` 保持原 inode/mtime，不复制或交换整个基因组。普通错误和进程中断仍按事务恢复，只交换发生变化的区域，科学文件和原生结果不动。
- 旧的无 generation 档案仍可实际解包检查；不冒充当前生成版本，下一次发布重建交付而非重跑原生或接纳。更新了中英文发布契约，并同步两份 runtime profile。

### 必要轻量检查

- 事务与原有交付定向检查 9 项通过（2.562 秒）；新增真实 full/light 刷新/声明缓存检查 2 项通过（5.670 秒）。覆盖相同配方不重新打包、报告更新、序列化 helper 变化、最终路径不变、拒绝混搭及中断回滚。
- 报告内容修改后仅重封 App 外层清单仍被拒绝，以及旧声明可检验，选定 2 项通过（1.587 秒）；最后只重跑扩展后的声明/当前 provenance 缓存检查 1 项，通过（1.621 秒）。这是 12 个不同的定向测试，不是完整统一验收。
- 没有执行真实原生工具、环境安装、浏览器、生产构建、完整回归或远端操作。后续仍需内部子任务恢复、未完成旧流程迁移、新片段证据、离线原生可视报告、中英文用户指南及真实固定环境/双架构和 A01–A18 最终检查。没有改动 master 或发布版本。


## 2026-11-22：中英文用户指南与旧说明纠正

- 新增随 Server 源码放置的 `REFINEMENT.md` / `REFINEMENT_zh.md`，完整说明环境、默认 DEGAP、四工具读取分配/固定版本、LGZ-only 原地追加、保存 reads 整体替换、`none`、编号结果/报告/交付、实际精修 Final Path、App Full/Light、恢复与显式迁移命令。
- 更新仓库根与 GPM/Server 共六份 README，移除当前源码“只能写额外 FASTA、App 仍显示旧 LGZ”“旧计划永不能追加”“交付只在工作区旁边”的过时说明，补工具参数与真实日志/报告路径。保留已发布 v2.0.21 的下载、版本和旧布局介绍并明确版本边界，不暗示功能已经发布。
- `REPORT.md` 区分 LGZ 过程、精修与比较三类报告；包内 `metadata/` 等协议路径不当作工作区 `.runtime/metadata` 改名。指南公开未完成原生内部恢复、未完成旧任务迁移、新 patch 证据、离线交互原生报告及真实环境/原生验收边界。
- 轻量文档检查通过：每语言 7 个 shell 示例均 `bash -n`，去注释后中英文命令一致；本地链接和四个源码 revision 与锁定清单一致。发布下载指南一致性检查通过，版本仍为 v2.0.21；未构建站点、未打开浏览器、未安装环境或运行科学流水线。
- 文档追踪另发现手动 App `DEGAP-JOBS` 的 `degap_results.py` 仍直接检查 `server/metadata` 并使用 `server/.run_all`（如 `collect`、`publish`、`collect_locked`）；新的自动精修交付不使用这条收集器路径。旧布局流程仍保留，但编号工作区的手动收集/增量路径需要后续适配并验证，不用文档改名掩盖代码缺口。README 已明确这两条入口的边界。


## 2026-11-22：编号工作区的人工 DEGAP 候选目录与原 LGZ 隔离

- 沿实际调用链确认：只替换旧 `metadata/` 路径会让手动收集追加主表，破坏原 LGZ/迁移冻结证明。因此先落独立契约 `server-refinement-manual-catalog-contract-20261122.md`，再新增 `degap_manual_catalog.py`。编号布局的候选来源/比对/包缓存在 `04_refinement/01_degap/06_manual/01_catalog/<generation>/` 分版本保存，以 `.runtime/manual_degap/current.json` 为准，不修改主工作区 LGZ metadata、原始 FASTA 或自动精修 Final Path。
- 收集器 staging、命令和来源查找均按实际布局处理，继承已验证人工目录并保留先前候选的独立 FASTA 来源；新候选追加只做自己的比对，旧候选包验证复用。包仍用原 incremental App 格式及原导出 receipt，不自动编辑用户的 Final Path；旧布局保持原写回语义。
- 原始表、完整候选文件/符号链接与不可变 token 包 registry 都按内容绑定。原始大 FASTA 在单进程内依 device/inode/size/mtime/ctime 复用已算内容 SHA，不把这种缓存持久化，也不因恢复 mtime 漏过内容修改。收集结束重新核对结果 receipt、已收集候选快照和只读比对输入，拒绝运行中混入的新内容。
- 新目录封存后，结果 ZIP 与 current 指针在真实工作区锁下通过持久化 pending/plan/原字节备份发布。中断可完成已验证的新集合或回到旧集合，未知变化的 ZIP/指针/备份拒绝覆盖；未登记目录和 ZIP 文件存在本身不算成功。CLI 明确打印“Manual candidates only; Final Path unchanged”和实际候选目录。

### 必要定向检查与边界

- 收集器及新目录事务两模块 15 项定向测试通过（1.219 秒）；此前新事务 6 项含 process-local 原始 FASTA hash 复用检查通过（0.471 秒）。覆盖旧布局不回归、编号布局连续两批追加/重收集不重比对、原始文件字节不变、来源连续、当前目录/缓存篡改拒绝、发布失败回滚、进程中断、未知输出保护。
- 最后新增的候选快照输入漂移回归通过（0.130 秒）。初始夹具改错了原生输出文件，已有 collector 快照本来就应不受其影响；已改为篡改真正被消费的 `.gpm_degap_candidate.fa`，生产接纳条件未放宽。
- 真实旧 LGZ 科学夹具经过显式迁移后，使用迁移实际安装的 `degap_results.py` CLI 及新 helper 完成候选收集；原 `verified_baseline`、完整 `validate_contract` 和原科学文件字节均不变。单个定向检查通过（13.080 秒），比对是显式的受控 PAF 生产器，不冒充真实 minimap2/DEGAP 验收。
- 全目标仍未完成：App 导出仍写死旧运行库和便携来源路径，精修 patch 的目标 track 不能直接当作源 dataset，旧人工缓存接续也需来源绑定适配；这些在新契约中列为必做项。已同步中英文使用边界，不宣称人工全链路就绪。原生内部子任务恢复、未完成旧任务迁移、新 patch 证据、离线原生可视报告、真实固定环境/双架构及 A01–A18 统一验收继续保留。未运行完整回归/浏览器/生产构建、未操作远端或升级现有环境。


## 2026-11-22：App 人工任务运行库与种子来源身份接入

- 先记录 `server-refinement-manual-source-contract-20261122.md`，再移除 App 脚本对旧 `.prepare_lib` 和便携 FASTA 路径的执行依赖。运行时在 Server 解析真实布局并检查声明运行库；缺失 helper、损坏标记或未完成迁移不静默退回旧路径。
- Full/Light 包增加 `metadata/server_sources.json`，绑定原始及已接纳 patch 来源。App receipt 的 token 绑定具体每侧成员/截取/方向；Full 可绑定实际消费片段的 SHA，Light 使用原 Server FASTA 身份。Server 按原始目录、已封存精修来源和人工候选目录解析，验证长度/内容，用私有索引提取和 IUPAC 反向互补，不往原始 FASTA 写索引。
- 原生运行前后及 App 导入均核对消费的种子与来源 proof；旧 receipt 仍保留兼容。人工 patch 优先沿用既有派生 track；仅上下文的种子使用真实 primary track 并显式标注“不是同源证据”，不篡改来源 dataset。来源查找只核对封存证明与被消费文件闭包，不扫描无关全基因组/历史候选阻碍有效来源。
- Python 来源/实际运行库模板 6 项通过（2.062 秒），Windows 已构建二进制中的来源 map/反向截取 2 项通过（0.04 秒）；原有人工导出 4 项此前通过。按用户要求未运行完整回归/生产构建/浏览器。
- 实际 Windows App 导出 → WSL Server 执行/收集 → 同一 App 数据库公开导入接口的受控桥接通过。Server 来源路径/换行与 App 不同；导入真实候选 `AACCGTTTTT`，原有手动 Final Path 完全未改，原 LGZ 文件集合/字节未改。原生阶段和比对是明确的受控 producer，不冒充 DEGAP/minimap2 或生物学验收。10bp 候选不产生合格真实 minimap2 命中，保留了该拒绝条件，再显式使用受控 PAF 完成协议检查。
- 收集阶段单独恢复且核对已完成原生 FASTA/receipt 的 SHA 与 mtime，未重跑 native。初始导出单测 DB 缺少真实项目成员/原始染色体排序，补的是受控夹具初始化而非放宽导入器。最新 `-B` 字符串和夹具 SQL 已落源码但尚未重新链接；最后统一验收必须重新构建最新 Rust 并生成干净桥接目录。
- 未完成：旧人工缓存的 receipt-bound 接续、未完成旧 LGZ 的迁移/续跑、原生内部子任务恢复、新 patch 比对/注释、原生离线交互报告、真实固定环境与四工具/双架构验收和 A01–A18 统一检查。未修改 master、客户目录/远端作业或现有环境。


## 2026-11-22：迁移前人工候选缓存的有据接续

- 扩展人工候选目录契约后新增 `degap_legacy_cache.py`。仅处理已提交完成-LGZ 迁移清单中的旧 `.run_all/degap_packages/<token>.json/.zip`；核对原引擎基线、迁移映射/未变字节、原 recipe、消费 seed/runtime/source proof、当前候选、历史增量包 manifest/locator 和已迁移实际序列，再复制到新的不可变 registry 并记录 adoption 依据。旧缓存和主 LGZ 表不写回。
- 有效缓存接续不执行 native 或旧候选比对，后续重收集直接走 registry。缓存/来源在安装及封存前重新检查，进程内内容 SHA 复用已有文件身份栅栏，不因重复核对反复读取未变化的大包。新编号目录中的散落缓存、迁移后补入/篡改的旧缓存或任务不一致均拒绝，而不是重跑已存在名字的候选。
- 未知旧结果 ZIP 的保护前移到 staging 前，避免先做无用比对才拒绝覆盖。保留原 ZIP，可将未改动的原 jobs/receipt 复制到新的空收集目录，不重新导出 token 或重跑原生任务。同步中英文使用边界；没有以缓存接续权限扩大为覆盖外部 ZIP 权限。
- 最终本段 4 项定向检查通过（15.425 秒）：实际旧收集器产生旧包 → 真实显式迁移 → 迁移安装的新版 CLI 接续/再次收集；旧包 bytes 不变，未触发禁止运行的比对器，native 文件/mtime 不变，原 LGZ 科学契约/完整证明/文件 bytes 不变。另覆盖未知 ZIP 保留、无迁移依据缓存、缓存漂移/未知 token、正常编号目录连续追加与现有目录校验。旧包初次比对使用受控 PAF，不冒充真实 minimap2/DEGAP 验收。
- 本段未运行全量回归、生产构建、浏览器或环境安装，未触及 master/远端/客户工作区。全目标继续保留：未完成旧 LGZ 阶段适配、原生内部部分子任务复用、新 patch 比对/注释、原生离线报告、四工具真实固定环境/双架构与 A01–A18 统一验收。


## 2026-11-22：精修新来源的实际测量、坐标证据与 App 协议接入

- 先记录 `server-refinement-source-evidence-contract-20261122.md`，再接入独立 `source_evidence` 阶段。只对已接纳的新 patch 来源做参考 PAF 和 tel/cen 扫描，使用原准备参考、原 preset、冻结库和现有线程总预算；不重跑 LGZ 或补洞工具，不向原始/已接纳来源写索引。原参考、库及已有来源注释也纳入跨工具共享输入封存。
- 测量代际在 `04_refinement/<tool>/04_accepted/<run>/01_source_evidence/<generation>/` 内容绑定缓存，测量和打包/报告生成器分开。报告/包变化不重跑已完成测量；新原生/admission 配方未被这些显示与交付模块改变。包内 `source_intervals.tsv`、`final_annotations.tsv` 按真实切片/方向映射，保留“完整来源标记”和“截断来源支持”的区别，不把来源扫描冒充完整终版基因组重扫描。
- `no_hit`、`disabled`、`no_rules`、`no_chr_library` 分开。patch 仍是上下文放置，不新增假的原始分配或同源锚点；独立 PAF 状态来自真实输出记录。Full/Light 携带同一 PAF、来源注释与证据投影；生产交付必须绑定测量 receipt 和匹配报告，不能回到未测量状态作成功交付。旧无该 capability 的 schema-5 包仍保持其原有 `not_measured` 语义。
- Python 和匹配 App 校验实际 PAF 名称/长度/CIGAR/记录数、库身份、完整 patch 放置覆盖与来源到终版的坐标重建；仅更改状态名称或重新计算外层 checksum 不能使假命中/错位通过。新增双模式导入、注释保留、精修序列再导出及错误包拒绝的 Windows 用例和真实序列化冻结夹具。
- 实际检查发现原内嵌 tel scanner 在独立子进程中缺少路径函数导入并仍用旧目录。提取共用 `tel_scan.py`，两布局和新 patch 使用同一 literal motif/反向互补算法，执行时校验冻结快照；外层 checkpoint 绑定该 helper。相关真实 prepare/cen 集成用例改为通过实际 WorkspaceLayout 取路径，未运行整个 prepare/科学流水线以做中间检查。
- 测量失败也保留命令、查询、日志及 failure receipt，绝不留下可作完成依据的 receipt；失败报告链接这些诊断。重试保留已完成 native/admission 结果，失败/中断的来源子步骤不因存在文件而冒充完成。

### 本段必要检查与证据边界

- 最终 13 项定向 Python 检查通过（9.494 秒）：真实开发机 minimap2 对 6bp 受控接纳来源产生合法无命中；冻结规则、受控 nucmer/show-coords、CEN 空库/无规则、反向/切片/重复来源坐标；缓存复用、来源/参考不变性、输入漂移、重新封装的假状态/坐标拒绝、实际生成的编号 tel 命令、Unicode/前导连字符名称；来源阶段独立失败；真实 Full/Light 归档校验与原子发布。
- 另在失败诊断接入后单独检查失败日志保留/恢复、缓存原始数据不变性及归档发布，3 项通过（5.435 秒）。初始归档定向检查发现一个新 receipt 路径的 str/Path 传参错误，已按既有 safe-file 接口修正调用，没有放宽生产校验。
- Windows `cargo check --lib --tests` 通过（41.82 秒），只做编译/类型检查，没有链接并执行新增 App 用例。新冻结夹具来自实际 serializer 和来源重建；其补洞候选、tel 规则和 MUMmer 输出是明确的受控材料，不冒充原生四工具、固定环境、真实 MUMmer/双架构或生物学验收。
- 没有运行全量回归、浏览器、生产构建、环境升级、远端作业或发布。全目标继续保留：未完成旧 LGZ 阶段适配、原生内部部分子任务复用、原生离线可视报告、真实固定环境/四工具/双架构，以及包含最新 App 运行闭环的 A01–A18 最后统一验收。


## 2026-11-22：quarTeT 原生内部逐输入比对恢复

- 先扩展 `server-refinement-native-resume-contract-20261122.md`，再实现消耗产物单元。整段 native checkpoint 仍优先；中途失败后使用新原生目录，仅恢复已封存的 PAF，不迁移旧 native 树，不修改固定源码或科学参数。封存同时绑定原生数据/版本/命令、实际线程、launcher/helper 和该次真正消耗的 reference/query FASTA 内容。
- 新增 `refinement_native_runner.py` 和 `refinement_native_units.py`。显式区分原科学命令与实际 launcher 命令；在 `02_jobs/<run>/native_units/<key>/` 保存不可变消耗副本及原 producer 回执，`native_launch.json`、`native_substeps.json` 记录逐输入实际计算/恢复情况及生产 run。恢复只查询原始 producer，不串接派生缓存链。
- A 完成而 B 失败时可复用 A，再执行 B；空 PAF 是固定 `allow_empty=True` 规则下完成的无命中，不遗漏后续 reads 输入。整个原生成功阶段仍须覆盖每个所选输入及真正完成的输出/明确无候选条件。恢复不会跳过原生解析/整合、CGAT 接纳、来源重建或最终发布检查。
- 原生完成证据包含单元回执及真正消耗的 PAF。修改数据、线程、运行时/helper、损坏/符号链接缓存、错 CIGAR、缺失输入、伪造原 producer 状态或改变已消费 PAF，不会被当作完成。完成校验器版本同时绑定单元校验 helper；修正完成检查后重验原封存字节，不因此重算已完成原生科学结果。
- 固定源码的真实检查发现 `util.minimap` 把 PAF 放入 `tmp/`，原空结果检查只找根目录；现覆盖真实位置，并保留历史已封存/受控根目录证据兼容。成功/失败报告包含逐单元来源、计算/复用统计与诊断；中英文用户指南注明只有 quarTeT 的该边界当前接入，其余工具内部恢复不冒称完成。

### 本段轻量证据

- 11 项定向检查通过（11.603 秒）：新恢复单元用例及既有三工具完成后再接纳、校验器升级重验。不是全量 Server/App 回归。补齐来源封闭与元数据形状检查后，最后 3 项检查通过（2.470 秒）：非法对象/执行结构的缓存失效、重新封装当前回执仍拒绝原生产者失败状态，以及固定源码实际 CLI 的失败/恢复/整段复用。
- 可选 `CGAT_TEST_QUARTET_ARCHIVE` 用例安装校验过的固定 quarTeT 源码和既定兼容补丁到隔离临时目录，使用本机 `minimap2 2.26-r1175`，注入第二输入退出 7；实际比对调用顺序为 A、B、B，第三次整段 native 复用不再比对。PAF 为短序列真实无命中，不是补洞生物学正确性或固定 conda 环境验收。独立冒烟回执/日志副本保存在 `/tmp/cgat-quartet-partial-evidence-20261122-a5m6ophb/`，副本不是可继续运行的迁移工作区。
- 未启动全量回归、生产构建、浏览器、现有环境升级、远端作业或发布。继续保留 DEGAP 单 gap、TGS 内部阶段和 LR 迭代恢复、未完成旧 LGZ 阶段迁移、原生离线可视报告、真实固定环境/四工具/双架构，以及最新 App 运行闭环与 A01–A18 最后统一验收。master 和客户工作区未改动。


## 2026-11-22：DEGAP 终止 gap 子任务复用与原生调度闭环

- 先扩展原生恢复协议，再新增 `refinement_degap_units.py`，由公共 launcher 接入。固定 `AutoGapfillerPart3.JobExecutor` 的原 ProcessPool、`--work 1`、LEFT/RIGHT 依赖和科学参数保持不变；只在真正执行 child 的边界封存/恢复终止结果，未修改 bundled DEGAP 字节或其版本。此阶段不恢复预处理或未完成的延伸轮次。
- 新 attempt 重新执行预处理、检测和 setup。单元 key 绑定实际 reads/index/stat/split 文件、两个 flank（包括明确缺失的 flank）、真实生成命令的已声明路径角色、gap 几何、原 raw-input/runtime/helper 和线程。只复制原生消费者需要的顶层 final FASTA 与日志；不搬迁旧 round 树，不接受裸 `checkpoint.info`、`.skip_right` 或存在性作为完成依据。
- 恢复成功 LEFT 后仍由原生调度器跳过 RIGHT；恢复固定版“退出零但未补上”的 LEFT 后仍调度 RIGHT。复用结果正常返回 future 并进入完整 native summary，原日志字节保留，当前恢复耗时与原生产者时间分开。非零/error/timeout 不生成完成回执；另一个 gap 失败时已封存 gap 保留可用。
- Native 完成同时核对子任务覆盖、LEFT 成功才允许跳过 RIGHT、配置几何、真实已消费字节与选择的合法 FASTA。多份 eligible final FASTA 的原生选择保留但不做部分复用，避免改变上游 glob 选择，也不因此否决合法原生运行。新生成的脚本只允许一条与 job/flank/direction 匹配的原生命令，保留 shell-safe Unicode/标点，防止未知目录别名进入准备输入。
- 成功/失败报告纳入单元回执、原生产者快照和 child 诊断；公开中英文指南区分已实现的 DEGAP/quarTeT 边界与仍待接入的 TGS/LR。恢复仍通过原生分析/整合和既有 CGAT 接纳、来源重建及 Final Path 发布，不新增 LGZ 整体复制或失败回退路径。

### 本段必要轻量证据

- 最终 9 项定向检查通过（24.383 秒）：新增 6 项 DEGAP 恢复用例，以及既有 quarTeT 恢复、完成校验器升级和 DEGAP 接纳来源重建。覆盖真实 fork/shell、未补上 LEFT 后 RIGHT、原 LEFT 成功后跳过、多候选不部分复用、reads/线程/缓存损坏、几何/跳过原因/遗漏任务/消费字节，以及 Unicode、明确缺失 flank、脚本和目录别名。
- 去掉每完成一个 child 都重扫并重写全部单位摘要的二次方元数据工作：worker 只提交自身 durable 回执，parent 退出时汇总一次；LEFT 依赖预先建索引。未改变原生调度或科学参数，未以单元检查冒充整流程性能基准。没有执行全量回归。
- 调度器/管理器/分析器取自 lock 绑定 manifest 校验过的 bundled Part3，子任务使用真实 fork worker 和 bash。预处理、child 组装和整合 FASTA 是受控夹具，不冒称完整 DEGAP、固定 conda 环境、双架构、真实补洞生物学或 App 验收。
- 全目标仍保留：TGS 原生阶段、LR 迭代恢复、未完成旧 LGZ 阶段迁移、原生离线可视报告、真实固定环境/四工具/双架构、终止与残留进程故障注入，以及最新 App 闭环和 A01–A18 最后统一检查。没有升级现有环境、运行远端/浏览器/生产构建或发布；master 和客户工作区未动。


## 2026-11-22：TGS 原生比对/校正命令恢复

- 先记录恢复边界，再新增 `refinement_tgs_units.py`。核对真实 bioconda build-4 档案 SHA 与脚本 SHA；不把不同的上游脚本当作该分发版。运行私有 driver 副本，仅校正新位置的 helper 查找并在原参数检查后路由 minimap2/Racon；原脚本、科学参数和运行时 lock 没有修改。实际 launcher、原脚本 SHA、私有 driver/wrapper hash 均进入回执。
- 原分块/轮次循环、候选选择、filter/merge、gap filling 与 seqgen 继续执行。恢复仅回放完成命令的 stdout/stderr，不恢复 done tag，因此不会丢失 shell 变量或跳过后续 chunks。HiFi `--ne` 与 ONT 原生 Racon 路径分别按实际原生命令检查有序阶段覆盖。
- key 绑定实际程序/参数、输入 FASTA/PAF 字节、阶段、线程和原生数据/runtime/helper。大 raw 输入可使用本次 live native attempt 已计算的 SHA 与完整文件身份 fence；PID/start 身份验证限制其生命周期，不做跨 run 的 stat-only 缓存。动态原生产物仍按内容绑定，失败不生成单位完成回执。
- 直接沿用原生命令的已重定向输出描述符。原 producer 只对自身只读流建立持久快照；新 attempt 复制到新文件，不与历史证据共享可写 inode。保留旧日志/原 producer，stdout 格式和完整单位清单在 native 完成时重验；minimap2 未请求 `-c` 时不虚构强制 CIGAR，quarTeT 的原强校验保持不变。
- 报告包含阶段回执、PAF/校正来源和日志；私有可执行 wrapper 按 server-only script 标注。公开中英文指南同步实际恢复范围，不把重新运行的 scaffold/候选/整合阶段冒称复用。

### 本段必要轻量证据

- 8 项定向检查通过（39.514 秒）：固定分发脚本的 ONT 3 chunks、7 已完成命令后最后比对失败/恢复、整段 native 再复用；真实开发机 minimap2 空 PAF 后下游失败/复用；输入/线程/流损坏、完整阶段与 driver 漂移、结束后的 snapshot lease 拒绝、无跨 attempt inode 共享；兼容既有完成校验器与 quarTeT 恢复。
- 另选定三工具真实格式解析/来源重建用例通过（2.996 秒），其 producer 是明确的受控夹具。初次 native 脚本用例发现受控 Candidate helper 错误读取不存在的 `--prefix` 参数，修正夹具后通过，没有修改或放宽原生生产校验。
- 测试解包 lock 校验的原脚本，C++ helpers/Racon 为受控程序；HiFi 无命中用例使用本机实际 minimap2。未执行真实四工具固定环境、ARM、完整生物学、App 或进程终止故障验收。普通 CI 可运行轻量格式用例，精确 driver 用例通过 `CGAT_TEST_TGS_ARCHIVE` 显式启用。
- 全目标继续保留：LR 迭代恢复、未完成旧 LGZ 阶段迁移、原生离线可视报告、固定环境/四工具/双架构、终止/残留进程故障以及最新 App 闭环与 A01–A18 统一检查。没有升级现有环境、浏览器/生产构建、远端作业或发布；master 和客户工作区未动。


## 2026-11-22：LR 迭代处理恢复与后台错误闭环

- 先记录恢复协议，再新增 `refinement_lr_units.py`。从 lock 验证的原分发 driver 及既有路径探测补丁生成私有执行副本；原脚本/参数不改。保留预处理、首个 BWA index、tag split 的原顺序，在首轮 mapping/filter/reconstruction 及后续迭代处理块添加严格 restore/commit 边界。明确不冒称复用首个索引或预处理。
- 单位同时封存完整 `gapclosed.fasta`、`tmp/info_filter2`、实际输入/版本/线程及原生产者。新尝试只恢复这些消费产物，不搬迁旧 BWA/Perl 临时树；源文件存在、部分 FASTA、协议错误均不会被当作完成或普通 miss。原 gap finder/空 genome-ID 分支仍决定提前停止，原公共输入清理仍执行。
- 大 normalized reads/tag 文件的内容快照只在本次实际 live controller PID/start epoch 中复用；不使用跨 run 的 stat-only 缓存。完成验证依赖封存输出，不依赖原脚本随后删除的公共输入。新消费文件独立于历史生产者，保留原回执/字节。
- 原脚本的裸 `wait` 可能掩盖后台 coverage/gap-finder 非零退出；私有副本记录原后台 PID 并逐一等待，保持原命令和并发，失败不生成单位完成回执。restore 的 miss=1 与错误=2 分开，错误不会反过来放行未证明的处理块。
- 公开中英文恢复说明整理为四工具边界列表，报告接入 LR 单位/FASTA/info 和原生产者。native 完成校验器升级只重验已封存科学结果，不因此重跑工具；Final Path 仍走原 CGAT trace/来源重建和发布。

### 本段必要轻量证据

- 7 项定向检查通过（30.481 秒）：新增 5 项 LR 用例，以及原有完成校验器重验、三工具真实格式解析/来源重建。覆盖第二轮失败后第一轮恢复、第一轮初始 index 仍 fresh、第三轮原生提前停止、公共输入原生清理后的整段复用、后台子进程失败、协议错误不运行 native block、reads/线程/输出漂移、遗漏单位/消费文件、历史文件和独立 inode。
- driver SHA 来自锁定的原 noarch 分发文件，native 循环/分支和 bash 执行真实；BWA 和 Perl 算法由受控程序替代，不冒称真实 LR、生物学结果、固定环境/双架构或 App 验收。通过 `CGAT_TEST_LR_DRIVER` 显式启用精确 driver 用例；未运行全量回归。
- 四工具的上述内部恢复边界现均有代码。仍需推进未完成旧 LGZ 阶段迁移、原生离线可视报告、固定环境/真实四工具/双架构、终止和残留进程故障，以及最新 App 闭环与 A01–A18 最后统一检查。没有升级现有环境、运行浏览器/生产构建/远端作业或发布，master 和客户工作区未动。


## 2026-11-22 — 未完成旧 LGZ 的原引擎续跑与独立迁移审批

- 先扩展迁移契约，再新增 `legacy_lgz_continuation.py` / `legacy_lgz_runner.py`，由新版 `migrate_workspace.py` 提供只读 `--preview-lgz-continuation` 和显式 `--continue-lgz --approve ... --confirm-idle`。续跑仍在原目录执行原运行库，只把到 `finalize_evidence` 的前缀交给原 runner；不修改持久化计划/科学脚本，不执行旧 DEGAP 和打包尾部，不升级环境或用新 LGZ 引擎重算。
- 新增 `contracts/legacy_lgz_engines.json`：当前只审核编号目录改造前 `f2ceafb0df1f9d932122c5af3a733b9214ca7eb2` 的 202 个运行库文件。匹配实际内容，不以版本号替代来源；未知/修改过的历史运行库拒绝处理。保存的输出目录、生成脚本的运行库/工作区根路径必须仍指向本目录；搬移后残留其他根路径时拒绝，不改写科学脚本或到另一项目执行。该来源是已观察运行库的审核锚点，旧科学 producer receipts 仍独立保留，不把更新后碰巧相同的运行库冒称为过去的精确生产者。
- 已完成外层步骤使用原输入/输出校验器；已有阶段的实际 output hash/result/目录必须有效。只读缓存保护观察原 `checkpoint_result` 返回和固定源码的 q0/供体重算边界，已有完成回执的 cache miss 会停止，不让原逻辑删除它后重算，不伪造命中。仅对必要的完成缓存边界做局部行跟踪，不逐行跟踪未完成科学算法。Python 历史字节码既不受信任也不删除，使用新的不落盘缓存命名空间读取已审核源码。
- 每次尝试在 `.run_all/legacy_continuation/<run>/` 保存审批、请求、缓存事件和状态。失败保留旧布局并要求新预览；成功先通过原完整 LGZ 契约，再返回一个新的完整基线迁移预览。后续 `--apply` 需要第二份审批，续跑不会自行提交布局标记。中英文指南补充完整操作顺序和已审核历史引擎范围。

定向轻量检查：

```text
CGAT_TEST_LEGACY_SERVER=/tmp/cgat-legacy-lgz-f2ceafb0.IO3bYW
PYTHONPATH=server/tests python3 -B -m unittest -v test_legacy_lgz_continuation
8 tests passed (33.932s)
```

- 实际加载经过内容核验的历史 runner/校验器，受控科学命令失败两次后，已完成参考比对 checkpoint 和原计划字节不变；旧尾部不执行。公共 CLI 只读预览与 API 的审批摘要一致；另行检查陈旧的生成脚本根路径被拒绝，原脚本不被改写。
- 实际历史阶段缓存正确命中时保留来源；错误输入指纹在失效前停止；实际历史 q0 重算分支受保护。陈旧审批、损坏输出、变更运行库不启动工作；伪造同 mtime/size 的旧 bytecode 不被导入，也不被删除。
- 成功路径由明确受控脚本产生可验证的冻结科学包，随后真实执行独立审批的物理迁移，并逐文件确认科学文件字节不变。冻结导出 fixture 缺少原生缓存文件，不能为了测试续跑而放宽完成 checkpoint 校验；该测试不冒称执行了原生 LGZ 算法。
- 后续仍需原生离线交互报告、真实固定环境与四工具/双架构、真实未完成历史引擎和终止/残留进程场景，以及最新 App 闭环与 A01–A18 最后统一验收。本段没有全量回归、浏览器、生产构建、远端或环境升级，没有修改 master 或发布版本。


## 2026-11-22 — 固定原生报告的离线浏览与可搬移资源闭合

- 先记录 `server-refinement-native-report-contract-20261122.md`，再新增 `refinement_native_reports.py` 和独立 `refinement-native-reports.lock.json`。实际固定 DEGAP 的总报告是 `05.visualization/Global.report.html`，不再仅依赖旧的 `gap_filling_report.html` 测试入口；收集实际 LEFT/RIGHT 任务 HTML 及总览拷贝，保留原生文件字节和哈希。
- 离线浏览保留固定渲染器内嵌 JS/CSS/SVG。其 Chart.js CDN 标签实际没有被代码使用，移除这条浮动网络引用，不额外下载 JS 库、不增加环境依赖；固定 SVG data-URI 与局部渐变仍可用。管理副本加 CSP、独立 `sandbox=allow-scripts` 框架与同框架详情导航，原文仍是 `.txt` 附件，未知 HTML 不提升为普通页面执行。当前另外三个固定工具入口不生成原生 HTML，明确保留实际日志/填补明细/AGP，不伪造上游可视化。
- 总览闭合依据它实际内嵌的 gap JSON，并与可用原生 gap 诊断的完整记录核对；不以另一批 gap 静默替换。缺失、未知依赖或超限的子报告使用明确的 CGAT 不可用说明，既不悬空链接，也不伪造原生结果。已封存原生 artifact 与报告阶段才观察的诊断分开标注；可视化不是原生完成、CGAT 接纳、生物学验证或最终发布回执。
- 原文与浏览正文共享大小预算：有可视化时为浏览预留额度、优先总览；先保证总览和缺失详情说明闭合，再放入较大真实子报告。相同内容的原文拷贝只计费/保存一次，来源路径仍各自保留。索引分页每页最多 200 条、导航最多 5 个入口，不在每页重复整个页码列表。实际拷贝名与一次目录清单匹配，不为每个缺口重复进行文件系统探测。索引/manifest 元数据单独保留，不丢完整计数。
- 主工具报告、逐 job 链接、失败报告及 Full/Light 包均接入独立原生浏览目录；缓存身份包含 helper、固定源/策略及完整视图哈希，展示变化不失效科学原生 checkpoint。中英文指南说明入口、观测/封存区别与未生成/不可用状态。

必要定向检查：

```text
PYTHONPATH=server/tests python3 -B -m unittest -v test_refinement_native_reports test_refinement_reports
14 tests passed (3.689s)
Evidence: /tmp/cgat-native-reports-20261122.7bhTSr.log
```

- 实际运行固定版上游两类 HTML 渲染器处理受控日志/JSON，不运行补洞算法；脱离原 Server 路径后逐一检查相对链接、iframe、原文/视图哈希、原始文件未变化，以及总览与两方向入口。
- 轻量 Node VM 实际解析保留的上游 JS，执行总览语言切换/格式化与子报告翻译，不提供 Chart.js。覆盖非法 CDN、gap 数据漂移、缺失详情、失败不声明 final、配额压力下保留总览/说明闭合、内容去重、5,000 页规模的恒定数量导航及普通数据名称不被误判为网络调用。
- 真实 serializer/来源重建检查验证 Full 与 Light 的完整报告树字节一致；沿用实际来源染色体标识，不为了测试把原始 chr2 改成 chr1。没有覆盖原工作区/原生报告或改动工具源字节。
- 本段没有浏览器、完整回归、原生补洞/真实 reads、生产构建、远端或环境安装。真实文件浏览器中的 CSP/框架交互、固定环境四工具/双架构、真实历史任务和终止/残留进程、最新 App 闭环与 A01–A18 仍留到最后统一验收。整体目标未完成，未改动 master 或发布版本。


## 2026-11-22 — 进入真实固定环境与 public LGZ-only 验收

- 在独立临时 HOME/mamba root/prefix 实际执行公共 installer，195 个 Conda 包已安装；没有修改已有环境。真实 Python 包的 `lib/python3.1 -> python3.11` 目录软链接暴露安装校验误判。新增目录链接结构回执并在原生运行前后重验；普通包文件内容、固定 archive/build/version 检查不削弱。相同 prefix 重试和独立 `install.sh --check` 均通过，21 个命令与四工具 runtime identity 一致。
- 实际 500-kb/2-kb gap 样例通过版本化生成器生成，两个 HiFi 文件刻意同 basename，另有含确定性替换错误的 ONT。不是准确率/性能数据；不 mock 科学命令。
- 首次 public LGZ-only 暴露 q0 CLI 硬编码旧路径，修复中央布局解析和 command 指纹一致性；只替换停止测试工作区中的这一模块，保留备份/新旧 hash，不整库更新。继续后又暴露 q0 整体替换 `03_lgz` 删除冻结注释输入，修复为只替换 LGZ 所属子组并覆盖文件型组回滚。
- 原工作区的三个注释输入通过独立生成与原 manifest **逐项 hash 完全一致**后恢复，原 manifest、参考比对和 LGZ 已完成结果不替换、不删除、不重新 prepare。随后实际 public `run_all.sh` 完成 LGZ-only 和 Full/Light 基线包。原参考/assignment 共 21 个 checkpoint/输出的 hash 和 mtime 仍不变；最终 500,000 bp 基线保留预期 2,000 N。
- 必要定点检查：目录软链接 3 项；legacy/numbered q0 公共 CLI 1 项（2.241 秒）；编号发布成功/故障回滚 2 项（0.015 秒）。这些不能替代真实四工具和 A01–A18 验收。统一验收记录见 `server-refinement-final-acceptance-20261122.md`；整体未完成，无 master/客户/远端/发布改动。


### 同轮实际四工具与来源/脱离工作区包核验

- 原 LGZ-only 工作区经实际 `run_all.sh` 追加两个同 basename HiFi 与一个 ONT，四固定引擎顺序执行并以 0 结束。quarTeT/LR 各接纳 1 个补丁；DEGAP/TGS 均零接纳，明确保留原 gap。没有为了让样例成功改动原生算法或放宽接纳。
- 独立 stdlib 按实际来源 FASTA/hash、区间和方向重建四条 final path，均与实际 Server 最终序列一致。quarTeT/LR 确实使用新来源且区别于 LGZ；LR 在本已知合成例中恰好等于参考，quarTeT 长度少 43 bp，不能由此宣称最佳工具或生物学准确率。
- 八个实际 Full/Light 包脱离原工作区解包，经真实 payload 校验器检查库存/来源/路径/报告；Full FASTA 等于已发布 final，Light 明确无序列。各工具 Full/Light 报告字节一致。203 个原基线文件内容未变；13 个 finalization/摘要文件只重写相同字节；原参考/assignment 21 文件 hash+mtime 未变。
- 补充公共终端的接纳数量/缺口分类和零接纳显式 unchanged 标记，避免成功执行冒称已应用精修；该格式定点检查通过。尚未完成实际相同输入续跑、ONT Racon 分支、新工作区无修复直跑、App/浏览器/ARM 及完整故障/兼容矩阵，整体目标继续。


### 同轮续跑、新工作区与 DEGAP 原生坐标核对

- 原四工具工作区无参数续跑实际通过；四个 native 产物树（248/28/18/54 文件）size+mtime 不变，没有新原生产者。零接纳的终端标签也经实际公共入口核对。
- 独立全新 ONT-only 工作区直接 public `run.sh` 一次完成，无中途补丁/恢复；编号 q0 路由与注释保留修复经真实新准备验证。TGS 实际执行 5 个 minimap2 和 3 个 Racon 命令，接纳一个补丁；Full/Light 脱离工作区校验通过，不冒称其序列准确率。
- 核对真实 DEGAP 行及固定 Part2/Part3 实现发现其字段实际为 **1-based inclusive**，Part3 的 0-based 注释过时；旧正向受控夹具也按错误原点构造。修复 CGAT 接纳/拒绝归属和报告相交，保留原生坐标审计，不试探平移到可匹配 gap。实际 Python 3.11 定点 7 项通过（6.299 秒），其中真实固定 detector/analyzer 产生坐标；正向补丁仍是明确受控，不能冒称完成真实 DEGAP 填补的正向验收。
- 后续仍需最新源码统一回归、真实 DEGAP 正向、故障/终止/旧工作区与迁移、App Full/Light 往返/人工编辑保护、文件浏览器及 ARM 独立证据。没有改动原生工具算法、已有环境、master 或发布。整体保持进行中。


- 坐标报告边界和受控 DEGAP 完成 checkpoint 复用另有 2 项通过（4.923 秒）。停止的实际测试工作区只同步 3 个 CGAT 接纳/报告模块，不换科学 driver 或 runtime profiles；再经 public `run_all.sh` 实际重接纳通过。四个原生产者树 hash/size/mtime 均未变，新接纳仍指向原 producer；独立来源重建及新八个脱离工作区的 Full/Light 包再次通过。全部证据路径记入统一验收文档；这不补足真实 DEGAP 正向或 App/ARM/全矩阵验收。42 文件运行库同步核验一致，`production_ready:false`，未改正式发布清单。
