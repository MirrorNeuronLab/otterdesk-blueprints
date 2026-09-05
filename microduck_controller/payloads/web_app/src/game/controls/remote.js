// Remote MCP input source. It intentionally accepts only already-validated
// high-level segments; the service never provides a raw MuJoCo action or a
// velocity value. The source is first in Controller priority while active,
// then releases authority back to local keyboard, touch, and gamepad input.

import { BallNavigator } from "./ball-navigation.js";

const ZERO = new Float32Array(3);

export class RemoteSource {
  id = "remote";
  connected = true;
  command = new Float32Array(3);
  axes = { jaw: 0, orbitX: 0, orbitY: 0, ride: 0 };
  pressed = {};

  #getVelocityLimits;
  #getNavigationState;
  #performBallAction;
  #clock;
  #plan = null;
  #segmentEndsAt = 0;
  #statusListener = () => {};

  constructor({
    getVelocityLimits,
    getNavigationState = () => ({}),
    performBallAction = () => ({ accepted: false, reason: "ball_action_unavailable" }),
    clock = () => performance.now(),
  }) {
    this.#getVelocityLimits = getVelocityLimits;
    this.#getNavigationState = getNavigationState;
    this.#performBallAction = performBallAction;
    this.#clock = clock;
  }

  setStatusListener(listener) {
    this.#statusListener = typeof listener === "function" ? listener : () => {};
  }

  isActive() {
    return this.#plan !== null;
  }

  get status() {
    return this.#plan
      ? { command_id: this.#plan.commandId, kind: this.#plan.kind, status: this.#plan.status }
      : {};
  }

  startPlan(commandId, segments) {
    if (this.#plan) {
      this.#emit(commandId, "rejected", "remote_motion_already_active");
      return false;
    }
    if (!Array.isArray(segments) || segments.length === 0) {
      this.#emit(commandId, "rejected", "invalid_motion_plan");
      return false;
    }
    this.#plan = {
      commandId,
      kind: "motion_plan",
      segments: segments.map((segment) => ({ ...segment })),
      index: 0,
      status: "accepted",
    };
    this.#segmentEndsAt = 0;
    this.command.set(ZERO);
    this.#emit(commandId, "accepted", "");
    return true;
  }

  startFindBall(commandId) {
    if (this.#plan) {
      this.#emit(commandId, "rejected", "remote_motion_already_active");
      return false;
    }
    const now = this.#clock();
    this.#plan = {
      commandId,
      kind: "find_ball",
      status: "accepted",
      navigator: new BallNavigator(commandId, now),
    };
    this.#segmentEndsAt = 0;
    this.command.set(ZERO);
    this.#emit(commandId, "accepted", "");
    return true;
  }

  startFreePlay(commandId) {
    if (this.#plan) {
      this.#emit(commandId, "rejected", "remote_motion_already_active");
      return false;
    }
    const snapshot = this.#getNavigationState();
    if (snapshot?.ball?.active !== true) {
      this.#emit(commandId, "rejected", "ball_not_active");
      return false;
    }
    if (snapshot?.duck?.locomotion !== "legs") {
      this.#emit(commandId, "rejected", "kicks_require_legs");
      return false;
    }
    if (snapshot?.ready !== true || snapshot?.duck?.mode !== "walk") {
      this.#emit(commandId, "rejected", "free_play_unavailable");
      return false;
    }
    const now = this.#clock();
    this.#plan = {
      commandId,
      kind: "free_play",
      status: "accepted",
      phase: "navigating",
      navigator: new BallNavigator(commandId, now),
      nextKick: "kick_left",
      kickCount: 0,
      activationReported: false,
    };
    this.#segmentEndsAt = 0;
    this.command.set(ZERO);
    this.#emit(commandId, "accepted", "");
    return true;
  }

  stop(reason = "stopped_by_operator") {
    if (!this.#plan) {
      this.command.set(ZERO);
      return;
    }
    const { commandId, navigator, kind, activationReported } = this.#plan;
    const result = navigator?.cancel(this.#getNavigationState(), this.#clock(), reason);
    this.#plan = null;
    this.#segmentEndsAt = 0;
    this.command.set(ZERO);
    if (kind !== "free_play" || !activationReported) {
      this.#emit(commandId, "cancelled", reason, "", result?.result);
    }
  }

  poll() {
    if (!this.#plan) return;
    const now = this.#clock();
    if (this.#plan.kind === "find_ball" || this.#plan.kind === "free_play") return;
    if (!this.#segmentEndsAt) this.#startSegment(now);
    while (this.#plan && now >= this.#segmentEndsAt) {
      this.#plan.index += 1;
      if (this.#plan.index >= this.#plan.segments.length) {
        const { commandId } = this.#plan;
        this.#plan = null;
        this.#segmentEndsAt = 0;
        this.command.set(ZERO);
        this.#emit(commandId, "completed", "");
        return;
      }
      this.#startSegment(this.#segmentEndsAt);
    }
  }

  pollNavigation() {
    if (this.#plan?.kind === "find_ball") this.#pollNavigation(this.#clock());
    if (this.#plan?.kind === "free_play") this.#pollFreePlay(this.#clock());
  }

  #pollNavigation(now) {
    if (!this.#plan?.navigator) return;
    const update = this.#plan.navigator.step(
      this.#getNavigationState(),
      this.#getVelocityLimits(),
      now,
    );
    this.command.set(update.command);
    if (update.status === "running") {
      this.#plan.status = "running";
      if (update.progress) {
        this.#emit(this.#plan.commandId, "running", "", update.progress);
      }
      return;
    }
    const commandId = this.#plan.commandId;
    this.#plan = null;
    this.command.set(ZERO);
    this.#emit(commandId, update.status, update.reason, "", update.result);
  }

  #pollFreePlay(now) {
    const plan = this.#plan;
    if (!plan || plan.kind !== "free_play") return;
    const snapshot = this.#getNavigationState();

    if (plan.phase === "waiting_for_kick") {
      this.command.set(ZERO);
      if (snapshot?.ball?.active !== true) {
        this.#finishFreePlay("ball_not_active");
        return;
      }
      if (snapshot?.duck?.locomotion !== "legs") {
        this.#finishFreePlay("kicks_require_legs");
        return;
      }
      if (snapshot?.ready !== true || snapshot?.duck?.mode !== "walk") return;
      plan.phase = "navigating";
      plan.navigator = new BallNavigator(plan.commandId, now);
    }

    const update = plan.navigator?.step(snapshot, this.#getVelocityLimits(), now);
    if (!update) return;
    this.command.set(update.command);
    if (update.status === "running") {
      plan.status = "running";
      if (update.progress && !plan.activationReported) {
        this.#emit(plan.commandId, "running", "", update.progress);
      }
      return;
    }
    if (update.status !== "completed") {
      this.#finishFreePlay(update.reason || "free_play_unavailable");
      return;
    }

    this.command.set(ZERO);
    const action = plan.nextKick;
    const kick = this.#performBallAction(action);
    if (!kick?.accepted) {
      this.#finishFreePlay(kick?.reason || "kick_not_available");
      return;
    }
    plan.kickCount += 1;
    plan.nextKick = action === "kick_left" ? "kick_right" : "kick_left";
    plan.phase = "waiting_for_kick";
    plan.navigator = null;
    plan.status = "running";
    if (!plan.activationReported) {
      plan.activationReported = true;
      this.#emit(plan.commandId, "completed", "");
    }
  }

  #finishFreePlay(reason) {
    const plan = this.#plan;
    if (!plan || plan.kind !== "free_play") return;
    const shouldReport = !plan.activationReported;
    const commandId = plan.commandId;
    this.#plan = null;
    this.#segmentEndsAt = 0;
    this.command.set(ZERO);
    if (shouldReport) this.#emit(commandId, "rejected", reason);
  }

  #startSegment(startedAt) {
    const segment = this.#plan?.segments[this.#plan.index];
    if (!segment || !this.#plan) return;
    const [forward, backward, angular] = this.#getVelocityLimits();
    this.command.set(ZERO);
    if (segment.direction === "forward") this.command[0] = forward;
    if (segment.direction === "backward") this.command[0] = backward;
    if (segment.direction === "turn_left") this.command[2] = angular;
    if (segment.direction === "turn_right") this.command[2] = -angular;
    this.#segmentEndsAt = startedAt + segment.duration_ms;
    if (this.#plan.status !== "running") {
      this.#plan.status = "running";
      this.#emit(this.#plan.commandId, "running", "");
    }
  }

  #emit(commandId, status, reason, progress = "", result = undefined) {
    const update = { command_id: commandId, status, reason };
    if (progress) update.progress = progress;
    if (result) update.result = result;
    this.#statusListener(update);
  }
}
