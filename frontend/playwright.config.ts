import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", testMatch: "**/*.spec.ts", timeout: 60000,
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure", channel: "chromium" },
  projects: [{ name: "chromium", use: {...devices["Desktop Chrome"]} }],
  webServer: {command: "npm run dev", url: "http://127.0.0.1:3000", reuseExistingServer: !process.env.CI}
});
