// Browser audit script - captures screenshots of all major screens
const { chromium } = require("@playwright/test");
const path = require("path");
const fs = require("fs");

const BASE = "http://127.0.0.1:3000";
const OUT = path.join(__dirname, "../../../output/web-dashboard");

async function login(page) {
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(1500);
  await page.locator('input[autocomplete="username"]').fill("admin");
  await page.locator('input[type="password"]').fill("oslab2026");
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(2000);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1366, height: 768 });

  // 1. Login screen
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT, "01-login.png"), fullPage: true });
  console.log("01-login.png captured");

  // Login
  await login(page);
  await page.screenshot({ path: path.join(OUT, "02-dashboard-home.png"), fullPage: true });
  console.log("02-dashboard-home.png captured");

  // 3. Click through sidebar nav items (Korean labels)
  const navItems = [
    { label: "시나리오", file: "03-scenarios-tab.png" },
    { label: "환경 준비(Fixture)", file: "04-fixtures-tab.png" },
    { label: "실행 묶음(Suite)", file: "05-suites-tab.png" },
    { label: "아티팩트", file: "06-artifacts-tab.png" },
    { label: "실행", file: "07-run-tab.png" },
    { label: "결과", file: "08-results-tab.png" },
  ];

  for (const nav of navItems) {
    try {
      const btn = page.locator(`nav a:has-text("${nav.label}"), aside a:has-text("${nav.label}"), button:has-text("${nav.label}"), a:has-text("${nav.label}")`).first();
      await btn.click({ timeout: 5000 });
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT, nav.file), fullPage: true });
      console.log(`${nav.file} captured`);
    } catch (e) {
      console.log(`SKIP ${nav.file}: ${e.message.split('\n')[0]}`);
    }
  }

  // 9. Scenario builder - click first scenario in list
  try {
    const scenarioNav = page.locator('a:has-text("시나리오"), button:has-text("시나리오")').first();
    await scenarioNav.click({ timeout: 5000 });
    await page.waitForTimeout(1000);
    // Look for any list item or card that can be clicked
    const firstItem = page.locator('li, [role="listitem"], .card, [data-testid]').first();
    if (await firstItem.isVisible({ timeout: 3000 })) {
      await firstItem.click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT, "09-scenario-builder.png"), fullPage: true });
      console.log("09-scenario-builder.png captured");
    }
  } catch (e) {
    console.log(`SKIP 09-scenario-builder: ${e.message.split('\n')[0]}`);
  }

  // 10. Mobile viewport
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(1000);
  await login(page);
  await page.screenshot({ path: path.join(OUT, "10-mobile-home.png"), fullPage: true });
  console.log("10-mobile-home.png captured");

  await browser.close();
  console.log("\nAll screenshots saved to:", OUT);
})();
