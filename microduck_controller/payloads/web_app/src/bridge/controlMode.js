// Keep the bridge's authority gate explicit and testable.  A bare
// `?control`, `?control=0`, or arbitrary query value never arms remote input.
export function isMcpControlMode(search = location.search) {
  return new URLSearchParams(search).get("control") === "1";
}
