const { readFileSync } = require("node:fs");
const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const script = readFileSync(
  require("node:path").join(
    __dirname,
    "../../software_verifier_suite/payloads/domain/workspace_assets/workspace.js",
  ),
  "utf8",
);

function render(view, report, query = "", inspectId = "", options = {}) {
  const content = { innerHTML: "" };
  const location = { hash: "#view=" + view };
  vm.runInNewContext(
    script +
      "\nquery=" +
      JSON.stringify(query) +
      ";render();" +
      (inspectId ? `inspectRule(${JSON.stringify(inspectId)});` : "") +
      (options.inspectSource
        ? `inspectSource(${JSON.stringify(options.inspectSource)}, null, {start: 2, end: 2});`
        : ""),
    {
      document: {
        getElementById(id) {
          return id === "content"
            ? content
            : {
                textContent: JSON.stringify({
                  report,
                  sources: {},
                  ...options.data,
                }),
              };
        },
        addEventListener() {},
      },
      MNWebReport: {
        createReport: () => ({
          setView() {},
          setInspectorOpen() {},
          enhance() {},
          ready() {},
          openInspector(_title, html) {
            content.innerHTML = html;
          },
        }),
      },
      location,
      history: {
        replaceState(_a, _b, hash) {
          location.hash = hash;
        },
      },
      URLSearchParams,
    },
  );
  return content.innerHTML;
}

test("each specialist tab renders its returned report and preserves a skip reason", () => {
  const specialists = ["functional", "security", "compatibility", "reliability"].map((id) => ({
    id, label: id, verdict: id === "reliability" ? "SKIPPED" : "PASS",
    document: {
      title: id, summary: id === "reliability" ? "Outside the selected change" : "Completed",
      sections: [{ title: "Evidence", blocks: [{ type: "table", columns: ["Source"],
        rows: [[id + "-<fixture>.json"]] }] }],
    },
  }));
  for (const specialist of specialists) {
    const html = render(specialist.id, { rules: [], results: [], coverage: {}, specialists });
    assert.ok(html.includes(specialist.id + "-&lt;fixture&gt;.json"));
    assert.ok(html.includes(specialist.document.summary));
  }
});

test("the overview stays readable when a specialist ledger is unavailable", () => {
  const html = render("overview", { rules: [], results: [], coverage: {},
    specialists: [{ id: "functional", label: "Functional verifier", verdict: "INCONCLUSIVE" }] });
  assert.match(html, /No rules to verify/);
});

test("a specialist opens the named specification, generated test and implementation in the captured tree", () => {
  const specialist = { id: "functional", label: "Functional verifier", check_ids: ["amount"],
    document: { title: "Functional verifier", summary: "Scoped review",
      sections: [{ id: "review", title: "Does the implementation meet the specification?", blocks: [] }] } };
  const trace = { specialist: "functional", expectation: "Keep the amount.", change: "Passed on both revisions",
    status: "passed", observed: "3 passed.", setup: "Fixed amount.", uncertainty: "One currency.",
    specification: {path:"specs.md",line:3}, test_location: {path:"test_total.py",line:4,symbol:"test_total"},
    locations: [{path:"amount.py",line:2}] };
  const html = render("functional", {rules: [], results: [], coverage: {}, specialists: [specialist],
    specialist_report: {requirement_traces: [trace]}}, "", "", { data:{repositoryPrefix:"repository/",
        sources: {"repository/specs.md":"A specification", "repository/test_total.py":"A test", "repository/amount.py":"A module"}}});
  for (const path of ["specs.md", "test_total.py", "amount.py"]) assert.ok(html.includes('data-path="repository/' + path + '"'));
  assert.match(html, /Generated test/);
  assert.match(html, /Passed on both revisions/);
  const failed = render("functional", {rules: [], results: [], coverage: {}, specialists: [specialist],
    specialist_report: {requirement_traces: [{...trace, status:"failed", change:"Not comparable",
      assertion:{path:"test_total.py",line:7}}]}}, "", "", {data:{sources:{"test_total.py":"Test source"}}});
  assert.match(failed, /Failed assertion/);
  assert.match(failed, /test_total\.py:7/);
});

test("approved rule details link to the specialist that returned the check", () => {
  const report = {
    rules: [{ id: "R1", statement: "Reject empty names", source: {} }],
    results: [{ rule_id: "R1", status: "pass", confidence: 0.8, evidence: [] }],
    coverage: {},
    rule_checks: { R1: ["names"] },
    specialist_report: { checks: [{ id: "names", status: "failed", specialist: "functional" }] },
  };
  const details = () => render("results", report, "", "R1");
  assert.match(details(), /data-action="view" data-id="functional">names · failed<\/button>/);
  report.rule_checks.R1 = [];
  assert.match(details(), /No specialist check was linked to this rule/);
  delete report.rule_checks;
  assert.doesNotMatch(details(), /Specialist checks/);
});

test("coordinator overview shows the candidate commit and links to unresolved rules", () => {
  const report = {
    rules: [{ id: "R1", statement: "Keep stable request IDs" }],
    results: [{ rule_id: "R1", status: "unknown", confidence: 0, evidence: [] }],
    coverage: {}, verdict: "INCONCLUSIVE", attention_rule_ids: ["R1"],
    specialists: [{ id: "functional", label: "Functional verifier", verdict: "PASS" }],
    specialist_report: { plan: { revision: "123456789abc123456789abc", decision: "development" } },
  };
  const html = render("overview", report);
  assert.match(html, /<code>123456789abc<\/code>/);
  assert.match(html, /data-action="filter" data-id="attention">Review 1 rule<\/button>/);
});

for (const view of ["overview", "results", "rules"]) {
  test(`${view} explains model failure when there are no results`, () => {
    const html = render(view, {
      rules: [],
      results: [],
      coverage: {
        extraction_gaps: [{ reason: "model_unavailable" }],
      },
    });
    assert.match(html, /Rule extraction failed/);
    assert.match(html, /No rules were verified/);
    assert.match(html, /1 source section remains unresolved/);
    assert.doesNotMatch(html, /No rules match these filters|result-filters/);
  });
}

test("an empty extraction without a model failure has its own explanation", () => {
  const html = render("results", {
    rules: [],
    results: [],
    coverage: { extraction_gaps: [] },
  });
  assert.match(html, /No rules to verify/);
  assert.doesNotMatch(
    html,
    /Rule extraction failed|No rules match these filters/,
  );
});

test("unknown details preserve evidence and explain the next step without executing source", () => {
  const html = render(
    "results",
    {
      rules: [
        {
          id: "R1",
          statement: "Bound output",
          origin: "custom",
          source: { path: "rules.md", start_line: 1, end_line: 2 },
        },
      ],
      results: [
        {
          rule_id: "R1",
          status: "unknown",
          confidence: 0,
          explanation: "A calling path remains unresolved.",
          reason_code: "parser_gap",
          next_step: "Inspect the unparsed source.",
          evidence: [
            {
              path: "src/a.py",
              start_line: 1,
              end_line: 1,
              quote: "<script>unsafe()</script>",
              sha256: "hash",
            },
          ],
        },
      ],
      coverage: {},
    },
    "",
    "R1",
  );
  assert.match(html, /parser gap/);
  assert.match(html, /Inspect the unparsed source/);
  assert.match(html, /data-start="1" data-end="1".*src\/a.py:1/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});

test("overview separates investigation diagnostics from result counts", () => {
  const html = render("overview", {
    rules: [{ id: "R1", statement: "Bound output" }],
    results: [{ rule_id: "R1", status: "unknown", confidence: 0 }],
    coverage: {},
    diagnostics: {
      model_calls: 8,
      empty_searches: 2,
      unknown_reasons: { reviewer_disagreement: 1 },
    },
  });
  assert.match(html, /8 model calls/);
  assert.match(html, /2 empty searches/);
  assert.match(html, /reviewer disagreement: 1/);
});

test("a filtered nonempty report keeps the filter empty state", () => {
  const html = render(
    "results",
    {
      rules: [{ id: "R1", statement: "Keep work" }],
      results: [{ rule_id: "R1", status: "unknown", confidence: 0 }],
      coverage: { extraction_gaps: [] },
    },
    "missing",
  );
  assert.match(html, /result-filters/);
  assert.match(html, /0 of 1 rules shown/);
  assert.match(html, /No rules match these filters/);
  assert.doesNotMatch(html, /Rule extraction failed/);
});

test("overview counts failures and unknowns together and leads with new regressions", () => {
  const report = {
    rules: ["unknown", "failure", "regression"].map((id) => ({
      id,
      statement: id,
      title: "rule-" + id,
    })),
    results: [
      {
        rule_id: "unknown",
        status: "unknown",
        explanation: "Find the caller.",
      },
      { rule_id: "failure", status: "fail", explanation: "Earlier behavior." },
      {
        rule_id: "regression",
        status: "fail",
        comparison_status: "regression",
        explanation: "The draft now saves.",
        evidence: [{ path: "src/a.py", start_line: 8, end_line: 12 }],
        recommended_check:
          "Cancel and check that the store receives zero writes.",
      },
    ],
    attention_rule_ids: ["regression", "failure", "unknown"],
    comparison: {
      base: { commit: "a".repeat(40) },
      head: { commit: "b".repeat(40) },
      summary: { regression: 1 },
      changes: [{ path: "src/a.py", kind: "modified" }],
    },
    coverage: {},
  };
  const html = render("overview", report, "", "", {
    data: { comparisonLabels: { regression: "New regression" } },
  });
  assert.match(html, /3 rules need attention/);
  assert.ok(html.indexOf("rule-regression") < html.indexOf("rule-failure"));
  assert.match(html, /Source evidence.*src\/a\.py:8–12/);
  assert.match(html, /data-action="source"/);
  assert.match(html, /Suggested check.*Cancel and check/);
});

test("the source inspector highlights the exact cited line and escapes source text", () => {
  const path = "src/save.py";
  const html = render(
    "scope",
    { rules: [], results: [], coverage: {} },
    "",
    "",
    {
      data: {
        sources: {
          [path]: "first\r\n<script>untrusted()</script>\r\nlast\r\n",
        },
      },
      inspectSource: path,
    },
  );
  assert.match(
    html,
    /class="code-line cited-line".*line-number">2<.*&lt;script&gt;untrusted/,
  );
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /View entire file/);
});

test("imported CI shows missing or edited mappings and identifies the proposed commit", () => {
  const html = render("ci", {
    rules: [],
    results: [],
    coverage: {},
    ci_evidence: {
      file: "junit.xml",
      commit: "a".repeat(40),
      sha256: "b".repeat(64),
      checks: [
        {
          rule_id: "EDITED",
          test: "test::case",
          status: "missing",
          mapping: "rule_edited",
        },
      ],
    },
  });
  assert.match(html, /Rule edited after mapping/);
  assert.match(html, /missing/);
  assert.match(html, /a{40}/);
});
