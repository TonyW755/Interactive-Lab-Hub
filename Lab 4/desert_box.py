"""ECE5413 Lab 4: Qwiic joystick + Servo pHAT channel 0 + speaker.

Run on the Raspberry Pi: python dessert_box.py
Uses the same two-argument servo command and melody as Part 1.
"""

import math
import shutil
import subprocess
import sys
import threading
import time
from array import array

SERVO_CHANNEL = 0
SERVO_MIN = 0.0
SERVO_MAX = 120.0
START_ANGLE = 0.0       # Starts at the OPEN endpoint, per the latest requirement.
DEGREES_PER_TURN = 30.0  # Four joystick revolutions cover the full lid travel.
CENTER_X = 504.0
CENTER_Y = 515.0
CENTER_RADIUS = 180.0
ANGLE_THRESHOLD = 2.0   # Accumulate small movements; suppress stationary noise.
DIRECTION = -1         # Clockwise decreases angle toward OPEN=0; CLOSED=120.
STOP_DELAY = 0.20
SAMPLE_INTERVAL = 0.02
MAX_SAMPLE_GAP = 0.20
MAX_ANGLE_JUMP = 90.0
AUDIO_DEVICE = None    # None uses the same default output as Part 1.
SAMPLE_RATE = 44100
BPM = 120
VOLUME = 0.25
TRANSPOSE = 0

LE_FESTIN = [
    ("Bb3", 0.5),
    ("G4", 1), ("F4", 1), ("Eb4", 1),
    ("G4", 1), ("F4", 1.5), ("Eb4", 0.5),
    ("G4", 1), ("F4", 1), ("Eb4", 1),
    ("Bb3", 2), ("Bb3", 1),
    ("Bb4", 1), ("F4", 1), ("Eb4", 1),
    ("Bb4", 1), ("D4", 1.5), ("D4", 0.5),
    ("Bb4", 1), ("F4", 1.5), ("D4", 0.5),
    ("Eb4", 2), ("F4", 0.5), ("Bb4", 0.5),
    ("G4", 1), ("F4", 1), ("Eb4", 1),
    ("G4", 1), ("F4", 1.5), ("A4", 0.5),
    ("Bb4", 1), ("G4", 1), ("Bb4", 1),
    ("C5", 2), ("rest", 1),
    ("Bb4", 1), ("F4", 1), ("Eb4", 1),
    ("Bb3", 1), ("D4", 1.5), ("C5", 0.5),
    ("D5", 1), ("D5", 1), ("Bb4", 0.5),
    ("C5", 2.5), ("rest", 0.5), ("G4", 0.5),
    ("A4", 1), ("Eb4", 1.5), ("C4", 0.5),
    ("D4", 2), ("G4", 0.75), ("G4", 0.25),
    ("Eb4", 3),
]


def note_frequency(note):
    pitch = {"C": 0, "D": 2, "E": 4, "F": 5,
             "G": 7, "A": 9, "B": 11}[note[0]]
    start = 1
    if note[1:2] in ("#", "b"):
        pitch += 1 if note[1] == "#" else -1
        start = 2
    midi = (int(note[start:]) + 1) * 12 + pitch + TRANSPOSE
    return 440.0 * 2 ** ((midi - 69) / 12)


def create_audio():
    """Generate the Part 1 melody as little-endian, mono, 16-bit PCM."""
    data = bytearray()
    for note, beats in LE_FESTIN:
        count = round(beats * 60.0 / BPM * SAMPLE_RATE)
        samples = array("h", [0]) * count
        if note != "rest":
            frequency = note_frequency(note)
            fade = max(1, min(int(0.005 * SAMPLE_RATE), count // 2))
            for i in range(count):
                t = i / SAMPLE_RATE
                envelope = min(1.0, i / fade, (count - 1 - i) / fade)
                envelope *= math.exp(-2.8 * t)
                phase = 2 * math.pi * frequency * t
                tone = (math.sin(phase) + 0.22 * math.sin(2 * phase)
                        + 0.08 * math.sin(3 * phase)) / 1.3
                samples[i] = round(32767 * VOLUME * envelope * tone)
        if sys.byteorder != "little":
            samples.byteswap()
        data.extend(samples.tobytes())
    return bytes(data)


class RotationController:
    """Convert measured rotation into bounded lid-position commands."""

    def __init__(self):
        self.position = START_ANGLE
        self.anchor = None
        self.last_sample = None
        self.last_motion = -math.inf

    def update(self, x, y, now):
        if not (0 <= x <= 1023 and 0 <= y <= 1023):
            raise ValueError("Invalid joystick reading")
        up, right = x - CENTER_X, y - CENTER_Y
        gap = (self.last_sample is not None
               and now - self.last_sample > MAX_SAMPLE_GAP)
        self.last_sample = now
        if math.hypot(up, right) < CENTER_RADIUS:
            self.anchor = None
            self.last_motion = -math.inf
            return self.position, False

        # Part 1 calibration: X increases upward; Y increases rightward.
        # This angle increases clockwise: up -> right -> down -> left.
        angle = math.degrees(math.atan2(right, up))
        if self.anchor is None or gap:
            self.anchor = angle
            self.last_motion = -math.inf
            return self.position, False

        # Correctly cross the -180/+180 degree boundary.
        delta = (angle - self.anchor + 180.0) % 360.0 - 180.0
        if abs(delta) > MAX_ANGLE_JUMP:
            # Ignore ambiguous jumps or a fast movement across the center.
            self.anchor = angle
            self.last_motion = -math.inf
            return self.position, False
        if abs(delta) >= ANGLE_THRESHOLD:
            self.anchor = angle
            self.last_motion = now
            self.position = max(SERVO_MIN, min(
                SERVO_MAX,
                self.position + DIRECTION * delta * DEGREES_PER_TURN / 360.0,
            ))
        return self.position, now - self.last_motion < STOP_DELAY


class MusicPlayer:
    """Stream music or silence on a separate thread; retain song position."""

    def __init__(self, player, audio):
        if not audio or len(audio) % 2:
            raise ValueError("Audio must contain complete 16-bit samples")
        self.audio = audio
        self.cursor = 0
        self.active_until = 0.0
        self.stopping = threading.Event()
        self.error = None
        command = [player, "-q", "-t", "raw", "-f", "S16_LE",
                   "-r", str(SAMPLE_RATE), "-c", "1",
                   "--buffer-time=100000", "--period-time=20000"]
        if AUDIO_DEVICE:
            command.extend(["-D", AUDIO_DEVICE])
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, bufsize=0)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def set_moving(self, moving):
        # Expire automatically if the control loop stalls.
        self.active_until = time.monotonic() + 0.10 if moving else 0.0

    def next_chunk(self, moving, size):
        if not moving:
            return bytes(size)
        result = bytearray()
        while len(result) < size:
            count = min(size - len(result), len(self.audio) - self.cursor)
            result.extend(self.audio[self.cursor:self.cursor + count])
            self.cursor = (self.cursor + count) % len(self.audio)
        return bytes(result)

    def _run(self):
        size = round(SAMPLE_RATE * 0.02) * 2
        deadline = time.monotonic()
        try:
            while not self.stopping.is_set():
                data = self.next_chunk(time.monotonic() < self.active_until, size)
                remaining = memoryview(data)
                while remaining and not self.stopping.is_set():
                    count = self.process.stdin.write(remaining)
                    if not count:
                        raise BrokenPipeError("Audio output stopped")
                    remaining = remaining[count:]
                # Limit queued audio so stopping does not leave a long tail.
                deadline += 0.02
                now = time.monotonic()
                if deadline < now - 0.10:
                    deadline = now
                self.stopping.wait(max(0.0, deadline - now))
        except Exception as error:
            if not self.stopping.is_set():
                self.error = error

    def check(self):
        if self.error is not None or self.process.poll() is not None:
            raise RuntimeError("Audio playback failed; check the speaker/output")

    def close(self):
        self.stopping.set()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.thread.join(timeout=2)
        self.process.stdin.close()


def main():
    import pi_servo_hat
    import qwiic_joystick

    servo = pi_servo_hat.PiServoHat()
    servo.restart()
    # Preserve the exact pulse mapping used in the successful Part 1 test.
    servo.move_servo_position(SERVO_CHANNEL, START_ANGLE)
    print("Servo commanded to 0 degrees (OPEN endpoint).")

    joystick = qwiic_joystick.QwiicJoystick()
    if not joystick.connected:
        raise RuntimeError("Qwiic Joystick is not connected")
    if joystick.begin() is False:
        raise RuntimeError("Could not initialize the joystick")
    player = shutil.which("aplay")
    if player is None:
        raise RuntimeError("aplay is missing. Install with: sudo apt install alsa-utils")

    print("Preparing the Part 1 melody...")
    music = MusicPlayer(player, create_audio())
    controller = RotationController()
    last_command = START_ANGLE
    next_status = 0.0
    print("Ready. Rotate clockwise to open; counterclockwise to close.")
    print("Keep the joystick tilted away from center while circling. Ctrl+C exits.")
    try:
        while True:
            start = time.monotonic()
            x, y = joystick.horizontal, joystick.vertical
            now = time.monotonic()
            position, moving = controller.update(x, y, now)
            if position != last_command:
                servo.move_servo_position(SERVO_CHANNEL, position)
                last_command = position
            music.set_moving(moving)
            music.check()
            if now >= next_status:
                print(f"Lid command: {position:6.1f} deg | "
                      f"Music: {'playing' if moving else 'paused'}")
                next_status = now + 0.5
            time.sleep(max(0.0, SAMPLE_INTERVAL - (time.monotonic() - start)))
    finally:
        music.close()
        # Hold the last command instead of unexpectedly closing on exit.
        print(f"Stopped. Last lid command: {last_command:.1f} degrees.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Exiting.")
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
