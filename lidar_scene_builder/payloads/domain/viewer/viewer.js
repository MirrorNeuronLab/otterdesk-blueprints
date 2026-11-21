(() => {
  const canvas = document.querySelector("canvas");
  const status = document.querySelector("#status");
  try {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas unavailable");
    const { count, positions, colors } = JSON.parse(document.querySelector("#scene").textContent);
    const coords = new Float32Array(Uint8Array.from(atob(positions), char => char.charCodeAt(0)).buffer);
    const rgb = Uint8Array.from(atob(colors), char => char.charCodeAt(0));
    if (count < 1 || coords.length !== count * 3 || rgb.length !== coords.length) {
      throw new Error("Incomplete preview data");
    }
    const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
    let radius = 0.01;
    const points = Array.from({ length: count }, (_, index) => {
      const offset = index * 3;
      const [x, y, z] = coords.subarray(offset, offset + 3);
      radius = Math.max(radius, Math.hypot(x, y, z));
      return { x, y, z, color: `rgb(${rgb[offset]} ${rgb[offset + 1]} ${rgb[offset + 2]})` };
    });
    const initial = { yaw: 0.72, pitch: 0.55, zoom: 1 };
    const view = { ...initial };
    let frame = 0;
    let pointer = null;

    function draw() {
      frame = 0;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      if (width < 1 || height < 1) return;
      const density = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * density);
      canvas.height = Math.round(height * density);
      ctx.setTransform(density, 0, 0, density, 0, 0);
      const sinYaw = Math.sin(view.yaw);
      const cosYaw = Math.cos(view.yaw);
      const sinPitch = Math.sin(view.pitch);
      const cosPitch = Math.cos(view.pitch);
      const scale = Math.min(width, height) * 0.43 * view.zoom;
      const dot = clamp(Math.min(width, height) / 230, 1.35, 3.2);
      for (const point of points) {
        const horizontal = (cosYaw * point.x - sinYaw * point.y) / radius;
        const forward = (sinYaw * point.x + cosYaw * point.y) / radius;
        const vertical = point.z / radius;
        point.depth = cosPitch * forward + sinPitch * vertical;
        const magnification = 3.5 / (3.5 - point.depth);
        point.u = width / 2 + horizontal * scale * magnification;
        point.v = height / 2 - (cosPitch * vertical - sinPitch * forward) * scale * magnification;
      }
      points.sort((a, b) => a.depth - b.depth);
      for (const point of points) {
        ctx.fillStyle = point.color;
        ctx.fillRect(point.u - dot / 2, point.v - dot / 2, dot, dot);
      }
    }

    function scheduleDraw() {
      if (!frame) frame = requestAnimationFrame(draw);
    }

    function rotate(yaw, pitch) {
      view.yaw += yaw;
      view.pitch = clamp(view.pitch + pitch, -Math.PI / 2, Math.PI / 2);
      scheduleDraw();
    }

    function zoom(factor) {
      view.zoom = clamp(view.zoom * factor, 0.5, 8);
      scheduleDraw();
    }

    canvas.addEventListener("pointerdown", event => {
      if (event.button !== 0 || pointer) return;
      pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", event => {
      if (pointer?.id !== event.pointerId) return;
      rotate((event.clientX - pointer.x) * 0.009, (event.clientY - pointer.y) * 0.009);
      pointer.x = event.clientX;
      pointer.y = event.clientY;
    });
    canvas.addEventListener("lostpointercapture", () => { pointer = null; });
    canvas.addEventListener("wheel", event => {
      event.preventDefault();
      zoom(Math.exp(clamp(-event.deltaY * 0.0015, -0.25, 0.25)));
    }, { passive: false });
    const keyboard = {
      ArrowLeft: () => rotate(-0.15, 0),
      ArrowRight: () => rotate(0.15, 0),
      ArrowUp: () => rotate(0, 0.15),
      ArrowDown: () => rotate(0, -0.15),
      "+": () => zoom(1.2),
      "-": () => zoom(1 / 1.2),
    };
    canvas.addEventListener("keydown", event => {
      if (!Object.hasOwn(keyboard, event.key)) return;
      event.preventDefault();
      keyboard[event.key]();
    });
    document.querySelector("#reset").addEventListener("click", () => {
      Object.assign(view, initial);
      scheduleDraw();
    });
    document.querySelector("#top").addEventListener("click", () => {
      Object.assign(view, { yaw: 0, pitch: Math.PI / 2, zoom: 1 });
      scheduleDraw();
    });
    document.querySelector("#zoom-in").addEventListener("click", () => zoom(1.2));
    document.querySelector("#zoom-out").addEventListener("click", () => zoom(1 / 1.2));
    new ResizeObserver(scheduleDraw).observe(canvas);
    draw();
    status.hidden = true;
  } catch {
    status.textContent = "Couldn't display the point cloud. Open scene.usdc in an OpenUSD viewer.";
    document.querySelectorAll("button").forEach(button => { button.disabled = true; });
  }
})();
