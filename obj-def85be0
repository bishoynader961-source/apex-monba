import { Page, Locator } from '@playwright/test';

/**
 * Parse RGB/RGBA color string to [r, g, b, a]
 */
export function parseColor(color: string): [number, number, number, number] {
  const match = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
  if (!match) return [0, 0, 0, 1];
  return [
    parseInt(match[1]),
    parseInt(match[2]),
    parseInt(match[3]),
    match[4] ? parseFloat(match[4]) : 1,
  ];
}

/**
 * Calculate relative luminance of a color
 */
export function getLuminance([r, g, b]: number[]): number {
  const srgb = [r, g, b].map(c => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2];
}

/**
 * Calculate contrast ratio between two colors
 * Returns ratio (1:1 to 21:1)
 */
export function getContrastRatio(fgColor: string, bgColor: string): number {
  const [fr, fg, fb] = parseColor(fgColor);
  const [br, bg, bb] = parseColor(bgColor);
  
  const fgLum = getLuminance([fr, fg, fb]);
  const bgLum = getLuminance([br, bg, bb]);
  
  const lighter = Math.max(fgLum, bgLum);
  const darker = Math.min(fgLum, bgLum);
  
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Get computed color of an element
 */
export async function getElementColor(page: Page, selector: string): Promise<string> {
  return page.locator(selector).first().evaluate(el => 
    getComputedStyle(el).color
  );
}

/**
 * Get computed background color of an element
 */
export async function getElementBackgroundColor(page: Page, selector: string): Promise<string> {
  return page.locator(selector).first().evaluate(el => 
    getComputedStyle(el).backgroundColor
  );
}

/**
 * Check if element has sufficient contrast against its background
 * Returns { passes: boolean, ratio: number, fg: string, bg: string }
 */
export async function checkContrast(page: Page, selector: string | Locator, minRatio = 4.5): Promise<{
  passes: boolean;
  ratio: number;
  fg: string;
  bg: string;
}> {
  let fg: string;
  let bg: string;
  
  if (typeof selector === 'string') {
    fg = await getElementColor(page, selector);
    bg = await getElementBackgroundColor(page, selector);
  } else {
    // For Locator, get the first element's colors
    fg = await selector.first().evaluate(el => getComputedStyle(el).color);
    bg = await selector.first().evaluate(el => getComputedStyle(el).backgroundColor);
  }
  
  const ratio = getContrastRatio(fg, bg);
  
  return {
    passes: ratio >= minRatio,
    ratio,
    fg,
    bg,
  };
}

/**
 * Get all heading elements that should be checked for contrast
 */
export async function getHeadingsToCheck(page: Page): Promise<Locator[]> {
  const selectors = [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    '.page-title',
    '.section-header', 
    '.dashboard-header h1',
    '.card-header h3',
    '.modal-header h2',
    '.tab-button',
    '[role="tab"]',
    '.tab-label',
  ];
  
  const locators: Locator[] = [];
  for (const sel of selectors) {
    try {
      const loc = page.locator(sel);
      const count = await loc.count();
      if (count > 0) locators.push(loc);
    } catch {
      // Skip invalid selectors
    }
  }
  return locators;
}

/**
 * Mock Tauri IPC for testing
 */
export async function mockTauriIPC(page: Page): Promise<void> {
  const initScript = `
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
  `;
  await page.addInitScript(initScript);

  // Also intercept at the module level
  await page.route('**/*', async route => {
    if (route.request().url().includes('@tauri-apps/api')) {
      // Let it through but we've mocked the global
    }
    await route.continue();
  });
}

/**
 * Wait for toast notification to appear and return its message
 */
export async function waitForToast(page: Page, timeout = 5000): Promise<string> {
  const toast = page.locator('[role="alert"], .toast, [class*="toast"]').first();
  await toast.waitFor({ state: 'visible', timeout });
  return (await toast.textContent()) || '';
}

/**
 * Click and wait for navigation/API call
 */
export async function clickAndWait(page: Page, selector: string, waitForUrl?: string): Promise<void> {
  const [response] = await Promise.all([
    waitForUrl ? page.waitForURL(waitForUrl) : page.waitForLoadState('networkidle'),
    page.click(selector),
  ]);
  return response as any;
}

/**
 * Fill form field and trigger validation
 */
export async function fillAndValidate(page: Page, selector: string, value: string): Promise<void> {
  await page.fill(selector, value);
  await page.locator(selector).dispatchEvent('blur');
  await page.waitForTimeout(200);
}

/**
 * Get all visible headings and their contrast ratios
 */
export async function auditHeadingsContrast(page: Page): Promise<Array<{
  selector: string;
  text: string;
  fg: string;
  bg: string;
  ratio: number;
  passes: boolean;
}>> {
  const headings = await getHeadingsToCheck(page);
  const results = [];
  
  for (const loc of headings) {
    const count = await loc.count();
    for (let i = 0; i < count; i++) {
      const el = loc.nth(i);
      const isVisible = await el.isVisible();
      if (!isVisible) continue;
      
      const text = await el.textContent();
      if (!text || text.trim().length === 0) continue;
      
      const result = await checkContrast(page, loc);
      results.push({
        selector: (await el.getAttribute('class')) || (await el.evaluate(el => el.tagName.toLowerCase())),
        text: text.trim().slice(0, 100),
        fg: result.fg,
        bg: result.bg,
        ratio: result.ratio,
        passes: result.passes,
      });
    }
  }
  
  return results;
}