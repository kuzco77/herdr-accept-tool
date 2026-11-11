// Arming rules for the accept-header mod. No imports, so Node can test it.
// A herdr-core terminal is armed by two labels: accept=all|permissions and
// accept.at=<epoch seconds>. The supervisor applies the TTL.

export const MODE_ALL = "all";
export const MODE_PERMISSIONS = "permissions";
export const MARKERS = { [MODE_ALL]: "⚡", [MODE_PERMISSIONS]: "🔐" };

/** The mode after `command`: null is off. Same switching rules as the TUI plugin. */
export function nextMode(current, command) {
  switch (command) {
    case "toggle":
      return current === MODE_ALL ? null : MODE_ALL;
    case "toggle-permissions":
      return current === MODE_PERMISSIONS ? null : MODE_PERMISSIONS;
    case "cycle":
      if (current === null) return MODE_ALL;
      return current === MODE_ALL ? MODE_PERMISSIONS : null;
    default:
      return current;
  }
}

/** `hc` arguments that put `address` into `mode` (null: off). */
export function labelArgs(address, mode, nowSeconds) {
  if (!mode) return ["label", address, "accept=", "accept.at="];
  return ["label", address, `accept=${mode}`, `accept.at=${Math.floor(nowSeconds)}`];
}

/** A terminal's mode from its labels, or null when not armed. */
export function modeOf(terminal) {
  const mode = terminal?.labels?.accept;
  return mode === MODE_ALL || mode === MODE_PERMISSIONS ? mode : null;
}

/** True when the supervisor heartbeat (epoch seconds as text) is missing or old. */
export function heartbeatStale(text, nowSeconds, maxAge = 15) {
  const beat = Number.parseFloat(text ?? "");
  return !Number.isFinite(beat) || nowSeconds - beat > maxAge;
}

const CORE_OK_MAX_AGE = 90;

/**
 * Why answering may not work, or null. `heartbeat` and `coreOk` are the texts of the two state
 * files (epoch seconds). core.ok is older than the supervisor's longest backoff (60 s) plus a margin
 * when the supervisor cannot reach herdr-core.
 */
export function supervisorWarning(heartbeat, coreOk, nowSeconds) {
  if (heartbeatStale(heartbeat, nowSeconds)) return "supervisor not running";
  if (heartbeatStale(coreOk, nowSeconds, CORE_OK_MAX_AGE)) return "supervisor cannot reach herdr-core";
  return null;
}

/**
 * The machine of a remote herdr-core address (`machine/tN`), or null for this computer.
 * A remote terminal is answered by the supervisor on its own machine, never by this one.
 */
export function machineOf(address) {
  if (typeof address !== "string") return null;
  const slash = address.indexOf("/");
  return slash > 0 ? address.slice(0, slash) : null;
}

/** `hc` arguments that print a supervisor state file on `machine`; relative paths start at its home. */
export function remoteStateReadArgs(machine, file) {
  return ["file", "read", "--on", machine, `.local/state/herdr-accept-tool/${file}`];
}

const MESSAGE_CAP = 200;

/** A short, user-facing reason for a failed `hc` call: the JSON error message, else the raw output. */
export function hcErrorMessage(result) {
  if (!result) return "hc gave no result";
  const stdout = (result.stdout ?? "").trim();
  const stderr = (result.stderr ?? "").trim();
  let message = "";
  try {
    const parsed = JSON.parse(stdout)?.error?.message;
    if (typeof parsed === "string") message = parsed.trim();
  } catch {
    // stdout is not JSON: use the raw text below.
  }
  return (message || stderr || stdout || `hc exited with code ${result.code}`).slice(0, MESSAGE_CAP);
}

/**
 * True for the one copy per tab that handles disarm-all. `focus` is {pane, tab} from `focused()`.
 * Actor: the focused pane when it belongs to the current tab, else the tab's zoomed pane
 * (the only shown header under zoom), else the tab's first pane in `panes` order.
 */
export function isDisarmAllActor(myPane, panes, focus) {
  const tab = focus?.tab;
  if (!myPane || !tab) return false;
  const inTab = panes.filter((p) => p.tab === tab);
  const focusedHere = focus.pane ? inTab.find((p) => p.pane === focus.pane) : undefined;
  const actor = focusedHere ?? inTab.find((p) => p.zoomed) ?? inTab[0];
  return actor?.pane === myPane;
}

/**
 * The mode to switch from. `assumed` is {mode, at} from this copy's last write: it wins
 * while the labels still disagree and it is at most `maxAge` seconds old.
 */
export function currentMode(labelMode, assumed, nowSeconds, maxAge = 5) {
  if (assumed && assumed.mode !== labelMode && nowSeconds - assumed.at <= maxAge) return assumed.mode;
  return labelMode;
}
