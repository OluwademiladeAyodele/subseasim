import { expect, test, type Page } from "@playwright/test";

async function flow(page: Page): Promise<number> {
  const txt = await page.getByTestId("kpi-flow").locator(".num").innerText();
  return parseFloat(txt.trim().split(/\s+/)[0]);
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("connection")).toHaveText("live");
});

test("dashboard is clearly marked as simulated and shows the tree", async ({ page }) => {
  await expect(page.getByTestId("simulated-badge")).toBeVisible();
  for (const tag of ["SCSSV-101", "PMV-101", "PWV-101", "CHK-101"]) await expect(page.getByTestId(`valve-${tag}`)).toBeVisible();
  expect(await flow(page)).toBeGreaterThan(0);
});

test("choke adjustment changes the calculated flow and differential", async ({ page }) => {
  const q0 = await flow(page);
  await page.getByRole("button", { name: "Start" }).click();
  await page.getByLabel("Simulation speed").selectOption("60");
  await page.getByTestId("valve-CHK-101").click();
  const input = page.getByLabel("Set position (0–100 %)");
  await input.fill("60");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect.poll(() => flow(page), { timeout: 30_000 }).toBeGreaterThan(q0 * 1.3);
  await expect(page.getByTestId("event-feed")).toContainText("CHK-101");
});

test("closing the wing valve stops flow", async ({ page }) => {
  await page.getByRole("button", { name: "Start" }).click();
  await page.getByLabel("Simulation speed").selectOption("60");
  await page.getByTestId("valve-PWV-101").click();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect.poll(() => flow(page), { timeout: 30_000 }).toBe(0);
  await expect(page.getByTestId("valve-state")).toHaveText("CLOSED");
  await expect(page.getByTestId("event-feed")).toContainText("Result of PWV-101 CLOSE");
});

test("invalid boundary input is rejected with a message", async ({ page }) => {
  await page.getByRole("tab", { name: "Conditions" }).click();
  await page.getByLabel("Reservoir pressure").fill("5000");
  await page.getByRole("button", { name: "Apply conditions" }).click();
  await expect(page.getByTestId("error-banner")).toContainText("reservoir_pressure_pa");
});

test("reservoir pressure change recalculates the operating point", async ({ page }) => {
  const q0 = await flow(page);
  await page.getByRole("tab", { name: "Conditions" }).click();
  await page.getByLabel("Reservoir pressure").fill("420");
  await page.getByRole("button", { name: "Apply conditions" }).click();
  await expect.poll(() => flow(page)).toBeGreaterThan(q0);
});

test("training exercise loads its scenario and guides the intern", async ({ page }) => {
  await page.getByRole("tab", { name: "Training" }).click();
  await page.getByRole("button", { name: "Start exercise" }).click();
  await expect(page.getByTestId("training-step-title")).toHaveText("Introduction");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByTestId("training-step-title")).toHaveText("Start the simulation");
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByTestId("task-status")).toContainText("Task complete");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByTestId("task-status")).toContainText("Task complete");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByTestId("training-step-title")).toContainText("Predict");
});
