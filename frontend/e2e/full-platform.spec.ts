import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const SCREENSHOTS_DIR = path.join(process.cwd(), "e2e-screenshots");
const BASE_URL = process.env.E2E_BASE_URL || "https://frontend-theta-seven-44.vercel.app";

function ensureScreenshotsDir() {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }
}

test.describe("People Discovery Platform - Full E2E", () => {
  test.beforeAll(() => {
    ensureScreenshotsDir();
  });

  test("Step 1: Login flow", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState("networkidle");

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "01-login-page.png"), fullPage: true });

    await expect(page.getByText("Admin Login")).toBeVisible();
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();

    await page.locator('input[type="email"]').fill("admin@discovery.local");
    await page.locator('input[type="password"]').fill("changeme123");
    await page.getByRole("button", { name: /sign in/i }).click();

    await page.waitForURL(/\/admin/);
    await page.waitForLoadState("networkidle");

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "02-after-login.png"), fullPage: true });

    expect(page.url()).toContain("/admin");
  });

  test("Step 2: Admin Persons List", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.locator('input[type="email"]').fill("admin@discovery.local");
    await page.locator('input[type="password"]').fill("changeme123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/admin/);
    await page.waitForLoadState("networkidle");

    await expect(page.getByText("Discovered Persons")).toBeVisible({ timeout: 10000 });

    await page.waitForSelector("table tbody tr", { timeout: 10000 });

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "03-persons-list.png"), fullPage: true });

    const rows = await page.locator("table tbody tr").count();
    expect(rows).toBeGreaterThan(0);

    await page.getByPlaceholder(/filter by name or company/i).fill("Elon");
    await page.getByRole("button", { name: /search/i }).click();
    await page.waitForTimeout(1000);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "04-persons-search-elon.png"), fullPage: true });

    await expect(page.getByText("Elon Musk")).toBeVisible();
  });

  test("Step 3: Person Detail Page", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.locator('input[type="email"]').fill("admin@discovery.local");
    await page.locator('input[type="password"]').fill("changeme123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/admin/);
    await page.waitForLoadState("networkidle");

    await page.waitForSelector("table tbody tr", { timeout: 10000 });

    await page.locator('table tbody tr:has-text("Elon Musk")').first().click();

    await page.waitForURL(/\/admin\/persons\//);
    await page.waitForLoadState("networkidle");

    await page.waitForTimeout(1000);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "05-person-detail.png"), fullPage: true });

    await expect(page.getByRole("heading", { name: "Elon Musk" })).toBeVisible();
    await expect(page.getByRole("button", { name: /re-search/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^JSON$/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^CSV$/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^PDF$/i })).toBeVisible();
  });

  test("Step 4: Cost Dashboard", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.locator('input[type="email"]').fill("admin@discovery.local");
    await page.locator('input[type="password"]').fill("changeme123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/admin/);
    await page.waitForLoadState("networkidle");

    await page.getByRole("link", { name: /cost dashboard/i }).click();
    await page.waitForURL(/\/admin\/costs/);
    await page.waitForLoadState("networkidle");

    await page.waitForTimeout(1000);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "06-cost-dashboard.png"), fullPage: true });

    await expect(page.getByRole("heading", { name: "Cost Dashboard" })).toBeVisible();
    await expect(page.getByText("Total Spend")).toBeVisible();
    await expect(page.getByText("Total Jobs")).toBeVisible();
    await expect(page.getByText("Avg Cost")).toBeVisible();
  });

  test("Step 5: API Keys", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.locator('input[type="email"]').fill("admin@discovery.local");
    await page.locator('input[type="password"]').fill("changeme123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/admin/);
    await page.waitForLoadState("networkidle");

    await page.getByRole("link", { name: /api keys/i }).click();
    await page.waitForURL(/\/admin\/api-keys/);
    await page.waitForLoadState("networkidle");

    await page.waitForTimeout(500);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "07-api-keys-page.png"), fullPage: true });

    await expect(page.getByText("API Key Management")).toBeVisible();
    await expect(page.getByText("Create New Key")).toBeVisible();

    await page.getByPlaceholder(/e.g., production api/i).fill("Test Key");
    await page.getByRole("button", { name: /create/i }).click();

    await page.waitForTimeout(1000);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "08-api-key-created.png"), fullPage: true });

    await expect(page.getByText(/key created!/i)).toBeVisible();
    await expect(page.getByRole("cell", { name: "Test Key" }).first()).toBeVisible();
  });

  test("Step 6: Webhooks", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.locator('input[type="email"]').fill("admin@discovery.local");
    await page.locator('input[type="password"]').fill("changeme123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/admin/);
    await page.waitForLoadState("networkidle");

    await page.getByRole("link", { name: /webhooks/i }).click();
    await page.waitForURL(/\/admin\/webhooks/);
    await page.waitForLoadState("networkidle");

    await page.waitForTimeout(500);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "09-webhooks-page.png"), fullPage: true });

    await expect(page.getByText("Webhook Management")).toBeVisible();
    await expect(page.getByText("job.completed")).toBeVisible();
  });

  test("Step 7: Compare", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.locator('input[type="email"]').fill("admin@discovery.local");
    await page.locator('input[type="password"]').fill("changeme123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/admin/);
    await page.waitForLoadState("networkidle");

    await page.getByRole("link", { name: /compare/i }).click();
    await page.waitForURL(/\/admin\/compare/);
    await page.waitForLoadState("networkidle");

    await page.waitForTimeout(500);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "10-compare-page.png"), fullPage: true });

    await expect(page.getByText("Compare Persons")).toBeVisible();
    await expect(page.getByPlaceholder(/type to search/i).first()).toBeVisible();

    await page.getByPlaceholder(/type to search/i).first().fill("Sam");
    await page.waitForTimeout(1000);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "11-compare-suggestions.png"), fullPage: true });

    await page.getByRole("button", { name: /Sam Altman/ }).first().click();
    await page.waitForTimeout(1500);

    await page.getByPlaceholder(/type to search/i).nth(1).fill("Jensen");
    await page.waitForTimeout(1000);
    await page.getByRole("button", { name: /Jensen Huang/ }).first().click();
    await page.waitForTimeout(1000);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "12-compare-result.png"), fullPage: true });

    await expect(page.getByRole("heading", { name: "Sam Altman" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Jensen Huang" })).toBeVisible();
  });

  test("Step 8: API Docs", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.locator('input[type="email"]').fill("admin@discovery.local");
    await page.locator('input[type="password"]').fill("changeme123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/admin/);
    await page.waitForLoadState("networkidle");

    await page.getByRole("link", { name: /api docs/i }).click();
    await page.waitForURL(/\/admin\/docs/);
    await page.waitForLoadState("networkidle");

    await page.waitForTimeout(500);

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "13-api-docs.png"), fullPage: true });

    await expect(page.getByText("API Documentation")).toBeVisible();
    await expect(page.getByText("Base URL")).toBeVisible();

    const firstEndpoint = page.locator('div.border button').filter({ hasText: /\/api\// }).first();
    if (await firstEndpoint.isVisible()) {
      await firstEndpoint.click();
      await page.waitForTimeout(500);
    }

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "14-api-docs-expanded.png"), fullPage: true });
  });

  test("Step 9: Logout", async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.locator('input[type="email"]').fill("admin@discovery.local");
    await page.locator('input[type="password"]').fill("changeme123");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/admin/);
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: /logout/i }).click();

    await page.waitForURL(/\/login/);
    await page.waitForLoadState("networkidle");

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, "15-after-logout.png"), fullPage: true });

    expect(page.url()).toContain("/login");
    await expect(page.getByText("Admin Login")).toBeVisible();
  });
});
