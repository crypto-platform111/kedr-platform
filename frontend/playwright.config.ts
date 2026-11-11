import { defineConfig } from "@playwright/test";

const networkTimeout = Number(process.env.KEDR_E2E_NETWORK_TIMEOUT_MS || 15_000);
if (!Number.isInteger(networkTimeout) || networkTimeout < 1_000 || networkTimeout > 120_000)
  throw new Error("KEDR_E2E_NETWORK_TIMEOUT_MS must be between 1000 and 120000");

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: process.env.KEDR_E2E_NETWORK_TIMEOUT_MS ? 300_000 : 120_000,
  expect: { timeout: networkTimeout },
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
    actionTimeout: networkTimeout,
  },
});
