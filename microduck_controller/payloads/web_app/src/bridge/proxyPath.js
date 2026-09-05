// OtterDesk embeds a worker UI at /job-ui-proxy/<job>/<port>/. Keep static
// content relative (Vite's base) and route the browser bridge through the
// proxy's WebSocket endpoint when the simulator is embedded there.

export function bridgeSocketPath(pathname = location.pathname) {
  const match = String(pathname).match(/^\/job-ui-proxy\/[^/]+\/\d+(?=\/|$)/);
  return match ? `${match[0]}/ws/bridge` : "/bridge";
}
