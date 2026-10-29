"use strict";
// Explicit opt-in: real cached CPU model, isolated profile, synthetic MCP receipts.
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const { constants } = require("node:fs");
const { createRequire } = require("node:module");
const root = path.resolve(__dirname, "../..");
const appRoot = path.resolve(process.env.OTTERDESK_APP_ROOT || path.join(root, "../otterdesk-desktop-app"));
const appRequire = createRequire(path.join(appRoot, "package.json"));

async function main() {
  assert.equal(process.env.CCTV_MONITORING_REAL_MODEL, "1", "Set CCTV_MONITORING_REAL_MODEL=1 to run the cached-model check.");
  const { createConversationModelService } = appRequire("./src/main/services/conversation-model");
  const { conversationModelAssets } = appRequire("./src/main/services/conversation-model-assets");
  const { createConversationAssistantService } = appRequire("./src/main/services/conversation-assistant");
  const { updateLiveMonitoring } = appRequire("./src/main/services/conversation-monitoring");
  const cache = process.env.BLUEPRINT_CONVERSATION_CACHE || path.join(os.homedir(), "Library/Application Support/otterdesk/conversation-model");
  const assets = conversationModelAssets();
  const profile = await fs.mkdtemp(path.join(os.tmpdir(), "cctv-monitoring-prompt-"));
  let model;
  try {
    const target = path.join(profile, "conversation-model");
    const engine = `${assets.engine.release}-${process.platform}-${process.arch}`;
    await fs.mkdir(target);
    await fs.copyFile(path.join(cache, assets.model.name), path.join(target, assets.model.name), constants.COPYFILE_FICLONE);
    await fs.cp(path.join(cache, engine), path.join(target, engine), { recursive: true, mode: constants.COPYFILE_FICLONE });
    model = createConversationModelService({ userDataDir: profile, fetchImpl: (url, options) => {
      assert.equal(new URL(url).hostname, "127.0.0.1", "This test cannot download assets or call a remote model.");
      return fetch(url, options);
    } });
    await model.prepare();
    assert.equal(model.getStatus().state, "ready");
    const assistant = createConversationAssistantService({ modelService: model });
    const declaration = JSON.parse(await fs.readFile(path.join(root, "cctv_operator/extensions/mcp.json"), "utf8")).tools.set_monitoring_instruction;
    const cases = [
      { message: "can you focus on if the person wearing the safety helmet", match: /helmet/i, positive: true },
      { message: "Please focus on people who are not wearing safety helmets.", match: /not wearing|without|missing/i },
      { message: "can you focus on find foreign object on the floor?", match: /floor/i },
      { message: "Watch for problems.", unchanged: true },
      { message: "Did anyone appear without a helmet?", unchanged: true },
      { message: "Did you detect anyone without a helmet earlier?", unchanged: true },
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
        client, interpret: input => assistant.interpretMonitoring(input), wait: async () => {} });
      if (scenario.unchanged) assert.equal(mutations.length, 0, scenario.message);
      else {
        assert.equal(mutations.length, 1, scenario.message);
        assert.equal(mutations[0].analyze_now, true);
        assert.equal(mutations[0].clear, scenario.clear === true);
        if (scenario.clear) assert.equal(mutations[0].instruction, "");
        else assert.match(mutations[0].instruction, scenario.match);
        if (scenario.positive) assert.doesNotMatch(mutations[0].instruction, /not wearing|without|uncovered/i);
        assert.match(result.text, /updated the monitoring goal|restored the saved monitoring goal/);
      }
      process.stdout.write(JSON.stringify({ message: scenario.message, mutations: mutations.length,
        ...(mutations.length ? { instruction: mutations[0].instruction, clear: mutations[0].clear } : {}) }) + "\n");
    }
  } finally { model?.close(); await fs.rm(profile, { recursive: true, force: true }); }
}
main().catch(error => { process.stderr.write(error.message + "\n"); process.exitCode = 1; });
