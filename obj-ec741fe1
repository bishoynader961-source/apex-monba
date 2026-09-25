import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'url';
import path from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
  testDir: path.join(__dirname, 'sections'),
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    actionTimeout: 60000,
    navigationTimeout: 120000,
  },
  projects: [
    {
      name: 'packaged',
      use: {
        ...devices['Desktop Chrome'],
        headless: false,
      },
    },
  ],
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
});