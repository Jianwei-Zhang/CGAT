# 未解决 gap 大范围替换：Claude Code 交接入口

日期：2026-09-26。父仓库代码基线：`cc112472bbbe6fc6ffcb2bde1913272c9c977394`。

**状态：方案和执行文档已编写；功能尚未实现，目标数据改善和最终验收均待完成。**

## 任务与分工

用户批准：提高 gs2 chr10 指定 gap 的结构修剪、补洞准确性，保护现有成功结果。
实施者：**Claude Code，模型 `deepseek-flash`**。最终独立验收者：**Codex**。
本次交付为文档，不表示 Claude 已开始执行，也不表示 Codex 已验收实现。

| 文档 | 用途 |
| --- | --- |
| [01-design.md](01-design.md) | 事实、算法、门槛、保护规则、坐标与事件契约 |
| [02-execution.md](02-execution.md) | 分步实施、运行环境、真实基线、测试和交付物 |
| [03-acceptance.md](03-acceptance.md) | Codex 独立验收流程、逐项标准与结果模板 |
| [evidence.json](evidence.json) | 原始锚点、报告摘录、数据和代码校验值 |

优先级：用户指令及适用 AGENTS.md > 本目录强制约束 > 局部代码组织选择。
证据与设计冲突时记录并反馈，不得靠放松正确性门槛、删除保护条件或改写基线凑出成功率。

## Claude 启动指令

在 Claude Code 中配置/选择 `deepseek-flash`，然后粘贴以下指令。若别名不可用，报告实际模型与配置错误，不默默换模型。
不要把未经验证的第三方模型配置方法当作仓库命令执行。

```text
请实现 GPM2.0 Server 未解决 gap 的大范围异常片段替换，使用 deepseek-flash。
先读取适用 AGENTS.md、RTK.md，以及：
GPM2.0/docs/plans/2026-09-26-unresolved-gap-repair/README.md
随后完整读取同目录的 01-design.md、02-execution.md、03-acceptance.md、evidence.json。

按 02-execution.md 的 M0–M7 顺序完成，每个里程碑更新 implementation-log.md。
先建立旧版完整 gs2 基线和成功片段保护清单，再写实现。
新增流程放在现有 Step3 两轮 refill 之后。off 保持原行为，audit 仅诊断，apply 只接受通过所有门槛的候选。
不要只提高 max-fill 或现有搜索常量，不硬编码 chr10 坐标，不重裁决旧成功候选，不从参考基因组取序列填补。
当前会话自行完成，不创建子代理。遵循项目的 Windows 验证、WSL 写入路径、提交和推送规则。
每步给出实际命令、退出码、产物和结论；失败后先定位修正，不跳过门禁。
最终提供提交、回归比较器、真实数据证据和验收交接，状态写“待 Codex 验收”，不得自行宣布最终验收通过。
```

## 交付范围和状态

- [x] 问题调查、方案与执行文档
- [ ] M0–M1：基线、坐标、保护清单
- [ ] M2–M3：候选构建、准确性验证
- [ ] M4–M5：原子应用、重放、缓存、CLI、报告/导出
- [ ] M6–M7：完整数据回归、提交、验收交接
- [ ] Codex 独立验收

第一版默认 `off`，通过明确的 `apply` 参数运行新增流程；默认开启不在本次范围内。
默认关闭不能替代 apply 模式的无回归证明。
默认不修改 Genome-Repair-Tools 原版、前端样式、DEGAP、reads 组装流程或旧成功补洞策略。
