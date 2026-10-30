import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

const screenshot = (name: string) =>
  path.resolve(import.meta.dirname, "../../../verification/v02", name);

async function mobileViewport(page: Page) {
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(async () => page.locator('.sidebar').evaluate(el => el.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
}

async function demo(page: Page) {
  await page.goto("/");
  await page.getByTestId("demo-login").click();
  await expect(page).toHaveURL(/onboarding/);
  await page
    .getByRole("button", { name: "Выбрать первую стратегию", exact: true })
    .click();
  await expect(page).toHaveURL(/\/new$/);
}

test("Russian beginner edits, saves, backtests, explains, publishes and forks a verified version", async ({
  page,
}) => {
  const sourceCatalog = await (await page.request.get('/api/datasets')).json();
  test.skip(!sourceCatalog.some((item: {id:string;status:string})=>item.id==='verified_btc_4h'&&item.status==='available'), 'Optional verified local archives are not installed in this source clone.');
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await demo(page);
  await page.getByTestId("template-ma_crossover").click();
  await expect(page).toHaveURL(/\/builder\//);
  const strategyUrl = page.url();
  await expect(page.locator(".react-flow__node")).toHaveCount(7);
  await page.getByTestId("strategy-name").fill("Проверка полного пути · SMA");
  await page.locator('.react-flow__node[data-id="fast"]').click();
  await page.getByLabel("Период, свечей", { exact: true }).fill("18");
  await page.getByTestId("save-strategy").click();
  await expect(page.locator(".save-status")).toContainText("Сохранено");
  await page.screenshot({
    path: screenshot("builder-desktop.png"),
    fullPage: true,
  });
  await page.getByTestId("run-backtest").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByTestId("dataset-select")).toHaveValue(
    "verified_btc_4h",
  );
  await page.getByTestId("backtest-start").fill("2023-01-01");
  await page.getByTestId("backtest-end").fill("2025-12-31");
  await expect(page.getByTestId("confirm-backtest")).toBeEnabled();
  await page.screenshot({
    path: screenshot("backtest-config.png"),
    fullPage: true,
  });
  await page.getByTestId("confirm-backtest").click();
  await expect(page).toHaveURL(/\/backtests\//, { timeout: 90_000 });
  await expect(
    page.getByRole("heading", { name: "Динамика капитала" }),
  ).toBeVisible();
  await expect(
    page.getByText("Исторический архив", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();
  const runUrl = page.url();
  await page.screenshot({
    path: screenshot("results-desktop.png"),
    fullPage: true,
  });
  await mobileViewport(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: screenshot("results-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: /Журнал сделок/ }).click();
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page
    .getByRole("button", { name: "Качество исследования", exact: true })
    .click();
  await expect(
    page.getByText("Без независимой валидации", { exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Обзор результата", exact: true })
    .click();
  await page.getByRole("link", { name: "Открыть разбор", exact: true }).click();
  await expect(page).toHaveURL(/\/analyst\//);
  await expect(
    page.getByText("Генеративный AI не подключён", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: screenshot("analyst-desktop.png"),
    fullPage: true,
  });
  await page.goto("/dashboard");
  await expect(
    page.getByText("Проверка полного пути · SMA").first(),
  ).toBeVisible();
  await page.screenshot({
    path: screenshot("dashboard-desktop.png"),
    fullPage: true,
  });
  await page.goto(strategyUrl);
  await expect(page.locator(".react-flow__node")).toHaveCount(7);
  await page.locator('.react-flow__node[data-id="fast"]').click();
  await expect(page.getByLabel("Период, свечей", { exact: true })).toHaveValue(
    "18",
  );
  await page.goto(runUrl);
  await page.getByTestId("publish-result").click();
  await page.getByTestId("confirm-publish").click();
  await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 90_000 });
  await page.goto("/community");
  await expect(
    page.getByText("Проверка полного пути · SMA").first(),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Проверка полного пути · SMA/ })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: /Создать приватную копию/ }).click();
  await expect(page).toHaveURL(/\/builder\//);
  expect(page.url()).not.toBe(strategyUrl);
  await expect(page.locator(".react-flow__node")).toHaveCount(7);
  await mobileViewport(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.screenshot({ path: screenshot("builder-mobile.png"), fullPage: true });
  expect(errors).toEqual([]);
});

test("Preferences persist and every secondary workspace is honest and responsive", async ({
  page,
}) => {
  await demo(page);
  await page.goto("/settings");
  await page.getByTestId("locale-switch").click();
  await expect(
    page.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Mineral", exact: true }).click();
  await page.getByLabel("Display timezone").selectOption("Europe/Minsk");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Display timezone")).toHaveValue("Europe/Minsk");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({
    path: screenshot("settings-light.png"),
    fullPage: true,
  });
  for (const route of [
    "/ml",
    "/intelligence",
    "/bots",
    "/integrations",
    "/community",
    "/dashboard",
  ]) {
    await page.goto(route);
    await expect(page.locator("h1").first()).toBeVisible();
    await expect(page.locator(".error-panel")).toHaveCount(0);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/dashboard");
  await page.getByTestId("mobile-menu").click();
  await page.getByRole("link", { name: "Integrations", exact: true }).click();
  await expect(page).toHaveURL(/\/integrations$/);
  await expect(page.locator("h1")).toContainText("Integration center");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: screenshot("integrations-mobile.png"),
    fullPage: true,
  });
});

test("A local account can register, log out and log in with its saved profile", async ({
  page,
}) => {
  const email = `browser-${Date.now()}@example.test`;
  const password = "Local-test-only-27!";
  await page.goto("/auth");
  await page.getByRole("button", { name: "Регистрация", exact: true }).click();
  await page.getByLabel("Имя", { exact: true }).fill("Проверка аккаунта");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Создать аккаунт", exact: true })
    .click();
  await expect(page).toHaveURL(/\/onboarding$/);
  await page.getByTestId("locale-switch").click();
  await page
    .getByRole("link", { name: "Explore the workspace first", exact: true })
    .click();
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await expect(page).toHaveURL(/\/(auth)?$/);
  await page.goto("/auth");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Enter your workspace", exact: true })
    .click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/settings");
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue(
    "Проверка аккаунта",
  );
  await expect(
    page.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();
});
