# Frontend（gpm_next）

本目录承载 `gpm_next` 的正式桌面工作台前端实现，主运行路径是 `src-tauri` 的 `invoke` command。

当前约束：

- 目标基线：`gpm_v1.0` 在无物理图谱场景的 UI 布局与交互逻辑。
- 路线约束：先后端复刻并对齐，再前端复刻并对齐。
- 工程约束：页面按模块拆分，避免所有逻辑堆叠到单文件。

## 启动

正式桌面运行（推荐）：

```bash
cd gpm_next/app/src-tauri
cargo tauri dev
```

仅前端浏览器预览（兜底）：

```bash
cd gpm_next/app/frontend
npm install
npm run dev
```

说明：

- 正式桌面模式下，前端通过 `window.__TAURI__.core.invoke` 直连后端 command。
- 浏览器预览保留 dev bridge 兜底，主要用于纯前端页面调试，不作为正式验收路径。

## 目录

- `src/ui/shell/`：应用壳与导航
- `src/ui/pages/`：页面级模块（导入/工作区/装配/记录/设置）
- `src/services/`：后端调用适配层
- `src/styles/`：基础样式与布局样式
