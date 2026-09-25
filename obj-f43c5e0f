import { test, expect } from '../fixtures/packaged-app';

test.describe('Debug Inventory Page', () => {
  test.beforeEach(async ({ page }) => {
    // Check if already logged in
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded', { timeout: 60000 });
    
    const isLoginPage = await page.locator('input[name="username"], input[type="text"]').first().isVisible({ timeout: 5000 }).catch(() => false);
    
    if (isLoginPage) {
      await page.goto('/login');
      await page.waitForLoadState('domcontentloaded', { timeout: 60000 });
      await page.fill('input[name="username"], input[type="text"]', 'admin');
      await page.fill('input[name="password"], input[type="password"]', 'admin123');
      await page.click('button[type="submit"], button:has-text("Sign In")');
      await page.waitForURL('**/dashboard', { timeout: 60000 });
      await page.waitForTimeout(2000);
    }
  });

  test('Inventory page loads and shows table', async ({ page }) => {
    console.log('Navigating to /dashboard/inventory...');
    await page.goto('/dashboard/inventory');
    await page.waitForLoadState('domcontentloaded', { timeout: 60000 });
    await page.waitForTimeout(5000);
    
    // Take screenshot for debugging
    await page.screenshot({ path: 'test-results/inventory-debug.png', fullPage: true });
    
    // Check what's on the page
    const bodyText = (await page.textContent('body').catch(() => '')) || '';
    console.log('Body text length:', bodyText.length);
    console.log('Body text preview:', bodyText.substring(0, 1000));
    
    // Check if license validation page is shown
    const isLicensePage = await page.locator('text=License Validation').first().isVisible({ timeout: 5000 }).catch(() => false);
    
    if (isLicensePage) {
      console.log('License validation page detected - skipping table check (valid license required)');
      return;
    }
    
    // Check for table
    const table = page.locator('table');
    await expect(table).toBeVisible({ timeout: 10000 });
    
    // Check for header buttons
    const buttons = await page.locator('button').allTextContents();
    console.log('Buttons found:', buttons);
    
    // Check for tabs
    const tabs = await page.locator('button[role="tab"], .tab-button, [role="tab"]').allTextContents();
    console.log('Tabs found:', tabs);
  });
});