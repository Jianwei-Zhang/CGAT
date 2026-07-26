export type TutorialStatus = "published" | "planned";

export interface TutorialVideoRecord {
  id: string;
  number: string;
  title: string;
  section: string;
  src?: string;
  page: string;
  status: TutorialStatus;
}

export const tutorialVideos: TutorialVideoRecord[] = [
  { id: "01-import", number: "1", title: "导入交付包", section: "快速开始", src: "/zh/video/01-import.mp4", page: "/zh/guide/getting-started#import-package", status: "published" },
  { id: "02-create-project", number: "2", title: "创建项目", section: "快速开始", src: "/zh/video/02-create-project.mp4", page: "/zh/guide/getting-started#create-project", status: "published" },
  { id: "03-minimal-path", number: "3", title: "完成最简操作路径", section: "快速开始", src: "/zh/video/03-minimal-path.mp4", page: "/zh/guide/getting-started#minimal-path", status: "published" },
  { id: "04-01-drag-contig", number: "4.1", title: "任意拖动 contig", section: "GPM Next 主视图", src: "/zh/video/04-01-drag-contig.mp4", page: "/zh/guide/main-view#drag-contig", status: "published" },
  { id: "04-02-flip-contig", number: "4.2", title: "翻转 contig", section: "GPM Next 主视图", src: "/zh/video/04-02-flip-contig.mp4", page: "/zh/guide/main-view#flip-contig", status: "published" },
  { id: "04-03-01-delete-contig-method-1", number: "4.3.1", title: "删除 contig：方法一", section: "GPM Next 主视图", src: "/zh/video/04-03-01-delete-contig-method-1.mp4", page: "/zh/guide/main-view#delete-contig", status: "published" },
  { id: "04-03-02-delete-contig-method-2", number: "4.3.2", title: "删除 contig：方法二", section: "GPM Next 主视图", src: "/zh/video/04-03-02-delete-contig-method-2.mp4", page: "/zh/guide/main-view#delete-contig", status: "published" },
  { id: "04-03-03-undo-delete-contig", number: "4.3.3", title: "撤销删除 contig", section: "GPM Next 主视图", src: "/zh/video/04-03-03-undo-delete-contig.mp4", page: "/zh/guide/main-view#undo-delete", status: "published" },
  { id: "04-04-hide-primary-dataset-contig", number: "4.4", title: "隐藏主 ds contig", section: "GPM Next 主视图", src: "/zh/video/04-04-hide-primary-dataset-contig.mp4", page: "/zh/guide/main-view#hide-primary-contig", status: "published" },
  { id: "04-05-mirror-support-dataset-contig", number: "4.5", title: "镜像辅 ds contig", section: "GPM Next 主视图", src: "/zh/video/04-05-mirror-support-dataset-contig.mp4", page: "/zh/guide/main-view#mirror-support-contig", status: "published" },
  { id: "04-06-01-switch-chromosome", number: "4.6.1", title: "切换 chromosome", section: "GPM Next 主视图", src: "/zh/video/04-06-01-switch-chromosome.mp4", page: "/zh/guide/main-view#view-controls", status: "published" },
  { id: "04-06-02-switch-support-dataset-track", number: "4.6.2", title: "切换辅 ds 轨道", section: "GPM Next 主视图", src: "/zh/video/04-06-02-switch-support-dataset-track.mp4", page: "/zh/guide/main-view#view-controls", status: "published" },
  { id: "04-06-03-filter-support-dataset-contigs", number: "4.6.3", title: "过滤辅 ds contig", section: "GPM Next 主视图", src: "/zh/video/04-06-03-filter-support-dataset-contigs.mp4", page: "/zh/guide/main-view#view-controls", status: "published" },
  { id: "04-06-04-adjust-main-view-scale", number: "4.6.4", title: "控制主视图比例", section: "GPM Next 主视图", src: "/zh/video/04-06-04-adjust-main-view-scale.mp4", page: "/zh/guide/main-view#view-controls", status: "published" },
  { id: "04-06-05-filter-alignment-length", number: "4.6.5", title: "按比对长度过滤", section: "GPM Next 主视图", src: "/zh/video/04-06-05-filter-alignment-length.mp4", page: "/zh/guide/main-view#view-controls", status: "published" },
  { id: "04-06-06-filter-alignment-mapq", number: "4.6.6", title: "按 MAPQ 过滤", section: "GPM Next 主视图", src: "/zh/video/04-06-06-filter-alignment-mapq.mp4", page: "/zh/guide/main-view#view-controls", status: "published" },
  { id: "05-01-enter-subview-from-track", number: "5.1", title: "从 track 进入 Subview", section: "Subview", src: "/zh/video/05-01-enter-subview-from-track.mp4", page: "/zh/guide/subview#enter-from-track", status: "published" },
  { id: "05-02-enter-subview-from-contig", number: "5.2", title: "从 contig 进入 Subview", section: "Subview", src: "/zh/video/05-02-enter-subview-from-contig.mp4", page: "/zh/guide/subview#enter-from-contig", status: "published" },
  { id: "05-03-swap-subview-track-order", number: "5.3", title: "切换 Subview 上下轨道次序", section: "Subview", src: "/zh/video/05-03-swap-subview-track-order.mp4", page: "/zh/guide/subview#swap-track-order", status: "published" },
  { id: "05-04-anchor", number: "5.4", title: "使用锚点", section: "Subview", src: "/zh/video/05-04-anchor.mp4", page: "/zh/guide/subview#anchor", status: "published" },
  { id: "05-05-offset-anchor", number: "5.5", title: "创建偏移锚点", section: "Subview", src: "/zh/video/05-05-offset-anchor.mp4", page: "/zh/guide/subview#offset-anchor", status: "published" },
  { id: "06-export", number: "6", title: "导出 final path", section: "结果导出", src: "/zh/video/06-export.mp4", page: "/zh/guide/export#export-video", status: "published" },
  { id: "07-01-degap-gapfiller", number: "7.1", title: "DEGAP GapFiller", section: "DEGAP", src: "/zh/video/07-01-degap-gapfiller.mp4", page: "/zh/guide/degap#gapfiller", status: "published" },
  { id: "07-02-degap-telseeker", number: "7.2", title: "DEGAP TelSeeker", section: "DEGAP", src: "/zh/video/07-02-degap-telseeker.mp4", page: "/zh/guide/degap#telseeker", status: "published" },
  { id: "07-03-add-contig-to-track", number: "7.3", title: "将新 contig 加入轨道", section: "DEGAP", page: "/zh/guide/workflows#planned-tutorials", status: "planned" },
  { id: "08-polyploid-assembly", number: "8", title: "多倍体组装", section: "专题工作流", page: "/zh/guide/workflows#planned-tutorials", status: "planned" },
  { id: "09-reference-guided-gap-filling", number: "9", title: "参考序列辅助填补", section: "专题工作流", page: "/zh/guide/workflows#planned-tutorials", status: "planned" }
];

export function findTutorialVideo(id: string): TutorialVideoRecord | undefined {
  return tutorialVideos.find((video) => video.id === id);
}
