import { PDFDocument } from "pdf-lib";
import { previewRasterScale } from "./project-preview-image-export.js";

// A4 landscape; never split a chromosome card across pages. Rasterizing each
// bounded page keeps CJK/system fonts, rounded corners and colors identical to
// PNG without shipping fonts or allocating the full tall overview as a canvas.
export function paginateProjectPreview(snapshot) {
  const pageWidth = 841.89, pageHeight = 595.28, margin = 24;
  const availableWidth = pageWidth - margin * 2, availableHeight = pageHeight - margin * 2;
  const maxHeight = availableHeight * snapshot.width / availableWidth;
  const groups = [];
  let top = null, bottom = 0, cards = [];
  for (const card of snapshot.cardBounds) {
    if (top !== null && card.bottom + 8 - top > maxHeight) {
      groups.push({ top, bottom, cards }); top = null; cards = [];
    }
    if (top === null) top = Math.max(0, card.top - 8);
    bottom = Math.min(snapshot.height, card.bottom + 8);
    cards.push(card);
  }
  if (top !== null) groups.push({ top, bottom, cards });
  return groups.map(({ top, bottom, cards }) => {
    const height = Math.ceil(bottom - top), scale = Math.min(availableWidth / snapshot.width, availableHeight / height);
    const svgMarkup = `${snapshot.svgHeader}${cards.map(card => card.svgMarkup).join("")}</svg>`.replace(/^<svg\b[^>]*>/, root => root
      .replace(/height="[^"]*"/, `height="${height}"`)
      .replace(/viewBox="[^"]*"/, `viewBox="0 ${top} ${snapshot.width} ${height}"`));
    return { snapshot: { ...snapshot, height, svgMarkup, rasterScale: previewRasterScale(snapshot.width, height) },
      pageWidth, pageHeight, x: margin, y: pageHeight - margin - height * scale, width: snapshot.width * scale, height: height * scale };
  });
}

export async function renderProjectPreviewPdf(snapshot, renderPng) {
  const pdf = await PDFDocument.create();
  for (const page of paginateProjectPreview(snapshot)) {
    const image = await pdf.embedPng(await renderPng(page.snapshot));
    pdf.addPage([page.pageWidth, page.pageHeight]).drawImage(image, { x: page.x, y: page.y, width: page.width, height: page.height });
  }
  return pdf.saveAsBase64();
}
