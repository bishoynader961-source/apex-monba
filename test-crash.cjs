const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Capture console messages
  page.on('console', msg => {
    console.log(`[${msg.type()}] ${msg.text()}`);
  });

  page.on('pageerror', error => {
    console.log('PAGE ERROR:', error.message);
    console.log('STACK:', error.stack);
  });

  page.on('requestfailed', request => {
    console.log('REQUEST FAILED:', request.url(), request.failure().errorText);
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      console.log(`RESPONSE ${response.status()}: ${response.url()}`);
    }
  });

  try {
    console.log('Navigating to http://localhost:3000...');
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
    console.log('Page loaded, waiting for login form...');

    // Wait for login form
    await page.waitForSelector('input[name="username"], input[type="text"]', { timeout: 10000 });
    
    // Fill login form
    await page.fill('input[name="username"], input[type="text"]', 'admin');
    await page.fill('input[name="password"], input[type="password"]', 'admin123');
    
    // Click login button
    await page.click('button[type="submit"], button:has-text("Sign In"), button:has-text("Login")');
    
    console.log('Login submitted, waiting for navigation...');
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    
    console.log('Navigation complete, waiting for any errors...');
    await page.waitForTimeout(3000);
    
    console.log('Test completed successfully');
  } catch (error) {
    console.error('TEST ERROR:', error.message);
    console.log('STACK:', error.stack);
  } finally {
    await browser.close();
  }
})();