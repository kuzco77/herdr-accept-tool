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
