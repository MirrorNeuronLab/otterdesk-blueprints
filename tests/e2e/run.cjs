"use strict";

// The installed runtime and desktop remain unchanged. This suite uses their
// normal API/IPC/GUI paths with isolated profiles and test-owned Jobs.
const path = require("node:path");
const fs = require("node:fs/promises");
const { spawn } = require("node:child_process");
const { createRequire } = require("node:module");

async function main() {
  const appRoot = path.resolve(process.env.OTTERDESK_APP_ROOT || path.join(__dirname, "../../../otterdesk-desktop-app"));
  const appRequire = createRequire(path.join(appRoot, "package.json"));
  const helpers = appRequire("./test/coworker/runtime.cjs");
  const runtime = await helpers.prepareRuntime(path.resolve(__dirname, "../.."));
  let child;
  const interrupt = () => child?.kill("SIGTERM");
  process.once("SIGINT", interrupt);
  process.once("SIGTERM", interrupt);
  try {
    const output = path.resolve(process.env.BLUEPRINT_E2E_OUTPUT || "/private/tmp/otterdesk-blueprint-experience-e2e");
    await fs.mkdir(output, { recursive: true });
    console.log(`Conversation experience suite includes every published blueprint, including General Assistant. Desktop replies use the cached real CPU conversation model. Job LLM mode: ${process.env.BLUEPRINT_E2E_FAKE_LLM === "0" ? "blueprint configuration" : "fake"}; skills: fake.`);
    const code = await new Promise((resolve, reject) => {
      child = spawn(process.execPath, [appRequire.resolve("@playwright/test/cli"), "test", "--config", path.join(__dirname, "playwright.config.cjs"), ...process.argv.slice(2)], {
        cwd: appRoot, stdio: "inherit", shell: false,
        env: { ...process.env, OTTERDESK_APP_ROOT: appRoot, OTTERDESK_COWORKER_CONTEXT: runtime.contextPath, BLUEPRINT_E2E_OUTPUT: output },
      });
      child.once("error", reject);
      child.once("exit", (code) => resolve(code ?? 1));
    });
    process.exitCode = code;
  } finally {
    process.removeListener("SIGINT", interrupt);
    process.removeListener("SIGTERM", interrupt);
    // The worker process may be interrupted before its test-body finally runs.
    // Reconcile its recorded receipts while the isolated API is still alive.
    const context = JSON.parse(await fs.readFile(runtime.contextPath, "utf8"));
    const profiles = await fs.readFile(path.join(path.dirname(runtime.contextPath), "profiles.jsonl"), "utf8").catch((error) => {
      if (error.code === "ENOENT") return "";
      throw error;
    });
    try {
      for (const line of profiles.split("\n").filter(Boolean)) {
        const owned = JSON.parse(line);
        if (!await fs.access(owned.profile).then(() => true, () => false)) continue;
        await helpers.cleanupOwnedJobs(context, owned.ownershipFile);
        await fs.rm(owned.profile, { recursive: true, force: true });
      }
    } catch (error) {
      await fs.writeFile(path.join(path.dirname(runtime.contextPath), "cleanup-failed"), "Interrupted test cleanup is unresolved.");
      throw error;
    } finally { await runtime.close(); }
  }
}

main().catch((error) => { console.error(error.message); process.exitCode = 1; });
