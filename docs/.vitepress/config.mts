import { defineConfig } from "vitepress";

const repositoryUrl = "https://github.com/Jianwei-Zhang/CGAT";
const releaseUrl = `${repositoryUrl}/releases/latest`;

const sharedTheme = {
  logo: "/logo.svg",
  socialLinks: [{ icon: "github", link: repositoryUrl }],
  search: {
    provider: "local" as const,
    options: {
      locales: {
        zh: {
          translations: {
            button: {
              buttonText: "搜索文档",
              buttonAriaLabel: "搜索文档"
            },
            modal: {
              noResultsText: "未找到相关结果",
              resetButtonTitle: "清除搜索",
              footer: {
                selectText: "选择",
                navigateText: "切换",
                closeText: "关闭"
              }
            }
          }
        }
      }
    }
  },
  footer: {
    message: "CGAT official documentation",
    copyright: "Copyright © CGAT contributors"
  }
};

export default defineConfig({
  title: "CGAT Docs",
  description: "Official documentation for the Complete Genome Assembly Toolkit",
  lang: "en-US",
  base: "/CGAT/",
  cleanUrls: true,
  outDir: process.env.CGAT_DOCS_OUT_DIR || ".vitepress/dist",
  lastUpdated: true,
  sitemap: {
    hostname: "https://jianwei-zhang.github.io/CGAT/"
  },
  vite: {
    build: {
      copyPublicDir: false
    }
  },
  head: [
    ["link", { rel: "icon", type: "image/svg+xml", href: "/CGAT/logo.svg" }],
    ["meta", { name: "theme-color", content: "#0f766e" }]
  ],
  locales: {
    root: {
      label: "Language",
      lang: "en-US",
      title: "CGAT Docs",
      description: "Official documentation for the Complete Genome Assembly Toolkit",
      themeConfig: {
        ...sharedTheme,
        nav: [
          { text: "简体中文", link: "/zh/" },
          { text: "English", link: "/en/" },
          { text: "GitHub", link: repositoryUrl }
        ]
      }
    },
    zh: {
      label: "简体中文",
      lang: "zh-CN",
      link: "/zh/",
      title: "CGAT 文档",
      description: "完整基因组组装工具集官方文档",
      themeConfig: {
        ...sharedTheme,
        nav: [
          { text: "指南", link: "/zh/guide/overview" },
          { text: "视频教程", link: "/zh/tutorials/" },
          { text: "参考", link: "/zh/reference/glossary" },
          { text: "下载", link: releaseUrl }
        ],
        sidebar: {
          "/zh/": [
            {
              text: "开始使用",
              items: [
                { text: "CGAT 概览", link: "/zh/guide/overview" },
                { text: "安装 GPM Next", link: "/zh/guide/installation" },
                { text: "服务端数据准备", link: "/zh/guide/server-workflow" },
                { text: "创建并导入项目", link: "/zh/guide/getting-started" }
              ]
            },
            {
              text: "GPM Next",
              items: [
                { text: "主视图编辑", link: "/zh/guide/main-view" },
                { text: "Subview 精细检查", link: "/zh/guide/subview" },
                { text: "导出组装结果", link: "/zh/guide/export" }
              ]
            },
            {
              text: "DEGAP 与工作流",
              items: [
                { text: "DEGAP 工具", link: "/zh/guide/degap" },
                { text: "完整工作流", link: "/zh/guide/workflows" }
              ]
            },
            {
              text: "教程与参考",
              items: [
                { text: "视频教程目录", link: "/zh/tutorials/" },
                { text: "术语表", link: "/zh/reference/glossary" },
                { text: "常见问题", link: "/zh/reference/troubleshooting" },
                { text: "引用与反馈", link: "/zh/about/citation" }
              ]
            }
          ]
        },
        outline: { label: "本页目录", level: [2, 3] },
        docFooter: { prev: "上一页", next: "下一页" },
        lastUpdated: { text: "最后更新于" },
        returnToTopLabel: "返回顶部",
        sidebarMenuLabel: "菜单",
        darkModeSwitchLabel: "主题",
        langMenuLabel: "切换语言",
        externalLinkIcon: true
      }
    },
    en: {
      label: "English",
      lang: "en-US",
      link: "/en/",
      title: "CGAT Docs",
      description: "Official documentation for the Complete Genome Assembly Toolkit",
      themeConfig: {
        ...sharedTheme,
        nav: [
          { text: "Documentation status", link: "/en/" },
          { text: "中文文档", link: "/zh/" },
          { text: "Download", link: releaseUrl }
        ],
        sidebar: false
      }
    }
  },
  themeConfig: sharedTheme
});
