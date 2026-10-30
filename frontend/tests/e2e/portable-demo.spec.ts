import { test, expect } from "@playwright/test";

test("portable demo works without private historical archives", async ({ page }) => {
  test.setTimeout(180_000);
  const catalogResponse = await page.request.get("/api/datasets");
  expect(catalogResponse.ok()).toBeTruthy();
  const datasets = await catalogResponse.json();
  test.skip(
    datasets.some((dataset: { source_type: string; status?: string }) =>
      dataset.source_type === "verified_historical" && dataset.status !== "unavailable"),
    "Run this workflow against a fresh demo-only clone with KEDR_LEGACY_ROOT unset.",
  );
  expect(datasets.some((dataset: { id: string }) => dataset.id === "demo_btc_4h")).toBeTruthy();
  expect(datasets.filter((dataset: { source_type: string }) => dataset.source_type === "verified_historical")
    .every((dataset: { status: string }) => dataset.status === "unavailable")).toBeTruthy();

  const session = await page.request.post("/api/auth/demo");
  expect(session.ok()).toBeTruthy();
  const { csrf_token } = await session.json();
  const profile = await page.request.patch("/api/profile", {
    headers: { "X-CSRF-Token": csrf_token },
    data: { locale: "en" },
  });
  expect(profile.ok()).toBeTruthy();

  const errors: string[] = [];
  const archiveRequests: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.url().includes("/api/market/chart?") && request.url().includes("verified_")) {
      archiveRequests.push(request.url());
    }
  });
  await page.goto("/market");
  await expect(page.getByTestId("chart-dataset")).toHaveValue("demo_btc_4h");
  await expect(page.getByTestId("candlestick-chart")).toBeVisible();
  await expect(page.getByText("These are synthetic demonstration candles", { exact: false })).toBeVisible();
  await expect(page.getByTestId("chart-dataset").locator('option[value="verified_btc_4h"]')).toHaveJSProperty("disabled", true);

  await page.goto("/new");
  await page.getByTestId("create-blank").click();
  await expect(page).toHaveURL(/\/builder\//);
  await page.getByTestId("guided-builder").click();
  await page.getByTestId("wizard-apply").click();
  await page.getByTestId("save-strategy").click();
  await page.getByTestId("run-backtest").click();
  await expect(page.getByTestId("dataset-select")).toHaveValue("demo_btc_4h");
  await expect(page.getByTestId("dataset-select").locator('option[value="verified_btc_4h"]')).toHaveJSProperty("disabled", true);
  await expect(page.getByText("Synthetic demo selected", { exact: false })).toBeVisible();
  await expect(page.getByTestId("backtest-unavailable-data")).toBeVisible();
  await page.getByTestId("confirm-backtest").click();
  await expect(page).toHaveURL(/\/backtests\//, { timeout: 90_000 });
  const run = await (await page.request.get(`/api/backtests/${page.url().split("/").at(-1)}`)).json();
  expect(run.dataset.id).toBe("demo_btc_4h");
  expect(run.quality.source_type).toBe("synthetic_demo");
  await page.getByTestId("result-tab-terminal").click();
  await expect(page.getByTestId("candlestick-chart")).toBeVisible();

  await page.goto("/ml");
  await expect(page.getByTestId("ml-dataset")).toHaveValue("demo_btc_4h");
  await expect(page.getByText("Synthetic data: training and interface demonstration only", { exact: false })).toBeVisible();
  await expect(page.getByTestId("ml-dataset").locator('option[value="verified_btc_4h"]')).toHaveJSProperty("disabled", true);
  await page.getByTestId("ml-train").click();
  await expect(page.locator(".ml-job-head")).toContainText("succeeded", { timeout: 90_000 });
  await expect(page.locator(".ml-score-grid")).toContainText("brier");
  expect(archiveRequests).toEqual([]);
  expect(errors).toEqual([]);
});
