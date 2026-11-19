import { createFloorPlan } from "./floor-plan.js";

const status = document.querySelector("#status");
const counters = { entered: document.querySelector("#entered"), left: document.querySelector("#left") };
const cameras = [...document.querySelectorAll(".cameras canvas")];
const floorPlan = createFloorPlan(
  document.querySelector("#map"),
  document.querySelectorAll("[data-plan-view]"),
  document.querySelector("#tracks"),
  document.querySelector("#track-details"),
);
const doors = document.querySelector("#doors");
const crossings = document.querySelector("#crossings");
const emptyCrossings = document.querySelector("#empty-crossings");
const clock = new Intl.DateTimeFormat(undefined, { timeStyle: "medium" });
let connected = false;
let previewReady = false;
let phase = "starting";
let lastDetails = "";

function showStatus() {
  const live = connected && previewReady && phase === "running";
  status.dataset.live = String(live);
  const messages = {
    running: "Connecting to live cameras…",
    starting: "Starting live tracking…",
    stopped: "Tracking stopped",
    failed: "Tracking stopped unexpectedly",
  };
  const value = !connected ? "Reconnecting to the lobby…" : live ? "Live simulation" : messages[phase];
  if (value !== status.textContent) status.textContent = value;
}

function cell(tag, value) {
  const node = document.createElement(tag);
  node.textContent = value;
  return node;
}

function showCounts(data) {
  const { layout, recent_crossings: recent } = data;
  for (const [direction, display] of Object.entries(counters)) {
    display.textContent = data[direction].toLocaleString();
  }
  const details = JSON.stringify([data.doors, recent]);
  if (details === lastDetails) return;
  lastDetails = details;
  doors.replaceChildren(...layout.doors.map((door) => {
    const row = document.createElement("tr");
    const label = cell("th", door.label);
    label.scope = "row";
    const counts = data.doors[door.id];
    row.append(label, cell("td", counts.entered.toLocaleString()), cell("td", counts.left.toLocaleString()));
    return row;
  }));
  emptyCrossings.hidden = recent.length > 0;
  crossings.replaceChildren(...recent.map((crossing) => {
    const label = layout.doors.find((door) => door.id === crossing.door).label;
    const verb = crossing.direction === "entered" ? "Entered" : "Left";
    const row = document.createElement("li");
    const time = cell("time", clock.format(new Date(crossing.observed_at)));
    time.dateTime = crossing.observed_at;
    row.append(cell("span", verb + " through " + label.toLowerCase()), time);
    return row;
  }));
}

async function request(path) {
  const response = await fetch(path, { cache: "no-store", signal: AbortSignal.timeout(4500) });
  if (!response.ok) throw new Error("Live workspace response unavailable");
  return response;
}

async function refreshCounts() {
  if (document.hidden) return;
  try {
    const data = await (await request("status.json")).json();
    showCounts(data);
    floorPlan.update(data.layout, data.tracks, data.robot);
    phase = data.status;
    connected = true;
  } catch {
    connected = false;
  }
  showStatus();
}

async function refreshCameras() {
  if (document.hidden) return;
  try {
    const image = await createImageBitmap(await (await request("cameras.jpg")).blob());
    cameras.forEach((canvas, index) => {
      const { width, height } = canvas;
      const x = index % 2 * width;
      const y = Math.floor(index / 2) * height;
      canvas.getContext("2d").drawImage(image, x, y, width, height, 0, 0, width, height);
    });
    image.close();
    previewReady = true;
  } catch {
    previewReady = false;
  }
  showStatus();
}

async function repeat(refresh, delay) {
  await refresh();
  setTimeout(() => void repeat(refresh, delay), delay);
}

void repeat(refreshCounts, 800);
void repeat(refreshCameras, 200);
