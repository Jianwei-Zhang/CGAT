# cen / tel 库 review 与测试记录

日期：2026-11-04

范围：审查并验证 `51e348e` 的官方/本地库实现及 `b10d53e` 的实施收尾结论。
本轮不修改已发布资产、不运行用户真实工作区、不升级用户安装。

## 1. Review 发现与修复

| 优先级 | 问题及复现 | 处理 |
| --- | --- | --- |
| P1 | 有 cen 标记时，`renderCentromereMarkersForTrackCtg` 引用作用域中不存在的 `i18n`，6 项标记渲染测试全部抛 `ReferenceError`。 | 由调用者显式传入当前 i18n；修复后运行前端全量测试。 |
| P1 | cen FASTA 的哈希与解析分别读取路径，期间输入被替换时，来源 SHA-256 可能属于旧文件，实际使用的序列却来自新文件。新增确定性“读取后替换”用例可复现。 | 对官方/本地条目与本次显式 cen 输入均先捕获一次字节，再对同一份字节计算来源哈希、解压及解析；新增压缩输入用例。 |
| P2 | 手工编辑 TSV 的重复表头会覆盖 note，多余单元格也会被忽略；新增用例复现静默信息丢失。 | 严格校验库表头集合、唯一性及每行列数，拒绝 malformed TSV，不默默截断依据。 |
| P2 | 新旧 Server 模块哈希变化后未同步长查询恢复模块的生成清单，标准质量门禁在 runtime integrity 步骤失败。 | 使用已有 `sync_server_runtime.py --write` 重新生成 `resume-base.json`、`branch-runtime.json`；不修改 native binary，也不修改恢复算法。 |
| 测试维护 | 两个旧 schema 迁移夹具只创建部分表，缺失在历史 schema 中已经存在的 tel/cen 表，因而迁移 7 报 `no such table`。 | 补齐夹具必需的两张表；未通过跳过迁移或忽略损坏数据库来让测试通过。schema 6→7 的真实表迁移与数据保留用例仍执行。 |

前述 P1/P2 均依据失败用例/质量门禁复现后修正，不以此前静态检查代替运行证据。

## 2. 验证清单

- Windows 前端全量 `node --test`：**2,547 passed，0 failed**。
- Windows backend `cargo test --manifest-path app/backend/Cargo.toml`：**332 passed，0 failed，6 ignored**；ignored 为仓库既有显式忽略用例，不计入通过数。
- Windows Tauri `cargo test --manifest-path app/src-tauri/Cargo.toml --lib`：**31 passed，0 failed**。
- Windows `npm.cmd run build`：成功；构建有 chunk 大于 500 kB 的现有提示，非失败；完成后删除本次生成的 `app/frontend/dist/`。
- 库管理与快照针对性回归：**11 passed**，包括新增的源字节一致性、gzip、malformed TSV、add-cen 复制与 remove 不修改既有快照。
- 真正的 MUMmer4 `4.0.1` 及 prepare/assignment/扫描集成：**4 passed**。
- Server 标准质量门禁：**完整通过**，包括 444 项 Python 测试、8 组 shell 测试、运行清单/版本/LF 校验及最后的 **Server-to-App E2E**；未设置 skip override。
- 完整门禁运行期间又补入两项测试：add-cen 复制隔离、真实 prepare 默认库链路；最终文件分别以 11 项库测试及 4 项真实工具集成测试完整重跑通过，上述计数不冒充来自同一次 suite collection。

Windows Node/npm、Rust/Tauri 测试与构建均在 Windows 宿主运行。Server Python/shell 与
Linux backend CLI E2E 在 WSL 运行，E2E 的前端 Node 仍转发到 Windows 宿主，Linux Cargo
使用独立 `/tmp` target，未复用 Windows 的 `node_modules` 或 Tauri target。

## 3. 真实工具覆盖与证据边界

新增 `server/tests/test_cen_scan_integration.py` 使用真实 nucmer/show-coords，不使用比对输出 mock：

1. 四个官方单体各自构造正、反链重复阵列，检查准确 1-based 坐标、覆盖长度、100% identity、来源条目及 MAPQ=0；随机序列作负对照。
2. 两段单独不足 min-len 的阵列，200 bp 间隔可以合并通过，201 bp 间隔不能跨越；不同 contig 不拼接通过阈值。
3. 两种不同 cen 家族相邻时保留两条来源，不重复计重叠支持。
4. 真正执行 `prepare.sh → reference alignment → assign_chr_groups.sh → chromosome command`，不传 tel/cen 参数；确认官方库自动启用、双链 tel 标记与 CentO 候选区域均产生且快照校验成功。

另外使用已获取的 ENA 原记录 **AY101510.1** 的 62,203 bp 序列作一次公开水稻片段检查。
运行前复核原序列长度与记录 MD5 `9f6d944e997a731a9e37cb0b72e1562f`。
默认 `identity=80`、`min-len=10000` 下得到一个 CentO 候选区域：

- 1-based 范围：22,635–62,136；区域跨度 39,502 bp。
- 命中覆盖 33,749 bp；命中加权 identity 93.914%；来源为 `cen_rice_CentO`。
- 本地本次扫描约 0.041 s，子进程峰值 RSS 19,848 KiB；这是小片段单次观察，**不能外推为全基因组性能**。

上述结果证明实际工具接口、坐标解析、候选合并及小规模真实序列执行能工作；
**不证明全物种敏感度、全基因组误报率，或 200-bp 间隔具有普遍生物学最优性**。
四条代表 cen 序列仍不是各物种所有着丝粒的完整模型。未做浏览器或原生窗口交互验收。

## 4. 可重复执行入口

```bash
# Linux Server 环境需含仓库锁定的 MUMmer4、minimap2、samtools 等依赖
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
  -s server/tests -p test_annotation_library.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
  -s server/tests -p test_cen_scan_integration.py -v
bash scripts/quality-gate-server.sh
```

真实 MUMmer 测试会在缺失工具或仅安装 MUMmer3 的环境显式 skip；不能把 skip 算作真实工具验证。
完整质量门禁必须包含最后的 Server-to-App E2E，不能使用 skip override 冒充完整通过。

## 5. 收尾结论

本次代码 review 发现的阻断性问题已修复并由回归测试覆盖；上述本地自动化测试与构建通过。
前端没有通过关闭 cen 标记规避错误，迁移没有通过跳过缺失表错误绕过验证；本地数据、项目快照、
Light 无 FASTA 等既有边界保持不变。工作区修改只涉及本功能修复、对应测试、受影响的生成清单与文档。

本轮没有访问/改写客户数据，没有创建 Release、替换 Server 源码资产、构建安装包或部署站点。
正式发布仍须单独执行发布流程；生物学全基因组验收和原生 UI 交互验收不在本报告的通过声明内。

## 6. 远端补充验证

2026-11-05 在 SSH 180 完成四组真实完整 Server 流程及 resume、446 项无跳过的 Python 回归、
8 组 shell 回归和生成运行时的架构匹配只读校验。数据、作业、环境修正过程、交付包哈希及
验收边界见 `server-cen-tel-library-ssh180-test-20261105.md`。本地验证结论与范围不作追溯改写。
