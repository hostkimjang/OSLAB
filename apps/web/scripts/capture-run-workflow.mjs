import { mkdir, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const templatePath = fileURLToPath(new URL("./oslab-run-workflow.html", import.meta.url));
const iconPath = fileURLToPath(new URL("../public/icon.svg", import.meta.url));
const outputDirectory = fileURLToPath(new URL("../../../output/readme-media/", import.meta.url));
const rawVideoPath = join(outputDirectory, "oslab-run-workflow.webm");

await mkdir(outputDirectory, { recursive: true });
await rm(rawVideoPath, { force: true });

const [template, icon] = await Promise.all([readFile(templatePath, "utf8"), readFile(iconPath)]);
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
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  const video = page.video();
  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(22_600);

  const publicText = await page.locator("body").innerText();
  const forbidden = ["C:\\Users\\", "/Users/", "192.168."];
  const found = forbidden.filter((value) => publicText.includes(value));
  if (found.length) throw new Error(`Workflow animation contains forbidden markers: ${found.join(", ")}`);
  if (browserErrors.length) throw new Error(`Workflow animation errors: ${browserErrors.join(" | ")}`);

  await context.close();
  if (!video) throw new Error("Playwright did not create the workflow video.");
  const temporaryVideoPath = await video.path();
  await video.saveAs(rawVideoPath);
  if (temporaryVideoPath !== rawVideoPath) await rm(temporaryVideoPath, { force: true });
} finally {
  await browser.close();
}

console.log(`Run workflow recording: ${rawVideoPath}`);
