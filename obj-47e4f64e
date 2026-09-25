# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: debug-label-engine.spec.ts >> Debug Label Engine Page >> Check what page we land on for Label Engine
- Location: sections\debug-label-engine.spec.ts:15:3

# Error details

```
Test timeout of 60000ms exceeded while running "beforeEach" hook.
```

```
Error: page.fill: Target page, context or browser has been closed
Call log:
  - waiting for locator('input[name="password"], input[type="password"]')

```

# Test source

```ts
  1  | import { test, expect } from '../fixtures/packaged-app';
  2  | 
  3  | test.describe('Debug Label Engine Page', () => {
  4  |   test.beforeEach(async ({ page }) => {
  5  |     // Log in first
  6  |     await page.goto('/login');
  7  |     await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
  8  |     await page.fill('input[name="username"], input[type="text"]', 'admin');
> 9  |     await page.fill('input[name="password"], input[type="password"]', 'admin123');
     |                ^ Error: page.fill: Target page, context or browser has been closed
  10 |     await page.click('button[type="submit"], button:has-text("Sign In")');
  11 |     await page.waitForURL('**/dashboard', { timeout: 30000 });
  12 |     await page.waitForTimeout(2000);
  13 |   });
  14 | 
  15 |   test('Check what page we land on for Label Engine', async ({ page }) => {
  16 |     console.log('Navigating to /dashboard/label-engine...');
  17 |     await page.goto('/dashboard/label-engine');
  18 |     await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
  19 |     await page.waitForTimeout(5000);
  20 |     
  21 |     // Take screenshot for debugging
  22 |     await page.screenshot({ path: 'test-results/label-engine-debug.png', fullPage: true });
  23 |     
  24 |     // Check what's on the page
  25 |     const bodyText = await page.textContent('body');
  26 |     console.log('Body text length:', bodyText.length);
  27 |     console.log('Body text preview:', bodyText.substring(0, 1000));
  28 |     
  29 |     // Check for toolbar buttons
  30 |     const buttons = await page.locator('button').allTextContents();
  31 |     console.log('Buttons found:', buttons);
  32 |     
  33 |     // Check for canvas
  34 |     const canvas = page.locator('canvas');
  35 |     const canvasCount = await canvas.count();
  36 |     console.log('Canvas count:', canvasCount);
  37 |     
  38 |     // Check for license-related elements
  39 |     const licenseElements = await page.locator('text=License, text=license, text=Validate, text=Purchase').allTextContents();
  40 |     console.log('License elements:', licenseElements);
  41 |     
  42 |     // Check page title/heading
  43 |     const headings = await page.locator('h1, h2, h3').allTextContents();
  44 |     console.log('Headings:', headings);
  45 |   });
  46 | });
```