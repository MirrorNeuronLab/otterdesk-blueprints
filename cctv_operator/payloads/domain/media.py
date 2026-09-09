"""Read-only CCTV media surface; observations belong in the conversation."""


def dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CCTV Operator</title>
  <style>
    :root { color-scheme: dark; font: 13px system-ui, sans-serif; color: #d7dee2; background: #0c1115; }
    * { box-sizing: border-box; }
    body { margin: 0; }
    main { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding: 12px; }
    figure { margin: 0; min-width: 0; overflow: hidden; border: 1px solid #283238; border-radius: 10px; }
    figcaption { padding: 10px 12px; }
    .media { position: relative; aspect-ratio: 16 / 9; background: #050809; }
    img { display: block; width: 100%; height: 100%; object-fit: contain; }
    .empty { position: absolute; inset: 0; display: grid; place-items: center; margin: 0; padding: 16px; color: #a2afb7; text-align: center; background: #050809; }
    [hidden] { display: none !important; }
    @media (max-width: 760px) { main { grid-template-columns: minmax(0, 1fr); } }
  </style>
</head>
<body>
  <main aria-label="CCTV media">
    <figure>
      <figcaption>Live video</figcaption>
      <div class="media">
        <img id="preview" src="streams/live.mjpg" alt="Live CCTV source preview">
        <p class="empty" id="preview-empty" role="status">Connecting to video…</p>
      </div>
    </figure>
    <figure>
      <figcaption>Latest analyzed snapshot</figcaption>
      <div class="media">
        <img id="evidence" alt="Latest analyzed CCTV snapshot" hidden>
        <p class="empty" id="evidence-empty" role="status">Waiting for an analyzed snapshot.</p>
      </div>
    </figure>
  </main>
  <script>
    const preview = document.querySelector('#preview');
    const evidence = document.querySelector('#evidence');
    const previewEmpty = document.querySelector('#preview-empty');
    const evidenceEmpty = document.querySelector('#evidence-empty');
    let evidenceRevision = '';
    let previewState = 'connecting';
    let previewRetry;
    let evidenceRetry;
    function loadEvidence() {
      if (evidenceRevision) evidence.src = 'artifacts/latest_analyzed_frame.jpg?v=' + encodeURIComponent(evidenceRevision);
    }
    function applyState(state) {
      const metrics = state && state.metrics ? state.metrics : {};
      previewState = String(metrics.preview || 'connecting');
      if (previewState === 'disabled') {
        clearTimeout(previewRetry);
        previewEmpty.textContent = 'Video preview is disabled.';
        previewEmpty.hidden = false;
      }
      const revision = String(metrics['last analyzed'] || '');
      if (revision && revision !== 'waiting' && revision !== evidenceRevision) {
        evidenceRevision = revision;
        clearTimeout(evidenceRetry);
        loadEvidence();
      }
    }
    preview.addEventListener('load', () => { previewEmpty.hidden = true; });
    preview.addEventListener('error', () => {
      previewEmpty.hidden = false;
      previewEmpty.textContent = previewState === 'disabled' ? 'Video preview is disabled.' : 'Reconnecting to video…';
      clearTimeout(previewRetry);
      if (previewState !== 'disabled') previewRetry = setTimeout(() => { preview.src = 'streams/live.mjpg?retry=' + Date.now(); }, 1500);
    });
    evidence.addEventListener('load', () => { evidence.hidden = false; evidenceEmpty.hidden = true; });
    evidence.addEventListener('error', () => {
      clearTimeout(evidenceRetry);
      evidenceRetry = setTimeout(loadEvidence, 1500);
    });
    const operatorEvents = new EventSource('streams/operator-events');
    operatorEvents.addEventListener('operator-state', event => {
      try { applyState(JSON.parse(event.data)); } catch { /* retain the last valid media */ }
    });
    window.addEventListener('pagehide', () => {
      operatorEvents.close();
      clearTimeout(previewRetry);
      clearTimeout(evidenceRetry);
    });
  </script>
</body>
</html>"""
