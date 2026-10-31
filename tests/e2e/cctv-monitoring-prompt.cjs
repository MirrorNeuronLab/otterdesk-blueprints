"use strict";
// Real authored blueprint contract + desktop controller, synthetic MCP receipts.
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { createRequire } = require("node:module");
const root = path.resolve(__dirname, "../..");
const appRoot = path.resolve(process.env.OTTERDESK_APP_ROOT || path.join(root, "../otterdesk-desktop-app"));
const { updateLiveMonitoring } = createRequire(path.join(appRoot, "package.json"))("./src/main/services/conversation-monitoring");
async function main() {
  const declaration = JSON.parse(await fs.readFile(path.join(root, "cctv_operator/extensions/mcp.json"), "utf8")).tools.set_monitoring_instruction;
  const cases = [
    { message: "can you focus on if the person wearing the safety helmet" },
    { message: "Please focus on people who are not wearing safety helmets." },
    { message: "can you focus on find foreign object on the floor?" },
    { message: "Watch for problems.", unchanged: true },
    { message: "Did anyone appear without a helmet?", unchanged: true },
    { message: "Did you detect anyone without a helmet earlier?", unchanged: true },
    { message: "please find if someone didn't wear the helmet", choice: true },
    { message: "please find if someone didn't wear the helmet", action: "update" },
    { message: "Restore the saved monitoring goal.", clear: true },
  ];
  for (const scenario of cases) {
    const mutations = [];
    const client = { callSupervisionTool: async (_worker, tool, args) => {
      if (tool === "get_capabilities") return { data: { tools: [{ ...declaration, name: "set_monitoring_instruction", _meta: { "mn.mcp.effect": declaration.effect } }] } };
      if (tool === "set_monitoring_instruction") { mutations.push(args); return { status: "accepted", operation_id: "test-op", run_id: "test-run" }; }
      assert.equal(tool, "get_operation_status");
      return { status: "completed", operation_id: "test-op", run_id: "test-run" };
    } };
    const result = await updateLiveMonitoring({ worker: { id: "cctv-test", jobId: "cctv-test" }, message: scenario.message,
      action: scenario.action, client, wait: async () => {} });
    if (scenario.unchanged || scenario.choice) {
      assert.equal(mutations.length, 0, scenario.message);
      if (scenario.choice) assert.equal(result.choice, scenario.message);
    } else {
      assert.equal(mutations.length, 1, scenario.message);
      assert.equal(mutations[0].analyze_now, true);
      assert.equal(mutations[0].clear, scenario.clear === true);
      assert.equal(mutations[0].instruction, scenario.clear ? "" : scenario.message);
      assert.match(result.text, /updated the monitoring goal|restored the saved monitoring goal/);
    }
    process.stdout.write(JSON.stringify({ message: scenario.message, mutations: mutations.length, choice: Boolean(result?.choice) }) + "\n");
  }
}
main().catch(error => { process.stderr.write(error.stack + "\n"); process.exitCode = 1; });
