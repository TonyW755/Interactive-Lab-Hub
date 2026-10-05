#!/usr/bin/env python3
"""Visitor intercom: the Lab 3 storyboard, acted out on the Pi.
 
  Panel  What happens                          Screen                        LED
  1      "Who are you visiting?" -> Maya Chen  Now recording                 steady green
  2      "Which floor?"          -> Floor 8    Now recording                 steady green
  3      answers are transcribed               Processing your request       blinking green
                                               Maya Chen / Floor 8
  4-5    Maya confirms on her phone            Waiting for confirmation      red
  6      door opens                            Access granted                green
 
Prototype assumptions: the visitor is always here for Maya Chen on floor 8,
and Maya always allows entry. The visitor's answers are still recorded and
transcribed, and printed in the terminal.
 
Run from Lab 3/speech-scripts with the venv active:
    python visitor_intercom.py
"""
 
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
 
import board
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789
from faster_whisper import WhisperModel
 
BASE = Path(__file__).resolve().parent
VOICES_DIR = BASE / "voices"
if not VOICES_DIR.is_dir():
    VOICES_DIR = BASE.parent / "voices"
AUDIO_DIR = Path(tempfile.gettempdir())
 
RESIDENT = "Maya Chen"
FLOOR = 8
RECORD_SECONDS = 5      # how long each answer is recorded
CONFIRM_SECONDS = 4     # pretend Maya takes this long to tap "Allow entry"
DOOR_OPEN_SECONDS = 6   # how long "Access granted" stays on screen
 
GREEN, RED, OFF = "#22dd44", "#ff3333", "#2a2a2a"
 
# ---- Mini PiTFT, 240 x 135 in landscape --------------------------------
# Same pins as the class Lab 2 scripts. If the screen stays blank, try board.CE0.
spi = board.SPI()
cs = digitalio.DigitalInOut(board.D5)
dc = digitalio.DigitalInOut(board.D25)
display = st7789.ST7789(spi, cs=cs, dc=dc, rst=None, baudrate=64000000,
                        width=135, height=240, x_offset=53, y_offset=40)
backlight = digitalio.DigitalInOut(board.D22)
backlight.switch_to_output(value=True)
 
 
def load_font(size):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()
 
 
# Font size depends on how many lines the message has.
FONTS = {1: load_font(26), 2: load_font(24), 3: load_font(19), 4: load_font(16)}
 
 
def show(lines, led=OFF):
    """Draw up to 4 centred lines in a frame, with the status LED below."""
    image = Image.new("RGB", (240, 135), "black")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 236, 100), radius=8, outline="gray", width=2)
 
    font = FONTS[len(lines)]
    line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + 2
    y = 4 + (96 - line_height * len(lines)) / 2
    for line in lines:
        x = (240 - draw.textlength(line, font=font)) / 2
        draw.text((x, y), line, font=font, fill="white")
        y += line_height
 
    draw.ellipse((112, 110, 128, 126), fill=led)
    display.image(image, 90)
 
 
def blink_while(lines, job):
    """Run job in the background while the LED blinks green (panel 3)."""
    with ThreadPoolExecutor(max_workers=1) as worker:
        result = worker.submit(job)
        lit = True
        while not result.done():
            show(lines, GREEN if lit else OFF)
            lit = not lit
            time.sleep(0.4)
    return result.result()
 
 
# ---- Speech ----------------------------------------------------------------
 
def speak(text):
    """Piper neural voice streamed to the speaker, like piper_demo.sh."""
    print(f'Intercom: "{text}"', flush=True)
    piper = subprocess.Popen([
        sys.executable, "-m", "piper",
        "--model", "en_US-lessac-medium",
        "--data-dir", str(VOICES_DIR),
        "--output-raw", "--", text,
    ], stdout=subprocess.PIPE)
    subprocess.run(["aplay", "-q", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"],
                   stdin=piper.stdout, check=True)
    piper.wait()
 
 
def ask(question, question_lines, wav_file):
    """Panels 1 and 2: ask (LED off), then record (LED steady green)."""
    show(question_lines)
    speak(question)
    show(["Now", "recording"], GREEN)
    subprocess.run(["arecord", "-q", "-d", str(RECORD_SECONDS), "-f", "S16_LE",
                    "-c", "1", "-r", "16000", str(wav_file)], check=True)
 
 
def transcribe(wav_file):
    segments, _ = model.transcribe(str(wav_file), language="en",
                                   beam_size=1, vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()
 
 
# ---- The storyboard ----------------------------------------------------------
 
name_wav = AUDIO_DIR / "visitor_name.wav"
floor_wav = AUDIO_DIR / "visitor_floor.wav"
 
try:
    show(["Starting..."])
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
 
    # Panel 1
    ask("Who are you visiting?", ["Who are you", "visiting?"], name_wav)
 
    # Panel 2
    ask("Which floor?", ["Which floor?"], floor_wav)
 
    # Panel 3: transcribe the answers and send the request
    def process_request():
        print("Visitor said:", repr(transcribe(name_wav)), "/",
              repr(transcribe(floor_wav)), flush=True)
        speak(f"Thank you. Contacting {RESIDENT} on floor {FLOOR}.")
 
    blink_while(["Processing", "your request", RESIDENT, f"Floor {FLOOR}"],
                process_request)
 
    # Panels 4 and 5: Maya's phone shows "Visitor at the door."
    # and she taps "Allow entry" (simulated: always allowed)
    show(["Waiting for", "confirmation"], RED)
    speak("Please wait for confirmation.")
    time.sleep(CONFIRM_SECONDS)
    print(f"{RESIDENT} allowed entry.", flush=True)
 
    # Panel 6
    show(["Access", "granted"], GREEN)
    speak("Access granted. Please come in.")
    time.sleep(DOOR_OPEN_SECONDS)
 
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    show([" "])
    backlight.value = False
