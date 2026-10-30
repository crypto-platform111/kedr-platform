import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [
    ["list"],
    ["json", { outputFile: "../verification/v02/e2e-results.json" }],
  ],
  outputDir: "../verification/v02/browser-failures",
  use: {
    baseURL: process.env.KEDR_E2E_BASE_URL || "http://127.0.0.1:5173",
    browserName: "chromium",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "off",
    actionTimeout: 15_000,
  },
});
