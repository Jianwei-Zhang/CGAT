# LGZ：基于比对证据的跨组装 q0 构建

- 决策日期：2026-11-18。
- 状态：设计已通过逐轮讨论确认；本文先于实现固定，实施进度见第 13 节。
- 基线：`deba82f15fa096bf5aaf16c968c98f9e3ca830ac`。
- 实施分支：`feat/lgz-evidence-guided-q0-20261118`。
- 范围：替换 q0 构建及其必要的证据准备、donor/LGZ、Server 包、App 导入和报告适配。
- Git 边界：仅在上述独立分支提交和推送；不向 master 提交、合并或推送。
- 发布边界：本任务不授权更新正式 Release、在线文档、已安装工具或客户工作区。

## 1. 要解决的问题

当前 q0 的候选只来自第一个 `--ds`。它已经使用 ref 确定分组、方向、顺序和部分去冗余，但没有在所有组装之间选择骨架。部分重叠、错误短片段和内部未知连接可能被保留，整条记录串联又会引入新的 N 间隔。后续 LGZ 因而可能面对原本不应出现的路径和 gap。

新目标不是“换一个主 ds”，也不是“最大限度贴近 ref”，而是：

> 每条 chr 在允许共同构建的所有组装中，选择来源可追踪的序列区段和有证据的连接，形成可信、非冗余的 q0；原组装连接、序列桥接和 ref 支持的未知连接分别记录。

更少 gap、更长序列或更高 N50 均不能单独证明改进。不得通过丢弃可信序列获得表面上更连续的结果。算法不承诺数学意义的全局最优，也不预先承诺真实数据上 Final Path 必然改善。

## 2. 已确认决策

| 编号 | 决策 | 明确边界 |
| --- | --- | --- |
| Q1 | 在同一样本、同一目标单倍型，或用户明确认可可共同构建的组装集合内整合 | 不由软件仅凭比对推断输入可混合；不同 ds 不等于独立生物学证据 |
| Q2 | 允许区段级选择、裁剪、替换 | 不修改来源碱基，不生成共识；原 FASTA 不覆盖，坐标可重建 |
| Q3 | 可信 ref 顺序可支持未知连接 | 不将插入 N 视为已证实的真实缺口，不以 ref 间距充当样本真实 gap 长度 |
| Q4 | 长片段优先建立骨架，但可被更好路径替换 | 依据有效连续区段，不以原始记录总长度锁死选择 |
| Q4a | 默认连续 N >= 100 为分段边界 | 与现有 LGZ 长 N 规则一致；更短 N 记录为未知碱基，不声称区段无 gap |
| Q4b | 保留输入组装的相邻关系，允许充分证据推翻 | 不能仅凭 FASTA 宣称连接一定由 de novo 算法产生；原 N 数不是已证实的物理距离 |
| Q5 | 短片段证明有可信非冗余贡献即可加入 | 不以统一短长度门槛代替证据；冗余或模糊命中不制造新连接 |
| Q6 | 跨 chr 命中不自动触发裁剪 | 区分重复、可能真实结构和错误连接；需充分证据及明确边界 |
| Q7 | 允许从原 chr 分组外找回可靠局部区段 | 扩展候选不意味着整条 contig 改归属，不能为了铺满 ref 强行纳入 |
| Q8 | 长区段起步，有限替代路径，可回退的局部替换 | 不用一次贪心锁死；限制和未解决范围可审计 |
| Q9 | 比对上下文与实际可新增区间分开管理 | 完整来源可作锚点；已占用来源不能被再次新增，明确替换除外 |
| Q10 | q0 前备齐必需信息；必需任务失败就报错结束 | 无命中是有效结果；未执行、失败、缺失和损坏不是“无支持”，不降级 |
| Q11 | 分支内直接替换旧构建策略 | 不保留新旧算法开关；基线结果从旧提交或外部结果获取，禁止旧缓存冒充新结果 |
| Q12 | 部分可信结果可输出，未解决范围明确记录 | 不强接、不造全 N 染色体；整份 q0 无可用记录时失败 |
| Q13 | 验收同时检查假 gap、可信序列保留和完整来源链 | 定向测试与真实样本效果分开报告 |
| Q14 | 决策记录为正式产物，报告提供摘要 | 本次不新增一套交互 UI；必要的 App 包校验与导入适配属于范围 |

## 3. 当前代码事实与必须改变的地方

下表对应上述基线的符号或文件，行号不作为稳定接口。

| 文件/符号 | 基线行为 | 本次要求 |
| --- | --- | --- |
| `server/tools/run_orchestration.py::build_unit_plan` | ref -> assign -> q0/LGZ -> chr 任务 | q0 必需的 chr 比对前置，扫描与后处理分开 |
| `server/prepare.sh` | 生成同样的顺序和阶段脚本 | 与调度依赖一起更新，不只改打印顺序 |
| `server/tools/assign_chr_groups.py` | 按整条 query 覆盖比例分组；生成组内 self/cross 和扫描任务 | 复用比对；保留分组外局部命中和全 ref 竞争证据 |
| `server/tools/lgz_prepare_inputs.py::prepare` | `primary_dataset = dataset_order[0]`；整条候选、固定 N 间隔、按来源整条排除普通 donor | 由跨 ds 区段路径替换；区间级 donor；策略和证据入缓存 |
| `lgz_prepare_inputs.py::parse_assignment_paf` | 使用 PAF 基本字段，不解析 CIGAR | 新 q0 证据解析支持精确投影，不能线性比例裁剪 |
| `server/tools/lgz_core/common.py::donor_fragment_rows` | N >= 100 分片，保留原始 donor 坐标 | 复用原则；不能未经审查把 member 局部坐标当来源绝对坐标 |
| `server/tools/lgz_core/repair_structural.py::_adjacent_primary_segments` | 直接重叠合并限制为 primary ds | 判断当前路径和来源证据，不以第一个 ds 授权 |
| `server/tools/lgz_core/contract/validator.py` | q0 直接证据要求 assignment/ref 路径；按来源坐标重建 | 扩展连接与选择证据，保持严格重建和校验 |
| `server/tools/server_report_collect.py` | 描述“原始主组装 -> q0”；已有 q0/q4 统计 | 改为多组装构建，区分两类未知间隔及未解决范围 |
| `app/backend/src/grt_package/` | 独立 types、校验、持久化、导入测试 | 与 Server 共同验证，不能假定 Server 通过就能导入 |

现有 LGZ Step1 的 external-contig 执行路径保持序列不变。因此不得把 q0 问题当作 Step1 一定会修复的问题。

## 4. 新阶段与依赖

```text
全部 ds 对完整 ref 比对
  -> 原始 chr 分组 + q0 区段和原连接索引
  -> 组内 self/cross 比对 + 按候选需要补充比对
  -> q0 证据准备完成（包含必需末端/已有 QC 证据）
  -> 跨 ds q0 路径选择
  -> q0、来源映射、连接/决策记录与配套 D0/Dtel 冻结
  -> LGZ 后续阶段
  -> 未前置的扫描、证据打包、报告
```

### 4.1 任务复用与成功判定

- 同输入、同参数、同实现内容的已有比对可复用；不得只因结果文件存在就跳过验证。
- 前置的是 q0 所需比对/扫描，不把原 chr 任务中的所有后处理无差别提前。
- 需要的同 ds 比对不能因旧的 skip-self 设置而悄悄缺席；配置冲突明确报错，不能忽略用户参数。
- 空 PAF 只有在任务正常结束且通过对应输出验证时才表示“无命中”。
- 任务失败时保存有界诊断，不发布新 q0，不破坏先前可用产物。
- reads 为可选证据；没有 reads 不是失败，质量值标记未测量，不能伪造质量优劣。
- 不默认对全基因组所有 contig 做全量两两比对。局部补比对由候选发现规则驱动，覆盖范围和未覆盖关系有记录。

### 4.2 跨组候选

原分组是检索入口，不是整条序列永久的唯一归属。对全 ref 的可靠局部命中、已有骨架的可靠序列锚定可以引入扩展候选。保留原 source 身份和分组事实，为 q0 区段另记定位证据，不粗暴改写整个源 contig 的分组以通过旧校验。

## 5. 数据模型及坐标约定

### 5.1 来源与候选

区段身份至少包含：dataset、原始 contig、来源区间、方向和内容校验值。内部算法采用统一的 0-based half-open 区间；现有 TSV 的 1-based inclusive 坐标在边界显式转换。反向序列、CIGAR query/target 坐标及 donor member 局部坐标必须有独立测试。

候选记录包含：稳定 ID、源区间、所属原记录、候选 chr、ref 比对链及竞争命中、长度/N 信息、质量证据可用性、分组来源、定位歧义和排除原因。

稳定身份和决胜顺序不能使用 `--ds` 行号。相同序列由不同来源提供时仍保留各自来源身份，不把相同内容自动计为多份独立证据。

### 5.2 原记录的长 N 分段

扫描 N >= 100 的内部区间，形成来源区段索引和原组装连接。N 在记录首尾时只有边界信息，不创建空候选或虚假的两个端点。全部为 N 的记录没有可用序列区段，但原记录仍保留。

原连接至少记录：左右区段 ID 和端点、方向、父记录和原 N 区间、原 N 数量、连接来源、状态、支持/反对证据。记录名称使用“输入组装原有连接”，只有输入提供明确 provenance 才进一步标注构建方式。

### 5.3 连接类型

| 类型 | 意义 | 输出要求 |
| --- | --- | --- |
| 原组装连接 | 原记录中两个区段跨 N 相邻 | 未被替换时保留原 N 表示与来源；不把 N 数当已测距离 |
| 直接重叠 | 可信 suffix/prefix 等序列比对支持连接 | 在精确来源坐标消解重叠，不能重复计入同一序列 |
| 桥接替换 | 第三候选在正确顺序和方向锚定两侧 | 保留外侧可信序列，使用桥接区间替换连接和必要重叠 |
| ref 支持的未知连接 | 归属、顺序可信但没有连续序列证据 | 使用既有固定 N 表示（当前 100），标注新增未知连接，不推断真实长度 |
| 未解决关系 | 归属、顺序、重复或竞争路径尚不能决定 | 不伪造连接，保存备选及原因 |

CIGAR 缺失、投影不唯一、重复锚点不能授权精确裁剪。作为必需投影输入的文件若格式损坏则报错；有效但歧义的命中保留为不足以授权编辑的证据。

### 5.4 路径与决策

路径由有向来源区段及连接组成。原子决策记录候选集、原路径、新路径、实际采用的比对、选择/拒绝原因、可信覆盖变化、重复/冲突、N 变化、来源切换和未解决范围。

决策证据先采用独立的版本化记录建模；是否扩展现有 TSV 由 Server/App 契约测试决定，不把桥接证据伪装成 assignment 来绕过验证。

## 6. 路径选择

### 6.1 候选准入

先判断数据有效性、来源集合、定位可信度和竞争命中。ref 比对不是序列真值，mapQ 不是唯一决策依据；ref 覆盖包含不等于来源序列冗余，去冗余需结合 contig 间证据。

短片段若提供可信非冗余序列、末端延伸或桥接即可竞争；不得以统一的短长度阈值代替这些判断。所有未采用记录仍保留，符合条件者进入 donor，而非从原始数据消失。

### 6.2 初始骨架与局部替换

1. 按当前 chr 上可信区段的连续性、有效长度和稳定来源身份产生初始方案。
2. 围绕重叠、连接、冲突区域构建局部竞争路径，保留有限替代方案。
3. 支持加入、去冗余、直接重叠连接、桥接替换、保留原连接、拒绝连接等操作。
4. 后来的候选可以推翻之前的选择，不能退化为不可回退的长到短贪心。
5. 桥接需要可信双侧锚点、方向/顺序相容、精确边界和来源占用检查；候选自身跨 N 不等于已经闭合缺口。
6. 没有可证明优势时保留较稳定的原路径，避免无理由碎片化和来源切换。

### 6.3 比较原则

先比较结构/连接可信度和可信非冗余贡献，再比较重复/冲突、未知连接、来源切换、连续片段和可用质量证据。不能通过删除困难但可信的覆盖区域来降低 gap 代价。ref 外的可信序列也要进入保留核算，而不是从评分中消失。

实现中的数值阈值、候选上限和证据规则集中在版本化策略中并进入指纹；未通过实验标定的数字不得被描述为生物学最优值。达到搜索界限时记录剪枝理由和未解决范围，不静默宣称全局最优。

### 6.4 跨 chr、末端和重复

- 同一区段在多个 chr 上存在相近命中：保留定位歧义，不据此裁剪。
- 主体和末端分别有不同 chr 的特异命中：视为待解释的结构关系，需结合其他区段/组装支持。
- 其他证据支持连续结构：不能仅为匹配 ref 拆开。
- 支持错误连接且边界明确：允许拆分和区段级采用。
- ref 未覆盖、但其他来源支持的末端：不能仅因 ref 外序列而删除。
- 端粒信号提供末端线索，不单独证明整段长尾都正确。

### 6.5 部分结果

可信部分可输出；冲突无法连接的其他区段留作候选/donor并记录。单条 chr 完全无路径时报告未构建，不造全 N 记录；所有 chr 都无法形成 q0 时失败。输出范围必须在报告中明确，不能把部分路径称为完整染色体。

## 7. donor 与后续 LGZ

完整来源序列用作比对上下文，可新增区间单独索引。已进入 q0 的来源区间可以作为锚点，但不能在同一结果路径中再次新增；替换时按原子操作释放旧区间并记录新占用。

- q0、D0/Dtel 身份和允许使用区间在同一准备事务内冻结。
- donor member 区间、fragment 局部区间、原始来源坐标明确区分。
- 冻结后的集合/资格不由阶段临时重写；后续使用与替换通过使用账本表达。
- 未通过质量或序列有效性检查的来源保留原数据和拒绝原因，不绕过 donor 条件。
- 原始相同来源区间不能因位于两个候选 chr 而被重复接受。
- 后续 primary-only 处理改为路径/来源证据判断；不要直接删掉安全检查。
- Step1 到 q4 的重放、事件和来源映射仍能逐段重建实际序列。

## 8. 持久化、App 与兼容边界

q0 仍输出到现有 `grt/q/q0.fa`，最终版本链和可复用来源字段尽量保持。机器命名 `grt_*` 不因本次算法变化顺带重命名。

`primary_dataset` 同时存在于 recipe、App 数据库和项目概念中。去掉“第一个 ds 决定 q0”的算法语义不等于直接删除所有该字段；保留必要的项目元数据，不允许它再决定候选资格或算法排名。具体契约扩展需同时更新 Python 和 Rust 校验测试。

旧包可读性与旧构建算法是两回事：不保留旧构建开关，但不主动破坏既有包读取。新包若使用旧格式不能表达的必需语义，必须显式版本化并同步消费端，不能用填假值或放宽完整性校验通过。

必要适配位于 `app/backend/src/grt_package/{types,contract_validator,delivery_validator,persistence}.rs` 及导入测试；除非验证证明必要，本次不改交互 UI。

## 9. 缓存、失败与事务

输入身份涵盖原始来源、ref、实际使用的 PAF/CIGAR、组内和补比对清单、参数/工具身份、区段规则、策略版本、可用 QC/末端证据和集合元数据。结果缓存不能仅以 ds 顺序和 ref 比对判定有效。

- 新策略指纹使旧 q0/donor 结果失效，不提供旧算法 fallback。
- 原始比对在内容和参数兼容时可复用；不能因为 q0 改变就无差别删除缓存。
- q0、metadata、donor 和 checkpoint 完整生成、验证后再发布。
- 发布失败恢复先前可用产物；失败诊断保留。
- 不在本任务中自动重算或迁移客户已有工作区；受控验证使用新输出目录。
- 随代码提交更新受版本控制的运行库清单；通过项目生成工具更新，不手改哈希。

## 10. 正式决策输出与报告

机器可读输出含策略版本、输入证据身份、区段、连接、路径、操作理由、未采用候选、未解决/未构建区域及搜索限制。每个引用可定位到原比对文件及记录。

报告摘要至少展示：各 chr 的来源构成、输入原有 N 间隔、新增未知连接、可靠桥接/重叠操作、未解决范围。将“原始主组装 -> q0”改为“多组装候选 -> q0”。q0 到 q4 的 gap 数差不再独自代表真实闭合数量，需避免将删除冗余连接描述为补齐真实缺失序列。

## 11. 验收矩阵

| ID | 场景 | 必须证明 |
| --- | --- | --- |
| A01 | ds 输入顺序置换 | q0 序列和来源选择不变；日志、运行 ID 不要求字节一致 |
| A02 | 低质量/冗余短候选 | 不凭分组顺序制造新连接，拒绝原因可追踪 |
| A03 | 短候选含可信独有序列 | 不为减少 gap 丢弃贡献 |
| A04 | c3 双侧跨越 c1/c2 | 精确替换、外侧保留、无重复来源/序列，反向案例覆盖 |
| A05 | c3 仅重复锚点或顺序错误 | 不授权桥接或裁剪 |
| A06 | 内部 N >= 100 | 分段、原连接、原 N 数和坐标准确；首尾 N、全 N、短 N 均覆盖 |
| A07 | 跨 chr 重复末端 | 不误裁剪、不错误改归属 |
| A08 | 可定位错误连接 | 有证据的区段处理、未决状态与精确来源 |
| A09 | 未分组可靠局部候选 | 可以被发现和采用，不篡改整条来源分组 |
| A10 | 部分 contig 进入 q0 | 剩余可用区间保留，已用区间作锚点不再次新增 |
| A11 | 必需比对失败/损坏 | 终止、诊断存在、旧可用产物不受损、不降级 |
| A12 | 成功空比对 | 与失败区分，不虚构边或证据 |
| A13 | chr 部分/全部缺失 | 部分可用、未构建明确；全局无 q0 时失败 |
| A14 | 缓存和事务 | 相同内容复用，策略/证据变化失效，安装失败恢复 |
| A15 | Step1 到 q4/Final Path | 序列重建、来源坐标、使用账本、事件证据一致 |
| A16 | Server 到 App | full/light 包必需内容齐备；Rust 校验、导入和持久化通过 |
| A17 | 决策报告 | 原有/新增间隔区别正确，未测质量和未解决区域不隐藏 |
| A18 | 有界搜索 | 竞争方案可替换初始贪心路径，限制及剪枝有记录 |
| A19 | 无 reads | 可正常构建，不伪造 QC；有 reads 时使用实际已有证据 |
| A20 | 来源合法性 | 禁止来源区间重复、超界、假 evidence 和错误坐标转换 |

先运行 Python 定向测试，再执行受影响的 Server 包和端到端 gate。App Rust 测试在 Windows host 运行；若涉及前端，只使用 Windows Node/npm。无需为纯数据契约变化启动浏览器。

真实样本与旧基线比较在输入获授权且可用后进行，记录输入哈希、参数、版本和范围；不能拿合成测试通过代替真实数据的效果结论。也不能把基于同一 ref 的评分提升当作独立正确性证明。

## 12. 实施顺序与提交边界

1. **D0 文档基线**：固定本文、审阅并提交推送独立分支。
2. **I1 证据与来源基础**：区间模型、长 N 分段/原连接、PAF/CIGAR 解析与投影、定向测试。
3. **I2 前置证据准备**：拆分 chr 比对/扫描依赖、候选补比对与成功清单、缓存及失败测试。
4. **I3 q0 路径引擎**：候选池、重叠/桥接、有限替代路径、短片段与冲突处理、决策记录；替换旧构建入口。
5. **I4 donor/LGZ 配套**：可用/占用区间、冻结及重放、去除 primary-only 资格依赖。
6. **I5 交付契约与报告**：Server/App 校验、导入、摘要和运行库清单。
7. **I6 验收与收尾**：A01–A20、受影响质量 gate、分支 diff 审阅、命名路径提交和分支推送。

每一步提交前审阅实际 diff，只暂存任务文件。开始时及每次推送前核对当前分支；显式推送该分支 ref，不推送 master。必要的设计细化或偏差先更新本文；不把未完成阶段记成已交付。

## 13. 实施状态与证据

本文是实现的设计基线，不是完成报告。状态需随实际证据更新。

| 阶段 | 状态 | 证据 |
| --- | --- | --- |
| D0 | 已提交并推送 | `a634df9`；Q1–Q14、A01–A20、13 个章节及 LF 格式检查通过 |
| I1 | 基础模块与定向回归已完成，已由 I2 证据阶段使用 | `q0_sources.py`、`q0_alignments.py`；新增 25 项测试，联合回归 44 项通过；运行库清单校验通过 |
| I2 | 已接入并验证：前置比对、扩展候选、按需补比对、必需证据清单及缓存保留 | 见 13.2–13.3；最终联合回归 230 项通过（含来源方向回归）；两套准备脚本测试通过 |
| I3 | 主入口已切换，跨 ds q0 与 donor 冻结已共同发布 | 见 13.4–13.6；后续 q0→q4 与交付定向验证见 13.8–13.11 |
| I4 | 区间授权、跨 ds overlap、原 N 软连接及真实工具受控编辑闭环已实现并验证 | 见 13.7–13.8；完整交付与大数据/生物学验收仍属 I5/I6 |
| I5 | 契约、导入与报告已接通并通过定向验证 | 见 13.9–13.11；完整质量 gate 与效果/规模收口留在 I6 |
| I6 | 进行中：已有矩阵定向证据，完整 gate 与旧流程夹具迁移待收口 | A01–A20 需逐项审计，不能将局部通过当作完整验收 |

尚无新算法真实样本收益结论；尚未执行发布或客户工作区迁移。


### 13.1 I1：来源与比对证据基础

新增文件：

- `server/tools/lgz_core/q0_sources.py`：严格半开区间及既有闭区间转换、覆盖并集与剩余来源区间、长 N 分段、原组装连接索引、稳定来源身份。
- `server/tools/lgz_core/q0_alignments.py`：PAF/CIGAR 验证、完整 ref 命中保留、双向及反向链坐标投影、indel 边界歧义、真实 paired-base 覆盖和 target skip 统计。
- `server/tests/test_q0_evidence.py`：25 项测试；投影另以独立的逐碱基网格路径 oracle 检查随机小 CIGAR 的全部子区间和两种方向。
- `server/tools/grt_core/q0_sources.py`、`q0_alignments.py`：沿用现有模块别名转发约定，仅指向同一份 LGZ 实现，不是保留旧构建策略。

运行库清单通过维护工具生成，未手工改写哈希，未更新任何正式 Release 或客户工作区。

在仓库的 `GPM2.0` 目录运行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  server.tests.test_q0_evidence \
  server.tests.test_grt_prepare_inputs \
  server.tests.test_lgz_compatibility -v
# 44 tests, OK

PYTHONDONTWRITEBYTECODE=1 python3 \
  experiments/long_query_alignment/sync_server_runtime.py
# status=verified, changed=[]
```

证据边界：本节记录 I1 提交时的基础模块验证，不是 A01–A20 全部通过。后续调度和必需证据入口见 13.2–13.3；路径选择引擎及 donor/App 适配仍由 I3–I5 完成。投影结果的 `exact` 仅表示裁剪坐标准确，不代表命中唯一、碱基一致、桥接成立或允许结构编辑。


### 13.2 I2a：前置组内比对并拆分扫描依赖

实际生成的计划已变为：

```text
ref:* -> assign -> q0_chr:* -> grt_prepare -> LGZ 后续阶段 -> chr:* -> finalize_evidence -> archives
```

- `q0_chr:<chr>` 使用 `q0_command.sh` / `q0_generated_command.sh` / `q0_alignment_tasks.json` 执行 self/cross 比对。
- 后面的 `chr:<chr>` 及原 `command.sh` / `generated_command.sh` / `alignment_tasks.json` 执行扫描；原始 PAF 路径不变。
- q0 染色体任务沿用现有 CPU 预算调度器；全部成功并通过 PAF/CIGAR/内容校验后才继续下一阶段。
- 两个阶段分别记录 checkpoint，不要求早期比对提前拥有未来扫描输出；扫描脚本变化不会单独使早期比对失效。
- 手动复制执行 `q0_command.sh` 由同一工具在运行前捕获输入，成功后记录同一种 checkpoint。手动和并行执行都会在提交前重新核对输入；运行期间来源或参数变化时拒绝发布成功记录。空比对、无比对任务、缺失结果分别处理。
- 缺失 q0 任务清单报错，不回退使用扫描清单。
- 跨 ds 比对方向按 dataset 名称稳定排列；`existing_display_evidence` 使用实际 PAF 路径判断 query/target，不能再按 `--ds` 顺序猜测角色。读取既有反向目录不等于保留旧 q0 构建算法。
- 当现有组中有多个同 ds 候选而显式要求 `--skip-self` 时，在分组输出写入前报告冲突；只有一个候选时不强制生成无意义的 self 任务。
- Server 报告区分 q0 候选比对与后续扫描，不重复计入同一 PAF。

验证：

1. `prepare_metadata_test.sh`、`prepare_full_test.sh` 均通过，包括新顺序、拆分清单、self batch 及 skip-self 冲突。
2. 最终代码冻结后，以下合并 Python 回归 **138 项通过**，其中新增调度测试 13 项。此前的分批回归也通过；最终以合并结果为准。
3. `sync_server_runtime.py --write` 重新生成清单；只读校验 `status=verified, changed=[]`。Python 语法、shell 语法、LF 和 Git whitespace 检查通过。

以下是最终合并回归及准备脚本复跑命令（在 `GPM2.0` 中执行）；这是受影响范围的定向验证，不宣称已完成整体质量 gate：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=server/tests:. python3 -m unittest \
  server.tests.test_q0_scheduling \
  server.tests.test_run_orchestration \
  server.tests.test_run_outer_checkpoints \
  server.tests.test_run_all_runner \
  server.tests.test_alignment_tasks \
  server.tests.test_self_alignment_batches \
  server.tests.test_self_alignment_parameters \
  server.tests.test_server_report \
  server.tests.test_q0_evidence \
  server.tests.test_grt_evidence_package \
  server.tests.test_lgz_compatibility \
  server.tests.test_workspace_runtime_update -v

PYTHONDONTWRITEBYTECODE=1 bash tests/gpm_server/prepare_metadata_test.sh
PYTHONDONTWRITEBYTECODE=1 bash tests/gpm_server/prepare_full_test.sh
```

I2a 提交时的剩余工作（已在 13.3 接入）：

- 主候选/扩展候选发现、内部 N 分段后的区段级关系，以及按需求生成跨组/未分组补比对。
- 把组内与补比对的成功状态、query/target 来源、参数及实际 PAF 汇总为 q0 的必需证据清单，并纳入 q0 输入指纹；独立调用新 q0 入口也必须校验该清单。
- 分组重新生成时保留输入与参数仍匹配的原始比对缓存，不能依赖当前分组脚本清理目录的旧行为满足此要求。

I2a 提交时 `lgz_prepare_inputs.py` 的路径选择尚未切换；调度通过不代表新 q0 或 Final Path 已验收。后续按 13.3、I3–I6 继续，不增加旧策略开关。


### 13.3 I2b：扩展候选、补比对和必需证据清单

当前实际计划：

```text
ref:* -> assign -> q0_chr:* -> q0_evidence -> grt_prepare -> LGZ 后续阶段 -> chr:* -> finalize_evidence -> archives
```

新增/接入接口：

| 接口 | 用途 |
| --- | --- |
| `runs/chr_<chr>/q0_alignment_inputs.json` | 明确声明每个原始 PAF 的 query/target dataset、输入 FASTA、方向和运行目录；不从 ds 顺序推测 |
| `server/tools/lgz_core/q0_catalog.py` | 跨 ds 来源区段、原 N 连接、完整 ref 命中候选及 pairwise 派生候选 |
| `server/tools/lgz_core/q0_preparation.py` | 校验已完成的组内任务、发现并执行补比对、缓存和清单发布/读取 |
| `prepare_q0_evidence.sh` / `lgz_prepare_evidence.py` | 独立于 q0 路径选择的必需准备阶段 |
| `grt/evidence/q0_prepare/catalog-*.json` | 来源、区段、原连接、候选、比对引用和未放置范围的内容寻址快照 |
| `metadata/grt_q0_evidence.json` | 版本化成功清单，绑定策略、构建器、输入、catalog 和补比对产物的 SHA-256 |

候选与任务范围：

1. 从所有 ds 的完整 ref PAF 建立区段候选，保留竞争 chr 和方向。只统计 CIGAR 配对块的区间并集，不把跨删除的包围跨度当作有效覆盖。
2. 初始无 ref 候选的区段对已有锚定区段做发现比对；新发现区段成为下一轮锚点，直到无新增区段。每个有效轮次至少增加一个区段，因此轮数受区段总数限制。
3. 每轮对尚未放置区段建立候选；保留该轮观测到的多个 chr/方向，不用投票强选。派生候选记录锚定候选 ID 和实际 pairwise 证据，不伪造直接 ref 坐标或 assignment。
4. 原分组之外的候选、同一来源长 N 分段后的区段，以及 ref 重叠/邻近但原始 PAF 没有观察到来源对命中的关系，触发 chr 内补比对。后者避免高阈值 self 比对漏掉短末端后，将“任务完成”误认为“连接证据足够”。
5. 已有实际来源对命中的普通组内关系继续复用其 PAF；不是再次做全基因组全量两两比对。ref 邻近只授权请求比对，不授权连接或裁剪。

补比对使用版本化策略中的 `-D -P --dual=yes --no-long-join`，并保留 `-c` 和选定 assembly preset：避免 query 本身在 target 集合中时的对角匹配压住部分重叠，同时避免名称字典序过滤有向 query 子集。该模式保留链而不依赖 primary MAPQ 排名；后续选择必须根据实际竞争命中和锚点判断，不把此类 MAPQ 当作独立质量证明。

缓存、失败和事务：

- 原始补比对缓存只绑定 mapper、实际 query/target 区段内容、preset 和比对参数；候选构建器更新或发现轮次变化不会无理由重跑同一原始比对。缓存读取仍核对产物内容和 CIGAR 几何。
- 成功空 PAF 是有效结果；缺失成功记录、缺失必需来源对、损坏 PAF、补比对失败或输入在执行中变化均终止，不发布新的成功清单。
- 显式 `--skip-self` 同样约束补比对：如果新发现或分段候选需要同 ds 非自身关系，直接报错，不静默绕过该参数。
- 清单校验同时检查输入指纹、catalog schema、原始比对依赖、补比对任务 ID/回执和完整产物闭包，不能删去某个条目后仅靠其余文件哈希通过；准备期间构建器代码变化也不发布成功清单。
- `load_verified_evidence` 没有旧策略 fallback。`lgz_prepare_inputs.py` 必须先通过该检查；清单及其产物进入 q0 输入指纹，准备器版本升至 4。
- q0/donor 原子发布会保留前一阶段的证据目录和清单（优先硬链接，必要时复制），并在发布前再次检查证据，不能因整体替换 `grt/` 而删除前置证据。
- 相同分组重新生成时保留原始 PAF 和 self batch 缓存，由内容 checkpoint 判定复用。已不在生成计划中的旧操作移动到 `.run_all/retired_chr_operations/`，既保留数据，又避免 App 将其误发现为当前运行。无关目录不按猜测清理。

最终验证：

- 最终联合回归 **230 项通过**（333.730 秒），覆盖候选/补比对、清单依赖闭包、skip-self、调度/断点、原 q0 准备、Step1、Step2/3、端粒收尾、证据包、报告、命名兼容、运行库更新及来源卡片方向。
- `prepare_metadata_test.sh` 和 `prepare_full_test.sh` 通过；包含相同分组重新生成后的 checkpoint 复用、缓存保留及不再使用的操作归档。
- 使用本机 **minimap2 2.26-r1175** 的受控随机序列测试通过：query 同时出现在 target 中、且两种名称顺序下，仍能发现另一来源的部分重叠。它是证据发现测试，不是物种数据或最终组装质量验收。
- 运行库清单由维护脚本重新生成并验证，不手改哈希；没有修改正式 Release 或客户工作区。

复跑：在 13.2 的 Python 测试列表中增加 `server.tests.test_q0_preparation`、`server.tests.test_grt_prepare_inputs`、`server.tests.test_grt_step1`、`server.tests.test_grt_repair_stages`、`server.tests.test_grt_telomere_finalize`、`server.tests.test_source_card_orientation`，得到本次 230 项联合回归（相同工作目录和 `PYTHONPATH`）。

完成边界：**证据准备和强制入口已完成，q0 的路径选择仍是待替换部分。** 本阶段没有引入新旧构建策略开关，也没有宣称 q0/Final Path 已改善。I3 将真正使用 catalog 和原始比对选择、替换路径；I4–I5 仍须完成区间级 donor/后续 LGZ 及 Server/App 的选择证据适配。运行期清单引用的 checkpoint/工具上下文也不能被直接当作已完成的便携 App 交付契约。


### 13.4 I3a：可替代路径内核与非重复来源覆盖

新增 `server/tools/lgz_core/q0_paths.py`、`q0_coverage.py` 及对应 GRT 模块别名。本节是 **I3 的内核阶段**，不是生产 q0 构建入口已完成。

接口与实际能力：

- `Placement` 接收已完成定位准入的来源区间、方向、chr、实际支持锚点和证据 ID。`PairLink` 使用经过 I1 解析的实际 PAF/CIGAR，同时保留 fragment FASTA 到原始来源的坐标偏移。
- `PathGraph` 构建原组装 N 邻接、精确序列重叠和 ref 支持的未知连接。直接重叠要求实际链到达相应末端，并在双方受支持的 paired-base 锚点内部选切点；链内 indel 不等于切点可以跨越 indel 歧义。
- `search_paths` 先按有效区段长度起步，再保留有限竞争路径，允许插入、删除和局部替换。c3 双侧桥接可替换原有 N 连接或新增未知连接，并保留 c1/c2 外侧来源；反向来源仍以原始正向坐标记录。
- `reconstruct` 仅截取/反向互补实际来源并写入明确类型的 N 连接，不生成共识，不覆盖输入 FASTA。原 N 连接保留原父记录、N 区间和 N 数；决策分别记录移除的原 N 连接与新增未知连接。
- 未采用候选区分“已被采用来源表示”和“仍有未表示区间/搜索限制”。ref 包含关系本身不证明序列冗余；短片段不因长度单独淘汰。没有获准裁剪的 ref 外来源尾部不会被内核自动删除。

来源覆盖不是 ds 投票：

1. 从有支持且无已知定位冲突的实际 paired-base 关系建立等价坐标区间。
2. 传播对应边界，形成等长的小区间；使用方向信息追踪反向等价关系。插入、不配对区间仍独立核算。
3. 一个等价区间无论由几个 ds 提供只计一次；复制一个 ds 不会使同一序列在路径评分中重复加分。
4. 若传递关系把同一原始来源的两个不同位置归为一处，则将相关证据标为歧义并撤销其等价/裁剪资格，而不是折叠生物学重复。
5. 路径不能重复使用同一来源坐标，也不能在不同来源中重复加入同一已确立的等价区间；未表示范围仍能回到每个来源坐标。

当前集中在 `PathPolicy` 的版本化数值：pair identity 下限 0.95、支持锚点至少 100 bp、新增未知连接 N=100、beam=8、最多 20,000 次路径/边变体评估、32 轮局部搜索、一次最多替换 3 个节点、每对端点最多 4 个边变体、等价坐标边界上限 200,000。它们是可审计的初始实现参数，**不是经真实样本标定的生物学最优值**；100 bp 是编辑锚点要求，不是候选 contig 的统一长度过滤。断开/失败的路径提案同样消耗评估预算，边和 beam 剪枝均有记录。等价关系复杂度超过边界上限时报错，不退回按 ds 累加覆盖。

定向证据：

- 新增 38 项路径/覆盖测试：跨 ds 输入顺序置换、c3 桥接及反向坐标、原 N 邻接与替换、短片段独有贡献、重复/方向冲突、不允许伪造 join、indel 插入保留、片段坐标偏移、ds 复制不加分、来源切换不偏好同 ds、传递重复冲突和搜索预算。
- 等价覆盖算法另在 120 组随机小实例中与独立逐碱基连通分量 oracle 比较：总独有长度、部分区间表示长度、重复加入判断和未表示来源碱基均需一致。
- 联合回归 **267 项通过**（389.319 秒），覆盖 I2、旧生产准备/后续 LGZ、来源方向和新路径内核。审阅中最后补充了“来源切换不偏好同 ds”的修正与测试；最终源码另运行内核、坐标基础、命名兼容及工作区更新 **100 项回归通过**（66.968 秒），不将两次重叠测试数相加。
- 运行库清单通过维护脚本生成并验证；未更新正式 Release 或客户工作区。

**I3a 提交时的后续接入边界（证据准入已在 13.5 实现，生产事务仍待切换）：**

- 从 I2 catalog 及完整原始 ref/pairwise 证据生成真正通过准入的 `Placement`，不能把 catalog 中的候选/最大 MAPQ/包围跨度直接当作可信锚点；加入实际已有 QC 条件。
- 定位歧义、跨 chr 特异末端与重复末端、原 N 连接推导、pairwise-only 候选及不同 chr 间来源占用，需要在该适配层落实。当前内核只处理一条 chr，不能据此宣称全局来源互斥已完成。
- I3a 当时的内核对直接 ref 候选的关系有保守的 ref 覆盖相交约束；在生产接入前须用实际 ref paired blocks 校验对应锚点，区分不同 ref 位点的重复与双方 ref 外的真实同源末端，不能保留此粗粒度约束作为最终判据。
- 使用新选择结果替换 `lgz_prepare_inputs.py` 中的 first-ds 构建逻辑，并与区间级 donor、来源卡片、校验器和正式决策产物一起接入。不得为现有测试保留旧算法分支。

目前生产入口仍使用旧路径选择；新内核测试通过不等于 A01–A20 端到端通过，更不是真实样本 q0/Final Path 改善的结论。


### 13.5 I3b：真实证据准入、跨 chr 局部来源与构建结果

新增 `server/tools/lgz_core/q0_admission.py` 及 GRT 模块别名。`build_q0(root)` 现在可从 I2 成功清单读取实际输入，返回 q0 FASTA records、逐 chr 路径、来源占用区间和正式决策数据；它**不自行写入 `grt/q/q0.fa`**，避免绕过后续 q0/donor/metadata 的共同发布事务。

数据与准入：

- 重新读取已绑定的全 ref、组内及补比对 PAF；恢复 fragment 到原始 source 的偏移，并核对 catalog 的区段/原 N 邻接确实来自原 FASTA。catalog 中的“候选”不是准入结论。
- 以实际 paired blocks 排除同一 query 区间上的竞争 chr、方向及不同 ref 位点，检查同一方向链的顺序。MAPQ 255 仍表示未知，MAPQ 很高也不能抹去竞争命中。
- 对支持区间做局部复杂度筛选，避免一个长片段整体复杂度较高就把其中的端粒式重复尾部当作独特裁剪锚点。对没有充分 ref 定位的来源，可以通过已有独立定位来源的序列上下文逐轮建立定位；无根的 pairwise 循环不能生成 chr。
- 新 `ReferenceAnchor` 保留 source/ref 精确对应。重叠/等价判断比较对应碱基的 ref 位点，不再要求两个候选的 ref 包围跨度相交；因此双方 ref 外的实际重叠可以被采用，而不同 ref 位点的重复不会仅因序列相同被折叠。
- pairwise 派生定位不伪造直接 ref 坐标。竞争命中即使落在当前选取 fragment 之外或方向相反，也不能在裁剪判定中被隐藏。
- reads QC 决策若提供，必须明确覆盖每个来源；未测量则明确记录，不伪造 QV。实际 QC 的运行及输入冻结仍由主准备入口负责。

跨 chr 与原 N：

1. 跨 chr 的重复末端保留为歧义，不据此裁掉原序列，也不作为独特重叠锚点。
2. 同一未分 N 区段包含多个 chr 的特异区间时，不仅凭 ref 自动拆开。其他已定位来源提供支持后，可以选择精确、互不重叠的局部来源区间；仍不将其标成“已证明组装错误”。
3. 原本没有直接 ref 命中的尾部，若得到另一 chr 上独立定位来源支持，也进入局部选择判断；若其他来源同时支持原来的连续结构，则保留连续候选，不为了贴合 ref 强拆。
4. 原 N 邻接可保留无独立比对锚点的相邻区段，但这种区段不能成为独立路径种子或序列重叠锚点。原 N 数、区间和来源保持可追踪；矛盾定位不能由原邻接直接覆盖。
5. 构建结果检查跨 chr 的实际来源占用，包含仍保留的原 N 区间。部分 chr 无结果时明确记录；整份 q0 无可信路径则失败。

补齐 I2 的实际信息缺口：

- 增加 `partial_source_discovery`。已有 ref 候选、但仍有连续 >=100 bp 不被粗筛 ref 支持覆盖的来源，也会作为 query 对当前已锚定区段集合进行补比对；不再只有“整段完全未定位”才能做跨组发现。
- 粗筛用 ref paired-base identity >=0.90、可用 MAPQ >=20 请求更多信息，**不直接授权定位/编辑**。保留整个来源区段作 mapper 上下文；只选择需要更多信息的 query 子集，不无条件执行所有 ctg 的全基因组两两比较。
- 新关系可为已分组来源增加其他 chr 的候选，原分组表不重写。新任务同样受成功回执、原始缓存、`--skip-self` 冲突和失败即终止规则约束。证据准备策略升至 version 2，旧成功清单不能冒充新准备结果；不因此无理由重算内容相同的原始映射。

有界搜索修正：初始化使用真实 ref 邻域及实际 pairwise/原来源邻接提出插入位置，每个候选默认最多 8 个位置，并记录剪枝。避免把预算浪费在所有不可能位置上，从而丢失原本可独立接入的可信区段。受控案例中，80 个独立候选在 500 次评估预算下全部保留；竞争搜索仍受原有总预算约束，不宣称全局最优。同分时先按稳定原始来源身份、区间和切点几何决胜；PAF 记录/证据 ID 的排序变化不能改变所选来源或切点。

准入初始参数集中在 `AdmissionPolicy`：ref identity 0.90、竞争 identity 差 0.02、独立 ref seed 的 MAPQ 下限 20、支持锚点 100 bp（短来源按其实际长度判断）、整段选择支持比例 0.20、k=15、局部 distinct-kmer 比例 0.50、碱基 entropy 1.20。`PathPolicy` 升至 version 2。这些是可追踪的初始策略，不是已标定的生物学最优阈值；低于整段支持条件时只选择有支持的局部区间，其他来源坐标仍保留为未选择范围，不能据此称其错误或不可用。

结果身份绑定准备清单的完整内容、选择器源码、策略及显式 QC 决策。选择器或证据在构建中变化会报错。决策保留实际原始证据引用、局部选择、被替代的候选、未定位区段、未构建 chr、原有/新增连接及搜索限制。

验证记录：

- 证据准入、路径和等价覆盖的组合测试通过；其中含实际文件清单到构建结果的校验，以及输入损坏、构建器变化和不绕过发布事务的检查。
- 使用本机 minimap2 **2.26-r1175** 对受控随机序列生成实际 ref/pair PAF，经成功证据准备后重建 25,000 bp 的 c3 双侧桥接结果，逐碱基等于受控输入真值。
- 另一个实际 minimap2 测试没有预先提供跨组 pair PAF，由 `partial_source_discovery` 找到已归组来源的另一 chr 尾部关系，随后得到预期局部来源结果。
- 最终 **165 项联合定向回归通过**（100.233 秒），包含准入/路径/坐标、I2 证据准备、既有主准备入口、命名兼容及运行库更新；运行库清单校验为 `verified, changed=[]`。以上均不是物种样本/客户数据质量收益或 App 导入验收。

**I3b 提交时尚未完成的切换（已在 13.6 接入主准备事务）：** 当时 `lgz_prepare_inputs.py` 尚未使用本构建结果，下一步必须在同一事务中替换旧 first-ds 路径构建、冻结区间级 donor/占用范围，并更新来源证据校验；不能把新选择证据伪装成旧 assignment，也不能只写一份新 FASTA 绕过 donor 和来源契约。I4–I6 与完整 Server/App 交付仍需继续。


### 13.6 I3c / I4 冻结基础：主入口切换与共同发布

`lgz_prepare_inputs.py` 已删除原 first-ds 候选选择、ref 包围范围去冗余、按原轨道成员顺序串接整条 contig 的实现。它现在在完成实际 reads QC（如启用）之后，直接调用 `build_q0`，将其结果与 D0/Dtel、来源映射及证据一起准备、验证、发布。没有旧算法分支或策略开关。

保留的 `primary_dataset` / `support_datasets_json` 是项目元数据，不决定 q0 候选资格或排序。donor 同分决胜也使用稳定原始来源身份，不再使用 `--ds` 行号。原 `chr_assignments.tsv` 不被改写；区段方向使用实际选择证据，不强行套用整条 contig 的旧显示方向。

新增发布契约：

| 产物 | 语义 |
| --- | --- |
| `metadata/package.tsv` 的 `schema_version=3` | 新 q0/donor 语义的显式版本门槛；workflow 机器标识和 Server Final Path JSON 版本不顺带改名 |
| `metadata/grt_q0_selection.json` | `lgz_q0_selection_artifact_v1`，包装实际构建决策及所引用原始比对/原 N catalog 的文件哈希 |
| `metadata/grt_q0_freeze.json` | `lgz_q0_donor_freeze_v1`，绑定选择结果、q0 来源行、q0 证据行、原始来源、来源占用、允许新增区间和完整 donor 成员 |
| `grt_evidence_registry.tsv` 中 `q0_construction / q0_path_selection` | 明确表示 q0 选择证据，引用版本化选择产物；不伪装成 `assignment` 或直接 ref PAF |
| `server/tools/lgz_core/q0_publication.py` | 发布序列化、source/card 映射、donor 可用区间计算和准备事务验证；不是完整 q4/App 交付校验器 |

坐标与资格：

- JSON 中的 source/occupied/available/member-available 区间为 **0-based half-open**；现有 q-segment 和 donor-member TSV 的来源区间仍为 **1-based inclusive**，只在明确边界转换。
- 每个 donor 成员 FASTA 仍是完整正向原始 contig，保留比对锚点上下文；其可新增区间单独冻结。已进入 q0 的源区间以及长 N 区间不能因为成员 FASTA 完整就被视为可再次新增。
- 部分进入 q0 的来源，只要仍满足原序列有效性、reads QC、长度等 donor 条件且存在未占用的可用区间，就可以留在 D0；不再按整个 contig 因“用于 q0”排除。
- Dtel 的上下文资格与实际新增授权分开。没有可新增区间的成员不能仅凭端粒信号再次追加已占用来源；后续使用仲裁见 I4 待办。
- donor-set ID 同时绑定成员和其允许区间。相同完整 FASTA 在不同 q0 占用状态下不能冒用同一冻结授权。
- “来源尚未选入 q0”不等于自动具有 donor 资格；序列/QC 拒绝仍有效。未测 reads QC 仍明确标记 `not_run`，不伪造分值。另修正实际输入 `+inf` QV 被转成零值的问题，避免错误作为低质量淘汰。

事务与缓存：

- q0 FASTA、source TSV、选择/冻结 JSON、证据 registry、D0/Dtel 与 checkpoint 在同一原有回滚事务中发布。
- 发布前验证序列可以由原始来源逐段重建、来源区间不重复、原 N 间隔确实存在、完整 donor FASTA/manifest 与来源一致、可用区间正好来自未占用的非长 N 来源区间。
- 新 fingerprint 升至 builder version 5，并绑定选择器、发布器及实际主准备脚本身份。旧 q0 缓存不能冒充新结果；原始映射缓存仍按已有独立规则复用。
- 缺失/损坏必需证据、序列化不一致或发布失败均不安装新结果；旧可用产物保留。输入确实改变并成功重建时，旧的下游生成结果不残留。

I3c 提交时的可运行范围与门槛（后续接入进度见 13.7）：

- 生成脚本现在产生 package schema 3；新主准备入口只构建这一版本，不自动迁移客户 schema-2 项目。
- Step1 已适配版本 3 的冻结校验和 q0 选择证据保留，并验证 q0、q0r1、q0f、q1 的序列/来源重放。已有版本 2 的输出读取兼容不等于保留旧 q0 构建器。
- **Step2/3、端粒收尾、完整 Server 契约、App 导入尚未适配版本 3。** 已实测：新 q0→q1 成功后，现有 Step2 在修改任何 q0/q1/冻结文件之前拒绝版本 3；不会套用旧 donor-reuse 规则继续输出。这是功能分支的实施中状态，不是整条 `run_all.sh` 已完成验收。
- 下一步必须修改实际候选使用仲裁（包括 `repair_common.arbitrate` 的旧允许复用行为）、当前路径占用/替换释放、跨阶段账本及 primary-only 限制，再放行版本 3。不能只改 `SCHEMA_VERSION` 常量。
- 仍使用旧准备过程构造 schema-2 输入的下游测试夹具，需要改为明确的冻结测试输入或新版场景；不得为了这些夹具恢复旧构建算法。完整交付/报告和旧包可读性继续由 I5 覆盖。

验证：

- **177 项定向回归通过**（125.867 秒）：主入口、选择/冻结、真实证据、来源区间、reads QC/缓存、发布回滚、Step1 重放、命名兼容和运行库更新。
- `prepare_metadata_test.sh`、`prepare_full_test.sh` 均通过，包含新生成 package schema 3。
- 主入口测试证明：第一个 ds 只有 2,200 bp 的情况下，实际写出的 q0 是来自 a/c/b 的 5,000 bp 桥接序列；交换 ds 元数据顺序不改变 q0 或来源选择。
- 检查了部分来源保留完整 donor 上下文、准确剩余区间、原 N 来源占用、反向切片、未分组来源不被伪造为原 assignment、损坏输入保留旧结果，以及发布前重建失败的回滚。
- 运行库清单仍由维护脚本生成；没有更新正式 Release、客户工作区或 master。尚未通过完整 Step1→q4/Final Path、App 导入或真实样本质量验收。


### 13.7 I4a：当前路径区间授权与实际阶段接入

本节记录 I4a 提交时的实施进度；当时 I4 仍未全部完成。后续跨 ds 结构证据、真实工具验证与 q0 短片段保护见 13.8；完整 Server/App 契约和真实样本验收仍需 I5/I6。

新增 `lgz_core/source_intervals.py`（含 GRT import 别名）：

- 用原始 `(dataset, contig, start, end)` 建立全部 chr 的当前路径占用；同名 contig 在不同 ds 中保持独立。源区间在另一条 chr 或相反方向出现，仍然算占用，不能当成可新增序列。
- 完整 donor FASTA 仅提供比对上下文。每个新增候选必须属于冻结成员，且实际使用区间位于该成员的非长 N 来源域内；未通过 reads QC 的来源不能因端粒信号进入 Dtel。
- 替换按实际 query 编辑窗口释放原始 source 区间，反向来源也精确换算。仅在自己真正移除的区间内复用是允许的；幸存区间、其他 chr 的区间和本轮已接受的新增区间均不可重复。
- 拒绝的候选不释放来源。下一轮从实际输出路径重新建立占用，不把历史 `consumed` 列表当作永久占用，也不沿用旧的“同方向、不同 object 可以重复使用”授权规则。
- 结构纠错的“仅删除/补 N”操作显式声明 `interval_edit_kind=remove`，不把用作证据的 donor/reference 误记成新增 DNA。参考来源可以为这类操作提供证据，但不能由此获得参考 DNA 的插入资格；结构判断仍归纠错引擎负责。
- 授权记录写入候选的相关 evidence `parameters_json`，包含工作版本、当前来源状态摘要、实际编辑窗口、新增区间、替换内复用及释放区间。普通比对证据和端粒 MUMmer/minimap 证据都携带该记录。

冻结与缓存调整：

- `grt_q0_freeze.json` 升至 `lgz_q0_donor_freeze_v2`，增加 `informative_intervals`。它表达原来源中可作为 DNA 的域，不等于本轮可新增区间；后者仍需减去当前路径占用。
- 满足序列/QC/长度条件的完整来源，即使初始 `available=[]`，也保留为 D0 比对上下文。这样后续真正删除其 q0 片段时，可以复用释放部分，不需要改写冻结成员 FASTA。
- 初始 `occupied` / `available` 继续由 q0 实际来源计算，并与完整成员一并绑定。v1 冻结不能冒充 v2；须重新运行准备入口生成新冻结，不能靠改 JSON 版本号迁移。
- Step2/3/端粒 checkpoint 纳入来源授权指纹；端粒阶段同时绑定其实际脚本哈希。冻结域损坏在命中阶段缓存或失效旧结果之前失败。

生产调用连接：

1. Step2 的初始 patch 仲裁使用完整 q1 路径。染色体级结构 fallback 若撤销初始 patch，则丢弃旧预占用，从最终可执行候选重新仲裁，避免被撤销的候选继续占用来源；写 q2 前再次检查实际输出。
2. Step3 的结构纠错、第一轮 refill、filter 后第二轮 refill 分别以 q2、实际 corrected 路径、实际 filtered 路径建立授权。每一步输出再次验证全局来源唯一性。
3. 端粒仲裁检查当前完整 q3，而不只是比较本轮两个末端候选。授权窗口与真正保留/替换的 q3 端部一致；写 q4 前再验证。
4. 上述入口已接受并校验 package schema 3，不只放宽版本常量。schema 2 仍可作为历史输入解码，但没有恢复旧 q0 构建器；实际可变阶段也使用当前路径授权。
5. refill 的 baseline/optimized 两种执行方式都使用 `-P` 保留竞争 chains，且记录到原始缓存与阶段参数。避免完整、已占用来源的命中将另一来源的可用命中挤掉；是否能用仍由路径区间与原有候选检查决定，不能把 MAPQ/primary 身份当成源区间授权。

验证边界与剩余工作：

- 单元测试覆盖全局重复、反向投影、替换内复用、删除释放、拒绝不释放、同轮新增冲突、长 N 禁入、冻结成员检查、端部裁剪、证据记录，以及逐碱基随机 oracle。
- 新 q0→Step1→Step2→Step3→端粒 q4 的无编辑案例已跑通并保持真值序列；这不是有结构编辑案例的完整验收。
- 受控两条 chr 的真实 minimap2 refill 案例：同一 bridge 源区间只在 chr1 插入，chr2 的重复使用被拒绝，q4 来源重建/全局唯一性通过。此测试的 MUMmer 明确使用“完成但零命中”的受控工具来隔离 refill 仲裁，不能据此宣称真实 MUMmer 结构纠错已验收。
- 真实 minimap2 的 8 个竞争完整 donor 上下文均保留，baseline 与 batch PAF 内容一致。该检查仅证明这一受控集合，不宣称所有真实大样本性能/结果等价。
- 本机默认 nucmer 不支持流水线使用的 MUMmer4 `--batch/-t` 参数；一次真实含 N 结构案例在该工具边界停止，没有冒称通过。正式有编辑验收仍需兼容的 MUMmer4 环境。
- **I4 剩余：**取消 Step3 direct-overlap 的 primary-only 限制时补齐跨 ds 的序列/外侧锚点/重复歧义依据，不能只删除 ds 判断；验证完整上下文带来的 self-guide/结构候选行为；补齐真实删除→释放→再次使用以及端粒新增的阶段级案例。当前该旧限制仍可能漏掉跨 ds 的安全合并，不把本轮称为 I4 完成。
- **I5/I6 剩余：**Server 契约、App 导入/来源呈现、报告、旧包只读兼容与旧测试夹具迁移，以及真实数据质量与性能验收。q4 CLI 成功不等于这些交付项通过；未发布 Release，也未修改客户工作区或 master。


本轮回归记录：

- 255 项定向测试通过（190.988 秒）：q0 evidence/coverage/preparation/scheduling/paths/admission/publication、source intervals、refill batch、准备入口、LGZ 兼容及运行库更新，以及 Step2/3 结构事件/覆盖/来源/lineage 的独立测试。
- 另单独运行 `test_grt_repair_stages.GrtRepairStagesTests` 中不依赖旧准备夹具的 34 项底层回归，全部通过（0.166 秒）。没有把尚待迁移的旧全流程夹具称为已通过。
- 运行库维护脚本重新生成两份清单，随后只读验证 39 个受管文件，结果 `verified`、无漂移；`production_ready=false`，正式 Release 未修改。


### 13.8 I4b：来源感知的结构证据、跨 ds 合并与真实工具验证

本节接续 13.7 的待办，完成 donor/LGZ 配套的受控实现验证，不替代 I5/I6。新增 `lgz_core/structural_support.py` 及 GRT import 别名，实际接入 Step2 structural fallback 和 Step3，而不只修改独立测试函数。

#### 两个由真实执行发现的问题

1. **自身命中不等于独立纠错证据。** 用真实 MUMmer4 重现：一个 `22 kb + 137 N + 23 kb` 原始 ctg 在 D0 保留完整上下文后，旧 Step2 会仅凭自身命中把 137 N 改成 100 N。现在在当前路径上逐段核对来源；完全来自同一原始 source 的命中，包括其重复/重排位置，不单独授权结构修改。保留这类候选及拒绝原因，不能让最高分 self hit 隐藏其他来源的 crossing/两侧锚点。 同样实测了将相同序列换名放到另一 ds 的情况：它不能仅因有了不同 SourceKey 就获得修改权限。实际 query/guide 上下文完全相同，或仅未知 N 的填充数不同，记录为 `guide_confirms_existing_sequence_context`，不重写现有路径。真正提供新 DNA 的 guide 仍可竞争；相同序列副本的 crossing 命中也不能遮挡另一个真实 bridge 的双侧锚点。重复使用的 context 比较按坐标/来源缓存。
2. **完整同源 donor 上下文会使默认唯一锚点消失。** 真实实验中，left/right/bridge 的序列在多个完整 donor 中出现，nucmer 默认要求 target 唯一的 seed，结果没有产生任何候选 coords。Step2/3 和端粒的 nucmer 现在显式使用 `--maxmatch`；命中是否可用交给后续来源、重复、结构和区间验证，而不是由 donor 集合中的副本数隐式淘汰。实际命令、参数、证据 preset 及缓存身份同步更新。Step2/3 原有不使用 `delta-filter -r` 的规则不变；端粒原有 filter/独立 minimap 验证规则不变。

此前的工具失败针对默认 `/usr/bin/nucmer`。本轮找到并验证了已有 `cgat-server` 环境的 MUMmer **4.0.1**，通过显式工具路径运行；没有安装新软件、覆盖默认工具或修改用户 PATH。

#### 不按 primary/ds 身份判断的 overlap

- 生产调用改为 `promote_direct_source_overlap_merges`。`primary_dataset` 不再参与资格或评分；同名 contig 在不同 ds 中仍是不同来源。保留旧 import 名称的薄转发和历史事件字段名，仅为接口读取兼容，指向同一份策略，不保留旧算法分支。
- 默认仍检查 >=10 kb 的精确、有方向的 suffix-prefix overlap；同时要求两侧实际保留的外侧锚点、局部复杂度、原始来源中没有额外竞争拷贝，以及 guide 对桥接长度和共享序列的支持。不是只删掉 primary 判断。
- 两个来源在 q0 冻结的实际 ref paired blocks 上若将对应碱基定位到不同位置/chr/方向，则不折叠为一次出现。比较原始 source 坐标到 ref 的对应关系，不用 ref 包围跨度冒充相同位点。
- 当前初始策略：外侧锚点各 100 bp，guide 中唯一且方向一致；guide 中间长度与 overlap 一致、碱基一致率 >=0.95、没有未知碱基。复杂度采用 k=15、distinct-kmer 比例 >=0.50、碱基 entropy >=1.20。参数写入阶段 fingerprint 和决策证据；不是已标定的生物学最优阈值。
- 每个候选必须用自己的 guide 证明连接，不复用同一 gap 上其他候选的成功结论。guide 的原始区间、方向、序列哈希、overlap 哈希、ref 证据命名空间及冻结授权身份写入 `source_overlap_support`。
- 成功时保留左侧全部序列，仅删除间隔及右侧已证明重复的 prefix；不插入 guide DNA。不同 ref 位点、重复歧义、缺失外侧锚点或 guide 不成立时，该候选被拒绝，不退回同一候选的宽泛 Type5 删除。
- 不再因为移开左端少量碱基就能匹配而删除该短尾。非 flush overlap 需要独立的变异/错误判定证据；当前缺少这些证据时保留序列并记录未决，不能把可信短序列当成修饰匹配的代价。

#### 内部 N 的语义保持一致

同一原始 scaffold 被长 N 分开的两段，仍可作为两个候选 component 处理：

- 只有 scaffold 自身的上下文时，不重写原 N 数量，也不据此删除序列。
- 如果另一个来源提供独立的完整 bridge，则可以移除错误间隔和已证明重复的部分。
- 两个 nominated overlap 副本恰好位于这两个 N-split 区段时，不因它们共用一个原始 source ID 就直接拒绝；但原始 source 中的额外第三个竞争拷贝、反向竞争或 ref 位点矛盾仍会阻止合并。
- 最终来源仍记录原始 scaffold 的实际区间，不生成虚构 contig；原 N 证据留在不可变 q0 选择产物中，后续删除由结构事件解释。

#### q0 的可信短片段不能被旧长度 filter 推翻

真实流水线另外重现了 `130 kb + 100 N + 1.2 kb` 的问题：q0 中有 ref 支持的 1.2 kb 来源，在没有任何反对证据时，仅因小于旧 filter 的 100 kb 阈值而从 q4 丢失（131,300 bp 变为 130,000 bp）。因此：

- 从 schema-3 冻结的 q0 occupied source 区间出发，精确投影到**本轮实际路径**，包括反向、裁剪和跨 chr 之后的位置。
- 含有仍保留的 q0 来源区间的组件，不允许仅因长度短而删除；结构纠错仍可依据独立证据修改它，不把 q0 永久锁定。
- 保护是区间级，不是“这个 contig 曾用于 q0”就整条受保护。同一个 source 中后续新增、没有 q0 选择依据的孤立区间，仍走既有长度 filter；schema-2 历史输入也不能凭空获得不存在的 q0 选择证明。
- 过滤其他组件时，连续保留组件之间的原有间隔一并保留；只折叠被删组件两侧的分隔。不再因为删除某个末端片段，就把另一处无关的原 `137 N` 连接改成 `100 N`。
- 事件用原有 `kept_intervals` 的连续区间表达可重放结果，并增加 `edit.q0_protection` 记录授权身份和受保护的短组件。阶段 fingerprint 记录这条规则。

修改共享 replay 模块也会刷新 q0 准备的代码身份；需要重跑准备入口生成一致的新冻结，但相同输入的原始比对仍可按其独立缓存复用，不手改旧冻结版本/哈希。

#### 受控实测范围

`test_source_structural_pipeline.py` 使用真实 MUMmer4、delta-filter、show-coords 和 minimap2 执行 Step1→q4；pre-q0 输入采用明确的受控 fixture，不冒充完整真实样本准备/生物学验收。覆盖：

1. 正向和反向原始 `137 N` 连接，仅有自身上下文或添加一个同序列、不同 ds 的副本时，q0/q1/q2/q3/q4 的序列均不变。
2. 原始 scaffold 的 N-split 重叠片段，在独立 bridge 支持下合并；额外相同序列副本不遮挡该 bridge，q4 保留原 source 的两段准确区间。
3. 不同 ds、同名 contig 的 12 kb overlap，在 baseline/optimized 两种执行方式下均合并为同一真值序列，guide 不进入 q4。
4. 原本 `available=[]` 的 right 来源，经真实 Step2 删除 prefix 后，其中 `[2000,10000)` 在 chr2 的后续 refill 中被采用；q4 同时保留 chr1 的 `[12000,16000)`，全局来源无重复。
5. 真实端粒新增恢复 `TTTAGGG × 80`，q4 序列正确；接受候选的两种比对证据均携带当前路径授权。terminal search 本身的成功记录不是编辑授权，二者分开检查。
6. q0 已选择的 1.2 kb 短组件经过全部阶段后仍保留，q4 保持 131,300 bp；filter 事件明确记录保护依据，而不只是碰巧触发“不能删完整条 chr”的兜底。

另有来源级单元验证：ref 坐标偏移/跨 chr/反向、额外重复拷贝、低复杂度、非 flush 尾部、guide 缺失/几何不符/含 N、候选间证据隔离、自身重复命中以及独立锚点不被 self crossing 隐藏。Step2 的完成日志也区分接受的结构修改与实际 donor DNA 新增，避免“accepted=0”掩盖已有结构编辑。

剩余边界：

- `--maxmatch` 是保留所需同源候选的语义变化，不能宣称与旧唯一-seed 结果相同；高重复/大样本的时间、内存和候选规模仍须由 I6 实测，当前小型真值案例不能代替性能验收。
- I5 的 Server/App 契约、导入、报告、旧包只读兼容和旧全流程夹具迁移仍未完成；不因为上述 q4 CLI 跑通就把交付标为完成。
- 没有发布 Release、迁移客户工作区或向 master 合并/推送。


最终代码回归：279 项定向测试通过（250.727 秒），包括本节 16 项结构证据单元测试、6 项真实工具流水线测试（含正反向、序列副本及 baseline/optimized 子场景），以及此前 q0、冻结/授权、filter/refill、准备、兼容、运行库与独立结构事件回归。另单独运行 34 项不依赖旧准备夹具的 repair 底层回归，全部通过（0.170 秒）。运行库维护脚本同步后只读验证通过：39 个受管产物无漂移，工具源文件哈希表明确包含新增 canonical 模块与 GRT 别名。旧全流程夹具迁移和 I5/I6 不计为通过。


### 13.9 I5 交付契约：保留的 q0 来源不是修补事件（Server 阶段）

旧交付链条有一个与新 q0 不相容的假设：`grt_promoted` / `cross_chr_grt_usage` 来源只能由后续 accepted repair event 引入。新 q0 已可直接选择这类来源；沿用旧检查会在 Final Path 发布时拒绝它，而只移除检查又会丢掉来源证明。

本阶段采用两种明确的来源证明，不伪造事件或 assignment：

- 后续修补新增片段仍须关联真实的 accepted path-producing event，并保留原有的双向链接校验。
- 没有关联修补事件的最终 source 片段，必须被冻结 q0 中同 chr、同 ds/contig、同方向的原始 source 区间完整覆盖，且携带对应 q0 选择证据。裁剪后的子区间允许保留；同名来源、区间外部分、其他 chr、错误方向或仅有区间外框不能替代证明。
- Final Path 的逐段 source、长度和 evidence 还必须与 q4 TSV 一致；q0→q4 各个版本的原始 source 区间均检查全局不重复。
- `grt_used_contigs.tsv` 同时收集最终保留的 q0 来源和真实修补来源。q0-only 卡片的 `accepted_event_ids_json` 合法为空，但必须精确反向关联实际保留的 Final Path segments。已经被删除且不再出现的 q0 来源不生成“仍在使用”的卡片。
- 同一张 full-contig display card 可以包含不同方向的片段。normal card 保持原始 assignment 的显示方向；promoted card 使用第一个实际保留片段的方向。二者都不改写片段自身的方向。

#### 版本边界

在现有 `grt_precomputed_v2.json` 中定义显式 package-schema-3 extension，而不是放松旧 schema-2 的规则。新扩展要求 `grt_q0_selection.json` / `grt_q0_freeze.json`，并增加 `q0_construction`、`q0_path_selection` 和 source 坐标声明。验证冻结文件、q0 选择、原始来源和比对文件的内容身份；不以当前安装代码的 SHA 取代历史包的来源事实。

schema-3 的粗分组 assignment 表可以为空，但表本身及其正确 header 仍然必需。是否有可用 q0 由完整比对和选择证明决定，不能为了通过导入而制造 assignment。schema-2 仍保持原来的非空限制。

#### 没有比对对象，不等于缺少比对结果

新增 q0-only 卡片后，单来源染色体也可能需要 used-source 记录。这时不生成假的 self PAF：

- normal card 的已有主视图比对对象来自该 chr 的原始 assignment 成员；promoted card 的补充比对对象还包含该 chr 实际保留的 promoted 来源。
- 只有 schema-3 且这个实际比较域内没有另一个来源时，pairwise evidence 列表才可为空。
- 有比较对象却缺少 pairwise 证据，仍然报错。空 PAF（实际完成比对但无命中）和空 evidence 列表（根本没有比较对象）不混为一谈。
- ref 证据、原始 full-source 序列及最终来源追溯仍然必须存在。

`test_q0_delivery.py` 覆盖 q0-only normal/promoted、粗分组方向与选中片段方向不同、单来源/空粗分组、真实修补与保留 q0 共用一张卡、已删除根来源不产生卡片，以及错误根证据、错误卡键和丢失 pairwise 反向链接。另验证包目录迁移后仍可读取，以及真实端粒新增与保留 q0 来源具有各自的证据链。流水线仍使用明确的受控 pre-q0 比对 fixture，加上真实 Step1→q4 工具执行；不作为真实样本效果或性能验收。

**完成边界：本节仅是 I5 的 Server 交付实现。Rust/App schema-3 校验、导入/持久化、报告及完整验收仍未完成；当前 App 不应仅放开版本号就接受新包。I5/I6 不因此标记完成，Release、客户工作区和 master 均不在本阶段操作范围内。**


本节最终验证：90 项定向回归通过（432.278 秒，包含新增交付测试以及 q0 publication、live source、真实结构流水线、schema-2 contract、LGZ 兼容和 workspace runtime update）；随后新增的真实端粒交付测试单独通过（1 项，7.575 秒）。后者验证 q0-only backbone 卡片没有修补事件，而实际 tel 来源卡片具有真实 accepted event 和补充比对证据。共覆盖 91 个不同测试方法，不把子场景或重复运行重复计数。运行库只读验证通过：39 个受管产物无漂移，`production_ready=false`，未修改正式 Release。


### 13.10 I5 原生校验、导入及精简 App 投影

完整 Server 包和精简 App 包是两个不同边界，不能把版本号放开后混用证明责任：

1. **完整 Server package schema 3**：Rust 校验器读取冻结文件与选择文件，核对必需 artifact 清单及内容哈希、原始 source FASTA 清单、选择结果生成的精确 q0 rows、source 序列身份、原 N 间隔、informative / occupied / available 区间及完整 donor context。q0 根证据和后续真实事件分开追溯；各 q 版本不得重复使用同一原始 source 区间，最终片段还必须与 q4 来源表一致。校验通过后才进入既有导入事务。
2. **精简 App package schema 3**：Server 投影入口先完整验证 schema-3 源包，再裁剪为 App 所需数据；仍不搬运 q0 / donor / 原始运行证据 / checkpoints。App 端校验包版本、manifest、Final Path、来源范围与显示卡关系，并执行跨 chr、跨方向的原始 source 区间去重。`no_fasta` 只验证其实际携带的索引、坐标和内容身份声明，不声称验证了不存在的序列字节。
3. 新 App 包保留显式 package version 3；**不是把新 Server 语义伪装成 package version 2**。Final Path 的 local-evidence schema version 3 是另一个已有协议维度，不与 package generation 混淆。旧 Server package 2 及旧 App package 2 的入口保留读取能力，不引入旧 q0 构建策略开关。
4. 粗 assignment 全空时，schema-3 App 的 assignment / track-order 表可以只有真实 header，但不能缺文件；有 assignment 却没有其排序仍须报错。q0-only promoted 来源由真正的 used-source 卡提供，不通过制造 assignment 或 accepted event 填表。
5. 原有持久化结构可以存储 q0-only 卡片的空事件列表及实际 Final Path segment 链接，因此没有为此新建数据库表或交互 UI。

原生实现位于 `grt_package/q0_provenance.rs`，与现有 contract / delivery validators、source-card 校验联动。Python 同步补强冻结清单完整性，避免仅核对“清单里剩下的条目”，却容忍删除某个必需 hash 绑定；q0 evidence 的坐标体系、方向、query FASTA 和阶段也必须与实际选择一致。

#### 共用冻结夹具，而不是两套不同的成功示例

`tests/fixtures/grt_contract_v3/` 中的 UTF-8 文件快照由 Python 与 Windows-native Rust 共同读取：

- 单个反向、粗分组未归属的 q0 来源，保留空 assignment、无比较对象、无修补事件这些真实状态。
- chr1 三个 ds 的反向 bridge，整条 `c` 的 display baseline 为 `+` 而实际选中片段为 `-`；chr2 保留原始 scaffold 的 `137 N` 连接。
- 同一单来源样本的实际 full / no-FASTA App 投影。Python 将新生成投影与快照逐文件比较，Rust 使用相同快照进行校验、导入和持久化回读。

快照包含当时的代码身份和工具路径，但读取它不要求安装同一份 selector，也不执行其中的历史工具路径。辅助 freezer 先验证源工作区，再验证迁移后的材料化副本；不能通过手工补假 assignment、假事件或改 checksum 把错误夹具“修好”。pre-q0 PAF 几何明确是受控输入，后续流水线使用真实工具，因此这些是契约与导入验收，不是生物学效果验收。

本轮不修改 frontend、不启动浏览器、不发布安装包；需要证明的是原生数据链与可显示的项目来源，而不是重新设计 UI。报告输出、旧全流程夹具迁移、完整真实比对准备/样本效果与规模性能仍需继续验收；I5/I6 和整体目标保持未完成。


最终验证：Python 定向回归 **89 项通过**（430.963 秒）；Windows 原生 `cargo test --lib grt_package::` **46 项通过**，`cargo test --lib importer::` **56 项通过**。另有两项 opt-in 性能探针按原配置 ignored，不计为通过，也不作为性能结论。新增 full / no-FASTA App 测试实际完成导入、项目初始化、q0 来源卡材料化和项目 Final Path 显示映射（`grt_display_available=true`）；full 模式还重验了持久化 q4。运行库同步后再次只读验证：39 个受管产物无漂移，未改变正式 Release。

后续验收还要补齐历史 schema-2 的 source-free boundary/correction 等事件在两端的分类一致性，不能把当前旧包基线通过当成所有历史边界都已覆盖；并继续报告输出、旧流程夹具迁移和 I6 的真实比对/规模测试，包括完整 Server 包的哈希与 FASTA 校验成本。

补充的 fail-fast 边界：未选中的 chr 必须有明确的 `path: null` 决定；缺少 `path` 字段不是默认跳过。accepted 的 DNA 新增事件也必须有 source 证明，不能把 source-free 事件改名为 fill 来绕过根来源校验。这两类反例已纳入回归。


### 13.11 I5 历史事件一致性与 q0 决策报告

#### 结构指导不等于新增来源序列

使用同一份 schema-2 契约输入复现了两端差异：Python 接受 `replacement_kind=gap` 的事件及其 `structural_evidence` donor usage，Rust 却报 `accepted path-producing event ... lacks Final Path segment`。原因是 Rust 把所有 `replace` / `correct_boundary` 都当成了 DNA 新增。

现在两端使用相同的 path-producing 定义：fill、patch、refill、端粒新增，以及明确 `replacement_kind=source` 的 replace。filter、纯 boundary 调整、gap-only replacement 不凭空生成 Final Path 片段或来源卡；其中的 donor 可以只是结构指导。`tests/fixtures/grt_contract_v2/non_path_events.json` 是双方共用的契约案例，不是修复效果数据。原生测试还实际导入、持久化并回读这些事件，验证其 Final Path / source-card 链接为空，而指导用途仍保留。

这不是放松来源检查：真正的 source replacement 仍必须关联最终片段；删去已接受来源的 used-source 卡仍须被两端拒绝。schema-2 和 schema-3 的 used-card 集合均须准确对应真实来源事件，schema-3 再加入保留的 q0 根来源。

#### 报告的事实与边界

新模块 `server_report_q0.py` 在成功发布边界读取正式选择产物，检查 selection SHA、q0 FASTA SHA 与 q0 rows 的冻结身份，然后生成有界摘要：

- 各 chr 的状态和实际来源 ds / bp / 原始 contig 数 / 来源片段数；`partial_path` 不称为完整染色体，`not_constructed` 在摘要区单独警告。
- 分开显示输入原有 N 连接、新增未知连接和最终保留的 overlap。真实输入 `137 N` 与未知连接的 `100 N` 不混同，参考上未覆盖的 1,000 bp 也不被解释成插入了 1,000 个 N。
- 显示参考未被选中锚点覆盖的范围、候选来源未被路径表示的范围，以及未选来源区间和候选准入记录。未选部分包含冗余/QC 排除等原因，不自动等于生物学缺失或 donor 可用范围。
- 搜索轮数、评估次数、停止原因、剪枝记录数、策略限制和操作数可查；过程中的 bridge 操作数不当作最终修补次数，也不声称全局最优。
- 大表保留准确总数、产物路径和内容哈希，只预览前 200 行；完整决策和原始证据仍留在 Server 正式产物中。离线 HTML 仍只读自己的报告快照，不回读工作区。

schema-3 输入统一显示为候选组装，统计比较不再只取第一个 ds 当作 q0 基线。`primary_dataset` 仍是项目元数据。报告里的 `q0_mode` 只是历史/当前产物的解释标记，不是新旧 q0 构建策略开关；新包缺 selection/freeze 时不会回退到旧构建或旧说明。

“关闭 Gap”改为 **Gap 数净变化（q4 − q0）**，增加时保留正号，不再被 `max(0, ...)` 隐藏。旧 `closed_gap_count` JSON 字段保留作兼容净减少量，并明确标记它不是真实缺失序列闭合数；新展示使用 `gap_count_change`。T2T 展示限定为已输出序列的结构条件，不等于完整基因组或独立生物学正确性验收。

schema-3 报告的 q0 统计来自本次成功 prepare 的快照，或成功 finalization 同时捕获的 q0/q4 快照。prepare 失败时，磁盘上残留的旧 q0 不会被当成本次构建；后续失败时可以展示本次已成功的 q0，但不能拿旧 q4 作结果。不同 run/schema 的成功快照拒绝混入。

#### 验证范围

报告集成夹具已从“调用旧 schema-2 q0 producer”迁移到当前 q0：受控 pre-q0 PAF 几何，加上真实 MUMmer4/minimap2 的 Step1→q4→evidence CLI。末端 donor 产生真实 accepted 来源事件，保留了首次发布、缓存复用、事件与最终来源协调、后续失败隔离这些原有断言。测试通过 `GPM_TEST_MUMMER_BIN` 指定 MUMmer4；缺少真实工具时会明确 skip，本轮运行提供了工具并实际执行，不能把其他环境的 skip 算作通过。

另有 Windows Node 数据契约回归读取同一份 schema-3 App 快照。测试按原生 read model 的方式从 FAI 提供完整 source_length，不从片段 end 猜长度；确认反向 q0-only promoted 来源无需修补 trace，也无需新增前端策略或放松来源长度检查。没有前端生产代码改动、浏览器或安装包验收。

新报告 helper 已纳入工作区 runtime 的必需文件清单，并通过生成脚本更新内容身份。I5 的这些定向证据不替代 I6 的完整 Server/E2E gate、旧流程夹具迁移及获授权真实样本与规模性能验证。


本节验证：98 项 Python 定向回归通过（366.390 秒，包含真实工具报告集成、10 项 q0 报告验证、运行库与 runner 回归）；增加“缺少已使用来源卡”的共享反例后，12 项契约测试再次通过（181.927 秒，不重复计入不同测试总数）。Windows 原生 LGZ 契约/导入组分别 47 和 56 项通过；两项 opt-in 性能探针保持 ignored，不作为性能结论。Windows Node 的 LGZ 状态/显示数据回归 16 项通过。生成脚本同步并只读核验通过：39 个受管产物无漂移。
