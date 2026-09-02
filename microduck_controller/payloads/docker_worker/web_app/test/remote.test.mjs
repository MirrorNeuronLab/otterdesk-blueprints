import assert from "node:assert/strict";
import test from "node:test";

import { isMcpControlMode } from "../src/bridge/controlMode.js";
import { bridgeSocketPath } from "../src/bridge/proxyPath.js";
import { BallNavigator } from "../src/game/controls/ball-navigation.js";
import { RemoteSource } from "../src/game/controls/remote.js";

function navigationState({
  x = 0,
  y = 0,
  yaw = 0,
  speed = 0,
  mode = "walk",
  locomotion = "legs",
  ballActive = true,
  ballX = 1,
  ballY = 0,
  ready = true,
} = {}) {
  return {
    ready,
    duck: { x, y, yaw, speed, mode, locomotion },
    ball: { active: ballActive, x: ballX, y: ballY },
  };
}

test("control mode requires the explicit control=1 query flag", () => {
  assert.equal(isMcpControlMode(""), false);
  assert.equal(isMcpControlMode("?control"), false);
  assert.equal(isMcpControlMode("?control=0"), false);
  assert.equal(isMcpControlMode("?control=1"), true);
});

test("bridge WebSocket uses the job-scoped proxy only when embedded by OtterDesk", () => {
  assert.equal(bridgeSocketPath("/"), "/bridge");
  assert.equal(bridgeSocketPath("/job-ui-proxy/job_mc-example/8080/"), "/job-ui-proxy/job_mc-example/8080/ws/bridge");
});

test("remote source sequences bounded segments and zeros at every terminal boundary", () => {
  let now = 0;
  const updates = [];
  const source = new RemoteSource({
    clock: () => now,
    getVelocityLimits: () => [1.5, -0.75, 2.25],
  });
  source.setStatusListener((update) => updates.push(update));

  assert.equal(source.startPlan("command-1", [
    { direction: "forward", duration_ms: 100 },
    { direction: "turn_right", duration_ms: 200 },
  ]), true);
  assert.deepEqual([...source.command], [0, 0, 0]);

  source.poll();
  assert.deepEqual([...source.command], [1.5, 0, 0]);
  now = 100;
  source.poll();
  assert.deepEqual([...source.command], [0, 0, -2.25]);
  now = 300;
  source.poll();

  assert.equal(source.isActive(), false);
  assert.deepEqual([...source.command], [0, 0, 0]);
  assert.deepEqual(updates.map((item) => item.status), ["accepted", "running", "completed"]);
});

test("remote stop preempts active movement and preserves a zero command", () => {
  const updates = [];
  const source = new RemoteSource({ getVelocityLimits: () => [1, -1, 1] });
  source.setStatusListener((update) => updates.push(update));
  source.startPlan("command-2", [{ direction: "backward", duration_ms: 100 }]);
  source.poll();
  source.stop();

  assert.equal(source.isActive(), false);
  assert.deepEqual([...source.command], [0, 0, 0]);
  assert.equal(updates.at(-1).status, "cancelled");
});

test("ball navigator turns left or right toward the observed bearing", () => {
  const left = new BallNavigator("left", 0).step(
    navigationState({ ballX: 0, ballY: 1 }),
    [0.25, -0.2, 1],
    0,
  );
  const right = new BallNavigator("right", 0).step(
    navigationState({ ballX: 0, ballY: -1 }),
    [0.25, -0.2, 1],
    0,
  );

  assert.equal(left.progress, "turning");
  assert.deepEqual(left.command, [0, 0, 1]);
  assert.deepEqual(right.command, [0, 0, -1]);
});

test("ball navigator uses existing legs and rollers forward limits once aligned", () => {
  const state = navigationState();
  const legs = new BallNavigator("legs", 0).step(state, [0.25, -0.2, 1], 0);
  const rollers = new BallNavigator("rollers", 0).step(
    navigationState({ locomotion: "rollers" }),
    [0.6, -0.5, 0.3],
    0,
  );

  assert.equal(legs.progress, "approaching");
  assert.deepEqual(legs.command, [0.25, 0, 0]);
  assert.deepEqual(rollers.command, [0.6, 0, 0]);
});

test("ball navigator retargets a moving ball and reports only phase changes", () => {
  let now = 0;
  let state = navigationState();
  const updates = [];
  const source = new RemoteSource({
    clock: () => now,
    getVelocityLimits: () => [0.25, -0.2, 1],
    getNavigationState: () => state,
  });
  source.setStatusListener((update) => updates.push(update));
  source.startFindBall("moving-ball");
  source.pollNavigation();
  now = 20;
  source.pollNavigation();
  state = navigationState({ ballX: 0, ballY: 1 });
  now = 40;
  source.pollNavigation();

  assert.deepEqual([...source.command], [0, 0, 1]);
  assert.deepEqual(
    updates.map((update) => [update.status, update.progress ?? ""]),
    [["accepted", ""], ["running", "approaching"], ["running", "turning"]],
  );
});

test("ball navigator settles at the target and records a successful result", () => {
  const navigator = new BallNavigator("settle", 0);
  const state = navigationState({ ballX: 0.2, speed: 0.04, locomotion: "rollers" });

  const settling = navigator.step(state, [0.6, -0.5, 0.3], 0);
  const notYetSettled = navigator.step(state, [0.6, -0.5, 0.3], 249);
  const complete = navigator.step(state, [0.6, -0.5, 0.3], 250);

  assert.equal(settling.progress, "settling");
  assert.equal(notYetSettled.status, "running");
  assert.equal(complete.status, "completed");
  assert.deepEqual(complete.command, [0, 0, 0]);
  assert.equal(complete.result.schema_version, "mn.microduck.navigation_result.v1");
  assert.equal(complete.result.outcome, "found_ball");
  assert.equal(complete.result.final_distance_m, 0.2);
  assert.equal(complete.result.final_speed_mps, 0.04);
  assert.equal(complete.result.locomotion, "rollers");
});

test("ball navigator rejects missing ball, unavailable mode, timeout, and travel exhaustion", () => {
  const missing = new BallNavigator("missing", 0).step(
    navigationState({ ballActive: false, ballX: null, ballY: null }),
    [0.25, -0.2, 1],
    0,
  );
  const unavailable = new BallNavigator("busy", 0).step(
    navigationState({ mode: "kickL" }),
    [0.25, -0.2, 1],
    0,
  );
  const timeout = new BallNavigator("timeout", 0).step(
    navigationState(),
    [0.25, -0.2, 1],
    30_000,
  );
  const travelNavigator = new BallNavigator("travel", 0);
  travelNavigator.step(navigationState({ ballX: 20 }), [0.25, -0.2, 1], 0);
  const travel = travelNavigator.step(
    navigationState({ x: 5.01, ballX: 20 }),
    [0.25, -0.2, 1],
    20,
  );

  assert.equal(missing.reason, "ball_not_active");
  assert.equal(unavailable.reason, "navigation_mode_unavailable");
  assert.equal(timeout.reason, "navigation_timeout");
  assert.equal(travel.reason, "navigation_travel_limit");
  assert.deepEqual(travel.command, [0, 0, 0]);
});

test("stop cancels ball navigation immediately and leaves remote input zeroed", () => {
  let now = 0;
  const updates = [];
  const source = new RemoteSource({
    clock: () => now,
    getVelocityLimits: () => [0.25, -0.2, 1],
    getNavigationState: () => navigationState(),
  });
  source.setStatusListener((update) => updates.push(update));
  source.startFindBall("stop-navigation");
  source.pollNavigation();
  now = 20;
  source.stop("stopped_by_operator");

  assert.equal(source.isActive(), false);
  assert.deepEqual([...source.command], [0, 0, 0]);
  assert.equal(updates.at(-1).status, "cancelled");
  assert.equal(updates.at(-1).result.outcome, "cancelled");
});

test("free play rejects a missing ball and non-legged locomotion before moving", () => {
  const updates = [];
  let state = navigationState({ ballActive: false, ballX: null, ballY: null });
  const source = new RemoteSource({
    getVelocityLimits: () => [0.25, -0.2, 1],
    getNavigationState: () => state,
  });
  source.setStatusListener((update) => updates.push(update));

  assert.equal(source.startFreePlay("missing-ball"), false);
  assert.equal(updates.at(-1).reason, "ball_not_active");
  state = navigationState({ locomotion: "rollers" });
  assert.equal(source.startFreePlay("rollers"), false);
  assert.equal(updates.at(-1).reason, "kicks_require_legs");
  assert.deepEqual([...source.command], [0, 0, 0]);
});

test("free play finds, alternates kicks, reacquires the moved ball, and reports start once", () => {
  let now = 0;
  let state = navigationState({ ballX: 0.2, speed: 0 });
  const updates = [];
  const kicks = [];
  const source = new RemoteSource({
    clock: () => now,
    getVelocityLimits: () => [0.25, -0.2, 1],
    getNavigationState: () => state,
    performBallAction: (action) => {
      kicks.push(action);
      state = navigationState({ ballX: 0.2, speed: 0, mode: action === "kick_left" ? "kickL" : "kickR", ready: false });
      return { accepted: true };
    },
  });
  source.setStatusListener((update) => updates.push(update));

  assert.equal(source.startFreePlay("play"), true);
  source.pollNavigation();
  now = 250;
  source.pollNavigation();
  assert.deepEqual(kicks, ["kick_left"]);
  assert.equal(source.isActive(), true);
  assert.equal(source.status.kind, "free_play");
  assert.deepEqual(
    updates.map((update) => [update.status, update.progress ?? ""]),
    [["accepted", ""], ["running", "settling"], ["completed", ""]],
  );

  state = navigationState({ ballX: 0, ballY: 1, speed: 0 });
  now = 1_000;
  source.pollNavigation();
  assert.deepEqual([...source.command], [0, 0, 1]);
  state = navigationState({ ballX: 0.2, speed: 0 });
  now = 1_020;
  source.pollNavigation();
  now = 1_270;
  source.pollNavigation();

  assert.deepEqual(kicks, ["kick_left", "kick_right"]);
  assert.equal(updates.filter((update) => update.status === "completed").length, 1);
  assert.equal(source.isActive(), true);
});

test("stop ends active free play immediately without reopening its completed start receipt", () => {
  let now = 0;
  const updates = [];
  const source = new RemoteSource({
    clock: () => now,
    getVelocityLimits: () => [0.25, -0.2, 1],
    getNavigationState: () => navigationState({ ballX: 0.2, speed: 0 }),
    performBallAction: () => ({ accepted: true }),
  });
  source.setStatusListener((update) => updates.push(update));
  source.startFreePlay("play-stop");
  source.pollNavigation();
  now = 250;
  source.pollNavigation();

  source.stop("stopped_by_operator");

  assert.equal(source.isActive(), false);
  assert.deepEqual([...source.command], [0, 0, 0]);
  assert.equal(updates.at(-1).status, "completed");
});
