import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "fs";

// Clean-Room E2E (Spec: Objective 4, Task D — steps 4–6).
// Preconditions (created by scripts/clean-room-e2e.ps1):
//   - App freshly installed, data dir wiped, sidecars running on :3000/:8000.
// Drives: setup wizard -> login with the created credentials -> Support tab ->
// Copy Diagnostic Info (clipboard captured and exported to e2e-artifacts/).

const ARTIFACTS = "e2e-artifacts";
const ADMIN_USER = "e2ebuyer";
const ADMIN_PASS = "Buyer!2345";

// The app renders label text without for/id association, so getByLabel()
// never matches. Name-attribute selectors are the reliable equivalent.
const userInput = (page: import("@playwright/test").Page) => page.locator('input[name="username"]');
const passInput = (page: import("@playwright/test").Page) => page.locator('input[name="password"]');

mkdirSync(ARTIFACTS, { recursive: true });

test("buyer lifecycle: wizard, login, diagnostics export", async ({ page }) => {
  test.setTimeout(180_000);

  // ── Step 4: first-run wizard on a 0-user cold start ──────────────────────
  // The app's 0-user gate may have already been consumed (e.g. the wizard was
  // completed from the desktop app window while the harness ran). In that case
  // sign in with the credentials that were created and skip the wizard.
  const status = await page.request.get("/api/v1/setup/status");
  const { setup_required } = (await status.json()) as { setup_required: boolean };

  if (setup_required) {
    await page.goto("/login");
    await page.waitForURL(/\/(setup|login)/, { timeout: 30_000 });
    if (page.url().includes("/login")) {
      await page.goto("/setup");
    }
    await expect(page).toHaveURL(/\/setup/);

    // Landing screen -> Get Started
    await page.getByRole("button", { name: /get started/i }).click();

    // Step 2: Create Admin Account (fields have no name attrs — position + type)
    const adminForm = page.locator("form").filter({ hasText: /username/i }).first();
    await adminForm.locator("input[type=text]").first().fill("E2E Buyer"); // Admin Full Name
    await adminForm.locator("input[type=text]").nth(1).fill(ADMIN_USER);   // Username
    await adminForm.locator("input[type=password]").nth(0).fill(ADMIN_PASS);
    await adminForm.locator("input[type=password]").nth(1).fill(ADMIN_PASS);
    await adminForm.getByRole("button", { name: "Next" }).click();

    // Step 3: Pharmacy Profile — pharmacy name is the first (only) text input
    await page.locator("form input[type=text]").first().fill("E2E Test Pharmacy");
    await page.getByRole("button", { name: /finish|complete/i }).click();
    await page.waitForURL(/login|dashboard/, { timeout: 60_000 });
  }

  // ── Step 5: log in with the credentials the wizard created ──────────────
  await page.goto("/login");
  await userInput(page).fill(ADMIN_USER);
  await passInput(page).first().fill(ADMIN_PASS);
  // React 19 form actions can ignore a synthetic click fired right after
  // hydration — press Enter in the password field instead, then retry once
  // after a reload if the SPA state is stale.
  await passInput(page).first().press("Enter");
  try {
    await page.waitForURL(/dashboard/, { timeout: 20_000 });
  } catch {
    await page.reload();
    await userInput(page).fill(ADMIN_USER);
    await passInput(page).first().fill(ADMIN_PASS);
    await passInput(page).first().press("Enter");
    await page.waitForURL(/dashboard/, { timeout: 20_000 });
  }
  await expect(page).toHaveURL(/dashboard/);

  // ── Step 6: Support tab -> Copy Diagnostic Info -> export the report ────
  await page.goto("/dashboard/support");
  await expect(page.getByText(/support/i).first()).toBeVisible();

  const report = await page.evaluate(async () => {
    // Route the clipboard write into JS-land so the test can export it.
    const writeText = navigator.clipboard.writeText.bind(navigator.clipboard);
    let captured = "";
    navigator.clipboard.writeText = async (text: string) => {
      captured = text;
      return writeText(text);
    };
    const btn = document.querySelector("button");
    const buttons = Array.from(document.querySelectorAll("button"));
    const copyBtn = buttons.find((b) => /copy diagnostic/i.test(b.textContent ?? ""));
    if (!copyBtn) throw new Error("Copy Diagnostic Info button not found");
    copyBtn.click();
    for (let i = 0; i < 50 && !captured; i++) {
      await new Promise((r) => setTimeout(r, 100));
    }
    navigator.clipboard.writeText = writeText;
    return captured;
  });

  expect(report).toContain("Pharmacy");
  expect(report).not.toMatch(/password|bearer/i); // privacy guardrail
  writeFileSync(`${ARTIFACTS}/diagnostic-report.txt`, report);
});
