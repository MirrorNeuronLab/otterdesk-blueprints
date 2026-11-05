// Highlight the tracker-confirmed operation without replacing native deck state.
(() => {
  let operation = null;
  let marker = null;
  let phase = '';
  const terminalLabels = {transitioning:'Preparing next phase', completed:'Completed',
    needs_review:'Needs review', failed:'Failed', cancelled:'Stopped'};
  const nativeStatus = updateStatusLabel;
  updateStatusLabel = status => {
    // A phase-owned listener deliberately closes after its final snapshot.
    // Keep that outcome visible instead of calling normal cleanup a disconnect.
    nativeStatus(terminalLabels[phase] ? 'loading' : status);
    if (terminalLabels[phase]) statusLabel.textContent = terminalLabels[phase];
  };
  function highlight() {
    marker?.destroy();
    marker = null;
    resourceLayer?.batchDraw();
    const resource = resources[operation?.resource];
    if (!resource || !resourceLayer) return;
    const position = resource.getAbsoluteLocation();
    marker = new Konva.Rect({x:position.x - 2, y:position.y - 2,
      width:resource.size_x + 4, height:resource.size_y + 4,
      stroke:'#26705c', strokeWidth:2, strokeScaleEnabled:false,
      cornerRadius:2, listening:false, name:'web-lab-operation'});
    resourceLayer.add(marker);
    resourceLayer.batchDraw();
  }
  const nativeEvent = processCentralEvent;
  processCentralEvent = async (event, data) => {
    await nativeEvent(event, data);
    highlight();
  };
  window.addEventListener('message', event => {
    if (event.source !== parent || event.origin !== location.origin || event.data?.type !== 'web-lab-operation') return;
    operation = event.data.operation;
    phase = event.data.status || '';
    if (terminalLabels[phase]) updateStatusLabel('loading');
    highlight();
  });
})();

// Refit after the native canvas observes a pane resize.
window.addEventListener('load', () => {
  const observer = new ResizeObserver(() => {
    requestAnimationFrame(() => requestAnimationFrame(fitToViewport));
  });
  observer.observe(document.getElementById('kanvas'));
});
