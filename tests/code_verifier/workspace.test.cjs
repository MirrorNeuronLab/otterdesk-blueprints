const { readFileSync } = require("node:fs");
const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const script = readFileSync(require("node:path").join(__dirname,
  "../../code_verifier/payloads/domain/workspace_assets/workspace.js"), "utf8");

function render(view, report, query = "") {
  const content = { innerHTML: "" };
  const location = { hash: "#view=" + view };
  vm.runInNewContext(script + "\nquery=" + JSON.stringify(query) + ";render();", {
    document: {
      getElementById(id) {
        return id === "content" ? content : { textContent: JSON.stringify({ report, sources: {} }) };
      },
      addEventListener() {},
    },
    MNWebReport: { createReport: () => ({ setView() {}, setInspectorOpen() {}, enhance() {}, ready() {} }) },
    location, history: { replaceState(_a, _b, hash) { location.hash = hash; } }, URLSearchParams,
  });
  return content.innerHTML;
}

for (const view of ["overview", "results", "rules"]) {
  test(`${view} explains model failure when there are no results`, () => {
    const html = render(view, { rules: [], results: [], coverage: {
      extraction_gaps: [{ reason: "model_unavailable" }],
    } });
    assert.match(html, /Rule extraction failed/);
    assert.match(html, /No rules were verified/);
    assert.match(html, /1 source section remains unresolved/);
    assert.doesNotMatch(html, /No rules match these filters|result-filters/);
  });
}

test("an empty extraction without a model failure has its own explanation", () => {
  const html = render("results", { rules: [], results: [], coverage: { extraction_gaps: [] } });
  assert.match(html, /No rules to verify/);
  assert.doesNotMatch(html, /Rule extraction failed|No rules match these filters/);
});

test("a filtered nonempty report keeps the filter empty state", () => {
  const html = render("results", { rules: [{ id: "R1", statement: "Keep work" }], results: [
    { rule_id: "R1", status: "unknown", confidence: 0 },
  ], coverage: { extraction_gaps: [] } }, "missing");
  assert.match(html, /result-filters/);
  assert.match(html, /0 of 1 rules shown/);
  assert.match(html, /No rules match these filters/);
  assert.doesNotMatch(html, /Rule extraction failed/);
});
