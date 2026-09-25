import { test, expect } from '../fixtures/packaged-app';

test.describe('Debug Inventory Page JS Errors', () => {
  test.beforeEach(async ({ page }) => {
    // Check if already logged in
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded', { timeout: 60000 });
    
    const isLoginPage = await page.locator('input[name="username"], input[type="text"]').first().isVisible({ timeout: 5000 }).catch(() => false);
    
    if (isLoginPage) {
      await page.goto('/login');
      await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
      await page.fill('input[name="username"], input[type="text"]', 'admin');
      await page.fill('input[name="password"], input[type="password"]', 'admin123');
      await page.click('button[type="submit"], button:has-text("Sign In")');
      await page.waitForURL('**/dashboard', { timeout: 60000 });
      await page.waitForTimeout(2000);
    }
  });

  test('Check for JavaScript errors on Inventory page', async ({ page }) => {
    const jsErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        jsErrors.push(msg.text());
      }
    });
    page.on('pageerror', error => {
      jsErrors.push(error.message);
    });

    console.log('Navigating to /dashboard/inventory...');
    await page.goto('/dashboard/inventory');
    await page.waitForLoadState('domcontentloaded', { timeout: 60000 });
    await page.waitForTimeout(10000);
    
    // Take screenshot
    await page.screenshot({ path: 'test-results/inventory-js-debug.png', fullPage: true });
    
    console.log('JavaScript errors:', jsErrors);
    
    // Check page content
    const bodyText = (await page.textContent('body').catch(() => '')) || '';
    
    // Check for any visible content
    const visibleText = await page.evaluate(() => document.body.innerText);
    console.log('Visible text length:', visibleText.length);
    console.log('Visible text preview:', visibleText.substring(0, 500));
  });
});