import { createHash } from "node:crypto";
import { mkdir, readFile, rm } from "node:fs/promises";
import { isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const templatePath = fileURLToPath(new URL("./oslab-live-lab.html", import.meta.url));
const iconPath = fileURLToPath(new URL("../public/icon.svg", import.meta.url));
const sourceDirectory = fileURLToPath(new URL("../../../output/readme-media/live-capture/", import.meta.url));
const outputDirectory = fileURLToPath(new URL("../../../output/readme-media/", import.meta.url));
const repositoryDirectory = fileURLToPath(new URL("../../../", import.meta.url));
const rawVideoPath = join(outputDirectory, "oslab-live-lab.webm");
const approvalPath = join(sourceDirectory, "source-approval.json");

await mkdir(outputDirectory, { recursive: true });
await rm(rawVideoPath, { force: true });

const [template, icon, proxmoxTasks, proxmoxCpu, windowsVm, windowsPowershell, approvalRaw] = await Promise.all([
  readFile(templatePath, "utf8"),
  readFile(iconPath),
  readFile(join(sourceDirectory, "proxmox-task-crop.png")),
  readFile(join(sourceDirectory, "proxmox-cpu-crop.png")),
  readFile(join(sourceDirectory, "windows-vm-console-crop.png")),
  readFile(join(sourceDirectory, "windows-vm-powershell-crop.png")),
  readFile(approvalPath, "utf8"),
]);

const approval = JSON.parse(approvalRaw);
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const approvedInputs = {
  "proxmox-task-crop.png": proxmoxTasks,
  "proxmox-cpu-crop.png": proxmoxCpu,
  "windows-vm-console-crop.png": windowsVm,
  "windows-vm-powershell-crop.png": windowsPowershell,
};
for (const [name, value] of Object.entries(approvedInputs)) {
  const expected = approval?.files?.[name]?.sha256;
  if (!expected || sha256(value) !== expected) {
    throw new Error(`${name} does not match the manually reviewed source approval.`);
  }
}
for (const check of [
  "infrastructureSourcesReviewed",
  "guestPowerShellMatchesRun",
  "sensitiveRegionsReviewed",
  "cleanupVerified",
]) {
  if (approval?.checks?.[check] !== true) throw new Error(`Live capture approval check is missing: ${check}`);
}

const readApprovedEvidence = async (entry, label) => {
  const evidencePath = resolve(repositoryDirectory, String(entry?.path || ""));
  const repositoryRelativePath = relative(repositoryDirectory, evidencePath);
  if (repositoryRelativePath.startsWith("..") || isAbsolute(repositoryRelativePath)) {
    throw new Error(`${label} path must stay inside the repository.`);
  }
  const evidence = await readFile(evidencePath);
  if (sha256(evidence) !== entry?.sha256) throw new Error(`${label} does not match its approved hash.`);
  return evidence;
};

const infrastructureEvidence = await readApprovedEvidence(
  approval?.infrastructureRunEvidence,
  "Infrastructure run evidence",
);
const infrastructureRun = JSON.parse(infrastructureEvidence.toString("utf8"));
if (infrastructureRun?.status !== "passed") {
  throw new Error("Approved infrastructure capture must point to a passing demo run.");
}
const runEvidence = await readApprovedEvidence(approval?.runEvidence, "Guest PowerShell run evidence");
const run = JSON.parse(runEvidence.toString("utf8"));
if (run?.status !== "passed" || run?.details?.assertions?.total !== 2 || run?.details?.assertions?.failed !== 0) {
  throw new Error("Approved guest PowerShell capture must point to a passing two-assertion demo run.");
}

const resultEvidence = await readApprovedEvidence(approval?.guestResultEvidence, "Guest command result evidence");
const commandResult = JSON.parse(resultEvidence.toString("utf8"));
if (commandResult?.exitCode !== 0 || !String(commandResult?.metadata?.osCaption || "").includes("Windows 11")) {
  throw new Error("Approved guest command result must show exit code 0 on Windows 11.");
}
const visibleEvidence = approval?.files?.["windows-vm-powershell-crop.png"]?.visibleEvidence;
for (const marker of ["exitCode 0", "Windows 11 Pro", "OSLAB-DEMO-PASS"]) {
  if (!Array.isArray(visibleEvidence) || !visibleEvidence.includes(marker)) {
    throw new Error(`Guest PowerShell approval is missing visible evidence marker: ${marker}`);
  }
}
if (approval?.cleanup?.resourceAbsent !== true) throw new Error("Capture VM cleanup has not been verified.");

const dataUrl = (mime, value) => `data:${mime};base64,${value.toString("base64")}`;
const html = template
  .replaceAll("{{OSLAB_ICON_DATA_URL}}", dataUrl("image/svg+xml", icon))
  .replaceAll("{{PROXMOX_TASKS_DATA_URL}}", dataUrl("image/png", proxmoxTasks))
  .replaceAll("{{PROXMOX_CPU_DATA_URL}}", dataUrl("image/png", proxmoxCpu))
  .replaceAll("{{WINDOWS_VM_DATA_URL}}", dataUrl("image/png", windowsVm))
  .replaceAll("{{WINDOWS_POWERSHELL_DATA_URL}}", dataUrl("image/png", windowsPowershell));
if (html.includes("{{")) throw new Error("Live lab composition contains an unresolved template placeholder.");

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
  await page.waitForTimeout(24_500);

  const publicText = await page.locator("body").innerText();
  const approvalMarkers = approval?.privacy?.forbiddenPublicMarkers;
  if (!Array.isArray(approvalMarkers)) throw new Error("Live capture approval must list forbidden public markers.");
  const forbidden = ["192.168.", "C:\\Users\\", "/Users/", ...approvalMarkers];
  const found = forbidden.filter((value) => publicText.includes(value));
  if (found.length) throw new Error(`Live lab composition contains forbidden markers: ${found.join(", ")}`);
  if (browserErrors.length) throw new Error(`Live lab composition errors: ${browserErrors.join(" | ")}`);

  await context.close();
  if (!video) throw new Error("Playwright did not create the live lab video.");
  const temporaryVideoPath = await video.path();
  await video.saveAs(rawVideoPath);
  if (temporaryVideoPath !== rawVideoPath) await rm(temporaryVideoPath, { force: true });
} finally {
  await browser.close();
}

console.log(`Live lab recording: ${rawVideoPath}`);
