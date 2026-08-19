import { expect, test } from "@playwright/test";

// Smoke: an unauthenticated visit to a protected route must be redirected to
// /login by the edge middleware, and the login page must render. This exercises
// the built bundle + middleware without requiring the backend API.
test("unauthenticated /pos redirects to /login and renders", async ({ page }) => {
  await page.goto("/pos");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.locator("body")).not.toBeEmpty();
});
