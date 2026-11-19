const labels = {
  "2d": "2D floor plan with colored movement trails for guests and AgiBot",
  "3d": "3D floor plan with numbered guest markers and time in the lobby",
};
const guestColors = ["#205ec7", "#a83e00", "#7040bd", "#008452", "#b33076", "#bb3045", "#006a94", "#826700"];
const robotColor = "#007977";
const trailDuration = 16_000;
const trailGap = 2_400;
const minimumMovement = .14;
const maximumTrailSpeed = 2.8; // Meters per second. Break the trail on abrupt tracker jumps.

export function createFloorPlan(canvas, buttons, countLabel, details) {
  const { width, height } = canvas;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  let view = canvas.dataset.view;
  let scene;
  const trails = new Map();

  function render() {
    if (!scene) return;
    const { layout, guests, robot, observedAt } = scene;
    details.textContent = view === "3d"
      ? guests.map(({ id, dwell }) => `Guest ${id}, ${formatDwell(dwell)} in the lobby.`)
          .concat(robot ? ["AgiBot G2 visible."] : []).join(" ")
      : robot ? "AgiBot G2 visible." : "";
    ctx.clearRect(0, 0, width, height);
    if (view === "3d") {
      draw3D(ctx, width, height, layout, guests, canvas.clientWidth || width, robot);
    } else {
      draw2D(ctx, width, layout, guests, robot, trails, observedAt);
    }
  }
  new ResizeObserver(render).observe(canvas);

  for (const button of buttons) {
    button.addEventListener("click", () => {
      const next = button.dataset.planView;
      if (next === view) return;
      view = next;
      canvas.dataset.view = view;
      canvas.setAttribute("aria-label", labels[view]);
      for (const option of buttons) {
        option.setAttribute("aria-pressed", String(option === button));
      }
      render();
    });
  }

  return {
    update(layout, observations, robot) {
      const guests = trackedGuests(layout, observations, robot);
      const observedAt = performance.now();
      recordTrails(trails, guests, robot, observedAt);
      scene = { layout, guests, robot, observedAt };
      const summary = guests.length === 1 ? "1 track in the lobby" : guests.length + " tracks in the lobby";
      if (summary !== countLabel.textContent) countLabel.textContent = summary;
      render();
    },
  };
}

function guestColor(id) {
  return guestColors[Number(id.slice(-4)) % guestColors.length];
}

function recordTrails(trails, guests, robot, at) {
  const points = guests.map(({ id, x, y }) => ({ id, x, y, color: guestColor(id) }));
  if (robot) {
    const [x, y] = robot.world_xy;
    points.push({ id: "robot", x, y, color: robotColor });
  }

  for (const { id, x, y, color } of points) {
    const trail = trails.get(id) ?? { color, points: [], lastSeen: -Infinity };
    const previous = trail.points.at(-1);
    const distance = previous ? Math.hypot(x - previous.x, y - previous.y) : Infinity;
    const join = previous && at - trail.lastSeen <= trailGap &&
      distance <= maximumTrailSpeed * (at - trail.lastSeen) / 1000;
    if (!join || distance >= minimumMovement) {
      trail.points.push({ x, y, at, join });
    }
    trail.lastSeen = at;
    trails.set(id, trail);
  }

  for (const [id, trail] of trails) {
    trail.points = trail.points.filter((point) => at - point.at < trailDuration);
    if (!trail.points.length) trails.delete(id);
  }
}

function trackedGuests(layout, observations, robot) {
  const [width, depth] = layout.size;
  const byId = new Map();
  for (const { id, world_xyz: [x, y], dwell_seconds: dwell } of observations) {
    if (dwell === null || Math.abs(x) > width / 2 || Math.abs(y) > depth / 2) continue;
    const point = byId.get(id) ?? { id, x: 0, y: 0, views: 0, dwell };
    point.x += x;
    point.y += y;
    point.views += 1;
    byId.set(id, point);
  }
  return [...byId.values()]
    .map(({ id, x, y, views, dwell }) => ({ id, x: x / views, y: y / views, dwell }))
    .filter(({ x, y }) => !robot || Math.hypot(x - robot.world_xy[0], y - robot.world_xy[1]) > .85);
}

function formatDwell(seconds) {
  if (!Number.isFinite(seconds)) return "—";
  return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
}

function draw2D(ctx, viewWidth, layout, guests, robot, trails, now) {
  const [width, depth] = layout.size;
  const scale = (viewWidth - 64) / width;
  const x = (value) => viewWidth / 2 + value * scale;
  const y = (value) => 28 + (depth / 2 - value) * scale;

  function box([left, bottom, right, top], color) {
    ctx.fillStyle = color;
    ctx.fillRect(x(left), y(top), (right - left) * scale, (top - bottom) * scale);
  }

  box([-width / 2, -depth / 2, width / 2, depth / 2], "#ded8ca");
  for (let line = -width / 2; line <= width / 2; line += 2) {
    box([line, -depth / 2, line + 0.025, depth / 2], "#c9c2b5");
  }
  for (let line = -depth / 2; line <= depth / 2; line += 2) {
    box([-width / 2, line, width / 2, line + 0.025], "#c9c2b5");
  }
  layout.rugs.forEach((rug) => box(rug, "#a4b5ac"));
  box(layout.desk, "#34584f");
  ctx.strokeStyle = "#6b5b49";
  ctx.lineWidth = 3;
  ctx.strokeRect(x(-width / 2), y(depth / 2), width * scale, depth * scale);
  ctx.font = "600 14px system-ui";
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  for (const door of layout.doors) {
    box([door.x - door.width / 2, door.y - .16, door.x + door.width / 2, door.y + .16], "#188269");
    ctx.fillStyle = "#254c45";
    ctx.fillText(door.label, x(door.x), y(door.y) + (door.y > 0 ? -11 : 29));
  }

  ctx.save();
  ctx.lineCap = "round";
  for (const { points, color } of trails.values()) {
    for (let index = 1; index < points.length; index += 1) {
      const start = points[index - 1];
      const end = points[index];
      if (!end.join) continue;
      ctx.globalAlpha = .9 * (1 - (now - start.at) / trailDuration);
      line(ctx, [[x(start.x), y(start.y)], [x(end.x), y(end.y)]], color, 3.25);
    }
  }
  ctx.restore();

  for (const { id, x: left, y: up } of guests) {
    circle(ctx, x(left), y(up), 5.5, guestColor(id), "#fff", 1.5);
  }
  if (robot) {
    const [left, up] = robot.world_xy;
    ctx.beginPath();
    ctx.roundRect(x(left) - 6, y(up) - 6, 12, 12, 2);
    ctx.fillStyle = robotColor;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = "#fff";
    ctx.stroke();
  }
}

function draw3D(ctx, viewWidth, viewHeight, layout, guests, displayWidth, robot) {
  const [width, depth] = layout.size;
  // An orthographic camera looking into the lobby from the southeast.
  const yaw = Math.PI / 6.4;
  const pitch = Math.PI / 4.4;
  const sinYaw = Math.sin(yaw);
  const cosYaw = Math.cos(yaw);
  const sinPitch = Math.sin(pitch);
  const cosPitch = Math.cos(pitch);
  const scale = (viewWidth - 64) / (width * cosYaw + depth * sinYaw);
  const toward = (x, y) => x * sinYaw - y * cosYaw;
  const project = (x, y, z = 0) => [
    viewWidth / 2 + scale * (x * cosYaw + y * sinYaw),
    viewHeight * .525 + scale * (toward(x, y) * sinPitch - z * cosPitch),
  ];
  const [left, front, right, back] = [-width / 2, -depth / 2, width / 2, depth / 2];
  const room = [left, front, right, back];
  ctx.save();
  ctx.shadowColor = "#0002";
  ctx.shadowBlur = 22;
  ctx.shadowOffsetY = 9;
  panel(ctx, corners(room).map(([x, y]) => project(x, y, -.36)), "#bbb");
  ctx.restore();
  prism(ctx, project, room, -.36, 0, ["#fafafa", "#d5d5d5", "#c5c5c5"]);
  for (const rug of layout.rugs) {
    panel(ctx, corners(rug).map(([x, y]) => project(x, y)), "#ededed", "#dfdfdf");
  }
  for (let x = left + 2; x < right; x += 2) {
    line(ctx, [project(x, front), project(x, back)], "#e4e4e4");
  }
  for (let y = front + 2; y < back; y += 2) {
    line(ctx, [project(left, y), project(right, y)], "#e4e4e4");
  }
  prism(ctx, project, layout.desk, 0, 1.10, ["#c7c7c7", "#989898", "#838383"]);
  prism(ctx, project, layout.desk, 1.10, 1.23, ["#fdfdfd", "#e1e1e1", "#cbcbcb"]);

  function wall(ax, ay, bx, by) {
    panel(ctx, [project(ax, ay), project(bx, by), project(bx, by, .35), project(ax, ay, .35)],
      "#d7d7d7", "#b8b8b8");
  }

  wall(left, front, left, back);
  wall(right, front, right, back);
  for (const y of [front, back]) {
    const openings = layout.doors.filter((door) => door.y === y).sort((a, b) => a.x - b.x);
    let start = left;
    for (const door of openings) {
      wall(start, y, door.x - door.width / 2, y);
      start = door.x + door.width / 2;
    }
    wall(start, y, right, y);
  }
  for (const door of layout.doors) {
    const a = door.x - door.width / 2;
    const b = door.x + door.width / 2;
    line(ctx, [project(a, door.y), project(b, door.y)], "#303030", 3);
    line(ctx, [project(a, door.y), project(a, door.y, 2.25), project(b, door.y, 2.25),
      project(b, door.y)], "#555", 1.7);
  }

  const tracked = guests.map((guest) => ({ ...guest, kind: "guest" }));
  if (robot) {
    const [x, y] = robot.world_xy;
    tracked.push({ kind: "robot", x, y });
  }
  tracked.sort((a, b) => toward(a.x, a.y) - toward(b.x, b.y));
  const tags = [];
  const placed = [];
  for (const object of tracked) {
    const { x, y } = object;
    const isRobot = object.kind === "robot";
    const anchor = project(x, y, isRobot ? .70 : 1.62);
    const foot = project(x, y);
    const halfWidth = scale * (isRobot ? .84 : .38);
    placed.push({
      left: anchor[0] - halfWidth, top: anchor[1] - 4,
      width: 2 * halfWidth, height: foot[1] - anchor[1] + 8,
    });
    if (isRobot) {
      drawRobot(ctx, project, x, y);
      tags.push({ anchor, text: "AgiBot", color: robotColor });
    } else {
      const color = guestColor(object.id);
      drawStick(ctx, project, scale, x, y, color);
      tags.push({ anchor, text: `#${object.id} · ${formatDwell(object.dwell)}`, color });
    }
  }

  const labelSize = Math.max(15, 11.5 * viewWidth / displayWidth);
  for (const door of layout.doors) {
    const isExit = door.y > 0;
    const [x, y] = project(door.x, door.y, isExit ? 2.25 : 0);
    const offset = labelSize / 2 + (isExit ? 13.5 : 16.5);
    const label = measureLabel(ctx, door.label, labelSize);
    const box = { ...label, left: x - label.width / 2, top: y + (isExit ? -offset : offset) - label.height / 2 };
    placed.push(box);
    drawLabel(ctx, box);
  }
  for (const { anchor, text, color } of tags) {
    const label = measureLabel(ctx, text, labelSize, color);
    const box = positionLabel(label, anchor, placed, viewWidth);
    const [anchorX, anchorY] = anchor;
    const labelX = Math.min(box.left + box.width - 8, Math.max(box.left + 8, anchorX));
    line(ctx, [[anchorX, anchorY - 2], [labelX, box.top + box.height]], color, 1);
    placed.push(box);
    drawLabel(ctx, box);
  }
}

function drawStick(ctx, project, scale, x, y, color) {
  const foot = project(x, y);
  ctx.save();
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.ellipse(...foot, scale * .38, scale * .22, 0, 0, Math.PI * 2);
  ctx.fillStyle = color + "22";
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  const upright = [project(x, y, .16), project(x, y, 1.62)];
  line(ctx, upright, "#fff", scale * .35 + 2);
  line(ctx, upright, color, scale * .35);
  ctx.restore();
}

function drawRobot(ctx, project, x, y) {
  prism(ctx, project, [x - .59, y - .47, x + .59, y + .47], .05, .38, ["#bceae6", "#057773", "#005451"]);
  prism(ctx, project, [x - .24, y - .20, x + .24, y + .20], .38, .70, ["#d7f4f1", "#23938b", "#00635f"]);
}

function measureLabel(ctx, text, fontSize, color) {
  ctx.font = `600 ${fontSize}px system-ui`;
  return { text, fontSize, color, width: ctx.measureText(text).width + (color ? 30 : 18), height: fontSize + 9 };
}

function positionLabel(label, [x, y], occupied, viewWidth) {
  const { width, height } = label;
  let candidate;
  for (let row = 0; row < 4; row += 1) {
    const top = Math.max(5, y - 10 - height - row * (height + 5));
    for (const shift of [0, -1, 1, -2, 2]) {
      const left = Math.min(viewWidth - width - 5, Math.max(5, x - width / 2 + shift * (width / 2 + 8)));
      candidate = { ...label, left, top };
      if (occupied.every((box) => left + width + 4 <= box.left || box.left + box.width + 4 <= left
          || top + height + 4 <= box.top || box.top + box.height + 4 <= top)) return candidate;
    }
  }
  return candidate;
}

function drawLabel(ctx, { text, fontSize, color, left, top, width, height }) {
  ctx.font = `600 ${fontSize}px system-ui`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const centerY = top + height / 2;
  ctx.beginPath();
  ctx.roundRect(left, top, width, height, 5);
  ctx.fillStyle = "#fff";
  ctx.fill();
  ctx.lineWidth = 1;
  ctx.strokeStyle = "#d3d3d3";
  ctx.stroke();
  if (color) circle(ctx, left + 10, centerY, 3.1, color, color, 1);
  ctx.fillStyle = "#242424";
  ctx.fillText(text, left + width / 2 + (color ? 6 : 0), centerY);
}

function corners([left, front, right, back]) {
  return [[left, front], [right, front], [right, back], [left, back]];
}

function prism(ctx, project, footprint, bottom, top, [topColor, frontColor, rightColor]) {
  const points = corners(footprint);
  const lower = points.map(([x, y]) => project(x, y, bottom));
  const upper = points.map(([x, y]) => project(x, y, top));
  panel(ctx, [lower[0], lower[1], upper[1], upper[0]], frontColor);
  panel(ctx, [lower[1], lower[2], upper[2], upper[1]], rightColor);
  panel(ctx, upper, topColor, "#c5c5c5");
}

function path(ctx, [start, ...rest]) {
  ctx.beginPath();
  ctx.moveTo(...start);
  for (const point of rest) ctx.lineTo(...point);
}

function panel(ctx, points, fill, border) {
  path(ctx, points);
  ctx.closePath();
  ctx.fillStyle = fill;
  ctx.fill();
  if (border) {
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    ctx.stroke();
  }
}

function line(ctx, points, color, width = 1) {
  path(ctx, points);
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
}

function circle(ctx, x, y, radius, fill, outline, lineWidth) {
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.strokeStyle = outline;
  ctx.lineWidth = lineWidth;
  ctx.stroke();
}
