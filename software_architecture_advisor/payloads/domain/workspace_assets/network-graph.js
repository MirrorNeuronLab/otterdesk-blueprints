"use strict";
// D3 owns zoom and spatial lookup; Canvas keeps large graphs out of the DOM.
(() => {
  const $ = (id) => document.getElementById(id);
  const cache = new Map();
  let active = null,
    pending = null,
    serial = 0;
  function cancel() {
    if (pending) {
      pending.worker?.terminate();
      clearTimeout(pending.timer);
      pending = null;
    }
  }
  function leave() {
    cancel();
    if (active) {
      active.canvas.parentElement.style.height = "";
      active.canvas.parentElement.classList.remove("network-host");
      active.observer.disconnect();
      window.removeEventListener("resize", active.onWindowResize);
      cancelAnimationFrame(active.frame);
      active = null;
    }
  }
  function resultFor(key, plan, onReady, onError) {
    if (cache.has(key)) {
      onReady(cache.get(key));
      return;
    }
    if (pending?.key === key) {
      pending.ready = onReady;
      pending.fail = onError;
      return;
    }
    cancel();
    const job = { key, id: ++serial, ready: onReady, fail: onError };
    pending = job;
    const finish = (result, error) => {
      if (pending !== job) return;
      clearTimeout(job.timer);
      job.worker?.terminate();
      pending = null;
      if (error) {
        job.fail(error);
        return;
      }
      cache.set(key, result);
      while (cache.size > 4) cache.delete(cache.keys().next().value);
      job.ready(result);
    };
    const input = {
      ids: plan.ids,
      algorithm: plan.algorithm,
      focus: plan.focus,
      edges: plan.edges.map((e) => ({ source: e.source, target: e.target })),
    };
    if (location.protocol === "file:") {
      // Browsers prohibit file-origin workers. Same bounded algorithm, explicit local mode.
      job.timer = setTimeout(() => {
        try {
          finish(ArchitectureGraphLayout.layout(input));
        } catch (e) {
          finish(null, e.message);
        }
      }, 0);
      return;
    }
    try {
      job.worker = new Worker($("layout-engine").src);
      job.worker.onmessage = ({ data }) => {
        if (data.id === job.id) finish(data.result, data.error);
      };
      job.worker.onerror = () =>
        finish(
          null,
          "Couldn’t arrange this graph. Reload the page to try again.",
        );
      job.timer = setTimeout(
        () =>
          finish(
            null,
            "Graph layout exceeded 20 seconds. Narrow the graph scope and try again.",
          ),
        20000,
      );
      job.worker.postMessage({ id: job.id, graph: input });
    } catch (e) {
      finish(
        null,
        "Couldn’t start graph layout. Serve this export from a local HTTP server or use offline file mode.",
      );
    }
  }
  function render(ctx) {
    const {
      graph,
      old,
      change,
      focus,
      level,
      edgeKey,
      onSelect,
      layoutGraph = graph,
      identity = "current",
    } = ctx;
    const host = $("graph"),
      scope = $("network-scope").value;
    const plan = ArchitectureGraphLayout.select({
      ids: [...layoutGraph.nodes.keys()],
      edges: layoutGraph.edges,
      focus,
      scope,
    });
    const algorithm = $("network-layout").value;
    plan.algorithm = algorithm;
    plan.focus = focus;
    const key = JSON.stringify([
      algorithm,
      algorithm === "radial" ? focus : null,
      plan.ids,
      plan.edges.map((e) => [e.source, e.target]),
    ]);
    const sceneKey =
      identity +
      "|" +
      level +
      "|" +
      scope +
      "|" +
      $("relation").value +
      "|" +
      algorithm;
    let scene = active;
    if (!scene || scene.key !== sceneKey || !host.contains(scene.canvas)) {
      if (scene) {
        scene.observer.disconnect();
        window.removeEventListener("resize", scene.onWindowResize);
        cancelAnimationFrame(scene.frame);
      }
      host.replaceChildren();
      const canvas = document.createElement("canvas"),
        tip = document.createElement("div");
      canvas.className = "network-canvas";
      canvas.tabIndex = 0;
      canvas.setAttribute("role", "img");
      canvas.setAttribute(
        "aria-label",
        "Interactive file or function dependency graph. Use the selection list and evidence tables for keyboard access. Arrow keys pan; plus and minus zoom; Home fits the graph; F focuses the selection.",
      );
      tip.className = "network-tooltip";
      tip.hidden = true;
      tip.setAttribute("role", "tooltip");
      host.append(canvas, tip);
      host.classList.add("network-host");
      scene = {
        key: sceneKey,
        canvas,
        tip,
        transform: d3.zoomIdentity,
        width: 1,
        height: 480,
        frame: 0,
        hover: null,
        ready: false,
        manual: false,
        planKey: null,
      };
      active = scene;
      scene.zoom = d3
        .zoom()
        .scaleExtent([0.000001, 12])
        .extent(() => [
          [0, 0],
          [scene.width, scene.height],
        ])
        .on("zoom", (event) => {
          scene.transform = event.transform;
          if (event.sourceEvent) scene.manual = true;
          requestPaint(scene);
        });
      d3.select(canvas).call(scene.zoom).on("dblclick.zoom", null);
      canvas.addEventListener("pointermove", (event) => {
        if (!scene.ready || !scene.tree) return;
        const point = scene.transform.invert(d3.pointer(event, canvas));
        const node = scene.tree.find(
          point[0],
          point[1],
          18 / scene.transform.k,
        );
        if (node?.id === scene.hover?.id) return;
        scene.hover = node || null;
        tip.hidden = !node;
        if (node) {
          tip.textContent = node.id;
          tip.style.left =
            Math.min(scene.width - 180, Math.max(8, event.offsetX + 12)) + "px";
          tip.style.top =
            Math.max(8, Math.min(scene.height - 50, event.offsetY + 12)) + "px";
        }
        canvas.style.cursor = node ? "pointer" : "grab";
        requestPaint(scene);
      });
      canvas.addEventListener("pointerleave", () => {
        scene.hover = null;
        tip.hidden = true;
        requestPaint(scene);
      });
      d3.select(canvas).on("click.select", (event) => {
        if (event.defaultPrevented || !scene.ready || !scene.tree) return;
        const point = scene.transform.invert(d3.pointer(event, canvas));
        const node = scene.tree.find(
          point[0],
          point[1],
          18 / scene.transform.k,
        );
        if (node) scene.ctx.onSelect(node.id);
      });
      canvas.addEventListener("keydown", (event) => {
        const pan = {
          ArrowLeft: [55, 0],
          ArrowRight: [-55, 0],
          ArrowUp: [0, 55],
          ArrowDown: [0, -55],
        }[event.key];
        if (pan) {
          event.preventDefault();
          scene.manual = true;
          d3.select(canvas).call(
            scene.zoom.translateBy,
            pan[0] / scene.transform.k,
            pan[1] / scene.transform.k,
          );
        } else if (["+", "=", "-", "Home", "f", "F"].includes(event.key)) {
          event.preventDefault();
          if (event.key === "Home") fit(scene);
          else if (event.key.toLowerCase() === "f") focusSelected(scene);
          else {
            scene.manual = true;
            d3.select(canvas).call(
              scene.zoom.scaleBy,
              event.key === "-" ? 0.8 : 1.25,
            );
          }
        }
      });
      scene.observer = new ResizeObserver(() => resize(scene));
      scene.observer.observe(host);
      scene.observer.observe(host.parentElement);
      scene.onWindowResize = () => resize(scene);
      window.addEventListener("resize", scene.onWindowResize);
      resize(scene);
    }
    scene.ctx = ctx;
    scene.plan = plan;
    const values = new Map([...(old?.nodes || []), ...graph.nodes]);
    const edges = new Map(
      [...(old?.edges || []), ...graph.edges].map((e) => [edgeKey(e), e]),
    );
    const nowKeys = new Set(graph.edges.map(edgeKey));
    scene.values = values;
    scene.edges = [...edges.values()].map((e) => ({
      ...e,
      status: change?.added.has(edgeKey(e))
        ? "added"
        : change?.removed.has(edgeKey(e))
          ? "removed"
          : old && !nowKeys.has(edgeKey(e))
            ? "unknown"
            : "",
    }));
    scene.selected = focus;
    scene.tip.hidden = true;
    scene.hover = null;
    window.ReportUI.bindGraphCommands({
      "zoom-in": () => {
        scene.manual = true;
        d3.select(scene.canvas).call(scene.zoom.scaleBy, 1.4);
      },
      "zoom-out": () => {
        scene.manual = true;
        d3.select(scene.canvas).call(scene.zoom.scaleBy, 1 / 1.4);
      },
      "zoom-reset": () => fit(scene),
      "zoom-focus": () => focusSelected(scene),
      "zoom-changes": () => fit(scene, true),
    });
    $("graph-title").textContent = old ? "Graph evolution" : "Dependency graph";
    document.querySelector(".legend").textContent = old
      ? "Green + added · Rust dashed − removed · Amber = changed definition · Arrows → dependencies"
      : `${algorithm === "sequential" ? "Left → right dependencies" : algorithm === "radial" ? "Radial overview · Rings = undirected hops from each root" : "Organic overview · Arrows → dependencies"} · Amber = candidate cycle`;
    const unit = level === "file" ? "files" : "functions";
    $("graph-note").textContent =
      `${algorithm === "organic" ? "Organic layout (recommended): seeded multilevel force refinement with Barnes–Hut repulsion." : algorithm === "radial" ? "Radial layout: concentric undirected-distance levels from the selected file or function; other disconnected graphs use their most connected node." : "Sequential layout: candidate strongly connected groups with six crossing-reduction sweeps."} Disconnected graphs are packed separately. ${old ? "Scope and layout use relationships across all captured history; displayed files or functions belong to the selected comparison. Positions remain fixed during playback. " : ""}Limits are 10,000 ${unit} and 50,000 relationships. Labels appear with zoom; full names and evidence remain in the selection list and tables. Spatial groups are visual hints, not inferred modules. Sequential ranks are dependency order, not approved architectural layers. Static candidates do not establish runtime behavior.`;
    const accept = (result) => {
      if (active !== scene || scene.planKey !== key) return;
      scene.result = result;
      scene.ready = true;
      scene.nodes = result.nodes.filter((n) => scene.values.has(n.id));
      scene.positions = new Map(scene.nodes.map((n) => [n.id, n]));
      const shownKeys = new Set(plan.edges.map(edgeKey));
      scene.drawEdges = scene.edges.filter(
        (e) =>
          shownKeys.has(edgeKey(e)) &&
          scene.positions.has(e.source) &&
          scene.positions.has(e.target),
      );
      scene.tree = d3.quadtree(
        scene.nodes,
        (n) => n.x,
        (n) => n.y,
      );
      scene.neighbors = new Set([scene.selected]);
      for (const e of scene.drawEdges)
        if (e.source === scene.selected || e.target === scene.selected) {
          scene.neighbors.add(e.source);
          scene.neighbors.add(e.target);
        }
      scene.canvas.setAttribute("aria-busy", "false");
      scene.canvas.dataset.layoutReady = "true";
      const accounting = ArchitectureComparison.coverage({
        graph,
        old,
        plan,
        change,
        capturedFiles: ctx.capturedFiles,
        comparisonFiles: ctx.comparisonFiles,
        level,
      });
      $("layout-status").textContent =
        `${scene.nodes.length.toLocaleString()} ${unit} · ${scene.drawEdges.length.toLocaleString()} relationships`;
      $("graph-coverage-line").textContent =
        `Scope and coverage${accounting.hiddenByScope ? ` · ${accounting.hiddenByScope} hidden by scope` : ""}${accounting.hiddenByLimit ? ` · ${accounting.hiddenByLimit} hidden by limit` : ""}${accounting.gapFiles ? ` · ${accounting.gapFiles} files with parser gaps` : ""}`;
      const row = (label, count) =>
        `<div><dt>${label}</dt><dd>${Number(count).toLocaleString()}</dd></div>`;
      $("graph-coverage-detail").innerHTML =
        "<dl>" +
        row(
          "Captured source files · latest snapshot",
          accounting.capturedFiles,
        ) +
        (old
          ? row(
              "Source file paths in this comparison",
              accounting.comparisonFiles,
            )
          : "") +
        row(
          `Extracted ${unit} in ${old ? "either comparison state" : "this capture"}`,
          accounting.inventory,
        ) +
        (old
          ? row(
              `${unit === "files" ? "Files" : "Functions"} eligible for definitive change comparisons`,
              accounting.comparable,
            )
          : "") +
        row(
          `${unit === "files" ? "Files" : "Functions"} eligible under selected scope`,
          accounting.scopeEligible,
        ) +
        row(`Displayed ${unit}`, accounting.displayed) +
        row(`Hidden ${unit} · scope`, accounting.hiddenByScope) +
        row(`Hidden ${unit} · display limit`, accounting.hiddenByLimit) +
        row(
          "Files with parser gaps · separate from filtering",
          accounting.gapFiles,
        ) +
        (old
          ? row(
              `${unit === "files" ? "Files" : "Functions"} across captured history · layout only`,
              accounting.historicalInventory,
            )
          : "") +
        '</dl><p class="qualification">' +
        (old
          ? "Connectivity and two-hop scope use the historical union. "
          : "Connectivity uses the captured graph. ") +
        `Parser gaps limit known definitions and relationships; they are not display filters. Relationship display limit omits ${accounting.relationshipLimit} scoped ${old ? "historical-union " : ""}relationships. Source exclusions and history bounds still apply.</p>`;
      $("graph-count").textContent = "";
      scene.changeIds = ArchitectureComparison.changeIds(
        change,
        scene.positions.keys(),
        scene.drawEdges,
      );
      window.ReportUI.setGraphChanges(
        Boolean(scene.changeIds.size),
        old && !scene.changeIds.size ? "No comparable changes displayed" : "",
      );
      if (!scene.framed && scene.nodes.length) fit(scene);
      else requestPaint(scene);
    };
    scene.planKey = key;
    if (cache.has(key)) {
      accept(cache.get(key));
      return;
    }
    scene.ready = false;
    scene.error = null;
    scene.canvas.dataset.layoutReady = "false";
    scene.canvas.setAttribute("aria-busy", "true");
    $("layout-status").textContent =
      `Arranging ${plan.ids.length.toLocaleString()} ${unit}…`;
    $("graph-count").textContent = "";
    requestPaint(scene);
    resultFor(key, plan, accept, (error) => {
      if (active !== scene || scene.planKey !== key) return;
      scene.canvas.setAttribute("aria-busy", "false");
      scene.ready = false;
      $("layout-status").textContent = error;
      scene.error = error;
      requestPaint(scene);
    });
  }
  function resize(scene) {
    if (active !== scene) return;
    const width = Math.max(1, scene.canvas.parentElement.clientWidth),
      height = Math.max(
        200,
        Math.min(
          680,
          window.innerHeight -
            (scene.canvas.parentElement.getBoundingClientRect().top +
              window.scrollY) -
            32,
        ),
      ),
      dpr = Math.min(devicePixelRatio || 1, 2);
    if (scene.width === width && scene.height === height && scene.dpr === dpr)
      return;
    const center = scene.transform.invert([scene.width / 2, scene.height / 2]);
    scene.width = width;
    scene.height = height;
    scene.dpr = dpr;
    scene.canvas.width = Math.round(width * dpr);
    scene.canvas.height = Math.round(height * dpr);
    scene.canvas.parentElement.style.height = height + "px";
    if (scene.ready && !scene.manual) fit(scene);
    else {
      scene.transform = d3.zoomIdentity
        .translate(
          width / 2 - center[0] * scene.transform.k,
          height / 2 - center[1] * scene.transform.k,
        )
        .scale(scene.transform.k);
      d3.select(scene.canvas).call(scene.zoom.transform, scene.transform);
    }
    requestPaint(scene);
  }
  function fit(scene, changesOnly = false) {
    if (!scene.result) return;
    const bounds = ArchitectureComparison.bounds(
      changesOnly
        ? scene.nodes.filter((n) => scene.changeIds?.has(n.id))
        : scene.nodes,
    );
    if (!bounds) return;
    scene.manual = true;
    scene.framed = true;
    const width = Math.max(100, bounds.x1 - bounds.x0),
      height = Math.max(100, bounds.y1 - bounds.y0),
      k = Math.max(
        0.000001,
        Math.min(1.6, (scene.width - 70) / width, (scene.height - 60) / height),
      );
    d3.select(scene.canvas).call(
      scene.zoom.transform,
      d3.zoomIdentity
        .translate(
          scene.width / 2 - ((bounds.x0 + bounds.x1) * k) / 2,
          scene.height / 2 - ((bounds.y0 + bounds.y1) * k) / 2,
        )
        .scale(k),
    );
  }
  function focusSelected(scene) {
    const n = scene.positions?.get(scene.selected);
    if (!n) return;
    scene.manual = true;
    const peers = scene.nodes.filter((n) => scene.neighbors.has(n.id));
    const dx = d3.extent(peers, (n) => n.x),
      dy = d3.extent(peers, (n) => n.y);
    const k = Math.max(
      0.05,
      Math.min(
        2.2,
        (scene.width - 110) / Math.max(150, dx[1] - dx[0]),
        (scene.height - 100) / Math.max(100, dy[1] - dy[0]),
      ),
    );
    d3.select(scene.canvas).call(
      scene.zoom.transform,
      d3.zoomIdentity
        .translate(
          scene.width / 2 - ((dx[0] + dx[1]) / 2) * k,
          scene.height / 2 - ((dy[0] + dy[1]) / 2) * k,
        )
        .scale(k),
    );
  }
  function requestPaint(scene) {
    if (active !== scene || scene.frame) return;
    scene.frame = requestAnimationFrame(() => {
      scene.frame = 0;
      paint(scene);
    });
  }
  function paint(scene) {
    if (active !== scene) return;
    const g = scene.canvas.getContext("2d"),
      { width, height, dpr = 1 } = scene;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, width, height);
    if (!scene.ready) {
      g.fillStyle = "#666666";
      g.font = "12px Geist, sans-serif";
      g.fillText(scene.error || "Arranging the dependency graph…", 20, 40);
      return;
    }
    if (!scene.nodes.length) {
      g.fillStyle = "#666666";
      g.font = "12px Geist, sans-serif";
      g.fillText("No files or functions are displayed in this scope.", 20, 40);
      return;
    }
    const t = scene.transform,
      k = t.k,
      positions = scene.positions,
      hover = scene.hover?.id;
    const primary = hover || scene.selected;
    const visible = (n) => {
      const x = n.x * k + t.x,
        y = n.y * k + t.y;
      return x >= -15 && x <= width + 15 && y >= -15 && y <= height + 15;
    };
    const screen = (n) => [n.x * k + t.x, n.y * k + t.y];
    const radii = (n) =>
      Math.min(9, Math.max(2, 2.3 + Math.sqrt(n.degree) * 0.55)) *
      Math.max(0.7, Math.min(1.5, k));
    function drawEdge(e, highlight) {
      const a = positions.get(e.source),
        b = positions.get(e.target),
        [ax, ay] = screen(a),
        [bx, by] = screen(b);
      if (
        Math.max(ax, bx) < -20 ||
        Math.min(ax, bx) > width + 20 ||
        Math.max(ay, by) < -20 ||
        Math.min(ay, by) > height + 20
      )
        return;
      g.strokeStyle =
        e.status === "added"
          ? "#39836b"
          : e.status === "removed"
            ? "#b47558"
            : highlight
              ? "#171717"
              : "#a3a3a3";
      g.globalAlpha = e.status ? 0.85 : highlight ? 0.8 : 0.22;
      g.lineWidth = highlight || e.status ? 1.3 : 0.65;
      g.setLineDash(
        e.status === "removed" ? [5, 3] : e.status === "unknown" ? [2, 4] : [],
      );
      g.beginPath();
      if (e.source === e.target) {
        g.arc(ax + 7, ay - 5, 10, 0, Math.PI * 1.7);
        g.stroke();
        return;
      }
      const angle = Math.atan2(by - ay, bx - ax),
        endX = bx - Math.cos(angle) * (radii(b) + 2),
        endY = by - Math.sin(angle) * (radii(b) + 2);
      g.moveTo(ax, ay);
      g.lineTo(endX, endY);
      g.stroke();
      if (
        (highlight || k > 0.7 || e.status) &&
        Math.hypot(bx - ax, by - ay) > 18
      ) {
        g.setLineDash([]);
        g.fillStyle = g.strokeStyle;
        g.beginPath();
        g.moveTo(endX, endY);
        g.lineTo(
          endX - 5 * Math.cos(angle - 0.4),
          endY - 5 * Math.sin(angle - 0.4),
        );
        g.lineTo(
          endX - 5 * Math.cos(angle + 0.4),
          endY - 5 * Math.sin(angle + 0.4),
        );
        g.closePath();
        g.fill();
      }
    }
    for (const e of scene.drawEdges)
      if (e.source !== primary && e.target !== primary) drawEdge(e, false);
    for (const e of scene.drawEdges)
      if (e.source === primary || e.target === primary) drawEdge(e, true);
    g.setLineDash([]);
    g.globalAlpha = 1;
    for (const n of scene.nodes) {
      if (!visible(n)) continue;
      const [x, y] = screen(n),
        status = scene.ctx.change?.statuses.get(n.id) || "";
      g.fillStyle =
        n.id === primary
          ? "#171717"
          : status === "added"
            ? "#91c7aa"
            : status === "removed"
              ? "#e1ac93"
              : status === "modified" || (!scene.ctx.old && n.cycle)
                ? "#d5b873"
                : "#d4d4d4";
      g.strokeStyle =
        status === "removed"
          ? "#b47558"
          : n.id === primary
            ? "#171717"
            : "#737373";
      g.lineWidth = n.id === primary ? 2 : 0.7;
      g.setLineDash(status === "removed" ? [3, 2] : []);
      g.beginPath();
      g.arc(x, y, radii(n) + (n.id === primary ? 2 : 0), 0, Math.PI * 2);
      g.fill();
      g.stroke();
    }
    g.setLineDash([]);
    const occupied = new Set(),
      candidates = scene.nodes
        .filter(visible)
        .sort(
          (a, b) =>
            Number(b.id === primary) - Number(a.id === primary) ||
            Number(scene.neighbors.has(b.id)) -
              Number(scene.neighbors.has(a.id)) ||
            b.degree - a.degree,
        );
    g.font = '10px "Geist Mono", ui-monospace, monospace';
    let labels = 0;
    const salient = new Set(candidates.slice(0, 8).map((n) => n.id));
    for (const n of candidates) {
      if (labels >= 160) break;
      if (n.id !== primary && k < 0.42 && !salient.has(n.id)) continue;
      if (
        n.id !== primary &&
        !scene.neighbors.has(n.id) &&
        !salient.has(n.id) &&
        k < 1
      )
        continue;
      const [x, y] = screen(n),
        name = n.id.split("::").at(-1).split("/").at(-1),
        label = name.length > 35 ? name.slice(0, 34) + "…" : name;
      const w = g.measureText(label).width + 8,
        l = Math.max(2, Math.min(width - w, x + radii(n) + 5)),
        top = Math.max(2, Math.min(height - 15, y - 8));
      const cells = [];
      for (let cx = Math.floor(l / 45); cx <= Math.floor((l + w) / 45); cx++)
        for (
          let cy = Math.floor(top / 16);
          cy <= Math.floor((top + 14) / 16);
          cy++
        )
          cells.push(cx + ":" + cy);
      if (n.id !== primary && cells.some((c) => occupied.has(c))) continue;
      cells.forEach((c) => occupied.add(c));
      g.fillStyle = "rgba(255,255,255,.92)";
      g.fillRect(l, top, w, 14);
      g.fillStyle = "#171717";
      g.fillText(label, l + 4, top + 10);
      labels++;
    }
  }
  window.ArchitectureNetwork = { render, leave };
})();
