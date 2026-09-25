# 方案：仅对残留 gap 做有证据的大范围替换

## 1. 目标与不变量

在现有 Step3 的结构修正、第一轮 refill、片段过滤、第二轮 refill 全部完成后，对残留 gap 增加受保护的补救阶段。
适用于较大异常主序列靠近 gap，导致 10 kb 近端侧翼或 500 kb 搜索无法找到合适两侧锚点的情况。
修剪和插入必须构成一个完整、可验证、可重放的替换事务。

必须满足：

1. 只接收旧流程结束后仍未解决的 gap，不重试成功 gap。
2. 不改变旧算法的阈值、候选排名及成功决策。
3. 保护旧成功片段的来源、方向、序列、顺序及两侧连接边界。
4. 验证失败时保留原路径，不能留下仅删除未填补的半成品。
5. 新接受事件与源序列能确定性重建实际输出，报告、路径和 FASTA 相互一致。
6. 不硬编码 chr10、contig_22、给定坐标或 9,529 bp 的预期答案。
7. 不以 gap 数减少作为唯一成功指标；必须验证重复、结构变异和误删除负例。

## 2. 已确认的事实

### 2.1 输入与坐标

项目 `D:\Desktop\gs2`，WSL `/mnt/d/Desktop/gs2`；主 dataset `pre`，辅 dataset `assembly`，未启用 reads QC。
完整输入为 `data/datasets/pre.fa`、`data/datasets/assembly.fa`、`data/reference/ref.fa`。
该目录是 App 项目导入结果，不能假定包含完整 Server 的 q1/q2/q3、checkpoint 或 `.prepare_lib`。

目标原始主序列 `NC_089044.1_RagTag`，chr10 第 2 个 N gap：

| 空间 | 1-based closed 范围 |
| --- | --- |
| 原始 pre | 7,315,692–7,315,791，100 bp |
| 旧 gs2 最终路径 | 7,309,494–7,309,593，100 bp |

旧 q4 chr10 长度为 25,625,436 bp。坐标不同来自前序修复，不能直接复用原始坐标切最终序列。

### 2.2 GPM 拒绝与原版实跑

Step2 对目标的记录包含 `mummer_anchor_distance_gt_1000000`，约束的是待修复序列上的锚点距离，不是 donor 填补长度。
Step3 correction 为 `no_structural_error_detected`、候选数 0；这只是没有可执行候选，不证明生物学上无错误。
两轮 refill 对应拒绝为 `anchors_on_different_donor_members`，该处没有 `fill_length_gt_1000000`；chr06 旧问题则有后者。

本地原版 `Genome-Repair-Tools` 基线 `975848d`。原版在 MUMmer 4.0.1 下使用 chr10 分区 donor：patch 成功 5/8，目标 patch 提取失败；直接 filler 成功 6/8，目标仍 Not_closed；patch 后 filler 也未填上。
单独分析该 gap 会在 `gap_analyzer.py` 的 `analyze_gap` 与 `_analyze_gap_with_synteny` 间递归，最终 RecursionError。
这些结果不能作为新算法的可靠结构分类标签，也不能代替全体 donor 的歧义检查。

原版 parser 曾把 identity 读取为 alignment length。必须使用正确解析后的原始 MUMmer 行验证百分比范围，不照搬原版数据对象。

### 2.3 候选证据，尚非最终切点

原始 MUMmer 文本两条同向比对：

| 字段 | 左锚点 | 右锚点 |
| --- | --- | --- |
| pre | 7,242,766–7,315,691 | 8,882,971–8,920,194 |
| contig_22 | 7,217,133–7,290,099 | 7,299,629–7,336,757 |
| identity | 97.97% | 97.11% |
| 方向 | + | + |

对应待验证区间为 pre `7,315,692–8,882,970`（1,567,279 bp）和 donor `7,290,100–7,299,628`（9,529 bp）。
若严格照此替换，净变化 -1,557,750 bp，但最终切点必须精细验证，测试不能强制等于这些坐标或长度。
现有 500 kb 搜索够不到右侧可靠锚点。结构差异支持扩大搜索，却不能独自排除 pre 的真实插入或 donor 的真实缺失。

## 3. 架构与接入位置

入口 `server/tools/grt_step23.py::run_step3`，在第二轮 `apply_round` 得到 `output_paths/output_records` 后，写最终 q3、计算最终 SHA-256、生成公开坐标之前接入。
内部冻结输入称 `step3_after_round2`，输出仍为最终 q3。内部空间名称不应直接成为新的公开 q_version 枚举；需要新增公开值时必须同步 schema/validator。

建议新增 `server/tools/grt_core/unresolved_gap_repair.py`，拆开纯候选、验证与应用职责；按依赖可再拆一个模块。
不将所有逻辑继续堆进 run_step3，也不单独改 FASTA 绕过路径和事件。

实现前定位这些现有符号并确认实际签名：

| 符号或模块 | 需要理解的契约 |
| --- | --- |
| run_refill_alignment、arbitrate、consumed_intervals | donor、候选和使用区间 |
| annotate_gap_path_origins、attach_gap_origins_from_paths | 原始及过滤后 gap 来源 |
| q_rows_for_paths、sequence_from_segment | 路径与真实序列 |
| replay_step3、finalize_step3_public_coordinates | 重建、最终坐标及哈希 |
| grt_core/stage_cache.py | 失效、阶段提交、checkpoint |
| grt_core/contract/ | schema、artifact、usage、路径与事件检查 |
| server_run.py、prepare.sh | 参数、恢复与复制运行库 |

原 `arbitrate_structural_candidates` 有合并/吸收结构区间行为，不可直接让它吸收原成功事件。
已有 accepted 结果不参与新阶段重新排名。

## 4. 模式与初始策略

拟新增 CLI（当前代码尚不支持）：

- `--unresolved-gap-repair off|audit|apply`，默认 off。
- `--unresolved-gap-max-search <bp>`，默认 3,000,000，支持 1–10,000,000 正整数；越界明确拒绝。

off 不建候选；audit 建候选并输出证据但不改变序列/事件成功状态/donor 使用；apply 仅应用通过全部门槛的候选。
保留原 CORRECTION_SEARCH_RANGE、PATCH_MAX_ANCHOR_DISTANCE 以及原 refill 参数含义。

下列值为第一版可测试的**工程起点，并非已验证的通用生物学阈值**。必须保存到 fingerprint 与证据配置。

| 项目 | 初始要求 |
| --- | --- |
| 单侧窗口 | 500 kb、1 Mb、2 Mb、配置上限；升序去重、截断；禁止无界递归 |
| 大异常触发 | 删除区内非 N 长度至少 100 kb |
| 目标替换总跨度 | 不超过 max-search；两边各搜索 3 Mb 不代表能删 6 Mb |
| donor 插入长度 | >0 且 <=实际 --max-fill；不得用目标删除长度代替它 |
| 主锚点 | 每侧对齐跨度至少 20 kb，identity >=95%，同 donor、同方向、次序一致 |
| 外侧追加支持 | 每侧另一个不重叠同线性块至少 10 kb、identity >=95%；不足则需复核 |
| 成功接头保护 | 左右各 10 kb，不足则保护全部可用序列 |
| 精细验证 flank | 每侧完整 20 kb；不足则不自动应用 |
| 两种工具切点差 | <=100 bp，仍要确定唯一具体坐标，不能平均坐标 |
| donor 完整性 | 不跨 fragment 边界、不含 N{100,} |
| 候选数量 | 同 gap canonical 区间去重后最多 32 个进入验证；超限标为复杂，不能截断后宣称唯一 |

不可为让 chr10 通过而降低门槛。需要调整时输出失败证据、理由与对应新增负例，交 Codex 复核。
全局阈值放宽和默认启用均不属于本次实现。

## 5. 成功基线与保护规则

### 5.1 两层只读基线

运行级：修改前代码、相同输入/环境/原有参数的完整 gs2 结果，用于最终回归。
阶段级：每次运行 round2 结束时的序列、路径、有效接受事件、donor 使用清单，用于新阶段检查。
覆盖所有实际生效的成功修改，不仅是 action=fill。旧 superseded 事件应沿来源追踪最终有效贡献，不能误保护已不存在的片段或漏掉有效 correction/filter。

### 5.2 保护清单

每个有效成功结果记录来源 dataset/contig/start/end、方向、实际序列 SHA-256、路径顺序、邻接来源身份、两侧连接处各 10 kb 的序列哈希。
将成功区间及接头 guard 映射到冻结输入坐标。候选只要与这些区域相交就不得自动接受；必须检查整个删除/替换区间，不能只检查 gap 起点。
比较用来源身份及序列而非 run_id/event_id：重跑可能重建 ID；同一次运行中禁止无故重建旧成功记录。

供体占用检查包含所有前序阶段接受的来源区间，也包含本轮新增接受区间。以区间冲突，不以整条 contig 是否曾被使用判断。
候选被拒绝不占用 donor。不得修改旧成功状态来释放 donor。

第一版不自动吞并多个 gap。目标区间跨其他残留 gap、无法投影的来源边界或另一个新编辑时，拒绝自动应用并说明原因。

## 6. 算法步骤

### 6.1 当前坐标与窗口

从 round2 冻结结果重新枚举残留 N gap，包含原始 source 内部 N 和跨路径片段 N；沿用 gap origin 语义。
不能直接把 q2 MUMmer query 坐标用于 q3。可对当前局部窗口重新比对；若投影旧缓存，要证明锚点未跨历史编辑并保存映射。
窗口受序列边缘、保护区和总跨度限制。按 canonical 来源区间/方向去重，member 别名不能算独立支持。
小窗口找到不同 donor 两侧锚点时继续合法扩展，不要复刻“左右都有记录就停止”的逻辑。

### 6.2 唯一性与替代解释

竞争检查使用完整可用 donor 集（包括其他染色体），不能只查 chr10 分区。
枚举达到基础跨度/identity 的替代比对，把同一 locus 的碎片合并再比较。
其他 locus 的匹配碱基数达到最佳的 95%，或不同 donor 存在同等级结构解释时，标记 ambiguous_anchor/ambiguous_donor。
只取 primary、secondary 被截断、候选超限、参考记录缺失时，不可宣称唯一。
两工具一致只证明技术复核，不是独立生物样本支持。

### 6.3 大删除的额外支持

删除 >=100 kb 非 N 序列必须额外区分错装/重复与真实插入/供体缺失。
第一版实现“重复/错位证据路径”：待删除区间存在覆盖 >=90%、identity >=95% 的非歧义链定位到另一已保留位置，且参考或另一独立组装支持目标位置两侧相邻。
链不能由短重复拼成；已保留位置须以来源与最终路径同时确认；同一 donor 的不同 member 不能当独立支持。
额外链的唯一性沿用 95% 竞争规则，必须保存比对和覆盖计算过程。

如果只能证明两套组装存在差异，输出 needs_review，不自动删除。gs2 没有 reads，不能声称已有 reads 支持。
若未来以跨边界 reads 作为另一证据路径，需要单独定义起点独立性、数量、质量与原连接竞争支持阈值，经复核后再扩展；本次不要求新增 reads 模块。
参考基因组可用于定位和证据，不能作为插入序列来源。

### 6.4 精细验证、模拟、接受

1. 用实际源序列构造候选替换，负向供体先正确取升序区间再 reverse-complement。
2. 精细比对两侧连接，保留 MUMmer 和 minimap2 原始结果，确认覆盖、方向、切点及竞争位点。
3. 检查目标 gap 被替换、供体合法、接头没有重复锚点或丢失 flank、没有新增 N gap。
4. 模拟结果在替换区间外与冻结基线逐碱基相同；成功清单各项相同。
5. 同一事务更新路径、序列、接受事件、usage、证据；任一步失败保留原状态。

证据不足是 rejected/needs_review，解析/工具/I/O 失败是 error。不能吞掉异常并记作“没有结构错误”或成功。

## 7. 坐标与重建

内部统一 0-based half-open，公开现有表仍按 1-based closed。每个区间注明空间及输入哈希。
目标初始候选内部为 `[7315691,8882970)`，donor 为 `[7290099,7299628)`。
负向来源保持 start<end，方向独立字段；显式测试 1 bp、相接边界、终端、split path。

新增事件可优先评估使用现有 action=replace，加 repair_method=unresolved_gap_repair；先确认 schema/消费者，不以伪装普通 refill 绕过检查。
至少保存原 gap 来源 ID、冻结输入范围、源 dataset/contig/范围/方向、删去非 N 长度、插入长度、输入输出哈希、候选/证据 ID、策略版本与全部门槛。

按冻结坐标生成不相交编辑集合一次拼接；若逐次应用，必须维护投影且测试多个编辑的偏移。
输出旧→新坐标映射及 deleted 标记。被删区的失败尝试不能投影成假成功片段；旧成功事件不得被标为本次 superseded。

扩展 replay_step3：旧 correction → round1 → filter → round2 → 新补救。
只靠事件与源序列重建，不再次调用比对器，不读取最终 FASTA 代替重建。
完成后统一生成 q3 哈希、公开坐标、q_segments 和下游输入。
新增 replace 必须同时反映删除和插入，不能只在 donor usage 中出现。

## 8. 审计、缓存、下游

建议新增 unresolved_gap_repair_candidates.tsv、unresolved_gap_repair_attempts.tsv、unresolved_gap_repair_manifest.json 及 raw/ 验证产物。
允许调整文件名，但要写清对应关系并进入报告/证据包的可达路径。
manifest 包含模式、冻结输入哈希、供体全集哈希、保护清单哈希、参数、实现版本和工具版本/命令。
audit 的通过候选只能记 eligible，不能 accepted/consumed。

稳定 reason code 至少覆盖：protected_target_overlap、protected_junction_overlap、donor_interval_consumed、other_gap_in_interval、anchor_not_found、ambiguous_anchor、ambiguous_donor、insufficient_structural_support、boundary_validation_failed、span_limit_exceeded、fill_length_exceeded、donor_unresolved_gap、unsupported_coordinate_projection。

新增模块内容、模式、所有参数和工具版本纳入 fingerprint，不能只 hash grt_step23.py。
off/audit/apply 切换需失效 Step3 与下游；旧原始比对只在输入和参数兼容时复用。
prepared workspace 使用 .prepare_lib 副本，新模块与参数处理必须完整分发；恢复时不能仅复制主文件。
失败或中断不得发布半成品 checkpoint/q3/final_path/usage。重跑等价于完整新运行。

完整 Step4、q4、App 导入和导出也要对比。新长度可能移动旧端粒事件坐标，但不能丢失其序列、来源和连接。
apply 若在批准替换区间外改变旧结果，最终验收失败，不能只检查本阶段 guard。

## 9. 结果分级

工程门禁通过、chr10 目标修复成功、全部旧成功项保护通过、Codex 验收通过，四项分别记录。
needs_review 是诊断进展，不是目标自动修复完成；不能为任务交付强行应用候选。
