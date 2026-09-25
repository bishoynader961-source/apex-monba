import { test, expect } from '../fixtures/packaged-app';

test.describe('Debug Label Engine Page', () => {
  test.beforeEach(async ({ page }) => {
    // Log in first
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
    await page.fill('input[name="username"], input[type="text"]', 'admin');
    await page.fill('input[name="password"], input[type="password"]', 'admin123');
    await page.click('button[type="submit"], button:has-text("Sign In")');
    await page.waitForURL('**/dashboard', { timeout: 30000 });
    await page.waitForTimeout(2000);
  });

  test('Check what page we land on for Label Engine', async ({ page }) => {
    console.log('Navigating to /dashboard/label-engine...');
    await page.goto('/dashboard/label-engine');
    await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
    await page.waitForTimeout(5000);
    
    // Take screenshot for debugging
    await page.screenshot({ path: 'test-results/label-engine-debug.png', fullPage: true });
    
    // Check what's on the page
    const bodyText = (await page.textContent('body').catch(() => '')) || '';
    console.log('Body text length:', bodyText.length);
    console.log('Body text preview:', bodyText.substring(0, 1000));
    
    // Check for toolbar buttons
    const buttons = await page.locator('button').allTextContents();
    console.log('Buttons found:', buttons);
    
    // Check for canvas
    const canvas = page.locator('canvas');
    const canvasCount = await canvas.count();
    console.log('Canvas count:', canvasCount);
    
    // Check for license-related elements
    const licenseElements = await page.locator('text=License, text=license, text=Validate, text=Purchase').allTextContents();
    console.log('License elements:', licenseElements);
    
    // Check page title/heading
    const headings = await page.locator('h1, h2, h3').allTextContents();
    console.log('Headings:', headings);
  });
});