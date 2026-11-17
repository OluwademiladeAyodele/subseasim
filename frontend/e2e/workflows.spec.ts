import { expect, test, type Page } from "@playwright/test";

async function flow(page: Page): Promise<number> {
  const txt = await page.getByTestId("kpi-flow").locator(".num").innerText();
  return parseFloat(txt.trim().split(/\s+/)[0]);
}

async function startFast(page: Page, speed = "60") {
  await page.getByRole("button", { name: "Start" }).click();
  await page.getByRole("radiogroup", { name: "Simulation speed" }).getByRole("radio", { name: `${speed}×` }).click();
}

async function nav(page: Page, name: string) {
  await page.getByRole("navigation", { name: "Workspaces" }).getByRole("link", { name }).click();
}

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("connection").first()).toHaveText("live");
});

// Leave no session running at high speed behind (keeps the shared backend responsive).
test.afterEach(async ({ page }) => {
  await page.keyboard.press("Escape").catch(() => undefined); // close any open overlay first
  const pause = page.getByRole("button", { name: "Pause" });
  if (await pause.isVisible().catch(() => false)) await pause.click({ timeout: 3000 }).catch(() => undefined);
});

test("workstation is clearly marked as simulated and shows the tree", async ({ page }) => {
  await expect(page.getByTestId("simulated-badge")).toBeVisible();
  for (const tag of ["SCSSV-101", "PMV-101", "PWV-101", "CHK-101", "AMV-101", "AWV-101", "CIV-301"]) await expect(page.getByTestId(`valve-${tag}`)).toBeVisible();
  expect(await flow(page)).toBeGreaterThan(0);
  await expect(page.getByTestId("mode-dynamic")).toHaveAttribute("aria-checked", "true");
});

test("sidebar navigation and deep links switch workspaces", async ({ page }) => {
  await nav(page, "Valves & actuators");
  await expect(page).toHaveURL(/#\/valves$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Valves & actuators");
  await page.goto("/#/trends");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Trends");
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Valves & actuators");
});

test("command palette runs a valve operation", async ({ page }) => {
  await page.keyboard.press("Control+k");
  await page.getByLabel("Search commands").fill("close pwv");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("event-feed")).toContainText("PWV-101 CLOSE commanded");
});

test("choke adjustment changes the calculated flow and differential", async ({ page }) => {
  const q0 = await flow(page);
  await startFast(page);
  await page.getByTestId("valve-CHK-101").click();
  const input = page.getByLabel("Set position (0–100 %)");
  await input.fill("60");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect.poll(() => flow(page), { timeout: 30_000 }).toBeGreaterThan(q0 * 1.3);
  await expect(page.getByTestId("event-feed")).toContainText("CHK-101");
});

test("closing the wing valve stops production flow progressively", async ({ page }) => {
  await startFast(page);
  await page.getByTestId("valve-PWV-101").click();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  // dynamic model: flow decays as the flowline drains; afterwards only small
  // thermal-contraction flows remain (not exactly zero)
  await expect.poll(async () => Math.abs(await flow(page)), { timeout: 30_000 }).toBeLessThan(5);
  await expect(page.getByTestId("valve-state")).toHaveText("CLOSED");
  await expect(page.getByTestId("event-feed")).toContainText("Result of PWV-101 CLOSE");
});

test("invalid boundary input is rejected with a message", async ({ page }) => {
  await nav(page, "Conditions");
  await page.getByLabel("Reservoir pressure").fill("5000");
  await page.getByRole("button", { name: "Apply conditions" }).click();
  await expect(page.getByTestId("error-banner")).toContainText("reservoir_pressure_pa");
});

test("reservoir pressure change propagates over simulated time", async ({ page }) => {
  const q0 = await flow(page);
  await startFast(page, "600");
  await nav(page, "Conditions");
  await page.getByLabel("Reservoir pressure").fill("420");
  await page.getByRole("button", { name: "Apply conditions" }).click();
  await nav(page, "Christmas tree");
  // the steady-state target moves at once; the actual flow follows as the
  // pressure change diffuses through the reservoir (simulated hours)
  const target = async () => parseFloat((await page.getByTestId("kpi-flow").innerText()).match(/heading to ([\d.]+)/)?.[1] ?? "0");
  await expect.poll(target, { timeout: 10_000 }).toBeGreaterThan(q0 * 1.1);
  await expect.poll(() => flow(page), { timeout: 60_000 }).toBeGreaterThan(q0 * 1.005);
});

test("methanol injection enters the production stream", async ({ page }) => {
  await startFast(page);
  await nav(page, "Chemicals");
  await page.getByRole("button", { name: "CIV-301 open" }).click();
  await expect(page.getByTestId("chem-status-methanol")).toHaveText(/Injecting/, { timeout: 30_000 });
  await nav(page, "Event history");
  await expect(page.getByTestId("event-log")).toContainText("injection STARTED");
});

test("steady model can be selected and branch subsystems are flagged", async ({ page }) => {
  await page.getByTestId("mode-steady").click();
  await expect(page.getByTestId("mode-steady")).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("inst-PT-401")).toContainText("N/M");
});

test("training exercise loads its scenario and guides the intern", async ({ page }) => {
  await nav(page, "Training");
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

test("trends can be expanded, stepped through and closed", async ({ page }) => {
  await startFast(page, "300");
  await page.waitForTimeout(2500);
  await nav(page, "Trends");
  await page.getByTestId("expand-pressure").click();
  const focus = page.getByTestId("trend-focus");
  await expect(focus).toBeVisible();
  await expect(focus.getByRole("heading", { level: 2 })).toContainText("Production pressure");
  await expect(focus.getByText("Statistics · visible range")).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(focus.getByRole("heading", { level: 2 })).toContainText("Annulus pressure");
  await page.keyboard.press("Escape");
  await expect(focus).toBeHidden();
  await page.getByTestId("chart-temperature").locator(".recharts-surface").dblclick();
  await expect(page.getByTestId("trend-focus").getByRole("heading", { level: 2 })).toContainText("Temperature");
});

test("Christmas tree workstation: reference layout, valve and selector-valve operation", async ({ page }) => {
  const xt = page.getByTestId("xt-schematic");
  await expect(xt).toBeVisible();
  await expect(xt.getByText("PMV3004")).toBeVisible();
  await startFast(page, "60");
  // operate the wing valve from the schematic: the tree cavity transmitter responds
  const cavity = async () => parseFloat(((await page.getByTestId("inst-PT-104").textContent()) ?? "").replace(/[^\d.]/g, ""));
  const p0 = await cavity();
  await page.getByTestId("valve-PWV-101").click();
  await page.getByTestId("component-panel").getByRole("button", { name: /^close$/i }).click();
  await expect.poll(cavity, { timeout: 30_000 }).toBeGreaterThan(p0 + 5);
  // selector valve: isolate SCM A from the LP supply; its header bleeds down
  await page.getByTestId("selector-SEL-LP-A").click();
  await expect(page.getByTestId("hydraulics-panel")).toBeVisible();
  await page.getByRole("button", { name: "SEL-LP-A close" }).click();
  await expect(page.getByTestId("selector-state")).toHaveText(/CLOSED/, { timeout: 20_000 });
  const lpA = async () => parseFloat((await page.getByTestId("hyd-LP-A").locator("text").nth(1).textContent()) ?? "NaN");
  await expect.poll(lpA, { timeout: 30_000 }).toBeLessThan(200);
  await page.keyboard.press("Escape");
});
