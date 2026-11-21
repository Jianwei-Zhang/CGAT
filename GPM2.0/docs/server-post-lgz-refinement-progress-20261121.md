# LGZ 后精修实施记录

本记录对应 [已确认设计](server-post-lgz-refinement-design-20261121.md)。目标仍是四工具、编号工作区、真正的精修 Final Path 与 App 完整交付；不能以迁移基础设施或额外 FASTA 替代目标。

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
