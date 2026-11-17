import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", testMatch: "public-site.spec.ts", workers: 1,
  timeout: 60000, reporter: [["list"]],
  use: { baseURL: process.env.SITE_E2E_BASE_URL ?? "http://127.0.0.1:13003/CareerPilot/", channel: "chrome", screenshot: "only-on-failure", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    { name: "tablet", use: { viewport: { width: 768, height: 1024 } } },
    { name: "mobile", use: { viewport: { width: 375, height: 812 } } },
  ],
});
