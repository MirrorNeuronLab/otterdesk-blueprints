"use strict";
// Lay out the complete bounded union once. Playback changes topology, not positions.
(() => {
  const unions = new Map();
  window.renderGraphEvolution = (ctx) => {
    const key = ctx.level + "|" + document.getElementById("relation").value;
    if (!unions.has(key)) {
      const nodes = new Map(),
        edges = new Map();
      for (let i = 0; i < ctx.frames.length; i++) {
        const graph = ctx.entityGraph(ctx.state(i));
        for (const [id, node] of graph.nodes) nodes.set(id, node);
        for (const edge of graph.edges) edges.set(ctx.edgeKey(edge), edge);
      }
      unions.set(key, { nodes, edges: [...edges.values()] });
    }
    window.ArchitectureNetwork.render({
      ...ctx,
      layoutGraph: unions.get(key),
      identity: "timeline",
    });
  };
})();
