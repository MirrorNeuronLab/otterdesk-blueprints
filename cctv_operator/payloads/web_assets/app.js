const byId = (id) => document.getElementById(id);
const labels = {starting: "Preparing", ready: "Ready", running: "Running", stopping: "Stopping", stopped: "Stopped", error: "Needs review"};
let rendered = "";
let stopped = false;

function render(data) {
  const session = data.session;
  byId("camera").textContent = data.camera;
  byId("goal").textContent = session.instruction || "Preparing video analysis…";
  byId("status").textContent = labels[session.status] || "Preparing";
  byId("preview-state").textContent = data.preview.connected ? "Live preview · separate from analyzed windows" : data.preview.error || "Connecting to live video…";
  byId("caption-count").textContent = String(session.total_captions || 0);
  byId("error").hidden = !(data.error || session.error);
  byId("error").textContent = data.error || session.error || "";
  const captions = data.captions || [];
  byId("empty").hidden = captions.length > 0;
  byId("analysis-state").textContent = session.last_caption_at
    ? `Last analysis received ${new Date(session.last_caption_at).toLocaleTimeString()}${session.inference_ms == null ? "" : ` · ${(session.inference_ms / 1000).toFixed(2)} s model inference`}`
    : "Waiting for the first completed video window.";
  byId("analysis-state").title = session.last_caption_at || "";
  const fingerprint = JSON.stringify(captions.map((caption) => [caption.id, caption.content]));
  if (fingerprint === rendered) return;
  rendered = fingerprint;
  const entries = captions.slice().reverse().map((caption) => {
    const item = document.createElement("li");
    item.className = "caption";
    const time = document.createElement("time");
    time.dateTime = caption.start_time;
    time.title = `${caption.start_time} – ${caption.end_time}; received ${caption.received_at}`;
    time.textContent = `${new Date(caption.start_time).toLocaleTimeString()} – ${new Date(caption.end_time).toLocaleTimeString()}`;
    const text = document.createElement("p");
    text.textContent = caption.content;
    item.append(time, text);
    return item;
  });
  byId("captions").replaceChildren(...entries);
}

async function refresh() {
  try {
    const response = await fetch("api/status", {cache: "no-store", signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error("Unavailable");
    render(await response.json());
  } catch {
    byId("error").hidden = false;
    byId("error").textContent = "Couldn't refresh camera status. Reconnecting…";
  } finally {
    if (!stopped) setTimeout(refresh, 2000);
  }
}
window.addEventListener("pagehide", () => {stopped = true;});
window.addEventListener("pageshow", (event) => {if (event.persisted) {stopped = false; refresh();}});
refresh();
