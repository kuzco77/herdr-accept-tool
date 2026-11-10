import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MARKERS,
  currentMode,
  hcErrorMessage,
  heartbeatStale,
  isDisarmAllActor,
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

test("hcErrorMessage prefers the hc JSON error message", () => {
  const stdout = JSON.stringify({ error: { kind: "not_found", message: 'no terminal "t9"' } });
  assert.equal(hcErrorMessage({ code: 3, stdout, stderr: "ignored" }), 'no terminal "t9"');
});

test("hcErrorMessage falls back to trimmed stderr, then stdout, then the exit code", () => {
  assert.equal(hcErrorMessage({ code: 1, stdout: "", stderr: "  boom\n" }), "boom");
  assert.equal(hcErrorMessage({ code: 1, stdout: " plain out \n", stderr: "" }), "plain out");
  assert.equal(hcErrorMessage({ code: 1, stdout: "{not json", stderr: "bad" }), "bad");
  assert.equal(hcErrorMessage({ code: 1, stdout: '{"error":{}}', stderr: "" }), '{"error":{}}');
  assert.equal(hcErrorMessage({ code: 7, stdout: "", stderr: "" }), "hc exited with code 7");
  assert.equal(hcErrorMessage(null), "hc gave no result");
});

test("hcErrorMessage caps the message at 200 characters", () => {
  assert.equal(hcErrorMessage({ code: 1, stdout: "", stderr: "x".repeat(500) }).length, 200);
  const stdout = JSON.stringify({ error: { message: "y".repeat(500) } });
  assert.equal(hcErrorMessage({ code: 1, stdout, stderr: "" }).length, 200);
});

const PANES = [
  { pane: "p1", tab: "tabA" },
  { pane: "p2", tab: "tabB" },
  { pane: "p3", tab: "tabB" },
];

test("isDisarmAllActor picks the first pane of the current tab only", () => {
  assert.equal(isDisarmAllActor("p2", PANES, "tabB"), true);
  assert.equal(isDisarmAllActor("p3", PANES, "tabB"), false);
  assert.equal(isDisarmAllActor("p1", PANES, "tabB"), false);
  assert.equal(isDisarmAllActor("p1", PANES, "tabA"), true);
});

test("isDisarmAllActor is false without a pane, a tab or a matching pane", () => {
  assert.equal(isDisarmAllActor(undefined, PANES, "tabB"), false);
  assert.equal(isDisarmAllActor("p2", PANES, null), false);
  assert.equal(isDisarmAllActor("p2", PANES, "tabZ"), false);
  assert.equal(isDisarmAllActor("p2", [], "tabB"), false);
});

test("currentMode uses the labels when nothing was written", () => {
  assert.equal(currentMode("all", null, 100), "all");
  assert.equal(currentMode(null, null, 100), null);
});

test("currentMode prefers a fresh assumed mode while labels disagree", () => {
  assert.equal(currentMode(null, { mode: "all", at: 100 }, 101), "all");
  assert.equal(currentMode("all", { mode: null, at: 100 }, 101), null);
  assert.equal(currentMode("permissions", { mode: "all", at: 100 }, 101), "all");
});

test("currentMode returns to the labels once they match or the assumption is old", () => {
  assert.equal(currentMode("all", { mode: "all", at: 100 }, 101), "all");
  assert.equal(currentMode(null, { mode: "all", at: 100 }, 106), null);
  assert.equal(currentMode(null, { mode: "all", at: 100 }, 105), "all");
});
