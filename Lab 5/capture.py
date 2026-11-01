"""
Bug counter, night 1: record a timelapse of the fly trap. No detection yet; we
collect real frames tonight and build the counter on them afterwards.

    python capture.py --once             # one frame to check framing and focus, then exit
    python capture.py                    # one frame every 5 s until Ctrl-C
    python capture.py --interval 10      # look less often

Frames go to frames/YYYYMMDD/HHMMSS.jpg at 1280x720 (flies are only a few pixels,
so we keep the resolution up). capture_log.jsonl gets one line per frame with the
mean brightness, so in the morning we can tell "no flies" from "the light went off".
Start it in tmux so it survives the ssh disconnect.
"""
import argparse
import datetime
import json
import pathlib
import time

import cv2

parser = argparse.ArgumentParser()
parser.add_argument("--interval", type=float, default=5, help="seconds between frames")
parser.add_argument("--once", action="store_true", help="save one frame as test.jpg and exit")
args = parser.parse_args()

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
if not cap.isOpened():
    raise SystemExit("no webcam found: is it plugged in?")

# The first frames are dark until the camera adjusts its exposure.
t_end = time.time() + 2
while time.time() < t_end:
    cap.read()

if args.once:
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("could not read a frame from the webcam")
    cv2.imwrite("test.jpg", frame)
    print("saved test.jpg")
    raise SystemExit

log = open("capture_log.jsonl", "a")
print("capturing, Ctrl-C to stop", flush=True)
while True:
    try:
        for _ in range(4):          # the webcam buffers a few frames; skip the stale ones
            cap.grab()
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("no frame")
        now = datetime.datetime.now()
        day = pathlib.Path("frames") / f"{now:%Y%m%d}"
        day.mkdir(parents=True, exist_ok=True)
        path = day / f"{now:%H%M%S}.jpg"
        cv2.imwrite(str(path), frame)
        brightness = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())
        log.write(json.dumps({"t": now.isoformat(timespec="seconds"), "frame": str(path),
                              "brightness": round(brightness, 1)}) + "\n")
        log.flush()
        time.sleep(args.interval)
    except KeyboardInterrupt:
        break
    except Exception as e:
        print("hiccup:", e, flush=True)
        time.sleep(args.interval)

cap.release()
print("capture stopped", flush=True)
