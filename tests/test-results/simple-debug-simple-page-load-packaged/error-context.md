# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: simple-debug.spec.ts >> simple page load
- Location: sections\simple-debug.spec.ts:3:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: locator('canvas')
Expected: visible
Timeout: 10000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for locator('canvas')

```

```yaml
- alert
- main:
  - heading "Pharmacy Suite — Sign In" [level=1]
  - paragraph: Enter your credentials to continue.
  - text: Username
  - textbox
  - text: Password
  - textbox
  - button "Sign In"
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test('simple page load', async ({ page }) => {
  4  |   console.log('Starting test...');
  5  |   await page.goto('http://localhost:3000/dashboard/label-engine', { timeout: 60000 });
  6  |   console.log('Page loaded');
  7  |   await page.waitForTimeout(5000);
  8  |   console.log('Waited 5 seconds');
  9  |   
  10 |   const buttons = await page.locator('button').allTextContents();
  11 |   console.log('Buttons:', buttons);
  12 |   
> 13 |   await expect(page.locator('canvas')).toBeVisible({ timeout: 10000 });
     |                                        ^ Error: expect(locator).toBeVisible() failed
  14 | });
```