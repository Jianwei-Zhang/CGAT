# Q0 正式入口的定点迁移（2026-11-26）

## 问题与边界

原工作区的 `prepare_q0_evidence.sh` 仍绑定 11/22 的 reader/builder。该版本不接收
`positive_threshold`，候选补证冷缓存可能继续执行整段原生回退。不能仅修改命令参数，
也不能把普通 `run_all.sh` 当作带原生路由凭据的续跑入口。

本次扩展既有显式迁移工具，不运行 `update.sh`、不替换整个 Server，不重写任何初始
比对或父检查点。运行中的冻结整麦草案及其结果比较继续使用各自的工具包。

## 修复

- `prepare_q0_runtime_transition.py` 明确接受 `positive_threshold`；从 Q0 builder、
  selector、阈值准备/验收模块递归收集局部依赖，并单独绑定旧工作区缺失的
  `workspace_layout.py`。完整源码清单、来源提交和目标文件原身份都必须吻合。
- 沿用原始 native/self/cross 来源、真实读取器和正常工作区锁。不把已选草案、孤立
  PAF 或新普通检查点当成旧路由检查点的替代品。
- 三处已批准的策略差异（区域目标分批、原生回退只读缓存、移除路径覆盖边界硬上限）
  逐项绑定旧/新 AST 摘要；其余原有 mapper 参数和定位准入策略仍须一致。不是删除策略检查。
- 新 reader 把补证范围固定传给真实 `prepare_evidence`，不使用会另行选路的 `auto`
  或默认 `full`。阈值语义进入正式 reader 声明与证据身份。
- 旧受保护的 `run_orchestration.py` 没有 `open_paf_text`。Q0 包初始化只给真实旧模块
  补上缺失的严格 UTF-8 / 1 MiB read-ahead API；不替换模块、不伪造 `__file__`、不改
  checkpoint/hash 代码，已有 API 的新运行时不动。新进程和 spawn worker 均走同一入口。
  `q0_alignments.py`、`q0_query_windows.py` 和区域 mapper 保持原内容身份，避免为接口兼容
  让有效 raw/projection 缓存失效。新增 I/O 实现进入 builder/selector 身份，安装清单另行绑定包初始化。

## 安装与验证不是正式计算

```bash
# 在已有正确 x86 环境与隔离的、内容已核对的迁移目录中执行。
python3 -Bu resume_q0_science.py --transition "$PWD/transition.json" --install-runtime --install-only
# install 已生成并绑定真实 reader 声明；不再重复 --describe-only 全量扫描。
python3 -Bu resume_q0_science.py --transition "$PWD/transition.json" --validate-only --validate-unit q0_chr:Un
```

`--install-only` 必须同时指定 `--install-runtime`，不能与 `--validate-only` 混用。
它正常持锁、先备份、再原子替换、生成真实声明；失败按既有事务回滚。它不会调用 Runner、
调整持久线程资源、启动 mapper 或运行后续单元。备份和安装 journal 均保留在隔离目录。

指定单个 `--validate-unit` 时要求新运行时确已安装，使用真实原始只读检查点读取器，
输出 `validation-selected.json`，不能冒称已完成全部 25 个父单元验证。
未指定该参数的既有全量只读 preflight 保持原行为。

正式续跑仍需先审阅 22 组结果与新证据引用，然后使用**同一新 transition 的**
`resume_q0_science.py --transition ... --threads 32`（不再加安装参数）；它保留原始路由
checkpoint 的核验与复用。不要直接调用 stock `run_all.sh`，不要跳过最终科学验收。

## 16:00 后安装事实与下一代兼容

`q0-threshold-entry-20261126.JjS32RPJ` 的安装已完成，源码 `4b29638e`，
transition `e1c31548e0bd733db85a6e8c5a9c3c3becd59df5c58aa6ecc6fd6f136dd96a6d`。
`43098456` 在安装完成后重复 describe 扫描时被主动停止，不是安装失败；
`43098462` 用安装器已封存的真实声明完成 `q0_chr:Un` 验证。
25 份原 checkpoint 和受保护控制文件均未改写，未启动正式计算。
详见 `q0-selection-reuse-preflight-20261126.json` 的 prior_entry。

下一代 selection 复用迁移必须以上述实际安装为前驱，不再使用 11/22 的旧入口 SHA。
已安装的 `workspace_layout.py` 仅在前次成功 journal 绑定且新旧字节相同时接受；
不允许任意已有文件混入。冻结外层的 `file_identity` 不支持 `within=`，新 Q0 的兼容
分支调用其原实现并保留路径包含及稳定目标检查，不更换原检查点模块。
