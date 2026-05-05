/**
 * Verify the fixes applied in this sprint.
 * Captures: login error i18n, validate banner i18n, command template wrapping,
 * assertion type dropdown, YAML apply status indicator, read-only badge as button.
 */
const { chromium } = require("@playwright/test");
const path = require("path");
const fs = require("fs");

const BASE = "http://127.0.0.1:3000";
const OUT = path.join(__dirname, "../../../output/web-dashboard/verify");
fs.mkdirSync(OUT, { recursive: true });

let n = 0;
async function shot(page, label) {
  n++;
  const file = path.join(OUT, `${String(n).padStart(2, "0")}-${label}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`[${n}] ${label}`);
}

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 350, args: ["--start-maximized"] });
  const context = await browser.newContext({ viewport: null });
  const page = await context.newPage();

  // 1. Login error in Korean
  await page.goto(BASE);
  await page.waitForTimeout(1500);
  await page.locator('input[autocomplete="username"]').fill("wrong");
  await page.locator('input[type="password"]').fill("wrong");
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(1500);
  await shot(page, "01-login-error-korean");

  // 2. Login OK
  await page.locator('input[autocomplete="username"]').fill("admin");
  await page.locator('input[type="password"]').fill("oslab2026");
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(2000);

  // 3. Read-only badge / clickable
  const navLinks = await page.locator("nav a, aside a, aside button").all();
  for (const link of navLinks) {
    const text = (await link.textContent() || "").trim();
    if (text === "시나리오") { await link.click(); break; }
  }
  await page.waitForTimeout(800);
  await page.locator("text=demo-powershell-system").first().click();
  await page.waitForTimeout(1200);
  await shot(page, "02-readonly-badge-clickable");

  // 4. Validate banner Korean
  await page.locator('button:has-text("검증")').click();
  await page.waitForTimeout(2000);
  await shot(page, "03-validate-banner-korean");

  // 5. Click on read-only badge to enter edit mode
  await page.locator('button.editorModeReadOnly').click().catch(() => {});
  await page.waitForTimeout(1200);
  await shot(page, "04-edit-mode-via-badge");

  // 6. Assertion editor — step 5 — dropdown
  const stepBtns = await page.locator('button[class*="builderStepNav"], .builderStep').all();
  for (const b of stepBtns) {
    const t = (await b.textContent() || "").trim();
    if (t.startsWith("5") || t === "5") { await b.click(); break; }
  }
  // fallback: click step button by text "5"
  await page.locator('button:has-text("5")').first().click({ timeout: 3000 }).catch(() => {});
  await page.waitForTimeout(1000);
  await shot(page, "05-assertion-step5");

  // Click the assertion type select
  try {
    const typeSelect = page.locator('select').filter({ hasText: 'command.exitCode' }).first();
    if (await typeSelect.isVisible({ timeout: 1500 })) {
      await typeSelect.click();
      await page.waitForTimeout(500);
      await shot(page, "06-assertion-type-dropdown");
    }
  } catch(e) {}

  // 7. YAML 적용 status indicator — step 4 (command overflow check)
  await page.locator('button:has-text("4")').first().click({ timeout: 3000 }).catch(() => {});
  await page.waitForTimeout(1000);
  await shot(page, "07-step4-command-no-overflow");

  // 8. Modify a field to trigger dirty state
  try {
    const nameInput = page.locator('input').filter({ hasText: '' }).nth(1);
    // Use a more specific selector — the artifact command shell select
    await page.locator('button:has-text("1")').first().click().catch(()=>{});
    await page.waitForTimeout(800);
    const idInput = page.locator('input[value*="demo.powershell"]').first();
    if (await idInput.isVisible({ timeout: 1500 })) {
      await idInput.fill("demo.powershell-system.windows.modified");
      await page.waitForTimeout(300);
      await shot(page, "08-builder-dirty-pending");
      await page.waitForTimeout(900); // wait for auto-apply (600ms)
      await shot(page, "09-builder-after-auto-apply");
    }
  } catch(e) { console.log("dirty test:", e.message.split('\n')[0]); }

  console.log("\nKeep browser open. Close window or Ctrl+C to exit.");
  await new Promise((resolve) => {
    page.on("close", resolve);
    browser.on("disconnected", resolve);
  });
})();
