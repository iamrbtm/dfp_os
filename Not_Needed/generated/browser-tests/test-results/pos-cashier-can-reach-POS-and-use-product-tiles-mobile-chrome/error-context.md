# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: pos.spec.ts >> cashier can reach POS and use product tiles
- Location: tests/e2e/pos.spec.ts:13:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByTestId('product-tile').first()
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 5000ms
  - waiting for getByTestId('product-tile').first()

```

```yaml
- link "Dude Fish OS":
  - /url: /dashboard/
- button:
  - img
- navigation:
  - link "Dashboard":
    - /url: /dashboard/
  - link "Notifications":
    - /url: /admin/notifications/
  - link "POS":
    - /url: /pos/sessions
  - link "Products":
    - /url: /products/products/
  - link "Customers":
    - /url: /customers/customers/
  - link "Orders":
    - /url: /orders/orders/
  - link "Custom Orders":
    - /url: /custom-orders/requests/
  - link "Printers":
    - /url: /printers/printers/
  - link "Print Jobs":
    - /url: /print-jobs/print-jobs/
  - link "Inventory":
    - /url: /inventory/records/
  - link "API Tokens":
    - /url: /settings/api-tokens/
  - link "Settings":
    - /url: /settings/themes
  - link "Markets":
    - /url: /markets/markets/
  - link "Prep Tasks":
    - /url: /prep-tasks/tasks/
  - link "Expenses":
    - /url: /expenses/expenses/
  - link "Analytics":
    - /url: /analytics/
  - link "DFP Intelligence":
    - /url: /admin/intelligence/
  - link "Trend Scout":
    - /url: /admin/trend-scout/
  - link "Cost Engine":
    - /url: /cost-engine/
  - link "Audit Logs":
    - /url: /audit-logs/
- text: AU
- paragraph: Admin User
- paragraph: admin
- combobox:
  - option "DFP GitHub Light"
  - option "DFP Atom One Light"
  - option "DFP Catppuccin Latte"
  - option "DFP Ayu Light"
  - option "DFP Quiet Light"
  - option "DFP One Dark Pro" [selected]
  - option "DFP Dracula"
  - option "DFP GitHub Dark"
  - option "DFP Tokyo Night"
  - option "DFP Catppuccin Mocha"
- button "Sign out"
- button:
  - img
- text: POS
- navigation:
  - link "Sessions":
    - /url: /pos/sessions
  - link "New Session":
    - /url: /pos/sessions/new
- main:
  - heading "POS Sessions" [level=1]
  - link "Open Session":
    - /url: /pos/sessions/new
  - textbox "Search sessions..."
  - button "Search"
  - table:
    - rowgroup:
      - row "Session Status Opened Opened By Sales Total Actions":
        - columnheader "Session"
        - columnheader "Status"
        - columnheader "Opened"
        - columnheader "Opened By"
        - columnheader "Sales"
        - columnheader "Total"
        - columnheader "Actions"
    - rowgroup:
      - row "No sessions yet.":
        - cell "No sessions yet."
- contentinfo:
  - paragraph: Dude Fish Printing
  - paragraph: Family-run 3D printing for dragons, fidgets, flexi animals, personalized gifts, and small business displays.
  - paragraph: © 2025 Dude Fish Printing — Clarksville, Tennessee
  - link "Returns":
    - /url: /returns
  - link "Policies":
    - /url: /customer-policies
  - link "Privacy":
    - /url: /privacy
  - link "Terms":
    - /url: /terms
  - link "FAQ":
    - /url: /faq
  - link "Contact":
    - /url: /contact
```

# Test source

```ts
  1  | import { expect, type Page, test } from "@playwright/test";
  2  | 
  3  | const email = process.env.E2E_ADMIN_EMAIL || "admin@example.com";
  4  | const password = process.env.E2E_ADMIN_PASSWORD || "change-me-now";
  5  | 
  6  | async function login(page: Page) {
  7  |   await page.goto("/auth/login");
  8  |   await page.getByLabel("Email").fill(email);
  9  |   await page.getByLabel("Password").fill(password);
  10 |   await page.getByRole("button", { name: /sign in|log in/i }).click();
  11 | }
  12 | 
  13 | test("cashier can reach POS and use product tiles", async ({ page }) => {
  14 |   await login(page);
  15 |   await page.goto("/pos");
  16 | 
  17 |   const firstTile = page.getByTestId("product-tile").first();
> 18 |   await expect(firstTile).toBeVisible();
     |                           ^ Error: expect(locator).toBeVisible() failed
  19 |   await firstTile.click();
  20 | 
  21 |   await expect(page.getByText("Cart")).toBeVisible();
  22 |   await expect(page.getByTestId("complete-sale")).toBeEnabled();
  23 | });
  24 | 
  25 | test("POS prevents insufficient cash in the browser", async ({ page }) => {
  26 |   await login(page);
  27 |   await page.goto("/pos");
  28 |   await page.getByTestId("product-tile").first().click();
  29 |   await page.getByTestId("amount-received").fill("0.01");
  30 | 
  31 |   page.once("dialog", async dialog => {
  32 |     expect(dialog.message()).toContain("Amount received");
  33 |     await dialog.accept();
  34 |   });
  35 |   await page.getByTestId("complete-sale").click();
  36 | });
  37 | 
```