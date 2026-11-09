/* Domain interaction only. The runtime owns the report shell and UI components. */
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("report-data").textContent);
  const record = data.recording;
  const $ = (id) => document.getElementById(id);
  const audio = $("audio");
  const transcript = $("transcript");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const storageKey = `mn.transcript.names.v1:${JSON.stringify([data.run_id, record.source_sha256, record.source])}`;
  let names = {};
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "{}");
    if (saved && typeof saved === "object" && !Array.isArray(saved)) {
      for (const [key, value] of Object.entries(saved)) {
        if (/^\d+:[0-7]$/.test(key) && typeof value === "string" && value.length <= 80) names[key] = value;
      }
    }
  } catch { /* Storage can be unavailable in a restricted report viewer. */ }
  let chunkIndex = -1;
  let follow = true;
  let waiting = false;
  let frame = 0;
  let generation = 0;
  let currentWords = new Set();
  let wordNodes = [];
  let prefixEnds = [];
  let lastScrolledRow;
  let editor;
  const escape = (value) => String(value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
  const time = (seconds) => {
    const s = Math.max(0, Math.floor(seconds));
    return s >= 3600 ? `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`
      : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };
  const name = (speaker, section = chunkIndex) => speaker === null ? "Unidentified speaker"
    : names[`${section}:${speaker}`] || `Speaker ${record.chunks[section].alignment.speakers.indexOf(speaker) + 1}`;
  const report = MNWebReport.createReport({
    tabs: [["transcript", "Transcript", "transcript-view"]],
    actions: [{ id: "details", label: "Recording details", icon: "info" }],
    onAction(id, trigger) {
      if (id !== "details") return;
      editor = null;
      report.openInspector("Recording details", `<p>${escape(record.source)}</p>
        <p>${time(record.duration_seconds)} · ${record.chunks.length} sections</p>
        <p>Word highlights use the model’s audio alignment. Overlapping speakers can be active together.</p>
        <p>Speaker labels restart in each section. They do not identify a person across sections or recordings.</p>
        <p>Custom names are saved only in this browser for this run. They do not change the original transcript.</p>
        <p>Audio is a captured, normalized copy of the original recording.</p>
        <p class="muted">Source SHA-256</p><code>${escape(record.source_sha256)}</code>`, trigger);
    },
    onDismiss() { editor = null; },
  });

  function displayError(message) {
    $("playback-error").textContent = message;
    $("playback-error").hidden = !message;
  }
  function renderSeats() {
    const speakers = record.chunks[chunkIndex].alignment.speakers;
    $("speaker-count").textContent = `${speakers.length} ${speakers.length === 1 ? "speaker" : "speakers"}`;
    $("section-label").textContent = `Section ${chunkIndex + 1} of ${record.chunks.length}`;
    $("seats").replaceChildren();
    for (const [index, speaker] of speakers.entries()) {
      const angle = -Math.PI / 2 + index * 2 * Math.PI / speakers.length;
      const seat = document.createElement("div");
      seat.className = "speaker-seat";
      seat.dataset.speaker = speaker;
      seat.style.left = `${50 + Math.cos(angle) * 38}%`;
      seat.style.top = `${50 + Math.sin(angle) * 38}%`;
      seat.innerHTML = `<button type="button" class="avatar" data-speaker="${speaker}" aria-label="Name ${escape(name(speaker))}" title="Name ${escape(name(speaker))}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="12" cy="8" r="3.5"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/></svg></button>
        <span class="speaker-name" title="${escape(name(speaker))}">${escape(name(speaker))}</span>`;
      $("seats").append(seat);
    }
    report.enhance($("seats"));
  }
  function renderTranscript() {
    const chunk = record.chunks[chunkIndex];
    transcript.replaceChildren();
    currentWords = new Set();
    wordNodes = [];
    prefixEnds = [];
    lastScrolledRow = null;
    let row, content, previous;
    for (const [index, word] of chunk.alignment.words.entries()) {
      if (!previous || previous.speaker !== word.speaker || word.start - previous.end > 1.5 || index % 45 === 0) {
        row = document.createElement("div");
        row.className = "utterance";
        const identity = document.createElement("div");
        identity.className = "utterance-identity";
        const label = document.createElement("span");
        label.className = "name";
        label.dataset.name = word.speaker ?? "unknown";
        label.textContent = name(word.speaker);
        label.title = label.textContent;
        const stamp = document.createElement("span");
        stamp.className = "muted time";
        stamp.textContent = time(chunk.start_seconds + word.start);
        identity.append(label, stamp);
        content = document.createElement("div");
        content.className = "utterance-text";
        row.append(identity, content);
        transcript.append(row);
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "word";
      button.dataset.word = index;
      button.textContent = word.word;
      button.title = `Seek to ${time(chunk.start_seconds + word.start)}`;
      content.append(button, document.createTextNode(" "));
      wordNodes.push(button);
      prefixEnds.push(Math.max(prefixEnds[index - 1] || 0, word.end));
      previous = word;
    }
    if (!wordNodes.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No transcript text was returned for this section.";
      transcript.append(empty);
    }
    transcript.scrollTop = 0;
  }
  function chooseSection(index, offset = 0) {
    generation += 1;
    audio.pause();
    chunkIndex = index;
    waiting = false;
    displayError("");
    audio.src = record.chunks[index].audio;
    audio.currentTime = offset;
    audio.playbackRate = Number($("speed").value);
    $("section").value = String(index);
    renderSeats();
    renderTranscript();
    update();
  }
  async function play() {
    const request = generation;
    displayError("");
    try {
      if (audio.error) audio.load();
      await audio.play();
    } catch (error) {
      if (request === generation && error.name !== "AbortError") {
        displayError("Couldn't play this recording. Open the report from its output folder and try again.");
      }
    }
    update();
  }
  function seek(seconds) {
    const resume = !audio.paused;
    const position = Math.min(Math.max(0, seconds), record.duration_seconds);
    let index = record.chunks.findIndex((chunk) => position < chunk.end_seconds);
    if (index < 0) index = record.chunks.length - 1;
    if (index !== chunkIndex) chooseSection(index, position - record.chunks[index].start_seconds);
    else audio.currentTime = position - record.chunks[index].start_seconds;
    if (resume) void play();
    update();
  }
  function update() {
    if (chunkIndex < 0) return;
    const chunk = record.chunks[chunkIndex];
    const t = audio.currentTime || 0;
    const playing = !audio.paused && !audio.ended && !audio.seeking && !audio.error && !waiting;
    $("play").textContent = audio.paused || audio.ended ? "Play" : "Pause";
    $("position").textContent = `${time(chunk.start_seconds + t)} / ${time(record.duration_seconds)}`;
    $("seek").value = String(chunk.start_seconds + t);
    $("seek").setAttribute("aria-valuetext", $("position").textContent);
    const words = chunk.alignment.words;
    let lo = 0, hi = words.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (words[mid].start <= t) lo = mid + 1;
      else hi = mid;
    }
    const active = new Set();
    for (let i = lo - 1; i >= 0 && prefixEnds[i] > t; i--) {
      if (words[i].start <= t && t < words[i].end) active.add(i);
    }
    if (audio.paused && t === 0) active.clear();
    for (const i of currentWords) if (!active.has(i)) {
      wordNodes[i].removeAttribute("aria-current");
      wordNodes[i].closest(".utterance").removeAttribute("data-current");
    }
    for (const i of active) {
      wordNodes[i].setAttribute("aria-current", "true");
      wordNodes[i].closest(".utterance").dataset.current = "true";
    }
    currentWords = active;
    const speaking = new Set();
    if (playing) for (const segment of chunk.alignment.segments) {
      if (segment.start <= t && t < segment.end) speaking.add(segment.speaker);
    }
    for (const seat of $("seats").children) {
      const activeSpeaker = speaking.has(seat.dataset.speaker);
      seat.dataset.speaking = String(activeSpeaker);
      seat.querySelector("button").dataset.speaking = String(activeSpeaker);
      seat.querySelector("button").setAttribute("aria-label", `Name ${name(seat.dataset.speaker)}${activeSpeaker ? ", speaking" : ""}`);
    }
    const speakingText = speaking.size ? [...speaking].map((s) => name(s)).join(" and ") + " speaking"
      : waiting ? "Loading audio" : playing ? "Listening" : "Ready to play";
    if ($("speaking").textContent !== speakingText) {
      $("speaking").textContent = speakingText;
      $("speaking").title = speakingText;
    }
    const first = active.size ? Math.min(...active) : null;
    const row = first === null ? null : wordNodes[first].closest(".utterance");
    if (playing && follow && row && row !== lastScrolledRow) {
      const top = row.getBoundingClientRect().top - transcript.getBoundingClientRect().top + transcript.scrollTop;
      transcript.scrollTo({ top: Math.max(0, top - transcript.clientHeight * 0.35), behavior: reducedMotion.matches ? "instant" : "smooth" });
      lastScrolledRow = row;
    }
  }
  function tick() {
    update();
    if (!audio.paused && !audio.ended) frame = requestAnimationFrame(tick);
  }
  function setFollow(value) {
    follow = value;
    $("follow").setAttribute("aria-pressed", String(follow));
    lastScrolledRow = null;
    update();
  }
  function editName(speaker, trigger) {
    editor = { speaker, section: chunkIndex };
    report.openInspector("Name this speaker", `<div class="name-editor"><label for="speaker-name">Name</label>
      <input id="speaker-name" type="text" maxlength="80" autocomplete="off" value="${escape(name(speaker))}">
      <p class="muted">This name applies to this speaker in section ${chunkIndex + 1}.</p>
      <div class="name-actions"><button id="save-name" class="primary" type="button">Save name</button><button id="cancel-name" type="button">Cancel</button></div></div>`, trigger);
    $("speaker-name").focus();
    $("speaker-name").select();
  }
  function saveName() {
    if (!editor) return;
    const key = `${editor.section}:${editor.speaker}`;
    const value = $("speaker-name").value.trim().slice(0, 80);
    if (value) names[key] = value;
    else delete names[key];
    let saved = true;
    try { localStorage.setItem(storageKey, JSON.stringify(names)); } catch { saved = false; }
    report.closeInspector();
    // Update labels in place to preserve playback, scrolling and focus.
    for (const label of transcript.querySelectorAll("[data-name]")) {
      label.textContent = name(label.dataset.name === "unknown" ? null : label.dataset.name);
      label.title = label.textContent;
    }
    for (const seat of $("seats").children) {
      const label = seat.querySelector(".speaker-name");
      label.textContent = name(seat.dataset.speaker);
      label.title = label.textContent;
      seat.querySelector("button").title = `Name ${label.textContent}`;
    }
    if (!saved) displayError("Name changed for this visit. This viewer couldn't save it for next time.");
    update();
  }
  for (const entry of data.recordings) {
    const option = new Option(entry.source, entry.page, false, entry.source === record.source);
    $("recording").append(option);
  }
  $("recording").title = record.source;
  $("duration").textContent = time(record.duration_seconds);
  $("seek").max = String(record.duration_seconds);
  for (const [index, chunk] of record.chunks.entries()) {
    $("section").append(new Option(`Section ${index + 1} · ${time(chunk.start_seconds)}`, String(index)));
  }
  report.enhance(document.querySelector(".recording-picker"));
  report.enhance(document.querySelector(".playback-controls"));
  report.enhance(document.querySelector(".transcript-heading"));
  document.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.id === "play") {
      if (!audio.paused && !audio.ended) audio.pause();
      else {
        if (audio.ended && chunkIndex === record.chunks.length - 1) chooseSection(0);
        void play();
      }
    } else if (button.id === "follow") setFollow(!follow);
    else if (button.id === "save-name") saveName();
    else if (button.id === "cancel-name") report.closeInspector();
    else if (button.classList.contains("avatar")) editName(button.dataset.speaker, button);
    else if (button.dataset.word !== undefined) {
      const chunk = record.chunks[chunkIndex];
      seek(chunk.start_seconds + chunk.alignment.words[Number(button.dataset.word)].start);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.target.id === "speaker-name" && event.key === "Enter") { event.preventDefault(); saveName(); }
  });
  document.addEventListener("change", (event) => {
    if (event.target.id === "speed") audio.playbackRate = Number(event.target.value);
    if (event.target.id === "section") seek(record.chunks[Number(event.target.value)].start_seconds);
    if (event.target.id === "recording") {
      audio.pause();
      location.href = data.recordings.find((entry) => entry.page === event.target.value).page;
    }
  });
  $("seek").addEventListener("input", (event) => seek(Number(event.target.value)));
  transcript.addEventListener("wheel", () => setFollow(false), { passive: true });
  transcript.addEventListener("touchstart", () => setFollow(false), { passive: true });
  transcript.addEventListener("keydown", (event) => {
    if (["PageUp", "PageDown", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) setFollow(false);
  });
  for (const event of ["timeupdate", "seeked", "seeking", "pause", "loadedmetadata"]) audio.addEventListener(event, update);
  audio.addEventListener("waiting", () => { waiting = true; update(); });
  audio.addEventListener("playing", () => {
    waiting = false;
    cancelAnimationFrame(frame);
    tick();
  });
  audio.addEventListener("ended", () => {
    if (!audio.ended) return;
    if (chunkIndex + 1 < record.chunks.length) { chooseSection(chunkIndex + 1); void play(); }
    else update();
  });
  audio.addEventListener("error", () => {
    if (!audio.error) return;
    waiting = false;
    displayError("Couldn't load the audio. Open the report with its audio folder and try again.");
    update();
  });
  addEventListener("pagehide", () => { generation += 1; audio.pause(); cancelAnimationFrame(frame); });
  chooseSection(0);
  report.ready();
})();
