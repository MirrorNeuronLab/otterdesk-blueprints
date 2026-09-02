import Box from "@mui/material/Box";
import { useGame } from "../store.js";

export default function RemoteStatus() {
  const remote = useGame((state) => state.remoteControl);
  if (!remote.enabled) return null;
  const labels = {
    connected: "MCP CONNECTED",
    ready: "MCP READY",
    waiting: "MCP WAITING",
    spectator: "MCP SPECTATOR",
    offline: "MCP OFFLINE",
    connecting: "MCP LINKING",
  };
  const label = labels[remote.status] ?? "MCP LINKING";
  const tone = remote.status === "ready"
    ? "#62e6a7"
    : remote.status === "spectator"
      ? "#ffc35d"
      : "#ff8b6a";
  return (
    <Box
      aria-live="polite"
      sx={{
        position: "fixed", left: "1rem", bottom: "1rem", zIndex: 13,
        px: "0.55rem", py: "0.3rem", border: "1px solid rgba(255,255,255,.28)",
        background: "rgba(8,8,12,.84)", color: tone, fontFamily: "monospace",
        fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.08em",
      }}
    >
      {label}
    </Box>
  );
}
