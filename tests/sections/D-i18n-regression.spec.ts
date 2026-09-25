import { test, expect } from '../fixtures/packaged-app';

test.describe('Section D: i18n Key Leakage Regression (requires valid license)', () => {
  test.beforeEach(async ({ page }) => {
    // Check if already logged in
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded', { timeout: 60000 });
    
    // Check if we're on login page (not logged in)
    const isLoginPage = await page.locator('input[name="username"], input[type="text"]').first().isVisible({ timeout: 5000 }).catch(() => false);
    
    if (isLoginPage) {
      // Log in
      await page.goto('/login');
      await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
      await page.fill('input[name="username"], input[type="text"]', 'admin');
      await page.fill('input[name="password"], input[type="password"]', 'admin123');
      await page.click('button[type="submit"], button:has-text("Sign In")');
      await page.waitForURL('**/dashboard', { timeout: 60000 });
      await page.waitForTimeout(2000);
    }
    
    // Now navigate to roles page
    await page.goto('/dashboard/roles');
    await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
    // Wait for React components to render
    await page.waitForTimeout(5000);
    // Wait for heading to appear
    await page.locator('h1, h2, h3').first().waitFor({ state: 'visible', timeout: 15000 });
  });

  test('Add Permission modal shows translated text, not raw keys', async ({ page }) => {
    // Check if license validation page is shown
    const heading = page.locator('h1, h2, h3').first();
    await heading.waitFor({ state: 'visible', timeout: 15000 });
    const headingText = await heading.textContent();
    
    console.log('Heading text:', JSON.stringify(headingText));
    
    if (headingText?.includes('License Validation') || headingText?.includes('License')) {
      console.log('License validation page detected - skipping Add Permission test (requires valid license)');
      return;
    }
    
    await page.click('button:has-text("Add Permission")');
    await expect(page.locator('h2:has-text("Add Permission")')).toBeVisible({ timeout: 10000 });
    
    // Check that labels show translated text, not raw keys
    await expect(page.locator('label')).toContainText('Module');
    await expect(page.locator('label')).toContainText('Select module');
    await expect(page.locator('label')).toContainText('Feature Key');
    await expect(page.locator('label')).toContainText('Feature Key');
    
    // Check hint text
    await expect(page.locator('text=Format: module.action')).toBeVisible();
    
    // Check that no raw keys are visible
    await expect(page.locator('text=roles.fieldModule')).not.toBeVisible();
    await expect(page.locator('text=roles.selectModule')).not.toBeVisible();
    await expect(page.locator('text=roles.fieldFeatureKey')).not.toBeVisible();
    await expect(page.locator('text=roles.featureKeyHint')).not.toBeVisible();
    await expect(page.locator('text=roles.addPermAllFieldsRequired')).not.toBeVisible();
    await expect(page.locator('text=roles.addPermFormatError')).not.toBeVisible();
    await expect(page.locator('text=roles.addPermModuleMismatch')).not.toBeVisible();
    await expect(page.locator('text=roles.addPermission')).not.toBeVisible();
    await expect(page.locator('text=roles.create')).not.toBeVisible();
    
    await page.click('button:has-text("Cancel")');
  });

  test('Lock Password modal shows translated text, not raw keys', async ({ page }) => {
    // Check if license validation page is shown
    const heading = page.locator('h1, h2, h3').first();
    const headingText = await heading.textContent();
    
    if (headingText?.includes('License Validation') || headingText?.includes('License')) {
      console.log('License validation page detected - skipping Lock Password test (requires valid license)');
      return;
    }
    
    await page.click('button:has-text("Set Lock Password")');
    await expect(page.locator('h2:has-text("Set Lock Password")')).toBeVisible({ timeout: 10000 });
    
    // Check warning text
    await expect(page.locator('text=This lock password cannot be recovered if lost')).toBeVisible();
    
    // Check labels
    await expect(page.locator('label')).toContainText('New Lock Password');
    await expect(page.locator('label')).toContainText('Confirm Lock Password');
    
    // Check that no raw keys are visible
    await expect(page.locator('text=roles.lockPasswordTitle')).not.toBeVisible();
    await expect(page.locator('text=roles.setLockPassword')).not.toBeVisible();
    await expect(page.locator('text=roles.lockPassNew')).not.toBeVisible();
    await expect(page.locator('text=roles.lockPassConfirm')).not.toBeVisible();
    await expect(page.locator('text=roles.lockPassRequired')).not.toBeVisible();
    await expect(page.locator('text=roles.lockPassMinLength')).not.toBeVisible();
    await expect(page.locator('text=roles.lockPassMismatch')).not.toBeVisible();
    await expect(page.locator('text=roles.lockPasswordSet')).not.toBeVisible();
    await expect(page.locator('text=common.next')).not.toBeVisible();
    await expect(page.locator('text=common.back')).not.toBeVisible();
    
    await page.click('button:has-text("Cancel")');
  });

  test('No raw i18n keys visible in Roles tab', async ({ page }) => {
    // Check if license validation page is shown
    const heading = page.locator('h1, h2, h3').first();
    const headingText = await heading.textContent();
    
    if (headingText?.includes('License Validation') || headingText?.includes('License')) {
      console.log('License validation page detected - skipping raw keys check (requires valid license)');
      return;
    }
    
    // Check that all visible text in the Roles tab is translated
    const rawKeys = [
      'roles.fieldModule',
      'roles.selectModule',
      'roles.fieldFeatureKey',
      'roles.featureKeyHint',
      'roles.addPermAllFieldsRequired',
      'roles.addPermFormatError',
      'roles.addPermModuleMismatch',
      'roles.addPermission',
      'roles.create',
      'roles.lockPasswordTitle',
      'roles.setLockPassword',
      'roles.lockPassNew',
      'roles.lockPassConfirm',
      'roles.lockPassRequired',
      'roles.lockPassMinLength',
      'roles.lockPassMismatch',
      'roles.lockPasswordSet',
      'common.next',
      'common.back',
    ];
    
    for (const key of rawKeys) {
      await expect(page.locator(`text=${key}`)).not.toBeVisible();
    }
  });
});