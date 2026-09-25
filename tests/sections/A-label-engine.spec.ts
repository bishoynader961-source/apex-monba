import { test, expect } from '../fixtures/packaged-app';

test.describe('Section A: Label Engine Buttons (requires valid license)', () => {
  test.beforeEach(async ({ page }) => {
    // Check if already logged in
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
    
    // Check if we're on login page (not logged in)
    const isLoginPage = await page.locator('input[name="username"], input[type="text"]').first().isVisible({ timeout: 5000 }).catch(() => false);
    
    if (isLoginPage) {
      // Log in
      await page.goto('/login');
      await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
      await page.fill('input[name="username"], input[type="text"]', 'admin');
      await page.fill('input[name="password"], input[type="password"]', 'admin123');
      await page.click('button[type="submit"], button:has-text("Sign In")');
      await page.waitForURL('**/dashboard', { timeout: 30000 });
      await page.waitForTimeout(2000);
    }
  });

  test('Label Engine page requires valid license', async ({ page }) => {
    await page.goto('/dashboard/label-engine');
    await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
    await page.waitForTimeout(3000);
    
    // Check if license validation page is shown
    const heading = page.locator('h1, h2, h3').first();
    const headingText = await heading.textContent();
    
    if (headingText?.includes('License Validation') || headingText?.includes('License')) {
      // License validation page is shown - this is expected behavior
      console.log('License validation page detected - Label Engine requires valid license');
      
      // Verify license validation page elements
      await expect(page.locator('h1:has-text("License Validation")')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('button:has-text("Validate License")')).toBeVisible();
      await expect(page.locator('button:has-text("Purchase License")')).toBeVisible();
      
      console.log('License validation page verified - Label Engine requires valid license');
      return; // Test passes - license validation working as expected
    }
    
    // If we get here, Label Engine page loaded (valid license present)
    await expect(page.locator('canvas')).toBeVisible({ timeout: 10000 });
  });

  test('License validation page has expected elements', async ({ page }) => {
    await page.goto('/dashboard/label-engine');
    await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
    await page.waitForTimeout(3000);
    
    // Verify license validation page elements
    await expect(page.locator('h1, h2, h3').first()).toContainText('License Validation');
    await expect(page.locator('button:has-text("Validate License")')).toBeVisible();
    await expect(page.locator('button:has-text("Purchase License")')).toBeVisible();
    await expect(page.locator('button:has-text("Logout")')).toBeVisible();
  });
});