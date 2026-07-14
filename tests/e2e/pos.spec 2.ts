import { expect, type Page, test } from "@playwright/test";

const email = process.env.E2E_ADMIN_EMAIL || "admin@example.com";
const password = process.env.E2E_ADMIN_PASSWORD || "change-me-now";

async function login(page: Page) {
  await page.goto("/auth/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in|log in/i }).click();
}

test("cashier can reach POS and use product tiles", async ({ page }) => {
  await login(page);
  await page.goto("/pos");

  const firstTile = page.getByTestId("product-tile").first();
  await expect(firstTile).toBeVisible();
  await firstTile.click();

  await expect(page.getByText("Cart")).toBeVisible();
  await expect(page.getByTestId("complete-sale")).toBeEnabled();
});

test("POS prevents insufficient cash in the browser", async ({ page }) => {
  await login(page);
  await page.goto("/pos");
  await page.getByTestId("product-tile").first().click();
  await page.getByTestId("amount-received").fill("0.01");

  page.once("dialog", async dialog => {
    expect(dialog.message()).toContain("Amount received");
    await dialog.accept();
  });
  await page.getByTestId("complete-sale").click();
});
