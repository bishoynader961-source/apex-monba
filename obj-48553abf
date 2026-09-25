import { test, expect } from '@playwright/test';

test('simple page load', async ({ page }) => {
  console.log('Starting test...');
  await page.goto('http://localhost:3000/dashboard/label-engine', { timeout: 60000 });
  console.log('Page loaded');
  await page.waitForTimeout(5000);
  console.log('Waited 5 seconds');
  
  const buttons = await page.locator('button').allTextContents();
  console.log('Buttons:', buttons);
  
  await expect(page.locator('canvas')).toBeVisible({ timeout: 10000 });
});