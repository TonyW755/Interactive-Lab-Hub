import re
import subprocess
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
 
import numpy as np
import board
import digitalio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789
from faster_whisper import WhisperModel
 
BASE = Path(__file__).resolve().parent
VOICES_DIR = BASE / "voices"
if not VOICES_DIR.is_dir():
    VOICES_DIR = BASE.parent / "voices"
RECORDINGS_DIR = BASE / "recordings"   # the visitor's answers are saved here
RECORDINGS_DIR.mkdir(exist_ok=True)
 
RESIDENT = "Maya Chen"
FLOOR = 8
FLOOR_WORDS = ("8", "8th", "eight", "eighth")   # ways Whisper writes floor 8
 
MIC_DEVICE = None       # e.g. "plughw:3,0" if the default mic is wrong (see arecord -l)
RECORD_SECONDS = 5      # how long each answer is recorded
MAX_TRIES = 2           # each question is asked at most this many times
CONFIRM_SECONDS = 4     # pretend Maya takes this long to tap "Allow entry"
DOOR_OPEN_SECONDS = 6   # how long "Access granted" stays on screen
DENIED_SECONDS = 5      # how long "Access denied" stays on screen
 
GREEN, RED, OFF = "#22dd44", "#ff3333", "#2a2a2a"
 
# ---- Mini PiTFT, 240 x 135 in landscape --------------------------------
# Same pins as the class Lab 2 scripts. If the screen stays blank, try board.CE0.
# If you get "GPIO busy", stop the boot screen first:
#     sudo systemctl stop piscreen.service
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
    """Run job in the background while the LED blinks green, then return its result."""
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
 
 
def record(wav_file):
    """Record the visitor's answer from the USB microphone into wav_file."""
    command = ["arecord", "-q", "-d", str(RECORD_SECONDS), "-f", "S16_LE",
               "-c", "1", "-r", "16000"]
    if MIC_DEVICE:
        command += ["-D", MIC_DEVICE]
    subprocess.run(command + [str(wav_file)], check=True)
 
    # Report how loud the recording was, so a muted mic is easy to spot.
    with wave.open(str(wav_file)) as audio:
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype=np.int16)
    peak = int(np.abs(samples).max()) if samples.size else 0
    print(f"Recorded {samples.size / 16000:.1f}s to {wav_file.name} (peak level {peak})",
          flush=True)
    if peak < 500:
        print("  This recording is almost silent. Check the mic with arecord -l "
              "and alsamixer.", flush=True)
 
 
def transcribe(wav_file):
    segments, _ = model.transcribe(str(wav_file), language="en",
                                   beam_size=1, vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()
 
 
# ---- Checking the answers --------------------------------------------------
 
def is_resident(text):
    """True if the answer contains "Maya Chen". Small slips from Whisper such as
    "Maya Chan" are accepted; other names are not."""
    words = re.findall(r"[a-z]+", text.lower())
    candidates = words + [a + b for a, b in zip(words, words[1:])]
    target = RESIDENT.lower().replace(" ", "")
    return any(SequenceMatcher(None, word, target).ratio() >= 0.85
               for word in candidates)
 
 
def is_resident_floor(text):
    """True if the answer is floor 8."""
    return any(word in FLOOR_WORDS for word in re.findall(r"[a-z0-9]+", text.lower()))
 
 
def ask(question, question_lines, retry, wav_file, is_correct):
    """Panels 1 and 2: ask (LED off), record (steady green), transcribe
    (blinking green). True once the answer is right, False after MAX_TRIES."""
    prompt = question
    for _ in range(MAX_TRIES):
        show(question_lines)
        speak(prompt)
        show(["Now", "recording"], GREEN)
        record(wav_file)
        heard = blink_while(["Processing"], lambda: transcribe(wav_file))
        correct = is_correct(heard)
        print(f'Visitor said: "{heard}" -> {"accepted" if correct else "not accepted"}',
              flush=True)
        if correct:
            return True
        prompt = retry
    return False
 
 
def deny(message):
    show(["Access", "denied"], RED)
    speak(message)
    time.sleep(DENIED_SECONDS)
 
 
# ---- The storyboard ----------------------------------------------------------
 
def visit():
    # Panel 1: only visitors for Maya Chen go further
    if not ask("Who are you visiting?", ["Who are you", "visiting?"],
               "Sorry, I didn't catch that. Who are you visiting?",
               RECORDINGS_DIR / "visitor_name.wav", is_resident):
        deny("Sorry, there is no resident by that name.")
        return
 
    # Panel 2: and only if they say floor 8
    if not ask("Which floor?", ["Which floor?"],
               "Sorry, I didn't catch the floor number. Which floor?",
               RECORDINGS_DIR / "visitor_floor.wav", is_resident_floor):
        deny(f"Sorry, {RESIDENT} does not live on that floor.")
        return
 
    # Panel 3: send the request, LED blinking green
    blink_while(["Processing", "your request", RESIDENT, f"Floor {FLOOR}"],
                lambda: speak(f"Thank you. Contacting {RESIDENT} on floor {FLOOR}."))
 
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
 
 
try:
    show(["Starting..."])
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    visit()
except KeyboardInterrupt:
    print("\nStopped.")
finally:
    show([" "])
    backlight.value = False
 
