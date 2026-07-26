import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { basename, join, resolve } from "node:path";

const projectRoot = process.cwd();
const docsRoot = resolve(projectRoot, "docs");
const catalogPath = resolve(docsRoot, ".vitepress/data/videos.ts");
const catalogSource = readFileSync(catalogPath, "utf8");
const recordPattern = /\{ id: "([^"]+)", number: "([^"]+)", title: "([^"]+)", section: "([^"]+)",(?: src: "([^"]+)",)? page: "([^"]+)", status: "(published|planned)" \}/g;
const records = [...catalogSource.matchAll(recordPattern)].map((match) => ({
  id: match[1],
  number: match[2],
  title: match[3],
  section: match[4],
  src: match[5],
  page: match[6],
  status: match[7]
}));

const errors = [];
const seenIds = new Set();
const seenSources = new Set();

if (records.length === 0) {
  errors.push("Video catalog contains no records.");
}

for (const record of records) {
  if (seenIds.has(record.id)) errors.push(`Duplicate video id: ${record.id}`);
  seenIds.add(record.id);

  const pageRoute = record.page.split("#", 1)[0].replace(/^\/+|\/+$/g, "");
  const directPage = join(docsRoot, `${pageRoute}.md`);
  const indexPage = join(docsRoot, pageRoute, "index.md");
  if (!existsSync(directPage) && !existsSync(indexPage)) {
    errors.push(`Missing documentation page for ${record.id}: ${record.page}`);
  }

  if (record.status === "planned") {
    if (record.src) errors.push(`Planned video must not have a source: ${record.id}`);
    continue;
  }

  if (!record.src) {
    errors.push(`Published video has no source: ${record.id}`);
    continue;
  }

  if (seenSources.has(record.src)) errors.push(`Duplicate video source: ${record.src}`);
  seenSources.add(record.src);

  const sourcePath = join(docsRoot, "public", record.src.replace(/^\//, ""));
  if (!existsSync(sourcePath)) {
    errors.push(`Missing published video: ${record.src}`);
    continue;
  }

  const filename = basename(sourcePath);
  if (!/^[a-z0-9][a-z0-9.-]*\.mp4$/.test(filename)) {
    errors.push(`Video filename is not URL-safe: ${filename}`);
  }
  if (statSync(sourcePath).size >= 100 * 1024 * 1024) {
    errors.push(`Video exceeds the 100 MiB Git limit: ${filename}`);
  }
}

const videoDirectory = join(docsRoot, "public", "zh", "video");
const mediaFiles = readdirSync(videoDirectory)
  .filter((filename) => filename.endsWith(".mp4"))
  .map((filename) => `/zh/video/${filename}`);

for (const mediaFile of mediaFiles) {
  if (!seenSources.has(mediaFile)) errors.push(`Uncatalogued video file: ${mediaFile}`);
}

if (errors.length > 0) {
  for (const error of errors) console.error(`ERROR: ${error}`);
  process.exit(1);
}

const publishedCount = records.filter((record) => record.status === "published").length;
const plannedCount = records.filter((record) => record.status === "planned").length;
console.log(`Validated ${publishedCount} published videos and ${plannedCount} planned tutorials.`);
