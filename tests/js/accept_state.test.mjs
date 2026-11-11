import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MARKERS,
  currentMode,
  hcErrorMessage,
  heartbeatStale,
  isDisarmAllActor,
  labelArgs,
  machineOf,
  modeOf,
  nextMode,
  remoteStateReadArgs,
  supervisorWarning,
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
  { pane: "p1", tab: "tabA", zoomed: false },
  { pane: "p2", tab: "tabB", zoomed: false },
  { pane: "p3", tab: "tabB", zoomed: false },
  { pane: "p4", tab: "tabB", zoomed: false },
];
const withZoom = (zoomedPane) => PANES.map((p) => ({ ...p, zoomed: p.pane === zoomedPane }));

test("isDisarmAllActor: the focused pane of the current tab wins", () => {
  const focus = { pane: "p3", tab: "tabB" };
  assert.equal(isDisarmAllActor("p3", PANES, focus), true);
  assert.equal(isDisarmAllActor("p2", PANES, focus), false);
  assert.equal(isDisarmAllActor("p4", PANES, focus), false);
});

test("isDisarmAllActor: the focused pane wins over a zoomed other pane", () => {
  const focus = { pane: "p3", tab: "tabB" };
  assert.equal(isDisarmAllActor("p3", withZoom("p4"), focus), true);
  assert.equal(isDisarmAllActor("p4", withZoom("p4"), focus), false);
});

test("isDisarmAllActor: the zoomed pane wins when nothing in the tab is focused", () => {
  const focus = { pane: null, tab: "tabB" };
  assert.equal(isDisarmAllActor("p4", withZoom("p4"), focus), true);
  assert.equal(isDisarmAllActor("p2", withZoom("p4"), focus), false);
  assert.equal(isDisarmAllActor("p3", withZoom("p4"), focus), false);
});

test("isDisarmAllActor: the first pane of the tab otherwise", () => {
  const focus = { pane: null, tab: "tabB" };
  assert.equal(isDisarmAllActor("p2", PANES, focus), true);
  assert.equal(isDisarmAllActor("p3", PANES, focus), false);
  assert.equal(isDisarmAllActor("p4", PANES, focus), false);
});

test("isDisarmAllActor: a focused pane outside the current tab is ignored", () => {
  const focus = { pane: "p1", tab: "tabB" };
  assert.equal(isDisarmAllActor("p1", PANES, focus), false);
  assert.equal(isDisarmAllActor("p2", PANES, focus), true);
});

test("isDisarmAllActor: a copy in another tab never acts", () => {
  const focused = { pane: "p3", tab: "tabB" };
  const unfocused = { pane: null, tab: "tabB" };
  assert.equal(isDisarmAllActor("p1", PANES, focused), false);
  assert.equal(isDisarmAllActor("p1", withZoom("p4"), focused), false);
  assert.equal(isDisarmAllActor("p1", PANES, unfocused), false);
  assert.equal(isDisarmAllActor("p1", withZoom("p1"), unfocused), false);
});

test("isDisarmAllActor is false without a pane, a tab or a matching pane", () => {
  assert.equal(isDisarmAllActor(undefined, PANES, { pane: "p3", tab: "tabB" }), false);
  assert.equal(isDisarmAllActor("p2", PANES, { pane: null, tab: null }), false);
  assert.equal(isDisarmAllActor("p2", PANES, undefined), false);
  assert.equal(isDisarmAllActor("p2", PANES, { pane: null, tab: "tabZ" }), false);
  assert.equal(isDisarmAllActor("p2", [], { pane: null, tab: "tabB" }), false);
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

test("machineOf names the machine of a remote address, null for this computer", () => {
  assert.equal(machineOf("mac-mini-tvf/t1"), "mac-mini-tvf");
  assert.equal(machineOf("t17"), null);
  assert.equal(machineOf(undefined), null);
  assert.equal(machineOf(""), null);
  assert.equal(machineOf("/t1"), null);
});

test("remoteStateReadArgs reads a supervisor state file from that machine's home", () => {
  assert.deepEqual(remoteStateReadArgs("mac-mini-tvf", "core.ok"), [
    "file",
    "read",
    "--on",
    "mac-mini-tvf",
    ".local/state/herdr-accept-tool/core.ok",
  ]);
});

test("no warning while the heartbeat and core.ok are fresh", () => {
  assert.equal(supervisorWarning("1000", "1000", 1010), null);
  assert.equal(supervisorWarning("1000", "950", 1010), null);
});

test("a stale or missing heartbeat means the supervisor is not running", () => {
  assert.equal(supervisorWarning("900", "1000", 1010), "supervisor not running");
  assert.equal(supervisorWarning(null, "1000", 1010), "supervisor not running");
  assert.equal(supervisorWarning("", "1000", 1010), "supervisor not running");
});

test("a fresh heartbeat with core.ok missing or older than 90 s means herdr-core is unreachable", () => {
  assert.equal(supervisorWarning("1000", null, 1010), "supervisor cannot reach herdr-core");
  assert.equal(supervisorWarning("1000", "garbage", 1010), "supervisor cannot reach herdr-core");
  assert.equal(supervisorWarning("1000", "900", 1000), "supervisor cannot reach herdr-core");
  assert.equal(supervisorWarning("1000", "910", 1000), null);
});

test("a dead supervisor is reported before an unreachable core", () => {
  assert.equal(supervisorWarning("100", null, 1000), "supervisor not running");
});
