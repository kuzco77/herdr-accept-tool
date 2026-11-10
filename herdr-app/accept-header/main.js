// The shipped pane header plus herdr-accept-tool: after the name it shows the
// herdr-core terminal address and ⚡ (answer every dialog) or 🔐 (permissions
// only). Clicking the marker cycles off → ⚡ → 🔐 → off. Key commands from
// keys.json (accept-header.toggle, .toggle-permissions, .disarm-all) reach every
// copy. toggle and toggle-permissions act in the copy of the focused pane only;
// disarm-all acts in one copy per tab: the focused pane's, else the zoomed pane's,
// else the first pane's, so it works under zoom and without a focused pane. Props: { pane, terminal }.

import { View, div, svg, image } from "gpui-kit";
import { h_flex } from "gpui-base";
import { focused, hc, home, nextCommand, notify, panes, props, readTextFile, run, terminals, theme } from "herdr";
import {
  MARKERS,
  MODE_ALL,
  currentMode,
  hcErrorMessage,
  isDisarmAllActor,
  isRemote,
  labelArgs,
  modeOf,
  nextMode,
  supervisorWarning,
} from "./state.js";

const STATE = "/.local/state/herdr-accept-tool/";
const HEARTBEAT = STATE + "supervisor.heartbeat";
const CORE_OK = STATE + "core.ok";

function icon(p, size, color) {
  if (!p?.icon) return null;
  return p.tint ? svg(p.icon).size(size).flex_none().text_color(color) : image(p.icon).w(size).h(size).flex_none();
}

function folder(cwd) {
  if (!cwd) return "";
  const h = home();
  return cwd === h ? "~" : cwd.startsWith(h + "/") ? "~" + cwd.slice(h.length) : cwd;
}

function nowSeconds() {
  return Date.now() / 1000;
}

export default class AcceptHeader extends View {
  init(_props, cx) {
    this.hovered = false;
    this.assumed = null;
    this.queue = Promise.resolve();
    cx.spawn(async (cx) => {
      for (;;) {
        const command = await nextCommand();
        if (this.handles(command)) {
          await this.enqueue(() => (command === "disarm-all" ? this.disarmAll() : this.apply(command)));
        }
        cx.notify();
      }
    });
  }

  handles(command) {
    const mine = props()?.pane;
    if (!mine) return false;
    if (command === "disarm-all") return isDisarmAllActor(mine, panes(), focused());
    return focused()?.pane === mine;
  }

  /** Runs `task` after the earlier ones of this copy. Never rejects: a failure becomes a toast. */
  enqueue(task) {
    const next = this.queue.then(async () => {
      try {
        await task();
      } catch (e) {
        notify({ title: "auto-accept failed", body: String(e?.message ?? e).slice(0, 200), level: "error" });
      }
    });
    this.queue = next.catch(() => {});
    return this.queue;
  }

  me() {
    return panes().find((p) => p.pane === props()?.pane);
  }

  terminal() {
    const address = props()?.terminal;
    return address ? terminals().find((t) => t.address === address) ?? null : null;
  }

  async apply(command) {
    const address = props()?.terminal;
    if (!address) return;
    const assumed = this.assumed?.address === address ? this.assumed : null;
    const current = currentMode(modeOf(this.terminal()), assumed, nowSeconds());
    const mode = nextMode(current, command);
    if (mode === current) return;
    if (mode && isRemote(address)) {
      notify({ title: "auto-accept failed", body: `${address} · remote terminals are not supported`, level: "error" });
      return;
    }
    const result = await hc(labelArgs(address, mode, nowSeconds()));
    if (result?.code !== 0) {
      notify({ title: "auto-accept failed", body: hcErrorMessage(result), level: "error" });
      return;
    }
    this.assumed = { mode, at: nowSeconds(), address };
    if (!mode) {
      notify({ title: "auto-accept OFF", body: address, level: "info" });
      return;
    }
    const [beat, coreOk] = await Promise.all(
      [HEARTBEAT, CORE_OK].map((file) => readTextFile(home() + file).catch(() => null)),
    );
    const warning = supervisorWarning(beat, coreOk, nowSeconds());
    const what = mode === MODE_ALL ? "all dialogs" : "permissions only";
    notify({
      title: `auto-accept ${MARKERS[mode]} ON`,
      body: warning ? `${address} · ${what} · ${warning}` : `${address} · ${what}`,
      level: warning ? "warning" : "success",
    });
  }

  async disarmAll() {
    const armed = terminals().filter((t) => modeOf(t));
    const failed = [];
    await Promise.all(
      armed.map(async (t) => {
        try {
          const result = await hc(labelArgs(t.address, null, 0));
          if (result?.code !== 0) failed.push(t.address);
        } catch {
          failed.push(t.address);
        }
      }),
    );
    if (failed.length > 0) {
      notify({
        title: "auto-accept still ON",
        body: `could not disarm ${failed.length} of ${armed.length}: ${failed.join(", ")}`,
        level: "error",
      });
      return;
    }
    notify({ title: "auto-accept OFF everywhere", body: `${armed.length} terminal(s)`, level: "info" });
  }

  button(t, id, iconName, command, args) {
    return div()
      .id(id)
      .p(3)
      .rounded(4)
      .text_color(t.dim)
      .hover((s) => s.bg(t.hover).text_color(t.foreground))
      .on_click((_e, cx) => {
        cx.stop_propagation();
        run(command, args);
      })
      .child(svg(`mods/pane/${iconName}.svg`).size(14));
  }

  marker(t, pane, mode) {
    return div()
      .id(`ph-a-${pane}`)
      .flex_none()
      .px(3)
      .rounded(4)
      .text_color(t.dim)
      .hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => {
        cx.stop_propagation();
        cx.spawn(async (cx) => {
          await this.enqueue(() => this.apply("cycle"));
          cx.notify();
        });
      })
      .child(mode ? MARKERS[mode] : "○");
  }

  render(cx) {
    const t = theme();
    const p = this.me();
    if (!p) return div();
    const name = ((p.program?.agent || p.program?.shell) && p.program.name) || p.title || p.program?.name || "shell";
    const pic = icon(p.program, 14, t.dim);
    const st = p.status;
    const pane = p.pane;
    const address = props()?.terminal;
    const mode = modeOf(this.terminal());
    return h_flex()
      .id(`pane-head-${pane}`)
      .size_full()
      .px(10)
      .gap(8)
      .items_center()
      .bg(t.background)
      .border_b(1)
      .border_color(t.border)
      .text_size(12)
      .on_hover((hovered, cx) => { this.hovered = hovered; cx.notify(); })
      .on_click(() => run("pane.focus", { pane }))
      .when(Boolean(pic), (el) => el.child(pic))
      .child(div().flex_none().truncate().max_w(260).font_medium().text_color(t.foreground).child(name))
      .when(Boolean(address), (el) => el.child(div().flex_none().text_color(t.dim).child(`· ${address}`)))
      .when(Boolean(address) && (Boolean(mode) || this.hovered), (el) => el.child(this.marker(t, pane, mode)))
      .child(div().flex_1().truncate().text_color(t.dim).child(folder(p.cwd)))
      .when(st === "working", (el) => el.child(svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900)))
      .when(st === "blocked", (el) => el.child(div().flex_none().px(6).h(18).flex().items_center().rounded(5).bg(t.blocked + "26").text_size(10.5).font_semibold().text_color(t.blocked).child("Needs you")))
      .when(st === "done", (el) => el.child(div().size(7).flex_none().rounded(4).bg(t.done)))
      .when(this.hovered, (el) => el
        .child(this.button(t, `ph-r-${pane}`, "split-right", "pane.split", { direction: "right", pane }))
        .child(this.button(t, `ph-d-${pane}`, "split-down", "pane.split", { direction: "down", pane }))
        .child(this.button(t, `ph-z-${pane}`, p.zoomed ? "unzoom" : "zoom", "pane.zoom", { pane }))
        .child(this.button(t, `ph-x-${pane}`, "close", "pane.close", { pane })));
  }
}
