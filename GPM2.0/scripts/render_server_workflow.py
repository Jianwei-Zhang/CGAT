#!/usr/bin/env python3
"""Render both README workflow diagrams with real, unstretched font glyphs.

Requires Pillow and the locally installed Microsoft YaHei, Segoe UI and
Consolas fonts; fonts are not distributed with this repository. Example:

    python3 GPM2.0/scripts/render_server_workflow.py --font-dir /mnt/c/Windows/Fonts

The default output is 3072 x 2048 (2x). All coordinates and font sizes use the
same scale, with no image/text resizing. Text overflow raises an error instead
of silently squeezing a line. Identical inputs produce identical PNG files.
Workflow order follows server/tools/run_orchestration.py::build_unit_plan.
"""

from __future__ import annotations

import argparse
import hashlib
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1536, 1024
BLUE, GREEN, PURPLE, ORANGE = "#1238e8", "#08792b", "#6213b8", "#f14b13"
INK = "#16202b"
ASSETS = Path(__file__).resolve().parents[1] / "app" / "readme-assets"
FONT_FILES = {
    "en": "segoeui.ttf",
    "en-bold": "segoeuib.ttf",
    "zh": "msyh.ttc",
    "zh-bold": "msyhbd.ttc",
    "mono": "consola.ttf",
}
INSTALL = ("bash server/install.sh", "micromamba activate cgat-server")
RUN = (
    "bash server/run.sh \\",
    "  --ref /path/to/ref.fa \\",
    "  --ds /path/to/hifi.fa \\",
    "  --ds /path/to/flye.fa \\",
    "  -t 32 -o ./gpm_server",
)
RESUME = "bash server/run.sh -o ./gpm_server"
LABELS = {
    "en": {
        "titles": ("Environment", "Input Data", "One Command",
                   "Automatic Workflow", "Delivery Packages"),
        "activate": "Activate using the command printed by install.sh.",
        "inputs": ("Reference FASTA", "One or more dataset FASTA",
                   "Optional reads FASTQ", "Optional --tel / --cen"),
        "optional": "Optional: --reads /path/to/reads.fastq.gz",
        "run_note": "Automatically prepares, computes, and packages.",
        "stages": ("Reference alignment + chromosome assignment",
                   "Freeze initial sequences and donors", "GRT Step1",
                   "GRT Step2/3 + telomere recovery / q4",
                   "Main-view alignments + evidence",
                   "Validation + report + parallel compression"),
        "donors": "q0 / D0 / Dtel; optional reads QC",
        "resume": "Resume: validate and reuse completed results",
        "outputs": ("Full: FASTA + report", "Light: no FASTA; report included",
                    "Server workspace"),
        "report": "Report: gpm_server/report/report.html",
    },
    "zh": {
        "titles": ("环境", "输入数据", "一条命令", "自动执行", "自动交付"),
        "activate": "按 install.sh 输出的命令激活环境",
        "inputs": ("参考序列 FASTA", "一个或多个组装数据集 FASTA",
                   "可选 reads FASTQ", "可选 --tel / --cen"),
        "optional": "可选：--reads /path/to/reads.fastq.gz",
        "run_note": "自动准备、计算并打包",
        "stages": ("参考比对与染色体分配", "固定初始序列与供体", "GRT Step1",
                   "GRT Step2/3 + 端粒恢复 / q4", "主视图比对与证据整理",
                   "校验、报告与多线程压缩"),
        "donors": "q0 / D0 / Dtel；按需 reads 质控",
        "resume": "断点继续：校验并复用已完成结果",
        "outputs": ("完整包：FASTA + 报告", "轻量包：不含 FASTA，保留报告",
                    "Server 工作目录"),
        "report": "报告：gpm_server/report/report.html",
    },
}


class Diagram:
    def __init__(self, language: str, font_dir: Path, scale: int):
        self.language, self.font_dir, self.scale = language, font_dir, scale
        self.image = Image.new("RGB", (WIDTH * scale, HEIGHT * scale), "white")
        self.draw = ImageDraw.Draw(self.image)

    def points(self, values):
        return tuple(round(value * self.scale) for value in values)

    @lru_cache(maxsize=None)
    def font(self, size: int, face: str = ""):
        return ImageFont.truetype(
            str(self.font_dir / FONT_FILES[face or self.language]), size * self.scale
        )

    def text(self, x, y, value, size=24, color=INK, face="", max_width=None):
        font = self.font(size, face)
        width = self.draw.textlength(value, font=font) / self.scale
        if max_width is not None and width > max_width:
            raise ValueError(f"{self.language}: text too wide ({width:.1f} > {max_width}): {value}")
        bounds = self.draw.textbbox(self.points((x, y)), value, font=font, anchor="lt")
        if bounds[0] < 0 or bounds[1] < 0 or bounds[2] > WIDTH * self.scale or bounds[3] > HEIGHT * self.scale:
            raise ValueError(f"{self.language}: text outside canvas: {value}")
        self.draw.text(self.points((x, y)), value, font=font, fill=color, anchor="lt")
        return width

    def box(self, box, color, fill="white", radius=14, width=1.5):
        self.draw.rounded_rectangle(self.points(box), radius=radius * self.scale,
                                    fill=fill, outline=color, width=round(width * self.scale))

    def line(self, points, color, width=2):
        self.draw.line([self.points(point) for point in points], fill=color,
                       width=round(width * self.scale), joint="curve")

    def badge(self, x, y, radius, value, color, size):
        self.draw.ellipse(self.points((x-radius, y-radius, x+radius, y+radius)), fill=color)
        # A fine upper highlight retains the original numbered-circle style.
        self.draw.arc(self.points((x-radius+2, y-radius+2, x+radius-2, y+radius-2)),
                      205, 300, fill="#ffffff", width=self.scale)
        self.draw.text(self.points((x, y-1)), str(value), font=self.font(size, "en-bold"),
                       anchor="mm", fill="white")

    def panel(self, box, number, title, color):
        self.box(box, color)
        x, y = box[:2]
        self.badge(x+42, y+42, 25, number, color, 37)
        self.text(x+84, y+22, title, 38, color, self.language+"-bold", box[2]-x-106)

    def terminal(self, x, y, size=72):
        self.box((x, y, x+size, y+size), "#111b24", "#080d12", 10)
        self.line([(x+size*.24, y+size*.30), (x+size*.43, y+size*.49),
                   (x+size*.24, y+size*.68)], "white", 5)
        self.line([(x+size*.50, y+size*.70), (x+size*.77, y+size*.70)], "white", 5)

    def info(self, x, y, color, check=False):
        self.draw.ellipse(self.points((x-18, y-18, x+18, y+18)),
                          outline=color, width=3*self.scale)
        if check:
            self.line([(x-9, y), (x-2, y+7), (x+10, y-9)], color, 3)
        else:
            self.draw.text(self.points((x, y-1)), "i", font=self.font(29, "en-bold"),
                           fill=color, anchor="mm")

    def document(self, x, y):
        self.box((x, y, x+25, y+31), GREEN, GREEN, 5)
        for offset in (8, 15, 22):
            self.line([(x+6, y+offset), (x+19, y+offset)], "white", 2)

    def archive(self, x, y):
        vertices = [(x, y), (x+30, y), (x+49, y+20), (x+49, y+62), (x, y+62)]
        self.draw.polygon([self.points(point) for point in vertices], fill=BLUE)
        self.draw.polygon([self.points(point) for point in
                           [(x+29, y+5), (x+29, y+21), (x+44, y+21)]], fill="white")
        self.text(x+6, y+31, "GZ", 25, "white", "en-bold", 39)

    def folder(self, x, y):
        self.box((x, y, x+26, y+21), BLUE, BLUE, 5)
        self.box((x, y+10, x+50, y+51), BLUE, BLUE, 5)

    def arrow(self, points, color):
        self.line(points, color, 3)
        x, y = points[-1]
        px, py = points[-2]
        if x > px:
            head = [(x-8, y-7), (x, y), (x-8, y+7)]
        else:
            head = [(x-8, y-8), (x, y), (x+8, y-8)]
        self.line(head, color, 3)

    def dashed_rule(self, y):
        for x in range(802, 1500, 13):
            self.line([(x, y), (min(x+7, 1500), y)], BLUE, 1)

    def render(self):
        words = LABELS[self.language]
        panels = [((16, 16, 752, 276), BLUE), ((16, 320, 752, 572), GREEN),
                  ((16, 616, 752, 1008), PURPLE), ((784, 16, 1520, 552), ORANGE),
                  ((784, 596, 1520, 1008), BLUE)]
        for number, ((box, color), title) in enumerate(zip(panels, words["titles"]), 1):
            self.panel(box, number, title, color)
        self.arrow([(384, 276), (384, 311)], BLUE)
        self.arrow([(384, 572), (384, 607)], GREEN)
        self.arrow([(752, 811), (768, 811), (768, 125), (784, 125)], PURPLE)
        self.arrow([(1152, 552), (1152, 587)], ORANGE)

        self.terminal(40, 100)
        self.box((136, 96, 728, 194), "#34435e", "#fafbfc", 10)
        for line, y in zip(INSTALL, (115, 154)):
            self.text(158, y, line, 25, face="mono", max_width=550)
        self.info(58, 236, BLUE, check=True)
        self.text(98, 224, words["activate"], 23, BLUE, max_width=630)

        for line, y in zip(words["inputs"], (403, 445, 487, 529)):
            self.document(66, y-3)
            self.text(120, y, line, 26, max_width=606)

        self.terminal(40, 698)
        self.box((136, 696, 728, 890), "#34435e", "#fafbfc", 10)
        for line, y in zip(RUN, (714, 748, 782, 816, 850)):
            if "/path/to/" in line:
                prefix, path = line.split("/path/to/", 1)
                offset = self.text(156, y, prefix, 25, face="mono")
                self.text(156+offset, y, "/path/to/"+path, 25, BLUE, "mono", 550-offset)
            else:
                self.text(156, y, line, 25, face="mono", max_width=550)
        self.text(136, 910, words["optional"], 23, max_width=592)
        self.info(58, 974, PURPLE)
        self.text(98, 962, words["run_note"], 24, PURPLE, max_width=630)

        for number, (line, y) in enumerate(zip(words["stages"], (111, 158, 222, 269, 316, 363)), 1):
            self.badge(826, y+14, 18, number, ORANGE, 27)
            self.text(862, y, line, 24, max_width=632)
        self.text(862, 190, words["donors"], 20, "#586574", max_width=632)
        self.box((806, 417, 1498, 530), ORANGE, "#fffaf7", 10)
        self.text(828, 434, words["resume"], 24, face=self.language+"-bold", max_width=646)
        self.terminal(828, 473, 42)
        self.box((890, 471, 1480, 517), "#34435e", "white", 7)
        self.text(908, 482, RESUME, 25, face="mono", max_width=554)

        for index, (filename, y) in enumerate((("gpm_server.tar.gz", 676),
                                              ("gpm_server.light.tar.gz", 773),
                                              ("gpm_server/", 870))):
            (self.archive if index < 2 else self.folder)(816, y-2)
            self.text(890, y, filename, 26, face="mono", max_width=606)
            self.text(890, y+35, words["outputs"][index], 23, BLUE, max_width=606)
            if index < 2:
                self.dashed_rule(y+76)
        self.dashed_rule(946)
        self.info(828, 978, BLUE)
        self.text(862, 966, words["report"], 23, BLUE, max_width=634)
        return self.image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path,
                        default=Path("C:/Windows/Fonts") if Path("C:/Windows/Fonts").is_dir()
                        else Path("/mnt/c/Windows/Fonts"))
    parser.add_argument("--output-dir", type=Path, default=ASSETS)
    parser.add_argument("--scale", type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    missing = [name for name in FONT_FILES.values() if not (args.font_dir / name).is_file()]
    if missing:
        parser.error(f"Missing fonts in {args.font_dir}: {', '.join(missing)}; use --font-dir.")
    # Render both first so a layout failure cannot leave only one language updated.
    images = {lang: Diagram(lang, args.font_dir, args.scale).render() for lang in LABELS}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for lang, image in images.items():
        path = args.output_dir / f"serve_pipeline_{lang}.png"
        image.save(path, format="PNG", optimize=True)
        print(f"{path}: {image.width}x{image.height}, SHA-256 {hashlib.sha256(path.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
