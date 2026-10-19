"use strict";
// Every view consumes the same immutable syntax graph and commit frames.
// D3 is bundled locally; there are no remote scripts or graph services.
window.renderArchitectureView = function (ctx) {
  const {
    kind,
    graph,
    value,
    focus,
    level,
    frames,
    history,
    order,
    excludeBroad,
    search,
    table,
    esc,
    button,
    edgeWitness,
    onSelect,
  } = ctx;
  const $ = (id) => document.getElementById(id),
    path = (id) => id.split("::")[0];
  $("visual-detail").replaceChildren();
  const host = d3.select($("graph")).html("");
  const title = (text) => {
    $("graph-title").textContent = text;
  };
  const note = (text) => {
    $("graph-note").textContent = text;
  };
  const legend = (text) => {
    document.querySelector(".legend").textContent = text;
  };
  const svg = (width, height, label) =>
    host
      .append("svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("role", "group")
      .attr("aria-label", label)
      .attr("class", "analysis-viz")
      .attr("width", width)
      .attr("height", height);
  function activate(selection, handler, label) {
    selection
      .attr("role", "button")
      .attr("tabindex", 0)
      .attr("aria-label", label)
      .on("click", (event, d) => handler(d))
      .on("keydown", (event, d) => {
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault();
          handler(d);
        }
      });
  }
  const degree = new Map();
  for (const e of graph.edges) {
    degree.set(e.source, (degree.get(e.source) || 0) + 1);
    degree.set(e.target, (degree.get(e.target) || 0) + 1);
  }
  const project = (id) => (level === "file" ? path(id) : id);
  const cycles = new Map();
  (value.cycles || []).forEach((group, index) =>
    group.forEach((id) => cycles.set(project(id), index)),
  );
  const matching = [...graph.nodes.keys()].filter(
    (id) => !search || id.toLowerCase().includes(search.toLowerCase()),
  );
  const ranked = matching.sort(
    (a, b) =>
      (a === focus ? -1 : b === focus ? 1 : 0) ||
      (degree.get(b) || 0) - (degree.get(a) || 0) ||
      a.localeCompare(b),
  );
  function commitsFor(frame) {
    if (level === "function")
      return [
        ...new Set(frame.event_indices.map((i) => history.events[i].function)),
      ];
    return [...new Set(frame.changed_paths.map(project))];
  }
  const commitSets = frames
    .filter(
      (f) => !f.baseline && (!excludeBroad || f.changed_paths.length <= 20),
    )
    .map((f) => ({ frame: f, ids: new Set(commitsFor(f)) }));
  const churn = new Map();
  for (const { ids } of commitSets)
    for (const id of ids) churn.set(id, (churn.get(id) || 0) + 1);
  if (kind === "matrix" || kind === "coupling") {
    let ids = ranked.slice(0, 80);
    if (kind === "coupling")
      ids.sort(
        (a, b) =>
          (churn.get(b) || 0) - (churn.get(a) || 0) || a.localeCompare(b),
      );
    else
      ids.sort((a, b) =>
        order === "degree"
          ? (degree.get(b) || 0) - (degree.get(a) || 0) || a.localeCompare(b)
          : (order === "cycles"
              ? (cycles.get(a) ?? 1e8) - (cycles.get(b) ?? 1e8)
              : 0) || a.localeCompare(b),
      );
    const cell = 17,
      left = 180,
      top = 160,
      width = left + ids.length * cell + 18,
      height = top + ids.length * cell + 18;
    const chart = svg(
      Math.max(620, width),
      Math.max(360, height),
      kind === "matrix"
        ? "Dependency structure matrix: row source to column dependency"
        : "Temporal coupling matrix: joint changed commits",
    );
    chart.classed("matrix-viz", true);
    const x = d3
        .scaleBand()
        .domain(ids)
        .range([left, left + ids.length * cell]),
      y = d3
        .scaleBand()
        .domain(ids)
        .range([top, top + ids.length * cell]);
    const weights = new Map();
    for (const e of graph.edges) {
      const k = e.source + "\0" + e.target;
      weights.set(k, (weights.get(k) || 0) + e.sites);
    }
    const cells = [];
    for (const a of ids)
      for (const b of ids) {
        if (a === b) continue;
        let count = weights.get(a + "\0" + b) || 0,
          shared = [];
        if (kind === "coupling") {
          shared = commitSets.filter((c) => c.ids.has(a) && c.ids.has(b));
          count = shared.length;
        }
        cells.push({
          source: a,
          target: b,
          count,
          shared,
          cycle: cycles.has(a) && cycles.get(a) === cycles.get(b),
        });
      }
    const max = d3.max(cells, (d) => d.count) || 1,
      color = d3
        .scaleSequential(d3.interpolateGreys)
        .domain([0, Math.log1p(max)]);
    chart
      .append("g")
      .selectAll("rect")
      .data(ids)
      .join("rect")
      .attr("x", (d) => x(d))
      .attr("y", (d) => y(d))
      .attr("width", cell - 1)
      .attr("height", cell - 1)
      .attr("fill", "#dfe4dc");
    chart
      .append("text")
      .attr("x", 8)
      .attr("y", top - 12)
      .attr("class", "matrix-label")
      .text(
        kind === "matrix" ? "Source ↓ / dependency →" : "Joint changed commits",
      );
    const marks = chart
      .append("g")
      .selectAll("rect")
      .data(cells)
      .join("rect")
      .attr("x", (d) => x(d.target))
      .attr("y", (d) => y(d.source))
      .attr("width", cell - 1)
      .attr("height", cell - 1)
      .attr("fill", (d) => (d.count ? color(Math.log1p(d.count)) : "#f1f3ef"))
      .attr("stroke", (d) =>
        kind === "matrix" && d.count && d.cycle ? "#b58025" : "none",
      );
    marks.filter((d) => !d.count).attr("aria-hidden", "true");
    marks
      .append("title")
      .text((d) =>
        kind === "matrix"
          ? `${d.source} → ${d.target}: ${d.count} source sites${d.cycle ? " · same file-level dependency cycle" : ""}`
          : `${d.source} + ${d.target}: ${d.count} joint commits; denominators ${churn.get(d.source) || 0} and ${churn.get(d.target) || 0}`,
      );
    activate(
      marks.filter((d) => d.count > 0),
      (d) => {
        onSelect(d.source);
        if (kind === "coupling") {
          $("visual-detail").innerHTML =
            `<h3>${esc(d.source)} + ${esc(d.target)}</h3><p>${d.count} joint changed commits out of ${churn.get(d.source) || 0} and ${churn.get(d.target) || 0} individual changed commits in this window. Correlation does not establish a shared responsibility.</p>` +
            table(
              ["Commit", "Date / subject"],
              d.shared
                .slice(0, 80)
                .map((c) => [
                  esc(c.frame.commit.slice(0, 12)),
                  esc(c.frame.date) + "<br>" + esc(c.frame.subject),
                ]),
            );
        } else {
          const edges = graph.edges.filter(
            (e) => e.source === d.source && e.target === d.target,
          );
          $("visual-detail").innerHTML =
            `<h3>${esc(d.source)} → ${esc(d.target)}</h3>` +
            table(
              ["Kind / sites", "Source witness"],
              edges.map((e) => [esc(e.kind) + " / " + e.sites, edgeWitness(e)]),
            );
        }
        $("visual-records").hidden = false;
        $("visual-records").open = true;
      },
      (d) =>
        kind === "matrix"
          ? `Inspect ${d.source} to ${d.target}: ${d.count} source sites`
          : `Inspect ${d.count} co-change commits for ${d.source} and ${d.target}`,
    );
    const rows = chart
      .append("g")
      .selectAll("text")
      .data(ids)
      .join("text")
      .attr("x", left - 8)
      .attr("y", (d) => y(d) + 12)
      .attr("text-anchor", "end")
      .attr("class", "matrix-label")
      .text((d) => (d.length > 30 ? "…" + d.slice(-29) : d));
    rows.append("title").text((d) => d);
    activate(rows, onSelect, (d) => "Inspect " + d);
    const cols = chart
      .append("g")
      .selectAll("text")
      .data(ids)
      .join("text")
      .attr(
        "transform",
        (d) => `translate(${x(d) + 11},${top - 8}) rotate(-55)`,
      )
      .attr("text-anchor", "start")
      .attr("class", "matrix-label")
      .text((d) => (d.length > 28 ? "…" + d.slice(-27) : d));
    cols.append("title").text((d) => d);
    $("graph-count").textContent = `${ids.length}/${matching.length} entities`;
    if (kind === "matrix") {
      title("Dependency structure matrix");
      legend(
        "Row refers to column · Color = source site count (log scale) · Amber outline = within a file-level dependency cycle",
      );
      note(
        `Showing up to 80 entities, ranked by coupling before reordering. Search to narrow the scope. ${value.cycles?.length || 0} file-level cycle groups measured. Empty cells mean no extracted edge, not proven independence. No approved layer rules were supplied; layer violations are not inferred.`,
      );
    } else {
      title("Temporal coupling heatmap");
      legend(
        "Darker = more joint changed commits · Symmetric matrix · Select a filled cell for matching commits",
      );
      const omitted = frames.filter(
        (f) => !f.baseline && excludeBroad && f.changed_paths.length > 20,
      ).length;
      note(
        `Co-change uses ${commitSets.length} committed states up to the selected time; ${omitted} commits touching more than 20 supported files excluded by the explicit filter. File changes include formatting and comments; function changes require complete parsed pairs. Missing history is not zero coupling.`,
      );
      const pairs = cells
        .filter((c) => c.count && c.source < c.target)
        .sort((a, b) => b.count - a.count || a.source.localeCompare(b.source));
      $("visual-detail").innerHTML =
        table(
          ["Pair", "Joint / individual commits"],
          pairs
            .slice(0, 12)
            .map((c) => [
              button(c.source, c.source) + " + " + button(c.target, c.target),
              `${c.count} / (${churn.get(c.source) || 0}, ${churn.get(c.target) || 0})`,
            ]),
        ) +
        (pairs.length > 12
          ? `<p>First 12/${pairs.length} pairs; cells retain every displayed pair.</p>`
          : "");
    }
    return;
  }
  if (kind === "treemap") {
    title("Size and churn");
    legend(
      "Area = physical source lines · Color = observed changed commits · Grey = history unknown · Not severity",
    );
    const children = ranked.map((id) => {
      const row = graph.nodes.get(id);
      const coverage = window.ArchitectureOverview.historyCoverage(
        row.id,
        level,
        value.components,
        history,
        frames,
      );
      return {
        name: row.id,
        id: row.id,
        size: Math.max(
          0,
          row.physical_lines ?? row.functions.reduce((n, f) => n + f.lines, 0),
        ),
        changes: coverage.known ? churn.get(row.id) || 0 : null,
        partial: coverage.partial,
      };
    });
    const root = d3
      .hierarchy({ name: "source", children })
      .sum((d) => d.size || 0)
      .sort(
        (a, b) => b.value - a.value || a.data.name.localeCompare(b.data.name),
      );
    d3.treemap().size([920, 470]).paddingInner(3).paddingOuter(3)(root);
    const chart = svg(920, 470, "File or function size and changed commits"),
      color = d3
        .scaleSequential(d3.interpolateGreens)
        .domain([0, d3.max(root.leaves(), (d) => d.data.changes) || 1]);
    const groups = chart
      .selectAll("g.leaf")
      .data(root.leaves().filter((d) => d.value > 0))
      .join("g")
      .attr("class", "leaf")
      .attr("transform", (d) => `translate(${d.x0},${d.y0})`);
    groups
      .append("rect")
      .attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0))
      .attr("fill", (d) =>
        d.data.changes === null ? "#e6e7e4" : color(d.data.changes),
      )
      .attr("stroke", (d) => (d.data.id === focus ? "#182c23" : "white"))
      .attr("stroke-width", (d) => (d.data.id === focus ? 3 : 1));
    groups
      .append("title")
      .text(
        (d) =>
          `${d.data.id}: ${d.data.size} physical lines; ${d.data.changes === null ? "history unknown" : `${d.data.partial ? "at least " : ""}${d.data.changes} observed changed commits`}`,
      );
    groups
      .filter((d) => d.x1 - d.x0 > 80 && d.y1 - d.y0 > 32)
      .append("text")
      .attr("x", 7)
      .attr("y", 17)
      .attr(
        "class",
        (d) =>
          "treemap-label" +
          (d.data.changes >
          (d3.max(root.leaves(), (x) => x.data.changes) || 1) * 0.5
            ? " dark"
            : ""),
      )
      .text((d) =>
        d.data.name
          .split("/")
          .at(-1)
          .slice(0, Math.floor((d.x1 - d.x0 - 12) / 7)),
      );
    groups
      .filter((d) => d.x1 - d.x0 > 80 && d.y1 - d.y0 > 50)
      .append("text")
      .attr("x", 7)
      .attr("y", 34)
      .attr(
        "class",
        (d) =>
          "treemap-label" +
          (d.data.changes >
          (d3.max(root.leaves(), (x) => x.data.changes) || 1) * 0.5
            ? " dark"
            : ""),
      )
      .text(
        (d) =>
          `${d.data.size} lines · ${d.data.changes === null ? "history unknown" : `${d.data.partial ? "≥" : ""}${d.data.changes} commits`}`,
      );
    activate(
      groups,
      (d) => onSelect(d.data.id),
      (d) =>
        `Inspect ${d.data.id}: ${d.data.size} source lines; ${d.data.changes === null ? "history unknown" : `${d.data.partial ? "at least " : ""}${d.data.changes} observed changed commits`}`,
    );
    $("graph-count").textContent =
      `${root.leaves().filter((d) => d.value > 0).length} entities with measured size`;
    note(
      "Inspect large, often changed areas first when planning a change. Grey means history was not measured for that entity; ≥ marks a lower bound from partial scope or parser gaps. Code health and semantic complexity are not measured. Text-only files retain measured size; zero-sized files have no area. Color includes formatting/comment edits.",
    );
    $("visual-detail").innerHTML = table(
      ["Entity", "Source lines", "Changed commits"],
      root
        .leaves()
        .sort((a, b) => b.data.changes - a.data.changes || b.value - a.value)
        .slice(0, 15)
        .map((d) => [
          button(d.data.id, d.data.id),
          String(d.data.size),
          d.data.changes === null
            ? "Unknown"
            : `${d.data.partial ? "≥" : ""}${d.data.changes}`,
        ]),
    );
    return;
  }
  if (kind === "impact") {
    title("Change impact");
    legend(
      "Arrows point from consumers to dependencies · Columns = minimum dependency distance · One shortest witness path per consumer",
    );
    const reverse = new Map();
    for (const edge of graph.edges) {
      if (!reverse.has(edge.target)) reverse.set(edge.target, []);
      reverse.get(edge.target).push(edge);
    }
    const queue = [{ id: focus, hops: 0, route: [] }],
      seen = new Set([focus]);
    let truncated = false;
    for (let index = 0; index < queue.length; index++) {
      const item = queue[index];
      if (item.hops >= 4) {
        if (reverse.get(item.id)?.some((e) => !seen.has(e.source)))
          truncated = true;
        continue;
      }
      for (const edge of reverse.get(item.id) || []) {
        if (seen.has(edge.source)) continue;
        if (seen.size >= 128) {
          truncated = true;
          continue;
        }
        seen.add(edge.source);
        queue.push({
          id: edge.source,
          hops: item.hops + 1,
          route: [...item.route, edge],
        });
      }
    }
    const shown = queue.slice(0, 32),
      positions = new Map(),
      counts = new Map();
    for (const item of shown) {
      const row = counts.get(item.hops) || 0;
      counts.set(item.hops, row + 1);
      positions.set(item.id, [110 + item.hops * 190, 46 + row * 62]);
    }
    const height = Math.max(
      230,
      ...[...counts.values()].map((n) => n * 64 + 70),
    );
    const maxHop = d3.max(shown, (item) => item.hops) || 0;
    const width = Math.max(620, (maxHop + 1) * 210 + 40);
    counts.clear();
    for (const item of shown)
      counts.set(item.hops, (counts.get(item.hops) || 0) + 1);
    const rowIndices = new Map();
    for (const item of shown) {
      const row = rowIndices.get(item.hops) || 0;
      rowIndices.set(item.hops, row + 1);
      positions.set(item.id, [
        120 + item.hops * 210,
        35 + ((row + 1) * (height - 50)) / (counts.get(item.hops) + 1),
      ]);
    }
    const chart = svg(
      width,
      height,
      "Transitive dependent graph for " + focus,
    ).classed("impact-viz", true);
    for (let hop = 0; hop <= maxHop; hop++)
      chart
        .append("text")
        .attr("x", 120 + hop * 210)
        .attr("y", 22)
        .attr("text-anchor", "middle")
        .attr("class", "column-label")
        .text(
          hop === 0
            ? "Selected"
            : hop === 1
              ? "Direct consumers"
              : hop + " hops",
        );
    chart
      .append("defs")
      .append("marker")
      .attr("id", "impact-arrow")
      .attr("viewBox", "0 0 10 10")
      .attr("refX", 9)
      .attr("refY", 5)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,0 L10,5 L0,10 Z")
      .attr("fill", "#7c9081");
    for (const edge of shown.slice(1).flatMap((item) => item.route.slice(-1))) {
      if (!positions.has(edge.source) || !positions.has(edge.target)) continue;
      const [x1, y1] = positions.get(edge.source),
        [x2, y2] = positions.get(edge.target);
      chart
        .append("path")
        .attr("d", `M${x1 - 80},${y1} L${x2 + 80},${y2}`)
        .attr("class", "edge")
        .attr("marker-end", "url(#impact-arrow)");
    }
    const marks = chart
      .selectAll("g.impact-node")
      .data(shown)
      .join("g")
      .attr("class", "impact-node")
      .attr("transform", (d) => `translate(${positions.get(d.id)})`);
    marks
      .append("rect")
      .attr("class", (d) => "node " + (d.hops === 0 ? "active" : ""))
      .attr("x", -82)
      .attr("y", -20)
      .attr("rx", 6)
      .attr("width", 164)
      .attr("height", 40);
    marks
      .append("text")
      .attr("text-anchor", "middle")
      .attr("y", -2)
      .text((d) => {
        const label = d.id.split("::").at(-1).split("/").at(-1);
        return label.length > 23 ? label.slice(0, 22) + "…" : label;
      });
    marks
      .append("text")
      .attr("text-anchor", "middle")
      .attr("y", 12)
      .attr("class", "node-context")
      .text((d) => {
        const label = path(d.id);
        return label.length > 25 ? "…" + label.slice(-24) : label;
      });
    marks.append("title").text((d) => d.id + " · " + d.hops + " hops");
    activate(
      marks,
      (d) => onSelect(d.id),
      (d) => "Inspect " + d.id,
    );
    $("graph-count").textContent =
      `${shown.length}/${queue.length} reachable entities`;
    note(
      `${queue.length - 1} candidate dependents reached within four hops and 128 entities${truncated ? " (truncated)" : ""}. Graph shows up to 32 nodes; the table retains one shortest witness route per reached consumer. Reachability scopes review and testing; it does not establish behavioral impact or compatibility.`,
    );
    $("visual-detail").innerHTML = table(
      ["Reachable consumer", "Hops", "Evidence path to selected root"],
      queue.slice(1).map((item) => [
        button(item.id, item.id),
        String(item.hops),
        item.route
          .slice()
          .reverse()
          .map(
            (e) => `${esc(e.source)} → ${esc(e.target)}<br>${edgeWitness(e)}`,
          )
          .join("<br>"),
      ]),
    );
  }
};
