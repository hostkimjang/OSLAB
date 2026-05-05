/**
 * Persistent visible browser for live verification.
 * Runs headed, navigates to dashboard, logs in, waits forever so user can verify.
 * Stop with Ctrl+C in terminal or close browser window.
 */
const { chromium } = require("@playwright/test");

const BASE = "http://127.0.0.1:3000";

(async () => {
  // headless: false = real GUI window. slowMo helps user see actions.
  // args ensures window appears on screen and is focused.
  const browser = await chromium.launch({
    headless: false,
    slowMo: 250,
    args: [
      "--start-maximized",
      "--disable-blink-features=AutomationControlled",
    ],
  });
  const context = await browser.newContext({ viewport: null });
  const page = await context.newPage();

  console.log("[OK] Browser window opened. Navigating to dashboard...");
  await page.goto(BASE);
  await page.waitForTimeout(1500);

  // Auto-login so user lands on dashboard
  try {
    const userInput = page.locator('input[autocomplete="username"]');
    if (await userInput.isVisible({ timeout: 3000 })) {
      await userInput.fill("admin");
      await page.locator('input[type="password"]').fill("oslab2026");
      await page.locator('button[type="submit"]').click();
      console.log("[OK] Logged in.");
      await page.waitForTimeout(2000);
    }
  } catch (e) {
    console.log("[WARN] Login skipped:", e.message.split("\n")[0]);
  }

  console.log("\n=========================================");
  console.log(" Browser is OPEN. Use it to verify fixes.");
  console.log(" Reload pages with F5 to see live changes.");
  console.log(" Close the browser window or Ctrl+C to exit.");
  console.log("=========================================\n");

  // Keep alive until window is closed
  await new Promise((resolve) => {
    page.on("close", resolve);
    browser.on("disconnected", resolve);
  });
  console.log("[OK] Browser closed.");
})();
