"use strict";
// Pure presentation of captured evidence. Never changes persisted analysis records.
(function (root) {
  function context(frames, selected, baseline = "0") {
    const index = Math.max(0, Math.min(frames.length - 1, selected));
    const before =
      baseline === "previous"
        ? Math.max(0, index - 1)
        : Math.max(0, Math.min(frames.length - 1, Number(baseline) || 0));
    const describe = (frame, i) => ({
      revision: frame?.commit || "",
      short: (frame?.commit || "").slice(0, 12),
      label: i === 0 ? "Window baseline" : frame?.subject || "Selected commit",
      date: frame?.date || null,
    });
    return {
      index,
      before,
      same: index === before,
      mode:
        baseline === "previous"
          ? "Since previous commit"
          : before === 0
            ? "Since window start"
            : "Custom comparison",
      baseline: describe(frames[before], before),
      selected: describe(frames[index], index),
    };
  }
  const edgeKey = (e) => [e.source, e.target, e.kind].join("\0");
  const path = (id) => id.split("::")[0];
  const order = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const hashes = (node) =>
    JSON.stringify(
      (node?.functions || []).map((f) => [f.id, f.body_sha256]).sort(),
    );
  function present({ graph, old = null, gaps = [] }) {
    const gapSet = new Set(gaps),
      unknown = (id) => gapSet.has(path(id));
    const nodes = new Map([...(old?.nodes || []), ...graph.nodes]);
    const known = (e) => !unknown(e.source) && !unknown(e.target);
    const nowEdges = new Map(graph.edges.map((e) => [edgeKey(e), e]));
    const oldEdges = new Map((old?.edges || []).map((e) => [edgeKey(e), e]));
    const added = new Set(),
      removed = new Set(),
      statuses = new Map();
    if (old) {
      for (const [key, e] of nowEdges)
        if (!oldEdges.has(key) && known(e)) added.add(key);
      for (const [key, e] of oldEdges)
        if (!nowEdges.has(key) && known(e)) removed.add(key);
    }
    const entries = new Map(
      [...nodes.keys()].map((id) => [
        id,
        {
          id,
          before: old?.nodes.get(id) || null,
          after: graph.nodes.get(id) || null,
          status: unknown(id)
            ? "Comparison incomplete"
            : !old
              ? "Current capture"
              : !old.nodes.has(id)
                ? "Added"
                : !graph.nodes.has(id)
                  ? "Removed"
                  : hashes(old.nodes.get(id)) !== hashes(graph.nodes.get(id))
                    ? "Definition edited"
                    : "Unchanged",
          incomplete: unknown(id),
          added: [],
          removed: [],
          beforeIn: 0,
          afterIn: 0,
          beforeOut: 0,
          afterOut: 0,
          cycleBefore: false,
          cycleAfter: false,
          cycleChanged: false,
          cycleIncomplete: false,
        },
      ]),
    );
    for (const [edges, prefix] of [
      [oldEdges, "before"],
      [nowEdges, "after"],
    ])
      for (const e of edges.values())
        if (known(e)) {
          if (entries.has(e.source)) entries.get(e.source)[prefix + "Out"]++;
          if (entries.has(e.target)) entries.get(e.target)[prefix + "In"]++;
        }
    for (const [keys, edges, field] of [
      [added, nowEdges, "added"],
      [removed, oldEdges, "removed"],
    ])
      for (const key of keys) {
        const e = edges.get(key);
        for (const id of new Set([e.source, e.target]))
          entries.get(id)?.[field].push(e);
      }
    const layout =
      root.ArchitectureGraphLayout ||
      (typeof require !== "undefined" ? require("./graph-layout.js") : null);
    if (old && layout) {
      // Union SCCs touching gaps can conceal a cycle path in either state.
      const union = {
        ids: [...nodes.keys()],
        edges: [...oldEdges.values(), ...nowEdges.values()],
      };
      const uncertain = new Set(
        layout
          .cycleGroups(union)
          .filter((group) => group.some(unknown))
          .flat(),
      );
      const beforeCycles = new Set(
        layout
          .cycleGroups({ ids: [...old.nodes.keys()], edges: old.edges })
          .flat(),
      );
      const afterCycles = new Set(
        layout
          .cycleGroups({ ids: [...graph.nodes.keys()], edges: graph.edges })
          .flat(),
      );
      for (const row of entries.values()) {
        row.cycleIncomplete = uncertain.has(row.id) || row.incomplete;
        row.cycleBefore = beforeCycles.has(row.id);
        row.cycleAfter = afterCycles.has(row.id);
        row.cycleChanged =
          !row.cycleIncomplete && row.cycleBefore !== row.cycleAfter;
      }
    }
    for (const row of entries.values()) {
      row.changedRelationships = row.added.length + row.removed.length;
      row.topologyChanged =
        row.changedRelationships > 0 ||
        row.cycleChanged ||
        ["Added", "Removed"].includes(row.status);
      row.definitionOnly =
        row.status === "Definition edited" && !row.topologyChanged;
      if (["Added", "Removed", "Definition edited"].includes(row.status))
        statuses.set(
          row.id,
          {
            Added: "added",
            Removed: "removed",
            "Definition edited": "modified",
          }[row.status],
        );
    }
    const highlights = [...entries.values()]
      .filter((r) => !r.incomplete && (r.topologyChanged || r.definitionOnly))
      .sort(
        (a, b) =>
          b.changedRelationships - a.changedRelationships || order(a.id, b.id),
      )
      .slice(0, 3);
    const edits = [...entries.values()].filter(
      (r) => r.status === "Definition edited",
    ).length;
    const addedNodes = [...statuses.values()].filter(
      (v) => v === "added",
    ).length;
    const removedNodes = [...statuses.values()].filter(
      (v) => v === "removed",
    ).length;
    const incomplete = gapSet.size > 0;
    const summary = !old
      ? "Current capture"
      : `${added.size} added / ${removed.size} removed relationships · ${addedNodes} added / ${removedNodes} removed · ${edits} definition edits`;
    return {
      entries,
      statuses,
      added,
      removed,
      gaps: gapSet,
      incomplete,
      highlights,
      edits,
      addedNodes,
      removedNodes,
      summary,
    };
  }
  function describe(row) {
    if (row.incomplete) return "Comparison incomplete · parser gap";
    if (row.definitionOnly)
      return "Definition edited · no observed topology change";
    const parts = [];
    if (["Added", "Removed"].includes(row.status)) parts.push(row.status);
    if (row.changedRelationships)
      parts.push(
        `Relationships +${row.added.length} / −${row.removed.length}; incoming ${row.beforeIn} → ${row.afterIn}, outgoing ${row.beforeOut} → ${row.afterOut}`,
      );
    if (row.cycleChanged)
      parts.push(
        `Observed cycle participation ${row.cycleBefore ? "yes" : "no"} → ${row.cycleAfter ? "yes" : "no"}`,
      );
    if (row.status === "Definition edited") parts.push("Definition edited");
    return parts.join(" · ") || row.status;
  }
  function changeIds(change, displayedIds, displayedEdges) {
    const shown = new Set(displayedIds),
      changed = new Set();
    for (const id of change?.statuses.keys() || [])
      if (shown.has(id)) changed.add(id);
    for (const row of change?.entries?.values() || [])
      if (row.cycleChanged && shown.has(row.id)) changed.add(row.id);
    for (const e of displayedEdges)
      if (change?.added.has(edgeKey(e)) || change?.removed.has(edgeKey(e)))
        for (const id of [e.source, e.target])
          if (shown.has(id)) changed.add(id);
    return changed;
  }
  function bounds(nodes) {
    let x0 = Infinity,
      y0 = Infinity,
      x1 = -Infinity,
      y1 = -Infinity;
    for (const n of nodes)
      if (Number.isFinite(n.x) && Number.isFinite(n.y)) {
        x0 = Math.min(x0, n.x);
        x1 = Math.max(x1, n.x);
        y0 = Math.min(y0, n.y);
        y1 = Math.max(y1, n.y);
      }
    return Number.isFinite(x0) ? { x0, y0, x1, y1 } : null;
  }
  function investigation(prompts, id) {
    const source = path(id);
    const index = prompts.findIndex(
      (p) =>
        p.mode === "Investigate" && (p.target_files || []).includes(source),
    );
    return index < 0 ? null : { prompt: prompts[index], index };
  }
  function coverage({
    graph,
    old,
    plan,
    change,
    capturedFiles,
    comparisonFiles,
    level,
  }) {
    const ids = new Set([...graph.nodes.keys(), ...(old?.nodes.keys() || [])]);
    const scoped = new Set(plan.scopeIds),
      displayed = new Set(plan.ids);
    let eligible = 0,
      shown = 0,
      gapNodes = 0;
    for (const id of ids) {
      if (scoped.has(id)) eligible++;
      if (displayed.has(id)) shown++;
      if (change?.gaps?.has(path(id))) gapNodes++;
    }
    return {
      unit: level === "file" ? "files" : "functions",
      capturedFiles,
      comparisonFiles,
      inventory: ids.size,
      comparable: ids.size - gapNodes,
      scopeEligible: eligible,
      displayed: shown,
      hiddenByScope: ids.size - eligible,
      hiddenByLimit: eligible - shown,
      gapNodes,
      gapFiles: change?.gaps?.size || 0,
      historicalInventory: plan.totalNodes,
      relationshipLimit: plan.omittedEdges,
    };
  }
  const api = {
    context,
    present,
    describe,
    edgeKey,
    changeIds,
    bounds,
    investigation,
    coverage,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ArchitectureComparison = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
