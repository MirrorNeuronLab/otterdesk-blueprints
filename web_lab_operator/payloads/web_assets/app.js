(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const text = (id, value) => { byId(id).textContent = value; };
  const replayNode = byId('replay-data');
  const replay = replayNode ? JSON.parse(replayNode.textContent) : null;
  let index = 0;
  let timer = null;
  let currentView = null;
  const labels = {preparing:'Preparing',planning:'Planning',transitioning:'Preparing next phase',running:'Running',completed:'Completed',needs_review:'Needs review',failed:'Failed',cancelled:'Stopped'};
  const eventReason = event => event.error || (event.action && !event.outcome.passed ?
    'The volume check did not pass.' : event.decision.reason);

  function renderState(view) {
    currentView = view;
    text('status', labels[view.status] || 'Preparing');
    text('summary', view.summary);
    text('reason', view.reason || 'Waiting for the next observed step.');
    text('tips', view.state.tips_remaining === null ? '' : `${view.state.tips_remaining} unused tips`);
    text('progress', ['preparing', 'planning', 'transitioning'].includes(view.status) ? '' :
      `${view.steps_completed} / ${view.steps_total ?? replay?.trace.events.length ?? 0} steps completed`);
    byId('operation').hidden = !view.operation;
    text('current-step', view.current_step?.replaceAll('_', ' ') || '');
    text('operation-label', view.operation?.label || '');
    byId('visualizer')?.contentWindow.postMessage({type:'web-lab-operation', operation:view.operation, status:view.status}, location.origin);
    const events = byId('events');
    events.replaceChildren();
    byId('empty').hidden = view.events.length > 0;
    for (const event of view.events) {
      const row = document.createElement('li');
      const name = document.createElement('span');
      name.className = 'step'; name.textContent = `${event.step.replaceAll('_', ' ')} · ${event.decision}`;
      name.title = name.textContent;
      const reason = document.createElement('span');
      reason.className = 'reason'; reason.textContent = event.reason;
      row.append(name, reason); events.append(row);
    }
    if (replay) renderDeck(view.state);
  }

  function renderDeck(state) {
    const deck = byId('deck'); deck.replaceChildren();
    const plates = [...new Set(Object.keys(state.wells).map(key => key.split('/')[0]))];
    for (const plate of plates) {
      const section = document.createElement('section'); section.className = 'plate';
      const title = document.createElement('h3'); title.textContent = plate; title.title = plate;
      const wells = document.createElement('div'); wells.className = 'wells';
      for (const [address, value] of Object.entries(state.wells).filter(([key]) => key.startsWith(plate + '/'))) {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'well';
        button.style.setProperty('--fill', `${Math.max(0, Math.min(100, value.volume_ul / 360 * 100))}%`);
        button.textContent = address.split('/')[1];
        button.title = `${address}: ${value.volume_ul} uL; ${value.liquids.join(', ') || 'empty'}`;
        button.setAttribute('aria-label', button.title);
        button.addEventListener('click', () => text('reason', button.title));
        wells.append(button);
      }
      section.append(title, wells); deck.append(section);
    }
  }

  function frame() {
    const events = replay.trace.events.slice(0, index);
    const last = events.at(-1);
    renderState({status: index === replay.trace.events.length ? replay.result.status : 'running',
      summary: replay.result.summary,
      reason: index === replay.trace.events.length && replay.result.reason ? replay.result.reason :
        (last ? eventReason(last) : 'Initial simulated deck.'),
      steps_completed: events.filter(event => event.outcome.passed).length,
      state: last ? last.after : replay.trace.initial,
      events: events.map(event => ({step:event.step.id,decision:event.decision.decision,reason:eventReason(event)}))});
    byId('frame').value = String(index);
    text('position', `${index} / ${replay.trace.events.length}`);
    byId('previous').disabled = index === 0;
    byId('next').disabled = index === replay.trace.events.length;
  }

  function pause() { if (timer) clearInterval(timer); timer = null; text('play', 'Play'); }
  if (replay) {
    byId('visualizer')?.remove();
    byId('deck').hidden = false; byId('replay').hidden = false;
    byId('frame').max = String(replay.trace.events.length);
    byId('play').disabled = replay.trace.events.length === 0;
    byId('previous').onclick = () => { pause(); index = Math.max(0, index - 1); frame(); };
    byId('next').onclick = () => { pause(); index = Math.min(replay.trace.events.length, index + 1); frame(); };
    byId('frame').oninput = event => { pause(); index = Number(event.target.value); frame(); };
    byId('play').onclick = () => {
      if (timer) { pause(); return; }
      if (index === replay.trace.events.length) index = 0;
      text('play', 'Pause'); frame();
      timer = setInterval(() => { index = Math.min(index + 1, replay.trace.events.length); frame();
        if (index === replay.trace.events.length) pause(); }, 850);
    };
    byId('limits').hidden = false;
    const issues = [...(replay.result.assumptions || []), ...(replay.result.unresolved || [])];
    byId('review').hidden = issues.length === 0;
    for (const issue of issues) { const li = document.createElement('li'); li.textContent = issue; byId('review-items').append(li); }
    for (const limit of replay.result.limitations) { const li = document.createElement('li'); li.textContent = limit; byId('limit-list').append(li); }
    byId('goals').hidden = false;
    for (const goal of replay.result.goals) {
      const row = document.createElement('tr');
      for (const value of [goal.well, goal.volume_ul, goal.observed_ul, goal.met ? 'Met' : 'Needs review']) {
        const cell = document.createElement('td'); cell.textContent = String(value); row.append(cell);
      }
      byId('goal-rows').append(row);
    }
    frame();
  } else {
    byId('visualizer').addEventListener('load', () => {
      if (currentView) byId('visualizer').contentWindow.postMessage(
        {type:'web-lab-operation', operation:currentView.operation, status:currentView.status}, location.origin);
    });
    function connect() {
      const url = new URL(window.__MN_JOB_UI_PROXY_BASE__ ? 'ws/monitor/ws' : 'monitor/ws', location.href);
      url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const socket = new WebSocket(url);
      socket.onmessage = event => {
        renderState(JSON.parse(event.data));
        byId('connection').hidden = true;
      };
      socket.onclose = () => {
        if (currentView && ['transitioning', 'completed', 'needs_review', 'failed', 'cancelled'].includes(currentView.status)) return;
        byId('connection').hidden = false;
        setTimeout(connect, 1000);
      };
    }
    connect();
  }
})();
