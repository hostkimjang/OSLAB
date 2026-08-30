import { mkdir, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const templatePath = fileURLToPath(new URL("./oslab-marketing.html", import.meta.url));
const iconPath = fileURLToPath(new URL("../public/icon.svg", import.meta.url));
const outputDirectory = fileURLToPath(new URL("../../../output/readme-media/", import.meta.url));
const rawVideoPath = join(outputDirectory, "oslab-overview.webm");

await mkdir(outputDirectory, { recursive: true });
await rm(rawVideoPath, { force: true });

const [template, icon] = await Promise.all([
  readFile(templatePath, "utf8"),
  readFile(iconPath),
]);
const iconDataUrl = `data:image/svg+xml;base64,${icon.toString("base64")}`;
const html = template.replaceAll("{{OSLAB_ICON_DATA_URL}}", iconDataUrl);

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({
    locale: "en-US",
    timezoneId: "UTC",
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: outputDirectory, size: { width: 1280, height: 720 } },
    reducedMotion: "no-preference",
  });
  const browserErrors = [];
  context.on("page", (page) => {
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(message.text());
    });
    page.on("pageerror", (error) => browserErrors.push(error.message));
  });

  const page = await context.newPage();
  const video = page.video();
  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(16_700);

  if (browserErrors.length) {
    throw new Error(`Overview animation errors: ${browserErrors.join(" | ")}`);
  }

  await context.close();
  if (!video) throw new Error("Playwright did not create the overview video.");
  const temporaryVideoPath = await video.path();
  await video.saveAs(rawVideoPath);
  if (temporaryVideoPath !== rawVideoPath) await rm(temporaryVideoPath, { force: true });
} finally {
  await browser.close();
}

console.log(`Overview recording: ${rawVideoPath}`);
