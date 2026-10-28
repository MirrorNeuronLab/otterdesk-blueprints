"use strict";
const path = require("node:path");
const { createRequire } = require("node:module");
const appRoot = path.resolve(process.env.OTTERDESK_APP_ROOT || path.join(__dirname, "../../../otterdesk-desktop-app"));
const { defineConfig } = createRequire(path.join(appRoot, "package.json"))("@playwright/test");
const output = process.env.BLUEPRINT_E2E_OUTPUT || "/private/tmp/otterdesk-blueprint-experience-e2e";
module.exports = defineConfig({
  testDir: __dirname, testMatch: "conversation-experience.spec.cjs",
  outputDir: path.join(output, "results"), fullyParallel: false, workers: 1,
  retries: 0, maxFailures: 0, timeout: 75 * 60 * 1000,
  expect: { timeout: 30000 },
  reporter: [["list"], ["html", { outputFolder: path.join(output, "report"), open: "never" }]],
  use: { trace: "retain-on-failure", screenshot: "only-on-failure" },
});
