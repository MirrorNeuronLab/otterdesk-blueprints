"use strict";
window.loadArchitectureData(
  ["static-code.json", "function-evolution.json", "report.json"],
  (data) => {
    const F = data["static-code.json"],
      H = data["function-evolution.json"],
      R = data["report.json"];
    if (
      F.schema_version !== "mn.static_code.v1" ||
      H.schema_version !== "mn.function_evolution.v1" ||
      R.schema_version !== "mn.architecture.catalog_report.v1"
    )
      throw new Error("Unsupported report schema.");
    if (F.snapshot_id !== H.snapshot_id || F.snapshot_id !== R.snapshot)
      throw new Error("The selected files belong to different snapshots.");
    const $ = (id) => document.getElementById(id);
    const esc = (x) =>
      String(x ?? "").replace(
        /[&<>"']/g,
        (c) =>
          ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          })[c],
      );
    const frames = H.timeline?.frames || [],
      defs = H.timeline?.definitions || {},
      historicalCalls = H.timeline?.calls || {};
    let view = "overview",
      level = "file",
      focus = "",
      time = Math.max(0, frames.length - 1),
      baseline = "0",
      timer = null,
      inspectorOpen = false,
      inspectorReturn = null,
      reportPanel = null;
    // Local Lucide sprite: icon names below are fixed UI constants, never source data.
    const icon = (name) =>
      `<svg class="report-icon" width="16" height="16" aria-hidden="true" focusable="false"><use href="#report-icon-${name}"></use></svg>`;
    const playbackLabel = (playing) => window.ReportUI.setPlaying(playing);
    const edgeKey = (e) => [e.source, e.target, e.kind].join("\0");
    const sourcePath = (id) => id.split("::")[0];
    const statusLabel = (value) =>
      String(value || "Needs review")
        .replace(/_/g, " ")
        .replace(/^./, (c) => c.toUpperCase());
    const metric = (value, label, note = "") =>
      `<div class="metric"><strong>${Number(value).toLocaleString()}</strong><span>${esc(label)}</span>${note ? `<small>${esc(note)}</small>` : ""}</div>`;
    const button = (text, value, kind = level) =>
      `<button data-focus="${esc(value)}" data-level="${kind}">${esc(text)}</button>`;
    const table = (headers, rows) =>
      rows.length
        ? `<div class="table-scroll"><table><thead><tr>${headers.map((h) => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
        : '<p class="qualification">No matching records in this scope.</p>';
    const current = {
      functions: F.functions,
      calls: F.calls.filter((c) => c.target),
      components: F.components,
      edges: F.component_edges,
      gaps: F.components.filter((f) => f.status !== "parsed").map((f) => f.id),
      revision: H.revision,
      cycles: F.cycles,
      evidence: F.component_evidence,
    };
    const cache = new Map();
    function state(index) {
      if (index === null) return current;
      if (cache.has(index)) return cache.get(index);
      const frame = frames[index],
        functions = frame.nodes.map((n) => defs[n]);
      const value = {
        functions,
        calls: frame.calls.map((c) => historicalCalls[c]),
        components: frame.files.map(([id, status, physical_lines]) => ({
          physical_lines,
          id,
          status,
        })),
        edges: frame.component_edges.map(([source, target, kind, sites]) => ({
          source,
          target,
          kind,
          sites,
        })),
        gaps: frame.gaps,
        revision: frame.commit,
        cycles: frame.cycles || [],
        evidence: (frame.component_evidence || []).map(
          (key) => H.timeline.relationships[key],
        ),
      };
      cache.set(index, value);
      return value;
    }
    function comparisonIndex() {
      return ArchitectureComparison.context(frames, time, baseline).before;
    }
    function models() {
      return view === "timeline" && frames.length
        ? [state(time), state(comparisonIndex())]
        : [current, null];
    }
    function entityGraph(value) {
      let nodes, edges;
      if (level === "function") {
        nodes = new Map(
          value.functions
            .filter((f) => !f.ambiguous)
            .map((f) => [
              f.id,
              {
                id: f.id,
                path: f.path,
                version: f.body_sha256,
                functions: [f],
                physical_lines: f.lines,
              },
            ]),
        );
        const pairs = new Map();
        for (const c of value.calls) {
          if (!nodes.has(c.source) || !nodes.has(c.target)) continue;
          const key = c.source + "\0" + c.target;
          if (!pairs.has(key))
            pairs.set(key, {
              source: c.source,
              target: c.target,
              kind: "call",
              sites: 0,
            });
          pairs.get(key).sites++;
        }
        edges = [...pairs.values()];
      } else if (level === "file") {
        const functionsByPath = new Map();
        for (const f of value.functions) {
          if (!functionsByPath.has(f.path)) functionsByPath.set(f.path, []);
          functionsByPath.get(f.path).push(f);
        }
        nodes = new Map(
          value.components.map((c) => [
            c.id,
            {
              ...c,
              path: c.id,
              functions: functionsByPath.get(c.id) || [],
            },
          ]),
        );
        edges = value.edges;
      }
      const relation = $("relation").value;
      return {
        nodes,
        edges: edges.filter((e) => relation === "all" || e.kind === relation),
      };
    }
    function unknown(id, values) {
      return values.some((v) => v && v.gaps.includes(sourcePath(id)));
    }
    function selectOptions(graph, old) {
      const search = $("search").value.toLowerCase();
      const historicalIds =
        view === "timeline"
          ? level === "function"
            ? Object.values(defs).map((f) => f.id)
            : frames.flatMap((f) => f.files.map(([path]) => path))
          : [];
      const ids = [
        ...new Set([
          ...graph.nodes.keys(),
          ...(old?.nodes.keys() || []),
          ...historicalIds,
        ]),
      ].sort();
      const matching = ids.filter(
        (id) => !search || id.toLowerCase().includes(search),
      );
      if (!matching.includes(focus)) focus = matching[0] || "";
      const options = matching.slice(0, 5000);
      if (focus && !options.includes(focus)) options.push(focus);
      $("focus").innerHTML = options
        .map(
          (id) =>
            `<option value="${esc(id)}" ${id === focus ? "selected" : ""}>${esc(id)}</option>`,
        )
        .join("");
      $("focus").disabled = !matching.length;
    }
    function draw(graph, old, change) {
      const allEdges = new Map(
        [...(old?.edges || []), ...graph.edges].map((e) => [edgeKey(e), e]),
      );
      const edgeRows = [...allEdges.values()].filter(
        (e) => e.source === focus || e.target === focus,
      );
      $("edge-count").textContent = `(${edgeRows.length})`;
      $("edges").innerHTML =
        table(
          [
            "From → dependency",
            "Kind / sites",
            "Compared with baseline",
            "Source witness",
          ],
          edgeRows
            .slice(0, 200)
            .map((e) => [
              button(e.source, e.source) + " → " + button(e.target, e.target),
              esc(e.kind) + " / " + e.sites,
              change.added.has(edgeKey(e))
                ? "Added"
                : change.removed.has(edgeKey(e))
                  ? "Removed"
                  : old
                    ? "Present / check gaps"
                    : "Current capture",
              edgeWitness(e),
            ]),
        ) +
        (edgeRows.length > 200
          ? `<p>Showing 200/${edgeRows.length}; all records remain in JSON.</p>`
          : "");
    }
    function edgeWitness(edge) {
      const [now, old] = models();
      const match = (e) => e.source === edge.source && e.target === edge.target;
      const records = (value) =>
        (level === "function" ? value.calls : value.evidence || []).filter(
          (e) => match(e) && (level === "function" || e.kind === edge.kind),
        );
      let rows = records(now),
        revision = now.revision;
      if (!rows.length && old) {
        rows = records(old);
        revision = old.revision;
      }
      return (
        rows
          .slice(0, 2)
          .map(
            (row) =>
              sourceLink(row.evidence, revision) +
              `<details><summary>Immutable identity</summary><code>SHA-256 ${esc(row.evidence.sha256)}<br>Revision ${esc(revision)}${row.evidence.blob ? "<br>Git blob " + esc(row.evidence.blob) : ""}</code></details>`,
          )
          .join("") +
        (rows.length > 2
          ? `<small>${rows.length - 2} further sites in JSON.</small>`
          : "")
      );
    }
    function sourceLink(loc, revision) {
      const repo = R.input?.location;
      const text = `${loc.path}:${loc.line_start}–${loc.line_end}`;
      if (
        !repo ||
        !/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(?:\.git)?$/.test(repo) ||
        !/^([a-f0-9]{40}|[a-f0-9]{64})$/.test(revision || "")
      )
        return esc(text);
      const href =
        repo.replace(/\.git$/, "") +
        "/blob/" +
        revision +
        "/" +
        loc.path.split("/").map(encodeURIComponent).join("/") +
        "#L" +
        loc.line_start;
      return `<a href="${esc(href)}" target="_blank" rel="noreferrer">${esc(text)} ↗</a>`;
    }
    function inspect(graph, old, nowValue, oldValue) {
      const node = graph.nodes.get(focus) || old?.nodes.get(focus);
      $("selected").textContent = focus || "No matching file or function";
      if (!node) {
        $("selected-detail").textContent =
          view === "timeline"
            ? "This file or function is not extracted in this graph state. It may be absent or inside a parser gap. Move the timeline to inspect its observed versions."
            : "Clear the search to explore this scope.";
        $("definition").textContent = "";
        $("selected-summary").textContent = "Not extracted in this state";
        return;
      }
      const edges = graph.nodes.has(focus) ? graph.edges : old.edges;
      const incoming = edges.filter((e) => e.target === focus),
        outgoing = edges.filter((e) => e.source === focus);
      const baselineOnly = !graph.nodes.has(focus);
      $("selected-detail").innerHTML =
        (baselineOnly
          ? "<p><strong>Baseline evidence only.</strong> This file or function is not extracted in the selected graph state. Definitions and reachability below come from the comparison baseline; parser gaps do not establish deletion.</p>"
          : "") +
        `<p>${level === "file" ? "Source file" : "Named function"} · ${node.functions.length} captured definitions</p><p>${incoming.length} direct dependent relationships · ${outgoing.length} dependencies</p>` +
        (unknown(focus, [nowValue, oldValue])
          ? "<p>Parser coverage is incomplete for this file or function. Missing definitions or edges are unknown.</p>"
          : "");
      $("selected-summary").textContent =
        `${incoming.length} incoming · ${outgoing.length} outgoing`;
      const rev = graph.nodes.has(focus)
        ? nowValue.revision
        : oldValue?.revision;
      $("definition").innerHTML =
        node.functions
          .slice(0, 25)
          .map(
            (f) =>
              `<p>${button(f.id, f.id, "function")}<br>${sourceLink(f.evidence, rev)}<br><code>SHA-256 ${esc(f.evidence.sha256)}<br>Definition ${esc(f.body_sha256)}${f.evidence.blob ? "<br>Git blob " + esc(f.evidence.blob) : ""}<br>Revision ${esc(rev || "unavailable")}</code></p>`,
          )
          .join("") +
        (node.functions.length > 25
          ? "<p>First 25 definitions shown; select Functions for the full inventory.</p>"
          : "");
    }
    function closeInspector(restore = true) {
      inspectorOpen = false;
      reportPanel = null;
      window.ReportUI.setInspectorOpen(false);
      if (restore) {
        let target = inspectorReturn?.isConnected
          ? inspectorReturn
          : $("tab-" + view);
        const disclosure = target.closest("details");
        if (disclosure && !disclosure.open)
          target = disclosure.querySelector("summary");
        target.focus({ preventScroll: true });
      }
    }
    function openInspector(target = document.activeElement) {
      if (!["map", "timeline"].includes(view)) return;
      inspectorReturn = target;
      reportPanel = null;
      inspectorOpen = true;
      render();
      $("inspector-close").focus({ preventScroll: true });
    }
    function renderInspector(change, nowValue, oldValue) {
      if (reportPanel) {
        renderReportPanel();
        return;
      }
      window.ReportUI.setInspectorTitle("Selection evidence");
      const visible = inspectorOpen && ["map", "timeline"].includes(view);
      window.ReportUI.setInspectorOpen(visible);
      if (!visible) return;
      const row = change.entries.get(focus);
      const source = (node, revision) =>
        node
          ? level === "file"
            ? sourceLink(
                { path: node.path, line_start: 1, line_end: 1 },
                revision,
              )
            : node.functions
                .map((f) => sourceLink(f.evidence, revision))
                .join("<br>")
          : "Not extracted in this state";
      const prompt = ArchitectureComparison.investigation(prompts, focus);
      $("inspector-content").innerHTML =
        `<p class="eyebrow">${level === "file" ? "File" : "Function"}</p><p class="inspector-identity">${esc(focus)}</p>` +
        (row
          ? `<p>${esc(oldValue ? ArchitectureComparison.describe(row) : row.incomplete ? "Coverage incomplete" : "Current capture")}</p>
          <h3>Source evidence</h3>${oldValue ? `<p>Before · <code>${esc(oldValue.revision.slice(0, 12))}</code><br>${source(row.before, oldValue.revision)}</p>` : ""}
          <p>${oldValue ? "After" : "Captured source"} · <code>${esc(nowValue.revision?.slice(0, 12))}</code><br>${source(row.after, nowValue.revision)}</p>
          ${oldValue && row.before && !row.after ? '<p class="qualification">Baseline evidence retained. Missing extraction inside parser gaps does not establish deletion.</p>' : ""}
          <h3>${oldValue ? "Changed relationships" : "Direct relationships"}</h3>
          <p>${oldValue ? `Comparable incoming ${row.beforeIn} → ${row.afterIn} · outgoing ${row.beforeOut} → ${row.afterOut}` : `${row.afterIn} comparable incoming · ${row.afterOut} outgoing`}</p>` +
            (oldValue
              ? `<details class="records"><summary>Changed relationship evidence (${row.changedRelationships})</summary>` +
                table(
                  ["Change / relationship", "Source witness"],
                  [
                    ...row.added.map((e) => [e, "Added"]),
                    ...row.removed.map((e) => [e, "Removed"]),
                  ]
                    .slice(0, 30)
                    .map(([e, status]) => [
                      `${status}<br>${button(e.source, e.source)} → ${button(e.target, e.target)}`,
                      edgeWitness(e),
                    ]),
                ) +
                (row.changedRelationships > 30
                  ? '<p class="qualification">First 30 shown. All relationship records remain in the saved data.</p>'
                  : "") +
                "</details>"
              : "")
          : "<p>Not extracted in either comparison state. Select another captured state to inspect its historical evidence.</p>") +
        `<button data-inspector-evidence="true">Open equivalent evidence tables ↓</button>
        <details class="records"><summary>${change.incomplete ? "Coverage limited" : "Scope and limitations"}</summary><p class="qualification">${change.incomplete ? `${change.gaps.size} files have parser gaps in this ${oldValue ? "comparison" : "capture"}. Counts exclude relationships involving those files. ${row?.cycleIncomplete ? "Cycle participation may cross a parser gap and remains unknown." : ""}` : "Static relationships are candidates; indirect dispatch and runtime behavior require verification."}</p></details>` +
        "<h3>Continue investigating</h3>" +
        (prompt
          ? promptCard(prompt.prompt, prompt.index, "inspector", true)
          : '<p>No matching saved investigation prompt.</p><button data-view="review">Recommended prompts →</button>');
      window.ReportUI.enhance($("inspector-content"));
    }
    function openReportPanel(kind, index, target) {
      inspectorReturn = target;
      reportPanel = { kind, index: Number(index) };
      inspectorOpen = true;
      renderReportPanel();
      $("inspector-close").focus({ preventScroll: true });
    }
    function renderReportPanel() {
      if (!reportPanel || !inspectorOpen) return;
      window.ReportUI.setInspectorOpen(true);
      const { kind, index } = reportPanel;
      const paragraph = (label, text) =>
        text ? `<h3>${esc(label)}</h3><p>${esc(text)}</p>` : "";
      const source = (path) =>
        F.components.some((c) => c.id === path)
          ? sourceLink({ path, line_start: 1, line_end: 1 }, H.revision)
          : esc(path);
      const fullReview =
        '<button data-view="evidence">Open evidence coverage →</button>';
      const register = `<a href="${esc($("review-register-link").getAttribute("href"))}">Open evidence register ↗</a>`;
      let title = "Evidence",
        body = "";
      if (kind === "lead") {
        title = "Recommendation evidence";
        const paths =
          plan?.prompt.target_files || opening.cycle || (lead ? [lead.id] : []);
        body =
          `<h3 class="panel-subject">${esc(leadEvidenceTitle)}</h3><p>${esc(leadExplanation)}</p>` +
          `<p class="qualification">${esc($("recommendation-state").textContent)}</p>` +
          (affected
            ? `<button data-focus="${esc(affected)}" data-level="file" data-view="map">Open dependency graph →</button>`
            : "") +
          (plan || investigation
            ? "<h3>Suggested next step</h3>" +
              promptCard(
                (plan || investigation).prompt,
                (plan || investigation).index,
                "panel",
                true,
              )
            : fullReview) +
          (paths.length
            ? `<details class="records"><summary>Source references (${paths.length})</summary><ul class="source-list">` +
              paths.map((path) => `<li>${source(path)}</li>`).join("") +
              "</ul></details>"
            : "") +
          '<details class="records"><summary>Scope and limitations</summary>' +
          paragraph(
            "Before acting",
            "A static cycle or high relationship count does not establish a defect. Verify the source, parser limits, and a concrete change scenario.",
          ) +
          paragraph("Source coverage", $("scope-readout").textContent) +
          fullReview +
          "</details>";
      } else if (kind === "prompt") {
        title = "Recommended prompt";
        body = prompts[index]
          ? promptCard(prompts[index], index, "panel", true)
          : "<p>No saved prompt is available.</p>";
      } else if (kind === "finding") {
        title = "Finding evidence";
        const finding = findings[index];
        if (finding)
          body =
            `<h3 class="panel-subject">${esc(finding.statement)}</h3>` +
            `<p class="qualification">${esc(statusLabel(finding.status))} · ${esc(finding.confidence || "Unknown")} confidence</p>` +
            paragraph("Why it matters", finding.architecture?.consequence) +
            paragraph("Next decision", finding.architecture?.next_decision) +
            register +
            '<details class="records"><summary>Reasoning and counterevidence</summary>' +
            paragraph("Reasoning", finding.confidence_rationale) +
            paragraph("Counterevidence", finding.counterevidence) +
            "</details>" +
            '<details class="records"><summary>Saved evidence references</summary><p>' +
            esc((finding.evidence_ids || []).join(" · ")) +
            "</p></details>";
      } else if (kind === "decision") {
        title = "Proposed change";
        const decision = R.decisions?.[index];
        if (decision)
          body =
            `<h3 class="panel-subject">${esc(decision.action)}</h3>` +
            paragraph("Next decision", decision.next_decision) +
            paragraph(
              "Status",
              decision.verification_required
                ? "Verification required"
                : "Review proposed scope",
            ) +
            register;
      } else if (kind === "report") {
        title = "Report details";
        body =
          paragraph("Source", R.input?.location || "Captured repository") +
          paragraph("Snapshot", snapshotText) +
          paragraph("Revision", H.revision || "Unavailable") +
          paragraph("Review status", $("review-status").textContent) +
          '<p class="qualification">Saved, read-only analysis. Static relationships are candidates, not runtime proof.</p>' +
          fullReview;
      } else {
        title = "Coverage and limitations";
        body =
          paragraph("Assessment", $("review-label").textContent) +
          paragraph("Source coverage", $("scope-readout").textContent) +
          paragraph("Model review", $("review-status").textContent) +
          "<h3>Limits</h3><ul>" +
          [...F.limitations, ...(H.limitations || [])]
            .map((text) => `<li>${esc(text)}</li>`)
            .join("") +
          "</ul>" +
          fullReview;
      }
      window.ReportUI.setInspectorTitle(title);
      $("inspector-content").innerHTML = body;
      if (kind === "prompt") {
        const disclosure = $("inspector-content").querySelector(
          ".prompt-card details",
        );
        if (disclosure) disclosure.open = true;
      }
      window.ReportUI.enhance($("inspector-content"));
      window.ReportUI.setInspectorOpen(true);
    }
    function renderGrowth() {
      if (!frames.length) return;
      const metrics = [
        ["files", "Supported files"],
        ["functions", "Extracted functions"],
        ["call_pairs", "Call candidate pairs"],
        ["physical_lines", "Physical source lines"],
      ];
      const width = 960,
        height = 172,
        pad = 36,
        panel = width / 4;
      const svg = d3
        .select($("growth-chart"))
        .html("")
        .append("svg")
        .attr("viewBox", `0 0 ${width} ${height}`)
        .attr("role", "group")
        .attr(
          "aria-label",
          "Codebase growth by first-parent commit; use the commit slider or measurement table for keyboard access",
        );
      metrics.forEach(([field, label], column) => {
        const values = frames.map((f, i) => ({ i, value: f.metrics[field] })),
          x = d3
            .scaleLinear()
            .domain([0, Math.max(1, frames.length - 1)])
            .range([column * panel + pad, (column + 1) * panel - 18]),
          extent = d3.extent(values, (d) => d.value),
          y = d3
            .scaleLinear()
            .domain([
              Math.max(0, extent[0] - (extent[1] - extent[0] || 1) * 0.2),
              extent[1] + (extent[1] - extent[0] || 1) * 0.2,
            ])
            .nice()
            .range([height - 32, 54]);
        svg
          .append("text")
          .attr("x", column * panel + pad)
          .attr("y", 16)
          .attr("class", "chart-label")
          .text(label);
        svg
          .append("text")
          .attr("x", column * panel + pad)
          .attr("y", 36)
          .attr("class", "chart-value")
          .text(frames[time].metrics[field].toLocaleString());
        svg
          .append("g")
          .attr("transform", `translate(${column * panel + pad},0)`)
          .attr("class", "chart-axis")
          .call(
            d3
              .axisLeft(y)
              .ticks(3)
              .tickSize(-panel + pad + 18),
          );
        svg
          .append("path")
          .datum(values)
          .attr("class", "growth-line")
          .attr(
            "d",
            d3
              .line()
              .x((d) => x(d.i))
              .y((d) => y(d.value)),
          );
        svg
          .append("line")
          .attr("class", "time-marker")
          .attr("x1", x(time))
          .attr("x2", x(time))
          .attr("y1", 48)
          .attr("y2", height - 32);
        svg
          .append("circle")
          .attr("class", "time-point")
          .attr("cx", x(time))
          .attr("cy", y(frames[time].metrics[field]))
          .attr("r", 4);
        svg
          .append("text")
          .attr("class", "chart-date")
          .attr("x", x(0))
          .attr("y", height - 12)
          .text(frames[0].date?.slice(0, 10) || "Baseline");
        svg
          .append("text")
          .attr("class", "chart-date")
          .attr("x", x(frames.length - 1))
          .attr("text-anchor", "end")
          .attr("y", height - 12)
          .text(frames.at(-1).date?.slice(0, 10) || "Latest");
        svg
          .append("rect")
          .attr("fill", "transparent")
          .attr("x", column * panel + pad)
          .attr("y", 48)
          .attr("width", panel - pad - 18)
          .attr("height", height - 72)
          .attr("cursor", "crosshair")
          .on("click", (event) => {
            stop();
            time = Math.max(
              0,
              Math.min(
                frames.length - 1,
                Math.round(x.invert(d3.pointer(event, svg.node())[0])),
              ),
            );
            render();
          });
      });
      const start = frames[comparisonIndex()].metrics,
        end = frames[time].metrics;
      $("growth-summary").textContent =
        "Compared with baseline: " +
        metrics
          .map(
            ([field, label]) =>
              `${label.toLowerCase()} ${end[field] - start[field] >= 0 ? "+" : ""}${end[field] - start[field]}`,
          )
          .join(" · ") +
        ". Each step follows first-parent ancestry, not an equal time interval. Displayed dates are author dates and may be out of order. Parsed counts can change with parser gaps.";
      $("growth-table").innerHTML = table(
        [
          "Commit / date",
          "Files / functions",
          "Call pairs / source lines",
          "Parser gaps",
        ],
        frames.map((f, i) => [
          `<button data-time="${i}">${esc(f.subject)} · ${f.commit.slice(0, 8)}</button><br>${esc(f.date || "Window baseline")}`,
          f.metrics.files + " / " + f.metrics.functions,
          f.metrics.call_pairs + " / " + f.metrics.physical_lines,
          String(f.gaps.length),
        ]),
      );
    }
    function renderTimeline() {
      if (!frames.length) {
        $("timeline-gap").textContent =
          H.reason || "Committed graph frames are unavailable for this input.";
        return;
      }
      renderGrowth();
      const frame = frames[time],
        base = frames[comparisonIndex()];
      const comparison = ArchitectureComparison.context(frames, time, baseline);
      $("comparison-mode").textContent = comparison.mode;
      const identity = (item) =>
        `${item.label === "Window baseline" ? "Window baseline · " : ""}${item.short}${item.date ? " · " + new Date(item.date).toLocaleDateString() : " · date unavailable"}`;
      $("comparison-range").textContent =
        `${identity(comparison.baseline)} → ${identity(comparison.selected)}`;
      $("time").value = time;
      $("time").max = frames.length - 1;
      $("frame-count").textContent =
        `${time + 1} / ${frames.length} graph states`;
      $("commit-title").textContent = comparison.selected.label;
      $("commit-title").title = comparison.selected.label;
      $("commit-id").textContent = frame.commit.slice(0, 12);
      $("commit-date").textContent = frame.date
        ? "Authored " + new Date(frame.date).toLocaleString()
        : "Window baseline · author date unavailable";
      $("baseline").innerHTML =
        '<option value="previous">Previous graph state</option>' +
        frames
          .map(
            (f, i) =>
              `<option value="${i}">${i + 1} · ${esc(f.subject.slice(0, 70))} · ${f.commit.slice(0, 8)}</option>`,
          )
          .join("");
      $("baseline").value = baseline;
      const before = new Map(
          base.nodes
            .map((n) => defs[n])
            .filter((f) => !f.ambiguous)
            .map((f) => [f.id, f]),
        ),
        after = new Map(
          frame.nodes
            .map((n) => defs[n])
            .filter((f) => !f.ambiguous)
            .map((f) => [f.id, f]),
        );
      const gaps = new Set([...base.gaps, ...frame.gaps]),
        changed = [];
      for (const id of [
        ...new Set([...before.keys(), ...after.keys()]),
      ].sort()) {
        if (gaps.has(sourcePath(id))) continue;
        const a = before.get(id),
          b = after.get(id);
        if (a && b && a.body_sha256 === b.body_sha256) continue;
        changed.push({
          id,
          kind: !a ? "Added" : !b ? "Removed" : "Modified",
          before: a,
          after: b,
        });
      }
      const added = changed.filter((c) => c.kind === "Added").length,
        removed = changed.filter((c) => c.kind === "Removed").length,
        modified = changed.filter((c) => c.kind === "Modified").length;
      const keys = (f) =>
        new Set(
          f.calls
            .map((k) => historicalCalls[k])
            .filter((c) => !gaps.has(c.path) && !gaps.has(sourcePath(c.target)))
            .map((c) => c.source + "\0" + c.target),
        );
      const a = keys(base),
        b = keys(frame),
        newEdges = [...b].filter((k) => !a.has(k)).length,
        removedEdges = [...a].filter((k) => !b.has(k)).length;
      $("change-summary").textContent =
        `${added} added · ${modified} modified · ${removed} removed definitions. Call candidate pairs: +${newEdges} / −${removedEdges}.`;
      $("timeline-gap").textContent =
        `${gaps.size ? gaps.size + " files have parser gaps in this comparison; their missing definitions/edges are excluded from change counts. " : ""}Committed syntax only; formatting can change definition hashes. Historical scope includes supported current and deleted source paths in the captured window; source exclusions and history bounds still apply.`;
      $("change-list").innerHTML =
        table(
          [
            "Function / syntax change",
            "Baseline evidence",
            "Selected commit evidence",
          ],
          changed
            .slice(0, 150)
            .map((c) => [
              button(c.id, c.id, "function") + "<br>" + c.kind,
              c.before
                ? sourceLink(c.before.evidence, base.commit)
                : "Absent from parsed scope",
              c.after
                ? sourceLink(c.after.evidence, frame.commit)
                : "Absent from parsed scope",
            ]),
        ) +
        (changed.length > 150
          ? `<p>First 150/${changed.length} changes shown; select a function or inspect complete JSON.</p>`
          : "");
      $("previous").disabled = time === 0;
      $("next").disabled = time === frames.length - 1;
    }
    // One chart per tab. All share file/function selection and immutable evidence.
    const viewInfo = {
      map: [
        "Dependency graph",
        "Explore the captured dependency graph, then focus on a file or function.",
        "graph",
      ],
      matrix: [
        "Dependency matrix",
        "Find dense coupling and cyclic dependencies across files or functions.",
        "matrix",
      ],
      paths: [
        "Call paths",
        "Follow candidate callers and callees, with source evidence for every step.",
        "paths",
      ],
      timeline: [
        "Graph evolution",
        "Watch relationships appear and disappear across committed graph states.",
        "graph",
      ],
      impact: [
        "Change impact",
        "Which consumers may need review when this file or function changes?",
        "impact",
      ],
      coupling: [
        "Changes together",
        "Find files or functions repeatedly changed in the same commits.",
        "coupling",
      ],
      treemap: [
        "Size and churn",
        "Locate large files or functions with frequent recorded changes.",
        "treemap",
      ],
    };
    const tabs = [
      "overview",
      "map",
      "timeline",
      "review",
      "matrix",
      "paths",
      "impact",
      "coupling",
      "treemap",
      "score",
      "evidence",
    ];
    function render() {
      const chartView = Boolean(viewInfo[view]);
      for (const [id, active] of Object.entries({
        overview: view === "overview",
        explore: chartView,
        review: view === "review",
        "score-panel": view === "score",
        evidence: view === "evidence",
      }))
        $(id).hidden = !active;
      $("timeline").hidden = view !== "timeline";
      $("timeline-evidence").hidden = view !== "timeline";
      $("explore").classList.toggle(
        "network-view",
        ["map", "timeline"].includes(view),
      );
      $("changes").hidden = view !== "timeline";
      $("topology-watch").hidden =
        view !== "timeline" || !opening.topology.length;
      window.ReportUI.setView(view);
      const network = view === "map" || view === "timeline";
      $("network-scope-label").hidden = !network;
      $("graph-coverage").hidden = !network;
      $("network-scope").querySelector('[value="connected"]').textContent =
        view === "timeline"
          ? "Historically connected"
          : "Connected files or functions";
      $("network-scope").querySelector('[value="all"]').textContent =
        level === "file" ? "All files" : "All functions";
      $("network-scope").querySelector('[value="neighbors"]').textContent =
        view === "timeline"
          ? "Selected + 2 historical hops"
          : "Selected + 2 hops";
      $("network-layout-control").hidden = !network;
      $("layout-status").hidden = !network;
      window.ReportUI.setGraphMode(network, view === "timeline");
      if (!network) {
        window.ArchitectureNetwork.leave();
        $("graph").classList.remove("network-host");
      }
      if (!chartView) {
        renderReportPanel();
        return;
      }
      $("explore").setAttribute("aria-labelledby", "tab-" + view);
      const [title, description, visual] = viewInfo[view];
      $("view-title").textContent = title;
      $("view-description").textContent = description;
      $("level-control").hidden = view === "paths";
      $("relation-label").hidden =
        level === "function" || ["coupling", "treemap"].includes(view);
      $("matrix-order-label").hidden = view !== "matrix";
      $("broad-label").hidden = view !== "coupling";
      document.querySelector(".filters").hidden = [
        "relation-label",
        "matrix-order-label",
        "broad-label",
        "network-scope-label",
      ].every((id) => $(id).hidden);
      const [nowValue, oldValue] = models(),
        graph = entityGraph(nowValue),
        old = oldValue ? entityGraph(oldValue) : null;
      selectOptions(graph, old);
      const change = ArchitectureComparison.present({
        graph,
        old,
        gaps: [...(nowValue.gaps || []), ...(oldValue?.gaps || [])],
      });
      draw(graph, old, change);
      $("visual-detail").replaceChildren();
      window.ReportUI.setGraphVisible(visual === "graph");
      document.querySelector(".graph-actions").hidden = visual !== "graph";
      const context = {
        kind: visual,
        graph,
        change,
        capturedFiles: F.coverage.files,
        comparisonFiles: new Set([
          ...(nowValue.components || []).map((c) => c.id),
          ...(oldValue?.components || []).map((c) => c.id),
        ]).size,
        value: nowValue,
        focus,
        level,
        frames,
        history: H,
        order: $("matrix-order").value,
        excludeBroad: $("exclude-broad").checked,
        search: $("search").value,
        table,
        esc,
        button,
        edgeWitness,
        edgeKey,
        onSelect: (id) => {
          focus = id;
          if (network) openInspector($("graph").querySelector("canvas"));
          else render();
        },
      };
      if (view === "timeline" && !frames.length) {
        window.ArchitectureNetwork.leave();
        $("graph").replaceChildren();
        $("layout-status").hidden = true;
        $("graph-title").textContent = "Graph history unavailable";
        $("graph-count").textContent = "0 committed graph states";
        $("graph-note").textContent =
          H.reason || "No committed graph states were captured.";
        document.querySelector(".legend").textContent = "History unavailable";
        $("timeline").hidden = true;
        $("timeline-evidence").hidden = true;
        $("graph-coverage").hidden = true;
      } else if (view === "timeline") {
        window.renderGraphEvolution({
          ...context,
          old,
          change,
          state,
          entityGraph,
          edgeKey,
        });
      } else if (view === "coupling" && !frames.length) {
        $("graph").innerHTML =
          '<p class="chart-empty">Committed history is unavailable for this capture.</p>';
        $("graph-title").textContent = "Co-change history unavailable";
        $("graph-count").textContent = "0 committed states";
        $("graph-note").textContent =
          H.reason ||
          "History must be available before co-change can be measured.";
        document.querySelector(".legend").textContent = "History unavailable";
      } else if (!graph.nodes.size || !focus) {
        window.ArchitectureNetwork.leave();
        $("graph").innerHTML =
          '<p class="chart-empty">No extracted ' +
          (level === "function" ? "functions" : "files") +
          " match this scope.</p>";
        $("layout-status").hidden = true;
        $("graph-coverage").hidden = true;
        $("graph-count").textContent =
          `0 matching ${level === "file" ? "files" : "functions"}`;
        $("graph-note").textContent =
          "Review source and parser coverage, or clear the search.";
        document.querySelector(".legend").textContent =
          `No matching ${level === "file" ? "files" : "functions"}`;
      } else if (view === "map") window.ArchitectureNetwork.render(context);
      else if (visual === "paths") window.renderCodePaths(context);
      else if (visual !== "graph") window.renderArchitectureView(context);
      inspect(graph, old, nowValue, oldValue);
      renderInspector(change, nowValue, oldValue);
      $("selection").hidden = !focus;
      $("relationships").hidden = ["coupling", "treemap"].includes(view);
      $("visual-records").hidden = !$("visual-detail").hasChildNodes();
      $("visual-records-title").textContent =
        {
          impact: "Reachable consumers and evidence paths",
          paths: "Call paths and source evidence",
          coupling: "Co-change pairs and matching commits",
          treemap: "Size and churn records",
          matrix: "Selected relationship evidence",
          timeline: "Selected relationship evidence",
        }[view] || "Chart records and evidence";
      if (view === "timeline" && frames.length) {
        renderTimeline();
        $("topology-summary").textContent =
          `${change.incomplete ? "Comparison incomplete · " : ""}${change.summary.replace(" removed ·", ` removed ${level === "file" ? "files" : "functions"} ·`).replace("definition edits", level === "file" ? "files with definition edits" : "function definition edits")}`;
        $("structural-changes").innerHTML = change.highlights.length
          ? "<ul>" +
            change.highlights
              .map(
                (row) =>
                  `<li><button data-change="true" data-focus="${esc(row.id)}">${esc(row.id)}</button><span>${esc(row.changedRelationships ? `Relationships +${row.added.length} / −${row.removed.length}` : row.cycleChanged ? "Cycle participation changed" : row.status)}</span></li>`,
              )
              .join("") +
            "</ul>"
          : `<p>${change.incomplete ? "No comparable changes observed outside parser gaps." : "No observed topology or definition changes in this comparison."}</p>`;
        $("comparison-limits").textContent = change.incomplete
          ? `${change.gaps.size} files have parser gaps. Relationships involving them are excluded; cycle changes that may cross them remain unknown. Counts describe comparable extracted relationships.`
          : "Counts describe extracted static relationships. Definition hashes can change with formatting.";
      }
    }
    function stop() {
      clearInterval(timer);
      timer = null;
      playbackLabel(false);
    }
    function setLevel(next) {
      const path = sourcePath(focus);
      if (next === "function" && level !== "function") {
        const [activeValue, baselineValue] = models();
        const functions = [
          ...new Map(
            [...(baselineValue?.functions || []), ...activeValue.functions].map(
              (f) => [f.id, f],
            ),
          ).values(),
        ];
        const calls = [...activeValue.calls, ...(baselineValue?.calls || [])];
        const choices = functions.filter(
          (f) => !f.ambiguous && f.path === path,
        );
        const degree = (id) =>
          calls.filter((c) => c.source === id || c.target === id).length;
        focus =
          choices.sort(
            (a, b) => degree(b.id) - degree(a.id) || a.id.localeCompare(b.id),
          )[0]?.id || "";
      } else if (next === "file") focus = path;
      level = next;
      $("level").value = level;
      $("relation").value = level === "function" ? "call" : "all";
      $("search").value = "";
    }
    function setView(next, updateHash = true) {
      if (!tabs.includes(next)) next = "overview";
      stop();
      closeInspector(false);
      if (view !== next) {
        $("visual-records").open = false;
        $("selection").open = false;
        $("evidence-tables").open = false;
        window.ReportUI.closeDisclosures();
      }
      view = next;
      if (view === "paths") setLevel("function");
      if (updateHash) window.history.replaceState(null, "", "#view=" + view);
      render();
    }
    const excluded = new Set(R.scope?.unselected_aspects || []),
      coverage = (R.coverage || []).filter((r) => !excluded.has(r.aspect_id));
    const reviewed = coverage.filter((r) =>
        ["partial", "complete_for_stated_scope"].includes(r.coverage),
      ).length,
      challenged = coverage.filter((r) => r.challenge === "supported").length;
    $("identity").textContent = (R.input?.location || "Captured repository")
      .replace(/^https:\/\/github.com\//, "")
      .replace(/\.git$/, "");
    $("identity").title = $("identity").textContent;
    const snapshotText = `${H.revision?.slice(0, 12) || F.snapshot_id} · ${F.coverage.files} source files`;
    $("review-label").textContent =
      !reviewed && !R.counts?.blocked && !R.terminal?.usage?.catalog_models
        ? "Static analysis only"
        : R.status === "partial"
          ? "Review incomplete"
          : "Review draft";
    $("review-status").textContent =
      `${reviewed}/${coverage.length} selected topics have model analysis; ${challenged} have a supporting challenge. Static graph evidence is available.`;
    const score = data["architecture-score.json"];
    if (
      score &&
      (score.schema_version !== "mn.architecture.score.v1" ||
        score.snapshot_id !== F.snapshot_id)
    )
      throw new Error("The architecture score does not match this snapshot.");
    const number = (value) =>
      Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 });
    const scoreSummary = window.ArchitectureOverview.scoreSummary(score);
    $("score-value").textContent = scoreSummary.value;
    $("overview-score-value").textContent = scoreSummary.value;
    $("overview-score-note").textContent = scoreSummary.note;
    $("score-status").textContent = score
      ? `${score.model} · Provisional${score.score === null ? " range" : ""}`
      : "No score was saved for this publication.";
    $("score-coverage").textContent = score
      ? `${score.assessed_weight}/100 scoring points assessed · ${score.source_parse_coverage}% of files fully parsed`
      : "Open a new scored publication or include architecture-score.json with the offline data.";
    $("score-breakdown").hidden = !score;
    $("score-range").textContent = score
      ? `Possible points: ${number(score.range.lower)}–${number(score.range.upper)} / 100. ${score.unassessed_weight} points remain unassessed.`
      : "";
    if (score)
      $("score-dimensions").innerHTML = score.dimensions
        .map(
          (row) =>
            `<div class="score-dimension"><div class="section-head"><span>${esc(row.label)}</span><strong>${row.points === null ? "Not assessed" : number(row.points)} / ${row.weight}</strong></div>${row.points === null ? '<p class="score-unassessed">Evidence missing</p>' : `<progress aria-label="${esc(row.label)}" max="${row.weight}" value="${row.points}"></progress>`}<p class="qualification">${esc(row.basis)}</p><details class="score-method"><summary>How calculated</summary><p class="qualification">${esc(row.formula)}</p></details></div>`,
        )
        .join("");
    const start = frames[0]?.metrics,
      end = frames.at(-1)?.metrics;
    const growth = (field) =>
      start && end
        ? `${end[field] - start[field] >= 0 ? "+" : ""}${(end[field] - start[field]).toLocaleString()} across the history window`
        : "History unavailable";
    $("metrics").innerHTML =
      metric(F.coverage.files, "Captured source files") +
      metric(F.functions.length, "Extracted functions", growth("functions")) +
      metric(
        F.cycles.length,
        "File-level dependency cycle groups",
        F.cycles.length
          ? `${new Set(F.cycles.flat()).size} files participate`
          : "No cycles extracted",
      ) +
      metric(
        frames.length,
        "Committed graph states",
        growth("call_pairs").replace(
          "across the history window",
          "call candidate pairs",
        ),
      );
    const churn = new Map();
    for (const e of H.events)
      churn.set(
        sourcePath(e.function),
        (churn.get(sourcePath(e.function)) || 0) + 1,
      );
    const connected = [...F.components].sort(
      (a, b) =>
        b.fan_in + b.fan_out - (a.fan_in + a.fan_out) ||
        a.id.localeCompare(b.id),
    );
    const referenced = [...F.components].sort(
      (a, b) => b.fan_in - a.fan_in || a.id.localeCompare(b.id),
    );
    const changed = [...F.components].sort(
      (a, b) =>
        (churn.get(b.id) || 0) - (churn.get(a.id) || 0) ||
        a.id.localeCompare(b.id),
    );
    const picks = [connected[0], referenced[0], changed[0]].filter(
      (p, i, rows) => p && rows.findIndex((x) => x.id === p.id) === i,
    );
    const opening = window.ArchitectureOverview.project(F, H, R);
    const lead = opening.lead;
    $("overview-status").textContent = $("review-label").textContent;
    $("scope-readout").textContent =
      `${opening.parsed}/${F.coverage.files} files parsed · ${opening.linkedCalls.toLocaleString()}/${opening.callSites.toLocaleString()} call sites have candidate targets. Grammar success does not establish complete dependency coverage.`;
    $("topology-changes").innerHTML = opening.topology
      .map(
        (row) =>
          `<div class="topology-row"><div><strong>${esc(row.subject)}</strong><p>File links +${row.filesAdded} / −${row.filesRemoved} · function call pairs +${row.callsAdded} / −${row.callsRemoved} · functions +${row.nodesAdded} / −${row.nodesRemoved}</p></div><button data-time="${row.index}" data-replay-level="${row.level}" data-replay-focus="${esc(row.focus)}" data-view="timeline" data-compare="previous">Replay change →</button></div>`,
      )
      .join("");
    const prompts = R.improvement_prompts?.prompts || [];
    const primaryPrompts = prompts
      .map((prompt, index) => ({ prompt, index }))
      .filter(({ prompt }) =>
        ["work_package", "cycle"].includes(prompt.record_type),
      );
    const plan =
      opening.planIndex < 0
        ? null
        : { prompt: prompts[opening.planIndex], index: opening.planIndex };
    const investigation =
      opening.investigateIndex < 0
        ? null
        : {
            prompt: prompts[opening.investigateIndex],
            index: opening.investigateIndex,
          };
    const recommended = [plan || investigation].filter(Boolean);
    for (const mode of ["Investigate", "Plan", "Verify", "Implement"]) {
      const match = primaryPrompts.find(({ prompt }) => prompt.mode === mode);
      if (match && !recommended.some((p) => p.index === match.index))
        recommended.push(match);
    }
    if (!recommended.length)
      recommended.push(
        ...prompts.slice(0, 3).map((prompt, index) => ({ prompt, index })),
      );
    recommended.splice(2);
    const change = plan?.prompt;
    $("lead-title").textContent = change
      ? plan?.prompt.title || change.action
      : lead
        ? opening.cycle
          ? `Investigate the ${opening.cycle.length}-file cycle around ${lead.id}`
          : `Inspect ${lead.id} before changing it`
        : "Review the captured scope";
    $("lead-detail").textContent = change
      ? plan?.prompt.expected_value
        ? "Proposed benefit: " + plan.prompt.expected_value
        : change.next_decision ||
          "Verify the premise and affected source before implementation."
      : lead
        ? `${lead.fan_in} files depend directly on it; it refers to ${lead.fan_out} other files.${opening.changedCommits ? ` Changed in ${opening.changedCommits} commits in the captured window.` : ""} Verify a concrete change scenario before deciding whether to refactor.`
        : "No connected component was extracted. Review parser coverage and source scope first.";
    const affected = plan?.prompt.target_files?.[0] || lead?.id;
    const leadEvidenceTitle = $("lead-title").textContent;
    const leadExplanation = $("lead-detail").textContent;
    if (!change && lead) {
      $("lead-title").textContent = opening.cycle
        ? "Review the dependency cycle"
        : `Review ${lead.id}`;
      $("lead-detail").textContent = opening.cycle
        ? `${opening.cycle.length} files participate. ${opening.hasHistory ? `${lead.id} changed in ${opening.changedCommits} captured commits.` : "Change history was not captured."}`
        : `${lead.fan_in} files depend on it; it refers to ${lead.fan_out} files.`;
    }
    $("lead-kicker").textContent = change
      ? "Recommended change"
      : lead
        ? "Recommended investigation"
        : "Review scope";
    $("recommendation-state").textContent = change
      ? "Proposed · Verify before acting"
      : lead
        ? "Static signal · No defect established"
        : "Evidence limited · No recommendation";
    $("lead-link").innerHTML =
      `<button class="vbg-button" data-variant="primary" data-panel="${lead || change ? "lead" : "coverage"}">${lead || change ? "Review evidence" : "Review scope"} →</button>`;
    $("overview-status").textContent =
      `${$("review-label").textContent} · ${opening.parsed < F.coverage.files || opening.linkedCalls < opening.callSites ? "Coverage limited" : "See assessment scope"}`;
    const findings = [...(R.findings || [])].sort(
      (a, b) =>
        Number(b.status === "supported") - Number(a.status === "supported"),
    );
    const observations = [
      ...findings.map((finding, index) => ({
        title: finding.statement,
        status: statusLabel(finding.status),
        kind: "finding",
        index,
      })),
      ...(R.decisions || [])
        .map((decision, index) => ({
          title: decision.action,
          status: "Proposed change",
          kind: "decision",
          index,
        }))
        .filter((row) => row.title !== change?.action),
    ];
    $("overview-findings").closest("section").hidden = !observations.length;
    $("finding-count").textContent = observations.length
      ? String(observations.length)
      : "";
    const observationRow = (row) =>
      `<button class="report-row" data-panel="${row.kind}" data-panel-index="${row.index}"><span><strong>${esc(row.title)}</strong><small>${esc(row.status)}</small></span><span aria-hidden="true">→</span></button>`;
    $("overview-findings").innerHTML =
      observations.slice(0, 3).map(observationRow).join("") +
      (observations.length > 3
        ? `<details class="records"><summary>More observations (${observations.length - 3})</summary>${observations.slice(3).map(observationRow).join("")}</details>`
        : "");
    $("priorities").innerHTML = picks
      .map((p, i) => {
        const why =
          p === connected[0]
            ? `${p.fan_in} dependent files · ${p.fan_out} dependencies`
            : p === referenced[0]
              ? `${p.fan_in} source files refer to this shared dependency`
              : `${churn.get(p.id) || 0} observed function syntax edits`;
        return `<div class="signal-row"><span>0${i + 1}</span><div><strong>${esc(p.id)}</strong><p>${esc(why)}</p></div><button data-focus="${esc(p.id)}" data-level="file" data-view="map">Inspect ↗</button></div>`;
      })
      .join("");
    focus = lead?.id || "";
    if (start && end) {
      $("growth-preview").innerHTML =
        `<div class="mini-growth"><strong>${end.functions.toLocaleString()} <small>functions</small></strong><span>${growth("functions").split(" across")[0]}</span></div><div id="mini-chart"></div><p>${frames.length} committed graph states · ${start.call_pairs} → ${end.call_pairs} call candidate pairs</p><p>Function counts reflect parsed syntax. Play evolution to inspect the topology, new links and removed connections.</p>`;
      const chart = d3
        .select($("mini-chart"))
        .append("svg")
        .attr("viewBox", "0 0 400 96")
        .attr("role", "img")
        .attr(
          "aria-label",
          `Extracted functions increased from ${start.functions} to ${end.functions} in the captured history window`,
        );
      const x = d3
        .scaleLinear()
        .domain([0, Math.max(1, frames.length - 1)])
        .range([3, 397]);
      const extent = d3.extent(frames, (f) => f.metrics.functions);
      const y = d3
        .scaleLinear()
        .domain([extent[0] - 1, extent[1] + 1])
        .range([86, 9]);
      chart
        .append("path")
        .datum(frames)
        .attr("class", "growth-line")
        .attr(
          "d",
          d3
            .line()
            .x((d, i) => x(i))
            .y((d) => y(d.metrics.functions)),
        );
      chart
        .append("circle")
        .attr("cx", x(frames.length - 1))
        .attr("cy", y(end.functions))
        .attr("r", 3)
        .attr("class", "time-point");
    } else
      $("growth-preview").textContent =
        H.reason || "Git history is unavailable for this capture.";
    $("review-summary").textContent = R.executive;
    $("findings").innerHTML = R.findings?.length
      ? R.findings
          .map(
            (f) =>
              `<article><h3>${esc(f.statement)}</h3><p>${esc(f.status)} · ${esc(f.confidence)} confidence</p><p>${esc(f.architecture?.consequence || f.confidence_rationale)}</p><p>Next decision: ${esc(f.architecture?.next_decision || "Inspect the source and challenge before acting.")}</p></article>`,
          )
          .join("")
      : "<p>No independently supported findings were produced. This does not establish that the architecture has no issues.</p>";
    $("proposals").innerHTML =
      "<p>Proposals require source verification and a challenge before implementation.</p>" +
      (R.decisions || [])
        .map(
          (d) =>
            `<article><h3>${esc(d.action)}</h3><p>${esc(d.next_decision)}</p><p>${d.verification_required ? "Verification required" : "Review proposed scope"}</p></article>`,
        )
        .join("");
    $("review-summary").textContent +=
      ` Provider timeouts: ${R.review_health?.provider_timeouts || 0}; provider errors: ${R.review_health?.provider_errors || 0}; invalid responses: ${R.review_health?.validation_failures || 0}.`;
    $("checks").innerHTML =
      "<ol><li>Select the file or function you plan to change and inspect its direct callers and reachable dependents.</li><li>Scrub the timeline for changes in that neighborhood. Check both source revisions and parser gaps.</li><li>Validate indirect dispatch, build configuration and relevant behavior before accepting a design change.</li></ol>";
    $("limits").innerHTML =
      "<ul>" +
      [
        ...F.limitations,
        ...(H.limitations || []),
        H.timeline?.gap_policy || "Historical graph frames were not collected.",
        "Inspection order combines file degree and observed function edits; it is not severity or measured failure risk.",
      ]
        .map((s) => "<li>" + esc(s) + "</li>")
        .join("") +
      "</ul>";
    $("language-coverage").innerHTML = F.language_coverage
      ? "<h3>Measured language coverage</h3>" +
        table(
          [
            "Language",
            "Files / parse status",
            "Functions / calls",
            "Binding scope",
          ],
          Object.entries(F.language_coverage).map(([language, row]) => [
            esc(language),
            `${row.files} · ${esc(JSON.stringify(row.status_counts))}`,
            `${row.functions} / ${row.call_sites}`,
            esc(row.dependency_scope),
          ]),
        )
      : '<p class="qualification">This older extraction has no per-language detail. See the file parser gaps and source scope above.</p>';
    $("history-coverage").textContent = JSON.stringify(
      { status: H.status, ...H.coverage },
      null,
      2,
    );
    function promptCard(p, index, prefix, compact = false) {
      const id = `${prefix}-prompt-${index}`;
      const text = `<textarea id="${id}" aria-label="${esc(p.mode + ": " + p.title)}" readonly>${esc(p.prompt)}</textarea>`;
      const copy = `<button class="vbg-button" data-copy="${id}">${icon("copy")}<span>Copy prompt</span></button>`;
      const feedback =
        '<p class="copy-feedback" role="status" aria-live="polite"></p>';
      return compact
        ? `<article class="prompt-card"><div class="prompt-card-head"><span class="prompt-mode">${esc(p.mode)}</span>${copy}</div><h3>${esc(p.title)}</h3>${p.target_files?.length ? `<p class="prompt-scope">${esc(p.target_files.slice(0, 2).join(" · "))}${p.target_files.length > 2 ? ` · ${p.target_files.length - 2} more files` : ""}</p>` : ""}<details><summary>Read prompt</summary>${text}</details>${feedback}</article>`
        : `<details class="handoff"><summary><span>${esc(p.mode)}</span>${esc(p.title)}</summary>${text}${copy}${feedback}</details>`;
    }
    $("overview-prompts").closest("section").hidden = !recommended.length;
    $("overview-prompts").innerHTML = recommended
      .slice(0, 1)
      .map(
        ({ prompt, index }) =>
          `<button class="report-row" data-panel="prompt" data-panel-index="${index}"><span><strong>${esc(prompt.title)}</strong><small>${esc(prompt.mode)} · Saved prompt</small></span><span aria-hidden="true">→</span></button>`,
      )
      .join("");
    const promptRows = prompts.map((p, i) => ({
      primary: ["work_package", "cycle"].includes(p.record_type),
      html: promptCard(p, i, "review"),
    }));
    const secondary = promptRows.filter((p) => !p.primary);
    $("handoffs").innerHTML =
      promptRows
        .filter((p) => p.primary)
        .map((p) => p.html)
        .join("") +
        (secondary.length
          ? `<details class="records"><summary>Further verification questions (${secondary.length})</summary>${secondary.map((p) => p.html).join("")}</details>`
          : "") || "<p>No scoped handoffs were produced.</p>";
    $("play").disabled = !frames.length;
    $("time").disabled = !frames.length;
    document.addEventListener("report:view", (event) =>
      setView(event.detail.view),
    );
    document.addEventListener("report:panel", (event) =>
      openReportPanel(
        event.detail.kind,
        event.detail.index,
        event.detail.trigger,
      ),
    );
    document.addEventListener("report:dismiss", () => closeInspector());
    document.addEventListener("click", async (event) => {
      const copy = event.target.closest("[data-copy]");
      if (!copy) return;
      const text = $(copy.dataset.copy);
      const feedback = copy
        .closest(".prompt-card, .handoff, #lead-link")
        .querySelector(".copy-feedback");
      try {
        await navigator.clipboard.writeText(text.value);
        feedback.textContent =
          "Prompt copied. Review its scope before using it.";
      } catch {
        const disclosure = text.closest("details");
        if (disclosure) disclosure.open = true;
        text.focus();
        text.select();
        text.scrollIntoView({ block: "nearest" });
        feedback.textContent = "Prompt selected. Copy it with your keyboard.";
      }
    });
    $("previous").onclick = () => {
      stop();
      time = Math.max(0, time - 1);
      render();
    };
    $("next").onclick = () => {
      stop();
      time = Math.min(frames.length - 1, time + 1);
      render();
    };
    $("play").onclick = () => {
      if (timer) {
        stop();
        return;
      }
      if (time === frames.length - 1) time = 0;
      playbackLabel(true);
      render();
      timer = setInterval(() => {
        if (time >= frames.length - 1) {
          stop();
          return;
        }
        time++;
        render();
      }, 900);
    };
    $("time").oninput = () => {
      stop();
      time = Number($("time").value);
      render();
    };
    $("baseline").onchange = () => {
      baseline = $("baseline").value;
      render();
    };
    $("level").onchange = () => {
      setLevel($("level").value);
      render();
    };
    $("relation").onchange = render;
    $("network-scope").onchange = render;
    $("network-layout").onchange = render;
    $("matrix-order").onchange = render;
    $("exclude-broad").onchange = render;
    $("search").oninput = render;
    $("focus").onchange = () => {
      focus = $("focus").value;
      if (["map", "timeline"].includes(view)) openInspector($("focus"));
      else render();
    };
    function activate(target) {
      const panel = target.closest("[data-panel]");
      if (panel) {
        openReportPanel(panel.dataset.panel, panel.dataset.panelIndex, panel);
        return;
      }
      const point = target.closest("[data-time]");
      if (point) {
        stop();
        time = Number(point.dataset.time);
        if (point.dataset.compare) {
          baseline = point.dataset.compare;
          $("baseline").value = baseline;
        }
        if (point.dataset.replayLevel) {
          level = point.dataset.replayLevel;
          focus = point.dataset.replayFocus;
          $("level").value = level;
          $("search").value = "";
          $("relation").value = level === "function" ? "call" : "all";
        }
        setView("timeline");
        return;
      }
      const navigation = target.closest("[data-view]");
      const value = target.closest("[data-focus]");
      if (value) {
        focus = value.dataset.focus;
        if (value.dataset.level) {
          level = value.dataset.level;
          $("level").value = level;
          $("relation").value = level === "function" ? "call" : "all";
          $("search").value = "";
        }
      }
      if (navigation) {
        setView(navigation.dataset.view);
        return;
      }
      if (!value) return;
      if (!viewInfo[view]) {
        setView("map");
        return;
      }
      if (["map", "timeline"].includes(view)) openInspector(value);
      else render();
      if (value.hasAttribute("data-change")) {
        $("evidence-tables").open = true;
        $("relationships").open = true;
      }
    }
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !e.defaultPrevented && inspectorOpen) {
        e.preventDefault();
        closeInspector();
      }
    });
    document.addEventListener("click", (e) => {
      if (e.target.closest("[data-inspector-evidence]")) {
        closeInspector(false);
        $("evidence-tables").open = true;
        $("selection").open = true;
        $("relationships").open = true;
        $("selection").scrollIntoView({ block: "center" });
        $("selection").querySelector("summary").focus({ preventScroll: true });
      } else activate(e.target);
    });
    document.addEventListener("keydown", (e) => {
      if (
        ["Enter", " "].includes(e.key) &&
        e.target.matches("g[role=button]")
      ) {
        e.preventDefault();
        activate(e.target);
      }
    });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stop();
    });
    const hashView = () => {
      const desired = new URLSearchParams(location.hash.slice(1)).get("view");
      if (desired || !location.hash)
        setView(desired === "work" ? "review" : desired, false);
    };
    window.addEventListener("hashchange", hashView);
    window.ReportUI.enhance($("overview"));
    window.ReportUI.enhance($("handoffs"));
    window.ReportUI.ready();
    hashView();
  },
  { optional: ["architecture-score.json"] },
);
