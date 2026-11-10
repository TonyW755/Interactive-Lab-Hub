"""Chop station: an LSM6DS3 IMU inside a cardboard knife counts chops.

Run on the Chop Pi:
    sudo systemctl stop piscreen.service
    python chop_station.py               # play
    python chop_station.py --calibrate   # print motion peaks to tune thresholds

Publishes {"type": "chop"} on IDD/orderup/chop/event for every chop and
shows the item on the chopping board from IDD/orderup/state.

Detection: a chop is the jolt when the blade hits the board. We measure how
far the total acceleration is from 1 g (so the knife's tilt doesn't matter),
count a chop when that jumps over CHOP_THRESHOLD, then wait for the knife to
settle below REARM_THRESHOLD and for LOCKOUT seconds before counting another.
Tune these with --calibrate and real swings.
"""

import math
import time

# --- Tuning (try --calibrate) --------------------------------------------------
GRAVITY = 9.81
CHOP_THRESHOLD = 11.0   # m/s^2 away from 1 g that counts as a chop
REARM_THRESHOLD = 4.0   # must settle below this before the next chop
LOCKOUT = 0.15          # seconds; at most ~6 chops a second
SAMPLE_HZ = 250
IMU_ADDRESSES = (0x6A, 0x6B)  # Lab 4 used 0x6A; SparkFun boards ship at 0x6B
FLASH_SECONDS = 0.12    # screen flash on each chop


class ChopDetector:
    """Hardware-free chop detection, so it can be unit-tested."""

    def __init__(self, threshold=CHOP_THRESHOLD, rearm=REARM_THRESHOLD, lockout=LOCKOUT):
        self.threshold = threshold
        self.rearm = rearm
        self.lockout = lockout
        self.armed = True
        self.last_chop = -math.inf
        self.motion = 0.0

    def update(self, ax, ay, az, now):
        """Feed one accelerometer sample (m/s^2). Returns True on a new chop."""
        self.motion = abs(math.sqrt(ax * ax + ay * ay + az * az) - GRAVITY)
        since = now - self.last_chop
        if not self.armed:
            if self.motion < self.rearm and since >= self.lockout:
                self.armed = True
            return False
        if self.motion >= self.threshold and since >= self.lockout:
            self.armed = False
            self.last_chop = now
            return True
        return False


def open_imu():
    import board
    from adafruit_lsm6ds import AccelRange, Rate
    from adafruit_lsm6ds.lsm6ds3 import LSM6DS3

    i2c = board.I2C()
    last_error = None
    for address in IMU_ADDRESSES:
        try:
            imu = LSM6DS3(i2c, address=address)
            imu.accelerometer_range = AccelRange.RANGE_8G   # hard chops clip at 4 g
            imu.accelerometer_data_rate = Rate.RATE_416_HZ
            print(f"[chop] IMU found at {hex(address)}")
            return imu
        except (ValueError, OSError, RuntimeError) as error:
            last_error = error
    raise RuntimeError(f"No LSM6DS3 at {[hex(a) for a in IMU_ADDRESSES]}. "
                       f"Check the Qwiic cable and i2cdetect -y 1 ({last_error})")


def calibrate(imu):
    """Print the biggest motion each half second. Chop for real, then wave the
    knife around without chopping, and pick a threshold between the two."""
    detector = ChopDetector()
    print("Chop, wave, tilt... Ctrl+C to stop.")
    print(f"Current CHOP_THRESHOLD={CHOP_THRESHOLD}  REARM_THRESHOLD={REARM_THRESHOLD}")
    peak, chops, window_start = 0.0, 0, time.monotonic()
    while True:
        now = time.monotonic()
        if detector.update(*imu.acceleration, now):
            chops += 1
        peak = max(peak, detector.motion)
        if now - window_start >= 0.5:
            bars = "#" * int(peak)
            print(f"peak {peak:5.1f} m/s^2 |{bars:<40}| chops so far: {chops}")
            peak, window_start = 0.0, now
        time.sleep(1.0 / SAMPLE_HZ)


def paint(draw, v):
    """Draw the chop screen. v is the tuple built by view() in main()."""
    from common import nice
    from display import BLACK, GREEN, GREY, RED, WHITE, YELLOW, centered, header

    status, phase, item, progress, needed, result, waiting, flashing = v
    if flashing:
        draw.rectangle((0, 0, 240, 135), fill=YELLOW)
    header(draw, "CHOP", status, color=BLACK if flashing else YELLOW)
    ink = BLACK if flashing else WHITE
    if phase != "playing":
        centered(draw, 50, "Round over" if phase == "over" else "Get ready!", 28, ink)
        centered(draw, 95, "Waiting for the Runner", 16, GREY)
        return f"chop: {phase}"
    if not item:
        centered(draw, 45, "Board empty", 30, ink if flashing else GREY)
        centered(draw, 92, "Wait for the Runner", 16, GREY)
        return "chop: empty"
    centered(draw, 32, nice(item).upper(), 32, ink)
    needed = needed or 6
    dot, gap = 26, 8
    x = (240 - (needed * dot + (needed - 1) * gap)) // 2
    for i in range(needed):
        box = (x + i * (dot + gap), 74, x + i * (dot + gap) + dot, 74 + dot)
        if i < (progress or 0):
            draw.ellipse(box, fill=GREEN if result else (BLACK if flashing else YELLOW))
        else:
            draw.ellipse(box, outline=BLACK if flashing else YELLOW, width=3)
    if result and waiting:
        centered(draw, 108, "Done! Counter full", 20, RED)
    elif result:
        centered(draw, 108, "Done!", 20, GREEN)
    else:
        centered(draw, 108, "CHOP! CHOP!", 20, ink)
    return f"chop: {item} {progress}/{needed}"


def main():
    from common import StationLink, parse_station_args
    from display import DisplayLoop, Screen

    parser = parse_station_args("Order Up! chop station")
    parser.add_argument("--calibrate", action="store_true", help="print motion peaks and exit")
    args = parser.parse_args()

    imu = open_imu()
    if args.calibrate:
        calibrate(imu)
        return

    link = StationLink("chop", args.broker, args.port, args.prefix).start()
    screen = Screen()
    detector = ChopDetector()
    flash_until = 0.0
    local_chops = 0

    def view():
        state = link.state or {}
        chop = state.get("chop") or {}
        flashing = time.monotonic() < flash_until
        return (link.status_text(), state.get("phase"), chop.get("item"), chop.get("progress"),
                chop.get("needed"), chop.get("result"), chop.get("waiting"), flashing)

    display = DisplayLoop(screen, view, paint)
    display.start()

    print("[chop] ready. Chop away! Ctrl+C to quit.")
    period = 1.0 / SAMPLE_HZ
    try:
        while True:
            start = time.monotonic()
            try:
                ax, ay, az = imu.acceleration
            except OSError as error:  # loose Qwiic cable mid-swing
                print(f"[chop] IMU read failed: {error}")
                time.sleep(0.2)
                continue
            if detector.update(ax, ay, az, start):
                local_chops += 1
                flash_until = start + FLASH_SECONDS
                link.send("chop/event", {"type": "chop"}, qos=0)
                print(f"[chop] chop #{local_chops} (motion {detector.motion:.1f})")
            time.sleep(max(0.0, period - (time.monotonic() - start)))
    except KeyboardInterrupt:
        print("\n[chop] bye")
    finally:
        display.stop()
        link.close()


if __name__ == "__main__":
    main()
