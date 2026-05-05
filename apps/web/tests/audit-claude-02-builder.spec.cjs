const { chromium } = require("@playwright/test");
const path = require("path");
const OUT = path.join(__dirname, "../../../output/web-dashboard");
const BASE = "http://127.0.0.1:3000";

async function login(page) {
  await page.goto(BASE);
  await page.waitForTimeout(1500);
  await page.locator('input[autocomplete="username"]').fill("admin");
  await page.locator('input[type="password"]').fill("oslab2026");
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(2000);
}

async function clickNav(page, exact) {
  const links = await page.locator("nav a, aside a, aside button, [class*='nav'] a, [class*='sidebar'] a").all();
  for (const link of links) {
    const text = (await link.textContent() || "").trim();
    if (text === exact) { await link.click(); return true; }
  }
  // fallback: partial text
  await page.locator(`a:has-text("${exact}"), button:has-text("${exact}")`).first().click({ timeout: 4000 });
  return true;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1366, height: 768 });
  await login(page);

  // 1. Scenario list → select demo-powershell-system
  await clickNav(page, "시나리오");
  await page.waitForTimeout(800);
  try {
    await page.locator("text=demo-powershell-system").first().click({ timeout: 3000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(OUT, "11-scenario-selected.png"), fullPage: true });
    console.log("11-scenario-selected.png captured");
  } catch(e) { console.log("SKIP 11:", e.message.split('\n')[0]); }

  // 2. Click 수정 button to enter edit mode
  try {
    const editBtn = page.locator('button:has-text("수정"), button:has-text("편집")').first();
    if (await editBtn.isVisible({ timeout: 2000 })) {
      await editBtn.click();
      await page.waitForTimeout(1200);
      await page.screenshot({ path: path.join(OUT, "12-scenario-edit-mode.png"), fullPage: true });
      console.log("12-scenario-edit-mode.png captured");
    } else {
      console.log("SKIP 12: edit button not visible");
    }
  } catch(e) { console.log("SKIP 12:", e.message.split('\n')[0]); }

  // 3. Run tab (exact match "실행")
  try {
    await clickNav(page, "실행");
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(OUT, "13-run-tab.png"), fullPage: true });
    console.log("13-run-tab.png captured");
  } catch(e) { console.log("SKIP 13:", e.message.split('\n')[0]); }

  // 4. Suite builder - new suite or existing
  try {
    await clickNav(page, "실행 묶음(Suite)");
    await page.waitForTimeout(800);
    // Click "새 실행 묶음" to create one
    await page.locator('button:has-text("새 실행 묶음")').click({ timeout: 2000 });
    await page.waitForTimeout(1200);
    await page.screenshot({ path: path.join(OUT, "14-suite-new.png"), fullPage: true });
    console.log("14-suite-new.png captured");
    // Open visual builder
    const builderBtn = page.locator('button:has-text("빌더 열기")');
    if (await builderBtn.isVisible({ timeout: 2000 })) {
      await builderBtn.click();
      await page.waitForTimeout(1200);
      await page.screenshot({ path: path.join(OUT, "15-suite-builder.png"), fullPage: true });
      console.log("15-suite-builder.png captured");
    }
  } catch(e) { console.log("SKIP 14/15:", e.message.split('\n')[0]); }

  // 5. Mobile
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.screenshot({ path: path.join(OUT, "16-mobile-dashboard.png"), fullPage: true });
  console.log("16-mobile-dashboard.png captured");

  // Mobile scenarios
  try {
    await clickNav(page, "시나리오");
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(OUT, "17-mobile-scenarios.png"), fullPage: true });
    console.log("17-mobile-scenarios.png captured");
  } catch(e) { console.log("SKIP 17:", e.message.split('\n')[0]); }

  await browser.close();
  console.log("Done.");
})();
