# LGZ naming contract / LGZ 命名约定

Confirmed on 2026-10-30.

## English

- Public abbreviation: **LGZ**.
- Full name: **Linking Inter-assembly Units for Genome Zipping**. Preserve spelling, capitalization and the hyphen in `Inter-assembly`.
- Use the abbreviation in compact labels, headings, notices, trace/source labels, CLI output and explanatory prose after its first definition.
- Use the full name in App-owned algorithm explanations and hover tooltips, including the result switch, baseline restoration, read-only anchor explanation, result intervals, junctions and alignment evidence.
- Define the full name at first introduction in the bilingual project/Server READMEs, website overview and glossary.
- This is a naming change, not an algorithm, schema or project migration. Keep existing `grt_*`/`Grt*` identifiers, CLI flags, database fields, tool filenames, package paths and machine-facing stage IDs compatible. The progress, cache-hit and report readers accept both the previous and current log prefixes.
- Preserve historical Release Notes, archived changes, benchmark/validation evidence and provenance paths verbatim. They are historical records, not current product labels.
- The website source under `docs/en`, `docs/zh` and `docs/.vitepress` is intentionally local and Git-ignored. Synchronizing its text does not publish the website or place that source under version control.
- This source change does not replace published App installers or authorize release-asset replacement or formal-site deployment.

### Validation

- Windows-host frontend: 2,219 tests passed; production build passed. The built JavaScript contains the full name and no standalone retired abbreviation; generated `dist/` was removed.
- Windows-host backend: `cargo test --locked grt_package` passed 33 tests, with one pre-existing opt-in benchmark ignored; `cargo fmt --all -- --check` passed.
- Server: all 378 Python tests passed in a local Linux source mirror; 189 Server source/test files were verified byte-for-byte against this working tree. Regression coverage includes old/new progress prefixes, canonical cache-hit detection and report collection.
- Local website: 64 public page entries validated and VitePress production build passed; both generated glossaries contain the exact full name. Six canonical Release Notes and 14 generated changelog pages remain synchronized and unchanged.
- Scoped diff/whitespace and shell syntax checks passed. No browser/native desktop interaction, biological workload, new installer publication, Release-asset replacement or formal-site deployment was performed.

## 中文

- 对外缩写统一为 **LGZ**；全称为 **Linking Inter-assembly Units for Genome Zipping**，大小写与 `Inter-assembly` 的连字符保持不变。
- 紧凑标签、标题、通知、追溯来源标签、命令行输出及首次定义后的说明文字使用缩写。
- App 中算法说明类悬浮提示使用全称，包括结果开关、预计算路径恢复、只读锚点说明、结果区间、连接与比对证据。
- 中英文项目/服务端 README、文档站概述与术语表在首次介绍时给出全称。
- 本次仅改名，不改变算法或执行项目迁移；保留既有 `grt_*`/`Grt*` 标识符、命令行选项、数据库字段、工具文件名、交付包路径及机器阶段 ID。进度、缓存命中与报告读取入口同时兼容新旧日志前缀。
- 历史发布说明、已归档变更、基准/验证证据与来源路径原样保留，不作为现行产品文案。
- 文档站 `docs/en`、`docs/zh`、`docs/.vitepress` 源文件按仓库现有规则仅存本地且被 Git 忽略；同步文案不等于上线或纳入版本控制。
- 本次源码提交不替换已发布 App 安装包，也不授权替换 Release 附件或部署正式站。

### 验证

- Windows 宿主前端：2,219 项测试通过，生产构建通过；产物包含准确全称且不含独立旧缩写，生成的 `dist/` 已删除。
- Windows 宿主后端：`cargo test --locked grt_package` 为 33 项通过、1 项原有按需基准跳过；Rust 格式检查通过。
- Server：本地 Linux 源码镜像中 378 项 Python 测试全部通过；189 个 Server 源码/测试文件与工作树逐字节核对一致。回归覆盖新旧进度前缀、规范化缓存命中及报告采集。
- 本地文档站：64 个公开页面条目校验通过，VitePress 生产构建通过，生成的双语术语表包含准确全称；6 份既有发布说明及 14 个生成页面保持同步且未改写。
- 范围内差异、空白和 shell 语法检查通过。未执行浏览器/原生桌面交互验收、生物数据分析、安装包发布、Release 附件替换或正式站部署。
