"""Read-only CCTV media and completed scene analysis."""


def dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CCTV Operator</title>
  <style>
    :root { color-scheme: dark; font: 12px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #d7dee2; background: #0c1115; }
    * { box-sizing: border-box; }
    body { margin: 0; }
    main { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; max-width: 1120px; margin: 0 auto; padding: 10px; }
    figure, section, details { margin: 0; min-width: 0; overflow: hidden; border: 1px solid #283238; border-radius: 8px; }
    figcaption, summary { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 2px 12px; padding: 8px 10px; font-size: 11px; font-weight: 500; color: #a2afb7; }
    h1 { margin: 0; padding: 8px 10px; border-bottom: 1px solid #283238; font-size: 12px; font-weight: 600; }
    h2 { margin: 10px 0 4px; font-size: 11px; font-weight: 600; color: #a2afb7; }
    .analysis { padding: 0 10px 10px; overflow-wrap: anywhere; }
    .analysis p { margin: 4px 0; white-space: pre-wrap; }
    .analysis ul { margin: 4px 0; padding-left: 18px; }
    .analysis li + li { margin-top: 6px; }
    dl { margin: 0; padding: 2px 10px; }
    .status-row { display: grid; grid-template-columns: 82px minmax(0, 1fr); gap: 12px; padding: 7px 0; }
    .status-row + .status-row { border-top: 1px solid #202a30; }
    dt { color: #8e9da6; font-size: 11px; }
    dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
    .health { margin: 0; }
    .history { margin: 4px 0 0; font-size: 11px; color: #8e9da6; }
    .warning { margin: 0; padding: 8px 10px; border-top: 1px solid #283238; color: #f5c87b; overflow-wrap: anywhere; }
    time { font: 10px/1.5 ui-monospace, "SFMono-Regular", Consolas, monospace; font-weight: 400; color: #8e9da6; overflow-wrap: anywhere; }
    summary { cursor: pointer; }
    summary::after { content: "+"; margin-left: auto; }
    details[open] summary::after { content: "−"; }
    summary:focus-visible { outline: 2px solid #90b9d0; outline-offset: -3px; }
    .media { position: relative; aspect-ratio: 16 / 9; background: #050809; }
    img { display: block; width: 100%; height: 100%; object-fit: contain; }
    .empty { position: absolute; inset: 0; display: grid; place-items: center; margin: 0; padding: 16px; color: #a2afb7; text-align: center; background: #050809; }
    [hidden] { display: none !important; }
    @media (max-width: 260px) { .status-row { grid-template-columns: minmax(0, 1fr); gap: 2px; } }
  </style>
</head>
<body>
  <main aria-label="CCTV media">
    <figure aria-label="Live video">
      <div class="media">
        <img id="preview" src="streams/live.mjpg" alt="Live CCTV source preview">
        <p class="empty" id="preview-empty" role="status">Connecting to video…</p>
      </div>
      <figcaption>Live video<span>Sampled analysis</span></figcaption>
    </figure>
    <section aria-labelledby="status-heading">
      <h1 id="status-heading">Status</h1>
      <dl>
        <div class="status-row"><dt>People</dt><dd>
          <p class="health" id="person-status" role="status">Starting person detection…</p>
          <p class="history" id="person-history" hidden></p>
        </dd></div>
        <div class="status-row"><dt>Scene analysis</dt><dd><p class="health" id="caption-status" role="status">Waiting for the first scene sample.</p></dd></div>
        <div class="status-row"><dt>Monitoring</dt><dd><p class="health" id="analysis-status" role="status">Waiting for the first analysis.</p></dd></div>
      </dl>
      <p class="warning" id="pipeline-warning" role="alert" hidden></p>
    </section>
    <section id="scene-analysis" aria-labelledby="scene-heading" hidden>
      <h1 id="scene-heading">Latest scene analysis</h1>
      <div class="analysis">
        <p><time id="scene-at"></time></p>
        <p id="scene-understanding"></p>
        <h2>Risk forecasts</h2>
        <ul id="risk-predictions" hidden></ul>
        <p id="no-risk-predictions">No risk forecasts returned for this sample.</p>
        <h2>Uncertainties</h2>
        <ul id="uncertainties" hidden></ul>
        <p id="no-uncertainties">No uncertainties reported by the model.</p>
        <p class="history" id="scene-qualification"></p>
      </div>
    </section>
    <details>
      <summary>Latest analyzed snapshot<time id="analyzed-at" hidden></time></summary>
      <div class="media">
        <img id="evidence" alt="Latest analyzed CCTV snapshot" hidden>
        <p class="empty" id="evidence-empty" role="status">Waiting for an analyzed snapshot.</p>
      </div>
    </details>
  </main>
  <script>
    const preview = document.querySelector('#preview');
    const evidence = document.querySelector('#evidence');
    const previewEmpty = document.querySelector('#preview-empty');
    const evidenceEmpty = document.querySelector('#evidence-empty');
    const analysisStatus = document.querySelector('#analysis-status');
    const pipelineWarning = document.querySelector('#pipeline-warning');
    const analyzedAt = document.querySelector('#analyzed-at');
    const personStatus = document.querySelector('#person-status');
    const personHistory = document.querySelector('#person-history');
    const captionStatus = document.querySelector('#caption-status');
    const sceneAnalysis = document.querySelector('#scene-analysis');
    const sceneAt = document.querySelector('#scene-at');
    let sceneRevision = '';
    let evidenceRevision = '';
    let previewState = 'connecting';
    let previewRetry;
    let evidenceRetry;
    function displayTime(value) {
      const date = new Date(value);
      return Number.isFinite(date.getTime()) ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : String(value);
    }
    function loadEvidence() {
      if (evidenceRevision) evidence.src = 'artifacts/latest_analyzed_frame.jpg?v=' + encodeURIComponent(evidenceRevision);
    }
    function analysisList(id, values) {
      const list = document.querySelector('#' + id);
      list.replaceChildren(...values.map(value => {
        const item = document.createElement('li');
        item.textContent = value;
        return item;
      }));
      list.hidden = !values.length;
      document.querySelector('#no-' + id).hidden = !!values.length;
    }
    function applyState(state) {
      const metrics = state && state.metrics ? state.metrics : {};
      const pipeline = state && state.pipeline ? state.pipeline : {};
      const person = pipeline.person_events || {};
      const summary = String(person.summary || 'Starting person detection…');
      if (personStatus.textContent !== summary) personStatus.textContent = summary;
      const presence = person.last_presence;
      personHistory.hidden = !presence;
      if (presence) {
        personHistory.textContent = 'Last confirmed at ' + displayTime(presence.observed_at) + ' · sampled presence';
        personHistory.title = String(presence.observed_at) + '. Sampled detection; scene review is separate.';
      }
      captionStatus.textContent = String((pipeline.captions || {}).summary || 'Waiting for the first scene sample.');
      const status = String(metrics.status || 'Waiting for the first analysis.');
      if (analysisStatus.textContent !== status) analysisStatus.textContent = status;
      const warning = String(state.warning || '');
      if (pipelineWarning.textContent !== warning) pipelineWarning.textContent = warning;
      pipelineWarning.hidden = !pipelineWarning.textContent;
      previewState = String(metrics.preview || 'connecting');
      if (previewState === 'disabled') {
        clearTimeout(previewRetry);
        previewEmpty.textContent = 'Video preview is disabled.';
        previewEmpty.hidden = false;
      }
      const revision = String(metrics['last analyzed'] || '');
      const understanding = state.understanding || {};
      if (revision && revision !== 'waiting' && revision !== sceneRevision &&
          typeof understanding.scene_understanding === 'string' && understanding.scene_understanding.trim()) {
        sceneRevision = revision;
        document.querySelector('#scene-understanding').textContent = understanding.scene_understanding.slice(0, 1800);
        sceneAt.textContent = displayTime(revision);
        sceneAt.dateTime = revision;
        sceneAt.title = 'Sample captured at ' + revision;
        const risks = Array.isArray(understanding.risk_predictions) ? understanding.risk_predictions : [];
        analysisList('risk-predictions', risks.filter(risk => risk && typeof risk === 'object').slice(0, 2).map(risk =>
          [risk.risk, risk.visible_evidence, risk.time_horizon,
            risk.recommended_review].filter(value => typeof value === 'string' && value.trim()).join(' · ').slice(0, 1000)));
        const uncertainties = Array.isArray(understanding.uncertainties) ? understanding.uncertainties : [];
        analysisList('uncertainties', uncertainties.filter(value => typeof value === 'string').slice(0, 8).map(value => value.slice(0, 200)));
        document.querySelector('#scene-qualification').textContent =
          (understanding.source_profile === 'bundled_demo' ? 'Recorded demo playback. ' : '') +
          'Sampled observations; review the evidence before acting. Risk forecasts are not confirmed incidents.';
        sceneAnalysis.hidden = false;
      }
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
    evidence.addEventListener('load', () => {
      evidence.hidden = false;
      evidenceEmpty.hidden = true;
      analyzedAt.textContent = displayTime(evidenceRevision);
      analyzedAt.dateTime = evidenceRevision;
      analyzedAt.title = 'Analyzed at ' + evidenceRevision;
      analyzedAt.hidden = false;
    });
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
