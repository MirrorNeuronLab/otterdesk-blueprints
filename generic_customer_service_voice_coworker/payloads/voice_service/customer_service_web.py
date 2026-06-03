"""Browser UI routes for the generic customer-service voice app."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse


CUSTOMER_SERVICE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Customer Service Voice Co-worker</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172026;
      --muted: #65717a;
      --line: #d7dee2;
      --surface: #fbfcfb;
      --panel: #eef5f1;
      --accent: #176b61;
      --accent-strong: #0b4f48;
      --warn: #a05a00;
      --error: #b3261e;
      --blue: #235d99;
      --focus: #2457d6;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      font: 16px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--surface);
    }

    button, textarea {
      font: inherit;
    }

    button {
      min-height: 42px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: #ffffff;
      color: var(--ink);
      padding: 0 14px;
      cursor: pointer;
      font-weight: 700;
    }

    button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #ffffff;
    }

    button.danger {
      border-color: #e5c6c3;
      color: var(--error);
    }

    button:disabled {
      opacity: .52;
      cursor: not-allowed;
    }

    button:focus-visible, textarea:focus-visible {
      outline: 3px solid var(--focus);
      outline-offset: 2px;
    }

    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(300px, 420px) minmax(0, 1fr);
    }

    aside {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 22px;
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      gap: 16px;
      min-height: 0;
    }

    main {
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
    }

    h1, h2, p {
      margin: 0;
    }

    h1 {
      font-size: 1.18rem;
      line-height: 1.2;
    }

    h2 {
      font-size: 1rem;
      line-height: 1.25;
    }

    .subtle {
      color: var(--muted);
      font-size: .92rem;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .mark {
      width: 42px;
      height: 42px;
      border-radius: 8px;
      background:
        linear-gradient(135deg, #176b61 0 48%, transparent 48%),
        linear-gradient(315deg, #235d99 0 48%, #f4c36b 48%);
      border: 1px solid #0f2d2a;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 8px 10px;
      min-height: 42px;
      color: #34424a;
      font-size: .92rem;
    }

    .dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--muted);
      flex: 0 0 auto;
    }

    .dot.live { background: var(--accent); }
    .dot.warn { background: var(--warn); }
    .dot.error { background: var(--error); }

    .knowledge {
      min-height: 0;
      display: grid;
      grid-template-rows: auto minmax(260px, 1fr) auto auto;
      gap: 10px;
    }

    textarea {
      width: 100%;
      min-height: 260px;
      resize: none;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink);
      padding: 12px;
      tab-size: 2;
    }

    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }

    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }

    .call {
      min-height: 0;
      display: grid;
      grid-template-columns: minmax(260px, 420px) minmax(280px, 1fr);
      gap: 24px;
      padding: 24px;
    }

    .voice {
      display: grid;
      align-content: start;
      gap: 16px;
    }

    .stage {
      min-height: 288px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      display: grid;
      align-content: center;
      justify-items: center;
      gap: 18px;
      padding: 24px;
      text-align: center;
    }

    .meter {
      width: min(240px, 70vw);
      height: 76px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }

    .bar {
      width: 14px;
      height: 20px;
      border-radius: 8px;
      background: var(--line);
      transition: height .12s ease, background .12s ease;
    }

    .speaking .bar:nth-child(1) { height: 32px; background: var(--accent); }
    .speaking .bar:nth-child(2) { height: 58px; background: var(--blue); }
    .speaking .bar:nth-child(3) { height: 72px; background: var(--warn); }
    .speaking .bar:nth-child(4) { height: 50px; background: var(--blue); }
    .speaking .bar:nth-child(5) { height: 36px; background: var(--accent); }

    .actions {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 10px;
    }

    .note {
      border-left: 4px solid var(--accent);
      background: #f6faf8;
      padding: 10px 12px;
      color: #34424a;
      font-size: .94rem;
    }

    .transcript {
      min-height: 0;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }

    .transcript header {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }

    .log {
      overflow: auto;
      padding: 16px;
      display: grid;
      align-content: start;
      gap: 12px;
      min-height: 320px;
    }

    .bubble {
      max-width: 74ch;
      border: 1px solid var(--line);
      border-left: 4px solid var(--blue);
      border-radius: 8px;
      background: #ffffff;
      padding: 10px 12px;
    }

    .bubble strong {
      display: block;
      color: var(--muted);
      font-size: .8rem;
      margin-bottom: 4px;
    }

    .bubble.user {
      border-left-color: var(--accent);
      justify-self: end;
    }

    .bubble.bot {
      border-left-color: var(--blue);
    }

    .footer {
      border-top: 1px solid var(--line);
      padding: 12px 24px;
      background: #ffffff;
      color: var(--muted);
      font-size: .88rem;
      display: flex;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    @media (max-width: 980px) {
      .shell {
        grid-template-columns: 1fr;
      }

      aside {
        border-right: 0;
        border-bottom: 1px solid var(--line);
        max-height: 54vh;
      }

      .call {
        grid-template-columns: 1fr;
      }

      main {
        min-height: auto;
      }
    }

    @media (max-width: 560px) {
      aside, .topbar, .call, .footer {
        padding-left: 16px;
        padding-right: 16px;
      }

      .topbar {
        align-items: flex-start;
        flex-direction: column;
      }

      .stage {
        min-height: 240px;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand">
        <div class="mark" aria-hidden="true"></div>
        <div>
          <h1 id="business-title">Customer Service Voice</h1>
          <p class="subtle">Editable support knowledge for this live run.</p>
        </div>
      </div>

      <div class="status" aria-live="polite">
        <span id="knowledge-dot" class="dot warn"></span>
        <span id="knowledge-status">Loading knowledge</span>
      </div>

      <section class="knowledge">
        <div>
          <h2>Knowledge</h2>
          <p class="subtle">Saved text is used on the next customer turn.</p>
        </div>
        <textarea id="knowledge-text" spellcheck="true"></textarea>
        <div class="row">
          <button id="reload-knowledge" type="button">Reload</button>
          <button id="save-knowledge" class="primary" type="button">Save knowledge</button>
        </div>
        <p id="knowledge-meta" class="subtle"></p>
      </section>

      <p class="subtle">Artifacts are written to the OtterDesk run store: knowledge, conversation, events, logs, voice_service.json, and final_artifact.json.</p>
    </aside>

    <main>
      <div class="topbar">
        <div>
          <h2>Live customer call</h2>
          <p class="subtle">Start voice, allow microphone access, and speak naturally.</p>
        </div>
        <div class="status" aria-live="polite">
          <span id="status-dot" class="dot"></span>
          <span id="status-text">Idle</span>
        </div>
      </div>

      <section class="call">
        <div class="voice">
          <div id="stage" class="stage">
            <div id="meter" class="meter" aria-hidden="true">
              <span class="bar"></span>
              <span class="bar"></span>
              <span class="bar"></span>
              <span class="bar"></span>
              <span class="bar"></span>
            </div>
            <div>
              <h2 id="stage-title">Ready for a customer</h2>
              <p id="stage-copy" class="subtle">The co-worker answers from the editable knowledge and recommends escalation when unsure.</p>
            </div>
            <div class="actions">
              <button id="start" class="primary" type="button">Start voice</button>
              <button id="mute" type="button" disabled>Mute mic</button>
              <button id="stop" class="danger" type="button" disabled>End</button>
            </div>
          </div>
          <div class="note">Ask a question that depends on the knowledge text, edit the text, save it, then ask again to confirm the answer changes.</div>
        </div>

        <div class="transcript">
          <header>
            <h2>Conversation</h2>
            <button id="clear" type="button">Clear</button>
          </header>
          <div id="log" class="log" aria-live="polite">
            <div class="bubble bot">
              <strong>Co-worker</strong>
              Press Start voice and I will answer from the current knowledge.
            </div>
          </div>
        </div>
      </section>

      <div class="footer">
        <span>Models: NVIDIA Parakeet ASR + Nemotron vLLM + Magpie TTS</span>
        <span>Transport: Pipecat SmallWebRTC over HTTPS</span>
      </div>
    </main>
  </div>

  <audio id="bot-audio" autoplay playsinline></audio>

  <script type="module">
    const CDN_CLIENT = "https://esm.sh/@pipecat-ai/client-js@1.3.0";
    const CDN_WEBRTC = "https://esm.sh/@pipecat-ai/small-webrtc-transport@1.3.0";

    const els = {
      start: document.querySelector("#start"),
      mute: document.querySelector("#mute"),
      stop: document.querySelector("#stop"),
      clear: document.querySelector("#clear"),
      log: document.querySelector("#log"),
      statusText: document.querySelector("#status-text"),
      statusDot: document.querySelector("#status-dot"),
      stage: document.querySelector("#stage"),
      stageTitle: document.querySelector("#stage-title"),
      stageCopy: document.querySelector("#stage-copy"),
      audio: document.querySelector("#bot-audio"),
      knowledgeText: document.querySelector("#knowledge-text"),
      knowledgeStatus: document.querySelector("#knowledge-status"),
      knowledgeDot: document.querySelector("#knowledge-dot"),
      knowledgeMeta: document.querySelector("#knowledge-meta"),
      reloadKnowledge: document.querySelector("#reload-knowledge"),
      saveKnowledge: document.querySelector("#save-knowledge"),
    };

    let client = null;
    let micEnabled = true;

    function setStatus(text, mode = "") {
      els.statusText.textContent = text;
      els.statusDot.className = `dot ${mode}`.trim();
    }

    function setKnowledgeStatus(text, mode = "") {
      els.knowledgeStatus.textContent = text;
      els.knowledgeDot.className = `dot ${mode}`.trim();
    }

    function setStage(title, copy, speaking = false) {
      els.stageTitle.textContent = title;
      els.stageCopy.textContent = copy;
      els.stage.classList.toggle("speaking", speaking);
    }

    function escapeHtml(text) {
      return text.replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      }[char]));
    }

    function appendBubble(who, text, type) {
      if (!text || !text.trim()) return;
      const bubble = document.createElement("div");
      bubble.className = `bubble ${type}`;
      bubble.innerHTML = `<strong>${who}</strong>${escapeHtml(text.trim())}`;
      els.log.appendChild(bubble);
      els.log.scrollTop = els.log.scrollHeight;
    }

    function attachAudioTrack(track, participant) {
      if (!track || track.kind !== "audio") return;
      if (participant && participant.local) return;
      els.audio.srcObject = new MediaStream([track]);
      els.audio.play().catch(() => {
        setStatus("Tap Start again to allow audio playback", "warn");
      });
    }

    function describeMeta(metadata) {
      if (!metadata) return "";
      const bytes = Number(metadata.bytes || 0).toLocaleString();
      const digest = metadata.sha256 ? String(metadata.sha256).slice(0, 12) : "none";
      return `${bytes} bytes | sha256 ${digest} | ${metadata.updated_at || ""}`;
    }

    async function loadKnowledge() {
      setKnowledgeStatus("Loading knowledge", "warn");
      const response = await fetch("/api/knowledge", { cache: "no-store" });
      if (!response.ok) throw new Error(`Knowledge load failed: ${response.status}`);
      const payload = await response.json();
      els.knowledgeText.value = payload.text || "";
      els.knowledgeMeta.textContent = describeMeta(payload.metadata);
      setKnowledgeStatus("Knowledge loaded", "live");
    }

    async function saveKnowledge() {
      els.saveKnowledge.disabled = true;
      setKnowledgeStatus("Saving knowledge", "warn");
      try {
        const response = await fetch("/api/knowledge", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ text: els.knowledgeText.value }),
        });
        if (!response.ok) throw new Error(`Knowledge save failed: ${response.status}`);
        const payload = await response.json();
        els.knowledgeMeta.textContent = describeMeta(payload.metadata);
        setKnowledgeStatus("Knowledge saved", "live");
      } catch (error) {
        setKnowledgeStatus(error?.message || "Knowledge save failed", "error");
      } finally {
        els.saveKnowledge.disabled = false;
      }
    }

    async function startCall() {
      els.start.disabled = true;
      setStatus("Loading voice client", "warn");
      setStage("Starting", "Preparing WebRTC and microphone access.");

      try {
        const [{ PipecatClient }, { SmallWebRTCTransport }] = await Promise.all([
          import(CDN_CLIENT),
          import(CDN_WEBRTC),
        ]);

        client = new PipecatClient({
          transport: new SmallWebRTCTransport({ waitForICEGathering: true }),
          enableMic: true,
          enableCam: false,
          callbacks: {
            onConnected: () => {
              setStatus("Connected", "live");
              els.mute.disabled = false;
              els.stop.disabled = false;
            },
            onDisconnected: () => {
              setStatus("Disconnected");
              setStage("Call ended", "Start a new voice session when you are ready.");
              els.start.disabled = false;
              els.mute.disabled = true;
              els.stop.disabled = true;
            },
            onTransportStateChanged: (state) => setStatus(state, state === "ready" ? "live" : "warn"),
            onBotReady: () => {
              setStatus("Ready", "live");
              setStage("Co-worker is listening", "Ask a customer-service question.");
            },
            onTrackStarted: attachAudioTrack,
            onUserStartedSpeaking: () => setStage("Listening", "Go ahead. The co-worker will wait for the end of your turn.", true),
            onUserStoppedSpeaking: () => setStage("Thinking", "Checking the editable knowledge.", false),
            onBotStartedSpeaking: () => setStage("Co-worker is speaking", "You can interrupt naturally.", true),
            onBotStoppedSpeaking: () => setStage("Co-worker is listening", "Continue or ask another question.", false),
            onUserTranscript: (data) => {
              if (data.final) appendBubble("You", data.text, "user");
            },
            onBotOutput: (data) => {
              if (data.text && data.spoken) appendBubble("Co-worker", data.text, "bot");
            },
            onDeviceError: (error) => {
              setStatus("Microphone unavailable", "error");
              setStage("Microphone blocked", error?.message || "Check browser permissions for this page.");
            },
            onError: (message) => {
              const text = message?.data?.message || "Voice session error";
              setStatus(text, "error");
              setStage("Connection error", text);
              els.start.disabled = false;
            },
          },
        });

        await client.connect({ webrtcUrl: "/api/offer" });
        const track = client.tracks()?.bot?.audio;
        if (track) attachAudioTrack(track, { local: false });
      } catch (error) {
        const message = error?.message || String(error);
        setStatus("Could not start", "error");
        setStage("Could not start voice", message);
        els.start.disabled = false;
      }
    }

    async function toggleMute() {
      if (!client) return;
      micEnabled = !micEnabled;
      client.enableMic(micEnabled);
      els.mute.textContent = micEnabled ? "Mute mic" : "Unmute mic";
      setStatus(micEnabled ? "Mic on" : "Mic muted", micEnabled ? "live" : "warn");
    }

    async function stopCall() {
      if (!client) return;
      await client.disconnect();
      client = null;
    }

    els.start.addEventListener("click", startCall);
    els.mute.addEventListener("click", toggleMute);
    els.stop.addEventListener("click", stopCall);
    els.clear.addEventListener("click", () => {
      els.log.innerHTML = "";
    });
    els.reloadKnowledge.addEventListener("click", () => {
      loadKnowledge().catch((error) => setKnowledgeStatus(error?.message || "Load failed", "error"));
    });
    els.saveKnowledge.addEventListener("click", saveKnowledge);

    loadKnowledge().catch((error) => setKnowledgeStatus(error?.message || "Load failed", "error"));
  </script>
</body>
</html>"""


def register_customer_service_routes(app: FastAPI) -> None:
    """Attach customer-service UI routes to the Pipecat runner app."""

    @app.get("/", include_in_schema=False)
    async def home():
        return RedirectResponse(url="/customer-service")

    @app.get("/customer-service", include_in_schema=False)
    async def customer_service():
        return HTMLResponse(CUSTOMER_SERVICE_HTML)

