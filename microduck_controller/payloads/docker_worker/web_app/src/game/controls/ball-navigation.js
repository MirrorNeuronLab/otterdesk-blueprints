const TURN_ENTER_RADIANS = 0.30;
const TURN_EXIT_RADIANS = 0.15;
const TARGET_DISTANCE_METERS = 0.22;
const SETTLED_SPEED_MPS = 0.05;
const SETTLE_DURATION_MS = 250;
const TIME_LIMIT_MS = 30_000;
const TRAVEL_LIMIT_METERS = 5;

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function round(value, places = 4) {
  if (!Number.isFinite(value)) return null;
  const scale = 10 ** places;
  return Math.round(value * scale) / scale;
}

export function normalizeAngle(value) {
  return Math.atan2(Math.sin(value), Math.cos(value));
}

export class BallNavigator {
  #startedAt;
  #phase = "";
  #settledSince = null;
  #lastPosition = null;
  #pathLength = 0;
  #forwardTicks = 0;
  #turnTicks = 0;
  #corrections = 0;
  #terminal = null;

  constructor(_commandId, startedAt) {
    this.#startedAt = startedAt;
  }

  get phase() {
    return this.#phase;
  }

  step(snapshot, velocityLimits, now) {
    if (this.#terminal) return this.#terminal;

    const observation = this.#observe(snapshot);
    this.#recordTravel(observation);
    const elapsedMs = Math.max(0, now - this.#startedAt);

    if (!observation.ballActive) {
      return this.#finish("rejected", "ball_not_active", "ball_not_active", observation, elapsedMs);
    }
    if (
      !observation.ready ||
      observation.mode !== "walk" ||
      !["legs", "rollers"].includes(observation.locomotion) ||
      observation.duckX === null ||
      observation.duckY === null ||
      observation.duckYaw === null ||
      observation.ballX === null ||
      observation.ballY === null
    ) {
      return this.#finish(
        "rejected",
        "navigation_mode_unavailable",
        "navigation_mode_unavailable",
        observation,
        elapsedMs,
      );
    }
    if (elapsedMs >= TIME_LIMIT_MS) {
      return this.#finish("rejected", "navigation_timeout", "timeout", observation, elapsedMs);
    }
    if (this.#pathLength >= TRAVEL_LIMIT_METERS) {
      return this.#finish(
        "rejected",
        "navigation_travel_limit",
        "travel_exhausted",
        observation,
        elapsedMs,
      );
    }

    const distance = Math.hypot(
      observation.ballX - observation.duckX,
      observation.ballY - observation.duckY,
    );
    const targetYaw = Math.atan2(
      observation.ballY - observation.duckY,
      observation.ballX - observation.duckX,
    );
    const angularError = normalizeAngle(targetYaw - observation.duckYaw);

    if (distance <= TARGET_DISTANCE_METERS) {
      const changed = this.#setPhase("settling");
      if (observation.speed !== null && observation.speed <= SETTLED_SPEED_MPS) {
        if (this.#settledSince === null) this.#settledSince = now;
        if (now - this.#settledSince >= SETTLE_DURATION_MS) {
          return this.#finish("completed", "", "found_ball", observation, elapsedMs, distance);
        }
      } else {
        this.#settledSince = null;
      }
      return this.#running([0, 0, 0], changed);
    }

    this.#settledSince = null;
    let nextPhase = this.#phase;
    if (!nextPhase || nextPhase === "settling") {
      nextPhase = Math.abs(angularError) <= TURN_EXIT_RADIANS ? "approaching" : "turning";
    } else if (nextPhase === "turning" && Math.abs(angularError) <= TURN_EXIT_RADIANS) {
      nextPhase = "approaching";
    } else if (nextPhase === "approaching" && Math.abs(angularError) > TURN_ENTER_RADIANS) {
      nextPhase = "turning";
      this.#corrections += 1;
    }

    const changed = this.#setPhase(nextPhase);
    const [forward, , angular] = velocityLimits;
    if (nextPhase === "turning") {
      this.#turnTicks += 1;
      return this.#running([0, 0, angularError >= 0 ? angular : -angular], changed);
    }

    this.#forwardTicks += 1;
    return this.#running([forward, 0, 0], changed);
  }

  cancel(snapshot, now, reason = "stopped_by_operator") {
    if (this.#terminal) return this.#terminal;
    const observation = this.#observe(snapshot);
    this.#recordTravel(observation);
    return this.#finish(
      "cancelled",
      reason,
      "cancelled",
      observation,
      Math.max(0, now - this.#startedAt),
    );
  }

  #observe(snapshot) {
    const duck = snapshot?.duck ?? {};
    const ball = snapshot?.ball ?? {};
    return {
      ready: snapshot?.ready === true,
      duckX: finiteNumber(duck.x),
      duckY: finiteNumber(duck.y),
      duckYaw: finiteNumber(duck.yaw),
      speed: finiteNumber(duck.speed),
      mode: typeof duck.mode === "string" ? duck.mode : "",
      locomotion: typeof duck.locomotion === "string" ? duck.locomotion : "",
      ballActive: ball.active === true,
      ballX: finiteNumber(ball.x),
      ballY: finiteNumber(ball.y),
    };
  }

  #recordTravel(observation) {
    if (observation.duckX === null || observation.duckY === null) return;
    const current = { x: observation.duckX, y: observation.duckY };
    if (this.#lastPosition) {
      this.#pathLength += Math.hypot(
        current.x - this.#lastPosition.x,
        current.y - this.#lastPosition.y,
      );
    }
    this.#lastPosition = current;
  }

  #setPhase(phase) {
    if (phase === this.#phase) return false;
    if (this.#phase === "settling" && phase !== "settling") this.#corrections += 1;
    this.#phase = phase;
    return true;
  }

  #running(command, phaseChanged) {
    return {
      status: "running",
      command,
      progress: phaseChanged ? this.#phase : "",
    };
  }

  #finish(status, reason, outcome, observation, elapsedMs, measuredDistance = null) {
    const finalDistance = measuredDistance ?? (
      observation.duckX !== null &&
      observation.duckY !== null &&
      observation.ballX !== null &&
      observation.ballY !== null
        ? Math.hypot(
            observation.ballX - observation.duckX,
            observation.ballY - observation.duckY,
          )
        : null
    );
    this.#terminal = {
      status,
      reason,
      command: [0, 0, 0],
      progress: "",
      result: {
        schema_version: "mn.microduck.navigation_result.v1",
        outcome,
        elapsed_ms: Math.round(elapsedMs),
        path_length_m: round(this.#pathLength),
        forward_ticks: this.#forwardTicks,
        turn_ticks: this.#turnTicks,
        corrections: this.#corrections,
        final_distance_m: round(finalDistance),
        final_duck_position: {
          x: round(observation.duckX),
          y: round(observation.duckY),
          yaw: round(observation.duckYaw),
        },
        final_ball_position: {
          x: round(observation.ballX),
          y: round(observation.ballY),
        },
        final_speed_mps: round(observation.speed),
        locomotion: observation.locomotion,
      },
    };
    return this.#terminal;
  }
}

export const BALL_NAVIGATION_LIMITS = Object.freeze({
  turn_enter_radians: TURN_ENTER_RADIANS,
  turn_exit_radians: TURN_EXIT_RADIANS,
  target_distance_m: TARGET_DISTANCE_METERS,
  settled_speed_mps: SETTLED_SPEED_MPS,
  settle_duration_ms: SETTLE_DURATION_MS,
  timeout_ms: TIME_LIMIT_MS,
  travel_limit_m: TRAVEL_LIMIT_METERS,
});
