/**
 * Full UX/Usability QA - headed browser, slow motion
 * Tests every major flow from a fresh-user perspective
 */
const { chromium } = require("@playwright/test");
const path = require("path");
const fs = require("fs");

const BASE = "http://127.0.0.1:3000";
const OUT = path.join(__dirname, "../../../output/web-dashboard/ux-qa");
fs.mkdirSync(OUT, { recursive: true });

let shotIdx = 0;
async function shot(page, label) {
  shotIdx++;
  const file = path.join(OUT, `${String(shotIdx).padStart(3, "0")}-${label}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`[${shotIdx}] ${label}`);
  return file;
}

async function clickNav(page, exact) {
  const links = await page.locator("nav a, aside a, aside button").all();
  for (const link of links) {
    const text = (await link.textContent() || "").trim();
    if (text === exact) { await link.click(); await page.waitForTimeout(800); return; }
  }
  await page.locator(`a:has-text("${exact}"), button:has-text("${exact}")`).first().click();
  await page.waitForTimeout(800);
}

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 300 });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });

  // ─────────────────────────────────────────────────────────
  // 1. FIRST IMPRESSION: Login Page
  // ─────────────────────────────────────────────────────────
  await page.goto(BASE);
  await page.waitForTimeout(1000);
  await shot(page, "login-first-impression");

  // Try wrong credentials first (user experience test)
  await page.locator('input[autocomplete="username"]').fill("wrong");
  await page.locator('input[type="password"]').fill("wrong");
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(1200);
  await shot(page, "login-wrong-credentials-feedback");

  // Correct login
  await page.locator('input[autocomplete="username"]').fill("admin");
  await page.locator('input[type="password"]').fill("oslab2026");
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(2000);
  await shot(page, "dashboard-after-login");

  // ─────────────────────────────────────────────────────────
  // 2. DASHBOARD HOME: Lab status UX
  // ─────────────────────────────────────────────────────────
  await shot(page, "dashboard-lab-status-panel");

  // Click the info icon on lab status
  try {
    await page.locator('[class*="labStatus"] button, [class*="info"]').first().click({ timeout: 2000 });
    await page.waitForTimeout(600);
    await shot(page, "dashboard-lab-status-info-click");
  } catch(e) {}

  // Click the "..." menu on lab status
  try {
    const menuBtn = page.locator('button:has-text("..."), button[aria-label*="menu"]').first();
    if (await menuBtn.isVisible({ timeout: 1000 })) {
      await menuBtn.click();
      await page.waitForTimeout(600);
      await shot(page, "dashboard-lab-status-menu");
      await page.keyboard.press("Escape");
    }
  } catch(e) {}

  // Switch to EN language
  await page.locator('button:has-text("EN")').click();
  await page.waitForTimeout(800);
  await shot(page, "dashboard-english-mode");
  await page.locator('button:has-text("KO")').click();
  await page.waitForTimeout(800);

  // ─────────────────────────────────────────────────────────
  // 3. SCENARIO: Browse and read
  // ─────────────────────────────────────────────────────────
  await clickNav(page, "시나리오");
  await shot(page, "scenario-list-empty-selection");

  // Click first scenario
  await page.locator("text=demo-powershell-system").first().click();
  await page.waitForTimeout(1000);
  await shot(page, "scenario-read-only-view");

  // Click 검증 button
  try {
    await page.locator('button:has-text("검증")').click();
    await page.waitForTimeout(1500);
    await shot(page, "scenario-validation-result");
  } catch(e) { console.log("validation btn:", e.message.split('\n')[0]); }

  // Click 수정 button → enter edit mode
  await page.locator('button:has-text("수정")').click();
  await page.waitForTimeout(1000);
  await shot(page, "scenario-builder-step1-vm");

  // Explore each step tab of the builder
  const steps = ["2", "3", "4", "5", "6"];
  for (const step of steps) {
    try {
      await page.locator(`button:has-text("${step}"), [class*="step"]:has-text("${step}")`).first().click({ timeout: 2000 });
      await page.waitForTimeout(800);
      await shot(page, `scenario-builder-step${step}`);
    } catch(e) {
      console.log(`step ${step}:`, e.message.split('\n')[0]);
    }
  }

  // Go back to step 1 and scroll down
  await page.locator('button:has-text("1"), [class*="step"]:has-text("1")').first().click({ timeout: 2000 }).catch(()=>{});
  await page.waitForTimeout(600);
  await page.evaluate(() => { const el = document.querySelector('[class*="builder"], [class*="Builder"]'); if(el) el.scrollTop = 400; });
  await page.waitForTimeout(500);
  await shot(page, "scenario-builder-step1-scrolled");

  // Click 취소 (cancel edit)
  try {
    await page.locator('button:has-text("취소")').click();
    await page.waitForTimeout(600);
    await shot(page, "scenario-after-cancel");
  } catch(e) {}

  // ─────────────────────────────────────────────────────────
  // 4. SCENARIO: Create new scenario flow
  // ─────────────────────────────────────────────────────────
  await page.locator('button:has-text("새 시나리오")').click();
  await page.waitForTimeout(1000);
  await shot(page, "new-scenario-dialog");

  // Fill in basic info if dialog appears
  try {
    const idInput = page.locator('input[placeholder*="id"], input[placeholder*="ID"]').first();
    if (await idInput.isVisible({ timeout: 1500 })) {
      await idInput.fill("demo.qa-test.windows");
      await page.waitForTimeout(300);
      await shot(page, "new-scenario-filled-id");
    }
    // Close/cancel dialog
    const cancelBtn = page.locator('button:has-text("취소"), button:has-text("닫기"), button:has-text("X")').first();
    if (await cancelBtn.isVisible({ timeout: 1000 })) {
      await cancelBtn.click();
      await page.waitForTimeout(500);
    } else {
      await page.keyboard.press("Escape");
    }
  } catch(e) {}

  // ─────────────────────────────────────────────────────────
  // 5. FIXTURE: Browse and edit
  // ─────────────────────────────────────────────────────────
  await clickNav(page, "환경 준비(Fixture)");
  await shot(page, "fixture-list");

  await page.locator("text=demo-python-runtime.ps1").first().click({ timeout: 3000 }).catch(()=>{});
  await page.waitForTimeout(800);
  await shot(page, "fixture-selected-view");

  // New fixture
  try {
    await page.locator('button:has-text("새 환경 준비")').click({ timeout: 2000 });
    await page.waitForTimeout(800);
    await shot(page, "new-fixture-dialog");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
  } catch(e) {}

  // ─────────────────────────────────────────────────────────
  // 6. SUITE: Create a suite
  // ─────────────────────────────────────────────────────────
  await clickNav(page, "실행 묶음(Suite)");
  await shot(page, "suite-list-empty");

  await page.locator('button:has-text("새 실행 묶음")').click({ timeout: 3000 });
  await page.waitForTimeout(1000);
  await shot(page, "suite-create-modal-step1");

  // Check template dropdown
  try {
    await page.locator('select, [role="combobox"]').first().click({ timeout: 1000 });
    await page.waitForTimeout(400);
    await shot(page, "suite-template-dropdown-open");
    await page.keyboard.press("Escape");
  } catch(e) {}

  // Select some scenarios
  try {
    const checkboxes = await page.locator('input[type="checkbox"]').all();
    if (checkboxes.length > 0) {
      await checkboxes[0].check();
      await page.waitForTimeout(300);
      if (checkboxes.length > 1) await checkboxes[1].check();
      await page.waitForTimeout(300);
      await shot(page, "suite-scenarios-selected");
    }

    // Next step
    const nextBtn = page.locator('button:has-text("다음"), button:has-text("Next")').first();
    if (await nextBtn.isVisible({ timeout: 1000 })) {
      await nextBtn.click();
      await page.waitForTimeout(800);
      await shot(page, "suite-create-step2");
    }
  } catch(e) { console.log("suite steps:", e.message.split('\n')[0]); }

  await page.keyboard.press("Escape");
  await page.waitForTimeout(500);

  // ─────────────────────────────────────────────────────────
  // 7. ARTIFACTS: Studio UX
  // ─────────────────────────────────────────────────────────
  await clickNav(page, "아티팩트");
  await shot(page, "artifact-studio-overview");

  // Filter by type
  try {
    const typeFilter = page.locator('select').first();
    await typeFilter.selectOption({ index: 1 });
    await page.waitForTimeout(600);
    await shot(page, "artifact-filter-applied");
    await typeFilter.selectOption({ index: 0 });
  } catch(e) {}

  // Click each artifact
  const artifactItems = await page.locator('[class*="artifact"] li, [class*="list"] li').all();
  if (artifactItems.length > 1) {
    await artifactItems[1].click();
    await page.waitForTimeout(600);
    await shot(page, "artifact-second-item-selected");
  }

  // New artifact button
  try {
    await page.locator('button:has-text("새 아티팩트 제작")').click({ timeout: 2000 });
    await page.waitForTimeout(800);
    await shot(page, "new-artifact-dialog");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
  } catch(e) {}

  // ─────────────────────────────────────────────────────────
  // 8. RUN: Full 5-step flow
  // ─────────────────────────────────────────────────────────
  await clickNav(page, "실행");
  await shot(page, "run-tab-overview");

  // Scroll down to see 5 steps
  await page.evaluate(() => window.scrollTo(0, 300));
  await page.waitForTimeout(400);
  await shot(page, "run-tab-steps-visible");

  // Step 1: Select scenario
  try {
    // Select demo-powershell-system
    const scenarioPicker = page.locator('select, [role="combobox"]').nth(1);
    if (await scenarioPicker.isVisible({ timeout: 1500 })) {
      await scenarioPicker.click();
      await page.waitForTimeout(400);
      await shot(page, "run-step1-scenario-dropdown");
      // Select powershell demo
      await page.locator('option:has-text("demo-powershell"), [role="option"]:has-text("demo-powershell")').first().click({ timeout: 1000 }).catch(()=>{});
      await page.waitForTimeout(400);
    }
  } catch(e) { console.log("run step1:", e.message.split('\n')[0]); }

  // Step navigation buttons
  const stepBtns = ["2", "3", "4", "5"];
  for (const s of stepBtns) {
    try {
      await page.locator(`[class*="step"]:has-text("${s}"), button[class*="step${s}"]`).first().click({ timeout: 1500 });
      await page.waitForTimeout(600);
      await shot(page, `run-step${s}`);
    } catch(e) { console.log(`run step ${s}:`, e.message.split('\n')[0]); }
  }

  // Try the run button
  try {
    const runBtn = page.locator('button:has-text("run"), button:has-text("실행"), button:has-text("시작")').last();
    if (await runBtn.isVisible({ timeout: 1500 })) {
      await shot(page, "run-before-launch");
    }
  } catch(e) {}

  // ─────────────────────────────────────────────────────────
  // 9. RESULTS: Empty state & filters
  // ─────────────────────────────────────────────────────────
  await clickNav(page, "결과");
  await shot(page, "results-empty-state");

  // Test all filter tabs
  const filterTabs = ["실패", "성공", "진행 중", "멈춤"];
  for (const tab of filterTabs) {
    try {
      await page.locator(`button:has-text("${tab}")`).click({ timeout: 1500 });
      await page.waitForTimeout(400);
      await shot(page, `results-filter-${tab}`);
    } catch(e) {}
  }

  // ─────────────────────────────────────────────────────────
  // 10. RESPONSIVE: narrow viewport
  // ─────────────────────────────────────────────────────────
  await page.setViewportSize({ width: 1024, height: 768 });
  await clickNav(page, "대시보드");
  await page.waitForTimeout(600);
  await shot(page, "responsive-1024-dashboard");

  await page.setViewportSize({ width: 768, height: 1024 });
  await page.waitForTimeout(600);
  await shot(page, "responsive-768-dashboard");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(600);
  await shot(page, "responsive-mobile-390");
  await clickNav(page, "시나리오").catch(()=>{});
  await page.waitForTimeout(600);
  await shot(page, "responsive-mobile-scenarios");

  await browser.close();
  console.log(`\nDone. ${shotIdx} screenshots saved to:\n${OUT}`);
})();
