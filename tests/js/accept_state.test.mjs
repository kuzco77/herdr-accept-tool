import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MARKERS,
  heartbeatStale,
  labelArgs,
  modeOf,
  nextMode,
} from "../../herdr-app/accept-header/state.js";

test("toggle arms all, disarms all, switches permissions to all", () => {
  assert.equal(nextMode(null, "toggle"), "all");
  assert.equal(nextMode("all", "toggle"), null);
  assert.equal(nextMode("permissions", "toggle"), "all");
});

test("toggle-permissions mirrors toggle", () => {
  assert.equal(nextMode(null, "toggle-permissions"), "permissions");
  assert.equal(nextMode("permissions", "toggle-permissions"), null);
  assert.equal(nextMode("all", "toggle-permissions"), "permissions");
});

test("a click cycles off, all, permissions, off", () => {
  assert.equal(nextMode(null, "cycle"), "all");
  assert.equal(nextMode("all", "cycle"), "permissions");
  assert.equal(nextMode("permissions", "cycle"), null);
});

test("an unknown command keeps the mode", () => {
  assert.equal(nextMode("all", "focus"), "all");
  assert.equal(nextMode(null, "focus"), null);
});

test("labelArgs arms with a whole-second timestamp and disarms both labels", () => {
  assert.deepEqual(labelArgs("t17", "all", 1000.7), ["label", "t17", "accept=all", "accept.at=1000"]);
  assert.deepEqual(labelArgs("t17", null, 1000), ["label", "t17", "accept=", "accept.at="]);
});

test("modeOf only trusts known modes", () => {
  assert.equal(modeOf({ labels: { accept: "all" } }), "all");
  assert.equal(modeOf({ labels: { accept: "permissions" } }), "permissions");
  assert.equal(modeOf({ labels: { accept: "yes" } }), null);
  assert.equal(modeOf({ labels: {} }), null);
  assert.equal(modeOf(null), null);
});

test("heartbeatStale", () => {
  assert.equal(heartbeatStale("1000", 1010), false);
  assert.equal(heartbeatStale("1000", 1016), true);
  assert.equal(heartbeatStale(null, 1000), true);
  assert.equal(heartbeatStale("", 1000), true);
});

test("markers match the TUI plugin", () => {
  assert.deepEqual(MARKERS, { all: "⚡", permissions: "🔐" });
});
