"use strict";
const http = require("node:http");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { createRequire } = require("node:module");
const appRoot = path.resolve(process.env.OTTERDESK_APP_ROOT || path.join(__dirname, "../../../otterdesk-desktop-app"));
const { test, expect } = createRequire(path.join(appRoot, "package.json"))("@playwright/test");
const html = execFileSync("python3", ["-c", "import runpy; print(runpy.run_path('cctv_operator/payloads/domain/media.py')['dashboard_html']())"],
  { cwd: path.resolve(__dirname, "../.."), encoding: "utf8" });

test("shows completed scene analysis and subsequent SSE results without a reload", async ({ page }) => {
  const streams = new Set();
  const server = http.createServer((req, res) => {
    if (req.url === "/") { res.writeHead(200, { "Content-Type": "text/html" }); res.end(html); }
    else if (req.url === "/streams/operator-events") {
      res.writeHead(200, { "Content-Type": "text/event-stream" }); res.flushHeaders();
      streams.add(res); req.on("close", () => streams.delete(res));
    } else { res.writeHead(404); res.end(); }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const send = state => { for (const stream of streams) stream.write(`event: operator-state\ndata: ${JSON.stringify(state)}\n\n`); };
  try {
    await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: "domcontentloaded" });
    await expect.poll(() => streams.size).toBe(1);
    await expect(page.getByRole("region", { name: "Latest scene analysis" })).toBeHidden();
    const state = {
      metrics: { status: "Monitoring", preview: "disabled", "last analyzed": "2026-10-28T23:30:00Z" },
      understanding: { scene_understanding: "A person carries a box along the warehouse aisle.",
        risk_predictions: [{ risk: "The box may obscure the travel path.", visible_evidence: "Box held in front of the person.",
          time_horizon: "Next few steps", recommended_review: "Review the original frames." }],
        uncertainties: ["The person's hands are partially obscured."] },
    };
    send(state);
    await expect(page.getByText(state.understanding.scene_understanding, { exact: true })).toBeVisible();
    await expect(page.getByText(/The box may obscure the travel path/)).toBeVisible();
    await expect(page.getByText(state.understanding.uncertainties[0], { exact: true })).toBeVisible();
    await expect(page.locator("#scene-at")).toHaveAttribute("datetime", state.metrics["last analyzed"]);
    send({ metrics: { ...state.metrics, status: "Analysis delayed" }, warning: "The next sample is processing." });
    await expect(page.locator("#analysis-status")).toHaveText("Analysis delayed");
    await expect(page.getByRole("alert")).toHaveText("The next sample is processing.");
    await expect(page.locator("#scene-understanding")).toHaveText(state.understanding.scene_understanding);
    // Native EventSource reconnects after a transport interruption; a fresh
    // stream must still deliver the next completed account without navigation.
    for (const stream of streams) stream.end();
    await expect.poll(() => streams.size).toBe(0);
    await expect.poll(() => streams.size).toBe(1);
    const malicious = '<img src=x onerror="window.injected=true">';
    state.metrics["last analyzed"] = "2026-10-28T23:31:00Z";
    state.understanding = { scene_understanding: malicious + " A second completed sample. ".repeat(45),
      risk_predictions: [], uncertainties: [], source_profile: "bundled_demo" };
    send(state);
    await expect(page.locator("#scene-understanding")).toHaveText(state.understanding.scene_understanding);
    await expect(page.locator("#scene-understanding img")).toHaveCount(0);
    await expect(page.getByText("No risk forecasts returned for this sample.")).toBeVisible();
    await expect(page.getByText("No uncertainties reported by the model.")).toBeVisible();
    await expect(page.locator("#scene-qualification")).toContainText("Recorded demo playback.");
    for (const width of [260, 900, 260]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    expect(streams.size).toBe(1);
  } finally {
    await page.close();
    for (const stream of streams) stream.end();
    await new Promise(resolve => server.close(resolve));
  }
});
