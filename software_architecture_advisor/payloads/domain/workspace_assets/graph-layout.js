"use strict";
if (typeof document === "undefined" && typeof importScripts === "function")
  importScripts("vendor/d3.v7.min.js");
// Source-graph presentation only. SCCs are measured candidate cycles, not modules.
// This file runs unchanged in a dedicated worker, local-file mode, and Node tests.
(function (root) {
  const compare = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const limits = Object.freeze({ nodes: 10000, edges: 50000 });
  function select({
    ids,
    edges,
    focus = "",
    scope = "connected",
    maxNodes = limits.nodes,
    maxEdges = limits.edges,
  }) {
    const known = new Set(ids),
      degree = new Map(),
      peers = new Map();
    const valid = edges.filter(
      (e) => known.has(e.source) && known.has(e.target),
    );
    for (const e of valid) {
      degree.set(e.source, (degree.get(e.source) || 0) + 1);
      degree.set(e.target, (degree.get(e.target) || 0) + 1);
      if (scope === "neighbors") {
        if (!peers.has(e.source)) peers.set(e.source, new Set());
        if (!peers.has(e.target)) peers.set(e.target, new Set());
        peers.get(e.source).add(e.target);
        peers.get(e.target).add(e.source);
      }
    }
    let eligible;
    if (scope === "neighbors") {
      eligible = new Set(known.has(focus) ? [focus] : []);
      let frontier = [...eligible];
      for (let hop = 0; hop < 2; hop++) {
        const next = [];
        for (const id of frontier)
          for (const peer of peers.get(id) || [])
            if (!eligible.has(peer)) {
              eligible.add(peer);
              next.push(peer);
            }
        frontier = next;
      }
    } else
      eligible = new Set(
        [...known].filter(
          (id) => scope === "all" || degree.has(id) || id === focus,
        ),
      );
    const ranked = [...eligible].sort(
      (a, b) =>
        (a === focus ? -1 : b === focus ? 1 : 0) ||
        (degree.get(b) || 0) - (degree.get(a) || 0) ||
        compare(a, b),
    );
    const selected = ranked.slice(0, maxNodes).sort(compare),
      kept = new Set(selected);
    const scopedEdges = valid.filter(
      (e) => eligible.has(e.source) && eligible.has(e.target),
    );
    const selectedEdges = scopedEdges
      .filter((e) => kept.has(e.source) && kept.has(e.target))
      .sort(
        (a, b) =>
          Number(b.source === focus || b.target === focus) -
            Number(a.source === focus || a.target === focus) ||
          compare(a.source, b.source) ||
          compare(a.target, b.target) ||
          compare(a.kind || "", b.kind || ""),
      );
    return {
      ids: selected,
      edges: selectedEdges
        .slice(0, maxEdges)
        .sort(
          (a, b) =>
            compare(a.source, b.source) ||
            compare(a.target, b.target) ||
            compare(a.kind || "", b.kind || ""),
        ),
      totalNodes: known.size,
      scopeNodes: eligible.size,
      scopeIds: [...eligible].sort(compare),
      scopeEdges: scopedEdges.length,
      omittedNodes: eligible.size - selected.length,
      omittedEdges:
        scopedEdges.length - Math.min(maxEdges, selectedEdges.length),
      hiddenNodes: known.size - eligible.size,
      invalidEdges: edges.length - valid.length,
    };
  }
  function stronglyConnected({ ids, edges }) {
    if (!Array.isArray(ids) || !Array.isArray(edges))
      throw new TypeError("Graph needs entity and relationship arrays.");
    ids = [...new Set(ids)].sort(compare);
    const index = new Map(ids.map((id, i) => [id, i])),
      n = ids.length;
    const out = Array.from({ length: n }, () => []),
      incoming = Array.from({ length: n }, () => []),
      pairs = new Set();
    for (const e of edges) {
      const a = index.get(e.source),
        b = index.get(e.target);
      if (a === undefined || b === undefined) continue;
      const key = a + ":" + b;
      if (pairs.has(key)) continue;
      pairs.add(key);
      out[a].push(b);
      incoming[b].push(a);
    }
    for (const row of [...out, ...incoming]) row.sort((a, b) => a - b);
    // Iterative Kosaraju: deep call chains cannot overflow the JavaScript stack.
    const visited = new Uint8Array(n),
      finish = [];
    for (let start = 0; start < n; start++) {
      if (visited[start]) continue;
      const stack = [start],
        offsets = [0];
      visited[start] = 1;
      while (stack.length) {
        const last = stack.length - 1,
          v = stack[last],
          next = offsets[last];
        if (next < out[v].length) {
          const w = out[v][next];
          offsets[last]++;
          if (!visited[w]) {
            visited[w] = 1;
            stack.push(w);
            offsets.push(0);
          }
        } else {
          finish.push(v);
          stack.pop();
          offsets.pop();
        }
      }
    }
    const membership = new Int32Array(n).fill(-1),
      groups = [];
    for (let k = finish.length - 1; k >= 0; k--) {
      const start = finish[k];
      if (membership[start] !== -1) continue;
      const id = groups.length,
        members = [],
        stack = [start];
      membership[start] = id;
      while (stack.length) {
        const v = stack.pop();
        members.push(v);
        for (const w of incoming[v])
          if (membership[w] === -1) {
            membership[w] = id;
            stack.push(w);
          }
      }
      members.sort((a, b) => a - b);
      groups.push({ id, members, next: new Set(), prev: new Set(), rank: 0 });
    }
    return { ids, index, n, out, incoming, groups, membership };
  }
  function cycleGroups(input) {
    const { ids, out, groups } = stronglyConnected(input);
    return groups
      .filter(
        (g) => g.members.length > 1 || out[g.members[0]].includes(g.members[0]),
      )
      .map((g) => g.members.map((i) => ids[i]));
  }
  function sequential(input) {
    const { ids, n, out, incoming, groups, membership } =
      stronglyConnected(input);
    for (let a = 0; a < n; a++)
      for (const b of out[a])
        if (membership[a] !== membership[b]) {
          groups[membership[a]].next.add(membership[b]);
          groups[membership[b]].prev.add(membership[a]);
        }
    const indegree = groups.map((g) => g.prev.size),
      queue = groups.filter((g) => !g.prev.size).map((g) => g.id);
    for (let i = 0; i < queue.length; i++) {
      const g = groups[queue[i]];
      for (const id of g.next) {
        groups[id].rank = Math.max(groups[id].rank, g.rank + 1);
        if (--indegree[id] === 0) queue.push(id);
      }
    }
    // Weak components are packed separately; no dependency is invented between them.
    const assigned = new Uint8Array(groups.length),
      components = [];
    for (const start of groups) {
      if (assigned[start.id]) continue;
      const rows = [],
        stack = [start.id];
      assigned[start.id] = 1;
      while (stack.length) {
        const id = stack.pop(),
          g = groups[id];
        rows.push(g);
        for (const peer of [...g.next, ...g.prev])
          if (!assigned[peer]) {
            assigned[peer] = 1;
            stack.push(peer);
          }
      }
      components.push({ groups: rows });
    }
    const coords = new Array(n),
      order = new Map();
    for (const component of components) {
      const layers = new Map();
      for (const g of component.groups) {
        const count = g.members.length,
          cols = Math.ceil(Math.sqrt(count));
        g.cols = cols;
        g.width = Math.max(70, cols * 42 + 30);
        g.height = Math.max(54, Math.ceil(count / cols) * 42 + 24);
        if (!layers.has(g.rank)) layers.set(g.rank, []);
        layers.get(g.rank).push(g);
      }
      const ranks = [...layers.keys()].sort((a, b) => a - b);
      const positionRows = () => {
        for (const layer of layers.values()) {
          let y = 0;
          for (const g of layer) {
            order.set(g.id, y + g.height / 2);
            y += g.height + 24;
          }
        }
      };
      for (const layer of layers.values())
        layer.sort((a, b) => a.members[0] - b.members[0]);
      positionRows();
      // Barycenter sweeps reduce crossings without claiming a global optimum.
      for (let sweep = 0; sweep < 6; sweep++) {
        const forward = sweep % 2 === 0;
        for (const rank of forward ? ranks : [...ranks].reverse()) {
          const layer = layers.get(rank),
            bary = new Map();
          for (const g of layer) {
            const peers = [...(forward ? g.prev : g.next)];
            bary.set(
              g.id,
              peers.length
                ? peers.reduce((s, id) => s + order.get(id), 0) / peers.length
                : order.get(g.id),
            );
          }
          layer.sort(
            (a, b) =>
              bary.get(a.id) - bary.get(b.id) || a.members[0] - b.members[0],
          );
          let y = 0;
          for (const g of layer) {
            order.set(g.id, y + g.height / 2);
            y += g.height + 24;
          }
        }
      }
      let x = 0;
      const heights = new Map();
      for (const rank of ranks) {
        const layer = layers.get(rank);
        heights.set(rank, layer.reduce((s, g) => s + g.height + 24, 0) - 24);
      }
      component.height = Math.max(0, ...heights.values());
      for (const rank of ranks) {
        const layer = layers.get(rank),
          width = Math.max(...layer.map((g) => g.width));
        let y = (component.height - heights.get(rank)) / 2;
        for (const g of layer) {
          g.x = x + (width - g.width) / 2;
          g.y = y;
          const cyclic =
            g.members.length > 1 || out[g.members[0]].includes(g.members[0]);
          for (let i = 0; i < g.members.length; i++) {
            const v = g.members[i];
            coords[v] = {
              id: ids[v],
              x: g.x + g.width / 2 + ((i % g.cols) - (g.cols - 1) / 2) * 42,
              y: g.y + 27 + Math.floor(i / g.cols) * 42,
              cycle: cyclic,
              cycleGroup: g.id,
              degree: out[v].length + incoming[v].length,
            };
          }
          y += g.height + 24;
        }
        x += width + 90;
      }
      component.width = Math.max(0, x - 90);
      component.first = component.groups.reduce(
        (v, g) => Math.min(v, g.members[0]),
        Infinity,
      );
    }
    components.sort(
      (a, b) => b.width * b.height - a.width * a.height || a.first - b.first,
    );
    const area = components.reduce(
        (sum, c) => sum + (c.width + 60) * (c.height + 60),
        0,
      ),
      target = Math.max(800, Math.sqrt(area * 1.6));
    let shelfX = 0,
      shelfY = 0,
      rowHeight = 0,
      width = 0,
      height = 0;
    for (const [componentIndex, c] of components.entries()) {
      if (shelfX && shelfX + c.width > target) {
        shelfY += rowHeight + 60;
        shelfX = 0;
        rowHeight = 0;
      }
      for (const g of c.groups)
        for (const v of g.members) {
          coords[v].component = componentIndex;
          coords[v].x += shelfX + 30;
          coords[v].y += shelfY + 30;
        }
      width = Math.max(width, shelfX + c.width + 60);
      height = Math.max(height, shelfY + c.height + 60);
      shelfX += c.width + 60;
      rowHeight = Math.max(rowHeight, c.height);
    }
    return {
      nodes: coords,
      width: Math.max(1, width),
      height: Math.max(1, height),
      components: components.length,
      cycles: groups.filter(
        (g) => g.members.length > 1 || out[g.members[0]].includes(g.members[0]),
      ).length,
    };
  }

  function packAlternative(base, components) {
    for (const c of components) {
      const xs = c.nodes.map((n) => n.x),
        ys = c.nodes.map((n) => n.y);
      const minX = Math.min(...xs),
        minY = Math.min(...ys);
      c.width = Math.max(60, Math.max(...xs) - minX + 40);
      c.height = Math.max(50, Math.max(...ys) - minY + 40);
      for (const n of c.nodes) {
        n.x -= minX - 20;
        n.y -= minY - 20;
      }
    }
    components.sort(
      (a, b) =>
        b.width * b.height - a.width * a.height ||
        compare(a.nodes[0].id, b.nodes[0].id),
    );
    const target = Math.max(
      700,
      Math.sqrt(
        components.reduce((s, c) => s + (c.width + 50) * (c.height + 50), 0) *
          1.5,
      ),
    );
    let x = 0,
      y = 0,
      rowHeight = 0,
      width = 1,
      height = 1;
    for (const c of components) {
      if (x && x + c.width > target) {
        y += rowHeight + 50;
        x = 0;
        rowHeight = 0;
      }
      for (const n of c.nodes) {
        n.x += x + 20;
        n.y += y + 20;
      }
      width = Math.max(width, x + c.width + 40);
      height = Math.max(height, y + c.height + 40);
      x += c.width + 50;
      rowHeight = Math.max(rowHeight, c.height);
    }
    return { ...base, width, height };
  }
  function splitComponents(base, edges) {
    const parts = new Map(),
      byId = new Map();
    for (const n of base.nodes) {
      if (!parts.has(n.component))
        parts.set(n.component, { nodes: [], edges: [] });
      parts.get(n.component).nodes.push(n);
      byId.set(n.id, n);
    }
    for (const e of edges) {
      const a = byId.get(e.source),
        b = byId.get(e.target);
      if (a && b && a.id !== b.id) parts.get(a.component).edges.push(e);
    }
    return [...parts.values()];
  }
  function organic(input, base) {
    const force =
      typeof module !== "undefined"
        ? require("./vendor/d3.v7.min.js")
        : root.d3;
    const components = splitComponents(base, input.edges);
    for (const component of components) {
      const fine = component.nodes;
      if (fine.length <= 2) {
        fine.forEach((n, i) => {
          n.x = i * 50;
          n.y = 0;
        });
        continue;
      }
      const byId = new Map(fine.map((n, i) => [n.id, i])),
        unique = new Map();
      for (const e of component.edges) {
        let a = byId.get(e.source),
          b = byId.get(e.target);
        if (a > b) [a, b] = [b, a];
        unique.set(a + ":" + b, { source: a, target: b, weight: 1 });
      }
      const levels = [
        {
          nodes: fine.map((n) => ({ id: n.id, mass: 1 })),
          links: [...unique.values()].sort(
            (a, b) => a.source - b.source || a.target - b.target,
          ),
        },
      ];
      // Heavy-edge matching exposes a small graph first, then refines every original node.
      while (levels.at(-1).nodes.length > 240 && levels.length < 7) {
        const level = levels.at(-1),
          adj = Array.from({ length: level.nodes.length }, () => new Map());
        for (const e of level.links) {
          adj[e.source].set(e.target, e.weight);
          adj[e.target].set(e.source, e.weight);
        }
        const ranked = level.nodes
            .map((_, i) => i)
            .sort((a, b) => adj[b].size - adj[a].size || a - b),
          parent = new Int32Array(level.nodes.length).fill(-1),
          nodes = [];
        for (const a of ranked) {
          if (parent[a] >= 0) continue;
          let best = -1,
            bestWeight = -1;
          for (const [b, w] of adj[a])
            if (
              parent[b] < 0 &&
              (w > bestWeight || (w === bestWeight && b < best))
            ) {
              best = b;
              bestWeight = w;
            }
          const id = nodes.length;
          parent[a] = id;
          let mass = level.nodes[a].mass;
          if (best >= 0) {
            parent[best] = id;
            mass += level.nodes[best].mass;
          }
          nodes.push({ id: level.nodes[a].id, mass });
        }
        if (nodes.length === level.nodes.length) break;
        const pairs = new Map();
        for (const e of level.links) {
          let a = parent[e.source],
            b = parent[e.target];
          if (a === b) continue;
          if (a > b) [a, b] = [b, a];
          const key = a + ":" + b;
          const old = pairs.get(key);
          if (old) old.weight += e.weight;
          else pairs.set(key, { source: a, target: b, weight: e.weight });
        }
        level.parent = parent;
        levels.push({
          nodes,
          links: [...pairs.values()].sort(
            (a, b) => a.source - b.source || a.target - b.target,
          ),
        });
      }
      for (let l = levels.length - 1; l >= 0; l--) {
        const level = levels[l];
        if (l < levels.length - 1) {
          const coarse = levels[l + 1];
          level.nodes.forEach((n, i) => {
            const p = coarse.nodes[level.parent[i]],
              angle = i * 2.399963;
            n.x = p.x + Math.cos(angle) * 13;
            n.y = p.y + Math.sin(angle) * 13;
          });
        }
        const simulation = force
          .forceSimulation(level.nodes)
          .randomSource(force.randomLcg(0.42))
          .stop()
          .alpha(l === levels.length - 1 ? 1 : 0.65)
          .alphaDecay(0.045)
          .velocityDecay(0.4)
          .force(
            "link",
            force
              .forceLink(level.links.map((e) => ({ ...e })))
              .distance(
                (e) =>
                  36 + 6 * Math.sqrt(Math.max(e.source.mass, e.target.mass)),
              )
              .strength(0.22),
          )
          .force(
            "charge",
            force
              .forceManyBody()
              .strength((n) => -55 * Math.sqrt(n.mass))
              .theta(1.1)
              .distanceMin(5),
          )
          .force(
            "collide",
            force
              .forceCollide((n) => 5 + Math.min(15, Math.sqrt(n.mass)))
              .iterations(1),
          )
          .force("center", force.forceCenter(0, 0));
        simulation.tick(
          l === levels.length - 1 ? 120 : level.nodes.length > 3000 ? 38 : 65,
        );
        simulation.stop();
      }
      levels[0].nodes.forEach((n, i) => {
        fine[i].x = n.x;
        fine[i].y = n.y;
      });
    }
    return packAlternative(base, components);
  }
  function radial(input, base) {
    const components = splitComponents(base, input.edges);
    for (const component of components) {
      const adj = new Map(component.nodes.map((n) => [n.id, new Set()]));
      for (const e of component.edges) {
        adj.get(e.source).add(e.target);
        adj.get(e.target).add(e.source);
      }
      const rootId = adj.has(input.focus)
        ? input.focus
        : [...component.nodes].sort(
            (a, b) => b.degree - a.degree || compare(a.id, b.id),
          )[0].id;
      const depths = new Map([[rootId, 0]]),
        queue = [rootId],
        rings = new Map([[0, [rootId]]]);
      for (let i = 0; i < queue.length; i++)
        for (const peer of [...adj.get(queue[i])].sort(compare))
          if (!depths.has(peer)) {
            const depth = depths.get(queue[i]) + 1;
            depths.set(peer, depth);
            queue.push(peer);
            if (!rings.has(depth)) rings.set(depth, []);
            rings.get(depth).push(peer);
          }
      const byId = new Map(component.nodes.map((n) => [n.id, n]));
      let radius = 0;
      for (const [depth, ids] of rings) {
        if (depth)
          radius = Math.max(radius + 65, (ids.length * 18) / (Math.PI * 2));
        ids.forEach((id, i) => {
          const n = byId.get(id),
            angle = (i / ids.length) * Math.PI * 2 - Math.PI / 2;
          n.x = Math.cos(angle) * radius;
          n.y = Math.sin(angle) * radius;
          n.distance = depth;
        });
      }
    }
    return packAlternative(base, components);
  }
  function layout(input) {
    const algorithm = input.algorithm || "organic";
    if (!["organic", "sequential", "radial"].includes(algorithm))
      throw new TypeError("Unknown graph layout.");
    const base = sequential(input);
    return algorithm === "organic"
      ? organic(input, base)
      : algorithm === "radial"
        ? radial(input, base)
        : base;
  }
  root.ArchitectureGraphLayout = { select, layout, limits, cycleGroups };
  if (typeof module !== "undefined")
    module.exports = root.ArchitectureGraphLayout;
  else if (typeof document === "undefined")
    root.onmessage = ({ data }) => {
      try {
        root.postMessage({ id: data.id, result: layout(data.graph) });
      } catch (error) {
        root.postMessage({ id: data.id, error: error.message });
      }
    };
})(typeof self === "undefined" ? globalThis : self);
