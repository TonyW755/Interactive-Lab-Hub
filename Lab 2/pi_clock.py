"""A day/night PiClock for the 240 x 135 Mini PiTFT.

Based on TonyW755's Lab 2 pi_clock.py (419c1e3). The original sun, moon,
stars and four time periods are retained; animation, layout, demo mode and
verification were developed with OpenAI Codex assistance.

Run: python pi_clock.py
Button A (GPIO23): switch between local time and a 60-second day.
Preview without a Pi: python pi_clock.py --preview pi_clock_preview.gif
Sunrise/sunset are configurable design presets, not astronomical forecasts.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
import math
from pathlib import Path
import signal
import sys
import time

from PIL import Image, ImageChops, ImageDraw, ImageFont


WIDTH, HEIGHT = 240, 135
HORIZON = 91
SUN_RADIUS = 16
BAUDRATE = 64_000_000
NIGHT_SKY = ((8, 15, 36), (30, 43, 68))
DAWN_SKY = ((48, 43, 79), (235, 147, 103))
DAY_SKY = ((48, 124, 185), (190, 223, 239))
NOON_SKY = ((37, 119, 188), (174, 216, 243))
DUSK_SKY = ((68, 48, 89), (245, 154, 97))
STARS = ((19, 36, 0.2), (51, 56, 1.7), (80, 29, 3.1),
         (111, 66, 4.4), (134, 34, 2.3), (202, 64, 5.2),
         (223, 30, 0.8), (27, 75, 3.6))


def smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def mix(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


@dataclass(frozen=True)
class Schedule:
    sunrise: float = 5 * 60 + 30
    sunset: float = 19 * 60
    transition: float = 30

    def __post_init__(self):
        if not (0 <= self.sunrise < self.dawn_end < self.sunset < self.dusk_end < 1440):
            raise ValueError("Sunrise and sunset must leave room for both 30-minute transitions.")

    @property
    def dawn_end(self):
        return self.sunrise + self.transition

    @property
    def dusk_end(self):
        return self.sunset + self.transition

    def phase(self, minutes):
        minutes %= 1440
        if self.sunrise <= minutes < self.dawn_end:
            return "SUNRISE"
        if self.dawn_end <= minutes < self.sunset:
            return "DAY"
        if self.sunset <= minutes < self.dusk_end:
            return "SUNSET"
        return "NIGHT"

    def night_amount(self, minutes):
        minutes %= 1440
        phase = self.phase(minutes)
        if phase == "SUNRISE":
            return 1 - smooth((minutes - self.sunrise) / self.transition)
        if phase == "SUNSET":
            return smooth((minutes - self.sunset) / self.transition)
        return float(phase == "NIGHT")

    def sun_position(self, minutes):
        minutes %= 1440
        phase = self.phase(minutes)
        below_ground, above_ground = HORIZON + SUN_RADIUS + 7, HORIZON - 23
        if phase == "SUNRISE":
            progress = smooth((minutes - self.sunrise) / self.transition)
            return 36.0, below_ground + (above_ground - below_ground) * progress
        if phase == "DAY":
            progress = smooth((minutes - self.dawn_end) / (self.sunset - self.dawn_end))
            return 36 + 168 * progress, above_ground - 23 * math.sin(math.pi * progress)
        if phase == "SUNSET":
            progress = smooth((minutes - self.sunset) / self.transition)
            return 204.0, above_ground + (below_ground - above_ground) * progress
        return None

    def sky(self, minutes):
        # Circular keyframes keep the sky continuous through midnight as well.
        night_length = 1440 - self.dusk_end + self.sunrise
        pre_dawn = (self.sunrise - min(30, night_length / 2)) % 1440
        keys = sorted(((pre_dawn, NIGHT_SKY), (self.sunrise, DAWN_SKY),
                       (self.dawn_end, DAY_SKY),
                       ((self.dawn_end + self.sunset) / 2, NOON_SKY),
                       (self.sunset, DUSK_SKY), (self.dusk_end, NIGHT_SKY)))
        minutes %= 1440
        if minutes < keys[0][0]:
            minutes += 1440
        keys.append((keys[0][0] + 1440, keys[0][1]))
        for (start, colors_a), (end, colors_b) in zip(keys, keys[1:]):
            if start <= minutes <= end:
                amount = smooth((minutes - start) / (end - start))
                return tuple(mix(a, b, amount) for a, b in zip(colors_a, colors_b))
        raise ValueError("Invalid time for sky interpolation")


class ClockMode:
    def __init__(self, demo_seconds=60.0):
        self.demo_seconds = demo_seconds
        self.demo_start = None
        self.demo_date = None

    @property
    def demo(self):
        return self.demo_start is not None

    def toggle(self, wall_time, monotonic_time):
        if self.demo:
            self.demo_start = None
        else:
            self.demo_start = monotonic_time
            self.demo_date = wall_time.replace(hour=0, minute=0, second=0, microsecond=0)

    def now(self, wall_time, monotonic_time):
        if not self.demo:
            return wall_time
        seconds = (monotonic_time - self.demo_start) * 86400 / self.demo_seconds
        return self.demo_date + timedelta(seconds=seconds)


class DebouncedButton:
    """Emit one event per stable press, including when a button is held."""

    def __init__(self, debounce_seconds=0.04):
        self.delay = debounce_seconds
        self.candidate = self.stable = False
        self.changed_at = 0.0

    def update(self, pressed, now):
        if pressed != self.candidate:
            self.candidate, self.changed_at = pressed, now
        if self.candidate != self.stable and now - self.changed_at >= self.delay:
            self.stable = self.candidate
            return self.stable
        return False


def load_font(size, path=None):
    if path:
        return ImageFont.truetype(str(path), size)
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                      "DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=32)
def sky_background(top, bottom):
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HORIZON + 1):
        draw.line((0, y, WIDTH - 1, y), fill=mix(top, bottom, y / HORIZON))
    return image


def centered_text(draw, text, font, top, color, center=WIDTH / 2):
    left, upper, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text((round(center - (right - left) / 2 - left), top - upper),
              text, font=font, fill=color)


class ClockRenderer:
    def __init__(self, schedule=None, font_path=None):
        self.schedule = schedule or Schedule()
        self.label_font = load_font(11, font_path)
        self.small_font = load_font(9, font_path)
        self.time_font = load_font(13, font_path)

    def draw_sun(self, layer, position, minutes, elapsed):
        draw = ImageDraw.Draw(layer)
        # Round once so tiny float differences at phase boundaries do not
        # move opposite edges of the same shape to different pixel rows.
        x, y = (round(value) for value in position)
        night = self.schedule.night_amount(minutes)
        color = mix((255, 222, 107), (255, 157, 80), night) + (255,)
        for ray in range(8):
            angle = ray * math.pi / 4 + 0.09 * math.sin(elapsed * 0.8)
            inner, outer = SUN_RADIUS + 3, SUN_RADIUS + 6
            draw.line((x + inner * math.cos(angle), y + inner * math.sin(angle),
                       x + outer * math.cos(angle), y + outer * math.sin(angle)),
                      fill=color, width=2)
        draw.ellipse((x - SUN_RADIUS, y - SUN_RADIUS, x + SUN_RADIUS, y + SUN_RADIUS),
                     fill=color)
        ink = (73, 44, 42, 255)
        blink = 4.8 <= elapsed % 6.4 < 5.0
        for offset in (-5, 5):
            if blink:
                draw.line((x + offset - 2, y - 2, x + offset + 2, y - 2), fill=ink)
            else:
                draw.ellipse((x + offset - 1, y - 4, x + offset + 1, y - 1), fill=ink)
        draw.arc((x - 6, y - 2, x + 6, y + 7), 15, 165, fill=ink, width=1)

    def draw_night(self, layer, amount, elapsed):
        if amount <= 0:
            return
        draw = ImageDraw.Draw(layer)
        for index, (x, y, phase) in enumerate(STARS):
            brightness = 0.65 + 0.35 * math.sin(elapsed * 1.1 + phase)
            color = (234, 244, 255, round(255 * amount * brightness))
            draw.point((x, y), fill=color)
            if index % 3 == 0:
                draw.line((x - 2, y, x + 2, y), fill=color)
                draw.line((x, y - 2, x, y + 2), fill=color)
        # A transparent cut-out preserves the sky gradient inside the crescent.
        moon_mask = Image.new("L", layer.size)
        mask_draw = ImageDraw.Draw(moon_mask)
        y = 47 + math.sin(elapsed * 0.35)
        mask_draw.ellipse((155, y - 15, 185, y + 15), fill=round(255 * amount))
        mask_draw.ellipse((165, y - 19, 189, y + 7), fill=0)
        moon = Image.new("RGBA", layer.size, (242, 242, 213, 255))
        moon.putalpha(moon_mask)
        layer.alpha_composite(moon)

    def render(self, now, elapsed, demo=False):
        minutes = now.hour * 60 + now.minute + (now.second + now.microsecond / 1e6) / 60
        top, bottom = self.schedule.sky(minutes)
        frame = sky_background(top, bottom).copy()
        sky_objects = Image.new("RGBA", frame.size)
        self.draw_night(sky_objects, self.schedule.night_amount(minutes), elapsed)
        sun = self.schedule.sun_position(minutes)
        if sun is not None:
            self.draw_sun(sky_objects, sun, minutes, elapsed)
        # The ground hides the sun as it rises/sets. Keep the header clear too.
        clip = Image.new("L", frame.size)
        ImageDraw.Draw(clip).rectangle((0, 22, WIDTH - 1, HORIZON), fill=255)
        sky_objects.putalpha(ImageChops.multiply(sky_objects.getchannel("A"), clip))
        frame.paste(sky_objects, (0, 0), sky_objects)
        draw = ImageDraw.Draw(frame)
        ground = mix(bottom, (7, 18, 29), 0.89)
        draw.rectangle((0, HORIZON + 1, WIDTH - 1, HEIGHT - 1), fill=ground)
        draw.line((12, HORIZON + 1, WIDTH - 13, HORIZON + 1),
                  fill=mix(bottom, (174, 187, 184), 0.45))

        draw.rounded_rectangle((80, 3, 160, 20), radius=8, fill=(17, 29, 47))
        centered_text(draw, self.schedule.phase(minutes), self.label_font, 7, (245, 247, 249))
        draw.text((8, 7), "DEMO" if demo else "LIVE", font=self.small_font,
                  fill=(255, 224, 156) if demo else (234, 242, 250))
        draw.rectangle((0, 103, WIDTH - 1, HEIGHT - 1), fill=(10, 19, 31))
        centered_text(draw, now.strftime("%m/%d/%Y"), self.small_font, 105, (160, 179, 199))
        centered_text(draw, now.strftime("%H:%M:%S"), self.time_font, 117, (242, 246, 250))
        return frame


class MiniPiTFT:
    """Hardware imports and GPIO ownership are confined to live display mode."""

    def __init__(self):
        import board
        import digitalio
        import adafruit_rgb_display.st7789 as st7789

        self.resources = []
        self.backlight = None
        try:
            spi = board.SPI()
            self.resources.append(spi)
            cs = digitalio.DigitalInOut(board.D5)
            self.resources.append(cs)
            dc = digitalio.DigitalInOut(board.D25)
            self.resources.append(dc)
            self.display = st7789.ST7789(spi, cs=cs, dc=dc, rst=None,
                                        baudrate=BAUDRATE, width=135, height=240,
                                        x_offset=53, y_offset=40)
            self.backlight = digitalio.DigitalInOut(board.D22)
            self.resources.append(self.backlight)
            self.backlight.switch_to_output(value=True)
            self.button = digitalio.DigitalInOut(board.D23)
            self.resources.append(self.button)
            self.button.switch_to_input(pull=digitalio.Pull.UP)
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.backlight is not None:
            try:
                self.backlight.value = False
            except (OSError, RuntimeError):
                pass
        for resource in reversed(self.resources):
            try:
                resource.deinit()
            except (OSError, RuntimeError) as error:
                print("Could not release display resource:", error, file=sys.stderr)
        self.resources.clear()
        self.backlight = None


def run_display(renderer, fps, demo_seconds, start_demo):
    mode = ClockMode(demo_seconds)
    started = time.monotonic()
    if start_demo:
        mode.toggle(datetime.now(), started)
    button = DebouncedButton()
    period = 1 / fps
    deadline = started
    with MiniPiTFT() as hardware:
        print("Button A: LIVE / DEMO. Ctrl-C: stop. Using the Pi's local timezone.")
        while True:
            tick = time.monotonic()
            wall_time = datetime.now()  # One snapshot for date, time and scene.
            if button.update(not hardware.button.value, tick):
                mode.toggle(wall_time, tick)
            frame = renderer.render(mode.now(wall_time, tick), tick - started, mode.demo)
            hardware.display.image(frame, 90)
            deadline += period
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            else:
                # Skip missed deadlines instead of replaying stale frames.
                deadline = time.monotonic()


def export_preview(renderer, path, seconds, fps):
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    schedule = renderer.schedule
    sample_minutes = (0, schedule.sunrise, schedule.sunrise + 15, schedule.dawn_end,
                      (schedule.dawn_end + schedule.sunset) / 2,
                      schedule.sunset, schedule.sunset + 15, schedule.dusk_end)
    samples = Image.new("RGB", (WIDTH * len(sample_minutes), HEIGHT))
    for index, minutes in enumerate(sample_minutes):
        samples.paste(renderer.render(start + timedelta(minutes=minutes), 1.0, True),
                      (index * WIDTH, 0))
    # A shared palette avoids palette-induced flicker between GIF frames.
    palette = samples.quantize(colors=256)
    count = max(1, round(seconds * fps))
    frames, durations = [], []
    for index in range(count):
        elapsed = index * seconds / count
        frame = renderer.render(start + timedelta(seconds=index * 86400 / count), elapsed, True)
        frames.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
        durations.append(10 * (round((index + 1) * seconds * 100 / count)
                               - round(index * seconds * 100 / count)))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=False, disposal=2)
    print(f"Saved {count} frames / {seconds:g} seconds to {path}")


def clock_minutes(value):
    try:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError
        hour, minute = map(int, parts)
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        return hour * 60 + minute
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use a 24-hour HH:MM time.") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="Start with a simulated day.")
    parser.add_argument("--demo-seconds", type=float, default=60, help="Real seconds per simulated day.")
    parser.add_argument("--fps", type=float, default=15, help="Target refresh rate, 1 to 30 (default: 15).")
    parser.add_argument("--sunrise", type=clock_minutes, default=330, help="Preset sunrise, HH:MM.")
    parser.add_argument("--sunset", type=clock_minutes, default=1140, help="Preset sunset, HH:MM.")
    parser.add_argument("--font", type=Path, help="Optional TrueType font for display and previews.")
    parser.add_argument("--preview", type=Path, help="Export a GIF of one day; no GPIO or Pi required.")
    args = parser.parse_args(argv)
    if not (math.isfinite(args.fps) and 1 <= args.fps <= 30):
        parser.error("--fps must be between 1 and 30.")
    if not (math.isfinite(args.demo_seconds) and 1 <= args.demo_seconds <= 3600):
        parser.error("--demo-seconds must be between 1 and 3600.")
    if args.preview and args.preview.suffix.lower() != ".gif":
        parser.error("--preview must name a .gif file.")
    if args.preview and args.demo_seconds * args.fps > 5000:
        parser.error("Preview is limited to 5000 frames; reduce --fps or --demo-seconds.")
    try:
        renderer = ClockRenderer(Schedule(args.sunrise, args.sunset), args.font)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.preview:
        export_preview(renderer, args.preview, args.demo_seconds, args.fps)
        return 0

    def stop(_signum, _frame):
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGTERM, stop)
    try:
        run_display(renderer, args.fps, args.demo_seconds, args.demo)
    except KeyboardInterrupt:
        print("Clock stopped; backlight and GPIO released.")
    except (ImportError, OSError, RuntimeError) as error:
        print(f"Cannot run the Pi display: {error}\n"
              "Use the course venv on the Pi, enable SPI and stop piscreen.service "
              "before running. Use --preview FILE.gif on another computer.", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    return 0


if __name__ == "__main__":
    sys.exit(main())
