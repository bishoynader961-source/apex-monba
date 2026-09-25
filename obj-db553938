const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (e) {
    console.log("Playwright launch failed.");
    console.error(e);
    process.exit(1);
  }
  const context = await browser.newContext();
  const page = await context.newPage();
  
  const logs = [];
  page.on('console', msg => logs.push('[Console ' + msg.type() + '] ' + msg.text()));
  page.on('pageerror', error => logs.push('[PageError] ' + error.message));
  page.on('requestfailed', request => logs.push('[RequestFailed] ' + request.url() + ' ' + request.failure().errorText));

  try {
    await page.goto('http://localhost:3000/dashboard/label-engine', { waitUntil: 'networkidle' });
    
    if (page.url().includes('login') || page.url() === 'http://localhost:3000/') {
      logs.push("Logging in...");
      await page.fill('input[type="text"]', 'admin');
      await page.fill('input[type="password"]', 'admin123');
      await page.click('button[type="submit"]');
      await page.waitForURL('**/dashboard/label-engine', { timeout: 10000 }).catch(e => logs.push("Wait for URL failed: " + e.message));
      await page.goto('http://localhost:3000/dashboard/label-engine', { waitUntil: 'networkidle' });
    }

    logs.push("--- Testing Export PNG ---");
    try {
      await page.click('button:has-text("Export PNG")', { timeout: 5000 });
      await page.waitForTimeout(1000);
    } catch(e) { logs.push('Export PNG Click Failed: ' + e.message); }

    logs.push("--- Testing Print ---");
    try {
      await page.click('button:has-text("Print")', { timeout: 5000 });
      await page.waitForTimeout(1000);
    } catch(e) { logs.push('Print Click Failed: ' + e.message); }

    logs.push("--- Testing Open Standalone ---");
    try {
      await page.click('button:has-text("Open Standalone")', { timeout: 5000 });
      await page.waitForTimeout(1000);
    } catch(e) { logs.push('Open Standalone Click Failed: ' + e.message); }

    logs.push("--- Testing Save Tpl ---");
    try {
      await page.fill('input[placeholder="Template name"]', 'test_template');
      await page.click('button:has-text("Save Tpl")', { timeout: 5000 });
      await page.waitForTimeout(1000);
    } catch(e) { logs.push('Save Tpl Click Failed: ' + e.message); }

  } catch(e) {
    logs.push('Script Error: ' + e.message);
  }

  await browser.close();
  fs.writeFileSync('playwright_logs.txt', logs.join('\n'));
})();
