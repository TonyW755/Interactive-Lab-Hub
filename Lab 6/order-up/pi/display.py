"""Mini PiTFT (240x135) helper shared by the three stations.

Set up the same way as Lab 6/pixel_grid_publisher.py. Remember to free the
screen first:   sudo systemctl stop piscreen.service

If the display libraries aren't there (e.g. running on a laptop), Screen falls
back to printing a one-line summary whenever the picture changes.

Drawing runs on its own thread (DisplayLoop) so a slow SPI push never stalls
sensor sampling in the station's main loop.
"""

import threading
import time

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 240, 135

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREY = (120, 110, 100)
DARK = (35, 26, 20)
YELLOW = (255, 200, 61)
RED = (255, 75, 62)
GREEN = (79, 214, 122)
ORANGE = (255, 140, 40)
BLUE = (95, 184, 255)

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
]
_font_cache = {}


def font(size):
    if size not in _font_cache:
        loaded = None
        for path in _FONT_PATHS:
            try:
                loaded = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        if loaded is None:
            try:
                loaded = ImageFont.load_default(size=size)  # Pillow >= 10.1
            except TypeError:
                loaded = ImageFont.load_default()
        _font_cache[size] = loaded
    return _font_cache[size]


def text_width(draw, text, size):
    left, _, right, _ = draw.textbbox((0, 0), text, font=font(size))
    return right - left


def fit_text(draw, text, max_width, size, min_size=12):
    """Largest font size (<= size) at which text fits in max_width."""
    while size > min_size and text_width(draw, text, size) > max_width:
        size -= 2
    return size


def centered(draw, y, text, size, fill=WHITE, shrink=True):
    if shrink:
        size = fit_text(draw, text, WIDTH - 8, size)
    w = text_width(draw, text, size)
    draw.text(((WIDTH - w) // 2, y), text, font=font(size), fill=fill)


def bar(draw, x, y, w, h, fraction, fill, back=DARK):
    fraction = max(0.0, min(1.0, fraction))
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=back)
    if fraction > 0:
        draw.rounded_rectangle((x, y, x + max(h, int(w * fraction)), y + h), radius=h // 2, fill=fill)


def header(draw, title, status=None, color=YELLOW):
    """Station name on the left, connection problem (if any) on the right."""
    draw.text((6, 3), title, font=font(18), fill=color)
    if status:
        w = text_width(draw, status, 14)
        draw.rounded_rectangle((WIDTH - w - 14, 3, WIDTH - 3, 23), radius=6, fill=RED)
        draw.text((WIDTH - w - 8, 5), status, font=font(14), fill=WHITE)


class Screen:
    """The Mini PiTFT plus its two buttons (A = top, B = bottom)."""

    def __init__(self):
        self.disp = None
        self._button_a = None
        self._button_b = None
        self._last_summary = None
        try:
            import board
            import digitalio
            import adafruit_rgb_display.st7789 as st7789

            cs_pin = digitalio.DigitalInOut(board.D5)
            dc_pin = digitalio.DigitalInOut(board.D25)
            backlight = digitalio.DigitalInOut(board.D22)
            backlight.switch_to_output()
            backlight.value = True
            self._button_a = digitalio.DigitalInOut(board.D23)
            self._button_b = digitalio.DigitalInOut(board.D24)
            self._button_a.switch_to_input(pull=digitalio.Pull.UP)
            self._button_b.switch_to_input(pull=digitalio.Pull.UP)
            self.disp = st7789.ST7789(
                board.SPI(), cs=cs_pin, dc=dc_pin, rst=None, baudrate=64000000,
                width=135, height=240, x_offset=53, y_offset=40, rotation=90,
            )
            print("[display] Mini PiTFT ready")
        except Exception as error:  # no Pi, no libraries, or screen busy
            print(f"[display] no PiTFT ({error}); printing to the terminal instead")

    @property
    def has_display(self):
        return self.disp is not None

    def button_a(self):
        """Top button held? (active low)"""
        return self._button_a is not None and not self._button_a.value

    def button_b(self):
        """Bottom button held? (active low)"""
        return self._button_b is not None and not self._button_b.value

    def new_frame(self, background=BLACK):
        image = Image.new("RGB", (WIDTH, HEIGHT), background)
        return image, ImageDraw.Draw(image)

    def show(self, image, summary=""):
        if self.disp is not None:
            self.disp.image(image)
        elif summary and summary != self._last_summary:
            print(f"[screen] {summary}")
        self._last_summary = summary


class DisplayLoop(threading.Thread):
    """Calls view() up to `fps` times a second. Whenever the returned view
    changes, paints it with paint(draw, view) and pushes it to the screen.

    view() must return something comparable with == (a tuple or dict).
    paint() may return a short text summary used when there's no screen.
    """

    def __init__(self, screen, view, paint, fps=12):
        super().__init__(daemon=True)
        self.screen = screen
        self.view = view
        self.paint = paint
        self.period = 1.0 / fps
        self._stop = threading.Event()

    def run(self):
        last = object()
        while not self._stop.is_set():
            try:
                current = self.view()
                if current != last:
                    last = current
                    image, draw = self.screen.new_frame()
                    summary = self.paint(draw, current) or ""
                    self.screen.show(image, summary)
            except Exception as error:
                print(f"[display] {error}")
            self._stop.wait(self.period)

    def stop(self):
        self._stop.set()


class Edge:
    """Turns a held/not-held reading into one press event, with debounce."""

    def __init__(self, debounce=0.04):
        self.debounce = debounce
        self.down = False
        self.changed_at = 0.0

    def pressed(self, held, now=None):
        now = time.monotonic() if now is None else now
        if held == self.down or now - self.changed_at < self.debounce:
            return False
        self.down = held
        self.changed_at = now
        return held
