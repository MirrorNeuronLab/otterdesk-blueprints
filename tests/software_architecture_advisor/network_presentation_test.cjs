// Exercise the real renderer's frame and camera lifecycle without a GUI or timers.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const assets = process.argv[2];
const model = require(path.join(assets, "comparison-presentation.js"));
const layout = require(path.join(assets, "graph-layout.js"));
const transforms = [];
const elements = new Map();
function element(tag = "div") {
  return {
    tag,
    value: "",
    style: {},
    dataset: {},
    children: [],
    clientWidth: 900,
    classList: { add() {}, remove() {} },
    setAttribute() {},
    addEventListener() {},
    replaceChildren() {
      this.children = [];
    },
    append(...nodes) {
      this.children.push(...nodes);
      for (const n of nodes) n.parentElement = this;
    },
    contains(node) {
      return this.children.includes(node);
    },
    getBoundingClientRect() {
      return { top: 400 };
    },
  };
}
const get = (id) => {
  if (!elements.has(id)) elements.set(id, element());
  return elements.get(id);
};
get("network-layout").value = "organic";
get("network-scope").value = "all";
get("relation").value = "call";
function transform(x = 0, y = 0, k = 1) {
  return {
    x,
    y,
    k,
    translate(a, b) {
      return transform(x + a * k, y + b * k, k);
    },
    scale(factor) {
      return transform(x, y, k * factor);
    },
    invert(p) {
      return [(p[0] - x) / k, (p[1] - y) / k];
    },
  };
}
function zoom() {
  const z = () => {};
  z.scaleExtent = z.extent = () => z;
  z.on = (_, listener) => {
    z.listener = listener;
    return z;
  };
  z.transform = (canvas, t) => {
    transforms.push(t);
    z.listener({ transform: t });
  };
  return z;
}
const d3 = {
  zoomIdentity: transform(),
  zoom,
  select: (canvas) => ({
    call(fn, ...args) {
      fn(canvas, ...args);
      return this;
    },
    on() {
      return this;
    },
  }),
  quadtree: () => ({ find: () => null }),
};
class Worker {
  terminate() {}
  postMessage({ id, graph }) {
    const points = { a: [100, 100], b: [200, 200], past: [10000, 10000] };
    this.onmessage({
      data: {
        id,
        result: {
          nodes: graph.ids.map((id) => ({
            id,
            x: points[id][0],
            y: points[id][1],
            degree: 1,
          })),
          width: 11000,
          height: 11000,
        },
      },
    });
  }
}
const sandbox = {
  window: {
    ReportUI: {
      bindGraphCommands(commands) {for (const [id,fn] of Object.entries(commands)) get(id).onclick=fn;},
      setGraphChanges(enabled,note) {get("zoom-changes").disabled=!enabled;get("change-zoom-note").textContent=note;get("change-zoom-note").hidden=!note;},
    },
    innerHeight: 864,
    scrollY: 0,
    addEventListener() {},
    removeEventListener() {},
  },
  document: {
    getElementById: get,
    querySelector: () => get("legend"),
    createElement: element,
  },
  ArchitectureComparison: model,
  ArchitectureGraphLayout: layout,
  d3,
  Worker,
  ResizeObserver: class {
    observe() {}
    disconnect() {}
  },
  location: { protocol: "http:" },
  devicePixelRatio: 1,
  requestAnimationFrame: () => 1,
  cancelAnimationFrame() {},
  setTimeout: () => 1,
  clearTimeout() {},
};
vm.runInNewContext(
  fs.readFileSync(path.join(assets, "network-graph.js"), "utf8"),
  sandbox,
);
const nodes = new Map(["a", "b"].map((id) => [id, { id, functions: [] }]));
const graph = { nodes, edges: [{ source: "a", target: "b", kind: "call" }] };
const layoutGraph = {
  nodes: new Map([...nodes, ["past", { id: "past" }]]),
  edges: graph.edges,
};
const ctx = {
  graph,
  old: graph,
  layoutGraph,
  identity: "timeline",
  level: "function",
  focus: "a",
  edgeKey: model.edgeKey,
  capturedFiles: 2,
  comparisonFiles: 2,
  onSelect() {},
  change: model.present({ graph, old: graph }),
};
sandbox.window.ArchitectureNetwork.render(ctx);
assert.equal(
  transforms.at(-1).k,
  1.6,
  "initial fit uses visible a/b, not the far historical union",
);
const count = transforms.length;
sandbox.window.ArchitectureNetwork.render({
  ...ctx,
  graph: { nodes: new Map([["a", nodes.get("a")]]), edges: [] },
});
assert.equal(
  transforms.length,
  count,
  "replay preserves the camera even when the displayed comparison shrinks",
);
get("zoom-reset").onclick();
assert.equal(
  transforms.length,
  count + 1,
  "explicit fit reframes the displayed comparison",
);
assert.equal(get("zoom-changes").disabled, true);
assert.equal(get("change-zoom-note").hidden, false);
sandbox.window.ArchitectureNetwork.leave();
