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
  // three-phase sessions take longer to create (PVT + steady multiphase march)
  await expect(page.getByTestId("connection").first()).toHaveText("live", { timeout: 15_000 });
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
  // the three-phase model is compute-limited (the server caps each session's
  // compute per tick to stay responsive), so simulated hours need more wall time
  test.setTimeout(240_000);
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
  await expect.poll(() => flow(page), { timeout: 200_000 }).toBeGreaterThan(q0 * 1.005);
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
  await page.getByTestId("start-ex03_choke_operation").click();
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

test("Christmas tree workstation: plain tags, valve and selector-valve operation", async ({ page }) => {
  const xt = page.getByTestId("xt-schematic");
  await expect(xt).toBeVisible();
  await expect(xt.getByText("PMV-101")).toBeVisible();
  await startFast(page, "60");
  // operate the wing valve from the schematic: the tree cavity transmitter responds
  const cavity = async () => parseFloat(((await page.getByTestId("inst-PT-104").textContent()) ?? "").replace(/[^\d.]/g, ""));
  const p0 = await cavity();
  await page.getByTestId("valve-PWV-101").click();
  await page.getByTestId("component-panel").getByRole("button", { name: /^close$/i }).click();
  await expect.poll(cavity, { timeout: 30_000 }).toBeGreaterThan(p0 + 5);
  // selector valve: isolate SCM A from the LP supply; its header bleeds down
  await page.getByTestId("selector-HSV-101").click();
  await expect(page.getByTestId("hydraulics-panel")).toBeVisible();
  await page.getByRole("button", { name: "HSV-101 close" }).click();
  await expect(page.getByTestId("selector-state")).toHaveText(/CLOSED/, { timeout: 20_000 });
  const lpA = async () => parseFloat((await page.getByTestId("hyd-LP-A").locator("text").nth(1).textContent()) ?? "NaN");
  await expect.poll(lpA, { timeout: 30_000 }).toBeLessThan(200);
  await page.keyboard.press("Escape");
});

test("three-phase production: phase rates, water-cut change, flow patterns", async ({ page }) => {
  await nav(page, "Multiphase flow");
  await expect(page.getByTestId("multiphase-page")).toBeVisible();
  const wcTile = page.getByTestId("mp-oil-Entering the well (sandface)").locator("xpath=..").getByText(/WC/);
  await expect(wcTile).toContainText("WC 30.0 %");
  await expect(page.getByTestId("pattern-strip")).toBeVisible();
  await startFast(page, "60");
  const wc = page.getByLabel("Water cut");
  await wc.fill("50");
  await page.getByRole("button", { name: "Apply fluid" }).click();
  // the composition entering the well changes at once; the manifold still sees the old fluid
  await expect(wcTile).toContainText("WC 50.0 %", { timeout: 15_000 });
  await expect(page.getByTestId("mp-balance")).toContainText("Surface gas");
});

test("MPFM: measured vs true, fault injection and calibration", async ({ page }) => {
  await page.getByTestId("mpfm-symbol").click();
  await expect(page.getByTestId("mpfm-summary")).toBeVisible();
  await page.getByRole("button", { name: "Open MPFM monitoring" }).click();
  await expect(page.getByTestId("mpfm-page")).toBeVisible();
  await expect(page.getByTestId("mpfm-quality")).toHaveText("GOOD");
  await startFast(page, "60");
  await page.getByRole("button", { name: "Gamma detector failed inject" }).click();
  await expect(page.getByTestId("mpfm-quality")).toHaveText("BAD", { timeout: 15_000 });
  await page.getByRole("button", { name: "Gamma detector failed clear" }).click();
  await page.getByTestId("mpfm-calibrate").click();
  await expect(page.getByTestId("mpfm-quality")).toHaveText("GOOD", { timeout: 15_000 });
  await expect(page.getByTestId("mpfm-std-oil_sm3_d")).toContainText("±");
});

test("sand & choke: inputs drive the prediction, choke health and fast-forward", async ({ page }) => {
  await nav(page, "Choke health");
  await expect(page.getByTestId("health-category")).toHaveText("Unavailable");
  await expect(page.getByTestId("unavailable").first()).toBeVisible();
  await nav(page, "Sand & choke inputs");
  await page.getByTestId("sand-load-example").click();
  await expect(page.getByTestId("in-max-hole")).toHaveValue("1.5", { timeout: 15_000 });
  await nav(page, "Choke health");
  await expect(page.getByTestId("health-category")).not.toHaveText("Unavailable", { timeout: 15_000 });
  await expect(page.getByTestId("confidence")).toContainText("screening");
  await page.getByTestId("fast-forward").click();
  await expect(page.getByTestId("job-state")).toHaveText("completed", { timeout: 30_000 });
  await expect(page.getByTestId("criterion-hole")).toBeVisible();
  // the sand source (onset and rates to the choke) is on the same page
  await expect(page.getByTestId("sand-source")).toBeVisible();
  await expect(page.getByTestId("risk-index")).toBeVisible();
  await nav(page, "Sand monitoring");
  await expect(page.getByTestId("detector-status")).toBeVisible();
});

test("choke cavitation screening: missing valve data, then the vendor FL and sigma limits", async ({ page }) => {
  await nav(page, "Choke health");
  // operator preset: no FL / sigma limits entered - the screening says what is missing
  await expect(page.getByTestId("cavitation-missing")).toContainText("FL");
  await nav(page, "Sand & choke inputs");
  await page.getByTestId("sand-load-example").click();
  await expect(page.getByTestId("in-sigma-i")).toHaveValue("2", { timeout: 15_000 });
  await nav(page, "Choke health");
  await expect(page.getByTestId("cavitation")).toBeVisible();
  await expect(page.getByText(/not a CFD result/)).toBeVisible();
  await expect(page.getByTestId("cavitation-risk")).not.toHaveText("Unavailable");
  // supplementary API RP 14E screening with all three locations from the simulated flow
  await expect(page.getByTestId("api14e-outlet")).toContainText("m/s");
  await expect(page.getByTestId("api14e-status")).toBeVisible();
});

test("exercise 7: integrated three-phase production, sand and choke health starts guided", async ({ page }) => {
  await nav(page, "Training");
  await page.getByTestId("start-ex07_integrated").click();
  await expect(page.getByTestId("training-step-title")).toContainText("three-phase production well");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByTestId("task-status")).toContainText("Task complete");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByTestId("training-step-title")).toContainText("Configure the reservoir fluid");
});

test("measured sand history: CSV import, abnormal increase, bad files rejected line by line", async ({ page }) => {
  await nav(page, "Sand & choke inputs");
  const csv = "timestamp,value,unit,method\n2025-01-01,2,kg/d,sand trap\n2025-02-01,2.2,kg/d,sand trap\n2025-03-01,1.9,kg/d,sand trap\n2025-04-01,7,kg/d,sand trap\n";
  await page.getByTestId("sand-csv-file").setInputFiles({ name: "sand.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByTestId("measurement-table").locator("tbody tr")).toHaveCount(4, { timeout: 15_000 });
  await nav(page, "Sand monitoring");
  await expect(page.getByTestId("abnormal-status")).toHaveText("ABNORMAL INCREASE");
  await nav(page, "Sand & choke inputs");
  await page.getByTestId("sand-csv-file").setInputFiles({ name: "bad.csv", mimeType: "text/csv", buffer: Buffer.from("timestamp,value\n2025-05-01,-3\n") });
  await expect(page.getByTestId("error-banner")).toContainText("line 2");
  await expect(page.getByTestId("measurement-table").locator("tbody tr")).toHaveCount(4);
});

test("simulation records: save the current assessment and inspect its provenance", async ({ page }) => {
  await nav(page, "Simulation records");
  const label = `e2e record ${Date.now()}`;
  await page.getByLabel("Record label").fill(label);
  await page.getByTestId("record-save").click();
  await expect(page.getByTestId("record-detail")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("records-table")).toContainText(label);
  await expect(page.getByTestId("record-provenance")).toContainText("simulated");
  await expect(page.getByTestId("record-validation")).toContainText("not field-validated");
  await page.getByRole("button", { name: `delete ${label}` }).click();
  await expect(page.getByTestId("records-table").getByText(label)).toHaveCount(0);
});

test("background job: a 10-year fast-forward runs without freezing the workstation and can be cancelled", async ({ page }) => {
  await nav(page, "Sand & choke inputs");
  await page.getByTestId("sand-load-example").click();
  await expect(page.getByTestId("in-max-hole")).toHaveValue("1.5", { timeout: 15_000 });
  await startFast(page, "60");
  await nav(page, "Choke health");
  await page.getByLabel("Fast-forward days").fill("3650");
  await page.getByTestId("fast-forward").click();
  await expect(page.getByTestId("job-state")).toHaveText("running", { timeout: 10_000 });
  // the live simulation keeps streaming while the job runs
  await expect(page.getByTestId("connection").first()).toHaveText("live");
  await expect(page.getByTestId("job-message")).toContainText("of 3650 days");
  await page.getByTestId("job-cancel").click();
  await expect(page.getByTestId("job-state")).toHaveText("cancelled", { timeout: 10_000 });
  await nav(page, "Event history");
  await expect(page.getByTestId("event-log")).toContainText("fast-forward STOPPED after");
});

test("scenario comparison: run a study, save it with a record and open the engineering report", async ({ page, context }) => {
  test.setTimeout(150_000);
  await nav(page, "Sand & choke inputs");
  await page.getByTestId("sand-load-example").click();
  await expect(page.getByTestId("in-max-hole")).toHaveValue("1.5", { timeout: 15_000 });
  await nav(page, "Scenario comparison");
  await page.getByLabel("Wear horizon days").fill("90");
  await page.getByTestId("run-comparison").click();
  await expect(page.getByTestId("job-state")).toHaveText("completed", { timeout: 90_000 });
  const results = page.getByTestId("comparison-results");
  await expect(results).toContainText("Choke 60 %");
  await expect(results).toContainText("Remaining life P50 after horizon");
  const label = `e2e study ${Date.now()}`;
  await page.getByLabel("Comparison record label").fill(label);
  await page.getByTestId("save-comparison").click();
  const link = page.getByTestId("comparison-report-link");
  await expect(link).toBeVisible();
  const [report] = await Promise.all([context.waitForEvent("page"), link.click()]);
  await expect(report.getByRole("heading", { level: 1 })).toContainText(label);
  await expect(report.getByText("12. Scenario comparison")).toBeVisible();
  await expect(report.getByText(/Validation status: Verified models, not field-validated/)).toBeVisible();
});

test("surrogate model: train on simulator cases, predict inside the envelope and check with the simulator", async ({ page }) => {
  test.setTimeout(150_000);
  await nav(page, "Sand & choke inputs");
  await page.getByTestId("sand-load-example").click();
  await expect(page.getByTestId("in-max-hole")).toHaveValue("1.5", { timeout: 15_000 });
  await nav(page, "Surrogate models");
  await page.getByLabel("Surrogate name", { exact: true }).fill(`e2e choke ${Date.now()}`);
  await page.getByLabel("use Water cut").uncheck();
  await page.getByLabel("Number of cases").fill("8");
  await page.getByTestId("train-surrogate").click();
  await expect(page.getByTestId("job-state")).toHaveText("completed", { timeout: 90_000 });
  await expect(page.getByTestId("surrogate-status")).toContainText("not CFD or field data", { timeout: 20_000 });
  await expect(page.getByTestId("surrogate-envelope")).toContainText("Inside the validated envelope");
  await page.getByTestId("surrogate-check").click();
  await expect(page.getByTestId("check-oil_sm3_d")).not.toHaveText("—", { timeout: 20_000 });
  const choke = page.getByLabel("predict Choke opening");
  await choke.fill("95");
  await page.getByTestId("surrogate-predict").click();
  await expect(page.getByTestId("surrogate-envelope")).toContainText("Outside the training range");
});

test("intern curriculum: nine exercises; exercise 2 start-up is driven by real valve operations", async ({ page }) => {
  test.setTimeout(150_000);
  await nav(page, "Training");
  for (const id of ["ex01_familiarisation", "ex02_startup", "ex03_choke_operation", "ex04_shutin", "ex05_chemicals", "ex06_annulus",
    "ex07_integrated", "ex08_leaktest", "ex09_hydraulics"]) await expect(page.getByTestId(`exercise-${id}`)).toBeVisible();
  await page.getByTestId("start-ex02_startup").click();
  await expect(page.getByTestId("training-step-title")).toContainText("A shut-in subsea well");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.getByTestId("task-status")).toContainText("Task complete");
  await page.getByRole("button", { name: "Continue" }).click();
  // answer the start-up order question
  await page.getByRole("radio", { name: /SCSSV, PMV, PWV, then crack the choke/ }).click();
  await page.getByRole("button", { name: "Submit answer" }).click();
  await expect(page.getByText("Correct", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByTestId("training-step-title")).toContainText("Open the SCSSV");
  // operate the real valve from the Christmas tree
  await page.getByRole("radiogroup", { name: "Simulation speed" }).getByRole("radio", { name: "60×" }).click();
  await nav(page, "Christmas tree");
  await page.getByTestId("valve-SCSSV-101").click();
  await page.getByTestId("component-panel").getByRole("button", { name: /^open$/i }).click();
  await nav(page, "Training");
  await expect(page.getByTestId("task-status")).toContainText("Task complete", { timeout: 60_000 });
});
