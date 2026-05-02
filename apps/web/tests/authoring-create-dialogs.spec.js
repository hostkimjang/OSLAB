import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const root = process.cwd();
const outDir = path.join(root, "output", "web-dashboard");
const baseUrl = process.env.OSLAB_WEB_BASE_URL ?? "http://127.0.0.1:3000";

async function installApiMocks(page) {
  const catalogs = {
    scenarios: [
      { path: "scenarios/windows/demo-powershell-system.example.yaml", name: "demo-powershell-system.example.yaml", kind: "scenario" },
      { path: "scenarios/linux/generic-smoke.example.yaml", name: "generic-smoke.example.yaml", kind: "scenario" },
    ],
    fixtures: [
      { path: "validation/fixtures/windows/demo-powershell-system.ps1", name: "demo-powershell-system.ps1", kind: "fixture" },
    ],
    suites: [
      { path: "validation/suites/smoke.example.yaml", name: "smoke.example.yaml", kind: "suite" },
    ],
    artifacts: [],
  };
  const created = [];

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;

    if (pathname === "/api/me") {
      await route.fulfill({ json: { user: { username: "admin" } } });
      return;
    }
    if (pathname === "/api/catalog/scenarios") {
      await route.fulfill({ json: catalogs.scenarios });
      return;
    }
    if (pathname === "/api/catalog/fixtures") {
      await route.fulfill({ json: catalogs.fixtures });
      return;
    }
    if (pathname === "/api/catalog/suites") {
      await route.fulfill({ json: catalogs.suites });
      return;
    }
    if (pathname === "/api/catalog/artifacts") {
      await route.fulfill({ json: catalogs.artifacts });
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
          scenarioPath: catalogs.scenarios[0].path,
          provider: { version: "mock", node: "mock-node" },
          template: { vmId: 100, name: "mock-template" },
          vmidRange: { start: 9000, end: 9010, freeCount: 11, recommendedVmId: 9001 },
          vms: { running: [], stale: [] },
          checks: {
            connectivity: { ok: true, message: "ok" },
            node: { ok: true, message: "ok" },
            template: { ok: true, message: "ok" },
            vmidRange: { ok: true, message: "ok" },
          },
          checkedAt: new Date().toISOString(),
          issues: [],
          warnings: [],
        },
      });
      return;
    }
    if (pathname === "/api/validate/content") {
      await route.fulfill({ json: { ok: true, kind: "mock", checkedAt: new Date().toISOString(), issues: [], message: "ok" } });
      return;
    }
    if (pathname === "/api/build/suite/inspect") {
      const body = request.postDataJSON();
      const content = String(body?.content || "");
      await route.fulfill({
        json: {
          ok: true,
          model: {
            id: /id:\s*(.+)/.exec(content)?.[1]?.trim() || "new.smoke",
            name: /name:\s*"?([^"\n]+)"?/.exec(content)?.[1]?.trim() || "New smoke suite",
            maxParallel: Number(/maxParallel:\s*(\d+)/.exec(content)?.[1] || 1),
            runs: [
              {
                id: "demo-powershell-system",
                scenario: catalogs.scenarios[0].path,
                tier: "ci",
                allowFailure: false,
                enabled: true,
              },
            ],
          },
        },
      });
      return;
    }
    if (pathname === "/api/build/fixture/template") {
      const body = request.postDataJSON();
      const fixturePath = String(body?.path || "validation/fixtures/windows/new-fixture.ps1");
      await route.fulfill({
        json: {
          ok: true,
          path: fixturePath,
          content: [
            "param(",
            "  [string]$OutputPath = \"C:\\Oslab\\fixture-result.json\"",
            ")",
            "",
            "$result = @{",
            "  ok = $true",
            `  id = "${body?.id || "new-fixture"}"`,
            "}",
            "",
            "$result | ConvertTo-Json -Depth 8 | Set-Content -Path $OutputPath -Encoding UTF8",
            "",
          ].join("\n"),
        },
      });
      return;
    }
    if (pathname === "/api/build/scenario/template") {
      const body = request.postDataJSON();
      const scenarioPath = String(body?.path || "scenarios/windows/new-smoke.example.yaml");
      await route.fulfill({
        json: {
          ok: true,
          path: scenarioPath,
          content: [
            "schemaVersion: 1",
            `id: ${body?.id || "new.windows.smoke"}`,
            `name: "${body?.name || "New Windows smoke"}"`,
            "os:",
            "  family: windows",
            "  version: \"11\"",
            "provider:",
            "  type: proxmox",
            "  template: windows11-template-qga-9101",
            "  vmIdRange:",
            "    start: 9102",
            "    end: 9199",
            "guest:",
            "  mode: auto",
            "assertions:",
            "  - type: command.exitCode",
            "    id: exit-zero",
            "    expected: 0",
            "",
          ].join("\n"),
        },
      });
      return;
    }
    if (pathname === "/api/build/suite/template") {
      const body = request.postDataJSON();
      const suitePath = String(body?.path || "validation/suites/new-smoke.example.yaml");
      const scenarioPaths = Array.isArray(body?.scenarioPaths) && body.scenarioPaths.length ? body.scenarioPaths : [String(body?.scenarioPath || catalogs.scenarios[0].path)];
      await route.fulfill({
        json: {
          ok: true,
          path: suitePath,
          content: [
            "schemaVersion: 1",
            `id: ${body?.id || "new.smoke"}`,
            `name: "${body?.name || "New smoke suite"}"`,
            `maxParallel: ${body?.maxParallel || 1}`,
            "runs:",
            ...scenarioPaths.flatMap((scenarioPath, index) => [
              `  - id: ${index === 0 ? "demo-powershell-system" : "generic-smoke"}`,
              `    scenario: ${scenarioPath}`,
              `    tier: ${body?.tier || "ci"}`,
              `    allowFailure: ${Boolean(body?.allowFailure)}`,
              `    enabled: ${body?.enabled !== false}`,
            ]),
            "",
          ].join("\n"),
        },
      });
      return;
    }
    if (pathname === "/api/files" && request.method() === "POST") {
      const body = request.postDataJSON();
      created.push(body);
      if (String(body.path).startsWith("validation/fixtures/")) {
        catalogs.fixtures = [{ path: body.path, name: path.basename(body.path), kind: "fixture" }, ...catalogs.fixtures];
      }
      if (String(body.path).startsWith("scenarios/")) {
        catalogs.scenarios = [{ path: body.path, name: path.basename(body.path), kind: "scenario" }, ...catalogs.scenarios];
      }
      if (String(body.path).startsWith("validation/suites/")) {
        catalogs.suites = [{ path: body.path, name: path.basename(body.path), kind: "suite" }, ...catalogs.suites];
      }
      await route.fulfill({ json: { ok: true, path: body.path } });
      return;
    }
    if (pathname === "/api/files" && request.method() === "GET") {
      const target = url.searchParams.get("path") || "";
      const match = created.find((item) => item.path === target);
      await route.fulfill({ json: { path: target, content: match?.content || "" } });
      return;
    }

    await route.fulfill({ status: 404, body: `unmocked ${request.method()} ${pathname}` });
  });

  return created;
}

async function gotoDashboard(page) {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.locator(".shell").waitFor({ timeout: 15000 });
}

test("scenario, fixture, and suite creation dialogs produce local templates", async ({ page }) => {
  fs.mkdirSync(outDir, { recursive: true });
  const created = await installApiMocks(page);
  await gotoDashboard(page);

  await page.getByRole("button", { name: /Scenarios|시나리오/ }).click();
  await page.getByRole("button", { name: /New scenario|새 시나리오/ }).click();
  await expect(page.getByTestId("scenario-create-dialog")).toBeVisible();
  await page.screenshot({ path: path.join(outDir, "authoring-new-scenario-dialog.png"), fullPage: false });
  await page.getByTestId("scenario-create-id-input").fill("web.ui.scenario");
  await page.getByTestId("scenario-create-name-input").fill("Web UI scenario");
  await page.getByTestId("scenario-create-path-input").fill("scenarios/windows/web-ui-scenario.example.yaml");
  await page.getByTestId("scenario-create-submit").click();
  await expect(page.locator(".editorTitle code")).toContainText("scenarios/windows/web-ui-scenario.example.yaml");

  await page.getByRole("button", { name: /Fixture Studio|환경 준비/ }).click();
  await page.getByRole("button", { name: /New fixture|새 환경 준비/ }).click();
  await expect(page.getByTestId("fixture-create-dialog")).toBeVisible();
  await page.screenshot({ path: path.join(outDir, "authoring-new-fixture-dialog.png"), fullPage: false });
  await page.getByTestId("fixture-create-id-input").fill("web-ui-fixture");
  await page.getByTestId("fixture-create-submit").click();
  await expect(page.locator(".editorTitle code")).toContainText("validation/fixtures/windows/web-ui-fixture.ps1");

  await page.getByRole("button", { name: /Suite Composer|실행 묶음/ }).click();
  await page.getByRole("button", { name: /New suite|새 실행 묶음/ }).click();
  await expect(page.getByTestId("suite-create-dialog")).toBeVisible();
  await page.screenshot({ path: path.join(outDir, "authoring-new-suite-dialog.png"), fullPage: false });
  await page.getByTestId("suite-create-id-input").fill("web.ui.smoke");
  await page.getByTestId("suite-create-name-input").fill("Web UI smoke");
  await expect(page.getByTestId("suite-create-id-input")).toHaveValue("web.ui.smoke");
  await expect(page.getByTestId("suite-create-name-input")).toHaveValue("Web UI smoke");
  await page.getByTestId("suite-create-scenario-search").fill("web-ui-scenario");
  await page.getByTestId("suite-create-dialog").locator(".suiteCreateScenarioOption", { hasText: "web-ui-scenario.example.yaml" }).locator("input[type=checkbox]").check();
  await page.getByTestId("suite-create-scenario-search").fill("generic");
  await page.getByTestId("suite-create-dialog").locator(".suiteCreateScenarioOption", { hasText: "generic-smoke.example.yaml" }).locator("input[type=checkbox]").check();
  await page.getByTestId("suite-create-scenario-search").fill("");
  await page.getByTestId("suite-create-path-input").fill("validation/suites/web-ui-smoke.example.yaml");
  await page.getByTestId("suite-create-max-parallel-input").fill("2");
  await page.getByTestId("suite-create-submit").click();
  await expect(page.locator(".editorTitle code")).toContainText("validation/suites/web-ui-smoke.example.yaml");
  await page.getByRole("button", { name: "실행", exact: true }).click();
  await expect(page.locator("label").filter({ hasText: "실행 묶음(Suite)" }).locator("select")).toHaveValue("validation/suites/web-ui-smoke.example.yaml");

  expect(created.find((item) => item.path === "scenarios/windows/web-ui-scenario.example.yaml")?.content).toContain("id: web.ui.scenario");
  expect(created.find((item) => item.path === "validation/fixtures/windows/web-ui-fixture.ps1")?.content).toContain('id = "web-ui-fixture"');
  const suiteContent = created.find((item) => item.path === "validation/suites/web-ui-smoke.example.yaml")?.content || "";
  expect(suiteContent).toContain("id: web.ui.smoke");
  expect(suiteContent).toContain('name: "Web UI smoke"');
  expect(suiteContent).toContain("maxParallel: 2");
  expect(suiteContent).toContain("scenario: scenarios/windows/web-ui-scenario.example.yaml");
  expect(suiteContent).toContain("scenario: scenarios/linux/generic-smoke.example.yaml");
  expect(suiteContent).toContain("enabled: true");
});
