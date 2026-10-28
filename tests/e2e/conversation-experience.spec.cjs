"use strict";
const fs = require("node:fs/promises");
const { readFileSync, constants } = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { createRequire } = require("node:module");
const appRoot = process.env.OTTERDESK_APP_ROOT;
if (!appRoot || !process.env.OTTERDESK_COWORKER_CONTEXT) throw new Error("Run node tests/e2e/run.cjs to prepare the isolated runtime API.");
const appRequire = createRequire(path.join(appRoot, "package.json"));
const { test, expect, _electron: electron } = appRequire("@playwright/test");
const { apiRequest, serviceReady, readRunOutput, cleanupOwnedJobs } = appRequire("./test/coworker/runtime.cjs");
const { completeSetup, status, verifyServiceWebUi } = appRequire("./test/coworker/gui.ts");
const { createSyntheticInputs } = appRequire("./test/coworker/inputs.cjs");
const { startSyntheticRtspStream } = appRequire("./test/coworker/rtsp.cjs");
const context = JSON.parse(readFileSync(process.env.OTTERDESK_COWORKER_CONTEXT, "utf8"));
if (![undefined, "0", "1"].includes(process.env.BLUEPRINT_E2E_FAKE_LLM)) throw new Error("BLUEPRINT_E2E_FAKE_LLM must be 0 or 1.");
const fakeLlm = process.env.BLUEPRINT_E2E_FAKE_LLM !== "0";
const terminal = new Set(["completed", "failed", "cancelled", "canceled"]);
const cleanupFailure = path.join(path.dirname(process.env.OTTERDESK_COWORKER_CONTEXT), "cleanup-failed");
const catalogRoot = path.resolve(__dirname, "../..");
const inventory = JSON.parse(readFileSync(path.join(catalogRoot, "index.json"), "utf8"));
const cases = inventory.map((folder) => {
  const manifest = JSON.parse(readFileSync(path.join(catalogRoot, folder, "manifest.json"), "utf8"));
  const welcome = JSON.parse(readFileSync(path.join(catalogRoot, folder, "extensions/ui.json"), "utf8")).setup_guide.introduction;
  const outputs = JSON.parse(readFileSync(path.join(catalogRoot, folder, manifest.contracts), "utf8")).outputs;
  const reportNames = [...new Set((outputs.artifacts || [])
    .filter((item) => item.required !== false && item.optional !== true && item.path.endsWith(".md"))
    .map((item) => path.posix.basename(item.path)))];
  const published = context.blueprints.find((item) => item.id === manifest.id);
  if (!published) throw new Error(`Runtime catalog omitted ${folder}.`);
  return { ...published, folder, welcome, reportNames };
});

async function copyConversationAssets(profile) {
  const cache = process.env.BLUEPRINT_CONVERSATION_CACHE || path.join(os.homedir(), "Library/Application Support/otterdesk/conversation-model");
  const assets = appRequire("./src/main/services/conversation-model-assets").conversationModelAssets();
  const destination = path.join(profile, "conversation-model");
  await fs.mkdir(destination, { recursive: true });
  // Clone cached bytes into the test profile; normal production hash checking
  // and the real llama-server still run. Never download or alter user assets.
  await fs.copyFile(path.join(cache, assets.model.name), path.join(destination, assets.model.name), constants.COPYFILE_FICLONE);
  const engine = `${assets.engine.release}-${process.platform}-${process.arch}`;
  await fs.cp(path.join(cache, engine), path.join(destination, engine), { recursive: true, mode: constants.COPYFILE_FICLONE });
}

async function conversationSnapshot(page, id) {
  return page.evaluate(async (id) => {
    const conversation = await window.otterdesk.listWorkerConversation(id);
    const setup = await window.otterdesk.getWorkerSetup(id);
    return { conversation, setup };
  }, id);
}

function replies(snapshot) {
  return [...(snapshot.conversation.messages || []), ...(snapshot.setup.turns || [])]
    .filter((message) => ["worker", "assistant"].includes(message.role) && message.text);
}

async function ipcFailure(diagnostics, since, channel) {
  const log = await fs.readFile(path.join(path.dirname(diagnostics), "logs/otterdesk-main.log"), "utf8").catch((error) => { if (error.code === "ENOENT") return ""; throw error; });
  return log.split("\n").filter(Boolean).map((line) => JSON.parse(line)).find((item) =>
    item.event === "ipc.error" && Date.parse(item.timestamp) >= since && channel.test(item.context?.channel || ""));
}

async function ask(page, id, question, observations, diagnostics) {
  // The normal dismiss control is needed: the persistent hiring notice can
  // otherwise cover the Send button. Keep that UI finding in the review.
  const hiringNotice = page.getByRole("button", { name: /^Dismiss .+ is on your team$/ });
  if (await hiringNotice.isVisible()) await hiringNotice.click();
  const current = await conversationSnapshot(page, id);
  const pending = current.setup.fields.find((field) => field.key === current.setup.nextFieldKey);
  if (pending?.secret) throw new Error(`Setup Chat is unavailable while the secure ${pending.label} answer is pending.`);
  const input = page.getByRole("region", { name: "Conversation input", exact: true });
  const message = input.getByRole("tab", { name: "Message", exact: true });
  if (await message.isVisible()) await message.click();
  const composer = page.getByRole("textbox", { name: "Ask this co-worker", exact: true });
  await expect(composer).toBeEnabled({ timeout: 180000 });
  const before = await conversationSnapshot(page, id);
  const previous = new Set(replies(before).map((item) => item.id));
  const attemptedAt = Date.now();
  const observation = { question, answers: [], status: "waiting" };
  observations.push(observation);
  await composer.fill(question);
  const send = input.getByRole("button", { name: /^Send message to / });
  await expect(send).toBeEnabled({ timeout: 180000 });
  await send.click();
  let after, responseState;
  await expect.poll(async () => {
    const drafts = await fs.readFile(diagnostics, "utf8").catch((error) => { if (error.code === "ENOENT") return ""; throw error; });
    const rejected = drafts.split("\n").filter(Boolean).map((line) => JSON.parse(line))
      .find((item) => item.timestamp >= attemptedAt && item.invalidKeys.length);
    if (rejected) { observation.status = "invalid_setup_draft"; observation.invalidKeys = rejected.invalidKeys; return "invalid_setup_draft"; }
    const failure = await ipcFailure(diagnostics, attemptedAt, /workers:.*(setup|conversation)/);
    if (failure) { observation.status = "rejected"; observation.errorCode = failure.error?.code; observation.error = failure.error?.message || "Conversation request failed."; return "rejected"; }
    after = await conversationSnapshot(page, id);
    responseState = replies(after).some((item) => !previous.has(item.id)) ? "answered" : "waiting";
    return responseState;
  }, { timeout: 150000, intervals: [500, 1000] }).not.toBe("waiting");
  if (observation.status === "invalid_setup_draft") throw new Error(`Help reply proposed undeclared settings: ${observation.invalidKeys.join(", ")}`);
  if (observation.status === "rejected") throw new Error(observation.error);
  const answer = replies(after).filter((item) => !previous.has(item.id)).map((item) => item.text);
  observation.answers = [...new Set(answer)];
  observation.status = "answered";
  if (observation.answers.some((text) => /^Simulated model response[.!]?$/i.test(text.trim()))) {
    observation.status = "placeholder";
    throw new Error("The runtime's fake model returned a placeholder rather than an explanation.");
  }
  expect(observation.answers.join("\n"), "Routine help should not expose internal configuration keys")
    .not.toMatch(/\bsampleAvailable\b|\b(?:inputs\.payload|outputs\.folder_path|document_sources\.folder_path)\b/);
  expect(after.setup.values, "Help must preserve confirmed setup values").toEqual(before.setup.values);
  expect(after.setup.mode, "A help question must not select an input source").toBe(before.setup.mode);
  expect(after.setup.fields.map(({ key, met }) => ({ key, met })), "Help must not confirm an existing default answer")
    .toEqual(before.setup.fields.map(({ key, met }) => ({ key, met })));
  const drafts = await fs.readFile(diagnostics, "utf8").catch((error) => { if (error.code === "ENOENT") return ""; throw error; });
  const drafted = drafts.split("\n").filter(Boolean).map((line) => JSON.parse(line)).filter((item) => item.timestamp >= attemptedAt);
  for (const item of drafted) {
    expect(item.requestedKeys, "An explanation must not draft even an unchanged setting").toEqual([]);
    expect(item.mode, "An explanation must not select a mode").toBeNull();
  }
  return after;
}

async function screenshotAtWidths(app, page, testInfo, phase) {
  for (const width of [1440, 1180, 1440]) {
    await app.evaluate(({ BrowserWindow }, width) => BrowserWindow.getAllWindows()[0].setSize(width, 900), width);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.getByRole("region", { name: "Conversation input", exact: true })).toBeInViewport();
    if (width === 1180) await page.screenshot({ path: testInfo.outputPath(`${phase}-narrow.png`) });
  }
  await page.screenshot({ path: testInfo.outputPath(`${phase}-wide.png`) });
}

async function reviewRules(page, testInfo) {
  const input = page.getByRole("region", { name: "Conversation input", exact: true });
  const respond = input.getByRole("tab", { name: /^Respond/ });
  if (await respond.isVisible()) await respond.click();
  const dialog = page.getByRole("dialog").filter({ has: page.getByRole("region", { name: "Rules review", exact: true }) });
  const open = input.getByRole("button", { name: /rules/i }).and(input.locator('[aria-haspopup="dialog"]'));
  if (!await dialog.isVisible() && await open.isVisible()) await open.click();
  const retry = dialog.getByRole("region", { name: "Rules review", exact: true }).getByRole("button", { name: "Try again", exact: true });
  if (await retry.isVisible() && await retry.isEnabled()) await retry.click();
  const approve = dialog.getByRole("button", { name: "Approve all", exact: true });
  if (await approve.isVisible() && await approve.isEnabled()) {
    await expect(dialog.getByRole("textbox", { name: "Search rules", exact: true })).toBeVisible();
    await dialog.screenshot({ path: testInfo.outputPath("rules-review.png") });
    await approve.click();
    return true;
  }
  return false;
}

async function preparationSnapshot(ownershipFile) {
  const recorded = await fs.readFile(ownershipFile, "utf8").catch((error) => { if (error.code === "ENOENT") return ""; throw error; });
  const ids = [...new Set(recorded.split("\n").filter(Boolean).map((line) => JSON.parse(line).operationId).filter(Boolean))];
  const operations = [];
  for (const id of ids) {
    const operation = await (await apiRequest(context, `/operations/${encodeURIComponent(id)}`)).json();
    if (operation.kind === "prepare_job") operations.push({ operationId: id, status: operation.status, ...(operation.error?.code ? { code: operation.error.code } : {}) });
  }
  return operations;
}

async function awaitPreparation(ownershipFile) {
  let operations;
  await expect.poll(async () => {
    operations = await preparationSnapshot(ownershipFile);
    return operations.length > 0 && operations.every((item) => ["completed", "failed", "interrupted", "cancelled"].includes(item.status));
  }, { timeout: 30 * 60 * 1000, intervals: [1000] }).toBe(true);
  return operations;
}

for (const blueprint of cases) {
  test(`${blueprint.id}: onboarding, work and result conversation`, async ({}, testInfo) => {
    test.skip(await fs.access(cleanupFailure).then(() => true, () => false), "Prior test cleanup is unresolved; do not overlap Jobs.");
    const profile = await fs.mkdtemp(path.join(os.tmpdir(), "blueprint-experience-profile-"));
    const ownershipFile = path.join(profile, "owned-jobs.jsonl");
    await fs.appendFile(path.join(path.dirname(process.env.OTTERDESK_COWORKER_CONTEXT), "profiles.jsonl"), JSON.stringify({ profile, ownershipFile }) + "\n", { mode: 0o600 });
    const diagnostics = testInfo.outputPath("model-boundary.jsonl");
    const observations = [];
    const facts = { blueprintId: blueprint.id, domainMode: fakeLlm ? "existing fake LLM and skills" : "blueprint LLM configuration and fake skills", conversationModel: "real cached convo_model for desktop replies; Job replies retain runtime mode", stages: [] };
    let app, page, stream, cleanupFailed = false, executionId = "", jobId = "", outcome = "";
    try {
      await copyConversationAssets(profile);
      const inputs = await createSyntheticInputs(testInfo.outputPath("inputs"));
      if (blueprint.id === "cctv_operator") stream = await startSyntheticRtspStream(context.streamHost);
      if (stream) inputs.streamUrl = stream.url;
      app = await electron.launch({
        args: ["-r", path.join(__dirname, "desktop-probe.cjs"), ".", ...(fakeLlm ? ["--fake-llm"] : []), "--fake-skill"], cwd: appRoot,
        env: { ...process.env, HOME: context.homeDir, USERPROFILE: context.homeDir,
          NODE_ENV: "test", MN_ENV: "test", OTTERDESK_MOCK_DATA: "0", MN_HOME: context.mnHome,
          MN_BLUEPRINT_SOURCE: "local", MN_BLUEPRINT_LOCAL: context.catalogDir,
          OTTERDESK_MIRROR_NEURON_API_BASE_URL: context.apiBaseUrl, OTTERDESK_MIRROR_NEURON_API_TOKEN: context.token,
          OTTERDESK_TEST_USER_DATA_DIR: profile, OTTERDESK_LOG_DIR: testInfo.outputPath("logs"), OTTERDESK_LOG_TO_STDOUT: "0",
          OTTERDESK_DISABLE_MIRROR_NEURON_AUTO_INSTALL: "1", OTTERDESK_COWORKER_API_ORIGIN: new URL(context.apiBaseUrl).origin,
          OTTERDESK_COWORKER_OWNERSHIP_FILE: ownershipFile, OTTERDESK_EXPERIENCE_PROBE_FILE: diagnostics },
      });
      page = await app.firstWindow();
      page.setDefaultTimeout(120000);
      await app.evaluate(({ dialog }, ctFile) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [ctFile] }); }, inputs.ctFile);
      await expect(page.getByRole("button", { name: "My Team", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Hire a co-worker", exact: true }).last().click();
      await page.getByRole("textbox", { name: "Search co-workers", exact: true }).fill(blueprint.name);
      await page.getByRole("button", { name: `Review work for ${blueprint.name}`, exact: true }).click();
      const hireStartedAt = Date.now();
      await page.getByRole("button", { name: `Hire ${blueprint.name}`, exact: true }).click();
      await page.getByRole("button", { name: "My Team", exact: true }).click();
      const openChat = page.getByRole("button", { name: `Open conversation with ${blueprint.name}`, exact: true });
      const failedHire = page.getByRole("region", { name: `${blueprint.name}: Couldn't hire this co-worker`, exact: true });
      await expect.poll(async () => {
        const failure = await ipcFailure(diagnostics, hireStartedAt, /^workers:install$/);
        if (failure) { facts.hireFailure = { code: failure.error?.code, message: failure.error?.message }; return true; }
        return await failedHire.isVisible() || await openChat.isVisible();
      }, { timeout: 30 * 60 * 1000, intervals: [1000] }).toBe(true);
      if (facts.hireFailure) throw new Error(`${facts.hireFailure.code}: ${facts.hireFailure.message}`);
      if (await failedHire.isVisible()) throw new Error(await failedHire.innerText());
      await openChat.click();
      facts.stages.push("hired");
      await expect(page.getByRole("log", { name: "Conversation messages", exact: true }))
        .toContainText(blueprint.welcome, { timeout: 120000 });
      const hiringNotice = page.getByRole("button", { name: /^Dismiss .+ is on your team$/ });
      if (await hiringNotice.isVisible()) { facts.hiringNoticeOverlaysComposer = true; await hiringNotice.click(); }
      await screenshotAtWidths(app, page, testInfo, "onboarding");
      facts.conversationFailures = [];
      try {
        await ask(page, blueprint.id, "What do you need from me, can I try a sample, and what will you deliver?", observations, diagnostics);
        facts.stages.push("onboarding_question_answered");
      } catch (error) {
        facts.conversationFailures.push({ stage: "onboarding", message: error.message });
      }
      await fs.writeFile(testInfo.outputPath("experience.json"), JSON.stringify({ ...facts, observations }, null, 2));
      await screenshotAtWidths(app, page, testInfo, "guidance");
      // Hiring prepares a Job asynchronously. Observe that exact operation
      // before source selection; a failed preparation must not be retried as
      // an accidental consequence of answering the next setup control.
      facts.initialPreparations = await awaitPreparation(ownershipFile);
      const preparationFailure = facts.initialPreparations.find((item) => item.status !== "completed");
      if (preparationFailure) {
        facts.preparationFailure = preparationFailure;
        try {
          await ask(page, blueprint.id, `Preparation reports ${preparationFailure.code}. What has not started, and what should I check next?`, observations, diagnostics);
        } catch (error) { facts.conversationFailures.push({ stage: "preparation_failure", message: error.message }); }
        await screenshotAtWidths(app, page, testInfo, "preparation-failed");
        throw new Error(`Test-owned Job preparation ${preparationFailure.status}: ${preparationFailure.code}`);
      }
      const respond = page.getByRole("region", { name: "Conversation input", exact: true }).getByRole("tab", { name: /^Respond/ });
      if (await respond.isVisible()) await respond.click();
      await completeSetup(page, blueprint.id, blueprint.name, inputs);
      await expect.poll(async () => {
        const snapshot = await status(page, blueprint.id);
        executionId = snapshot.executionId || snapshot.worker?.executionId || "";
        jobId = snapshot.jobId || snapshot.worker?.jobId || "";
        return Boolean(executionId && jobId);
      }, { timeout: 180000, intervals: [1000] }).toBe(true);
      facts.stages.push("started");
      facts.jobId = jobId;
      facts.executionId = executionId;
      const runtimeJob = await (await apiRequest(context, `/jobs/${encodeURIComponent(jobId)}`)).json();
      facts.runtimeMode = { fakeLlm: runtimeJob.resolved_configuration?.llm?.mode === "fake" && runtimeJob.resolved_configuration?.llm?.provider === "fake", fakeSkills: runtimeJob.resolved_configuration?.execution?.fake_skills === true };
      expect(facts.runtimeMode).toEqual({ fakeLlm, fakeSkills: true });
      await fs.writeFile(testInfo.outputPath("experience.json"), JSON.stringify({ ...facts, observations }, null, 2));
      let approvedRules = false;
      await expect.poll(async () => {
        const run = await (await apiRequest(context, `/runs/${encodeURIComponent(executionId)}`)).json();
        expect(run.job_id).toBe(jobId);
        if (terminal.has(run.status)) { outcome = run.status; return true; }
        if (blueprint.type === "service") {
          const progress = await (await apiRequest(context, `/runs/${encodeURIComponent(executionId)}/workflow-progress`)).json();
          if (serviceReady(progress, executionId)) { outcome = "serving"; return true; }
        }
        await status(page, blueprint.id);
        if (blueprint.id === "code_verifier" && !approvedRules) approvedRules = await reviewRules(page, testInfo);
        return false;
      }, { timeout: 12 * 60 * 1000, intervals: [1000, 2000, 3000] }).toBe(true);
      facts.outcome = outcome;
      await status(page, blueprint.id);
      if (outcome === "serving") {
        facts.output = await verifyServiceWebUi(page, blueprint.id, blueprint.name, executionId);
        const askedAt = Date.now();
        await ask(page, blueprint.id, blueprint.id === "cctv_operator"
          ? "What saved observations are available, and what remains unconfirmed?"
          : "What is the current simulated state, and what would prove that a command completed?", observations, diagnostics);
        const routes = await fs.readFile(testInfo.outputPath("job-question-boundary.jsonl"), "utf8").catch((error) => { if (error.code === "ENOENT") return ""; throw error; });
        facts.liveServiceQuestionDispatched = routes.split("\n").filter(Boolean).map((line) => JSON.parse(line))
          .some((item) => item.timestamp >= askedAt && item.blueprintId === blueprint.id && item.state === "completed");
        expect(facts.liveServiceQuestionDispatched, "A running service must answer through its Job rather than defer until the service finishes")
          .toBe(true);
      } else if (outcome === "completed") {
        await expect(async () => { facts.output = await readRunOutput(context, executionId, apiRequest, blueprint.reportNames); }).toPass({ timeout: 180000, intervals: [1000, 2000, 5000] });
        await expect.poll(async () => { const s = await status(page, blueprint.id); return s.worker?.status || s.status; }, { timeout: 180000, intervals: [1000] }).toBe("completed");
        await ask(page, blueprint.id, blueprint.id === "mac_security_investigator"
          ? "How do I review my local report and its coverage without sharing private log findings in Chat?"
          : "Walk me through the saved result: what matters, what supports it, what is uncertain, and what should I review next?", observations, diagnostics);
        await ask(page, blueprint.id, "Explain the most important limitation in plain language.", observations, diagnostics);
      } else {
        await ask(page, blueprint.id, "What did not complete, what remains available, and what should I check next?", observations, diagnostics);
      }
      await screenshotAtWidths(app, page, testInfo, "result");
      facts.stages.push("result_reviewed");
      expect(outcome).toBe(blueprint.type === "service" ? "serving" : "completed");
      expect(facts.conversationFailures, "Every conversation phase must succeed, even if later work can run").toEqual([]);
    } finally {
      facts.jobId = jobId; facts.executionId = executionId;
      if (page) {
        await page.screenshot({ path: testInfo.outputPath("final.png"), fullPage: true, timeout: 5000 }).catch(() => undefined);
        await fs.writeFile(testInfo.outputPath("visible-conversation.txt"), await page.getByRole("log", { name: "Conversation messages", exact: true }).innerText().catch(() => "Unavailable"));
      }
      await fs.writeFile(testInfo.outputPath("experience.json"), JSON.stringify({ ...facts, observations }, null, 2));
      try {
        await app?.close();
        facts.preparations = await cleanupOwnedJobs(context, ownershipFile);
        await fs.writeFile(testInfo.outputPath("experience.json"), JSON.stringify({ ...facts, observations }, null, 2));
      } catch (error) {
        cleanupFailed = true;
        await fs.writeFile(cleanupFailure, "A test-owned Job could not be reconciled; stop before another launch.");
        await fs.writeFile(path.join(path.dirname(cleanupFailure), "cleanup-context.json"), JSON.stringify({ profile, ownershipFile }), { mode: 0o600 });
        throw error;
      } finally {
        await stream?.close();
        if (!cleanupFailed) await fs.rm(profile, { recursive: true, force: true });
      }
    }
  });
}
