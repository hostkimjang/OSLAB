import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const root = process.cwd();
const outDir = path.join(root, "output", "web-dashboard");
const baseUrl = process.env.OSLAB_WEB_BASE_URL ?? "http://127.0.0.1:3000";

async function login(page) {
  const response = await page.request.post(`${baseUrl}/api/auth/login`, {
    data: { username: "admin", password: "oslab-admin" },
  });
  if (!response.ok()) throw new Error(`API login failed: ${response.status()}`);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.locator(".shell").waitFor({ timeout: 15000 });
}

async function selectDemoSkeletonRun(page) {
  await page.locator(".nav button").nth(4).click();
  await page.locator(".runGrid").waitFor({ timeout: 15000 });
  await page.evaluate(() => {
    for (const select of Array.from(document.querySelectorAll("select"))) {
      const demo = Array.from(select.options).find((option) => option.value.includes("demo-powershell-system"));
      if (demo) {
        select.value = demo.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      const artifactNone = Array.from(select.options).find((option) => option.value === "" && (option.textContent || "").includes("없음"));
      if (artifactNone && Array.from(select.options).some((option) => option.value.includes("validation/artifacts"))) {
        select.value = "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  });
}

const activeRunWithIncompleteEvidence = {
  id: "20260429-999999-ui-running-contract-gaps",
  kind: "run",
  status: "running",
  scenarioId: "demo.powershell.system.windows",
  scenarioPath: "scenarios/windows/demo-powershell-system.example.yaml",
  evidenceSummary: { total: 14, present: 3, missingRequired: 5, contractGaps: 5 },
  path: "runs/20260429-999999-ui-running-contract-gaps",
  updatedAt: new Date().toISOString(),
};

const activeRunDetailWithIncompleteEvidence = {
  id: activeRunWithIncompleteEvidence.id,
  status: "running",
  scenarioId: activeRunWithIncompleteEvidence.scenarioId,
  scenarioPath: activeRunWithIncompleteEvidence.scenarioPath,
  startedAt: new Date().toISOString(),
  details: {
    mode: "artifact",
    reportFormats: ["json", "html", "junit"],
    outputs: { raw: "raw/actual-output.json", normalized: "normalized/command-result.json" },
  },
  evidence: {
    total: 6,
    present: 2,
    missingRequired: 4,
    contractGaps: 4,
    items: [
      { key: "run-json", label: "run.json", group: "core", relativePath: "run.json", required: true, status: "present", size: 512, description: "Run summary", previewable: true },
      { key: "progress-jsonl", label: "progress.jsonl", group: "timeline", relativePath: "logs/progress.jsonl", required: true, status: "present", size: 128, description: "Timeline", previewable: true },
      { key: "actual-output", label: "actual-output.json", group: "outputs", relativePath: "raw/actual-output.json", required: true, status: "contractGap", description: "Raw output", previewable: false },
      { key: "command-result", label: "command-result.json", group: "outputs", relativePath: "normalized/command-result.json", required: true, status: "contractGap", description: "Command result", previewable: false },
      { key: "result-json", label: "result.json", group: "reports", relativePath: "reports/result.json", required: true, status: "contractGap", description: "Result report", previewable: false },
      { key: "cleanup-state", label: "Cleanup state", group: "cleanup", required: true, status: "contractGap", reason: "No cleanup state has been recorded yet.", description: "Cleanup", previewable: false },
    ],
  },
  files: [
    { label: "run.json", group: "core", relativePath: "run.json", status: "present", required: true, size: 512, previewable: true, discovered: false },
    { label: "actual-output.json", group: "outputs", relativePath: "raw/actual-output.json", status: "contractGap", required: true, previewable: false, discovered: false },
  ],
};

test("running result shows incomplete evidence as checking instead of finalized contract gaps", async ({ page }) => {
  fs.mkdirSync(outDir, { recursive: true });

  await page.route(`${baseUrl}/api/runs`, async (route) => {
    await route.fulfill({ json: [activeRunWithIncompleteEvidence] });
  });
  await page.route(`${baseUrl}/api/runs/${activeRunWithIncompleteEvidence.id}`, async (route) => {
    await route.fulfill({ json: activeRunDetailWithIncompleteEvidence });
  });

  await login(page);
  await page.locator(".nav button").nth(5).click();
  await page.locator(".resultsGrid").waitFor({ timeout: 15000 });
  await expect(page.locator(".resultRow.selected")).toContainText(activeRunWithIncompleteEvidence.id);
  await expect(page.locator(".resultRow.selected")).toContainText("확인 중");
  await expect(page.locator(".resultRow.selected")).not.toContainText("계약 누락");
  await expect(page.locator(".evidencePanel")).toContainText("확인 중");
  await expect(page.locator(".evidencePanel .statusBadge")).not.toContainText("계약 누락");
  await page.screenshot({ path: path.join(outDir, "running-evidence-checking.png"), fullPage: false });
});

test("running result transitions to terminal status without manual refresh", async ({ page }) => {
  test.setTimeout(120000);
  fs.mkdirSync(outDir, { recursive: true });

  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await login(page);
  await selectDemoSkeletonRun(page);

  const beforeJobs = await page.request.get(`${baseUrl}/api/jobs`).then((response) => response.json());
  const beforeLatestJobId = beforeJobs[0]?.id;
  const buttons = await page.locator("button").allTextContents();
  const runButtonIndex = buttons.findIndex((text) => text.includes("선택한 시나리오 실행") || text.includes("Run selected scenario"));
  if (runButtonIndex < 0) throw new Error(`Run scenario button not found: ${buttons.join(" | ")}`);
  await page.locator("button").nth(runButtonIndex).click();

  await expect
    .poll(async () => {
      const jobs = await page.request.get(`${baseUrl}/api/jobs`).then((response) => response.json());
      return jobs[0]?.id && jobs[0]?.id !== beforeLatestJobId ? jobs[0] : null;
    }, { timeout: 20000 })
    .not.toBeNull();
  const jobsAfterStart = await page.request.get(`${baseUrl}/api/jobs`).then((response) => response.json());
  const jobId = jobsAfterStart[0].id;

  await page.screenshot({ path: path.join(outDir, "running-status-sync-started.png"), fullPage: false });
  await page.locator(".nav button").nth(5).click();
  await page.locator(".resultsGrid").waitFor({ timeout: 15000 });
  await page.screenshot({ path: path.join(outDir, "running-status-sync-results-open.png"), fullPage: false });

  await expect
    .poll(async () => {
      const jobs = await page.request.get(`${baseUrl}/api/jobs`).then((response) => response.json());
      const job = jobs.find((item) => item.id === jobId);
      const selectedBadge = await page.locator(".resultRow.selected .rowBadge").textContent().catch(() => "");
      const bannerVisible = await page.locator(".globalRunBanner").isVisible().catch(() => false);
      return {
        jobStatus: job?.status || "",
        runId: job?.runId || "",
        selectedBadge: selectedBadge?.trim() || "",
        bannerVisible,
      };
    }, { timeout: 45000 })
    .toEqual(expect.objectContaining({
      jobStatus: "passed",
      selectedBadge: "passed",
      bannerVisible: false,
    }));

  await page.screenshot({ path: path.join(outDir, "running-status-sync-results-terminal.png"), fullPage: false });
  const finalJobs = await page.request.get(`${baseUrl}/api/jobs`).then((response) => response.json());
  const finalJob = finalJobs.find((item) => item.id === jobId);
  const finalSelectedBadge = await page.locator(".resultRow.selected .rowBadge").textContent().catch(() => "");
  const report = {
    ok: consoleErrors.length === 0,
    checkedAt: new Date().toISOString(),
    jobId,
    terminal: {
      jobStatus: finalJob?.status || "",
      runId: finalJob?.runId || "",
      selectedBadge: finalSelectedBadge?.trim() || "",
    },
    consoleErrors,
  };
  fs.writeFileSync(path.join(outDir, "running-status-sync-smoke.json"), JSON.stringify(report, null, 2));
  expect(consoleErrors).toEqual([]);
});
