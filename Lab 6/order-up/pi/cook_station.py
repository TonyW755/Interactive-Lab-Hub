"""Cook station: a rotary encoder in a cardboard pan, plus a servo heat needle.

Run on the Cook Pi (the Servo pHAT needs its own USB-C power!):
    sudo systemctl stop piscreen.service
    python cook_station.py
    python cook_station.py --test-needle   # sweep the needle through its zones

Turning the encoder (either way) stirs: ticks are added up and sent at most
5 times a second as {"type": "stir", "ticks": N}. Pressing the encoder takes
the food off the heat: {"type": "pull", "id": "..."}.

The servo needle shows the pan's heat from the game state:
    cold (empty) -> rises while you stir -> DONE zone -> creeps toward BURNT
The encoder's LED: orange while cooking, blinking green when it's time to
pull, red when burnt.
"""

import time

# --- Tuning -----------------------------------------------------------------------
STIR_SEND_GAP = 0.2       # seconds between stir messages (max 5/s)
SAMPLE_HZ = 60

SERVO_CHANNEL = 0
SERVO_MIN, SERVO_MAX = 0, 120   # safe range for the lab's 9g servos
NEEDLE_COLD = 0                 # angle for an empty / cold pan
NEEDLE_DONE = 60                # angle when the food is done
NEEDLE_BURNT = 120              # angle when it burns
SERVO_REVERSED = False          # flip if the needle moves the wrong way on your dial
NEEDLE_DEADBAND = 1.5           # don't twitch the servo for tiny changes

ENCODER_ADDRESS = 0x36
ENCODER_BUTTON_PIN = 24
ENCODER_LED_PIN = 6
LED_BRIGHTNESS = 0.4


def needle_angle(cook, seconds_since_state=0.0):
    """Where the heat needle should point for a cook state from the server.

    During the done window we count the burn timer down locally between state
    updates so the needle creeps smoothly toward BURNT.
    """
    if not cook or cook.get("status") in (None, "empty"):
        return NEEDLE_COLD
    status = cook["status"]
    if status == "cooking":
        progress = max(0.0, min(1.0, cook.get("progress") or 0.0))
        return NEEDLE_COLD + progress * (NEEDLE_DONE - NEEDLE_COLD)
    if status == "done":
        window = cook.get("burn_seconds") or 8
        left = (cook.get("burn_in") if cook.get("burn_in") is not None else window) - seconds_since_state
        heat = 1.0 - max(0.0, min(1.0, left / window))
        return NEEDLE_DONE + heat * (NEEDLE_BURNT - NEEDLE_DONE)
    return NEEDLE_BURNT  # burning


def servo_command(angle):
    angle = max(SERVO_MIN, min(SERVO_MAX, angle))
    return SERVO_MAX - angle + SERVO_MIN if SERVO_REVERSED else angle


class StirCounter:
    """Adds up encoder movement (either direction) and decides when to send."""

    def __init__(self, gap=STIR_SEND_GAP):
        self.gap = gap
        self.last_position = None
        self.pending = 0
        self.last_sent = -1e9
        self.last_stir = -1e9

    def update(self, position, now):
        """Feed the raw encoder position. Returns ticks to send now, or 0."""
        if self.last_position is not None:
            moved = abs(position - self.last_position)
            if moved:
                self.pending += moved
                self.last_stir = now
        self.last_position = position
        if self.pending and now - self.last_sent >= self.gap:
            ticks, self.pending = self.pending, 0
            self.last_sent = now
            return ticks
        return 0

    def stirring(self, now, window=0.3):
        return now - self.last_stir < window


def led_color(cook, phase, now, stirring):
    """(r, g, b) for the encoder's NeoPixel."""
    blink = int(now * 4) % 2 == 0
    if phase != "playing":
        return (20, 20, 20)
    status = (cook or {}).get("status", "empty")
    if status == "cooking":
        return (255, 120, 0) if stirring else (90, 40, 0)
    if status == "done":
        burn_in = cook.get("burn_in") or 0
        fast = int(now * (10 if burn_in <= 3 else 4)) % 2 == 0
        return (0, 255, 40) if fast else (0, 0, 0)
    if status == "burning":
        return (255, 0, 0) if blink else (60, 0, 0)
    return (0, 0, 0)


class Hardware:
    """Encoder (seesaw) + Servo pHAT. All I2C happens on the main thread."""

    def __init__(self):
        import board
        import pi_servo_hat
        from adafruit_seesaw import digitalio, neopixel, rotaryio, seesaw

        ss = seesaw.Seesaw(board.I2C(), addr=ENCODER_ADDRESS)
        ss.pin_mode(ENCODER_BUTTON_PIN, ss.INPUT_PULLUP)
        self.button = digitalio.DigitalIO(ss, ENCODER_BUTTON_PIN)
        self.encoder = rotaryio.IncrementalEncoder(ss)
        try:
            self.pixel = neopixel.NeoPixel(ss, ENCODER_LED_PIN, 1, brightness=LED_BRIGHTNESS)
        except Exception as error:
            print(f"[cook] encoder LED unavailable: {error}")
            self.pixel = None
        self.servo = pi_servo_hat.PiServoHat()
        self.servo.restart()
        self._angle = None
        self._color = None

    def position(self):
        return -self.encoder.position  # clockwise positive, like encoder_test.py

    def pressed(self):
        return not self.button.value

    def set_needle(self, angle):
        if self._angle is None or abs(angle - self._angle) >= NEEDLE_DEADBAND:
            self.servo.move_servo_position(SERVO_CHANNEL, servo_command(angle))
            self._angle = angle

    def set_led(self, color):
        if self.pixel is not None and color != self._color:
            self.pixel.fill(color)
            self._color = color


def test_needle(hw):
    for label, angle in (("COLD", NEEDLE_COLD), ("DONE", NEEDLE_DONE), ("BURNT", NEEDLE_BURNT),
                         ("DONE", NEEDLE_DONE), ("COLD", NEEDLE_COLD)):
        print(f"needle -> {label} ({angle} deg)")
        hw.set_needle(angle)
        time.sleep(1.5)


def paint(draw, v):
    """Draw the cook screen. v is the tuple built by view() in main()."""
    from common import nice
    from display import DARK, GREEN, GREY, ORANGE, RED, WHITE, YELLOW, bar, centered, header

    status, phase, item, cook_status, progress, burn_in, result, stirring, message, blink = v
    header(draw, "COOK", status)
    if phase != "playing":
        centered(draw, 50, "Round over" if phase == "over" else "Get ready!", 28)
        centered(draw, 95, "Waiting for the Runner", 16, GREY)
        return f"cook: {phase}"
    if not item:
        centered(draw, 42, "Pan empty", 30, GREY)
        centered(draw, 88, "Wait for the Runner", 16, GREY)
    elif cook_status == "cooking":
        centered(draw, 30, nice(item).upper(), 28)
        bar(draw, 14, 70, 212, 20, progress or 0, ORANGE)
        centered(draw, 98, "stirring..." if stirring else "STIR!", 24, ORANGE if stirring else YELLOW)
    elif cook_status == "done":
        centered(draw, 28, nice(result).upper(), 26, GREEN)
        centered(draw, 62, f"PULL! {burn_in}s", 36, GREEN if blink else WHITE)
        centered(draw, 105, "press the knob", 16, GREY)
    else:  # burning
        if blink:
            draw.rectangle((0, 26, 240, 135), fill=(70, 10, 5))
        centered(draw, 34, "BURNT!", 40, RED)
        centered(draw, 88, "Press to pull it off", 18, WHITE)
    if message:
        text, ok = message
        draw.rectangle((0, 113, 240, 135), fill=DARK)
        centered(draw, 115, text, 16, GREEN if ok else RED)
    return f"cook: {item} {cook_status} {progress}"


def main():
    import threading

    from common import StationLink, parse_station_args
    from display import DisplayLoop, Edge, Screen

    parser = parse_station_args("Order Up! cook station")
    parser.add_argument("--test-needle", action="store_true", help="sweep the servo and exit")
    args = parser.parse_args()

    hw = Hardware()
    if args.test_needle:
        test_needle(hw)
        return

    note = {"text": None, "ok": True, "until": 0.0}
    note_lock = threading.Lock()

    def on_result(result):
        with note_lock:
            note.update(text=result.get("msg"), ok=result.get("ok", False),
                        until=time.monotonic() + 2.5)

    link = StationLink("cook", args.broker, args.port, args.prefix, on_result=on_result).start()
    screen = Screen()
    stir = StirCounter()
    button = Edge()

    def view():
        state = link.state or {}
        cook = state.get("cook") or {}
        now = time.monotonic()
        with note_lock:
            message = (note["text"], note["ok"]) if now < note["until"] else None
        blink = int(now * 3) % 2 if cook.get("status") in ("done", "burning") else 0
        return (link.status_text(), state.get("phase"), cook.get("item"), cook.get("status"),
                cook.get("progress"), cook.get("burn_in"), cook.get("result"),
                stir.stirring(now), message, blink)

    display = DisplayLoop(screen, view, paint)
    display.start()
    print("[cook] ready. Stir with the knob, press it to pull. Ctrl+C to quit.")

    period = 1.0 / SAMPLE_HZ
    try:
        while True:
            now = time.monotonic()
            try:
                ticks = stir.update(hw.position(), now)
                if ticks:
                    link.send("cook/event", {"type": "stir", "ticks": ticks}, qos=0)
                if button.pressed(hw.pressed(), now):
                    link.send("cook/event", {"type": "pull", "id": link.new_id()}, qos=1)
                    print("[cook] pull")

                state = link.state or {}
                cook = state.get("cook")
                hw.set_needle(needle_angle(cook, now - link.state_time))
                hw.set_led(led_color(cook, state.get("phase"), now, stir.stirring(now)))
            except OSError as error:  # I2C hiccup: keep going
                print(f"[cook] I2C error: {error}")
                time.sleep(0.2)
            time.sleep(max(0.0, period - (time.monotonic() - now)))
    except KeyboardInterrupt:
        print("\n[cook] bye")
    finally:
        display.stop()
        try:
            hw.set_led((0, 0, 0))
            hw.set_needle(NEEDLE_COLD)
        except OSError:
            pass
        link.close()


if __name__ == "__main__":
    main()
