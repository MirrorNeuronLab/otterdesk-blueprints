"use strict";
// Evidence-backed call navigation. These are syntax/name candidates, not data-flow slices.
window.renderCodePaths = ({
  graph,
  focus,
  table,
  esc,
  button,
  edgeWitness,
  onSelect,
}) => {
  const $ = (id) => document.getElementById(id);
  const found = new Map([[focus, { id: focus, depth: 0, route: [] }]]);
  const outgoing = new Map(),
    incoming = new Map();
  for (const edge of graph.edges) {
    if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
    if (!incoming.has(edge.target)) incoming.set(edge.target, []);
    outgoing.get(edge.source).push(edge);
    incoming.get(edge.target).push(edge);
  }
  let truncated = false;
  for (const direction of [-1, 1]) {
    const queue = [{ id: focus, depth: 0, route: [] }];
    const seen = new Set([focus]);
    for (let i = 0; i < queue.length; i++) {
      const item = queue[i];
      const edges = (direction < 0 ? incoming : outgoing).get(item.id) || [];
      for (const edge of edges) {
        const id = direction < 0 ? edge.source : edge.target;
        if (seen.has(id)) continue;
        if (Math.abs(item.depth) >= 2 || found.size >= 32) {
          truncated = true;
          continue;
        }
        seen.add(id);
        const next = {
          id,
          depth: item.depth + direction,
          route: direction < 0 ? [edge, ...item.route] : [...item.route, edge],
        };
        queue.push(next);
        if (!found.has(id)) found.set(id, next);
      }
    }
  }
  const nodes = [...found.values()].filter((n) => graph.nodes.has(n.id));
  const rows = new Map();
  for (const node of nodes) {
    const column = rows.get(node.depth) || [];
    column.push(node);
    rows.set(node.depth, column);
  }
  const height = Math.max(
    380,
    ...[...rows.values()].map((row) => row.length * 48 + 55),
  );
  const positions = new Map();
  for (const [depth, column] of rows)
    column.forEach((node, i) =>
      positions.set(node.id, [
        500 + depth * 205,
        ((i + 1) * height) / (column.length + 1),
      ]),
    );
  const chart = d3
    .select($("graph"))
    .html("")
    .append("svg")
    .attr("class", "analysis-viz paths-viz")
    .attr("width", 1000)
    .attr("height", height)
    .attr("viewBox", `0 0 1000 ${height}`)
    .attr("role", "group")
    .attr("aria-label", "Candidate call paths into and out of " + focus);
  chart
    .append("defs")
    .append("marker")
    .attr("id", "path-arrow")
    .attr("viewBox", "0 0 10 10")
    .attr("refX", 9)
    .attr("refY", 5)
    .attr("markerWidth", 5)
    .attr("markerHeight", 5)
    .attr("orient", "auto")
    .append("path")
    .attr("d", "M0,0 L10,5 L0,10 Z")
    .attr("fill", "#769287");
  const witnessEdges = new Map(
    nodes.flatMap((n) => n.route).map((e) => [e.source + "\0" + e.target, e]),
  );
  for (const edge of witnessEdges.values()) {
    const [x1, y1] = positions.get(edge.source),
      [x2, y2] = positions.get(edge.target);
    chart
      .append("path")
      .attr("class", "edge")
      .attr("marker-end", "url(#path-arrow)")
      .attr(
        "d",
        `M${x1 + 82},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2 - 82},${y2}`,
      );
  }
  const marks = chart
    .selectAll("g.path-node")
    .data(nodes)
    .join("g")
    .attr("class", "path-node")
    .attr("transform", (n) => `translate(${positions.get(n.id)})`)
    .attr("role", "button")
    .attr("tabindex", 0)
    .attr("aria-label", (n) => "Inspect " + n.id)
    .on("click", (event, n) => onSelect(n.id))
    .on("keydown", (event, n) => {
      if (["Enter", " "].includes(event.key)) {
        event.preventDefault();
        onSelect(n.id);
      }
    });
  marks
    .append("rect")
    .attr("class", (n) => "node " + (n.id === focus ? "active" : ""))
    .attr("x", -82)
    .attr("y", -17)
    .attr("width", 164)
    .attr("height", 34);
  marks
    .append("text")
    .attr("text-anchor", "middle")
    .attr("y", 4)
    .text((n) => n.id.split("::").at(-1).slice(0, 23));
  marks.append("title").text((n) => n.id);
  $("graph-title").textContent = "Evidence-backed call paths";
  $("graph-count").textContent =
    `${nodes.length} functions · ${witnessEdges.size} witnessed call pairs`;
  document.querySelector(".legend").textContent =
    "Callers ← selected function → callees · Up to two hops each way · Arrows follow candidate calls";
  $("graph-note").textContent =
    `Bounded to 32 functions${truncated ? " (truncated)" : ""}. One shortest witness path per reached function. Name resolution is conservative; macros, indirect dispatch and build conditions may hide calls. This is call navigation, not a program slice, data-flow proof or runtime execution order.`;
  $("visual-detail").innerHTML = table(
    ["Function / direction", "Candidate call path and source witnesses"],
    nodes
      .filter((n) => n.id !== focus)
      .map((n) => [
        button(n.id, n.id, "function") +
          `<br>${n.depth < 0 ? "Caller" : "Callee"} · ${Math.abs(n.depth)} hops`,
        n.route
          .map(
            (e) => `${esc(e.source)} → ${esc(e.target)}<br>${edgeWitness(e)}`,
          )
          .join("<br>"),
      ]),
  );
};
