"use strict";
const path = require("node:path");
const { createRequire } = require("node:module");
const appRoot = path.resolve(process.env.OTTERDESK_APP_ROOT || path.join(__dirname, "../../../otterdesk-desktop-app"));
const { defineConfig } = createRequire(path.join(appRoot, "package.json"))("@playwright/test");
module.exports = defineConfig({
  testDir: __dirname, testMatch: "cctv-media.spec.cjs", workers: 1, timeout: 30000,
  outputDir: "/private/tmp/cctv-media-e2e", reporter: "list",
  use: { viewport: { width: 420, height: 900 }, screenshot: "only-on-failure" },
});
