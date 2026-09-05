// Same-origin browser bridge for one Microduck control tab. The server owns
// the lease and public MCP contract; this code only accepts server-delivered,
// allowlisted commands and reports compact simulation state.

import { useGame } from "../store.js";
import { isMcpControlMode } from "./controlMode.js";
import { bridgeSocketPath } from "./proxyPath.js";

const STATE_INTERVAL_MS = 200;
const RETRY_INTERVAL_MS = 1000;

export class McpBridge {
  #remote;
  #snapshot;
  #requestLoco;
  #reset;
  #ballAction;
  #stopAll;
  #socket = null;
  #timer = null;
  #retry = null;
  #sessionId;
  #pending = null;
  #stopped = false;

  constructor({ remote, snapshot, requestLoco, reset, ballAction, stopAll }) {
    this.#remote = remote;
    this.#snapshot = snapshot;
    this.#requestLoco = requestLoco;
    this.#reset = reset;
    this.#ballAction = ballAction;
    this.#stopAll = typeof stopAll === "function"
      ? stopAll
      : (reason) => remote.stop(reason);
    this.#sessionId = globalThis.crypto?.randomUUID?.() ?? `microduck-${Date.now()}-${Math.random()}`;
    remote.setStatusListener((update) => this.sendCommandUpdate(update));
  }

  start() {
    if (this.#socket || !isMcpControlMode()) return;
    this.#stopped = false;
    this.#connect();
  }

  stop() {
    this.#stopped = true;
    this.#pending = null;
    this.#stopAll("bridge_stopped");
    clearInterval(this.#timer);
    clearTimeout(this.#retry);
    this.#timer = null;
    this.#retry = null;
    this.#socket?.close();
    this.#socket = null;
    useGame.setState({ remoteControl: { enabled: true, status: "offline", lease: "none" } });
  }

  sendCommandUpdate(update) {
    this.#send({ type: "command_update", ...update });
  }

  #connect() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${location.host}${bridgeSocketPath()}`);
    this.#socket = socket;
    useGame.setState({ remoteControl: { enabled: true, status: "connecting", lease: "none" } });
    socket.addEventListener("open", () => {
      this.#send({ type: "hello", session_id: this.#sessionId, control_mode: true });
    });
    socket.addEventListener("message", (event) => this.#receive(event));
    socket.addEventListener("close", () => {
      if (this.#socket !== socket) return;
      this.#socket = null;
      clearInterval(this.#timer);
      this.#timer = null;
      this.#pending = null;
      this.#stopAll("bridge_disconnected");
      useGame.setState({ remoteControl: { enabled: true, status: "offline", lease: "none" } });
      if (!this.#stopped) this.#retry = setTimeout(() => this.#connect(), RETRY_INTERVAL_MS);
    });
    socket.addEventListener("error", () => socket.close());
  }

  #receive(event) {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    if (message?.type === "lease") {
      const accepted = message.accepted === true;
      useGame.setState({
        remoteControl: {
          enabled: true,
          status: accepted ? "connected" : "spectator",
          lease: accepted ? "active" : "spectator",
        },
      });
      if (accepted && !this.#timer) {
        this.#timer = setInterval(() => this.#publish(), STATE_INTERVAL_MS);
        this.#publish();
      }
      return;
    }
    if (message?.type === "command" && message.command) this.#applyCommand(message.command);
  }

  #applyCommand(command) {
    const { command_id: commandId, kind, payload = {} } = command;
    if (!commandId || !kind) return;
    if (kind === "motion_plan") {
      this.#remote.startPlan(commandId, payload.segments);
      return;
    }
    if (kind === "find_ball") {
      this.#remote.startFindBall(commandId);
      return;
    }
    if (kind === "free_play") {
      this.#remote.startFreePlay(commandId);
      return;
    }
    if (kind === "stop") {
      if (this.#pending) {
        this.sendCommandUpdate({
          command_id: this.#pending.commandId,
          status: "cancelled",
          reason: "stopped_by_operator",
        });
        this.#pending = null;
      }
      this.#stopAll("stopped_by_operator");
      this.sendCommandUpdate({ command_id: commandId, status: "completed", reason: "" });
      return;
    }
    if (kind === "set_locomotion") {
      this.#requestLoco(payload.locomotion);
      this.#watch(commandId, kind, (state) =>
        state.duck.locomotion === payload.locomotion && !state.duck.busy && state.ready,
      );
      return;
    }
    if (kind === "ball_action") {
      const result = this.#ballAction(payload.action);
      if (!result?.accepted) {
        this.sendCommandUpdate({ command_id: commandId, status: "rejected", reason: result?.reason || "action_rejected" });
        return;
      }
      this.#watch(commandId, kind, (state, elapsed) => {
        if (payload.action === "spawn_ball") return state.ball.active;
        return elapsed > 250 && !state.duck.busy;
      });
      return;
    }
    if (kind === "reset") {
      this.#reset();
      this.#watch(commandId, kind, (state, elapsed) => elapsed > 500 && state.ready && !state.duck.busy);
      return;
    }
    this.sendCommandUpdate({ command_id: commandId, status: "rejected", reason: "unsupported_command" });
  }

  #watch(commandId, kind, complete) {
    if (this.#pending) {
      this.sendCommandUpdate({ command_id: commandId, status: "rejected", reason: "browser_busy" });
      return;
    }
    this.#pending = { commandId, kind, startedAt: performance.now(), complete };
    this.sendCommandUpdate({ command_id: commandId, status: "accepted", reason: "" });
  }

  #publish() {
    const state = this.#snapshot();
    useGame.setState({
      remoteControl: {
        enabled: true,
        status: state.ready ? "ready" : "waiting",
        lease: "active",
      },
    });
    const pending = this.#pending;
    if (pending) {
      const elapsed = performance.now() - pending.startedAt;
      if (pending.complete(state, elapsed)) {
        this.sendCommandUpdate({ command_id: pending.commandId, status: "completed", reason: "" });
        this.#pending = null;
      } else if (elapsed > 15_000) {
        this.sendCommandUpdate({ command_id: pending.commandId, status: "rejected", reason: "browser_command_timeout" });
        this.#pending = null;
      } else {
        this.sendCommandUpdate({ command_id: pending.commandId, status: "running", reason: "" });
      }
    }
    this.#send({ type: "state", state });
  }

  #send(value) {
    if (this.#socket?.readyState !== WebSocket.OPEN) return false;
    this.#socket.send(JSON.stringify(value));
    return true;
  }
}
