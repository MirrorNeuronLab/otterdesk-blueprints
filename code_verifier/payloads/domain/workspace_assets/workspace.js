"use strict";
const data = JSON.parse(document.getElementById("report-data").textContent);
const R = data.report,
  sources = data.sources;
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const byRule = new Map(R.rules.map((rule) => [rule.id, rule]));
const results = new Map(R.results.map((result) => [result.rule_id, result]));
const extractionGaps = R.coverage.extraction_gaps || [];
let view = "overview",
  filter = "all",
  query = "";
const label = (status) =>
  ({ pass: "Pass", fail: "Fail", unknown: "Unknown" })[status] || "Unknown";
const button = (text, action, id = "", primary = false) =>
  `<button data-action="${esc(action)}" data-id="${esc(id)}" ${primary ? 'data-variant="primary"' : ""}>${esc(text)}</button>`;
const counts = Object.fromEntries(
  ["pass", "fail", "unknown"].map((status) => [
    status,
    R.results.filter((result) => result.status === status).length,
  ]),
);
const ui = MNWebReport.createReport({
  tabs: [
    ["overview", "Overview", "content"],
    ["results", "Rule results", "content"],
    ["rules", "Approved rules", "content"],
    ["scope", "Scope & limits", "content"],
  ],
  navigationLabel: "Verification views",
  actions: [
    {
      id: "report",
      label: "Export report",
      icon: "download",
      href: "../report.md",
    },
    { id: "rules", label: "Editable rules", href: "../rules.md" },
    { id: "details", label: "Report details", icon: "info" },
  ],
  onView(next) {
    view = next;
    render();
  },
  onAction(_id, trigger) {
    ui.openInspector(
      "Report details",
      `<p>Static AI review of the captured implementation.</p><p>${R.rules.length} approved rules · ${Object.keys(sources).length} captured files</p><details><summary>Source identity</summary><p>${esc(R.snapshot_id)}</p><p>Rules were approved before verification. This report cannot approve or modify them.</p></details>`,
      trigger,
    );
  },
});
function selected() {
  return R.rules.filter(
    (rule) =>
      (filter === "all" || results.get(rule.id)?.status === filter) &&
      `${rule.id} ${rule.statement}`
        .toLocaleLowerCase()
        .includes(query.toLocaleLowerCase()),
  );
}
function emptyRules() {
  const modelFailed = extractionGaps.some((gap) => gap.reason === "model_unavailable");
  return `<section class="card" role="status"><h3>${modelFailed ? "Rule extraction failed" : "No rules to verify"}</h3><p>${modelFailed ? "The model could not extract rules. No rules were verified. Start a new run after the model is ready." : "No software rules were identified. Review the source scope and custom rules before starting a new run."}</p>${extractionGaps.length ? `<p>${extractionGaps.length} source section${extractionGaps.length === 1 ? " remains" : "s remain"} unresolved.</p>` : ""}${button("Review source coverage", "view", "scope", true)}</section>`;
}
function diagnostics() {
  const reasons = R.diagnostics?.unknown_reasons || {};
  return `<details><summary>Investigation details</summary><p>${Number(R.diagnostics?.model_calls || 0)} model calls · ${Number(R.diagnostics?.empty_searches || 0)} empty searches</p>${Object.entries(reasons).map(([reason, count]) => `<p>${esc(reason.replaceAll("_", " "))}: ${Number(count)}</p>`).join("")}</details>`;
}
function overview() {
  if (!R.rules.length)
    return `<h2>Overview</h2>${emptyRules()}`;
  const pending = counts.fail || counts.unknown;
  const first = R.rules.find(
    (rule) =>
      results.get(rule.id)?.status === (counts.fail ? "fail" : "unknown"),
  );
  return `<h2>Overview</h2><div class="verification-summary">${["fail", "unknown", "pass"].map((status) => `<button class="count-link" data-action="filter" data-id="${status}"><strong>${counts[status]}</strong><span>${label(status)}</span></button>`).join("")}</div>
    <section class="card"><p class="qualification">${pending ? "Next review" : "Review complete within this scope"}</p><h3>${counts.fail ? "Inspect rules the implementation does not support" : counts.unknown ? "Resolve rules with insufficient evidence" : "Review the source-backed results"}</h3><p>${pending ? `${pending} rule${pending === 1 ? " needs" : "s need"} attention. Read the source and reasoning before deciding what to change.` : "Pass reflects the inspected source; runtime behavior remains unverified."}</p>${first ? button("Review first result", "rule", first.id, true) : button("View rule results", "view", "results", true)}</section>
    ${diagnostics()}<p class="qualification">${R.rules.length} approved rules · Static review · Confidence is an uncalibrated AI assessment.</p><button class="text-action" data-action="view" data-id="scope">Coverage and limitations →</button>`;
}
function resultRows() {
  if (!R.rules.length) return `<h2>Rule results</h2>${emptyRules()}`;
  const rows = selected();
  return `<h2>Rule results</h2><form id="result-filters" class="toolbar"><label>Find a rule<input id="rule-query" type="search" placeholder="Rule ID or statement" value="${esc(query)}"></label><label>Status<select id="rule-status">${["all", "fail", "unknown", "pass"].map((status) => `<option value="${status}" ${status === filter ? "selected" : ""}>${status === "all" ? "All results" : label(status)}</option>`).join("")}</select></label><button type="submit">Apply</button></form><p class="qualification">${rows.length} of ${R.rules.length} rules shown</p>
    ${
      rows.length
        ? `<div class="table-wrap"><table><thead><tr><th>Rule</th><th>Status</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>${rows
            .map((rule) => {
              const result = results.get(rule.id);
              return `<tr><td><small>${esc(rule.id)}</small><p>${esc(rule.statement)}</p></td><td>${label(result.status)}</td><td>${Number(result.confidence).toFixed(2)}</td><td>${button("Inspect result", "rule", rule.id)}</td></tr>`;
            })
            .join("")}</tbody></table></div>`
        : "<p>No rules match these filters.</p>"
    }`;
}
function ruleBook() {
  if (!R.rules.length) return `<h2>Approved rules</h2>${emptyRules()}`;
  return `<h2>Approved rules</h2><p class="qualification">These exact rules were approved before source verification. Edit rules.md and start a new reviewed run to change them.</p>${R.rules.map((rule) => `<button class="report-row" data-action="rule" data-id="${esc(rule.id)}"><span><small>${esc(rule.id)} · ${esc(rule.origin)}</small><span>${esc(rule.statement)}</span></span><span aria-hidden="true">→</span></button>`).join("") || "<p>No approved rules in this report.</p>"}`;
}
function scope() {
  const omitted = R.coverage.omitted || [];
  const gaps = extractionGaps.length ? `<section class="card"><h3>Unresolved source sections</h3><p>Requirements in these sections were not fully extracted. No conformance claim covers them.</p>${extractionGaps.map(gap => `<p>${button(`${gap.path}:${gap.start_line}–${gap.end_line}`, "source", gap.path)} · ${esc(gap.reason)}</p>`).join("")}</section>` : "";
  return `<h2>Scope & limits</h2>${gaps}<p>${Object.keys(sources).length} captured UTF-8 files. ${omitted.length} entries excluded; an excluded folder represents its whole subtree.</p><p>Repository code and tests were not executed. Pass means the inspected implementation supports the rule within this scope. Missing matches do not establish absence.</p><p>Confidence is an uncalibrated AI assessment, capped at 0.85 for static judgments. Unknown requires more evidence or human review.</p><details><summary>Extraction exclusions</summary><pre>${esc(JSON.stringify(R.coverage.documentation_selection || {}, null, 2))}</pre><pre>${esc(JSON.stringify(R.coverage.excluded_candidates || [], null, 2))}</pre></details><details><summary>Excluded entries</summary><pre>${esc(JSON.stringify(omitted, null, 2))}</pre></details><details><summary>Extraction coverage</summary><pre>${esc(JSON.stringify(R.coverage.documents, null, 2))}</pre></details><details><summary>Captured files</summary>${Object.keys(
    sources,
  )
    .map((path) => `<p>${button(path, "source", path)}</p>`)
    .join(
      "",
    )}</details><p class="qualification">The structured capture and static-analysis.json retain the full inventory and parser gaps.</p>`;
}
function render() {
  ui.setView(view);
  ui.setInspectorOpen(false);
  const host = document.getElementById("content");
  const gapNotice = extractionGaps.length && R.rules.length ? `<section class="card" role="status"><h2>Partial extraction</h2><p>${extractionGaps.length} source sections remain unresolved. This report assesses the approved candidate rules; missing requirements remain unknown.</p>${button("Review source coverage", "view", "scope")}</section>` : "";
  host.innerHTML = gapNotice + (
    { overview, results: resultRows, rules: ruleBook, scope }[view] || overview
  )();
  ui.enhance(host);
  const hash = "#view=" + view;
  if (location.hash !== hash) history.replaceState(null, "", hash);
}
function inspectRule(id, trigger) {
  const rule = byRule.get(id),
    result = results.get(id);
  if (!rule || !result) return;
  ui.openInspector(
    rule.id,
    `<p class="rule-statement">${esc(rule.statement)}</p><p><strong>${label(result.status)}</strong> · Confidence ${Number(result.confidence).toFixed(2)}</p><p>${esc(result.explanation)}</p>${result.reason_code ? `<p class="qualification">${esc(result.reason_code.replaceAll("_", " "))}</p><p>${esc(result.next_step)}</p>` : ""}<h3>Inspected evidence</h3>${result.evidence.map((ref) => `<section class="evidence-record"><p>${esc(ref.path)}:${ref.start_line}–${ref.end_line}</p><blockquote>${esc(ref.quote)}</blockquote>${button("Read captured source", "source", ref.path)}<details><summary>Exact source identity</summary><p>SHA-256 ${esc(ref.sha256)}</p></details></section>`).join("") || "<p>No admissible implementation evidence. More evidence is needed.</p>"}<details><summary>Rule origin</summary><p>${esc(rule.origin)}</p><p>${esc(rule.source.path)}:${rule.source.start_line}–${rule.source.end_line}</p><blockquote>${esc(rule.source.quote || "")}</blockquote></details><p class="qualification">Static review · Tests not executed · This result is not runtime proof.</p>`,
    trigger,
  );
}
function inspectSource(path, trigger) {
  if (!Object.hasOwn(sources, path)) return;
  ui.openInspector(
    path,
    `<p class="qualification">Captured source; the current checkout may differ.</p><pre class="source-lines">${esc(sources[path])}</pre>`,
    trigger,
  );
}
document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const { action, id } = target.dataset;
  if (action === "rule") inspectRule(id, target);
  else if (action === "source") inspectSource(id, target);
  else if (action === "view") {
    view = id;
    render();
  } else if (action === "filter") {
    filter = id;
    query = "";
    view = "results";
    render();
  }
});
document.addEventListener("submit", (event) => {
  if (event.target.id !== "result-filters") return;
  event.preventDefault();
  query = document.getElementById("rule-query").value;
  filter = document.getElementById("rule-status").value;
  render();
});
const saved = new URLSearchParams(location.hash.slice(1)).get("view");
if (["overview", "results", "rules", "scope"].includes(saved)) view = saved;
ui.ready();
render();
