"""Runner station: a Qwiic joystick drives the menus in runner_menu.py.

Run on the Runner Pi:
    sudo systemctl stop piscreen.service
    python runner_station.py
    python runner_station.py --test     # print raw readings and detected flicks

Buttons: joystick press = confirm, PiTFT top button = back, bottom = home.
Only confirmed actions go over MQTT (IDD/orderup/runner/action); replies come
back on IDD/orderup/runner/result and show as a banner.
"""

import threading
import time

from runner_menu import BACK, DOWN, HOME, LEFT, PRESS, RIGHT, UP, RunnerMenu

# --- Joystick mounting ---------------------------------------------------------------
# Which raw reading means "up" and which means "right" depends on how the
# joystick sits in its box. These match our Lab 4 notes (dessert_box.py:
# horizontal grows upward, vertical grows rightward). Run --test and flick
# each way; if a direction comes out backwards, flip its sign here.
UP_AXIS = ("horizontal", +1)
RIGHT_AXIS = ("vertical", +1)

FLICK_FIRE = 330       # distance from center (0-512) that counts as a flick
FLICK_RELEASE = 140    # must come back this close to center before the next flick
REPEAT_DELAY = 0.45    # hold up/down this long to start scrolling
REPEAT_EVERY = 0.16
SAMPLE_HZ = 60


class FlickDetector:
    """Turns joystick readings into one event per flick (with hold-to-repeat
    for up/down so long lists scroll)."""

    def __init__(self, center=(512, 512), fire=FLICK_FIRE, release=FLICK_RELEASE):
        self.center = center
        self.fire = fire
        self.release = release
        self.held = None
        self.next_repeat = 0.0

    def to_up_right(self, horizontal, vertical):
        raw = {"horizontal": horizontal - self.center[0], "vertical": vertical - self.center[1]}
        return raw[UP_AXIS[0]] * UP_AXIS[1], raw[RIGHT_AXIS[0]] * RIGHT_AXIS[1]

    def update(self, horizontal, vertical, now):
        up, right = self.to_up_right(horizontal, vertical)
        if self.held is None:
            if max(abs(up), abs(right)) < self.fire:
                return None
            if abs(up) >= abs(right):
                self.held = UP if up > 0 else DOWN
            else:
                self.held = RIGHT if right > 0 else LEFT
            self.next_repeat = now + REPEAT_DELAY
            return self.held
        if max(abs(up), abs(right)) < self.release:
            self.held = None
            return None
        if self.held in (UP, DOWN) and now >= self.next_repeat:
            self.next_repeat = now + REPEAT_EVERY
            return self.held
        return None


def open_joystick():
    import qwiic_joystick

    joystick = qwiic_joystick.QwiicJoystick()
    if not joystick.connected:
        raise RuntimeError("Qwiic Joystick not found. Check the cable and i2cdetect -y 1 (0x20)")
    joystick.begin()
    # Measure the resting center so a slightly off-center stick doesn't drift.
    samples = []
    for _ in range(20):
        samples.append((joystick.horizontal, joystick.vertical))
        time.sleep(0.01)
    center = (sum(s[0] for s in samples) / len(samples), sum(s[1] for s in samples) / len(samples))
    print(f"[runner] joystick center {center[0]:.0f}, {center[1]:.0f}")
    return joystick, center


def test_mode(joystick, center):
    flicks = FlickDetector(center)
    print("Flick the joystick each way and press it. Ctrl+C to stop.")
    while True:
        h, v = joystick.horizontal, joystick.vertical
        up, right = flicks.to_up_right(h, v)
        event = flicks.update(h, v, time.monotonic())
        pressed = joystick.button == 0
        if event or pressed:
            print(f"raw h={h:4d} v={v:4d} -> up={up:+5.0f} right={right:+5.0f}  "
                  f"{event or ''} {'PRESS' if pressed else ''}")
        time.sleep(0.05)


# --- Drawing ---------------------------------------------------------------------------

def paint(draw, v):
    from display import (BLACK, BLUE, DARK, GREEN, GREY, RED, WHITE, YELLOW, WIDTH, centered,
                         fit_text, font, header)

    header(draw, v["title"], v.get("status"))
    kind = v["kind"]
    summary = f"runner: {v['title']}"

    if kind == "idle":
        centered(draw, 34, v["lines"][0], 30, YELLOW)
        if len(v["lines"]) > 1:
            centered(draw, 72, v["lines"][1], 22)
        centered(draw, 104, v["hint"], 18, GREEN)
        summary += " " + " / ".join(v["lines"])

    elif kind == "home":
        centered(draw, 26, "GET", 22, YELLOW)
        centered(draw, 104, "SERVE", 22, YELLOW)
        draw.text((8, 62), "TRASH", font=font(20), fill=YELLOW)
        draw.text((WIDTH - 66, 62), "SEND", font=font(20), fill=YELLOW)
        used, total = v["info"].split("/")
        centered(draw, 56, v["info"], 18, RED if used == total else WHITE, shrink=False)
        centered(draw, 78, "slots", 12, GREY, shrink=False)

    elif kind == "station":
        centered(draw, 28, v["item"].upper(), 22)
        for side, x in (("left", 6), ("right", 124)):
            name, busy = v[side]
            draw.rounded_rectangle((x, 58, x + 110, 104), radius=8,
                                   fill=DARK, outline=RED if busy else GREEN, width=3)
            label = f"< {name}" if side == "left" else f"{name} >"
            w = draw.textbbox((0, 0), label, font=font(22))[2]
            draw.text((x + (110 - w) // 2, 62), label, font=font(22), fill=WHITE)
            note = "busy" if busy else "free"
            w = draw.textbbox((0, 0), note, font=font(14))[2]
            draw.text((x + (110 - w) // 2, 86), note, font=font(14), fill=RED if busy else GREEN)
        draw.text((6, 112), v["hint"], font=font(14), fill=GREY)

    else:  # list
        items, cursor = v["items"], v["cursor"]
        rows, row_h, top = 4, 21, 27
        start = 0 if cursor is None else max(0, min(cursor - 1, len(items) - rows))
        for row, i in enumerate(range(start, min(len(items), start + rows))):
            text, tag = items[i]
            y = top + row * row_h
            selected = i == cursor
            color = {"bad": RED, "ready": GREEN, "urgent": RED, "dim": GREY}.get(tag, WHITE)
            if selected:
                # highlight in the tag's color so the text stays readable
                fill = {"bad": RED, "urgent": RED, "ready": GREEN}.get(tag, BLUE)
                draw.rounded_rectangle((2, y, WIDTH - 3, y + row_h - 1), radius=5, fill=fill)
                color = WHITE if fill == RED else BLACK
            size = fit_text(draw, text, WIDTH - 24, 18)
            draw.text((10, y + 1), text, font=font(size), fill=color)
        if len(items) > rows:
            draw.text((WIDTH - 12, top), "^" if start > 0 else "", font=font(12), fill=GREY)
        draw.text((6, 114), v["hint"], font=font(14), fill=GREY)
        if 0 <= (cursor or 0) < len(items):
            summary += f" > {items[cursor or 0][0]}"

    if v.get("banner"):
        text, ok = v["banner"]
        draw.rectangle((0, 110, WIDTH, 135), fill=GREEN if ok else RED)
        centered(draw, 113, text, 17, BLACK if ok else WHITE)
        summary += f" [{text}]"
    return summary


def main():
    from common import StationLink, parse_station_args
    from display import DisplayLoop, Edge, Screen

    parser = parse_station_args("Order Up! runner station")
    parser.add_argument("--test", action="store_true", help="print joystick readings and flicks")
    args = parser.parse_args()

    joystick, center = open_joystick()
    if args.test:
        test_mode(joystick, center)
        return

    menu = RunnerMenu()
    lock = threading.Lock()   # MQTT callbacks and the main loop both touch the menu

    def on_state(state):
        with lock:
            menu.set_state(state)

    def on_result(result):
        with lock:
            menu.show_result(result, time.monotonic())

    link = StationLink("runner", args.broker, args.port, args.prefix,
                       on_state=on_state, on_result=on_result).start()
    screen = Screen()

    def view():
        with lock:
            v = menu.view(time.monotonic())
        v["status"] = link.status_text()
        return v

    display = DisplayLoop(screen, view, paint, fps=15)
    display.start()

    flicks = FlickDetector(center)
    stick_button, top_button, bottom_button = Edge(), Edge(), Edge()
    print("[runner] ready. Ctrl+C to quit.")

    period = 1.0 / SAMPLE_HZ
    try:
        while True:
            now = time.monotonic()
            events = []
            try:
                flick = flicks.update(joystick.horizontal, joystick.vertical, now)
                if flick:
                    events.append(flick)
                if stick_button.pressed(joystick.button == 0, now):
                    events.append(PRESS)
            except OSError as error:
                print(f"[runner] joystick read failed: {error}")
                time.sleep(0.2)
            if top_button.pressed(screen.button_a(), now):
                events.append(BACK)
            if bottom_button.pressed(screen.button_b(), now):
                events.append(HOME)

            for event in events:
                with lock:
                    action = menu.handle(event, now)
                if action:
                    action["id"] = link.new_id()
                    link.send("runner/action", action, qos=1)
                    print(f"[runner] {action}")
            time.sleep(max(0.0, period - (time.monotonic() - now)))
    except KeyboardInterrupt:
        print("\n[runner] bye")
    finally:
        display.stop()
        link.close()


if __name__ == "__main__":
    main()
