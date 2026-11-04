// Use the native inspector control so it remains available at every width.
window.addEventListener('load', () => {
  const compact = window.matchMedia('(max-width: 640px)');
  const inspector = document.getElementById('toolbar-right-toggle');
  const toolbar = document.getElementById('toolbar');
  let restoreInspector = false;
  function fitWorkspace() {
    if (compact.matches) {
      restoreInspector = toolbar.style.display !== 'none';
      if (restoreInspector) inspector.click();
    } else if (restoreInspector && toolbar.style.display === 'none') {
      inspector.click();
    }
    // Let the native canvas resize first, then fit the deck to the new pane.
    requestAnimationFrame(() => requestAnimationFrame(fitToViewport));
  }
  compact.addEventListener('change', fitWorkspace);
  fitWorkspace();
});
