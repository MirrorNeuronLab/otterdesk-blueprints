import { test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import fs from "node:fs";
import path from "node:path";
const assets = path.resolve(
  import.meta.dirname,
  "../../payloads/domain/workspace_assets",
);
const html = fs
  .readFileSync(assets + "/code-map.html", "utf8")
  .replace(
    "@REPORT_ICONS@",
    fs.readFileSync(assets + "/vendor/lucide-sprite.svg", "utf8"),
  );
async function waitFor(fn) {
  const end = Date.now() + 2000;
  while (!fn()) {
    assert.ok(Date.now() < end, "component state did not settle");
    await new Promise(setImmediate);
  }
}
function boot() {
  const dom = new JSDOM(html, {
    url: "http://localhost/web/index.html",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  const w = dom.window;
  w.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  w.matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  });
  w.HTMLElement.prototype.scrollIntoView = function () {};
  const errors = [];
  w.console.error = (...v) => errors.push(v.join(" "));
  const common=process.env.MN_WEB_REPORT_ASSETS || path.resolve(import.meta.dirname,"../../../../mirror-neuron-set/mn-skills/web_report_skill/src/mn_web_report_skill/assets");
  w.eval(fs.readFileSync(common + "/report-ui.js", "utf8"));
  w.eval(fs.readFileSync(assets + "/report-shell.js", "utf8"));
  const ui = w.ReportUI,
    d = w.document;
  d.addEventListener("report:view", (e) => ui.setView(e.detail.view));
  d.addEventListener("report:dismiss", () => ui.setInspectorOpen(false));
  ui.ready();
  const key = (el, name) =>
    el.dispatchEvent(
      new w.KeyboardEvent("keydown", {
        key: name,
        bubbles: true,
        cancelable: true,
      }),
    );
  return { dom, w, d, ui, key, errors };
}
test("real dropdown supports keyboard navigation, dismissal and focus restoration", async () => {
  const { dom, d, key, errors } = boot();
  const trigger = d.getElementById("report-actions-trigger");
  key(trigger, "ArrowDown");
  await waitFor(() => d.querySelector("[role=menuitem]"));
  await waitFor(() => d.activeElement?.getAttribute("role") === "menuitem");
  assert.match(d.activeElement.textContent, /Export report/);
  key(d.activeElement, "ArrowDown");
  await waitFor(() => /Report details/.test(d.activeElement.textContent));
  key(d.activeElement, "Escape");
  await waitFor(() => !d.querySelector("[role=menu]"));
  await waitFor(() => d.activeElement === trigger);
  assert.deepEqual(errors, []);
  dom.window.close();
});
test("non-modal Sheet has a valid title and nested menu Escape preserves evidence", async () => {
  const { dom, d, ui, key, errors } = boot();
  ui.setInspectorTitle("Evidence test");
  ui.setInspectorOpen(true);
  const sheet = d.getElementById("graph-inspector");
  assert.equal(sheet.getAttribute("role"), "dialog");
  assert.equal(sheet.getAttribute("aria-modal"), "false");
  assert.equal(
    d.getElementById(sheet.getAttribute("aria-labelledby")).textContent,
    "Evidence test",
  );
  assert.equal(d.querySelector("[data-slot=sheet-overlay]"), null);
  key(d.getElementById("report-actions-trigger"), "ArrowDown");
  await waitFor(() => d.querySelector("[role=menuitem]"));
  key(d.querySelector("[role=menuitem]"), "Escape");
  await waitFor(() => !d.querySelector("[role=menu]"));
  assert.ok(d.getElementById("graph-inspector"));
  d.getElementById("inspector-close").click();
  await waitFor(() => !d.getElementById("graph-inspector"));
  assert.deepEqual(errors, []);
  dom.window.close();
});
test("Tabs reveal extra views and support Home and End", () => {
  const { dom, d, ui, key, errors } = boot();
  ui.setView("review");
  key(d.getElementById("tab-review"), "End");
  assert.equal(
    d.getElementById("tab-evidence").getAttribute("aria-selected"),
    "true",
  );
  assert.equal(d.activeElement.id, "tab-evidence");
  assert.equal(
    d.querySelector("[data-slot=collapsible-content]").hidden,
    false,
  );
  key(d.activeElement, "Home");
  assert.equal(
    d.getElementById("tab-overview").getAttribute("aria-selected"),
    "true",
  );
  assert.equal(d.querySelector("[data-slot=collapsible-content]").hidden, true);
  assert.deepEqual(errors, []);
  dom.window.close();
});
test("NativeSelect values survive and actual Button/Textarea preserve prompt bytes", () => {
  const { dom, d, ui, errors } = boot();
  const scope = d.getElementById("network-scope");
  assert.equal(scope.value, "connected");
  assert.equal(scope.dataset.slot, "native-select");
  assert.ok(scope.querySelector("[value=all]"));
  assert.equal(d.getElementById("search").dataset.slot, "input");
  ui.setInspectorOpen(true);
  const host = d.getElementById("inspector-content");
  host.innerHTML =
    '<button data-copy="test-prompt">Copy prompt</button><textarea id="test-prompt" readonly></textarea>';
  const text = "source <name> & evidence\nExact saved prompt: $value `code`";
  host.querySelector("textarea").value = text;
  ui.enhance(host);
  assert.equal(host.querySelector("button").dataset.slot, "button");
  assert.equal(host.querySelector("textarea").dataset.slot, "textarea");
  assert.equal(host.querySelector("textarea").value, text);
  assert.deepEqual(errors, []);
  dom.window.close();
});
test("Graph menu uses command bindings and shows unavailable change framing", async () => {
  const { dom, d, ui, key, errors } = boot();
  let fits = 0;
  ui.bindGraphCommands({ "zoom-reset": () => fits++ });
  ui.setGraphMode(true, true);
  ui.setGraphChanges(false, "No comparable changes displayed");
  const trigger = [...d.querySelectorAll("button")].find(
    (b) => b.textContent === "Graph actions",
  );
  key(trigger, "ArrowDown");
  await waitFor(() => d.getElementById("zoom-changes"));
  assert.equal(
    d.getElementById("zoom-changes").getAttribute("aria-disabled"),
    "true",
  );
  assert.match(
    d.getElementById("change-zoom-note").textContent,
    /No comparable/,
  );
  d.getElementById("zoom-reset").click();
  assert.equal(fits, 1);
  await waitFor(() => !d.querySelector("[role=menu]"));
  assert.deepEqual(errors, []);
  dom.window.close();
});
