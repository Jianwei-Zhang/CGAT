# GPM GRT 与原版 GRT：gs1/gs2 逐 gap 对比（2026-08-31）

## 结论

当前 GPM 集成流程与原版 `Genome-Repair-Tools` **不完全一致**。以两套项目中新生成的 q0 共 13 个 `N{100,}` gap 为对象：

| 分类 | 数量 | 含义 |
| --- | ---: | --- |
| `exact_match` | 4 | gap 终态一致，且相关最终染色体序列完全一致 |
| `outcome_match_sequence_diff` | 5 | 最终均填补、均移除或均保留 gap，但编辑边界或最终序列不同 |
| `result_mismatch` | 4 | 一边填补/移除，另一边仍保留 gap |

gs1 最容易被“最终 gap 数量”误导：GPM 与原版最后都剩 2 个 gap，但对象不同。GPM 保留 Chr3 的两个 gap；原版保留 Chr2 的第一个 gap 和 Chr16 的第二个 gap。因此不能把 `2 vs 2` 判为结果一致。

gs2 的唯一 gap 在两边最终都还存在，但 GPM 的 q4 与 q0 完全相同；原版先后执行 Type5 和 Type1 结构编辑，最终在该染色体净删除 105,918 bp。它属于“未填补终态一致、序列不同”，不是严格一致。

完整逐项证据见 [grt_gap_comparison_gs1_gs2_20260831.tsv](grt_gap_comparison_gs1_gs2_20260831.tsv)。坐标均为 q0 的 1-based closed 区间；若原版编辑导致坐标移动，表中另列最终坐标。

## 输入与公平比较边界

输入包：

- `D:\Desktop\gs1_lvzao .zip`，SHA-256 `c029cc26ee398318a8e9b055e6d2b42fe6a563e7984019fc6426a35d9d5bc61f`
- `D:\Desktop\gs2_ara.zip`，SHA-256 `dafe14cfcc4c8713dbeb2bbd3728af2a0766765b89d87d1f479168df0b13bb91`

两个输入包是旧的 App delivery，只保留 q4，没有完整 q0-q3、D0、事件与 checkpoint，不能直接用于本次比较。因此先从包内 reference 和完整 dataset FASTA 重建 workspace，再执行当前 GPM 完整流程。

重建参数保持原包语义：score 60、minimap2 `asm10`、10 threads、保留 self alignment、不提供 reads、不显式指定端粒 motif。gs1 的数据集顺序为 `nextdenovo`（主）→ `flye`（辅）；gs2 为 `my_hifiasm`（主）→ `verkkoper`（辅）。

原版 GRT 使用每次新 GPM 运行产生的同一个 q0 和冻结 D0，执行 `--stages 1,2,3,4 --repair-mode aggressive --no-quality-filter --skip-craq`。这是可比较的 q0/D0 边界；原版 CLI 只有一个 contig pool，并不会像 GPM 一样冻结 D0 后再独立构建 Dtel。为隔离 Stage 4 供体域差异，另用 GPM Dtel 对原版 Stage 4 做了受控复跑。

| 项目 | D0 成员数 | D0 FASTA SHA-256 | Dtel 成员数 | Dtel FASTA SHA-256 |
| --- | ---: | --- | ---: | --- |
| gs1 | 111 | `9f72de7f2e99cfbb480ab9a92189c9496c6031dfaf010008484f9711ecd8ef05` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| gs2 | 69 | `baba8cfcd51f328d4397f103523d0b2001e262873653542075c08591cf1e05e1` | 9 | `461294769a89c300969fd2cbd20e8e874cca5923f7de0477dc1d40cc20fea374` |

代码版本：

- GPM：`2ab5b8485f88990091b5d48996d7a9cb9928809d`
- 原版 GRT：`975848d08b629ab3ce8d8ef5d0006e0479dfd75a`
- Python 3.11.14、samtools 1.23.1、minimap2 2.31-r1302、MUMmer/nucmer 4.0.1

## 两个 gpm_server 完整重跑结果

两个 workspace 都执行了生成的完整 `run_all.sh`，没有跳阶段，并分别通过独立 `server/tools/grt_contract.py --bundle` 校验和 ZIP 完整性校验。没有覆盖用户原 ZIP，新 full delivery 位于：

| 项目 | run ID / 计划单元 | q0 → q4 | contract 摘要 | 新 ZIP |
| --- | --- | --- | --- | --- |
| gs1 | `20260831T060354Z-1376606-3ac4c28f`；32/32 success | 12 gap → 2 gap | 92 events、121 evidence、32 segments | `D:\Desktop\gs1_lvzao_gpm_server_rerun_20260831.zip`；SHA-256 `59801a8f15e1b528180c6386696620a7614f591cdc293adae2659c9cd75cb0a6` |
| gs2 | `20260831T061600Z-1382579-d1ef2e50`；15/15 success | 1 gap → 1 gap | 12 events、21 evidence、7 segments | `D:\Desktop\gs2_ara_gpm_server_rerun_20260831.zip`；SHA-256 `73f25e32ce387487f094f4e0b33ae3f3e5fba926f669376c59564aaaa846ce08` |

gs1 的 GPM 分阶段结果：

| q 版本 | 染色体数 | 总长度 (bp) | gap 数 | FASTA SHA-256 |
| --- | ---: | ---: | ---: | --- |
| q0 | 22 | 51,700,178 | 12 | `f887e50f4771df58aea9c1bb5f8f1143a6963a0461b040838438766523bae674` |
| q0r1 | 22 | 51,715,392 | 11 | `420a4b57815af5bd5ee967c918db5111452a2827ab51f90ec05500a839108308` |
| q0f / q1 | 22 | 51,313,476 | 4 | `17ce291fe3b6b91ba2af790b81fe5de05e3bb1b40e49fc2060c8792d9a76d06f` |
| q2 | 22 | 51,471,302 | 3 | `f42ff56be2307be10dabf5bdf937af1828a96b92e784ecccca240aad953fbb7f` |
| q3 / q4 | 22 | 51,431,646 | 2 | `78fb4dcfd3721929b316b7d67d6122eae56c249ac3fb98fd722bfff320c848d6` |

gs2 的 GPM q0、q0r1、q0f、q1、q2、q3、q4 完全同 hash：`f6bd0ae940e12e79440377856912dcd5ef50e21ccdfacd7fd98f509218291029`。即所有 stage 都留下可审计的 rejected/unresolved 记录，但没有接受任何序列编辑。

### Final Path

- gs1 的 Final Path 覆盖 22 条染色体、32 个 segment：27 个 source、3 个 patch、2 个 gap；3 个 patch 都能回溯到 accepted event、evidence 和 D0 fragment。
- gs2 的 Final Path 覆盖 5 条染色体、7 个 segment：6 个 source、1 个 gap、0 个 patch，准确表达 q0 到 q4 没有接受编辑。
- 两套 Final Path 都已由 contract validator 按每条染色体的 q4 长度和 sequence SHA-256 重建校验通过。
- 原版 GRT 没有与 `grt_final_path.json` 对等的谱系数据模型，只输出阶段 FASTA 和各模块 repair JSON。因此 Final Path 不能做同 schema/hash 比较；逐 gap 表用 GPM event/Final Path 对照原版阶段 FASTA、gap report 和 repair report。

## 原版 GRT 结果

| 项目 | 阶段 | 染色体数 | 总长度 (bp) | gap 数 | FASTA SHA-256 |
| --- | --- | ---: | ---: | ---: | --- |
| gs1 | 输入 q0 | 22 | 51,700,178 | 12 | `f887e50f4771df58aea9c1bb5f8f1143a6963a0461b040838438766523bae674` |
| gs1 | Stage 2 | 12 | 27,426,514 | 10 | `f707d85289f80a54a3dbd5f00f73cd46ada3be69ea0eca840bc996f50361fc81` |
| gs1 | Stage 3 / final | 12 | 27,172,773 | 2 | `bc23d707646fd6da34e26eca9e7f62b5667c0fd657d64f22d4a31584987989d9` |
| gs2 | 输入 q0 | 5 | 134,184,023 | 1 | `f6bd0ae940e12e79440377856912dcd5ef50e21ccdfacd7fd98f509218291029` |
| gs2 | Stage 2 | 5 | 134,082,692 | 1 | `e8908e7b2acd33ae8125594e9a3a082b2e0bc3d09a9a08b67ee95dd2cb1498c9` |
| gs2 | Stage 3 / Stage 4 | 5 | 134,078,105 | 1 | `b2fb52c6d0e7f2065ae675338d16dd332f813133822547ebcf6207e7d48498c9` |

gs1 原版 Stage 3 的 final-fill 第一轮填掉 3 个 gap，之后 fragment filter 移除 5 个 gap-bearing component，最后保留 2 个 gap。gs2 原版没有填掉唯一 gap，只改变其邻域结构。

## 逐 gap 结果摘要

### gs1

| q0 gap | GPM | 原版 | 判定 |
| --- | --- | --- | --- |
| Chr1:1021973-1022072 | Step1 填补 | Stage 2 填补 | 终态同、替换边界和序列不同 |
| Chr2:1422529-1422628 | Step2 填补 | 两次结构修正后仍为 100N | 结果不一致 |
| Chr2:1467254-1467353 | Step1 filter 移除 | 被 Stage 2 Type5 区间吸收 | 终态同、结构不同 |
| Chr2:1552529-1552628 | Step1 filter 移除 | final-fill filter 移除 | 终态同、最终 Chr2 不同 |
| Chr3:2371812-2371911 | 保留 | final-fill 填补 | 结果不一致 |
| Chr3:3314786-3314885 | Type5 后仍保留 | Type5/Type1 后填补 | 结果不一致 |
| Chr8 两个 gap | filter 移除 | Type5 后 filter 移除 | 最终 Chr8 长度和 sequence SHA-256 均一致 |
| Chr16:2075129-2075228 | Step3 refill | final-fill 填补 | 终态同、序列不同 |
| Chr16:2125086-2125185 | filter 移除 | 最终仍保留 | 结果不一致 |
| Chr17、Chr18 各一个 gap | filter 移除 | Type5 后 filter 移除 | 各自最终染色体长度和 sequence SHA-256 均一致 |

### gs2

唯一 gap `GWHBDNP00000004.1:371442-371541`：

- GPM Step3 将唯一结构候选分类为 Type3 `simple_translocation`，因 anchor pair 的 source/orientation conflict 拒绝；q4 与 q0 完全一致。
- 原版 Stage 2 执行 Type5，删除 101,382 bp；Stage 3 再执行 Type1，替换 4,687 bp；最后仍有一个 100N gap，坐标移至 366855-366954。
- 两边都是“未填补”，但原版最终 Chr4 比 GPM 少 105,918 bp，严格不一致。

## Stage 4 不能只看 success 状态

- gs1：GPM Dtel 为 0 个成员，q3=q4；原版用 D0 找不到端粒供体并跳过；受控使用空 Dtel 时也跳过。
- gs2：GPM 检查 10 个染色体端，2 个缺少端粒信号，最终接受 0 次修复，q3=q4。
- gs2 原版用 D0 时提取 1 个候选修复区，用 GPM Dtel 受控复跑时提取 6 个；两次日志都报告 Stage 4 success，但两次最终 FASTA 都与原版 Stage 3 输入完全同 hash。

因此原版 Stage 4 的 `success` 表示流程完成，不表示序列发生过端粒恢复。本次两项目在 Stage 4 均没有实际 FASTA 改动。

## 原版 gs1 的染色体误判缺陷

原版 Stage 2 合并最终 genome 时用前缀判断“是否已经存在染色体”，导致：

- `Chr10`–`Chr15` 和 `Chr19` 被误判为已存在的 `Chr1`；
- `Chr20`–`Chr22` 被误判为已存在的 `Chr2`。

日志明确记录 `Skipping possibly duplicate original chromosome`。因此原版 gs1 从 22 条染色体降到 12 条，整份 final FASTA/hash 无法与 GPM 严格等价。该问题不影响这 12 个 q0 gap 所在的 7 条染色体逐 gap 归因，但属于原版全基因组输出的额外严重差异。

## 复现命令骨架

当前 GPM 每个项目使用以下语义执行（路径按项目替换）：

```bash
micromamba run -n cgat-server bash server/prepare.sh \
  --ref <reference_name> <reference.fa> \
  --ds <primary_name> <primary.fa> \
  --ds <support_name> <support.fa> \
  --score 60 --aligner minimap2 --minimap-preset asm10 --threads 10 \
  --out <fresh_workspace>
micromamba run -n cgat-server bash <fresh_workspace>/run_all.sh
micromamba run -n cgat-server python server/tools/grt_contract.py \
  --bundle <fresh_workspace>
```

原版主对照命令：

```bash
micromamba run -n GRT python \
  /mnt/d/desktop/cgat/Genome-Repair-Tools/scripts/genome_repair_tools.py \
  -q <fresh_workspace>/grt/q/q0.fa \
  -c <fresh_workspace>/grt/donors/<d0>.fa \
  -t 10 -o <isolated_upstream_output> \
  --stages 1,2,3,4 --repair-mode aggressive \
  --no-quality-filter --skip-craq --quiet
```

原版程序会在当前工作目录写 `final_contigs_processed_*.fa` 和 `patch_report.json`，所以本次从独立 `/tmp` 工作目录启动，避免污染原版代码仓库。第一次从 DrvFS 仓库目录启动 gs1 时还触发了跨文件系统 `copy2` 的 `Operation not permitted`；该次诊断运行已排除，不作为比较证据。

## 判断

当前 GPM 的执行、contract、Final Path 与交付 ZIP 均完整有效，但它不是原版 GRT 的逐 gap 结果复刻。差异集中在候选接受规则、结构冲突保护、component filtering 时机，以及 GPM 的冻结 D0/独立 Dtel 语义。若后续目标是“与原版行为完全兼容”，需要先明确是否也要复刻原版的激进 Type5/Type1 编辑；若目标是“保留 GPM 可追溯且更保守的结构编辑约束”，则这些差异应作为有意行为纳入回归基线，而不是简单改成原版输出。
