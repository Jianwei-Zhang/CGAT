# 执行手册：Claude Code / deepseek-flash

## 0. 执行约定

按 M0→M7 顺序推进。每个里程碑完成后更新本目录 `implementation-log.md`：提交/工作树状态、完成内容、命令、退出码、产物、尚未解决事项。
日志从实现开始时新建，本次文档没有预填完成状态。遇到失败先修复或明确记录阻塞，不在未运行的测试上打勾。

任务目标为 GPM2.0 Server 的生产实现，不修复原版 Genome-Repair-Tools 的递归 bug，不把测试数据复制进生产源码，不单纯提高 max-fill。
由当前 Claude 会话执行，不建立子代理，不调用其他模型代写。最终验收由 Codex 独立完成。

## M0. 环境、工作树、可重现的旧基线

### M0.1 检查与记录

读取根 AGENTS.md、GPM2.0/AGENTS.md、`/home/xbzhang/.codex/RTK.md`；有新子目录规则时继续读取。
Comet 依规则执行 resume-probe；本次文档编写时结果为 none，后续状态可能改变，不自行启动 Comet change。
父仓库在 master；只提交任务文件，不提交既有原版目录的 pycache/FASTA 等修改。
先用 CodeGraph 查找代码；无匹配时再用 rg/read。不得重新索引仓库。

记录实际 HEAD 与文档基线的差异。若 HEAD 已前进，先确认有关实现未被别人更改，不用旧行号盲改代码。
WSL 写入使用 `/mnt/d/desktop/CGAT` 小写路径；若沙箱只允许大写别名而拒绝写入，按宿主权限机制处理，不能忽略 AGENTS.md。

可用环境线索（必须实测，不保证未来仍可用）：

```bash
rtk proxy /home/xbzhang/micromamba/envs/GRT/bin/nucmer --version
rtk proxy /home/xbzhang/micromamba/envs/GRT/bin/python -c 'import Bio; print(Bio.__version__)'
rtk proxy /home/xbzhang/micromamba/envs/GRT/bin/minimap2 --version
```

系统 `/usr/bin/nucmer` 曾为 3.1，不能执行原版/GPM 的 MUMmer 4 参数。
环境路径是否存在、工具版本、可执行路径和实际返回码都要保存。工具名字可见不等于版本正确。
需要依赖的运行遵循项目宿主环境规则；不要为了绕过权限换工具或改算法。

### M0.2 保存基线，禁止覆盖原项目

`D:\Desktop\gs2` 只作为输入与历史结果。读 FASTA 的程序可能在旁边写 `.fai`，因此把输入及需要写入的中间文件复制到临时实验根目录。
建议实验根为 `/tmp/gpm-unresolved-gap-<时间或唯一ID>`；空间先检查，使用独立 off/audit/apply 输出，不在原 gs2 上直接重跑。
大 FASTA/PAF、原始数据库和临时包禁止提交 Git。

必须保存：

- 三套完整输入 FASTA 的记录名、长度和内容哈希，数据集顺序（pre 第一、assembly 第二）。
- metadata、grt/q/q4.fa、report/final_summary.json、report/steps/grt-step2.json 和 grt-step3.json 的校验值。
- 旧版代码快照或可复现 commit，完整运行参数、工具版本、线程数。
- 所有旧成功结果的保护清单，历史 q4 每条染色体序列哈希和长度。

gs2 不是完整 Server workspace。若原 Server workspace 可读，可将其复制为基线并核验输入/运行库；否则从以上完整 FASTA 重建。
重建时用相同 reference/dataset 名称和顺序，并从 metadata/report 恢复旧参数。端粒参数、分配参数不能凭默认值推测。
以下仅为已知输入的命令骨架，路径须换成复制后的输入，旧参数核准后才能作为可比基线：

```bash
# 在 GPM2.0 目录、正确的宿主工具环境中执行。
rtk proxy bash server/run.sh \
  --ref ref /path/to/copied-inputs/ref.fa \
  --ds pre /path/to/copied-inputs/pre.fa \
  --ds assembly /path/to/copied-inputs/assembly.fa \
  --max-fill 1000000 -t 4 -o /path/to/experiment/baseline
```

先用修改前代码运行。核对历史 gs2 与新跑 baseline 的成功片段语义差异；若工具版本/参数差异造成不同结果，要解释并冻结可比基线，不能把历史差异归于新算法。
必须同时保留历史 gs2 成功清单与匹配环境新 baseline 清单。不能只验证 chr10 分区，再宣称所有旧 gap 无回归。
禁止在工作目录运行已修改算法后，把结果重命名成 baseline。

M0 产物：baseline-manifest.json、baseline-successes.json、baseline-reproduction-diff.json、commands.log、工具版本记录。
M0 退出条件：可比旧基线已建立；缺失参数/数据明确列出，无法解释的成功项差异未被忽略。

## M1. 坐标投影与保护清单，先于编辑实现

建议先完成纯函数职责，不要求死守函数名称：

```text
freeze_baseline(paths, records, effective_events, consumed_intervals)
    -> immutable stage baseline + hashes
build_protected_intervals(baseline, guard_bp)
    -> target intervals + protected junctions + canonical source identities
project_source_and_gap_origins(paths, working_gap)
    -> original gap identities + explicit coordinate-space mapping
compare_preserved_successes(before, after, edit_map)
    -> exact semantic differences, missing items, changed junctions
```

清单从实际路径重建序列，不只比较 JSON 字段。source 内部 N、跨片段 N、被过滤合并的来源、负向路径都要支持。
来源不完整时返回明确失败，不能用坐标接近或 contig 同名猜测。
保护区包含成功片段本体和左右 10 kb 连接区；有效 correction/filter 修改也须可证明不被本次改动破坏。

先写失败测试：一段新替换虽然不覆盖旧 patch 中点，却删了其端部；应拒绝。另写长度缩短导致下游坐标平移但旧源序列不变的正例；应通过。
不要比较整个 JSON 的时间戳或 run_id 来决定是否序列回归。

M1 产物：保护清单构建/比较代码，坐标/保护专项测试，真实 gs2 成功清单统计。

## M2. 新候选构建，只做 audit

新增模块放在 grt_core，生产旧入口暂不改变默认路径。
实现：残留 gap 枚举、受限迭代窗口、同供体同向锚点链、canonical donor 去重、跨其他 gap/成功区间拒绝、目标跨度与填补长度分开检查。
使用当前 stage 冻结序列；复用 q2 比对前必须投影验证。实现 parser identity 0–100%/0–1 的统一约定和范围校验。

不要只找最近的一左一右：最近锚点可能来自重复或错误片段。收集合法链，并保留失败原因和竞争解释。
不得因小窗口出现不同 donor 锚点就结束，也不能只看到第一组能拼接的链就接受。
完整 donor 集检查不能降级为单 chr 分区；重复 member 别名要归并，其他真正竞争 locus 不能丢弃。

M2 产物：audit candidate/attempt 表、raw 比对及命令、对 chr10 是否找到约 1.57 Mb→9.5 kb 候选的解释。
候选范围可以与调查值有小幅变化；必须用精细比对解释，不硬编码纠正为调查值。

## M3. 结构支持与边界验证

依 01-design 的所有门槛验证唯一性、外围链、替代 locus、大删除额外支持和两个新接头。
对 gs2 需使用完整 pre/assembly/ref 检查“这段是否为重复/错位”，不把来自同一 contig 的两段比对计作独立组装支持。
记录覆盖率的分母、重叠区去重方式、identity 的计算方式，以及被删除候选序列在保留路径中的另一个位置。

细化插入切点后，重新计算目标删除区间、donor 消费区间和全部保护冲突；禁止只在粗候选阶段检查一次。
输出每项门槛的原始测量值、阈值、pass/fail 和引用证据。
含歧义或缺少大删除支持的候选为 needs_review，不自动应用。

M3 退出条件：可靠正例能通过；真实插入/供体缺失/重复多拷贝负例不能通过。
目标若暂未通过，继续诊断；不能把未证实的删大片段作为默认自动路径。

## M4. 原子替换、事件和重放

在不相交的冻结坐标编辑集合上构造新序列。多个编辑按确定性次序生成 output_paths 和 edit_map，记录旧→新映射和被删除区间。
复用源序列读取/方向处理，不能复制旧表的来源标签却插入其他序列。
扩展事件、usage、证据和重放；候选通过验证前不得写 accepted 状态。

接入 run_step3 的 round2 之后、最终 q3 哈希之前。任何后续事件/哈希/表/报告生成仍须一致。
新候选不能让已有 accepted patch/refill 参与重裁决，不得合并吸收旧成功事件。
将 donor fragment、旧消费区间及本次消费同时纳入检查，拒绝候选不消费区间。

必须模拟：验证失败、第二个候选冲突、工具失败、写产物中断，以及同输入重跑。
原子性针对序列/路径/事件/usage 整体，不仅 FASTA 写入。
保留现有 replay_step3 最终等式检查并扩展到新编辑，不删除或弱化检查。

M4 产物：apply 正例、失败无副作用正反例、事件独立重放测试及多编辑坐标测试。

## M5. 运行入口、缓存与交付契约

新增模式和 max-search 参数需要逐层连通：

1. server/run.sh 对应的 server_run.py 解析、验证、参数持久化和恢复白名单。
2. prepare.sh 帮助、参数保存、生成 run_grt_step23.sh。
3. grt_step23.py 的 CLI、run/run_step3 传参和 fingerprint。
4. .prepare_lib 中新增模块及全部传参代码的分发；核对实际 runtime 内容哈希。
5. report、证据包、final_path、schema/validator 和 App 导入读取。

扩展旧 workspace 的恢复行为，不能因为白名单仍只有 out/max-fill 而静默忽略新模式。
缺失新运行库时明确报不兼容并给出需要更新的文件清单，禁止运行一半新一半旧代码。
新模块内容变化和模式切换必须使缓存失效；raw alignment 缓存可按真正依赖复用。

更新中英文 Server 参数说明。模式不需要新增前端开关；如新事件导致既有 App 无法展示，做最小契约兼容并验证，不能无依据改 UI。
新 rejected/needs_review 原因应进入报告，不能只有终端日志。

M5 产物：CLI 参数/恢复/旧 workspace/证据包/报告测试；实际 off→audit→apply→off 的恢复证明。

## M6. 测试矩阵与真实数据比较

### M6.1 必须有的合成测试

| 编号 | 场景 | 必须结果 |
| --- | --- | --- |
| T01 | 右可靠锚点超过 500 kb，小 donor 区间，独立结构支持完整 | 构建并接受完整替换 |
| T02 | 同一序列反向供体/反向主路径 | 序列、来源、方向、重放正确 |
| T03 | 左右不同 donor 或方向/次序冲突 | 拒绝，不改序列 |
| T04 | 短重复、多拷贝、等分 donor、候选截断 | 歧义/复杂，不宣称唯一 |
| T05 | pre 真实大插入、donor 缺失，无额外错误证据 | needs_review，不删除 |
| T06 | 同 contig 未用区间 / 已用区间 | 前者可继续验证，后者拒绝 |
| T07 | 目标覆盖成功片段/guard，精细切点扩大后冲突 | 全部拒绝，旧接头哈希不变 |
| T08 | 跨两个 gap、跨未知来源边界、超目标跨度上限 | 拒绝并准确归因 |
| T09 | donor 超 max-fill / 内部 N gap / 跨 fragment | 拒绝；不改变旧 max-fill 语义 |
| T10 | source 内部 N、跨 path 的 N、负向 gap origin | 正确定位，不能漏检/错投影 |
| T11 | 两个不相交新编辑、先前修改造成偏移 | edit_map、来源、最终坐标完全正确 |
| T12 | 模拟验证/工具/I/O 失败，中断后重跑 | 无半成品，无假成功，重跑确定性 |
| T13 | off/audit/apply/恢复；新模块修改 | off/audit 不改结果，缓存正确失效 |
| T14 | 新事件重放、证据打包、最终导出 | 实际 FASTA、路径、事件重建一致 |
| T15 | 被投影原版字段出现 identity>100 等异常 | 明确解析错误，不以高分通过 |
| T16 | 基线已有成功端粒和多染色体 | 完整下游成功来源、序列、接头不变 |

测试夹具用合成、缩小但保持条件的序列。可以在测试中缩小命名策略阈值以减少数据量，但必须另有至少一个真实尺度的集成例，不能只验证常量重述。
固定 seed；每例要对接受结果或拒绝原因有明确预期，不能仅 assert 程序没崩溃。

### M6.2 现有门禁

在 GPM2.0、适当宿主环境中：

```bash
rtk proxy python3 -m unittest discover -s server/tests -p 'test_*.py'
rtk proxy python3 scripts/check_line_endings.py
rtk proxy bash scripts/quality-gate-server.sh
```

以 QUALITY_zh.md 和实际脚本为准，不锁死历史测试数量。完整 Server 门禁包括 server-to-app E2E。
WSL 不运行 app/src-tauri Rust 验证；若本地只能运行非 Rust 部分，可明确用 `GPM_SKIP_GRT_SERVER_APP_E2E=1` 做阶段诊断，但它不等于完整门禁通过，剩余 E2E 在符合规则的宿主环境/CI 完成。
改到 frontend 时，必须 Windows Node/npm.cmd 测试和生产构建，验证后删除生成 dist；改 Rust 时按 Windows 门禁验证。
若没有相关代码改动，不为文档变更触发前端生产构建。

### M6.3 数据实验

基线冻结后，使用相同输入、环境、旧参数和线程数创建独立 off/audit/apply 工作区。
实现后新命令示意如下，`/path/to/...` 是必须替换的占位符：

```bash
rtk proxy bash server/run.sh \
  --ref ref /path/to/copied-inputs/ref.fa \
  --ds pre /path/to/copied-inputs/pre.fa \
  --ds assembly /path/to/copied-inputs/assembly.fa \
  --max-fill 1000000 --unresolved-gap-repair apply \
  --unresolved-gap-max-search 3000000 -t 4 \
  -o /path/to/experiment/apply
```

不可从 App 的 q4 直接当 Server q2 输入。不可用原版分区运行代替 GPM 完整流水线。
对齐并比较：旧版→新 off、新 off→audit、新 off→apply；分别输出 q3 与最终 q4/包的差异。
保存逐染色体长度/序列哈希、接受/失败/needs_review 数量及全部成功项的逐项比较。
允许新增多个确有证据的修复，但每个都必须有报告；不能把非 chr10 差异默认为允许。

chr06 旧 max-fill 案例作为控制项：不增加 max-fill 的 off/audit 运行应保持旧结果；若 apply 对它产生新结果，也必须按新流程全部证据解释，不能隐式忽略原填补长度上限。
记录实际运行耗时与最大内存，新窗口和候选上限不得造成重复全基因组比对风暴；旧 off 不新增重型比对。

M6 退出条件：03-acceptance 的门禁全部有实际证据。若目标仅 needs_review，单独报告，不能标自动修复完成。

## M7. 提交与交接

提交前检查所有 tracked diff、LF、未跟踪文件和大文件。不要 add -f，不批量 git add .，不提交原 gs2 或 /tmp 数据。
实现/必要测试/文档/小型复现夹具可提交；只更新有合理语义变化的 golden，并附旧→新差异理由，不能用重录快照消掉失败。
按项目规则提交当前 master 的任务相关文件，然后推送该分支 upstream；若不安全，记录具体原因，保留工作结果。

提交下列小型交付物至 `GPM2.0/docs/validation/unresolved-gap-repair/`：

- implementation-summary.md：改动、接口、实际状态、局限、运行命令和提交。
- acceptance-manifest.json：baseline/new commit、输入/运行库/工具哈希、实验目录、命令和结果索引。
- baseline-comparison.json：全部染色体和旧成功项的统计、逐项差异或可定位清单。
- chr10-case.md：粗细切点、供体、结构/唯一性证据、长度变化、两个连接结果、拒绝项。
- checks.md：每项测试命令、退出码、日志路径、CI 链接（如有），未执行项明确写未执行。
- 可重复执行的保护清单构建/比较器及使用说明（代码放 scripts 或 tests 的合适目录）。

大日志/FASTA 保留实验目录，manifest 保存路径及哈希；必要证据还应留在生成的 Server evidence 包，不能只有易失 /tmp 路径。
实现日志应记录文档偏离、未解决问题和任何需要复核的阈值调整。

交接最后写：**“实现已提交，待 Codex 独立验收。”** 提供 HEAD、push 状态、目标 gap 结果、旧成功项变化数和所有未通过门禁。
Claude 不勾选 README 的 Codex 验收项，不发布 Release，不替用户修改原 gs2 项目。
