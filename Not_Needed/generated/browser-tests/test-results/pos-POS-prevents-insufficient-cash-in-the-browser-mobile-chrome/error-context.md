# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: pos.spec.ts >> POS prevents insufficient cash in the browser
- Location: tests/e2e/pos.spec.ts:25:5

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByTestId('product-tile').first()

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - generic [ref=e2]:
    - generic [ref=e3]:
      - link "Dude Fish OS" [ref=e4] [cursor=pointer]:
        - /url: /dashboard/
      - button [ref=e5] [cursor=pointer]:
        - img [ref=e6]
    - navigation [ref=e8]:
      - link "Dashboard" [ref=e9] [cursor=pointer]:
        - /url: /dashboard/
      - link "Notifications" [ref=e10] [cursor=pointer]:
        - /url: /admin/notifications/
      - link "POS" [ref=e11] [cursor=pointer]:
        - /url: /pos/sessions
      - link "Products" [ref=e12] [cursor=pointer]:
        - /url: /products/products/
      - link "Customers" [ref=e13] [cursor=pointer]:
        - /url: /customers/customers/
      - link "Orders" [ref=e14] [cursor=pointer]:
        - /url: /orders/orders/
      - link "Custom Orders" [ref=e15] [cursor=pointer]:
        - /url: /custom-orders/requests/
      - link "Printers" [ref=e16] [cursor=pointer]:
        - /url: /printers/printers/
      - link "Print Jobs" [ref=e17] [cursor=pointer]:
        - /url: /print-jobs/print-jobs/
      - link "Inventory" [ref=e18] [cursor=pointer]:
        - /url: /inventory/records/
      - link "API Tokens" [ref=e19] [cursor=pointer]:
        - /url: /settings/api-tokens/
      - link "Settings" [ref=e20] [cursor=pointer]:
        - /url: /settings/themes
      - link "Markets" [ref=e21] [cursor=pointer]:
        - /url: /markets/markets/
      - link "Prep Tasks" [ref=e22] [cursor=pointer]:
        - /url: /prep-tasks/tasks/
      - link "Expenses" [ref=e24] [cursor=pointer]:
        - /url: /expenses/expenses/
      - link "Analytics" [ref=e25] [cursor=pointer]:
        - /url: /analytics/
      - link "DFP Intelligence" [ref=e27] [cursor=pointer]:
        - /url: /admin/intelligence/
      - link "Trend Scout" [ref=e29] [cursor=pointer]:
        - /url: /admin/trend-scout/
      - link "Cost Engine" [ref=e30] [cursor=pointer]:
        - /url: /cost-engine/
      - link "Audit Logs" [ref=e31] [cursor=pointer]:
        - /url: /audit-logs/
    - generic [ref=e32]:
      - generic [ref=e33]:
        - generic [ref=e34]: AU
        - generic [ref=e35]:
          - paragraph [ref=e36]: Admin User
          - paragraph [ref=e37]: admin
      - generic [ref=e38]:
        - combobox [ref=e39]:
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
        - button "Sign out" [ref=e41] [cursor=pointer]
  - generic [ref=e42]:
    - generic [ref=e43]:
      - button [ref=e44] [cursor=pointer]:
        - img [ref=e45]
      - generic [ref=e47]: POS
      - navigation [ref=e48]:
        - link "Sessions" [ref=e49] [cursor=pointer]:
          - /url: /pos/sessions
        - link "New Session" [ref=e50] [cursor=pointer]:
          - /url: /pos/sessions/new
    - main [ref=e51]:
      - generic [ref=e52]:
        - generic [ref=e53]:
          - heading "POS Sessions" [level=1] [ref=e54]
          - link "Open Session" [ref=e55] [cursor=pointer]:
            - /url: /pos/sessions/new
        - generic [ref=e56]:
          - textbox "Search sessions..." [ref=e57]
          - button "Search" [ref=e58] [cursor=pointer]
        - table [ref=e60]:
          - rowgroup [ref=e61]:
            - row "Session Status Opened Opened By Sales Total Actions" [ref=e62]:
              - columnheader "Session" [ref=e63]
              - columnheader "Status" [ref=e64]
              - columnheader "Opened" [ref=e65]
              - columnheader "Opened By" [ref=e66]
              - columnheader "Sales" [ref=e67]
              - columnheader "Total" [ref=e68]
              - columnheader "Actions" [ref=e69]
          - rowgroup [ref=e70]:
            - row "No sessions yet." [ref=e71]:
              - cell "No sessions yet." [ref=e72]
    - contentinfo [ref=e73]:
      - generic [ref=e74]:
        - generic [ref=e75]:
          - paragraph [ref=e76]: Dude Fish Printing
          - paragraph [ref=e77]: Family-run 3D printing for dragons, fidgets, flexi animals, personalized gifts, and small business displays.
          - paragraph [ref=e78]: © 2025 Dude Fish Printing — Clarksville, Tennessee
        - generic [ref=e79]:
          - link "Returns" [ref=e80] [cursor=pointer]:
            - /url: /returns
          - link "Policies" [ref=e81] [cursor=pointer]:
            - /url: /customer-policies
          - link "Privacy" [ref=e82] [cursor=pointer]:
            - /url: /privacy
          - link "Terms" [ref=e83] [cursor=pointer]:
            - /url: /terms
          - link "FAQ" [ref=e84] [cursor=pointer]:
            - /url: /faq
          - link "Contact" [ref=e85] [cursor=pointer]:
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
  18 |   await expect(firstTile).toBeVisible();
  19 |   await firstTile.click();
  20 | 
  21 |   await expect(page.getByText("Cart")).toBeVisible();
  22 |   await expect(page.getByTestId("complete-sale")).toBeEnabled();
  23 | });
  24 | 
  25 | test("POS prevents insufficient cash in the browser", async ({ page }) => {
  26 |   await login(page);
  27 |   await page.goto("/pos");
> 28 |   await page.getByTestId("product-tile").first().click();
     |                                                  ^ Error: locator.click: Test timeout of 30000ms exceeded.
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