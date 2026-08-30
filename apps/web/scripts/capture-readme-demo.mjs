import { spawn } from "node:child_process";
import { copyFile, cp, mkdir, mkdtemp, readFile, rm, symlink } from "node:fs/promises";
import { createServer } from "node:net";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const webDirectory = fileURLToPath(new URL("../", import.meta.url));
const repositoryDirectory = fileURLToPath(new URL("../../../", import.meta.url));
const nextBin = join(webDirectory, "node_modules", "next", "dist", "bin", "next");
const monacoDirectory = join(webDirectory, "node_modules", "monaco-editor", "min", "vs");
const outputDirectory = fileURLToPath(new URL("../../../output/readme-media/", import.meta.url));
const rawVideoPath = join(outputDirectory, "oslab-dashboard-demo.webm");
const posterPath = join(outputDirectory, "oslab-dashboard-demo-poster.png");
const fixedNow = "2026-08-30T09:00:00.000Z";

const scenarioPath = "scenarios/windows/demo-powershell-system.example.yaml";
const fixturePath = "validation/fixtures/windows/demo-powershell-system.ps1";
const artifactPath = "validation/artifacts/powershell-system";
const jobId = "demo-job-001";
const runId = "demo-run-001";

const scenarioYaml = await readFile(join(repositoryDirectory, ...scenarioPath.split("/")), "utf8");

const scenarioModel = {
  schemaVersion: 1,
  id: "demo.powershell.system.windows",
  name: "Generic PowerShell system information Windows demo",
  osFamily: "windows",
  osVersion: "11",
  template: "windows11-template-qga-9200",
  templateVmId: 9200,
  vmIdStart: 9102,
  vmIdEnd: 9199,
  guestMode: "auto",
  windowsOrder: ["qemuAgent", "winrm"],
  linuxOrder: [],
  artifactType: "folder",
  artifactPathParam: "artifactPath",
  artifactDestination: "C:\\Oslab\\artifact",
  artifactTransfer: "archive",
  artifactCommand: {
    shell: "powershell",
    template: '& "{ArtifactDir}\\run-system-demo.ps1" -OutputPath "{OutputPath}"',
  },
  outputActualPath: "C:\\Oslab\\command-result.json",
  outputActualAdapter: "canonical.command",
  reportFormats: ["junit", "json", "html"],
  cleanupDestroyVm: true,
  cleanupKeepVmOnFailure: false,
  fixtures: [],
  productSteps: [],
  assertions: [
    { id: "powershell-system-exit-zero", type: "command.exitCode", bodyJson: '{"exitCode":0}' },
    { id: "powershell-system-marker", type: "command.stdoutContains", bodyJson: '{"text":"oslab powershell system demo"}' },
  ],
  fixtureCount: 0,
  assertionCount: 2,
};

const readyCheck = (message) => ({ ok: true, message });
const labStatus = {
  status: "ready",
  checkedAt: fixedNow,
  scenarioPath,
  configPath: "config/oslab.local.yaml",
  envFilePath: "config/oslab.local.env",
  checks: {
    configFile: readyCheck("Configuration loaded"),
    envFile: readyCheck("Environment loaded"),
    token: readyCheck("API token available"),
    connectivity: readyCheck("Provider reachable"),
    node: readyCheck("Demo node ready"),
    template: readyCheck("Windows template ready"),
    vmidRange: readyCheck("98 disposable VM IDs available"),
  },
  provider: { type: "proxmox", version: "8.3", node: "demo-node" },
  template: { vmId: 9200, name: "windows11-template-qga-9200", node: "demo-node", status: "stopped", isTemplate: true },
  vmidRange: {
    start: 9102,
    end: 9199,
    total: 98,
    usedInRange: [],
    reservedLocks: [],
    freeCount: 98,
    recommendedVmId: 9102,
    requiredCapacity: 1,
    capacityOk: true,
  },
  vms: { running: [], stale: [], oslab: [] },
  issues: [],
  warnings: [],
};

const runningJob = {
  id: jobId,
  kind: "run",
  status: "running",
  title: "Generic PowerShell system information Windows demo",
  createdAt: fixedNow,
  startedAt: fixedNow,
  completedAt: null,
  runId: null,
  exitCode: null,
};

const passedJob = {
  ...runningJob,
  status: "passed",
  completedAt: "2026-08-30T09:00:08.000Z",
  runId,
  exitCode: 0,
};

const passedRun = {
  id: runId,
  kind: "run",
  status: "passed",
  scenarioId: "demo.powershell.system.windows",
  scenarioPath,
  evidenceSummary: { total: 7, present: 7, missingRequired: 0, contractGaps: 0 },
  artifactStatus: "complete",
  jobId,
  jobStatus: "passed",
  startedAt: fixedNow,
  completedAt: "2026-08-30T09:00:08.000Z",
  path: `runs/${runId}`,
  updatedAt: "2026-08-30T09:00:08.000Z",
};

const evidenceItems = [
  ["run-json", "run.json", "core", "run.json", "Run summary"],
  ["progress-jsonl", "progress.jsonl", "timeline", "logs/progress.jsonl", "Execution timeline"],
  ["actual-output", "actual-output.json", "outputs", "raw/actual-output.json", "Raw command output"],
  ["command-result", "command-result.json", "outputs", "normalized/command-result.json", "Normalized result"],
  ["result-json", "result.json", "reports", "reports/result.json", "JSON report"],
  ["junit-xml", "result.junit.xml", "reports", "reports/result.junit.xml", "JUnit report"],
  ["report-html", "result.html", "reports", "reports/result.html", "HTML report"],
].map(([key, label, group, relativePath, description], index) => ({
  key,
  label,
  group,
  relativePath,
  required: true,
  status: "present",
  size: 640 + index * 128,
  modifiedAt: "2026-08-30T09:00:08.000Z",
  description,
  previewable: true,
}));

const runDetail = {
  ...passedRun,
  details: {
    mode: "artifact",
    reportFormats: ["junit", "json", "html"],
    artifactPath,
    outputs: { raw: "raw/actual-output.json", normalized: "normalized/command-result.json" },
    assertionSummary: { total: 2, passed: 2, failed: 0 },
    cleanup: { attempted: true, destroyed: true },
  },
  evidence: { total: 7, present: 7, missingRequired: 0, contractGaps: 0, items: evidenceItems },
  files: evidenceItems.map((item) => ({ ...item, discovered: false })),
};

const progressEvents = [
  ["09:00:00", "provider", "running", "Cloning disposable VM 9102"],
  ["09:00:02", "guest", "passed", "QEMU Guest Agent is ready"],
  ["09:00:03", "guest", "passed", "Windows guest channel selected: qemuAgent"],
  ["09:00:04", "artifact", "passed", "Artifact uploaded and verified"],
  ["09:00:05", "command", "passed", "PowerShell check exited with code 0"],
  ["09:00:06", "assertion", "passed", "2/2 assertions passed"],
  ["09:00:08", "cleanup", "passed", "Disposable VM destroyed; reports saved"],
].map(([time, phase, status, message]) => JSON.stringify({ timestamp: `2026-08-30T${time}.000Z`, phase, status, message })).join("\n");

await mkdir(outputDirectory, { recursive: true });
await Promise.all([rm(rawVideoPath, { force: true }), rm(posterPath, { force: true })]);

async function findAvailablePort() {
  const probe = createServer();
  await new Promise((resolve, reject) => {
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", resolve);
  });
  const address = probe.address();
  if (!address || typeof address === "string") throw new Error("Could not allocate a local capture port.");
  await new Promise((resolve, reject) => probe.close((error) => error ? reject(error) : resolve()));
  return address.port;
}

async function createIsolatedNextWorkspace() {
  const directory = await mkdtemp(join(outputDirectory, ".dashboard-next-"));
  const directoryLinkType = process.platform === "win32" ? "junction" : "dir";
  await Promise.all([
    copyFile(join(webDirectory, "package.json"), join(directory, "package.json")),
    copyFile(join(webDirectory, "tsconfig.json"), join(directory, "tsconfig.json")),
    copyFile(join(webDirectory, "next-env.d.ts"), join(directory, "next-env.d.ts")),
    copyFile(join(webDirectory, "next.config.mjs"), join(directory, "next.config.mjs")),
    cp(join(webDirectory, "public"), join(directory, "public"), { recursive: true }),
    cp(join(webDirectory, "src"), join(directory, "src"), { recursive: true }),
    symlink(join(webDirectory, "node_modules"), join(directory, "node_modules"), directoryLinkType),
  ]);
  return directory;
}

const capturePort = await findAvailablePort();
const baseUrl = `http://127.0.0.1:${capturePort}`;
const nextWorkspace = await createIsolatedNextWorkspace();
const serverOutput = [];
const server = spawn(process.execPath, [nextBin, "dev", "-H", "127.0.0.1", "-p", String(capturePort)], {
  cwd: nextWorkspace,
  env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
  windowsHide: true,
  stdio: ["ignore", "pipe", "pipe"],
});
for (const stream of [server.stdout, server.stderr]) {
  stream?.on("data", (chunk) => {
    serverOutput.push(String(chunk));
    if (serverOutput.length > 80) serverOutput.shift();
  });
}

async function waitForServer() {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) throw new Error(`Next.js exited early.\n${serverOutput.join("")}`);
    try {
      const response = await fetch(baseUrl);
      if (response.ok) return;
    } catch {
      // The development server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`Timed out waiting for ${baseUrl}.\n${serverOutput.join("")}`);
}

function json(route, value, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(value) });
}

async function installApiMocks(page) {
  let phase = "idle";
  const blockedRequests = [];
  const blockedWebSockets = [];

  await page.routeWebSocket("**/*", async (webSocket) => {
    const url = new URL(webSocket.url());
    if (url.hostname === "127.0.0.1" && url.port === String(capturePort)) {
      webSocket.connectToServer();
      return;
    }
    blockedWebSockets.push(webSocket.url());
    await webSocket.close({ code: 1008, reason: "External WebSockets are disabled in README capture" });
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const monacoPrefix = "/npm/monaco-editor@0.55.1/min/vs/";
    if (url.hostname === "cdn.jsdelivr.net" && url.pathname.startsWith(monacoPrefix)) {
      const relativePath = decodeURIComponent(url.pathname.slice(monacoPrefix.length));
      if (relativePath.includes("..")) {
        await route.abort("blockedbyclient");
        return;
      }
      const contentTypes = {
        ".css": "text/css",
        ".js": "text/javascript",
        ".json": "application/json",
        ".ttf": "font/ttf",
      };
      try {
        const body = await readFile(join(monacoDirectory, relativePath));
        await route.fulfill({ status: 200, contentType: contentTypes[extname(relativePath)] || "application/octet-stream", body });
      } catch {
        await route.fulfill({ status: 404, contentType: "text/plain", body: "Missing local Monaco asset" });
      }
      return;
    }
    const isLocal = url.hostname === "127.0.0.1" && [String(capturePort), "3001"].includes(url.port);
    if (["blob:", "data:"].includes(url.protocol)) {
      await route.continue();
      return;
    }
    if (!isLocal) {
      blockedRequests.push(request.url());
      await route.abort("blockedbyclient");
      return;
    }
    if (!url.pathname.startsWith("/api/")) {
      await route.continue();
      return;
    }

    const pathname = url.pathname;
    if (pathname === "/api/me") return json(route, { user: { username: "demo" } });
    if (pathname === "/api/catalog/scenarios") return json(route, [{ path: scenarioPath, name: "demo-powershell-system.example.yaml", kind: "scenario" }]);
    if (pathname === "/api/catalog/fixtures") return json(route, [{ path: fixturePath, name: "demo-powershell-system.ps1", kind: "fixture" }]);
    if (pathname === "/api/catalog/suites") return json(route, []);
    if (pathname === "/api/catalog/artifacts") return json(route, [{ path: artifactPath, name: "powershell-system", kind: "artifact" }]);
    if (pathname === "/api/lab/status") return json(route, labStatus);
    if (pathname === "/api/artifacts/check") return json(route, { ok: true, exists: true, kind: "directory", path: artifactPath, message: "Artifact is ready" });
    if (pathname === "/api/files" && request.method() === "GET") return json(route, { path: url.searchParams.get("path") || scenarioPath, content: scenarioYaml });
    if (pathname === "/api/build/scenario/inspect") return json(route, { ok: true, model: scenarioModel });
    if (pathname === "/api/validate/content") return json(route, { ok: true, kind: "yaml", checkedAt: fixedNow, issues: [], message: "Valid YAML" });
    if (pathname === "/api/jobs/run-scenario" && request.method() === "POST") {
      phase = "running";
      setTimeout(() => { phase = "passed"; }, 5_900);
      return json(route, runningJob);
    }
    if (pathname === "/api/jobs") return json(route, phase === "idle" ? [] : [phase === "passed" ? passedJob : runningJob]);
    if (pathname === `/api/jobs/${jobId}`) return json(route, phase === "passed" ? passedJob : runningJob);
    if (pathname === `/api/jobs/${jobId}/log`) return json(route, {
      log: phase === "idle" ? "" : [
        "[provider] clone VM 9102 from windows11-template-qga-9200",
        "[guest] waiting for QEMU Guest Agent",
        "[artifact] powershell-system archive ready",
      ].join("\n") + "\n",
    });
    if (pathname === "/api/runs") return json(route, phase === "passed" ? [passedRun] : []);
    if (pathname === `/api/runs/${runId}`) return json(route, runDetail);
    if (pathname === `/api/runs/${runId}/file`) return route.fulfill({ contentType: "application/x-ndjson", body: progressEvents });
    return route.fulfill({ status: 404, contentType: "text/plain", body: `Unmocked demo request: ${request.method()} ${pathname}` });
  });
  return { blockedRequests, blockedWebSockets };
}

async function installPageEnvironment(page) {
  await page.addInitScript(({ now }) => {
    const NativeDate = Date;
    const fixed = NativeDate.parse(now);
    class FixedDate extends NativeDate {
      constructor(...args) {
        super(...(args.length ? args : [fixed]));
      }
      static now() { return fixed; }
    }
    Object.setPrototypeOf(FixedDate, NativeDate);
    globalThis.Date = FixedDate;
    localStorage.setItem("oslab.lang", "en");
    localStorage.removeItem("oslab.recentArtifacts");

    class DemoEventSource extends EventTarget {
      constructor() {
        super();
        const events = [
          [700, "stdout", "[provider] disposable VM 9102 cloned\n"],
          [1_600, "stdout", "[guest] QEMU Guest Agent ready\n"],
          [2_500, "stdout", "[guest] selected qemuAgent channel\n"],
          [3_400, "stdout", "[artifact] powershell-system uploaded\n"],
          [4_400, "stdout", "[command] exit code 0\n"],
          [5_300, "stdout", "[assertion] 2/2 passed\n"],
          [6_300, "done", "passed"],
        ];
        this.timers = events.map(([delay, type, data]) => setTimeout(() => this.dispatchEvent(new MessageEvent(type, { data })), delay));
      }
      close() { for (const timer of this.timers || []) clearTimeout(timer); }
    }
    globalThis.EventSource = DemoEventSource;
  }, { now: fixedNow });

}

async function installPresentationLayer(page) {
  await page.addStyleTag({ content: `
    nextjs-portal { display: none !important; }
    #readme-demo-cursor {
      position: fixed; z-index: 2147483647; width: 18px; height: 18px;
      border: 2px solid #edf2f4; border-radius: 50%; pointer-events: none;
      box-shadow: 0 0 0 4px rgba(69,212,131,.22), 0 4px 18px rgba(0,0,0,.42);
      transform: translate(-50%, -50%); transition: left .48s cubic-bezier(.22,1,.36,1), top .48s cubic-bezier(.22,1,.36,1), transform .16s;
    }
    #readme-demo-cursor.clicking { transform: translate(-50%, -50%) scale(.68); }
  ` });
  await page.evaluate(() => {
    const cursor = document.createElement("div");
    cursor.id = "readme-demo-cursor";
    cursor.style.left = "82%";
    cursor.style.top = "12%";
    document.body.append(cursor);
  });
}

async function moveCursor(page, locator) {
  const box = await locator.boundingBox();
  if (!box) throw new Error("Cannot move the demo cursor to a hidden element.");
  await page.evaluate(({ x, y }) => {
    const cursor = document.querySelector("#readme-demo-cursor");
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
  }, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
  await page.waitForTimeout(560);
}

async function demoClick(page, locator) {
  await locator.scrollIntoViewIfNeeded();
  await moveCursor(page, locator);
  await page.evaluate(() => document.querySelector("#readme-demo-cursor")?.classList.add("clicking"));
  await page.waitForTimeout(140);
  await locator.click();
  await page.evaluate(() => document.querySelector("#readme-demo-cursor")?.classList.remove("clicking"));
  await page.waitForTimeout(650);
}

async function smoothIntoView(page, locator) {
  await locator.evaluate((element) => element.scrollIntoView({ behavior: "smooth", block: "center" }));
  await page.waitForTimeout(900);
}

async function assertPublicFrame(page) {
  const text = await page.locator("body").innerText();
  const forbidden = ["C:\\Users\\", "/Users/", "192.168."];
  const found = forbidden.filter((value) => text.includes(value));
  if (found.length) throw new Error(`Public demo contains forbidden markers: ${found.join(", ")}`);
}

let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    locale: "en-US",
    timezoneId: "UTC",
    viewport: { width: 1280, height: 800 },
    recordVideo: { dir: outputDirectory, size: { width: 1280, height: 800 } },
    reducedMotion: "no-preference",
    serviceWorkers: "block",
  });
  const page = await context.newPage();
  const video = page.video();
  const browserErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("favicon")) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));

  const { blockedRequests, blockedWebSockets } = await installApiMocks(page);
  await installPageEnvironment(page);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.locator(".shell").waitFor({ timeout: 30_000 });
  await installPresentationLayer(page);
  await page.waitForTimeout(1_400);
  await assertPublicFrame(page);

  const scenarioNav = page.getByRole("button", { name: "Scenario Studio", exact: true });
  await demoClick(page, scenarioNav);
  const scenarioRow = page.locator(".listPanelBody button").filter({ hasText: "demo-powershell-system" }).first();
  await demoClick(page, scenarioRow);
  await page.locator(".editorWorkspaceVertical").waitFor({ timeout: 10_000 });
  const editButton = page.getByRole("button", { name: "Edit", exact: true }).last();
  await demoClick(page, editButton);
  const expandBuilder = page.locator(".scenarioBuilderPanel .builderToggle[aria-expanded='false']").first();
  if (await expandBuilder.count()) await demoClick(page, expandBuilder);
  await page.waitForTimeout(2_000);
  await assertPublicFrame(page);

  const runNav = page.getByRole("button", { name: "Run Launcher", exact: true });
  await demoClick(page, runNav);
  const selects = page.locator(".runGrid select");
  await selects.nth(1).selectOption(scenarioPath);
  await selects.nth(2).selectOption(artifactPath);
  await page.waitForTimeout(1_200);
  const runButton = page.getByRole("button", { name: "Run selected scenario", exact: true });
  await smoothIntoView(page, runButton);
  await demoClick(page, runButton);
  const consolePanel = page.locator(".runGrid .console");
  await smoothIntoView(page, consolePanel);
  await page.waitForTimeout(6_900);
  await assertPublicFrame(page);

  const resultsNav = page.getByRole("button", { name: "Results Explorer", exact: true });
  await demoClick(page, resultsNav);
  await page.locator(".resultsGrid").waitFor({ timeout: 15_000 });
  await page.locator(".resultRow").first().click();
  await page.locator(".evidencePanel").waitFor({ timeout: 15_000 });
  await smoothIntoView(page, page.locator(".evidencePanel"));
  await page.waitForTimeout(2_400);
  await assertPublicFrame(page);
  await page.screenshot({ path: posterPath, fullPage: false });

  if (blockedRequests.length) throw new Error(`Dashboard demo blocked external requests:\n${blockedRequests.join("\n")}`);
  if (blockedWebSockets.length) throw new Error(`Dashboard demo blocked external WebSockets:\n${blockedWebSockets.join("\n")}`);
  if (browserErrors.length) throw new Error(`Dashboard demo browser errors:\n${browserErrors.join("\n")}`);
  await context.close();
  if (!video) throw new Error("Playwright did not create the dashboard demo video.");
  const temporaryVideoPath = await video.path();
  await video.saveAs(rawVideoPath);
  if (temporaryVideoPath !== rawVideoPath) await rm(temporaryVideoPath, { force: true });
} finally {
  await browser?.close();
  server.kill("SIGTERM");
  await new Promise((resolve) => setTimeout(resolve, 600));
  if (server.exitCode === null) server.kill("SIGKILL");
  await rm(nextWorkspace, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}

console.log(`Dashboard recording: ${rawVideoPath}`);
console.log(`Dashboard poster: ${posterPath}`);
