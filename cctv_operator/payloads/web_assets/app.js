const byId = (id) => document.getElementById(id);
const labels = {starting: "Preparing", ready: "Ready", running: "Running", stopping: "Stopping", stopped: "Stopped", error: "Needs review"};
let current;
let view = "all";
let stopped = false;
let olderPage = null;
let scope = "";

function entry(caption) {
  const item = document.createElement("li");
  item.className = "caption";
  item.dataset.id = caption.id;
  const time = document.createElement("time");
  time.dateTime = caption.start_time;
  time.title = `${caption.start_time} – ${caption.end_time}; received ${caption.received_at}`;
  const start = new Date(caption.start_time);
  const end = new Date(caption.end_time);
  const date = start.toDateString() === new Date().toDateString() ? "" : start.toLocaleDateString() + " · ";
  time.textContent = `${date}${start.toLocaleTimeString()} – ${end.toLocaleTimeString()}`;
  item.dataset.match = caption.goal_match || "uncertain";
  const header = document.createElement("div");
  header.className = "caption-header";
  header.append(time);
  if (caption.goal_match === "matched") {
    const label = document.createElement("span");
    label.className = "finding-label";
    label.textContent = "Possible match";
    header.append(label);
  }
  const body = document.createElement("div");
  body.className = "caption-body";
  const copy = document.createElement("div");
  copy.className = "caption-copy";
  const content = caption.goal_match ? caption.content : caption.content.split("```", 1)[0].trim() || "No readable window description.";
  const text = document.createElement("p");
  text.className = "caption-excerpt";
  text.textContent = content;
  const details = document.createElement("details");
  details.className = "caption-analysis";
  const summary = document.createElement("summary");
  summary.textContent = "Analysis details";
  const full = document.createElement("p");
  full.textContent = content;
  details.append(summary, full);
  copy.append(text, details);
  body.append(copy);
  if (caption.snapshot) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "snapshot";
    button.setAttribute("aria-label", `View saved frame at ${start.toLocaleTimeString()}`);
    const image = document.createElement("img");
    image.loading = "lazy";
    image.src = `api/windows/${encodeURIComponent(caption.id)}/snapshot.jpg`;
    image.alt = "Saved camera preview from this observation window";
    const label = document.createElement("span");
    label.textContent = caption.snapshot.bbox_2d ? "View highlighted frame" : "View frame";
    button.append(image, label);
    button.addEventListener("click", () => {
      byId("evidence-image").src = image.src;
      byId("evidence-image").alt = image.alt;
      byId("evidence-caption").textContent = `Preview received ${new Date(caption.snapshot.received_at).toLocaleString()} during this window.${caption.snapshot.bbox_2d ? " Box estimated on this image." : ""}`;
      byId("evidence-description").textContent = content;
      byId("evidence-dialog").showModal();
    });
    body.append(button);
  } else {
    const label = document.createElement("small");
    label.textContent = "No preview frame saved for this window.";
    copy.append(label);
  }
  item.append(header, body);
  return item;
}

function transcript(data) {
  const goal = view === "goal";
  const nextScope = JSON.stringify([data.run_id, view, goal && data.session.instruction_revision]);
  if (nextScope !== scope) {
    scope = nextScope;
    olderPage = null;
    byId("transcript").scrollTop = 0;
  }
  const rows = olderPage?.observations || (goal ? data.goal_matches : data.captions) || [];
  const list = byId("captions");
  const scroll = byId("transcript");
  const following = scroll.scrollTop < 4;
  const anchor = following ? null : [...list.children].find(el => el.getBoundingClientRect().bottom > scroll.getBoundingClientRect().top);
  const top = anchor?.getBoundingClientRect().top;
  const previous = new Map([...list.children].map(el => [el.dataset.id, el]));
  let cursor = list.firstElementChild;
  for (const caption of rows.slice().reverse()) {
    const element = previous.get(caption.id) || entry(caption);
    previous.delete(caption.id);
    if (element !== cursor) list.insertBefore(element, cursor);
    cursor = element.nextElementSibling;
  }
  for (const obsolete of previous.values()) obsolete.remove();
  if (following) scroll.scrollTop = 0;
  else if (anchor?.isConnected) scroll.scrollTop += anchor.getBoundingClientRect().top - top;
  byId("latest").hidden = !olderPage && scroll.scrollTop < 4;
  byId("earlier").hidden = !(olderPage ? olderPage.omitted_count : (goal ? data.match_count - rows.length : data.omitted_count));
  byId("caption-count").textContent = String(goal ? data.match_count || 0 : data.session.total_captions || 0);
  byId("empty").hidden = rows.length > 0;
  byId("empty").textContent = !goal ? "No completed video observations yet." : data.has_target
    ? "No matches reported for this goal yet." : "Set a monitoring goal in Chat to see matches here.";
  scroll.hidden = !rows.length;
}

function render(data) {
  current = data;
  const session = data.session;
  byId("camera").setAttribute("aria-label", `Live video · ${data.camera}`);
  byId("camera").title = data.camera;
  byId("camera-image").alt = `Current camera preview · ${data.camera}`;
  byId("status").textContent = labels[session.status] || "Preparing";
  byId("status").dataset.state = session.status;
  byId("preview-state").hidden = data.preview.connected;
  byId("preview-state").textContent = data.preview.error || "Connecting to live video…";
  byId("error").hidden = !(data.error || session.error);
  byId("error").textContent = data.error || session.error || "";
  transcript(data);
}

byId("close-evidence").addEventListener("click", () => byId("evidence-dialog").close());
byId("evidence-dialog").addEventListener("close", () => byId("evidence-image").removeAttribute("src"));

byId("filters").addEventListener("change", (event) => {
  view = event.target.value;
  byId("captions").replaceChildren();
  byId("transcript").scrollTop = 0;
  if (current) transcript(current);
});
byId("earlier").addEventListener("click", async () => {
  const key = scope;
  const button = byId("earlier");
  button.disabled = true;
  try {
    const before = byId("captions").lastElementChild.dataset.id;
    const params = new URLSearchParams({view, before_id: before, revision: current.session.instruction_revision || 0});
    const response = await fetch("api/observations?" + params, {cache: "no-store", signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error("Unavailable");
    const page = await response.json();
    if (scope === key) {
      olderPage = page;
      byId("transcript").scrollTop = 0;
      transcript(current);
      byId("transcript").focus();
    }
  } catch {
    byId("error").hidden = false;
    byId("error").textContent = "Couldn't load earlier observations. Try again.";
  } finally {
    button.disabled = false;
  }
});
byId("transcript").addEventListener("scroll", () => { byId("latest").hidden = !olderPage && byId("transcript").scrollTop < 4; });
byId("latest").addEventListener("click", () => {
  olderPage = null;
  byId("transcript").scrollTop = 0;
  transcript(current);
  byId("transcript").focus();
});

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
