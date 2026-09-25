import { test as base, type Page } from '@playwright/test';
import { fileURLToPath } from 'url';
import path from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface PackagedAppFixtures {
  page: Page;
}

const STORAGE_STATE_PATH = path.join(__dirname, '..', '.auth', 'packaged-app-state.json');

async function ensureAuthenticatedState(): Promise<void> {
  const { chromium } = await import('@playwright/test');
  const { fileURLToPath } = await import('url');
  const { dirname } = await import('path');
  
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  
  const browser = await chromium.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });
  
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    recordVideo: { dir: 'test-results/videos', size: { width: 1366, height: 768 } },
  });
  
  const page = await context.newPage();
  
  // Login
  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded', { timeout: 30000 });
  await page.fill('input[name="username"], input[type="text"]', 'admin');
  await page.fill('input[name="password"], input[type="password"]', 'admin123');
  await page.click('button[type="submit"], button:has-text("Sign In")');
  await page.waitForURL('**/dashboard', { timeout: 60000 });
  await page.waitForTimeout(2000);
  
  // Save storage state
  await context.storageState({ path: STORAGE_STATE_PATH });
  await context.close();
  await browser.close();
}

export const test = base.extend<{ page: Page }>({
  page: async ({}, use) => {
    const { chromium } = await import('@playwright/test');
    const { fileURLToPath } = await import('url');
    const { dirname } = await import('path');
    
    const __filename = fileURLToPath(import.meta.url);
    const __dirname = path.dirname(__filename);
    
    // Ensure authenticated state exists
    try {
      const fs = await import('fs');
      if (!fs.existsSync(STORAGE_STATE_PATH)) {
        await ensureAuthenticatedState();
      }
    } catch {
      await ensureAuthenticatedState();
    }
    
    // Use regular Chromium browser with persisted storage state
    const browser = await chromium.launch({
      headless: false,
      args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    });
    
    const context = await browser.newContext({
      viewport: { width: 1366, height: 768 },
      recordVideo: { dir: 'test-results/videos', size: { width: 1366, height: 768 } },
      storageState: STORAGE_STATE_PATH,
    });

    const page = await context.newPage();
    
    // Mock Tauri IPC for consistent testing
    await page.addInitScript(`
      (window as any).__TAURI_IPC_MOCK__ = {
        invoke: async (cmd, args) => {
          console.log('[TAURI IPC MOCK]', cmd, args);
          if (cmd === 'print_label') {
            return { success: true, printed: true };
          }
          if (cmd === 'open_label_window') {
            return { success: true, windowId: 'mock-window' };
          }
          return { success: true };
        };
        
        if ((window as any).__TAURI__) {
          (window as any).__TAURI__.invoke = async (cmd, args) => {
            console.log('[TAURI IPC MOCK - __TAURI__]', cmd, args);
            return { success: true };
          };
        }
      }
    `);
    
    await use(page);
    await page.context().browser()?.close();
  },
});

export { expect } from '@playwright/test';