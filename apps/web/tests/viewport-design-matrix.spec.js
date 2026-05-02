import fs from "node:fs";
import path from "node:path";
import { test } from "@playwright/test";

const root = process.cwd();
const outDir = path.join(root, "output", "web-dashboard");
const baseUrl = process.env.OSLAB_WEB_BASE_URL ?? "http://127.0.0.1:3000";

const viewports = [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "narrow-desktop", width: 1024, height: 768 },
  { name: "desktop-1366", width: 1366, height: 768 },
  { name: "fhd", width: 1920, height: 1080 },
  { name: "qhd", width: 2560, height: 1440 },
];

const navLabels = {
  시나리오: ["시나리오", "Scenarios"],
  실행: ["실행", "Run"],
  결과: ["결과", "Results"],
};

async function login(page) {
  const response = await page.request.post(`${baseUrl}/api/auth/login`, {
    data: { username: "admin", password: "oslab-admin" },
  });
  if (!response.ok()) {
    throw new Error(`API login failed: ${response.status()}`);
  }
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.locator(".shell").waitFor({ timeout: 15000 });
}

async function go(page, label) {
  for (const name of navLabels[label] ?? [label]) {
    const button = page.getByRole("button", { name, exact: true }).first();
    if ((await button.count()) && (await button.isVisible().catch(() => false))) {
      await button.click({ timeout: 5000 });
      await page.waitForTimeout(700);
      return;
    }
  }
  throw new Error(`Navigation button not found: ${label}`);
}

async function openScenarioBuilder(page) {
  await go(page, "시나리오");
  const expandButton = page.locator(".listPanel .iconButton[aria-expanded='false']").first();
  if (await expandButton.count()) {
    await expandButton.click();
    await page.waitForTimeout(250);
  }
  const search = page.getByPlaceholder("파일 검색");
  if (await search.count()) {
    await search.fill("uat-windows-smoke");
    await page.waitForTimeout(250);
  }
  let selected = page.locator(".listPanelBody button").filter({ hasText: "uat-windows-smoke" }).first();
  if (!(await selected.count())) selected = page.locator(".listPanelBody button").first();
  if (await selected.count()) {
    await selected.click();
    await page.waitForTimeout(500);
  }
  if (await search.count()) {
    await search.fill("");
    await page.waitForTimeout(250);
  }
  const edit = page.getByRole("button", { name: "수정" });
  if (await edit.count()) {
    await edit.click();
    await page.waitForTimeout(500);
  }
  await page.locator(".editorWorkspaceVertical").waitFor({ timeout: 10000 });
}

async function collectMetrics(page) {
  return await page.evaluate(() => {
    const rect = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const box = element.getBoundingClientRect();
      return {
        x: Math.round(box.x),
        y: Math.round(box.y),
        width: Math.round(box.width),
        height: Math.round(box.height),
      };
    };
    const all = (selector) => Array.from(document.querySelectorAll(selector));
    const stepButtons = all(".builderStepperRail button").map((button) => {
      const box = button.getBoundingClientRect();
      return {
        x: Math.round(box.x),
        y: Math.round(box.y),
        width: Math.round(box.width),
        height: Math.round(box.height),
      };
    });
    const stepWidths = stepButtons.map((button) => button.width);
    const stepHeights = stepButtons.map((button) => button.height);
    const stepGapMax = (() => {
      if (stepButtons.length < 2) return 0;
      const horizontal = (Math.max(...stepButtons.map((button) => button.x)) - Math.min(...stepButtons.map((button) => button.x))) >=
        (Math.max(...stepButtons.map((button) => button.y)) - Math.min(...stepButtons.map((button) => button.y)));
      const sorted = [...stepButtons].sort((a, b) => horizontal ? a.x - b.x : a.y - b.y);
      return Math.max(...sorted.slice(1).map((button, index) => {
        const prev = sorted[index];
        return horizontal ? button.x - (prev.x + prev.width) : button.y - (prev.y + prev.height);
      }));
    })();
    const workspaceRect = rect(".editorWorkspaceVertical");
    const shellRect = rect(".codeEditorShell");
    const runGrid = document.querySelector(".runGrid");
    const runPanels = all(".runGrid > .panel").map((panel) => {
      const box = panel.getBoundingClientRect();
      const style = getComputedStyle(panel);
      return {
        x: Math.round(box.x),
        y: Math.round(box.y),
        width: Math.round(box.width),
        height: Math.round(box.height),
        internalYScroll: panel.scrollHeight > panel.clientHeight + 1 && style.overflowY !== "visible",
        contentOverflow: panel.scrollHeight > panel.clientHeight + 1,
      };
    });
    const statusCells = all(".labGrid .statusCell").map((cell) => cell.scrollWidth > cell.clientWidth + 1);
    const listRows = all(".listPanelBody button").map((row) => {
      const rowBox = row.getBoundingClientRect();
      const title = row.querySelector(".listTitle");
      const path = row.querySelector("small");
      const titleBox = title?.getBoundingClientRect();
      const pathBox = path?.getBoundingClientRect();
      return {
        rowHeight: Math.round(rowBox.height),
        titleVisible: !!titleBox && titleBox.top >= rowBox.top - 1 && titleBox.bottom <= rowBox.bottom + 1,
        pathVisible: !!pathBox && pathBox.top >= rowBox.top - 1 && pathBox.bottom <= rowBox.bottom + 1,
      };
    });
    const doc = document.documentElement;
    return {
      document: {
        clientWidth: doc.clientWidth,
        scrollWidth: doc.scrollWidth,
        clientHeight: doc.clientHeight,
        scrollHeight: doc.scrollHeight,
        horizontalOverflow: doc.scrollWidth > doc.clientWidth + 1,
      },
      shellMain: rect(".shellMain"),
      catalog: rect(".catalogPanel"),
      listPanel: rect(".listPanel"),
      listPanelBody: rect(".listPanelBody"),
      editorWorkspaceVertical: workspaceRect,
      builderSide: rect(".editorBuilderSide"),
      builderCollapsed: document.querySelector(".editorWorkspaceVertical")?.classList.contains("editorWorkspaceBuilderCollapsed") ?? false,
      builderToggle: rect(".scenarioBuilderPanel .builderToggle"),
      yamlSide: rect(".editorYamlSide"),
      yamlTextarea: rect(".editorYamlSide textarea"),
      codeEditorShell: shellRect,
      yamlWorkspaceHeightDelta: workspaceRect && shellRect ? Math.abs(workspaceRect.height - shellRect.height) : null,
      lineNumberGutter: rect(".lineNumberGutter"),
      scenarioBuilderLayout: rect(".scenarioBuilderVerticalLayout"),
      builderStepperRail: rect(".builderStepperRail"),
      builderStepDetail: rect(".builderStepDetail"),
      runLayout: rect(".runGrid"),
      runGridColumns: runGrid ? getComputedStyle(runGrid).gridTemplateColumns.split(" ").filter(Boolean).length : 0,
      runPanels,
      runPanelInternalYScroll: runPanels.some((panel) => panel.internalYScroll),
      runPanelContentOverflow: runPanels.some((panel) => panel.contentOverflow),
      runConsole: rect(".runGrid .console"),
      labGrid: rect(".labGrid"),
      labStatusOverflow: statusCells.some(Boolean),
      resultLayout: rect(".resultsGrid"),
      stepperCount: all(".builderStepperRail button").length,
      stepButtonSizes: stepButtons,
      stepButtonWidthDelta: stepWidths.length ? Math.max(...stepWidths) - Math.min(...stepWidths) : 0,
      stepButtonHeightDelta: stepHeights.length ? Math.max(...stepHeights) - Math.min(...stepHeights) : 0,
      stepButtonGapMax: stepGapMax,
      builderHasInternalYScroll: all(".editorBuilderSide .builderStepDetail, .editorBuilderSide .builderList, .editorBuilderSide .scenarioBuilderPanel").some((element) => element.scrollHeight > element.clientHeight + 1 && getComputedStyle(element).overflowY !== "visible"),
      builderHeightDelta: workspaceRect && rect(".editorBuilderSide") ? Math.abs(workspaceRect.height - rect(".editorBuilderSide").height) : null,
      listRowHeightMin: listRows.length ? Math.min(...listRows.map((row) => row.rowHeight)) : 0,
      listRowTextClipped: listRows.some((row) => !row.titleVisible || !row.pathVisible),
      productStepOverflow: all(".productStepRow").some((row) => row.scrollWidth > row.clientWidth + 1),
      assertionOverflow: all(".assertionRow").some((row) => row.scrollWidth > row.clientWidth + 1),
      builderRowOverflow: all(".editorBuilderSide .builderListRow").some((row) => row.scrollWidth > row.clientWidth + 1),
      editorListCollapsed: document.querySelector(".listPanel")?.classList.contains("collapsed") ?? false,
    };
  });
}

test("viewport design matrix captures core dashboard surfaces", async ({ page }) => {
  test.setTimeout(180000);
  const consoleErrors = [];
  const pageErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(String(error)));

  await login(page);
  const results = [];

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    await openScenarioBuilder(page);
    await page.screenshot({
      path: path.join(outDir, `viewport-matrix-${viewport.name}-scenario.png`),
      fullPage: false,
    });
    results.push({
      viewport,
      screen: "scenario",
      screenshot: `output/web-dashboard/viewport-matrix-${viewport.name}-scenario.png`,
      metrics: await collectMetrics(page),
    });

    const builderCollapseButton = page.locator(".scenarioBuilderPanel .builderToggle[aria-expanded='true']").first();
    if (await builderCollapseButton.count()) {
      await builderCollapseButton.click();
      await page.waitForTimeout(250);
      const builderCollapsedMetrics = await collectMetrics(page);
      if (!builderCollapsedMetrics.builderCollapsed) {
        throw new Error(`Scenario builder did not enter collapsed layout at ${viewport.name}`);
      }
      if (viewport.width > 900 && builderCollapsedMetrics.builderSide?.width > 70) {
        throw new Error(`Scenario builder collapsed rail is too wide at ${viewport.name}: ${builderCollapsedMetrics.builderSide?.width}px`);
      }
      if (viewport.width <= 900 && builderCollapsedMetrics.editorWorkspaceVertical && builderCollapsedMetrics.builderSide && builderCollapsedMetrics.builderSide.width < builderCollapsedMetrics.editorWorkspaceVertical.width - 2) {
        throw new Error(`Scenario builder collapsed mobile bar does not use full width at ${viewport.name}`);
      }
      await page.screenshot({
        path: path.join(outDir, `viewport-matrix-${viewport.name}-scenario-builder-collapsed.png`),
        fullPage: false,
      });
      results.push({
        viewport,
        screen: "scenario-builder-collapsed",
        screenshot: `output/web-dashboard/viewport-matrix-${viewport.name}-scenario-builder-collapsed.png`,
        metrics: builderCollapsedMetrics,
      });
      const builderExpandButton = page.locator(".scenarioBuilderPanel .builderToggle[aria-expanded='false']").first();
      if (await builderExpandButton.count()) {
        await builderExpandButton.click();
        await page.waitForTimeout(250);
      }
    }

    const collapseButton = page.locator(".listPanel .iconButton[aria-expanded='true']").first();
    if (await collapseButton.count()) {
      await collapseButton.click();
      await page.waitForTimeout(250);
      await page.screenshot({
        path: path.join(outDir, `viewport-matrix-${viewport.name}-scenario-collapsed.png`),
        fullPage: false,
      });
      results.push({
        viewport,
        screen: "scenario-collapsed",
        screenshot: `output/web-dashboard/viewport-matrix-${viewport.name}-scenario-collapsed.png`,
        metrics: await collectMetrics(page),
      });
    }

    await go(page, "실행");
    await page.screenshot({
      path: path.join(outDir, `viewport-matrix-${viewport.name}-run.png`),
      fullPage: false,
    });
    results.push({
      viewport,
      screen: "run",
      screenshot: `output/web-dashboard/viewport-matrix-${viewport.name}-run.png`,
      metrics: await collectMetrics(page),
    });
    const runMetrics = results[results.length - 1].metrics;
    if (runMetrics.document.horizontalOverflow) {
      throw new Error(`Run layout has horizontal overflow at ${viewport.name}`);
    }
    if (viewport.width <= 1280 && runMetrics.runGridColumns !== 1) {
      throw new Error(`Run layout should collapse to one column at ${viewport.name}, got ${runMetrics.runGridColumns}`);
    }
    if (viewport.width <= 1280 && runMetrics.runPanelInternalYScroll) {
      throw new Error(`Run settings panel should use page flow instead of internal vertical scroll at ${viewport.name}`);
    }
    if (viewport.width <= 1280 && runMetrics.runPanelContentOverflow) {
      throw new Error(`Run settings panel content should be contained by its card at ${viewport.name}`);
    }
    if (runMetrics.labStatusOverflow) {
      throw new Error(`Lab status cells overflow at ${viewport.name}`);
    }

    await go(page, "결과");
    await page.screenshot({
      path: path.join(outDir, `viewport-matrix-${viewport.name}-results.png`),
      fullPage: false,
    });
    results.push({
      viewport,
      screen: "results",
      screenshot: `output/web-dashboard/viewport-matrix-${viewport.name}-results.png`,
      metrics: await collectMetrics(page),
    });
  }

  const report = {
    ok: consoleErrors.length === 0 && pageErrors.length === 0,
    checkedAt: new Date().toISOString(),
    baseUrl,
    viewports,
    consoleErrors,
    pageErrors,
    results,
  };
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(
    path.join(outDir, "viewport-design-matrix-smoke.json"),
    JSON.stringify(report, null, 2),
  );
});
