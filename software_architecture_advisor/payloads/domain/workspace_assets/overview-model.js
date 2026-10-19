"use strict";
/* Presentation policy over saved facts. No inferred severity or model answers. */
(function (root) {
  function scoreSummary(score) {
    if (!score)
      return {
        value: "Not available",
        note: "No score saved for this report.",
      };
    const number = (value) =>
      Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 });
    const hasStructure = score.dimensions.some(
      (row) =>
        ["modularity", "dependencies"].includes(row.id) && row.points !== null,
    );
    if (!score.assessed_weight)
      return {
        value: "Not assessed",
        note: "More evidence is needed to score this codebase.",
      };
    const coverage = `${score.assessed_weight}/100 scoring points assessed`;
    if (!hasStructure)
      return {
        value: "Evidence incomplete",
        note: `${coverage} · Structural evidence missing`,
      };
    const partial = score.score === null;
    return {
      value: partial
        ? `${number(score.range.lower)}–${number(score.range.upper)} / 100`
        : `${number(score.score)} / 100`,
      note: `Provisional${partial ? " range" : ""} · ${coverage}`,
    };
  }

  function topologyChanges(history) {
    const frames = history.timeline?.frames || [];
    const calls = history.timeline?.calls || {};
    const definitions = history.timeline?.definitions || {};
    const changes = [];
    const path = (id) => id.split("::")[0];
    const difference = (left, right) =>
      [...left].filter((key) => !right.has(key)).length;
    for (let index = 1; index < frames.length; index++) {
      const before = frames[index - 1],
        after = frames[index];
      const gaps = new Set([...before.gaps, ...after.gaps]);
      const filePairs = (frame) =>
        new Set(
          frame.component_edges
            .filter(([a, b]) => !gaps.has(a) && !gaps.has(b))
            .map(([a, b, kind]) => JSON.stringify([a, b, kind])),
        );
      const callPairs = (frame) =>
        new Set(
          frame.calls
            .map((id) => calls[id])
            .filter(
              (c) =>
                c && !gaps.has(path(c.source)) && !gaps.has(path(c.target)),
            )
            .map((c) => JSON.stringify([c.source, c.target])),
        );
      const nodes = (frame) =>
        new Set(
          frame.nodes
            .map((id) => definitions[id])
            .filter((f) => f && !f.ambiguous && !gaps.has(f.path))
            .map((f) => f.id),
        );
      const oldFiles = filePairs(before),
        newFiles = filePairs(after);
      const oldCalls = callPairs(before),
        newCalls = callPairs(after);
      const oldNodes = nodes(before),
        newNodes = nodes(after);
      const row = {
        index,
        commit: after.commit,
        subject: after.subject,
        filesAdded: difference(newFiles, oldFiles),
        filesRemoved: difference(oldFiles, newFiles),
        callsAdded: difference(newCalls, oldCalls),
        callsRemoved: difference(oldCalls, newCalls),
        nodesAdded: difference(newNodes, oldNodes),
        nodesRemoved: difference(oldNodes, newNodes),
        excludedGapPaths: gaps.size,
      };
      row.relationshipChanges =
        row.filesAdded + row.filesRemoved + row.callsAdded + row.callsRemoved;
      row.level =
        row.callsAdded + row.callsRemoved || row.nodesAdded + row.nodesRemoved
          ? "function"
          : "file";
      const oldPairs = row.level === "function" ? oldCalls : oldFiles;
      const newPairs = row.level === "function" ? newCalls : newFiles;
      const touched = new Map();
      for (const key of [...oldPairs, ...newPairs]) {
        if (oldPairs.has(key) && newPairs.has(key)) continue;
        for (const id of JSON.parse(key).slice(0, 2))
          touched.set(id, (touched.get(id) || 0) + 1);
      }
      row.focus =
        [...touched].sort(
          (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
        )[0]?.[0] ||
        [...newNodes].find((id) => !oldNodes.has(id)) ||
        [...oldNodes].find((id) => !newNodes.has(id)) ||
        "";
      if (row.relationshipChanges || row.nodesAdded || row.nodesRemoved)
        changes.push(row);
    }
    return changes
      .sort(
        (a, b) =>
          b.relationshipChanges - a.relationshipChanges ||
          b.nodesAdded + b.nodesRemoved - a.nodesAdded - a.nodesRemoved ||
          b.index - a.index,
      )
      .slice(0, 3);
  }

  function project(facts, history, report) {
    const commits = new Map();
    for (const frame of history.timeline?.frames || []) {
      if (frame.baseline) continue;
      for (const path of new Set(frame.changed_paths))
        commits.set(path, (commits.get(path) || 0) + 1);
    }
    const cycle = [...facts.cycles].sort(
      (a, b) => b.length - a.length || a[0].localeCompare(b[0]),
    )[0];
    const ranked = [...facts.components].sort(
      (a, b) =>
        (commits.get(b.id) || 0) - (commits.get(a.id) || 0) ||
        b.fan_in + b.fan_out - a.fan_in - a.fan_out ||
        a.id.localeCompare(b.id),
    );
    const lead =
      (cycle ? ranked.find((c) => cycle.includes(c.id)) : null) ||
      ranked.find((c) => c.fan_in + c.fan_out > 0);
    const prompts = report.improvement_prompts?.prompts || [];
    const supported = new Set(
      (report.findings || [])
        .filter((f) => f.status === "supported")
        .map((f) => f.id),
    );
    const planIndex = prompts.findIndex(
      (p) =>
        p.mode === "Plan" &&
        p.record_type === "work_package" &&
        !p.omitted_source_records &&
        p.finding_ids?.length &&
        p.finding_ids.every((id) => supported.has(id)) &&
        prompts.some(
          (other) =>
            other.record_id === p.record_id &&
            other.mode === "Implement" &&
            !other.omitted_source_records,
        ),
    );
    const investigateIndex = prompts.findIndex(
      (p) =>
        p.record_type === "cycle" &&
        p.mode === "Investigate" &&
        (!lead || p.target_files?.includes(lead.id)),
    );
    const statuses = facts.coverage.status_counts || {};
    const unresolved = facts.coverage.unresolved_calls || 0;
    const failures = Object.entries(statuses)
      .filter(([key]) => !["parsed", "unsupported"].includes(key))
      .reduce((n, [, value]) => n + value, 0);
    const unsupported = new Map();
    for (const c of facts.components.filter(
      (c) => c.status === "unsupported",
    )) {
      const name = c.id.split("/").at(-1),
        ext = name.includes(".") ? "." + name.split(".").at(-1) : name;
      unsupported.set(ext, (unsupported.get(ext) || 0) + 1);
    }
    return {
      lead,
      cycle,
      hasHistory: (history.timeline?.frames || []).some(
        (frame) => !frame.baseline,
      ),
      planIndex,
      investigateIndex,
      changedCommits: lead ? commits.get(lead.id) || 0 : 0,
      parsed: statuses.parsed || 0,
      parseGaps: failures,
      unsupported: statuses.unsupported || 0,
      unsupportedTypes: [...unsupported].sort(
        (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]),
      ),
      callSites: facts.calls.length,
      linkedCalls: facts.calls.length - unresolved,
      topology: topologyChanges(history),
    };
  }
  function historyCoverage(id, level, components, history, frames) {
    if (!frames.some((f) => !f.baseline))
      return { known: false, partial: false };
    const paths = new Set(frames.flatMap((f) => f.files.map(([path]) => path)));
    const members = [id.split("::")[0]];
    let known = members.some((path) => paths.has(path));
    let partial = members.some((path) => !paths.has(path));
    if (level === "function") {
      known = frames.some((f) =>
        f.nodes.some((key) => history.timeline.definitions[key]?.id === id),
      );
      partial = frames.some((f) => f.gaps.includes(members[0]));
    }
    return { known, partial };
  }
  root.ArchitectureOverview = {
    project,
    topologyChanges,
    historyCoverage,
    scoreSummary,
  };
  if (typeof module !== "undefined") module.exports = root.ArchitectureOverview;
})(typeof window === "undefined" ? globalThis : window);
