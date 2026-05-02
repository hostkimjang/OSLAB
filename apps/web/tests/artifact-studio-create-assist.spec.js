import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const root = process.cwd();
const outDir = path.join(root, "output", "web-dashboard");
const baseUrl = process.env.OSLAB_WEB_BASE_URL ?? "http://127.0.0.1:3000";

async function installArtifactStudioMocks(page) {
  const artifacts = [
    {
      path: "validation/artifacts/powershell-system/run-system-demo.ps1",
      name: "run-system-demo.ps1",
      source: "repo",
      kind: "file",
      artifactType: "text",
      editable: true,
      previewable: true,
      size: 512,
      totalBytes: 512,
      fileCount: 1,
      modifiedAt: new Date().toISOString(),
      hash: "a".repeat(64),
      archivable: true,
      deletable: false,
      archiveOnly: true,
    },
    {
      path: "validation/artifacts/powershell-system",
      name: "powershell-system",
      source: "repo",
      kind: "directory",
      artifactType: "directory",
      editable: false,
      previewable: false,
      size: 2048,
      totalBytes: 2048,
      fileCount: 2,
      modifiedAt: new Date().toISOString(),
      hash: null,
      archivable: true,
      deletable: false,
      archiveOnly: true,
    },
    {
      path: "validation/artifacts/web-python-demo.py",
      name: "web-python-demo.py",
      source: "repo",
      kind: "file",
      artifactType: "text",
      editable: true,
      previewable: true,
      size: 64,
      totalBytes: 64,
      fileCount: 1,
      modifiedAt: new Date().toISOString(),
      hash: "c".repeat(64),
      archivable: true,
      deletable: false,
      archiveOnly: true,
    },
  ];
  const contents = new Map([
    [
      "validation/artifacts/powershell-system/run-system-demo.ps1",
      "param(\n  [string]$OutputPath = \"C:\\Oslab\\command-result.json\"\n)\nWrite-Output \"artifact executed\"\n",
    ],
    [
      "validation/artifacts/web-python-demo.py",
      "pri\n",
    ],
  ]);

  const toolStatus = {
    language: "powershell",
    label: "PowerShell",
    state: "partial",
    installable: true,
    installHint: "Install PowerShell 7 (`pwsh`) for the best editor and validation path.",
    nextAction: "Built-in checks are available; optional tools can improve diagnostics.",
    tools: [
      { id: "pwsh", label: "PowerShell 7", state: "missing", hint: "Recommended modern PowerShell host." },
      { id: "powershell", label: "Windows PowerShell", state: "available", command: "powershell.exe", version: "5.1" },
    ],
  };
  const pythonToolStatus = {
    language: "python",
    label: "Python",
    state: "available",
    mode: "lsp",
    serverManaged: true,
    installable: false,
    installHint: "Repo-managed Pyright provides Python completion and diagnostics.",
    nextAction: "LSP-backed completion is available from the dashboard API server.",
    tools: [{ id: "pyright-langserver", label: "Pyright LSP", state: "available", command: "pyright-langserver", hint: "Repo-managed Python language server." }],
  };

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;

    if (pathname === "/api/me") {
      await route.fulfill({ json: { user: { username: "admin" } } });
      return;
    }
    if (pathname.startsWith("/api/catalog/")) {
      await route.fulfill({ json: [] });
      return;
    }
    if (pathname === "/api/jobs" || pathname === "/api/runs") {
      await route.fulfill({ json: [] });
      return;
    }
    if (pathname === "/api/lab/status") {
      await route.fulfill({
        json: {
          status: "ready",
          scenarioPath: "scenarios/windows/demo-powershell-system.example.yaml",
          provider: { version: "mock", node: "mock-node" },
          template: { vmId: 9101, name: "mock-template" },
          vmidRange: { start: 9102, end: 9199, freeCount: 98, recommendedVmId: 9102 },
          vms: { running: [], stale: [] },
          checks: {
            configFile: { ok: true, message: "Config file exists" },
            envFile: { ok: true, message: "Env file exists" },
            token: { ok: true, message: "Token exists" },
            connectivity: { ok: true, message: "Provider reachable" },
            node: { ok: true, message: "Node exists" },
            template: { ok: true, message: "Template exists" },
            vmidRange: { ok: true, message: "VMID range ready" },
          },
          checkedAt: new Date().toISOString(),
          issues: [],
          warnings: [],
        },
      });
      return;
    }
    if (pathname === "/api/artifacts/manage") {
      await route.fulfill({ json: artifacts });
      return;
    }
    if (pathname === "/api/artifacts/language-tools") {
      await route.fulfill({ json: [toolStatus, pythonToolStatus] });
      return;
    }
    if (pathname === "/api/artifacts/language-tools/install") {
      await route.fulfill({ json: { ok: false, language: "powershell", message: toolStatus.installHint, status: toolStatus } });
      return;
    }
    if (pathname === "/api/artifacts/content" && request.method() === "GET") {
      const target = url.searchParams.get("path") || "";
      await route.fulfill({ json: { path: target, content: contents.get(target) || "" } });
      return;
    }
    if (pathname === "/api/artifacts/template" && request.method() === "POST") {
      const body = request.postDataJSON();
      const artifact = {
        path: body.path,
        name: path.basename(body.path),
        source: "repo",
        kind: "file",
        artifactType: "text",
        editable: true,
        previewable: true,
        size: 256,
        totalBytes: 256,
        fileCount: 1,
        modifiedAt: new Date().toISOString(),
        hash: "b".repeat(64),
        archivable: true,
        deletable: false,
        archiveOnly: true,
      };
      artifacts.unshift(artifact);
      contents.set(body.path, "param(\n  [string]$OutputPath = \"C:\\Oslab\\command-result.json\"\n)\nWrite-Output \"created\"\n");
      await route.fulfill({ json: { path: body.path, content: contents.get(body.path) } });
      return;
    }
    if (pathname === "/api/artifacts/assist/check") {
      const body = request.postDataJSON();
      const isPython = String(body.path || "").endsWith(".py");
      await route.fulfill({
        json: {
          ok: true,
          checkedAt: new Date().toISOString(),
          language: isPython ? "python" : "powershell",
          toolStatus: isPython ? pythonToolStatus : toolStatus,
          issues: [{ severity: "info", code: "output.contract", message: "Consider writing a machine-readable output file.", line: 1 }],
          snippets: [{ id: "placeholder-output-path", label: "{{OutputPath}}", detail: "Output JSON path placeholder.", language: isPython ? "python" : "powershell", insertText: "{{OutputPath}}" }],
          suggestedSnippets: [{ id: "placeholder-output-path", label: "{{OutputPath}}", detail: "Output JSON path placeholder.", language: isPython ? "python" : "powershell", insertText: "{{OutputPath}}" }],
          firstRunTips: ["Artifact is copied into the VM before the command runs."],
        },
      });
      return;
    }
    if (pathname === "/api/artifacts/assist/complete") {
      const body = request.postDataJSON();
      const language = body.language || "python";
      await route.fulfill({
        json: {
          ok: true,
          language,
          mode: language === "python" ? "lsp" : "internal",
          checkedAt: new Date().toISOString(),
          toolStatus: language === "python" ? pythonToolStatus : toolStatus,
          fallbackReason: null,
          items: language === "python"
            ? [
              { id: "python-print", label: "print", detail: "Python 출력 함수", documentation: "Python stdout", language, insertText: "print(${1:\"artifact executed\"})", source: "lsp", kind: "function" },
              { id: "python-range", label: "range", detail: "Python range 함수", documentation: "Python integer sequence", language, insertText: "range(${1:3})", source: "lsp", kind: "function" },
              { id: "python-for-range", label: "for i in range", detail: "Python 반복문", documentation: "Python loop snippet", language, insertText: "for ${1:i} in range(${2:3}):\\n    ${3:print($1)}", source: "snippet", kind: "snippet" },
              { id: "python-json", label: "json.dumps", detail: "JSON writer", documentation: "JSON writer", language, insertText: "json.dumps(${1:result}, indent=2)", source: "lsp", kind: "function" },
            ]
            : [{ id: "ps-write", label: "Write-Output", detail: "PowerShell stdout", language, insertText: "Write-Output ${1:\"artifact executed\"}", source: "internal", kind: "function" }],
        },
      });
      return;
    }
    if (pathname === "/api/validate/content") {
      await route.fulfill({ json: { ok: true, kind: "powershell", checkedAt: new Date().toISOString(), issues: [], message: "ok" } });
      return;
    }
    if (pathname === "/api/artifacts/tree") {
      await route.fulfill({ json: { path: "validation/artifacts/powershell-system", items: [], totalItems: 0, truncated: false } });
      return;
    }

    await route.fulfill({ status: 404, body: `unmocked ${request.method()} ${pathname}` });
  });
}

test("artifact studio create mode clears selection and exposes assist guidance", async ({ page }) => {
  fs.mkdirSync(outDir, { recursive: true });
  await installArtifactStudioMocks(page);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.locator(".shell").waitFor({ timeout: 15000 });

  await page.getByRole("button", { name: /Artifact Studio|아티팩트/ }).click();
  await expect(page.locator(".artifactManagerList button.selected")).toHaveCount(1);

  await page.getByTestId("artifact-studio-new").click();
  await expect(page.getByTestId("artifact-create-workspace")).toBeVisible();
  await expect(page.locator(".artifactManagerList button.selected")).toHaveCount(0);
  await expect(page.getByText(/Create a new artifact|새로운 artifact/)).toBeVisible();
  await expect(page.getByText(/Language tools|언어 도구/)).toBeVisible();
  await page.screenshot({ path: path.join(outDir, "artifact-studio-create-flow.png"), fullPage: false });

  const createPath = `validation/artifacts/web-qa-${Date.now()}.ps1`;
  await page.getByLabel(/Save path|저장 경로/).fill(createPath);
  await page.getByTestId("artifact-create-submit").click();
  await expect(page.locator(".artifactManagerList button.selected")).toHaveCount(1);
  await expect(page.locator(".artifactManagerList button.selected")).toContainText(path.basename(createPath));

  await page.getByRole("button", { name: /Edit|수정/ }).click();
  await expect(page.getByText(/Script building help|스크립트 제작 도움/)).toBeVisible();
  await expect(page.getByText("자동완성 안내")).toBeVisible();
  await expect(page.locator(".languageToolCard").filter({ hasText: "PowerShell" })).toBeVisible();
  await page.screenshot({ path: path.join(outDir, "artifact-studio-assist-language-tools.png"), fullPage: false });

  await page.getByRole("button", { name: /web-python-demo\.py validation/ }).click();
  await page.getByRole("button", { name: /Edit|수정/ }).click();
  await page.locator(".monaco-editor").evaluate((node) => {
    const target = node.querySelector('[role="textbox"]');
    if (target instanceof HTMLElement) target.focus();
  });
  await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
  await page.keyboard.type("pri");
  await page.keyboard.press(process.platform === "darwin" ? "Meta+Space" : "Control+Space");
  await expect(page.locator(".suggest-widget")).toContainText("print", { timeout: 10000 });
  await page.screenshot({ path: path.join(outDir, "artifact-studio-python-lsp-print.png"), fullPage: false });

  await page.keyboard.press("Escape");
  await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
  await page.keyboard.type("for i in ra");
  await page.keyboard.press(process.platform === "darwin" ? "Meta+Space" : "Control+Space");
  await expect(page.locator(".suggest-widget")).toContainText("range", { timeout: 10000 });
  await page.screenshot({ path: path.join(outDir, "artifact-studio-python-lsp-range.png"), fullPage: false });

  const exactInput = "alpha beta gamma\nprint(\"stable input\")\nfor i in range(3)\n";
  await page.keyboard.press("Escape");
  await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
  await page.keyboard.type(exactInput, { delay: 1 });
  await expect.poll(async () => page.locator(".monaco-editor").evaluate((node) => {
    const model = (window).monaco?.editor?.getModels?.().find((candidate) => candidate.uri.path.endsWith("web-python-demo.py"));
    return model?.getValue() || node.textContent || "";
  })).toBe(exactInput);
  await page.screenshot({ path: path.join(outDir, "artifact-studio-python-typing-stability.png"), fullPage: false });

  await page.getByRole("button", { name: /Autocomplete|자동완성/ }).click();
  await expect(page.getByText(/언어별 자동완성|Autocomplete/)).toBeVisible();
  await expect(page.locator(".completionGuideItem").filter({ hasText: "print" }).first()).toBeVisible();
});
