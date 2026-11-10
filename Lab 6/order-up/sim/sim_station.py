"""Keyboard stand-in for any Pi, so the game can be played and tested on a
laptop with no hardware. It speaks exactly the same MQTT as the real stations.

    python sim_station.py all        # one terminal plays all three stations
    python sim_station.py runner     # or stand in for just one missing Pi
    python sim_station.py chop --broker localhost

Keys
    Runner:  arrow keys = joystick flicks, Enter = joystick press,
             Backspace or b = top button (back), h = bottom button (home)
    Chop:    c   (Space also chops in chop mode)
    Cook:    s = stir (hold it down), p = pull off the heat (Space in cook mode)
    q quits.

On Windows, curses needs:  pip install windows-curses
"""

import argparse
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pi"))

from common import StationLink, add_broker_args, nice  # noqa: E402
from runner_menu import BACK, DOWN, HOME, LEFT, PRESS, RIGHT, UP, RunnerMenu  # noqa: E402

try:
    import curses
except ImportError:
    sys.exit("curses isn't installed. On Windows run:  pip install windows-curses")

STIR_TICKS_PER_KEY = 2
STIR_SEND_GAP = 0.2   # same 5 messages/second limit as the real Cook Pi


class Sim:
    def __init__(self, mode, args):
        self.mode = mode
        self.lock = threading.Lock()
        self.menu = RunnerMenu()
        self.log = []          # recent results, newest last
        self.stir_pending = 0
        self.stir_last_sent = 0.0
        self.links = {}
        roles = ["chop", "cook", "runner"] if mode == "all" else [mode]
        for role in roles:
            kwargs = {}
            if role == "runner":
                kwargs = {"on_state": self._on_state, "on_result": self._on_runner_result}
            elif role == "cook":
                kwargs = {"on_result": self._on_cook_result}
            self.links[role] = StationLink(role, args.broker, args.port, args.prefix,
                                           log=self._log_line, **kwargs)

    # --- MQTT callbacks (paho thread) ---

    def _on_state(self, state):
        with self.lock:
            self.menu.set_state(state)

    def _on_runner_result(self, result):
        with self.lock:
            self.menu.show_result(result, time.monotonic())
            self._remember("runner", result)

    def _on_cook_result(self, result):
        with self.lock:
            self._remember("cook", result)

    def _remember(self, who, result):
        mark = "ok" if result.get("ok") else "NO"
        self._log_line(f"{who:6s} {mark}  {result.get('msg', '')}")

    def _log_line(self, text):
        self.log.append(text)
        del self.log[:-4]

    # --- Inputs ---

    def has(self, role):
        return role in self.links

    def key(self, ch):
        runner_keys = {curses.KEY_UP: UP, curses.KEY_DOWN: DOWN, curses.KEY_LEFT: LEFT,
                       curses.KEY_RIGHT: RIGHT, 10: PRESS, 13: PRESS, curses.KEY_ENTER: PRESS,
                       curses.KEY_BACKSPACE: BACK, 127: BACK, 8: BACK, ord("b"): BACK, ord("h"): HOME}
        if self.mode == "runner":
            runner_keys[ord(" ")] = PRESS
        if self.has("runner") and ch in runner_keys:
            now = time.monotonic()
            with self.lock:
                action = self.menu.handle(runner_keys[ch], now)
            if action:
                action["id"] = self.links["runner"].new_id()
                self.links["runner"].send("runner/action", action, qos=1)
            return
        if self.has("chop") and (ch == ord("c") or (self.mode == "chop" and ch == ord(" "))):
            self.links["chop"].send("chop/event", {"type": "chop"}, qos=0)
            return
        if self.has("cook"):
            if ch == ord("s"):
                self.stir_pending += STIR_TICKS_PER_KEY
            elif ch == ord("p") or (self.mode == "cook" and ch == ord(" ")):
                link = self.links["cook"]
                link.send("cook/event", {"type": "pull", "id": link.new_id()}, qos=1)

    def flush_stir(self):
        now = time.monotonic()
        if self.stir_pending and now - self.stir_last_sent >= STIR_SEND_GAP:
            self.links["cook"].send("cook/event", {"type": "stir", "ticks": self.stir_pending}, qos=0)
            self.stir_pending = 0
            self.stir_last_sent = now

    # --- Drawing ---

    def any_link(self):
        return self.links.get("runner") or next(iter(self.links.values()))

    def draw(self, scr):
        scr.erase()
        h, w = scr.getmaxyx()
        lines = []
        link = self.any_link()
        state = link.state or {}
        problem = link.status_text()
        lines.append((f"ORDER UP! simulator [{self.mode}]   {link.broker}:{link.port}   "
                      f"{problem or 'connected'}", curses.A_BOLD))
        if state:
            t = state.get("time_left", 0)
            lines.append((f"Phase {state.get('phase')}   Score {state.get('score')}   "
                          f"Time {t // 60}:{t % 60:02d}", 0))
            tickets = "  |  ".join(
                f"#{x['id']} {x['recipe']} {x['time_left']}s{' READY' if x.get('ready') else ''}"
                for x in state.get("tickets", [])) or "(none)"
            lines.append((f"Orders:  {tickets}", 0))
            counter = "  ".join(f"[{i + 1} {nice(c) or '--'}]" for i, c in enumerate(state.get("counter", [])))
            lines.append((f"Counter: {counter}", 0))
            chop = state.get("chop", {})
            if chop.get("item"):
                dots = "#" * chop["progress"] + "." * (chop["needed"] - chop["progress"])
                extra = " (counter full!)" if chop.get("waiting") else ""
                chop_text = f"{nice(chop['item'])} [{dots}]{extra}"
            else:
                chop_text = "empty"
            cook = state.get("cook", {})
            if cook.get("item"):
                filled = int((cook.get("progress") or 0) * 10)
                cook_text = f"{nice(cook['item'])} [{'#' * filled}{'.' * (10 - filled)}] {cook['status']}"
                if cook.get("status") == "done":
                    cook_text += f" PULL within {cook.get('burn_in')}s"
            else:
                cook_text = "empty"
            lines.append((f"Chop:    {chop_text}", 0))
            lines.append((f"Cook:    {cook_text}", 0))
            online = state.get("online", {})
            lines.append(("Online:  " + "  ".join(f"{k} {'yes' if v else 'NO'}" for k, v in online.items()), 0))
        lines.append(("", 0))

        if self.has("runner"):
            with self.lock:
                view = self.menu.view(time.monotonic())
            lines.extend(runner_box(view))
            lines.append(("", 0))

        help_parts = []
        if self.has("runner"):
            help_parts.append("arrows/Enter/Backspace(b)/h = runner")
        if self.has("chop"):
            help_parts.append("c = chop")
        if self.has("cook"):
            help_parts.append("s = stir, p = pull")
        help_parts.append("q = quit")
        lines.append(("Keys: " + " | ".join(help_parts), curses.A_DIM))
        with self.lock:
            log = list(self.log)
        for entry in log:
            lines.append(("  " + entry, curses.A_DIM))

        for y, (text, attr) in enumerate(lines[: h - 1]):
            try:
                scr.addnstr(y, 0, text, w - 1, attr)
            except curses.error:
                pass
        scr.refresh()


def runner_box(view):
    """The runner's Pi screen as text."""
    width = 34
    out = [("+" + f" {view['title']} ".center(width, "-") + "+", curses.A_BOLD)]
    body = []
    kind = view["kind"]
    if kind == "idle":
        body = view["lines"] + ["", view["hint"]]
    elif kind == "home":
        body = ["            UP: GET", "",
                "LEFT: TRASH       RIGHT: SEND",
                f"     counter {view['info']}  orders {view['orders']}",
                "           DOWN: SERVE"]
    elif kind == "station":
        left, right = view["left"], view["right"]
        body = [f"  {view['item']}", "",
                f"<- {left[0]}{' (busy)' if left[1] else ''}      {right[0]}{' (busy)' if right[1] else ''} ->",
                "", view["hint"]]
    else:
        for i, (text, tag) in enumerate(view["items"]):
            body.append(("> " if i == view["cursor"] else "  ") + text + (f"  ({tag})" if tag and tag != "dim" else ""))
        body += ["", view["hint"]]
    for line in body:
        out.append(("|" + (" " + line).ljust(width)[:width] + "|", 0))
    if view.get("banner"):
        text, ok = view["banner"]
        out.append(("|" + (" " + text).ljust(width)[:width] + "|",
                    curses.A_REVERSE if ok else curses.A_REVERSE | curses.A_BOLD))
    out.append(("+" + "-" * width + "+", 0))
    return out


def run(scr, sim):
    curses.curs_set(0)
    scr.nodelay(True)
    scr.keypad(True)
    for link in sim.links.values():
        link.start()
    next_draw = 0.0
    try:
        while True:
            ch = scr.getch()
            while ch != -1:
                if ch in (ord("q"), ord("Q")):
                    return
                sim.key(ch)
                ch = scr.getch()
            if sim.has("cook"):
                sim.flush_stir()
            now = time.monotonic()
            if now >= next_draw:
                sim.draw(scr)
                next_draw = now + 0.1
            time.sleep(0.01)
    finally:
        for link in sim.links.values():
            link.close()


def main():
    parser = argparse.ArgumentParser(description="Order Up! keyboard simulator")
    parser.add_argument("mode", choices=["all", "chop", "cook", "runner"])
    add_broker_args(parser)
    args = parser.parse_args()
    curses.wrapper(run, Sim(args.mode, args))


if __name__ == "__main__":
    main()
