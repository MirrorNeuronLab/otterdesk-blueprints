"use strict";
const path = require("node:path");
const fs = require("node:fs");
const { createHash } = require("node:crypto");
const appRoot = process.env.OTTERDESK_APP_ROOT;

// Observe the real model boundary without changing its inputs or response.
// Keep only static field names, modes and a prompt digest, never draft values,
// credentials, raw model/IPC payloads or source material.
const setup = require(path.join(appRoot, "src/main/services/conversation-setup-assistant"));
const answer = setup.answerSetup;
setup.answerSetup = async (options) => {
  const result = await answer(options);
  const declared = new Set((options.input.context?.fields || []).map((field) => field.key));
  const requested = Object.keys(result.values || {});
  fs.appendFileSync(process.env.OTTERDESK_EXPERIENCE_PROBE_FILE, JSON.stringify({
    kind: "setup_model_draft", timestamp: Date.now(),
    promptSha256: createHash("sha256").update(options.input.prompt || "").digest("hex"),
    profileSha256: createHash("sha256").update(JSON.stringify(options.input.context?.conversationProfile || null)).digest("hex"),
    stage: options.input.context?.stage,
    requestedKeys: requested, invalidKeys: requested.filter((key) => !declared.has(key)),
    mode: result.mode || null,
  }) + "\n");
  return result;
};
const mcp = require(path.join(appRoot, "src/main/services/worker-mcp-client"));
const createClient = mcp.createWorkerMcpClient;
mcp.createWorkerMcpClient = (options) => {
  const client = createClient(options);
  const askJob = client.askJob.bind(client);
  client.askJob = async (worker, question) => {
    const record = (state) => fs.appendFileSync(path.join(path.dirname(process.env.OTTERDESK_EXPERIENCE_PROBE_FILE), "job-question-boundary.jsonl"), JSON.stringify({
      kind: "job_question", timestamp: Date.now(), blueprintId: worker.id, state,
    }) + "\n");
    record("started");
    try { const result = await askJob(worker, question); record("completed"); return result; }
    catch (error) { record("failed"); throw error; }
  };
  return client;
};
// Install the observer before config/service composition captures the helper.
require(path.join(appRoot, "test/coworker/desktop-bootstrap.cjs"));
