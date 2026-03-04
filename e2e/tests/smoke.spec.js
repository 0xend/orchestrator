const { test, expect } = require("@playwright/test");

const backendPort = process.env.ORCHESTRATOR_BACKEND_PORT || "18000";

test("backend health endpoint responds", async ({ request }) => {
  const response = await request.get(`http://127.0.0.1:${backendPort}/healthz`);
  expect(response.ok()).toBeTruthy();
  await expect(response.json()).resolves.toMatchObject({ status: "ok" });
});

test("user can create a task from the homepage", async ({ page }) => {
  const title = `CI smoke ${Date.now()}`;
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Orchestrator" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create Task" })).toBeEnabled();

  await page.getByPlaceholder("https://github.com/owner/repo").fill("https://github.com/0xend/orchestrator");
  await page.getByPlaceholder("Title").fill(title);
  await page.getByPlaceholder("Describe the task").fill("Smoke test task from Playwright.");
  await page.getByRole("button", { name: "Create Task" }).click();

  await expect(page.getByText(title).first()).toBeVisible();

  await page.reload();
  await expect(page.getByText(title).first()).toBeVisible();
});
