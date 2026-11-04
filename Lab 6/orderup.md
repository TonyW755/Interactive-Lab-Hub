diff --git a/Lab 6/GAME_PLAN.md b/Lab 6/GAME_PLAN.md
index b3f668c..efcddda 100644
--- a/Lab 6/GAME_PLAN.md	
+++ b/Lab 6/GAME_PLAN.md	
@@ -2,7 +2,7 @@
 
 A co-op kitchen game for three players and three Raspberry Pis. Orders appear on a shared screen, and the team has to prep and serve them before time runs out.
 
-**Status:** proposal for the team to review. Nothing here is built yet. Numbers such as timers and scores are starting guesses to tune in playtesting.
+**Status:** software implementation is available in [order-up/](order-up/README.md): game rules, shared screen, simulators, MQTT and Pi clients. Automated and laptop checks are complete; physical parts checks, sensor calibration, campus-network measurements and user playtests remain. Numbers such as timers and scores are starting guesses to tune in playtesting.
 
 "Order Up!" is a working title. The idea comes from co-op kitchen games we like, but the name, art, recipes and rules are our own.
 
diff --git a/Lab 6/README.md b/Lab 6/README.md
index 714ccaf..dcbe85a 100644
--- a/Lab 6/README.md	
+++ b/Lab 6/README.md	
@@ -1,3 +1,5 @@
+> **Order Up! implementation:** See [order-up/README.md](order-up/README.md) for the playable laptop simulator, Pi setup, MQTT configuration and tests. The original lab brief follows.
+
 # Distributed Interaction
 
 **NAMES OF COLLABORATORS HERE**
diff --git a/Lab 6/order-up/.env.example b/Lab 6/order-up/.env.example
new file mode 100644
index 0000000..6494352
--- /dev/null
+++ b/Lab 6/order-up/.env.example	
@@ -0,0 +1,7 @@
+# Load manually: set -a; source .env; set +a
+MQTT_HOST=127.0.0.1
+MQTT_PORT=1883
+MQTT_USERNAME=
+MQTT_PASSWORD=
+MQTT_TLS=0
+ORDERUP_TOPIC=IDD/orderup
diff --git a/Lab 6/order-up/.gitignore b/Lab 6/order-up/.gitignore
new file mode 100644
index 0000000..a98520d
--- /dev/null
+++ b/Lab 6/order-up/.gitignore	
@@ -0,0 +1,4 @@
+.venv/
+__pycache__/
+*.pyc
+.env
diff --git a/Lab 6/order-up/README.md b/Lab 6/order-up/README.md
new file mode 100644
index 0000000..ffc6bb2
--- /dev/null
+++ b/Lab 6/order-up/README.md	
@@ -0,0 +1,191 @@
+# Order Up!
+
+A three-player co-op kitchen game implementing [the Lab 6 game plan](../GAME_PLAN.md). One laptop owns the rules; three Raspberry Pis act as Runner, Chopper and Cook. A browser shows the shared kitchen. Everything can also be played on a laptop with no broker or hardware.
+
+**Implemented:** rules, shared screen, browser and terminal simulators, MQTT transport, three Pi clients, hardware-independent controls, and automated tests. **Still requires the team:** hardware assembly and calibration, campus-network measurement, physical playtests, props, and user-test evidence. No physical hardware was connected during implementation.
+
+## Play on a laptop
+
+Use Python 3.10 or newer. From this `order-up` directory:
+
+```bash
+python3 -m venv .venv
+source .venv/bin/activate
+python -m pip install -r requirements-server.txt
+python -m server.app --port 5056
+```
+
+Open **http://127.0.0.1:5056/sim** and click **Start service**. Use **http://127.0.0.1:5056/** for the shared screen. Browser assets are bundled; after installing dependencies, practice mode needs no internet connection.
+
+- Runner: click an ingredient to get it; select a counter slot and choose Send to Chop, Send to Cook or Trash. Click a ticket to serve it.
+- Chopper: click Chop or press **C**, six times per ingredient.
+- Cook: click Stir or press **S** (three ticks); after eight such presses, press **P** to pull. You have eight seconds after reaching 100%.
+- The round ends automatically after three minutes. **Another round** starts a fresh game. An active round cannot be restarted accidentally.
+
+Optional reproducible or short playtests:
+
+```bash
+python -m server.app --port 5056 --seed 1 --round-seconds 30
+```
+
+The default port without `--port` is 5000. If another app occupies it, use 5056 or another free port. Keep one server per topic prefix. The server runs in Flask-SocketIO's `threading` mode, with debug/reloader disabled. This is a classroom/LAN application, with no player authentication or persistent game storage.
+
+### Terminal controls
+
+In three terminals, with the same virtual environment activated:
+
+```bash
+python sim/sim_station.py runner --url http://127.0.0.1:5056
+python sim/sim_station.py chop --url http://127.0.0.1:5056
+python sim/sim_station.py cook --url http://127.0.0.1:5056
+```
+
+Commands:
+
+| Role | Commands |
+|---|---|
+| Any | `state`, `help`, `quit`; `start` in HTTP mode |
+| Runner | `get lettuce`, `get tomato`, `get patty`, `get bun`, `send 1 chop`, `send 1 cook`, `trash 1`, `serve 1` |
+| Chopper | `chop` |
+| Cook | `stir` (3 ticks), `stir 1`, `pull` |
+
+Terminal slot numbers are **1–6**. MQTT and HTTP JSON slot indices are **0–5**. `serve` takes the ticket's displayed ID, not its position in the list.
+
+## Connect three Pis
+
+Use a separate `order-up` virtual environment: this implementation uses **paho-mqtt 2.x**, whereas the earlier pixel-grid demo pins 1.x. Do not install both lab requirement sets into the same environment.
+
+1. On each Pi, enable I²C/SPI as in Labs 2–4, run `i2cdetect -y 1`, and confirm the relevant Lab 4 example works.
+2. Copy this directory to each Pi, then install its requirements:
+
+   ```bash
+   python3 -m venv --system-site-packages .venv
+   source .venv/bin/activate
+   python -m pip install -r requirements-pi.txt
+   sudo systemctl stop piscreen.service
+   ```
+
+3. Set the same broker and topic prefix in every terminal (laptop and Pis). Defaults are `127.0.0.1`, port `1883`, no credentials, prefix `IDD/orderup`. For the lab broker, use:
+
+   ```bash
+   export MQTT_HOST=farlab.infosci.cornell.edu
+   export MQTT_PORT=1883
+   export MQTT_USERNAME=idd
+   # Set MQTT_PASSWORD to the value in the Lab 6 README.
+   export ORDERUP_TOPIC=IDD/orderup
+   ```
+
+   `MQTT_PASSWORD` is read from the environment and never logged. `MQTT_TLS=1` enables certificate-verified TLS; set the port to the broker's TLS port as well. For local Mosquitto, use the laptop's LAN address on the Pis and configure a listener they can reach. Use a unique prefix for independent teams or test games.
+
+4. On the laptop:
+
+   ```bash
+   python -m server.app --mqtt --host 0.0.0.0 --port 5056
+   ```
+
+   Open `http://LAPTOP_IP:5056/` on the display. The browser host option is independent of the broker address. With the display on the same laptop, the default loopback host also works with remote Pis over MQTT.
+
+5. On the appropriate Pi, run one command:
+
+   ```bash
+   python -m pi.chop_station
+   python -m pi.cook_station
+   python -m pi.runner_station
+   ```
+
+Each client reconnects automatically, subscribes to retained state, publishes retained presence with a last will, and waits for a **live** server heartbeat before accepting gameplay. A cached retained snapshot alone does not enable controls. Presence on the shared screen describes MQTT stations; browser/HTTP simulator controls work even when all Pi labels say offline.
+
+To replace a hardware station with a laptop terminal while testing MQTT:
+
+```bash
+python sim/sim_station.py runner --mqtt
+python sim/sim_station.py chop --mqtt
+python sim/sim_station.py cook --mqtt
+```
+
+Run only one client for each role when interpreting its online indicator. Server and all clients must share the same broker/prefix.
+
+### Hardware and calibration
+
+| Pi | Hardware / defaults | Tuning |
+|---|---|---|
+| Chop | LSM6DS3 at `0x6A`, ±8g range / 208 Hz sensor rate, sampled about 100 Hz | `--threshold 12 --cooldown 0.3`; threshold is deviation from gravity in m/s². A chop requires the signal to settle before rearming. Test actual chops, carrying the knife, and bumps to the table. |
+| Cook | Seesaw encoder at `0x36`; switch pin 24; NeoPixel pin 6; Servo pHAT channel 0 | `--servo-channel 0 --servo-min 0 --servo-max 120`; `--no-servo` allows encoder-only bring-up. Supply the Servo pHAT's **separate USB-C power**. |
+| Runner | Qwiic joystick, active-low press | Defaults follow the team's Lab 4 orientation: horizontal reading increases upward, vertical increases rightward, centers 504/515. Adjust with `--swap-axes`, `--invert-up`, `--invert-right`, `--center-up`, `--center-right`. |
+| All | Mini PiTFT: CS GPIO5, DC GPIO25, backlight GPIO22, top button GPIO23; 240×135 landscape | `--headless` skips the screen and prints status for hardware bring-up. Runner's top-button back control requires the display wiring. |
+
+Runner home: **up Get / right Send / left Trash / down Serve**. Within lists, up/down selects, press confirms, left goes back. In Send's station choice, **left means Chop, right means Cook**; use the PiTFT top button to go back. Return the joystick to center between flicks. Lists capture item versions/ticket IDs, so a stale selection is rejected instead of acting on a different item.
+
+Cook batches absolute encoder movement at most five times per second; either direction stirs. The servo goes from cold to done to burning, and the LED is blue while cooking, flashing amber when done, green while safely waiting, red when burnt. Pulling before completion is rejected. After burning, Pull still removes the food so the Runner can trash it. On exit or lost live state the servo returns to its configured cold endpoint.
+
+### Measure the network
+
+With the server running with `--mqtt`, run on **each Pi**:
+
+```bash
+python sim/network_check.py --count 10
+```
+
+This measures Pi → broker → game server → broker → Pi round-trip time. Record replies, median and maximum in the lab writeup. Timeouts fail with a nonzero exit code. Local test measurements are not campus Wi-Fi results.
+
+## Rules and implementation decisions
+
+- Six counter slots; one item per station. A completed chop returns automatically, or waits if full.
+- Cook takes 24 encoder ticks. Progress stops without input. After completion there are eight seconds to Pull; the deadline is inclusive (a pull exactly at eight seconds is too late).
+- **Pull removes heat immediately.** If the counter is full, pulled food waits safely at Cook; it does not burn while waiting. If both stations are waiting, Chop receives the next free counter slot first.
+- Invalid prep paths produce ruined food when preparation finishes. Burnt and ruined items consume slots until trashed and cannot satisfy a recipe.
+- Salad: chopped lettuce + chopped tomato, 10 points. Burger: bun + cooked patty + chopped lettuce, 20 points. Soup: chop tomato, then cook it, 20 points.
+- The first order arrives immediately; another arrives every 20 seconds, up to four. Each lasts 60 seconds. Tip = `floor(seconds_remaining / 10)`. Expiration costs 10; scores may go negative. Serving is atomic: missing ingredients remove nothing.
+- A round lasts 180 seconds. There is no extra penalty for tickets still pending at the end. No new orders arrive at the round endpoint; expirations at the endpoint still count. A server restart starts in the lobby.
+
+All tunable defaults live in `server/game.py:Rules`. These choices are starting values for playtesting.
+
+## Protocol and code
+
+The implementation follows the plan's `chop/event`, `cook/event`, `runner/action`, `state`, `runner/result` and `<role>/online` topics. Additional topics:
+
+- `cook/result`: acknowledgement for reliable Pull events.
+- `server/online`: retained presence plus one-second heartbeat, with last will `0`.
+- `ping` / `pong`: diagnostic round-trip probes with matching `id`.
+
+State adds `round_id`, `counter_versions`, station `waiting`, `online`, `message`, recipe/rule metadata and the network mode. Clients add `round_id` to events and `version` to slot actions. The server accepts the original plan's simpler payloads too. Retained action messages are ignored. Confirmed actions use UUIDs; the server caches the latest 4,096 IDs across rounds, and retries return the original result without repeating the action. The hardware clients retry unanswered reliable actions with the same ID. State publishes on change at up to 5 Hz, with a one-second heartbeat even when unchanged. A lock serializes HTTP, MQTT and timer mutations.
+
+| File | Responsibility |
+|---|---|
+| `server/game.py` | Rules only, injectable clock and random generator |
+| `server/app.py` | Flask routes, Socket.IO, MQTT, serialized authoritative loop |
+| `server/templates/`, `server/static/` | Shared screen and browser simulator; vendored Socket.IO 4.8.1 with license |
+| `pi/common.py` | Broker configuration, reconnect, reliable actions, freshness checks |
+| `pi/controls.py` | Pure gesture detectors and Runner menu |
+| `pi/display.py` | Mini PiTFT drawing and top-button input |
+| `pi/*_station.py` | Real sensor/actuator loops |
+| `sim/` | Terminal clients and RTT tool |
+| `tests/` | Rules, controls, HTTP/Socket.IO, MQTT routing, optional real-broker smoke test |
+
+Computation follows the plan: Pis translate sensors into discrete events and render local menus; the laptop owns all rules and timing; browsers draw snapshots. No language model is part of the running game.
+
+## Verify
+
+```bash
+python -m unittest discover -s tests -v
+```
+
+The suite covers all recipes, invalid prep, atomic serving, six-slot backpressure, busy stations, deadlines, pause-free cooking, deduplication, stale choices, round rollover, malformed input, gestures, menus, HTTP/Socket.IO and MQTT routing.
+
+Optional real-network integration test, using an isolated temporary local broker on port 18884:
+
+```bash
+python -m pip install 'amqtt>=0.11,<1'
+python tests/mqtt_smoke.py
+```
+
+The broker dependency is only for testing; actual play uses your chosen broker. The smoke test launches all three MQTT clients, prepares and serves soup, checks duplicate Get/Pull delivery, restarts Runner, verifies presence and RTT, then checks that server loss pauses input. It does not contact the campus broker.
+
+## Team handoff
+
+1. Confirm each Pi's parts and power, then tune chop detection and joystick orientation.
+2. Run the RTT tool from all three Pis on the intended Wi-Fi.
+3. Play full rounds; record score, idle station time, mistaken actions and counter jams. Tune the rule defaults.
+4. Build and strain-relieve the props; test them with real swings.
+5. Test with two or more people outside the team and capture consented photos/video and feedback.
+6. Replace the lab assignment text with the team's actual build narrative, results and reflection. Do not report these physical milestones as completed until they are.
diff --git a/Lab 6/order-up/pi/__init__.py b/Lab 6/order-up/pi/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/Lab 6/order-up/pi/chop_station.py b/Lab 6/order-up/pi/chop_station.py
new file mode 100644
index 0000000..a79816c
--- /dev/null
+++ b/Lab 6/order-up/pi/chop_station.py	
@@ -0,0 +1,48 @@
+"""Run on the Chop Pi: python -m pi.chop_station."""
+import argparse
+import time
+from pi.common import StationClient
+from pi.controls import ChopDetector
+from pi.display import Display
+
+
+def main():
+    parser = argparse.ArgumentParser()
+    parser.add_argument("--headless", action="store_true")
+    parser.add_argument("--threshold", type=float, default=12, help="Acceleration magnitude deviation from gravity, m/s²")
+    parser.add_argument("--cooldown", type=float, default=0.3)
+    args = parser.parse_args()
+    if args.threshold <= 0 or args.cooldown <= 0:
+        parser.error("threshold and cooldown must be positive")
+    import board
+    from adafruit_lsm6ds import AccelRange, Rate
+    from adafruit_lsm6ds.lsm6ds3 import LSM6DS3
+    sensor = LSM6DS3(board.I2C(), address=0x6A)
+    sensor.accelerometer_range = AccelRange.RANGE_8G
+    sensor.accelerometer_data_rate = Rate.RATE_208_HZ
+    detector = ChopDetector(args.threshold, args.cooldown)
+    display = Display(args.headless)
+    client = StationClient("chop")
+    client.start()
+    try:
+        while True:
+            state, result = client.snapshot()
+            station = state.get("chop", {})
+            detected = detector.sample(sensor.acceleration, time.monotonic())
+            if detected and client.ready() and station.get("item") and not station.get("waiting"):
+                client.send({"type": "chop"})
+            hint = "Waiting for counter" if station.get("waiting") else "Chop to prepare"
+            display.show("CHOP / " + state.get("phase", "offline"), [str(station.get("item") or "Empty board").replace("_", " "),
+                         f"{station.get('progress', 0)} / {station.get('needed', 6)} chops", hint,
+                         "LIVE" if client.ready() else "Waiting for live round"])
+            client.service()
+            time.sleep(0.01)
+    except KeyboardInterrupt:
+        pass
+    finally:
+        client.close()
+        display.close()
+
+
+if __name__ == "__main__":
+    main()
diff --git a/Lab 6/order-up/pi/common.py b/Lab 6/order-up/pi/common.py
new file mode 100644
index 0000000..52a0579
--- /dev/null
+++ b/Lab 6/order-up/pi/common.py	
@@ -0,0 +1,132 @@
+"""MQTT transport shared by hardware clients and the terminal simulator."""
+import json
+import os
+import threading
+import time
+import uuid
+
+
+def topic(suffix):
+    return os.getenv("ORDERUP_TOPIC", "IDD/orderup").rstrip("/") + "/" + suffix
+
+
+def make_client(name):
+    import paho.mqtt.client as mqtt
+    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"orderup-{name}-{uuid.uuid4().hex[:12]}")
+    username = os.getenv("MQTT_USERNAME")
+    if username:
+        client.username_pw_set(username, os.getenv("MQTT_PASSWORD", ""))
+    if os.getenv("MQTT_TLS", "0") == "1":
+        client.tls_set()
+    client.reconnect_delay_set(min_delay=1, max_delay=10)
+    client.max_queued_messages_set(32)
+    return client
+
+
+def connect(client):
+    client.connect_async(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")), keepalive=10)
+    client.loop_start()
+
+
+class StationClient:
+    def __init__(self, role):
+        self.role = role
+        self.client = make_client(role)
+        self.client.will_set(topic(f"{role}/online"), "0", qos=1, retain=True)
+        self.client.on_connect = self._connected
+        self.client.on_disconnect = self._disconnected
+        self.client.on_message = self._message
+        self.lock = threading.Lock()
+        self.state = {}
+        self.result = "Connecting…"
+        self.received_at = 0
+        self.server_online = False
+        self.server_seen_at = 0
+        self.connected = False
+        self.pending = {}
+
+    def _connected(self, client, userdata, flags, reason, properties):
+        self.connected = not reason.is_failure
+        if self.connected:
+            client.subscribe([(topic("state"), 1), (topic("server/online"), 1), (topic(f"{self.role}/result"), 1)])
+            client.publish(topic(f"{self.role}/online"), "1", qos=1, retain=True)
+
+    def _disconnected(self, client, userdata, flags, reason, properties):
+        with self.lock:
+            self.connected = False
+            self.server_online = False
+            self.received_at = 0
+            self.result = "Disconnected — reconnecting"
+
+    def _message(self, client, userdata, message):
+        try:
+            with self.lock:
+                if message.topic == topic("server/online"):
+                    self.server_online = message.payload == b"1"
+                    # A retained '1' alone is not proof that the server is alive.
+                    if not message.retain and self.server_online:
+                        self.server_seen_at = time.monotonic()
+                    return
+                data = json.loads(message.payload)
+                if not isinstance(data, dict):
+                    return
+                if message.topic == topic("state"):
+                    self.state = data
+                    if not message.retain:
+                        self.received_at = time.monotonic()
+                else:
+                    self.result = str(data.get("msg", ""))
+                    self.pending.pop(data.get("id"), None)
+        except (ValueError, TypeError):
+            pass
+
+    def start(self):
+        connect(self.client)
+
+    def snapshot(self):
+        with self.lock:
+            return self.state, self.result
+
+    def ready(self):
+        return (self.connected and self.server_online and time.monotonic() - self.received_at < 3
+                and time.monotonic() - self.server_seen_at < 3 and self.state.get("phase") == "playing")
+
+    def send(self, payload):
+        with self.lock:
+            if not self.ready():
+                self.result = "Waiting for live server / round"
+                return False
+            payload = dict(payload)
+            payload.setdefault("round_id", self.state["round_id"])
+            reliable = self.role == "runner" or payload.get("type") == "pull"
+            if reliable:
+                payload.setdefault("id", uuid.uuid4().hex)
+            suffix = "action" if self.role == "runner" else "event"
+            info = self.client.publish(topic(f"{self.role}/{suffix}"), json.dumps(payload), qos=int(reliable))
+            if info.rc != 0:
+                self.result = "Send failed — try again"
+                return False
+            if reliable:
+                self.pending[payload["id"]] = (payload, time.monotonic())
+                self.result = "Sent…"
+            return True
+
+    def service(self):
+        # Application-level retries reuse the same ID, so a lost result is harmless.
+        with self.lock:
+            if not self.ready():
+                return
+            now = time.monotonic()
+            for action_id, (payload, sent) in list(self.pending.items()):
+                if payload["round_id"] != self.state["round_id"]:
+                    self.pending.pop(action_id)
+                elif now - sent >= 2:
+                    suffix = "action" if self.role == "runner" else "event"
+                    self.client.publish(topic(f"{self.role}/{suffix}"), json.dumps(payload), qos=1)
+                    self.pending[action_id] = (payload, now)
+
+    def close(self):
+        if self.client.is_connected():
+            self.client.publish(topic(f"{self.role}/online"), "0", qos=1, retain=True).wait_for_publish(timeout=1)
+        self.client.disconnect()
+        self.client.loop_stop()
diff --git a/Lab 6/order-up/pi/controls.py b/Lab 6/order-up/pi/controls.py
new file mode 100644
index 0000000..dca639a
--- /dev/null
+++ b/Lab 6/order-up/pi/controls.py	
@@ -0,0 +1,119 @@
+"""Hardware-independent gesture detection and Runner menus."""
+import math
+
+
+class ChopDetector:
+    def __init__(self, threshold=12.0, cooldown=0.3):
+        self.threshold = threshold
+        self.cooldown = cooldown
+        self.last_chop = -math.inf
+        self.armed = True
+
+    def sample(self, acceleration, now):
+        impact = abs(math.sqrt(sum(a * a for a in acceleration)) - 9.81)
+        if impact < self.threshold * 0.4:
+            self.armed = True
+        if self.armed and impact >= self.threshold and now - self.last_chop >= self.cooldown:
+            self.last_chop = now
+            self.armed = False
+            return True
+        return False
+
+
+class FlickDetector:
+    def __init__(self, center_up=504, center_right=515, threshold=240, invert_up=False, invert_right=False):
+        self.center_up, self.center_right = center_up, center_right
+        self.threshold = threshold
+        self.up_sign = -1 if invert_up else 1
+        self.right_sign = -1 if invert_right else 1
+        self.armed = True
+
+    def sample(self, up_axis, right_axis):
+        up = (up_axis - self.center_up) * self.up_sign
+        right = (right_axis - self.center_right) * self.right_sign
+        if max(abs(up), abs(right)) < self.threshold * 0.55:
+            self.armed = True
+        if not self.armed or max(abs(up), abs(right)) < self.threshold:
+            return None
+        self.armed = False
+        return ("up" if up > 0 else "down") if abs(up) >= abs(right) else ("right" if right > 0 else "left")
+
+
+class PressDetector:
+    def __init__(self, cooldown=0.15):
+        self.held = False
+        self.last_press = -math.inf
+        self.cooldown = cooldown
+
+    def sample(self, pressed, now):
+        edge = pressed and not self.held and now - self.last_press >= self.cooldown
+        self.held = pressed
+        if edge:
+            self.last_press = now
+        return edge
+
+
+class RunnerMenu:
+    def __init__(self):
+        self.round_id = None
+        self.reset()
+
+    def reset(self):
+        self.mode = "home"
+        self.entries = []
+        self.index = 0
+        self.selected = None
+
+    def sync(self, state):
+        if state.get("round_id") != self.round_id or state.get("phase") != "playing":
+            self.reset()
+        self.round_id = state.get("round_id")
+
+    def input(self, event, state):
+        self.sync(state)
+        if event == "back":
+            self.reset()
+            return None
+        if self.mode == "home":
+            action = {"up": "get", "right": "send", "left": "trash", "down": "serve"}.get(event)
+            if not action:
+                return None
+            self.mode = action
+            self.index = 0
+            if action == "get":
+                self.entries = [(item.title(), {"item": item}) for item in ("lettuce", "tomato", "patty", "bun")]
+            elif action == "serve":
+                self.entries = [(f"#{t['id']} {t['recipe']}", {"ticket": t["id"]}) for t in state.get("tickets", [])]
+            else:
+                self.entries = [(f"{i+1}: {item.replace('_', ' ')}", {"slot": i, "version": state["counter_versions"][i]})
+                                for i, item in enumerate(state.get("counter", [])) if item]
+            return None
+        if self.mode == "station":
+            if event in ("left", "right"):
+                payload = {"action": "send", **self.selected, "to": "chop" if event == "left" else "cook", "round_id": self.round_id}
+                self.reset()
+                return payload
+            return None
+        if event == "left":
+            self.reset()
+        elif event in ("up", "down") and self.entries:
+            self.index = (self.index + (-1 if event == "up" else 1)) % len(self.entries)
+        elif event == "press" and self.entries:
+            entry = self.entries[self.index][1]
+            if self.mode == "send":
+                self.selected = entry
+                self.mode = "station"
+            else:
+                payload = {"action": self.mode, **entry, "round_id": self.round_id}
+                self.reset()
+                return payload
+        return None
+
+    def lines(self):
+        if self.mode == "home":
+            return ["UP Get / RIGHT Send", "LEFT Trash / DOWN Serve", "Flick, then release"]
+        if self.mode == "station":
+            return ["LEFT: Chop", "RIGHT: Cook", "Top button: back"]
+        if not self.entries:
+            return [self.mode.upper(), "Nothing available", "LEFT: back"]
+        return [self.mode.upper() + f" ({self.index+1}/{len(self.entries)})", "> " + self.entries[self.index][0], "UP/DOWN pick; press OK", "LEFT: back"]
diff --git a/Lab 6/order-up/pi/cook_station.py b/Lab 6/order-up/pi/cook_station.py
new file mode 100644
index 0000000..6f6c760
--- /dev/null
+++ b/Lab 6/order-up/pi/cook_station.py	
@@ -0,0 +1,95 @@
+"""Encoder turns stir; encoder press pulls; servo and NeoPixel show heat."""
+import argparse
+import time
+from pi.common import StationClient
+from pi.controls import PressDetector
+from pi.display import Display
+
+
+def main():
+    parser = argparse.ArgumentParser()
+    parser.add_argument("--headless", action="store_true")
+    parser.add_argument("--no-servo", action="store_true")
+    parser.add_argument("--servo-channel", type=int, default=0)
+    parser.add_argument("--servo-min", type=float, default=0)
+    parser.add_argument("--servo-max", type=float, default=120)
+    args = parser.parse_args()
+    if not 0 <= args.servo_min < args.servo_max <= 120:
+        parser.error("servo endpoints must satisfy 0 <= min < max <= 120")
+    import board
+    from adafruit_seesaw import seesaw, rotaryio, digitalio, neopixel
+    ss = seesaw.Seesaw(board.I2C(), addr=0x36)
+    ss.pin_mode(24, ss.INPUT_PULLUP)
+    button = digitalio.DigitalIO(ss, 24)
+    encoder = rotaryio.IncrementalEncoder(ss)
+    led = neopixel.NeoPixel(ss, 6, 1, brightness=0.2)
+    servo = None
+    if not args.no_servo:
+        import pi_servo_hat
+        servo = pi_servo_hat.PiServoHat()
+        servo.restart()
+    display = Display(args.headless)
+    client = StationClient("cook")
+    last_position = encoder.position
+    pending_ticks = 0
+    last_sent = 0
+    last_round = None
+    previous_angle = None
+    press = PressDetector()
+    client.start()
+    try:
+        while True:
+            now = time.monotonic()
+            state, result = client.snapshot()
+            station = state.get("cook", {})
+            position = encoder.position
+            delta = abs(position - last_position)
+            last_position = position
+            live = client.ready()
+            if state.get("round_id") != last_round:
+                pending_ticks = 0
+                last_round = state.get("round_id")
+            if live and station.get("status") == "cooking":
+                pending_ticks = min(24, pending_ticks + delta)
+            else:
+                pending_ticks = 0
+            if now - last_sent >= 0.2:
+                if pending_ticks:
+                    client.send({"type": "stir", "ticks": int(pending_ticks)})
+                    pending_ticks = 0
+                last_sent = now
+            if press.sample(not button.value, now) and live:
+                client.send({"type": "pull"})
+            status = station.get("status", "empty")
+            heat = station.get("progress", 0) * 0.65
+            color = (0, 40, 150)
+            if status == "done":
+                heat = 0.65 if station.get("waiting") else 0.65 + 0.35 * (1 - (station.get("burn_in") or 0) / state["rules"]["burn_seconds"])
+                color = (0, 220, 40) if station.get("waiting") else ((220, 100, 0) if int(now * 4) % 2 else (0, 0, 0))
+            elif status == "burning":
+                heat, color = 1, (255, 0, 0)
+            if not live or status == "empty":
+                heat, color = 0, (0, 0, 0)
+            angle = round(args.servo_min + (args.servo_max - args.servo_min) * max(0, min(1, heat)))
+            if servo and angle != previous_angle:
+                servo.move_servo_position(args.servo_channel, angle)
+                previous_angle = angle
+            led[0] = color
+            hint = "Waiting for counter" if station.get("waiting") else f"PULL! {station.get('burn_in')}s" if status == "done" else "Pull then trash" if status == "burning" else "Turn knob to stir"
+            display.show("COOK / " + state.get("phase", "offline"), [str(station.get("item") or "Empty pan").replace("_", " "),
+                         f"{int(station.get('progress', 0)*100)}% / {status}", hint, result,
+                         "LIVE" if live else "Waiting for live round"])
+            client.service()
+            time.sleep(0.02)
+    except KeyboardInterrupt:
+        pass
+    finally:
+        if servo:
+            servo.move_servo_position(args.servo_channel, args.servo_min)
+        led[0] = (0, 0, 0)
+        client.close()
+        display.close()
+
+
+if __name__ == "__main__":
+    main()
diff --git a/Lab 6/order-up/pi/display.py b/Lab 6/order-up/pi/display.py
new file mode 100644
index 0000000..27ed10c
--- /dev/null
+++ b/Lab 6/order-up/pi/display.py	
@@ -0,0 +1,57 @@
+"""Mini PiTFT wiring follows Lab 6/pixel_grid_publisher.py."""
+import textwrap
+import time
+
+
+class Display:
+    def __init__(self, headless=False):
+        self.headless = headless
+        self.last = 0
+        self.previous = None
+        if headless:
+            return
+        import board
+        import digitalio
+        from PIL import Image, ImageDraw, ImageFont
+        from adafruit_rgb_display import st7789
+        self.cs = digitalio.DigitalInOut(board.D5)
+        self.dc = digitalio.DigitalInOut(board.D25)
+        self.light = digitalio.DigitalInOut(board.D22)
+        self.light.switch_to_output(value=True)
+        self.top = digitalio.DigitalInOut(board.D23)
+        self.top.switch_to_input(pull=digitalio.Pull.UP)
+        self.disp = st7789.ST7789(board.SPI(), cs=self.cs, dc=self.dc, rst=None, baudrate=64000000,
+                                width=135, height=240, x_offset=53, y_offset=40, rotation=90)
+        self.image = Image.new("RGB", (240, 135))
+        self.draw = ImageDraw.Draw(self.image)
+        try:
+            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 13)
+        except OSError:
+            self.font = ImageFont.load_default()
+
+    def back_pressed(self):
+        return not self.headless and not self.top.value
+
+    def show(self, title, lines):
+        now = time.monotonic()
+        if now - self.last < 0.2:
+            return
+        self.last = now
+        content = [title] + [part for line in lines for part in (textwrap.wrap(str(line), 29) or [""])]
+        content = content[:8]
+        if content == self.previous:
+            return
+        self.previous = content
+        if self.headless:
+            print(" | ".join(content), flush=True)
+            return
+        self.draw.rectangle((0, 0, 240, 135), fill="#132b27")
+        for i, line in enumerate(content):
+            self.draw.text((4, 3 + i * 16), line, fill="#ffbd69" if i == 0 else "#fff5df", font=self.font)
+        self.disp.image(self.image)
+
+    def close(self):
+        if not self.headless:
+            self.light.value = False
+            for pin in (self.top, self.light, self.cs, self.dc):
+                pin.deinit()
diff --git a/Lab 6/order-up/pi/runner_station.py b/Lab 6/order-up/pi/runner_station.py
new file mode 100644
index 0000000..dde8ffe
--- /dev/null
+++ b/Lab 6/order-up/pi/runner_station.py	
@@ -0,0 +1,58 @@
+"""Joystick menu; Mini PiTFT top button always goes back."""
+import argparse
+import time
+from pi.common import StationClient
+from pi.controls import FlickDetector, PressDetector, RunnerMenu
+from pi.display import Display
+
+
+def main():
+    parser = argparse.ArgumentParser()
+    parser.add_argument("--headless", action="store_true")
+    parser.add_argument("--swap-axes", action="store_true")
+    parser.add_argument("--invert-up", action="store_true")
+    parser.add_argument("--invert-right", action="store_true")
+    parser.add_argument("--center-up", type=float, default=504)
+    parser.add_argument("--center-right", type=float, default=515)
+    args = parser.parse_args()
+    import qwiic_joystick
+    joystick = qwiic_joystick.QwiicJoystick()
+    if not joystick.connected:
+        raise RuntimeError("Qwiic joystick not found; check i2cdetect -y 1")
+    joystick.begin()
+    display = Display(args.headless)
+    client = StationClient("runner")
+    flick = FlickDetector(args.center_up, args.center_right, invert_up=args.invert_up, invert_right=args.invert_right)
+    press, back = PressDetector(), PressDetector()
+    menu = RunnerMenu()
+    client.start()
+    try:
+        while True:
+            state, result = client.snapshot()
+            menu.sync(state)
+            now = time.monotonic()
+            up_axis, right_axis = joystick.horizontal, joystick.vertical
+            if args.swap_axes:
+                up_axis, right_axis = right_axis, up_axis
+            event = flick.sample(up_axis, right_axis)
+            if press.sample(joystick.button == 0, now):
+                event = "press"
+            if back.sample(display.back_pressed(), now):
+                event = "back"
+            if event:
+                payload = menu.input(event, state)
+                if payload:
+                    client.send(payload)
+            display.show("RUNNER / " + state.get("phase", "offline"), menu.lines() + [result,
+                         "LIVE" if client.ready() else "Waiting for live round"])
+            client.service()
+            time.sleep(0.02)
+    except KeyboardInterrupt:
+        pass
+    finally:
+        client.close()
+        display.close()
+
+
+if __name__ == "__main__":
+    main()
diff --git a/Lab 6/order-up/requirements-pi.txt b/Lab 6/order-up/requirements-pi.txt
new file mode 100644
index 0000000..9fe58df
--- /dev/null
+++ b/Lab 6/order-up/requirements-pi.txt	
@@ -0,0 +1,8 @@
+paho-mqtt>=2.1,<3
+Pillow>=10,<13
+Adafruit-Blinka>=8.67
+adafruit-circuitpython-rgb-display>=3.12
+sparkfun-qwiic-joystick>=2
+adafruit-circuitpython-seesaw>=1
+adafruit-circuitpython-lsm6ds>=4
+sparkfun-pi-servo-hat>=1
diff --git a/Lab 6/order-up/requirements-server.txt b/Lab 6/order-up/requirements-server.txt
new file mode 100644
index 0000000..9a5a0f1
--- /dev/null
+++ b/Lab 6/order-up/requirements-server.txt	
@@ -0,0 +1,4 @@
+Flask>=3.1,<4
+Flask-SocketIO>=5.5,<6
+simple-websocket>=1.1,<2
+paho-mqtt>=2.1,<3
diff --git a/Lab 6/order-up/server/__init__.py b/Lab 6/order-up/server/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/Lab 6/order-up/server/app.py b/Lab 6/order-up/server/app.py
new file mode 100644
index 0000000..e26938c
--- /dev/null
+++ b/Lab 6/order-up/server/app.py	
@@ -0,0 +1,185 @@
+"""Run from order-up: python -m server.app [--mqtt]."""
+import argparse
+import json
+import logging
+import threading
+import time
+
+from flask import Flask, jsonify, render_template, request
+from flask_socketio import SocketIO, emit
+
+from pi.common import connect, make_client, topic
+from server.game import Game, Rules
+
+log = logging.getLogger(__name__)
+
+
+class Runtime:
+    def __init__(self, socketio, game=None):
+        self.game = game or Game()
+        self.socketio = socketio
+        self.lock = threading.RLock()
+        self.stopping = threading.Event()
+        self.mqtt = None
+        self.thread = None
+        self.last_payload = None
+        self.last_heartbeat = 0
+        self.mqtt_connected = False
+
+    def state(self):
+        with self.lock:
+            self.game.tick()
+            state = self.game.snapshot()
+            state["network"] = "connected" if self.mqtt_connected else ("reconnecting" if self.mqtt else "simulator")
+            return state
+
+    def start_round(self):
+        with self.lock:
+            return self.game.start()
+
+    def action(self, source, data):
+        if source not in ("runner", "chop", "cook"):
+            return {"ok": False, "msg": "Unknown station"}
+        with self.lock:
+            return self.game.handle(source, data)
+
+    def mqtt_connect(self, client, userdata, flags, reason, properties):
+        if reason.is_failure:
+            log.warning("MQTT connection rejected: %s", reason)
+            return
+        with self.lock:
+            self.mqtt_connected = True
+            self.last_payload = None
+        client.subscribe([(topic("runner/action"), 1), (topic("chop/event"), 0),
+                          (topic("cook/event"), 1), (topic("+/online"), 1), (topic("ping"), 0)])
+        client.publish(topic("server/online"), "1", qos=1, retain=True)
+
+    def mqtt_disconnect(self, client, userdata, flags, reason, properties):
+        with self.lock:
+            self.mqtt_connected = False
+            self.game.online = dict.fromkeys(self.game.online, False)
+
+    def mqtt_message(self, client, userdata, message):
+        suffix = message.topic[len(topic("")):]
+        try:
+            if suffix.endswith("/online"):
+                role = suffix.split("/")[0]
+                if role in self.game.online:
+                    with self.lock:
+                        self.game.online[role] = message.payload == b"1"
+                return
+            # Actions must never be replayed by a broker as retained messages.
+            if message.retain or len(message.payload) > 4096:
+                return
+            data = json.loads(message.payload)
+            if not isinstance(data, dict):
+                return
+            if suffix == "ping":
+                ping_id = data.get("id")
+                if isinstance(ping_id, str) and len(ping_id) <= 128:
+                    client.publish(topic("pong"), json.dumps({"id": ping_id}), qos=0)
+                return
+            source = {"runner/action": "runner", "chop/event": "chop", "cook/event": "cook"}.get(suffix)
+            if source:
+                result = self.action(source, data)
+                if source == "runner" or data.get("type") == "pull":
+                    client.publish(topic(f"{source}/result"), json.dumps(result), qos=1)
+        except (ValueError, TypeError, UnicodeError):
+            log.warning("Ignored malformed MQTT payload on %s", message.topic)
+
+    def publish_once(self):
+        state = self.state()
+        payload = json.dumps(state, sort_keys=True)
+        now = time.monotonic()
+        heartbeat = now - self.last_heartbeat >= 1
+        if payload != self.last_payload or heartbeat:
+            self.socketio.emit("state", state)
+            if self.mqtt_connected:
+                self.mqtt.publish(topic("state"), payload, qos=1, retain=True)
+            self.last_payload = payload
+        if heartbeat:
+            if self.mqtt_connected:
+                self.mqtt.publish(topic("server/online"), "1", qos=1, retain=True)
+            self.last_heartbeat = now
+
+    def start(self, use_mqtt=False):
+        if use_mqtt:
+            self.mqtt = make_client("server")
+            self.mqtt.will_set(topic("server/online"), "0", qos=1, retain=True)
+            self.mqtt.on_connect = self.mqtt_connect
+            self.mqtt.on_disconnect = self.mqtt_disconnect
+            self.mqtt.on_message = self.mqtt_message
+            connect(self.mqtt)
+        self.thread = threading.Thread(target=self._loop, daemon=True)
+        self.thread.start()
+
+    def _loop(self):
+        while not self.stopping.is_set():
+            self.publish_once()
+            self.stopping.wait(0.2)
+
+    def close(self):
+        self.stopping.set()
+        if self.thread:
+            self.thread.join(timeout=2)
+        if self.mqtt:
+            if self.mqtt.is_connected():
+                self.mqtt.publish(topic("server/online"), "0", qos=1, retain=True).wait_for_publish(timeout=1)
+            self.mqtt.disconnect()
+            self.mqtt.loop_stop()
+
+
+def create_app(game=None):
+    app = Flask(__name__)
+    app.config["MAX_CONTENT_LENGTH"] = 4096
+    socketio = SocketIO(app, async_mode="threading")
+    runtime = Runtime(socketio, game)
+    app.extensions["orderup"] = runtime
+
+    @app.get("/")
+    def screen():
+        return render_template("screen.html", simulator=False)
+
+    @app.get("/sim")
+    def simulator():
+        return render_template("screen.html", simulator=True)
+
+    @app.get("/api/state")
+    def state():
+        return jsonify(runtime.state())
+
+    @app.post("/api/start")
+    def start():
+        return jsonify(runtime.start_round())
+
+    @app.post("/api/action/<source>")
+    def action(source):
+        return jsonify(runtime.action(source, request.get_json(silent=True)))
+
+    @socketio.on("connect")
+    def connected(auth=None):
+        emit("state", runtime.state())
+
+    return app, socketio, runtime
+
+
+def main():
+    parser = argparse.ArgumentParser(description="Order Up! laptop server")
+    parser.add_argument("--mqtt", action="store_true", help="Enable Pi / MQTT simulator clients")
+    parser.add_argument("--host", default="127.0.0.1")
+    parser.add_argument("--port", type=int, default=5000)
+    parser.add_argument("--round-seconds", type=float, default=180)
+    parser.add_argument("--seed", type=int, help="Reproducible recipe sequence for playtests")
+    args = parser.parse_args()
+    import random
+    app, socketio, runtime = create_app(Game(Rules(round_seconds=args.round_seconds), rng=random.Random(args.seed)))
+    runtime.start(args.mqtt)
+    print(f"Shared screen: http://{args.host}:{args.port}/   Simulator: /sim", flush=True)
+    try:
+        socketio.run(app, host=args.host, port=args.port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
+    finally:
+        runtime.close()
+
+
+if __name__ == "__main__":
+    main()
diff --git a/Lab 6/order-up/server/game.py b/Lab 6/order-up/server/game.py
new file mode 100644
index 0000000..931db81
--- /dev/null
+++ b/Lab 6/order-up/server/game.py	
@@ -0,0 +1,252 @@
+"""Authoritative rules. No I/O; callers serialize access and supply monotonic time."""
+from collections import Counter, OrderedDict
+from dataclasses import dataclass
+import math
+import random
+import time
+import uuid
+
+INGREDIENTS = ("lettuce", "tomato", "patty", "bun")
+RECIPES = {
+    "salad": {"needs": ["chopped_lettuce", "chopped_tomato"], "points": 10},
+    "burger": {"needs": ["bun", "cooked_patty", "chopped_lettuce"], "points": 20},
+    "soup": {"needs": ["soup"], "points": 20},
+}
+CHOP_OUTPUT = {"lettuce": "chopped_lettuce", "tomato": "chopped_tomato"}
+COOK_OUTPUT = {"patty": "cooked_patty", "chopped_tomato": "soup"}
+
+
+@dataclass(frozen=True)
+class Rules:
+    round_seconds: float = 180
+    arrival_seconds: float = 20
+    ticket_seconds: float = 60
+    burn_seconds: float = 8
+    chops: int = 6
+    stir_ticks: int = 24
+
+    def __post_init__(self):
+        for value in vars(self).values():
+            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
+                raise ValueError("Rule values must be positive finite numbers")
+        if type(self.chops) is not int or type(self.stir_ticks) is not int:
+            raise ValueError("Chop and stir targets must be integers")
+
+
+class Game:
+    def __init__(self, rules=None, clock=time.monotonic, rng=None):
+        self.rules = rules or Rules()
+        self.clock = clock
+        self.rng = rng or random.Random()
+        self.phase = "lobby"
+        self.round_id = None
+        self.score = 0
+        self.counter = [None] * 6
+        self.versions = [0] * 6
+        self.chop = self.empty_chop()
+        self.cook = self.empty_cook()
+        self.tickets = []
+        self.online = {name: False for name in ("runner", "chop", "cook")}
+        self.message = "Ready for the dinner rush?"
+        self.started = None
+        self.next_arrival = None
+        self.next_ticket = 1
+        self.results = OrderedDict()
+        self.now = self.clock()
+
+    def empty_chop(self):
+        return {"item": None, "progress": 0, "needed": self.rules.chops, "waiting": False}
+
+    @staticmethod
+    def empty_cook():
+        return {"item": None, "ticks": 0, "status": "empty", "done_at": None, "waiting": False}
+
+    def start(self, now=None):
+        self.tick(now)
+        if self.phase == "playing":
+            return {"ok": False, "msg": "A round is already running"}
+        self.phase = "playing"
+        self.round_id = uuid.uuid4().hex
+        self.score = 0
+        self.counter = [None] * 6
+        self.versions = [v + 1 for v in self.versions]
+        self.chop, self.cook = self.empty_chop(), self.empty_cook()
+        self.tickets = []
+        self.started = self.now
+        self.next_arrival = self.now
+        self.message = "Service is open!"
+        self.tick(self.now)
+        return {"ok": True, "msg": self.message}
+
+    def tick(self, now=None):
+        self.now = max(self.now, self.clock() if now is None else now)
+        if self.phase != "playing":
+            return
+        end = self.started + self.rules.round_seconds
+        horizon = min(self.now, end)
+        # Process arrivals and expirations in order even after a long pause.
+        while True:
+            expiry = min((t["expires"] for t in self.tickets), default=math.inf)
+            arrival = self.next_arrival if self.next_arrival < end else math.inf
+            event_at = min(expiry, arrival)
+            if event_at > horizon:
+                break
+            expired = [t for t in self.tickets if t["expires"] <= event_at]
+            if expired:
+                self.score -= 10 * len(expired)
+                self.tickets = [t for t in self.tickets if t["expires"] > event_at]
+                self.message = "Order expired: -10 points" if len(expired) == 1 else f"{len(expired)} orders expired"
+            if arrival == event_at:
+                if len(self.tickets) < 4:
+                    self.tickets.append({"id": self.next_ticket, "recipe": self.rng.choice(tuple(RECIPES)),
+                                         "expires": event_at + self.rules.ticket_seconds})
+                    self.next_ticket += 1
+                self.next_arrival += self.rules.arrival_seconds
+        if (self.cook["status"] == "done" and not self.cook["waiting"]
+                and horizon >= self.cook["done_at"] + self.rules.burn_seconds):
+            self.cook.update(item="burnt", status="burning")
+            self.message = "Food burnt! Pull it, then trash it."
+        self._drain()
+        if self.now >= end:
+            self.phase = "over"
+            self.message = f"Service finished! Final score: {self.score}"
+
+    def _set_slot(self, index, item):
+        self.counter[index] = item
+        self.versions[index] += 1
+
+    def _drain(self):
+        for name in ("chop", "cook"):
+            station = getattr(self, name)
+            if station["waiting"] and None in self.counter:
+                self._set_slot(self.counter.index(None), station["item"])
+                setattr(self, name, self.empty_chop() if name == "chop" else self.empty_cook())
+
+    def handle(self, source, payload, now=None):
+        self.tick(now)
+        if not isinstance(payload, dict):
+            return {"ok": False, "msg": "Expected a JSON object"}
+        action_id = payload.get("id")
+        needs_id = source == "runner" or (source == "cook" and payload.get("type") == "pull")
+        if needs_id and (not isinstance(action_id, str) or not 1 <= len(action_id) <= 128):
+            return {"ok": False, "msg": "An action id (1–128 characters) is required"}
+        key = (source, action_id) if isinstance(action_id, str) else None
+        if key and key in self.results:
+            return dict(self.results[key])
+        try:
+            if source not in ("runner", "chop", "cook"):
+                raise ValueError("Unknown station")
+            if self.phase != "playing":
+                raise ValueError("Start a round first" if self.phase == "lobby" else "Round is over")
+            if "round_id" in payload and payload["round_id"] != self.round_id:
+                raise ValueError("That action belongs to an old round")
+            msg = self._runner(payload) if source == "runner" else self._station(source, payload)
+            result = {"id": action_id, "ok": True, "msg": msg}
+        except ValueError as error:
+            result = {"id": action_id, "ok": False, "msg": str(error)}
+        if source == "runner" or not result["ok"]:
+            self.message = result["msg"]
+        if key:
+            self.results[key] = result
+            if len(self.results) > 4096:
+                self.results.popitem(last=False)
+        self._drain()
+        return dict(result)
+
+    def _runner(self, p):
+        action = p.get("action")
+        if action == "get":
+            item = p.get("item")
+            if item not in INGREDIENTS:
+                raise ValueError("Choose lettuce, tomato, patty or bun")
+            if None not in self.counter:
+                raise ValueError("Counter is full — trash or send an item")
+            self._set_slot(self.counter.index(None), item)
+            return f"Got {item}"
+        if action in ("send", "trash"):
+            slot = p.get("slot")
+            if type(slot) is not int or not 0 <= slot < 6 or self.counter[slot] is None:
+                raise ValueError("Choose an occupied counter slot")
+            if "version" in p and p["version"] != self.versions[slot]:
+                raise ValueError("That slot changed — choose it again")
+            item = self.counter[slot]
+            if action == "send":
+                destination = p.get("to")
+                if destination not in ("chop", "cook"):
+                    raise ValueError("Choose Chop or Cook")
+                station = getattr(self, destination)
+                if station["item"] is not None:
+                    raise ValueError(f"{destination.title()} is busy")
+                station["item"] = item
+                if destination == "cook":
+                    station["status"] = "cooking"
+            self._set_slot(slot, None)
+            return f"Sent {item.replace('_', ' ')} to {p['to']}" if action == "send" else f"Trashed {item.replace('_', ' ')}"
+        if action == "serve":
+            ticket_id = p.get("ticket")
+            if type(ticket_id) is not int:
+                raise ValueError("Choose a ticket")
+            ticket = next((t for t in self.tickets if t["id"] == ticket_id), None)
+            if ticket is None:
+                raise ValueError("That ticket is no longer available")
+            recipe = RECIPES[ticket["recipe"]]
+            missing = Counter(recipe["needs"]) - Counter(self.counter)
+            if missing:
+                raise ValueError("Missing " + ", ".join(item.replace('_', ' ') for item in missing.elements()))
+            for item in recipe["needs"]:
+                self._set_slot(self.counter.index(item), None)
+            tip = int(max(0, ticket["expires"] - self.now) // 10)
+            self.score += recipe["points"] + tip
+            self.tickets.remove(ticket)
+            return f"Served {ticket['recipe']}! +{recipe['points']} +{tip} tip"
+        raise ValueError("Unknown Runner action")
+
+    def _station(self, source, p):
+        station = getattr(self, source)
+        event = p.get("type")
+        if station["item"] is None:
+            raise ValueError("Station is empty")
+        if station["waiting"]:
+            raise ValueError("Waiting for a counter slot")
+        if source == "chop" and event == "chop":
+            station["progress"] += 1
+            if station["progress"] >= self.rules.chops:
+                station.update(item=CHOP_OUTPUT.get(station["item"], "ruined"), waiting=True)
+            return "Chop!"
+        if source == "cook" and event == "stir":
+            ticks = p.get("ticks", 1)
+            if type(ticks) is not int or not 1 <= ticks <= 24:
+                raise ValueError("Stir ticks must be an integer from 1 to 24")
+            if station["status"] != "cooking":
+                raise ValueError("Pull the food off the heat")
+            station["ticks"] = min(self.rules.stir_ticks, station["ticks"] + ticks)
+            if station["ticks"] >= self.rules.stir_ticks:
+                station.update(status="done", done_at=self.now)
+            return "Stir!"
+        if source == "cook" and event == "pull":
+            if station["status"] == "cooking":
+                raise ValueError("Keep stirring — food is not done")
+            if station["status"] == "done":
+                station["item"] = COOK_OUTPUT.get(station["item"], "ruined")
+            # Pulling removes heat immediately, even if the counter is full.
+            station["waiting"] = True
+            return "Off the heat"
+        raise ValueError("Unknown station event")
+
+    def snapshot(self):
+        cook = self.cook
+        display_now = min(self.now, self.started + self.rules.round_seconds) if self.phase == "over" else self.now
+        burn_in = None
+        if cook["status"] == "done" and not cook["waiting"]:
+            burn_in = round(max(0, cook["done_at"] + self.rules.burn_seconds - display_now), 1)
+        remaining = self.rules.round_seconds if self.started is None else max(0, self.started + self.rules.round_seconds - self.now)
+        return {
+            "phase": self.phase, "round_id": self.round_id, "time_left": math.ceil(remaining),
+            "score": self.score, "message": self.message,
+            "tickets": [{"id": t["id"], "recipe": t["recipe"], "time_left": math.ceil(max(0, t["expires"] - display_now))} for t in self.tickets],
+            "counter": list(self.counter), "counter_versions": list(self.versions),
+            "chop": dict(self.chop),
+            "cook": {"item": cook["item"], "progress": cook["ticks"] / self.rules.stir_ticks,
+                     "status": cook["status"], "burn_in": burn_in, "waiting": cook["waiting"]},
+            "online": dict(self.online), "recipes": RECIPES, "rules": vars(self.rules).copy(),
+        }
diff --git a/Lab 6/order-up/server/static/SOCKET.IO-LICENSE.txt b/Lab 6/order-up/server/static/SOCKET.IO-LICENSE.txt
new file mode 100644
index 0000000..a9fd2d6
--- /dev/null
+++ b/Lab 6/order-up/server/static/SOCKET.IO-LICENSE.txt	
@@ -0,0 +1,21 @@
+The MIT License (MIT)
+
+Copyright (c) 2014-present Guillermo Rauch and Socket.IO contributors
+
+Permission is hereby granted, free of charge, to any person obtaining a copy
+of this software and associated documentation files (the "Software"), to deal
+in the Software without restriction, including without limitation the rights
+to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
+copies of the Software, and to permit persons to whom the Software is
+furnished to do so, subject to the following conditions:
+
+The above copyright notice and this permission notice shall be included in
+all copies or substantial portions of the Software.
+
+THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
+IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
+FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
+AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
+LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
+OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
+THE SOFTWARE.
\ No newline at end of file
diff --git a/Lab 6/order-up/server/static/screen.css b/Lab 6/order-up/server/static/screen.css
new file mode 100644
index 0000000..c85407b
--- /dev/null
+++ b/Lab 6/order-up/server/static/screen.css	
@@ -0,0 +1,428 @@
+:root {
+  --paper:#f6f1e7;
+  --ink:#233b35;
+  --orange:#ce4526;
+  --line:#d6d1c5;
+  --green:#217653;
+  --muted:#63726a;
+  --white:#fffdf7;
+}
+* {
+  box-sizing:border-box;
+}
+body {
+  margin:0;
+  background:var(--paper);
+  color:var(--ink);
+  font-family:Arial,Helvetica,sans-serif;
+}
+main {
+  max-width:1600px;
+  margin:auto;
+  padding:32px 4vw 22px;
+}
+header {
+  display:flex;
+  align-items:center;
+  justify-content:space-between;
+  gap:24px;
+  border-bottom:3px solid var(--ink);
+  padding-bottom:22px;
+}
+h1 {
+  font-family:Georgia,serif;
+  font-size:clamp(48px,5.2vw,82px);
+  letter-spacing:-4px;
+  line-height:1;
+  margin:4px 0;
+}
+h1 span {
+  color:var(--orange);
+}
+.eyebrow {
+  font-size:12px;
+  font-weight:800;
+  letter-spacing:2px;
+  margin:0 0 10px;
+}
+.scoreboard {
+  display:flex;
+  gap:clamp(24px,5vw,90px);
+}
+.scoreboard>div {
+  display:flex;
+  flex-direction:column;
+}
+.scoreboard strong {
+  font-size:clamp(40px,4.5vw,64px);
+  font-variant-numeric:tabular-nums;
+  line-height:1;
+}
+.service-bar {
+  display:flex;
+  align-items:center;
+  gap:24px;
+  min-height:68px;
+  border-bottom:1px solid var(--line);
+  font-size:13px;
+  font-weight:bold;
+  letter-spacing:1px;
+}
+.service-bar #connection {
+  margin-left:auto;
+  color:var(--muted);
+  font-size:12px;
+  letter-spacing:0;
+}
+.section-title {
+  display:flex;
+  align-items:baseline;
+  justify-content:space-between;
+  gap:16px;
+  margin:24px 0 14px;
+}
+.section-title h2 {
+  font-family:Georgia,serif;
+  font-size:29px;
+  letter-spacing:-1px;
+  margin:0;
+}
+.section-title>span {
+  font-size:13px;
+  color:var(--muted);
+}
+.tickets {
+  display:grid;
+  grid-template-columns:repeat(4,1fr);
+  gap:16px;
+  min-height:190px;
+}
+.ticket {
+  background:var(--white);
+  border:1px solid var(--line);
+  border-top:5px solid var(--orange);
+  padding:18px;
+  text-align:left;
+  color:var(--ink);
+  border-radius:3px;
+  position:relative;
+  box-shadow:0 4px 0 #e9e2d6;
+  font-size:inherit;
+}
+.ticket .ticket-meta {
+  display:flex;
+  justify-content:space-between;
+  color:var(--muted);
+  font-size:11px;
+  letter-spacing:1px;
+}
+.ticket h3 {
+  font-family:Georgia,serif;
+  font-size:clamp(23px,2.4vw,34px);
+  margin:14px 0;
+}
+.ticket .needs {
+  font-size:14px;
+  line-height:1.7;
+  min-height:50px;
+}
+.ticket .ready {
+  color:var(--green);
+  font-weight:bold;
+}
+.ticket .clock {
+  display:flex;
+  justify-content:space-between;
+  font-size:20px;
+  font-weight:bold;
+  margin-top:16px;
+}
+.ticket.urgent {
+  border-color:var(--orange);
+  background:#ffede3;
+  animation:urgent 1s ease-in-out infinite alternate;
+}
+.ticket progress {
+  margin-top:10px;
+  height:7px;
+}
+.ticket.urgent .clock {
+  color:var(--orange);
+}
+progress {
+  width:100%;
+  height:13px;
+  accent-color:var(--green);
+  border:0;
+  border-radius:0;
+  display:block;
+}
+progress::-webkit-progress-bar {
+  background:#e4e4d8;
+}
+progress::-webkit-progress-value {
+  background:var(--green);
+}
+.placeholder {
+  color:var(--muted);
+  align-self:center;
+  grid-column:1/-1;
+  font-family:Georgia,serif;
+  font-size:26px;
+}
+.counter {
+  display:grid;
+  grid-template-columns:repeat(6,1fr);
+  gap:12px;
+}
+.slot {
+  min-height:112px;
+  border:1px dashed #b9bfb3;
+  border-radius:5px;
+  padding:13px;
+  background:transparent;
+  text-align:left;
+  color:var(--ink);
+  font-size:20px;
+}
+.slot .number {
+  font-size:11px;
+  color:var(--muted);
+  display:block;
+  margin-bottom:15px;
+}
+.slot.filled {
+  background:var(--white);
+  border:1px solid var(--line);
+}
+.slot.spoiled {
+  background:#e9d7cc;
+  color:#8b321b;
+}
+.slot.selected {
+  outline:3px solid var(--orange);
+  outline-offset:2px;
+}
+.slot.empty .item {
+  font-size:14px;
+  color:#869086;
+}
+.stations {
+  display:grid;
+  grid-template-columns:1fr 1fr;
+  gap:18px;
+  margin-top:24px;
+}
+.station {
+  padding:22px 24px;
+  background:#e5eadd;
+  border-radius:5px;
+  min-height:148px;
+}
+.station h2 {
+  font-size:12px;
+  letter-spacing:2px;
+  margin:0 0 14px;
+}
+.station .station-main {
+  font-size:28px;
+  font-family:Georgia,serif;
+  display:flex;
+  justify-content:space-between;
+  gap:12px;
+  margin-bottom:16px;
+}
+.station .hint {
+  font-size:13px;
+  color:var(--muted);
+}
+.station.hot {
+  background:#f9ddac;
+}
+.station.burnt {
+  background:#e9c5b8;
+}
+.pips {
+  letter-spacing:7px;
+  font-family:monospace;
+  color:var(--green);
+  font-size:25px;
+}
+.message {
+  background:var(--ink);
+  color:var(--paper);
+  border-radius:5px;
+  padding:18px 24px;
+  font-size:21px;
+  margin:18px 0 0;
+}
+.sim-panel {
+  border-top:2px solid var(--ink);
+  margin-top:28px;
+}
+.sim-grid {
+  display:grid;
+  grid-template-columns:2fr 1fr 1fr;
+  gap:28px;
+}
+.sim-grid h3 {
+  font-size:15px;
+}
+.sim-grid p {
+  font-size:14px;
+  line-height:1.5;
+  color:var(--muted);
+}
+.buttons {
+  display:flex;
+  gap:8px;
+  flex-wrap:wrap;
+}
+button {
+  font:inherit;
+  cursor:pointer;
+  background:var(--ink);
+  color:var(--white);
+  border:0;
+  border-radius:4px;
+  padding:11px 15px;
+}
+button:hover:not(:disabled) {
+  filter:brightness(.91);
+}
+button:focus-visible,a:focus-visible {
+  outline:3px solid var(--orange);
+  outline-offset:3px;
+}
+button:disabled {
+  cursor:default;
+  opacity:.55;
+}
+button.ticket:disabled,button.slot:disabled {
+  opacity:1;
+}
+#start {
+  background:var(--orange);
+  padding:10px 18px;
+}
+#result {
+  font-weight:bold;
+  min-height:22px;
+}
+fieldset {
+  border:0;
+  margin:0;
+  padding:0;
+  min-width:0;
+}
+kbd {
+  font-size:11px;
+  opacity:.65;
+  margin-left:6px;
+}
+footer {
+  display:flex;
+  justify-content:space-between;
+  gap:16px;
+  color:var(--muted);
+  font-size:12px;
+  padding-top:24px;
+}
+footer a {
+  color:var(--ink);
+}
+.sr-only {
+  position:absolute;
+  width:1px;
+  height:1px;
+  padding:0;
+  overflow:hidden;
+  clip:rect(0,0,0,0);
+  white-space:nowrap;
+}
+.offline {
+  color:var(--orange)!important;
+}
+@keyframes urgent {
+  to {
+    box-shadow:0 0 0 3px #ce45263b;
+  }
+}
+@media(prefers-reduced-motion:reduce) {
+  .ticket.urgent {
+    animation:none;
+  }
+}
+@media(min-width:1800px) {
+  main {
+    max-width:1900px;
+  }
+  .ticket .needs {
+    font-size:20px;
+  }
+  .ticket {
+    min-height:250px;
+  }
+  .slot {
+    min-height:150px;
+  }
+  .station {
+    min-height:190px;
+  }
+}
+@media(max-width:800px) {
+  main {
+    padding:20px;
+  }
+  .tickets {
+    grid-template-columns:repeat(2,1fr);
+  }
+  .counter {
+    grid-template-columns:repeat(3,1fr);
+  }
+  .sim-grid {
+    grid-template-columns:1fr;
+  }
+  .section-title>span {
+    max-width:45%;
+    text-align:right;
+  }
+  .stations {
+    grid-template-columns:1fr;
+  }
+  .service-bar {
+    gap:8px;
+    flex-wrap:wrap;
+    padding:12px 0;
+  }
+  .scoreboard {
+    gap:20px;
+  }
+  .eyebrow {
+    font-size:9px;
+    letter-spacing:1px;
+  }
+  header {
+    gap:12px;
+  }
+  h1 {
+    letter-spacing:-3px;
+  }
+  footer {
+    flex-direction:column;
+  }
+}
+@media(max-width:420px) {
+  .tickets {
+    grid-template-columns:1fr;
+  }
+  .scoreboard strong {
+    font-size:32px;
+  }
+  h1 {
+    font-size:44px;
+  }
+  .slot {
+    font-size:16px;
+  }
+}
diff --git a/Lab 6/order-up/server/static/screen.js b/Lab 6/order-up/server/static/screen.js
new file mode 100644
index 0000000..059dbbc
--- /dev/null
+++ b/Lab 6/order-up/server/static/screen.js	
@@ -0,0 +1,78 @@
+'use strict';
+const sim = document.body.dataset.simulator === 'true';
+const $ = id => document.getElementById(id);
+const names = {lettuce:'Lettuce',tomato:'Tomato',patty:'Patty',bun:'Bun',chopped_lettuce:'Chopped lettuce',chopped_tomato:'Chopped tomato',cooked_patty:'Cooked patty',soup:'Tomato soup',salad:'Garden salad',burger:'House burger',ruined:'Ruined',burnt:'Burnt'};
+const label = item => names[item] || 'Empty';
+const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
+let state = null, selected = null, live = false, lastUpdate = 0, busy = false;
+const socket = io();
+function html(id, content){if($(id).innerHTML !== content) $(id).innerHTML = content;}
+function updateConnection(){
+  live = socket.connected && Date.now()-lastUpdate < 3500;
+  $('connection').textContent = live ? (state?.network === 'simulator' ? 'Practice mode · no broker needed' : state?.network === 'connected' ? 'Live kitchen' : 'Broker reconnecting') : 'Server disconnected · controls paused';
+  $('connection').classList.toggle('offline', !live);
+  $('start').disabled = !live || busy || state?.phase === 'playing';
+  if(sim){
+    const disabled = !live || busy || state?.phase !== 'playing';
+    $('controls').disabled = disabled;
+    document.querySelectorAll('#tickets button, #counter button').forEach(button => button.disabled = disabled);
+  }
+}
+socket.on('disconnect',updateConnection);
+socket.on('state', data => {state=data;lastUpdate=Date.now();render();updateConnection();});
+setInterval(updateConnection,500);
+function render(){
+  const s=state, playing=s.phase==='playing';
+  $('score').textContent=s.score;
+  $('timer').textContent=`${Math.floor(s.time_left/60)}:${String(s.time_left%60).padStart(2,'0')}`;
+  $('phase').textContent={lobby:'KITCHEN CLOSED · READY WHEN YOU ARE',playing:'SERVICE IS OPEN',over:'THAT’S A WRAP'}[s.phase];
+  $('start').textContent=s.phase==='over'?'Another round':'Start service';
+  $('message').textContent=s.message;
+  $('capacity').textContent=`${s.counter.filter(Boolean).length} / 6 spaces used`;
+  if(selected && (selected.round !== s.round_id || s.counter_versions[selected.slot] !== selected.version)) selected=null;
+  html('tickets',s.tickets.length?s.tickets.map(t=>{
+    const recipe=s.recipes[t.recipe], ready=recipe.needs.every(i=>s.counter.includes(i));
+    return `<${sim?'button':'article'} class="ticket ${t.time_left<=15?'urgent':''}" ${sim?`data-ticket="${t.id}" aria-label="Serve ${esc(label(t.recipe))}" ${playing?'':'disabled'}`:''}><div class="ticket-meta"><span>ORDER ${String(t.id).padStart(2,'0')}</span><span>${recipe.points} PTS + TIP</span></div><h3>${label(t.recipe)}</h3><div class="needs">${recipe.needs.map(i=>`<div class="${s.counter.includes(i)?'ready':''}">${s.counter.includes(i)?'✓':'○'} ${label(i)}</div>`).join('')}</div><div class="clock"><span>${t.time_left}s</span><span>${ready?'READY':sim?'SERVE →':'IN PREP'}</span></div><progress value="${t.time_left}" max="${s.rules.ticket_seconds}"></progress></${sim?'button':'article'}>`;
+  }).join(''):`<p class="placeholder">${s.phase==='lobby'?'Start service to receive your first order.':s.phase==='over'?'Aprons off. Ready for another round?':'Rail cleared. Next order coming soon…'}</p>`);
+  html('counter',s.counter.map((item,i)=>`<${sim?'button':'div'} class="slot ${item?'filled':'empty'} ${['burnt','ruined'].includes(item)?'spoiled':''} ${selected?.slot===i?'selected':''}" ${sim?`data-slot="${i}" aria-label="Counter slot ${i+1}: ${label(item)}" aria-pressed="${selected?.slot===i}" ${playing?'':'disabled'}`:''}><span class="number">${String(i+1).padStart(2,'0')}</span><span class="item">${item?label(item):'Open space'}</span></${sim?'button':'div'}>`).join(''));
+  const c=s.chop,k=s.cook;
+  html('chop',`<h2>02 / CHOP STATION</h2><div class="station-main"><span>${c.item?label(c.item):'Board is clear'}</span><span class="pips">${'●'.repeat(c.progress)}${'○'.repeat(c.needed-c.progress)}</span></div><span class="hint">${c.waiting?'Finished · waiting for counter space':c.item?'Six clear chops. Make them count.':'Runner, send something over.'}</span>`);
+  const hint=k.waiting?'Off heat · waiting for counter space':k.status==='done'?`PULL NOW · burns in ${k.burn_in.toFixed(1)}s`:k.status==='burning'?'Burnt · pull it, then trash it':k.item?'Keep stirring to make progress.':'Runner, send something over.';
+  html('cook',`<h2>03 / COOK STATION</h2><div class="station-main"><span>${k.item?label(k.item):'Pan is empty'}</span><span>${Math.round(k.progress*100)}%</span></div><progress value="${k.progress}" max="1"></progress><p class="hint">${hint}</p>`);
+  $('cook').className=`station ${k.status==='done'?'hot':k.status==='burning'?'burnt':''}`;
+  $('online').textContent=Object.entries(s.online).map(([name,on])=>`${name[0].toUpperCase()+name.slice(1)} Pi: ${on?'online':'offline'}`).join('   /   ');
+  if(sim) $('selection').textContent=selected?`Slot ${selected.slot+1} · ${label(s.counter[selected.slot])}`:'No counter slot selected';
+}
+async function post(path,data){
+  if(!live || busy) return;
+  busy=true;updateConnection();
+  const body=JSON.stringify(data);
+  try{
+    let result;
+    // Retrying a request keeps its ID: a lost response must not repeat an action.
+    for(let attempt=0;attempt<2;attempt++){
+      try{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body,signal:AbortSignal.timeout(4000)});if(!response.ok)throw Error(`HTTP ${response.status}`);result=await response.json();break;}
+      catch(error){if(attempt===1)throw error;}
+    }
+    if(sim) $('result').textContent=result.msg;
+    else $('message').textContent=result.msg;
+  }catch(error){(sim?$('result'):$('message')).textContent=`Connection problem: ${error.message}`;}
+  finally{busy=false;updateConnection();}
+}
+function act(role,data){
+  if(state?.phase!=='playing')return;
+  return post(`/api/action/${role}`,{...data,id:globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,round_id:state.round_id});
+}
+$('start').onclick=()=>post('/api/start',{});
+if(sim){
+  $('get-buttons').onclick=e=>{const b=e.target.closest('[data-get]');if(b)act('runner',{action:'get',item:b.dataset.get});};
+  $('counter').onclick=e=>{const b=e.target.closest('[data-slot]');if(!b||!live||state.phase!=='playing')return;const slot=Number(b.dataset.slot);selected=state.counter[slot]?{slot,version:state.counter_versions[slot],round:state.round_id}:null;render();};
+  function move(action,to){if(!selected){$('result').textContent='Select an occupied counter slot first.';return;}act('runner',{action,to,slot:selected.slot,version:selected.version});}
+  document.querySelectorAll('[data-send]').forEach(b=>b.onclick=()=>move('send',b.dataset.send));
+  $('trash').onclick=()=>move('trash');
+  $('tickets').onclick=e=>{const b=e.target.closest('[data-ticket]');if(b)act('runner',{action:'serve',ticket:Number(b.dataset.ticket)});};
+  $('do-chop').onclick=()=>act('chop',{type:'chop'});
+  $('stir').onclick=()=>act('cook',{type:'stir',ticks:3});
+  $('pull').onclick=()=>act('cook',{type:'pull'});
+  document.addEventListener('keydown',e=>{if(e.repeat||e.ctrlKey||e.metaKey||e.altKey||['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;const button={c:'do-chop',s:'stir',p:'pull'}[e.key.toLowerCase()];if(button){e.preventDefault();$(button).click();}});
+}
diff --git a/Lab 6/order-up/server/static/socket.io.min.js b/Lab 6/order-up/server/static/socket.io.min.js
new file mode 100644
index 0000000..c72110d
--- /dev/null
+++ b/Lab 6/order-up/server/static/socket.io.min.js	
@@ -0,0 +1,7 @@
+/*!
+ * Socket.IO v4.8.1
+ * (c) 2014-2024 Guillermo Rauch
+ * Released under the MIT License.
+ */
+!function(t,n){"object"==typeof exports&&"undefined"!=typeof module?module.exports=n():"function"==typeof define&&define.amd?define(n):(t="undefined"!=typeof globalThis?globalThis:t||self).io=n()}(this,(function(){"use strict";function t(t,n){(null==n||n>t.length)&&(n=t.length);for(var i=0,r=Array(n);i<n;i++)r[i]=t[i];return r}function n(t,n){for(var i=0;i<n.length;i++){var r=n[i];r.enumerable=r.enumerable||!1,r.configurable=!0,"value"in r&&(r.writable=!0),Object.defineProperty(t,f(r.key),r)}}function i(t,i,r){return i&&n(t.prototype,i),r&&n(t,r),Object.defineProperty(t,"prototype",{writable:!1}),t}function r(n,i){var r="undefined"!=typeof Symbol&&n[Symbol.iterator]||n["@@iterator"];if(!r){if(Array.isArray(n)||(r=function(n,i){if(n){if("string"==typeof n)return t(n,i);var r={}.toString.call(n).slice(8,-1);return"Object"===r&&n.constructor&&(r=n.constructor.name),"Map"===r||"Set"===r?Array.from(n):"Arguments"===r||/^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(r)?t(n,i):void 0}}(n))||i&&n&&"number"==typeof n.length){r&&(n=r);var e=0,o=function(){};return{s:o,n:function(){return e>=n.length?{done:!0}:{done:!1,value:n[e++]}},e:function(t){throw t},f:o}}throw new TypeError("Invalid attempt to iterate non-iterable instance.\nIn order to be iterable, non-array objects must have a [Symbol.iterator]() method.")}var s,u=!0,h=!1;return{s:function(){r=r.call(n)},n:function(){var t=r.next();return u=t.done,t},e:function(t){h=!0,s=t},f:function(){try{u||null==r.return||r.return()}finally{if(h)throw s}}}}function e(){return e=Object.assign?Object.assign.bind():function(t){for(var n=1;n<arguments.length;n++){var i=arguments[n];for(var r in i)({}).hasOwnProperty.call(i,r)&&(t[r]=i[r])}return t},e.apply(null,arguments)}function o(t){return o=Object.setPrototypeOf?Object.getPrototypeOf.bind():function(t){return t.__proto__||Object.getPrototypeOf(t)},o(t)}function s(t,n){t.prototype=Object.create(n.prototype),t.prototype.constructor=t,h(t,n)}function u(){try{var t=!Boolean.prototype.valueOf.call(Reflect.construct(Boolean,[],(function(){})))}catch(t){}return(u=function(){return!!t})()}function h(t,n){return h=Object.setPrototypeOf?Object.setPrototypeOf.bind():function(t,n){return t.__proto__=n,t},h(t,n)}function f(t){var n=function(t,n){if("object"!=typeof t||!t)return t;var i=t[Symbol.toPrimitive];if(void 0!==i){var r=i.call(t,n||"default");if("object"!=typeof r)return r;throw new TypeError("@@toPrimitive must return a primitive value.")}return("string"===n?String:Number)(t)}(t,"string");return"symbol"==typeof n?n:n+""}function c(t){return c="function"==typeof Symbol&&"symbol"==typeof Symbol.iterator?function(t){return typeof t}:function(t){return t&&"function"==typeof Symbol&&t.constructor===Symbol&&t!==Symbol.prototype?"symbol":typeof t},c(t)}function a(t){var n="function"==typeof Map?new Map:void 0;return a=function(t){if(null===t||!function(t){try{return-1!==Function.toString.call(t).indexOf("[native code]")}catch(n){return"function"==typeof t}}(t))return t;if("function"!=typeof t)throw new TypeError("Super expression must either be null or a function");if(void 0!==n){if(n.has(t))return n.get(t);n.set(t,i)}function i(){return function(t,n,i){if(u())return Reflect.construct.apply(null,arguments);var r=[null];r.push.apply(r,n);var e=new(t.bind.apply(t,r));return i&&h(e,i.prototype),e}(t,arguments,o(this).constructor)}return i.prototype=Object.create(t.prototype,{constructor:{value:i,enumerable:!1,writable:!0,configurable:!0}}),h(i,t)},a(t)}var v=Object.create(null);v.open="0",v.close="1",v.ping="2",v.pong="3",v.message="4",v.upgrade="5",v.noop="6";var l=Object.create(null);Object.keys(v).forEach((function(t){l[v[t]]=t}));var p,d={type:"error",data:"parser error"},y="function"==typeof Blob||"undefined"!=typeof Blob&&"[object BlobConstructor]"===Object.prototype.toString.call(Blob),b="function"==typeof ArrayBuffer,w=function(t){return"function"==typeof ArrayBuffer.isView?ArrayBuffer.isView(t):t&&t.buffer instanceof ArrayBuffer},g=function(t,n,i){var r=t.type,e=t.data;return y&&e instanceof Blob?n?i(e):m(e,i):b&&(e instanceof ArrayBuffer||w(e))?n?i(e):m(new Blob([e]),i):i(v[r]+(e||""))},m=function(t,n){var i=new FileReader;return i.onload=function(){var t=i.result.split(",")[1];n("b"+(t||""))},i.readAsDataURL(t)};function k(t){return t instanceof Uint8Array?t:t instanceof ArrayBuffer?new Uint8Array(t):new Uint8Array(t.buffer,t.byteOffset,t.byteLength)}for(var A="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",j="undefined"==typeof Uint8Array?[]:new Uint8Array(256),E=0;E<64;E++)j[A.charCodeAt(E)]=E;var O,B="function"==typeof ArrayBuffer,S=function(t,n){if("string"!=typeof t)return{type:"message",data:C(t,n)};var i=t.charAt(0);return"b"===i?{type:"message",data:N(t.substring(1),n)}:l[i]?t.length>1?{type:l[i],data:t.substring(1)}:{type:l[i]}:d},N=function(t,n){if(B){var i=function(t){var n,i,r,e,o,s=.75*t.length,u=t.length,h=0;"="===t[t.length-1]&&(s--,"="===t[t.length-2]&&s--);var f=new ArrayBuffer(s),c=new Uint8Array(f);for(n=0;n<u;n+=4)i=j[t.charCodeAt(n)],r=j[t.charCodeAt(n+1)],e=j[t.charCodeAt(n+2)],o=j[t.charCodeAt(n+3)],c[h++]=i<<2|r>>4,c[h++]=(15&r)<<4|e>>2,c[h++]=(3&e)<<6|63&o;return f}(t);return C(i,n)}return{base64:!0,data:t}},C=function(t,n){return"blob"===n?t instanceof Blob?t:new Blob([t]):t instanceof ArrayBuffer?t:t.buffer},T=String.fromCharCode(30);function U(){return new TransformStream({transform:function(t,n){!function(t,n){y&&t.data instanceof Blob?t.data.arrayBuffer().then(k).then(n):b&&(t.data instanceof ArrayBuffer||w(t.data))?n(k(t.data)):g(t,!1,(function(t){p||(p=new TextEncoder),n(p.encode(t))}))}(t,(function(i){var r,e=i.length;if(e<126)r=new Uint8Array(1),new DataView(r.buffer).setUint8(0,e);else if(e<65536){r=new Uint8Array(3);var o=new DataView(r.buffer);o.setUint8(0,126),o.setUint16(1,e)}else{r=new Uint8Array(9);var s=new DataView(r.buffer);s.setUint8(0,127),s.setBigUint64(1,BigInt(e))}t.data&&"string"!=typeof t.data&&(r[0]|=128),n.enqueue(r),n.enqueue(i)}))}})}function M(t){return t.reduce((function(t,n){return t+n.length}),0)}function x(t,n){if(t[0].length===n)return t.shift();for(var i=new Uint8Array(n),r=0,e=0;e<n;e++)i[e]=t[0][r++],r===t[0].length&&(t.shift(),r=0);return t.length&&r<t[0].length&&(t[0]=t[0].slice(r)),i}function I(t){if(t)return function(t){for(var n in I.prototype)t[n]=I.prototype[n];return t}(t)}I.prototype.on=I.prototype.addEventListener=function(t,n){return this.t=this.t||{},(this.t["$"+t]=this.t["$"+t]||[]).push(n),this},I.prototype.once=function(t,n){function i(){this.off(t,i),n.apply(this,arguments)}return i.fn=n,this.on(t,i),this},I.prototype.off=I.prototype.removeListener=I.prototype.removeAllListeners=I.prototype.removeEventListener=function(t,n){if(this.t=this.t||{},0==arguments.length)return this.t={},this;var i,r=this.t["$"+t];if(!r)return this;if(1==arguments.length)return delete this.t["$"+t],this;for(var e=0;e<r.length;e++)if((i=r[e])===n||i.fn===n){r.splice(e,1);break}return 0===r.length&&delete this.t["$"+t],this},I.prototype.emit=function(t){this.t=this.t||{};for(var n=new Array(arguments.length-1),i=this.t["$"+t],r=1;r<arguments.length;r++)n[r-1]=arguments[r];if(i){r=0;for(var e=(i=i.slice(0)).length;r<e;++r)i[r].apply(this,n)}return this},I.prototype.emitReserved=I.prototype.emit,I.prototype.listeners=function(t){return this.t=this.t||{},this.t["$"+t]||[]},I.prototype.hasListeners=function(t){return!!this.listeners(t).length};var R="function"==typeof Promise&&"function"==typeof Promise.resolve?function(t){return Promise.resolve().then(t)}:function(t,n){return n(t,0)},L="undefined"!=typeof self?self:"undefined"!=typeof window?window:Function("return this")();function _(t){for(var n=arguments.length,i=new Array(n>1?n-1:0),r=1;r<n;r++)i[r-1]=arguments[r];return i.reduce((function(n,i){return t.hasOwnProperty(i)&&(n[i]=t[i]),n}),{})}var D=L.setTimeout,P=L.clearTimeout;function $(t,n){n.useNativeTimers?(t.setTimeoutFn=D.bind(L),t.clearTimeoutFn=P.bind(L)):(t.setTimeoutFn=L.setTimeout.bind(L),t.clearTimeoutFn=L.clearTimeout.bind(L))}function F(){return Date.now().toString(36).substring(3)+Math.random().toString(36).substring(2,5)}var V=function(t){function n(n,i,r){var e;return(e=t.call(this,n)||this).description=i,e.context=r,e.type="TransportError",e}return s(n,t),n}(a(Error)),q=function(t){function n(n){var i;return(i=t.call(this)||this).writable=!1,$(i,n),i.opts=n,i.query=n.query,i.socket=n.socket,i.supportsBinary=!n.forceBase64,i}s(n,t);var i=n.prototype;return i.onError=function(n,i,r){return t.prototype.emitReserved.call(this,"error",new V(n,i,r)),this},i.open=function(){return this.readyState="opening",this.doOpen(),this},i.close=function(){return"opening"!==this.readyState&&"open"!==this.readyState||(this.doClose(),this.onClose()),this},i.send=function(t){"open"===this.readyState&&this.write(t)},i.onOpen=function(){this.readyState="open",this.writable=!0,t.prototype.emitReserved.call(this,"open")},i.onData=function(t){var n=S(t,this.socket.binaryType);this.onPacket(n)},i.onPacket=function(n){t.prototype.emitReserved.call(this,"packet",n)},i.onClose=function(n){this.readyState="closed",t.prototype.emitReserved.call(this,"close",n)},i.pause=function(t){},i.createUri=function(t){var n=arguments.length>1&&void 0!==arguments[1]?arguments[1]:{};return t+"://"+this.i()+this.o()+this.opts.path+this.u(n)},i.i=function(){var t=this.opts.hostname;return-1===t.indexOf(":")?t:"["+t+"]"},i.o=function(){return this.opts.port&&(this.opts.secure&&Number(443!==this.opts.port)||!this.opts.secure&&80!==Number(this.opts.port))?":"+this.opts.port:""},i.u=function(t){var n=function(t){var n="";for(var i in t)t.hasOwnProperty(i)&&(n.length&&(n+="&"),n+=encodeURIComponent(i)+"="+encodeURIComponent(t[i]));return n}(t);return n.length?"?"+n:""},n}(I),X=function(t){function n(){var n;return(n=t.apply(this,arguments)||this).h=!1,n}s(n,t);var r=n.prototype;return r.doOpen=function(){this.v()},r.pause=function(t){var n=this;this.readyState="pausing";var i=function(){n.readyState="paused",t()};if(this.h||!this.writable){var r=0;this.h&&(r++,this.once("pollComplete",(function(){--r||i()}))),this.writable||(r++,this.once("drain",(function(){--r||i()})))}else i()},r.v=function(){this.h=!0,this.doPoll(),this.emitReserved("poll")},r.onData=function(t){var n=this;(function(t,n){for(var i=t.split(T),r=[],e=0;e<i.length;e++){var o=S(i[e],n);if(r.push(o),"error"===o.type)break}return r})(t,this.socket.binaryType).forEach((function(t){if("opening"===n.readyState&&"open"===t.type&&n.onOpen(),"close"===t.type)return n.onClose({description:"transport closed by the server"}),!1;n.onPacket(t)})),"closed"!==this.readyState&&(this.h=!1,this.emitReserved("pollComplete"),"open"===this.readyState&&this.v())},r.doClose=function(){var t=this,n=function(){t.write([{type:"close"}])};"open"===this.readyState?n():this.once("open",n)},r.write=function(t){var n=this;this.writable=!1,function(t,n){var i=t.length,r=new Array(i),e=0;t.forEach((function(t,o){g(t,!1,(function(t){r[o]=t,++e===i&&n(r.join(T))}))}))}(t,(function(t){n.doWrite(t,(function(){n.writable=!0,n.emitReserved("drain")}))}))},r.uri=function(){var t=this.opts.secure?"https":"http",n=this.query||{};return!1!==this.opts.timestampRequests&&(n[this.opts.timestampParam]=F()),this.supportsBinary||n.sid||(n.b64=1),this.createUri(t,n)},i(n,[{key:"name",get:function(){return"polling"}}])}(q),H=!1;try{H="undefined"!=typeof XMLHttpRequest&&"withCredentials"in new XMLHttpRequest}catch(t){}var z=H;function J(){}var K=function(t){function n(n){var i;if(i=t.call(this,n)||this,"undefined"!=typeof location){var r="https:"===location.protocol,e=location.port;e||(e=r?"443":"80"),i.xd="undefined"!=typeof location&&n.hostname!==location.hostname||e!==n.port}return i}s(n,t);var i=n.prototype;return i.doWrite=function(t,n){var i=this,r=this.request({method:"POST",data:t});r.on("success",n),r.on("error",(function(t,n){i.onError("xhr post error",t,n)}))},i.doPoll=function(){var t=this,n=this.request();n.on("data",this.onData.bind(this)),n.on("error",(function(n,i){t.onError("xhr poll error",n,i)})),this.pollXhr=n},n}(X),Y=function(t){function n(n,i,r){var e;return(e=t.call(this)||this).createRequest=n,$(e,r),e.l=r,e.p=r.method||"GET",e.m=i,e.k=void 0!==r.data?r.data:null,e.A(),e}s(n,t);var i=n.prototype;return i.A=function(){var t,i=this,r=_(this.l,"agent","pfx","key","passphrase","cert","ca","ciphers","rejectUnauthorized","autoUnref");r.xdomain=!!this.l.xd;var e=this.j=this.createRequest(r);try{e.open(this.p,this.m,!0);try{if(this.l.extraHeaders)for(var o in e.setDisableHeaderCheck&&e.setDisableHeaderCheck(!0),this.l.extraHeaders)this.l.extraHeaders.hasOwnProperty(o)&&e.setRequestHeader(o,this.l.extraHeaders[o])}catch(t){}if("POST"===this.p)try{e.setRequestHeader("Content-type","text/plain;charset=UTF-8")}catch(t){}try{e.setRequestHeader("Accept","*/*")}catch(t){}null===(t=this.l.cookieJar)||void 0===t||t.addCookies(e),"withCredentials"in e&&(e.withCredentials=this.l.withCredentials),this.l.requestTimeout&&(e.timeout=this.l.requestTimeout),e.onreadystatechange=function(){var t;3===e.readyState&&(null===(t=i.l.cookieJar)||void 0===t||t.parseCookies(e.getResponseHeader("set-cookie"))),4===e.readyState&&(200===e.status||1223===e.status?i.O():i.setTimeoutFn((function(){i.B("number"==typeof e.status?e.status:0)}),0))},e.send(this.k)}catch(t){return void this.setTimeoutFn((function(){i.B(t)}),0)}"undefined"!=typeof document&&(this.S=n.requestsCount++,n.requests[this.S]=this)},i.B=function(t){this.emitReserved("error",t,this.j),this.N(!0)},i.N=function(t){if(void 0!==this.j&&null!==this.j){if(this.j.onreadystatechange=J,t)try{this.j.abort()}catch(t){}"undefined"!=typeof document&&delete n.requests[this.S],this.j=null}},i.O=function(){var t=this.j.responseText;null!==t&&(this.emitReserved("data",t),this.emitReserved("success"),this.N())},i.abort=function(){this.N()},n}(I);if(Y.requestsCount=0,Y.requests={},"undefined"!=typeof document)if("function"==typeof attachEvent)attachEvent("onunload",G);else if("function"==typeof addEventListener){addEventListener("onpagehide"in L?"pagehide":"unload",G,!1)}function G(){for(var t in Y.requests)Y.requests.hasOwnProperty(t)&&Y.requests[t].abort()}var Q,W=(Q=tt({xdomain:!1}))&&null!==Q.responseType,Z=function(t){function n(n){var i;i=t.call(this,n)||this;var r=n&&n.forceBase64;return i.supportsBinary=W&&!r,i}return s(n,t),n.prototype.request=function(){var t=arguments.length>0&&void 0!==arguments[0]?arguments[0]:{};return e(t,{xd:this.xd},this.opts),new Y(tt,this.uri(),t)},n}(K);function tt(t){var n=t.xdomain;try{if("undefined"!=typeof XMLHttpRequest&&(!n||z))return new XMLHttpRequest}catch(t){}if(!n)try{return new(L[["Active"].concat("Object").join("X")])("Microsoft.XMLHTTP")}catch(t){}}var nt="undefined"!=typeof navigator&&"string"==typeof navigator.product&&"reactnative"===navigator.product.toLowerCase(),it=function(t){function n(){return t.apply(this,arguments)||this}s(n,t);var r=n.prototype;return r.doOpen=function(){var t=this.uri(),n=this.opts.protocols,i=nt?{}:_(this.opts,"agent","perMessageDeflate","pfx","key","passphrase","cert","ca","ciphers","rejectUnauthorized","localAddress","protocolVersion","origin","maxPayload","family","checkServerIdentity");this.opts.extraHeaders&&(i.headers=this.opts.extraHeaders);try{this.ws=this.createSocket(t,n,i)}catch(t){return this.emitReserved("error",t)}this.ws.binaryType=this.socket.binaryType,this.addEventListeners()},r.addEventListeners=function(){var t=this;this.ws.onopen=function(){t.opts.autoUnref&&t.ws.C.unref(),t.onOpen()},this.ws.onclose=function(n){return t.onClose({description:"websocket connection closed",context:n})},this.ws.onmessage=function(n){return t.onData(n.data)},this.ws.onerror=function(n){return t.onError("websocket error",n)}},r.write=function(t){var n=this;this.writable=!1;for(var i=function(){var i=t[r],e=r===t.length-1;g(i,n.supportsBinary,(function(t){try{n.doWrite(i,t)}catch(t){}e&&R((function(){n.writable=!0,n.emitReserved("drain")}),n.setTimeoutFn)}))},r=0;r<t.length;r++)i()},r.doClose=function(){void 0!==this.ws&&(this.ws.onerror=function(){},this.ws.close(),this.ws=null)},r.uri=function(){var t=this.opts.secure?"wss":"ws",n=this.query||{};return this.opts.timestampRequests&&(n[this.opts.timestampParam]=F()),this.supportsBinary||(n.b64=1),this.createUri(t,n)},i(n,[{key:"name",get:function(){return"websocket"}}])}(q),rt=L.WebSocket||L.MozWebSocket,et=function(t){function n(){return t.apply(this,arguments)||this}s(n,t);var i=n.prototype;return i.createSocket=function(t,n,i){return nt?new rt(t,n,i):n?new rt(t,n):new rt(t)},i.doWrite=function(t,n){this.ws.send(n)},n}(it),ot=function(t){function n(){return t.apply(this,arguments)||this}s(n,t);var r=n.prototype;return r.doOpen=function(){var t=this;try{this.T=new WebTransport(this.createUri("https"),this.opts.transportOptions[this.name])}catch(t){return this.emitReserved("error",t)}this.T.closed.then((function(){t.onClose()})).catch((function(n){t.onError("webtransport error",n)})),this.T.ready.then((function(){t.T.createBidirectionalStream().then((function(n){var i=function(t,n){O||(O=new TextDecoder);var i=[],r=0,e=-1,o=!1;return new TransformStream({transform:function(s,u){for(i.push(s);;){if(0===r){if(M(i)<1)break;var h=x(i,1);o=!(128&~h[0]),e=127&h[0],r=e<126?3:126===e?1:2}else if(1===r){if(M(i)<2)break;var f=x(i,2);e=new DataView(f.buffer,f.byteOffset,f.length).getUint16(0),r=3}else if(2===r){if(M(i)<8)break;var c=x(i,8),a=new DataView(c.buffer,c.byteOffset,c.length),v=a.getUint32(0);if(v>Math.pow(2,21)-1){u.enqueue(d);break}e=v*Math.pow(2,32)+a.getUint32(4),r=3}else{if(M(i)<e)break;var l=x(i,e);u.enqueue(S(o?l:O.decode(l),n)),r=0}if(0===e||e>t){u.enqueue(d);break}}}})}(Number.MAX_SAFE_INTEGER,t.socket.binaryType),r=n.readable.pipeThrough(i).getReader(),e=U();e.readable.pipeTo(n.writable),t.U=e.writable.getWriter();!function n(){r.read().then((function(i){var r=i.done,e=i.value;r||(t.onPacket(e),n())})).catch((function(t){}))}();var o={type:"open"};t.query.sid&&(o.data='{"sid":"'.concat(t.query.sid,'"}')),t.U.write(o).then((function(){return t.onOpen()}))}))}))},r.write=function(t){var n=this;this.writable=!1;for(var i=function(){var i=t[r],e=r===t.length-1;n.U.write(i).then((function(){e&&R((function(){n.writable=!0,n.emitReserved("drain")}),n.setTimeoutFn)}))},r=0;r<t.length;r++)i()},r.doClose=function(){var t;null===(t=this.T)||void 0===t||t.close()},i(n,[{key:"name",get:function(){return"webtransport"}}])}(q),st={websocket:et,webtransport:ot,polling:Z},ut=/^(?:(?![^:@\/?#]+:[^:@\/]*@)(http|https|ws|wss):\/\/)?((?:(([^:@\/?#]*)(?::([^:@\/?#]*))?)?@)?((?:[a-f0-9]{0,4}:){2,7}[a-f0-9]{0,4}|[^:\/?#]*)(?::(\d*))?)(((\/(?:[^?#](?![^?#\/]*\.[^?#\/.]+(?:[?#]|$)))*\/?)?([^?#\/]*))(?:\?([^#]*))?(?:#(.*))?)/,ht=["source","protocol","authority","userInfo","user","password","host","port","relative","path","directory","file","query","anchor"];function ft(t){if(t.length>8e3)throw"URI too long";var n=t,i=t.indexOf("["),r=t.indexOf("]");-1!=i&&-1!=r&&(t=t.substring(0,i)+t.substring(i,r).replace(/:/g,";")+t.substring(r,t.length));for(var e,o,s=ut.exec(t||""),u={},h=14;h--;)u[ht[h]]=s[h]||"";return-1!=i&&-1!=r&&(u.source=n,u.host=u.host.substring(1,u.host.length-1).replace(/;/g,":"),u.authority=u.authority.replace("[","").replace("]","").replace(/;/g,":"),u.ipv6uri=!0),u.pathNames=function(t,n){var i=/\/{2,9}/g,r=n.replace(i,"/").split("/");"/"!=n.slice(0,1)&&0!==n.length||r.splice(0,1);"/"==n.slice(-1)&&r.splice(r.length-1,1);return r}(0,u.path),u.queryKey=(e=u.query,o={},e.replace(/(?:^|&)([^&=]*)=?([^&]*)/g,(function(t,n,i){n&&(o[n]=i)})),o),u}var ct="function"==typeof addEventListener&&"function"==typeof removeEventListener,at=[];ct&&addEventListener("offline",(function(){at.forEach((function(t){return t()}))}),!1);var vt=function(t){function n(n,i){var r;if((r=t.call(this)||this).binaryType="arraybuffer",r.writeBuffer=[],r.M=0,r.I=-1,r.R=-1,r.L=-1,r._=1/0,n&&"object"===c(n)&&(i=n,n=null),n){var o=ft(n);i.hostname=o.host,i.secure="https"===o.protocol||"wss"===o.protocol,i.port=o.port,o.query&&(i.query=o.query)}else i.host&&(i.hostname=ft(i.host).host);return $(r,i),r.secure=null!=i.secure?i.secure:"undefined"!=typeof location&&"https:"===location.protocol,i.hostname&&!i.port&&(i.port=r.secure?"443":"80"),r.hostname=i.hostname||("undefined"!=typeof location?location.hostname:"localhost"),r.port=i.port||("undefined"!=typeof location&&location.port?location.port:r.secure?"443":"80"),r.transports=[],r.D={},i.transports.forEach((function(t){var n=t.prototype.name;r.transports.push(n),r.D[n]=t})),r.opts=e({path:"/engine.io",agent:!1,withCredentials:!1,upgrade:!0,timestampParam:"t",rememberUpgrade:!1,addTrailingSlash:!0,rejectUnauthorized:!0,perMessageDeflate:{threshold:1024},transportOptions:{},closeOnBeforeunload:!1},i),r.opts.path=r.opts.path.replace(/\/$/,"")+(r.opts.addTrailingSlash?"/":""),"string"==typeof r.opts.query&&(r.opts.query=function(t){for(var n={},i=t.split("&"),r=0,e=i.length;r<e;r++){var o=i[r].split("=");n[decodeURIComponent(o[0])]=decodeURIComponent(o[1])}return n}(r.opts.query)),ct&&(r.opts.closeOnBeforeunload&&(r.P=function(){r.transport&&(r.transport.removeAllListeners(),r.transport.close())},addEventListener("beforeunload",r.P,!1)),"localhost"!==r.hostname&&(r.$=function(){r.F("transport close",{description:"network connection lost"})},at.push(r.$))),r.opts.withCredentials&&(r.V=void 0),r.q(),r}s(n,t);var i=n.prototype;return i.createTransport=function(t){var n=e({},this.opts.query);n.EIO=4,n.transport=t,this.id&&(n.sid=this.id);var i=e({},this.opts,{query:n,socket:this,hostname:this.hostname,secure:this.secure,port:this.port},this.opts.transportOptions[t]);return new this.D[t](i)},i.q=function(){var t=this;if(0!==this.transports.length){var i=this.opts.rememberUpgrade&&n.priorWebsocketSuccess&&-1!==this.transports.indexOf("websocket")?"websocket":this.transports[0];this.readyState="opening";var r=this.createTransport(i);r.open(),this.setTransport(r)}else this.setTimeoutFn((function(){t.emitReserved("error","No transports available")}),0)},i.setTransport=function(t){var n=this;this.transport&&this.transport.removeAllListeners(),this.transport=t,t.on("drain",this.X.bind(this)).on("packet",this.H.bind(this)).on("error",this.B.bind(this)).on("close",(function(t){return n.F("transport close",t)}))},i.onOpen=function(){this.readyState="open",n.priorWebsocketSuccess="websocket"===this.transport.name,this.emitReserved("open"),this.flush()},i.H=function(t){if("opening"===this.readyState||"open"===this.readyState||"closing"===this.readyState)switch(this.emitReserved("packet",t),this.emitReserved("heartbeat"),t.type){case"open":this.onHandshake(JSON.parse(t.data));break;case"ping":this.J("pong"),this.emitReserved("ping"),this.emitReserved("pong"),this.K();break;case"error":var n=new Error("server error");n.code=t.data,this.B(n);break;case"message":this.emitReserved("data",t.data),this.emitReserved("message",t.data)}},i.onHandshake=function(t){this.emitReserved("handshake",t),this.id=t.sid,this.transport.query.sid=t.sid,this.I=t.pingInterval,this.R=t.pingTimeout,this.L=t.maxPayload,this.onOpen(),"closed"!==this.readyState&&this.K()},i.K=function(){var t=this;this.clearTimeoutFn(this.Y);var n=this.I+this.R;this._=Date.now()+n,this.Y=this.setTimeoutFn((function(){t.F("ping timeout")}),n),this.opts.autoUnref&&this.Y.unref()},i.X=function(){this.writeBuffer.splice(0,this.M),this.M=0,0===this.writeBuffer.length?this.emitReserved("drain"):this.flush()},i.flush=function(){if("closed"!==this.readyState&&this.transport.writable&&!this.upgrading&&this.writeBuffer.length){var t=this.G();this.transport.send(t),this.M=t.length,this.emitReserved("flush")}},i.G=function(){if(!(this.L&&"polling"===this.transport.name&&this.writeBuffer.length>1))return this.writeBuffer;for(var t,n=1,i=0;i<this.writeBuffer.length;i++){var r=this.writeBuffer[i].data;if(r&&(n+="string"==typeof(t=r)?function(t){for(var n=0,i=0,r=0,e=t.length;r<e;r++)(n=t.charCodeAt(r))<128?i+=1:n<2048?i+=2:n<55296||n>=57344?i+=3:(r++,i+=4);return i}(t):Math.ceil(1.33*(t.byteLength||t.size))),i>0&&n>this.L)return this.writeBuffer.slice(0,i);n+=2}return this.writeBuffer},i.W=function(){var t=this;if(!this._)return!0;var n=Date.now()>this._;return n&&(this._=0,R((function(){t.F("ping timeout")}),this.setTimeoutFn)),n},i.write=function(t,n,i){return this.J("message",t,n,i),this},i.send=function(t,n,i){return this.J("message",t,n,i),this},i.J=function(t,n,i,r){if("function"==typeof n&&(r=n,n=void 0),"function"==typeof i&&(r=i,i=null),"closing"!==this.readyState&&"closed"!==this.readyState){(i=i||{}).compress=!1!==i.compress;var e={type:t,data:n,options:i};this.emitReserved("packetCreate",e),this.writeBuffer.push(e),r&&this.once("flush",r),this.flush()}},i.close=function(){var t=this,n=function(){t.F("forced close"),t.transport.close()},i=function i(){t.off("upgrade",i),t.off("upgradeError",i),n()},r=function(){t.once("upgrade",i),t.once("upgradeError",i)};return"opening"!==this.readyState&&"open"!==this.readyState||(this.readyState="closing",this.writeBuffer.length?this.once("drain",(function(){t.upgrading?r():n()})):this.upgrading?r():n()),this},i.B=function(t){if(n.priorWebsocketSuccess=!1,this.opts.tryAllTransports&&this.transports.length>1&&"opening"===this.readyState)return this.transports.shift(),this.q();this.emitReserved("error",t),this.F("transport error",t)},i.F=function(t,n){if("opening"===this.readyState||"open"===this.readyState||"closing"===this.readyState){if(this.clearTimeoutFn(this.Y),this.transport.removeAllListeners("close"),this.transport.close(),this.transport.removeAllListeners(),ct&&(this.P&&removeEventListener("beforeunload",this.P,!1),this.$)){var i=at.indexOf(this.$);-1!==i&&at.splice(i,1)}this.readyState="closed",this.id=null,this.emitReserved("close",t,n),this.writeBuffer=[],this.M=0}},n}(I);vt.protocol=4;var lt=function(t){function n(){var n;return(n=t.apply(this,arguments)||this).Z=[],n}s(n,t);var i=n.prototype;return i.onOpen=function(){if(t.prototype.onOpen.call(this),"open"===this.readyState&&this.opts.upgrade)for(var n=0;n<this.Z.length;n++)this.tt(this.Z[n])},i.tt=function(t){var n=this,i=this.createTransport(t),r=!1;vt.priorWebsocketSuccess=!1;var e=function(){r||(i.send([{type:"ping",data:"probe"}]),i.once("packet",(function(t){if(!r)if("pong"===t.type&&"probe"===t.data){if(n.upgrading=!0,n.emitReserved("upgrading",i),!i)return;vt.priorWebsocketSuccess="websocket"===i.name,n.transport.pause((function(){r||"closed"!==n.readyState&&(c(),n.setTransport(i),i.send([{type:"upgrade"}]),n.emitReserved("upgrade",i),i=null,n.upgrading=!1,n.flush())}))}else{var e=new Error("probe error");e.transport=i.name,n.emitReserved("upgradeError",e)}})))};function o(){r||(r=!0,c(),i.close(),i=null)}var s=function(t){var r=new Error("probe error: "+t);r.transport=i.name,o(),n.emitReserved("upgradeError",r)};function u(){s("transport closed")}function h(){s("socket closed")}function f(t){i&&t.name!==i.name&&o()}var c=function(){i.removeListener("open",e),i.removeListener("error",s),i.removeListener("close",u),n.off("close",h),n.off("upgrading",f)};i.once("open",e),i.once("error",s),i.once("close",u),this.once("close",h),this.once("upgrading",f),-1!==this.Z.indexOf("webtransport")&&"webtransport"!==t?this.setTimeoutFn((function(){r||i.open()}),200):i.open()},i.onHandshake=function(n){this.Z=this.nt(n.upgrades),t.prototype.onHandshake.call(this,n)},i.nt=function(t){for(var n=[],i=0;i<t.length;i++)~this.transports.indexOf(t[i])&&n.push(t[i]);return n},n}(vt),pt=function(t){function n(n){var i=arguments.length>1&&void 0!==arguments[1]?arguments[1]:{},r="object"===c(n)?n:i;return(!r.transports||r.transports&&"string"==typeof r.transports[0])&&(r.transports=(r.transports||["polling","websocket","webtransport"]).map((function(t){return st[t]})).filter((function(t){return!!t}))),t.call(this,n,r)||this}return s(n,t),n}(lt);pt.protocol;var dt="function"==typeof ArrayBuffer,yt=function(t){return"function"==typeof ArrayBuffer.isView?ArrayBuffer.isView(t):t.buffer instanceof ArrayBuffer},bt=Object.prototype.toString,wt="function"==typeof Blob||"undefined"!=typeof Blob&&"[object BlobConstructor]"===bt.call(Blob),gt="function"==typeof File||"undefined"!=typeof File&&"[object FileConstructor]"===bt.call(File);function mt(t){return dt&&(t instanceof ArrayBuffer||yt(t))||wt&&t instanceof Blob||gt&&t instanceof File}function kt(t,n){if(!t||"object"!==c(t))return!1;if(Array.isArray(t)){for(var i=0,r=t.length;i<r;i++)if(kt(t[i]))return!0;return!1}if(mt(t))return!0;if(t.toJSON&&"function"==typeof t.toJSON&&1===arguments.length)return kt(t.toJSON(),!0);for(var e in t)if(Object.prototype.hasOwnProperty.call(t,e)&&kt(t[e]))return!0;return!1}function At(t){var n=[],i=t.data,r=t;return r.data=jt(i,n),r.attachments=n.length,{packet:r,buffers:n}}function jt(t,n){if(!t)return t;if(mt(t)){var i={_placeholder:!0,num:n.length};return n.push(t),i}if(Array.isArray(t)){for(var r=new Array(t.length),e=0;e<t.length;e++)r[e]=jt(t[e],n);return r}if("object"===c(t)&&!(t instanceof Date)){var o={};for(var s in t)Object.prototype.hasOwnProperty.call(t,s)&&(o[s]=jt(t[s],n));return o}return t}function Et(t,n){return t.data=Ot(t.data,n),delete t.attachments,t}function Ot(t,n){if(!t)return t;if(t&&!0===t._placeholder){if("number"==typeof t.num&&t.num>=0&&t.num<n.length)return n[t.num];throw new Error("illegal attachments")}if(Array.isArray(t))for(var i=0;i<t.length;i++)t[i]=Ot(t[i],n);else if("object"===c(t))for(var r in t)Object.prototype.hasOwnProperty.call(t,r)&&(t[r]=Ot(t[r],n));return t}var Bt,St=["connect","connect_error","disconnect","disconnecting","newListener","removeListener"];!function(t){t[t.CONNECT=0]="CONNECT",t[t.DISCONNECT=1]="DISCONNECT",t[t.EVENT=2]="EVENT",t[t.ACK=3]="ACK",t[t.CONNECT_ERROR=4]="CONNECT_ERROR",t[t.BINARY_EVENT=5]="BINARY_EVENT",t[t.BINARY_ACK=6]="BINARY_ACK"}(Bt||(Bt={}));var Nt=function(){function t(t){this.replacer=t}var n=t.prototype;return n.encode=function(t){return t.type!==Bt.EVENT&&t.type!==Bt.ACK||!kt(t)?[this.encodeAsString(t)]:this.encodeAsBinary({type:t.type===Bt.EVENT?Bt.BINARY_EVENT:Bt.BINARY_ACK,nsp:t.nsp,data:t.data,id:t.id})},n.encodeAsString=function(t){var n=""+t.type;return t.type!==Bt.BINARY_EVENT&&t.type!==Bt.BINARY_ACK||(n+=t.attachments+"-"),t.nsp&&"/"!==t.nsp&&(n+=t.nsp+","),null!=t.id&&(n+=t.id),null!=t.data&&(n+=JSON.stringify(t.data,this.replacer)),n},n.encodeAsBinary=function(t){var n=At(t),i=this.encodeAsString(n.packet),r=n.buffers;return r.unshift(i),r},t}(),Ct=function(t){function n(n){var i;return(i=t.call(this)||this).reviver=n,i}s(n,t);var i=n.prototype;return i.add=function(n){var i;if("string"==typeof n){if(this.reconstructor)throw new Error("got plaintext data when reconstructing a packet");var r=(i=this.decodeString(n)).type===Bt.BINARY_EVENT;r||i.type===Bt.BINARY_ACK?(i.type=r?Bt.EVENT:Bt.ACK,this.reconstructor=new Tt(i),0===i.attachments&&t.prototype.emitReserved.call(this,"decoded",i)):t.prototype.emitReserved.call(this,"decoded",i)}else{if(!mt(n)&&!n.base64)throw new Error("Unknown type: "+n);if(!this.reconstructor)throw new Error("got binary data when not reconstructing a packet");(i=this.reconstructor.takeBinaryData(n))&&(this.reconstructor=null,t.prototype.emitReserved.call(this,"decoded",i))}},i.decodeString=function(t){var i=0,r={type:Number(t.charAt(0))};if(void 0===Bt[r.type])throw new Error("unknown packet type "+r.type);if(r.type===Bt.BINARY_EVENT||r.type===Bt.BINARY_ACK){for(var e=i+1;"-"!==t.charAt(++i)&&i!=t.length;);var o=t.substring(e,i);if(o!=Number(o)||"-"!==t.charAt(i))throw new Error("Illegal attachments");r.attachments=Number(o)}if("/"===t.charAt(i+1)){for(var s=i+1;++i;){if(","===t.charAt(i))break;if(i===t.length)break}r.nsp=t.substring(s,i)}else r.nsp="/";var u=t.charAt(i+1);if(""!==u&&Number(u)==u){for(var h=i+1;++i;){var f=t.charAt(i);if(null==f||Number(f)!=f){--i;break}if(i===t.length)break}r.id=Number(t.substring(h,i+1))}if(t.charAt(++i)){var c=this.tryParse(t.substr(i));if(!n.isPayloadValid(r.type,c))throw new Error("invalid payload");r.data=c}return r},i.tryParse=function(t){try{return JSON.parse(t,this.reviver)}catch(t){return!1}},n.isPayloadValid=function(t,n){switch(t){case Bt.CONNECT:return Mt(n);case Bt.DISCONNECT:return void 0===n;case Bt.CONNECT_ERROR:return"string"==typeof n||Mt(n);case Bt.EVENT:case Bt.BINARY_EVENT:return Array.isArray(n)&&("number"==typeof n[0]||"string"==typeof n[0]&&-1===St.indexOf(n[0]));case Bt.ACK:case Bt.BINARY_ACK:return Array.isArray(n)}},i.destroy=function(){this.reconstructor&&(this.reconstructor.finishedReconstruction(),this.reconstructor=null)},n}(I),Tt=function(){function t(t){this.packet=t,this.buffers=[],this.reconPack=t}var n=t.prototype;return n.takeBinaryData=function(t){if(this.buffers.push(t),this.buffers.length===this.reconPack.attachments){var n=Et(this.reconPack,this.buffers);return this.finishedReconstruction(),n}return null},n.finishedReconstruction=function(){this.reconPack=null,this.buffers=[]},t}();var Ut=Number.isInteger||function(t){return"number"==typeof t&&isFinite(t)&&Math.floor(t)===t};function Mt(t){return"[object Object]"===Object.prototype.toString.call(t)}var xt=Object.freeze({__proto__:null,protocol:5,get PacketType(){return Bt},Encoder:Nt,Decoder:Ct,isPacketValid:function(t){return"string"==typeof t.nsp&&(void 0===(n=t.id)||Ut(n))&&function(t,n){switch(t){case Bt.CONNECT:return void 0===n||Mt(n);case Bt.DISCONNECT:return void 0===n;case Bt.EVENT:return Array.isArray(n)&&("number"==typeof n[0]||"string"==typeof n[0]&&-1===St.indexOf(n[0]));case Bt.ACK:return Array.isArray(n);case Bt.CONNECT_ERROR:return"string"==typeof n||Mt(n);default:return!1}}(t.type,t.data);var n}});function It(t,n,i){return t.on(n,i),function(){t.off(n,i)}}var Rt=Object.freeze({connect:1,connect_error:1,disconnect:1,disconnecting:1,newListener:1,removeListener:1}),Lt=function(t){function n(n,i,r){var o;return(o=t.call(this)||this).connected=!1,o.recovered=!1,o.receiveBuffer=[],o.sendBuffer=[],o.it=[],o.rt=0,o.ids=0,o.acks={},o.flags={},o.io=n,o.nsp=i,r&&r.auth&&(o.auth=r.auth),o.l=e({},r),o.io.et&&o.open(),o}s(n,t);var o=n.prototype;return o.subEvents=function(){if(!this.subs){var t=this.io;this.subs=[It(t,"open",this.onopen.bind(this)),It(t,"packet",this.onpacket.bind(this)),It(t,"error",this.onerror.bind(this)),It(t,"close",this.onclose.bind(this))]}},o.connect=function(){return this.connected||(this.subEvents(),this.io.ot||this.io.open(),"open"===this.io.st&&this.onopen()),this},o.open=function(){return this.connect()},o.send=function(){for(var t=arguments.length,n=new Array(t),i=0;i<t;i++)n[i]=arguments[i];return n.unshift("message"),this.emit.apply(this,n),this},o.emit=function(t){var n,i,r;if(Rt.hasOwnProperty(t))throw new Error('"'+t.toString()+'" is a reserved event name');for(var e=arguments.length,o=new Array(e>1?e-1:0),s=1;s<e;s++)o[s-1]=arguments[s];if(o.unshift(t),this.l.retries&&!this.flags.fromQueue&&!this.flags.volatile)return this.ut(o),this;var u={type:Bt.EVENT,data:o,options:{}};if(u.options.compress=!1!==this.flags.compress,"function"==typeof o[o.length-1]){var h=this.ids++,f=o.pop();this.ht(h,f),u.id=h}var c=null===(i=null===(n=this.io.engine)||void 0===n?void 0:n.transport)||void 0===i?void 0:i.writable,a=this.connected&&!(null===(r=this.io.engine)||void 0===r?void 0:r.W());return this.flags.volatile&&!c||(a?(this.notifyOutgoingListeners(u),this.packet(u)):this.sendBuffer.push(u)),this.flags={},this},o.ht=function(t,n){var i,r=this,e=null!==(i=this.flags.timeout)&&void 0!==i?i:this.l.ackTimeout;if(void 0!==e){var o=this.io.setTimeoutFn((function(){delete r.acks[t];for(var i=0;i<r.sendBuffer.length;i++)r.sendBuffer[i].id===t&&r.sendBuffer.splice(i,1);n.call(r,new Error("operation has timed out"))}),e),s=function(){r.io.clearTimeoutFn(o);for(var t=arguments.length,i=new Array(t),e=0;e<t;e++)i[e]=arguments[e];n.apply(r,i)};s.withError=!0,this.acks[t]=s}else this.acks[t]=n},o.emitWithAck=function(t){for(var n=this,i=arguments.length,r=new Array(i>1?i-1:0),e=1;e<i;e++)r[e-1]=arguments[e];return new Promise((function(i,e){var o=function(t,n){return t?e(t):i(n)};o.withError=!0,r.push(o),n.emit.apply(n,[t].concat(r))}))},o.ut=function(t){var n,i=this;"function"==typeof t[t.length-1]&&(n=t.pop());var r={id:this.rt++,tryCount:0,pending:!1,args:t,flags:e({fromQueue:!0},this.flags)};t.push((function(t){if(r===i.it[0]){if(null!==t)r.tryCount>i.l.retries&&(i.it.shift(),n&&n(t));else if(i.it.shift(),n){for(var e=arguments.length,o=new Array(e>1?e-1:0),s=1;s<e;s++)o[s-1]=arguments[s];n.apply(void 0,[null].concat(o))}return r.pending=!1,i.ft()}})),this.it.push(r),this.ft()},o.ft=function(){var t=arguments.length>0&&void 0!==arguments[0]&&arguments[0];if(this.connected&&0!==this.it.length){var n=this.it[0];n.pending&&!t||(n.pending=!0,n.tryCount++,this.flags=n.flags,this.emit.apply(this,n.args))}},o.packet=function(t){t.nsp=this.nsp,this.io.ct(t)},o.onopen=function(){var t=this;"function"==typeof this.auth?this.auth((function(n){t.vt(n)})):this.vt(this.auth)},o.vt=function(t){this.packet({type:Bt.CONNECT,data:this.lt?e({pid:this.lt,offset:this.dt},t):t})},o.onerror=function(t){this.connected||this.emitReserved("connect_error",t)},o.onclose=function(t,n){this.connected=!1,delete this.id,this.emitReserved("disconnect",t,n),this.yt()},o.yt=function(){var t=this;Object.keys(this.acks).forEach((function(n){if(!t.sendBuffer.some((function(t){return String(t.id)===n}))){var i=t.acks[n];delete t.acks[n],i.withError&&i.call(t,new Error("socket has been disconnected"))}}))},o.onpacket=function(t){if(t.nsp===this.nsp)switch(t.type){case Bt.CONNECT:t.data&&t.data.sid?this.onconnect(t.data.sid,t.data.pid):this.emitReserved("connect_error",new Error("It seems you are trying to reach a Socket.IO server in v2.x with a v3.x client, but they are not compatible (more information here: https://socket.io/docs/v3/migrating-from-2-x-to-3-0/)"));break;case Bt.EVENT:case Bt.BINARY_EVENT:this.onevent(t);break;case Bt.ACK:case Bt.BINARY_ACK:this.onack(t);break;case Bt.DISCONNECT:this.ondisconnect();break;case Bt.CONNECT_ERROR:this.destroy();var n=new Error(t.data.message);n.data=t.data.data,this.emitReserved("connect_error",n)}},o.onevent=function(t){var n=t.data||[];null!=t.id&&n.push(this.ack(t.id)),this.connected?this.emitEvent(n):this.receiveBuffer.push(Object.freeze(n))},o.emitEvent=function(n){if(this.bt&&this.bt.length){var i,e=r(this.bt.slice());try{for(e.s();!(i=e.n()).done;){i.value.apply(this,n)}}catch(t){e.e(t)}finally{e.f()}}t.prototype.emit.apply(this,n),this.lt&&n.length&&"string"==typeof n[n.length-1]&&(this.dt=n[n.length-1])},o.ack=function(t){var n=this,i=!1;return function(){if(!i){i=!0;for(var r=arguments.length,e=new Array(r),o=0;o<r;o++)e[o]=arguments[o];n.packet({type:Bt.ACK,id:t,data:e})}}},o.onack=function(t){var n=this.acks[t.id];"function"==typeof n&&(delete this.acks[t.id],n.withError&&t.data.unshift(null),n.apply(this,t.data))},o.onconnect=function(t,n){this.id=t,this.recovered=n&&this.lt===n,this.lt=n,this.connected=!0,this.emitBuffered(),this.emitReserved("connect"),this.ft(!0)},o.emitBuffered=function(){var t=this;this.receiveBuffer.forEach((function(n){return t.emitEvent(n)})),this.receiveBuffer=[],this.sendBuffer.forEach((function(n){t.notifyOutgoingListeners(n),t.packet(n)})),this.sendBuffer=[]},o.ondisconnect=function(){this.destroy(),this.onclose("io server disconnect")},o.destroy=function(){this.subs&&(this.subs.forEach((function(t){return t()})),this.subs=void 0),this.io.wt(this)},o.disconnect=function(){return this.connected&&this.packet({type:Bt.DISCONNECT}),this.destroy(),this.connected&&this.onclose("io client disconnect"),this},o.close=function(){return this.disconnect()},o.compress=function(t){return this.flags.compress=t,this},o.timeout=function(t){return this.flags.timeout=t,this},o.onAny=function(t){return this.bt=this.bt||[],this.bt.push(t),this},o.prependAny=function(t){return this.bt=this.bt||[],this.bt.unshift(t),this},o.offAny=function(t){if(!this.bt)return this;if(t){for(var n=this.bt,i=0;i<n.length;i++)if(t===n[i])return n.splice(i,1),this}else this.bt=[];return this},o.listenersAny=function(){return this.bt||[]},o.onAnyOutgoing=function(t){return this.gt=this.gt||[],this.gt.push(t),this},o.prependAnyOutgoing=function(t){return this.gt=this.gt||[],this.gt.unshift(t),this},o.offAnyOutgoing=function(t){if(!this.gt)return this;if(t){for(var n=this.gt,i=0;i<n.length;i++)if(t===n[i])return n.splice(i,1),this}else this.gt=[];return this},o.listenersAnyOutgoing=function(){return this.gt||[]},o.notifyOutgoingListeners=function(t){if(this.gt&&this.gt.length){var n,i=r(this.gt.slice());try{for(i.s();!(n=i.n()).done;){n.value.apply(this,t.data)}}catch(t){i.e(t)}finally{i.f()}}},i(n,[{key:"disconnected",get:function(){return!this.connected}},{key:"active",get:function(){return!!this.subs}},{key:"volatile",get:function(){return this.flags.volatile=!0,this}}])}(I);function _t(t){t=t||{},this.ms=t.min||100,this.max=t.max||1e4,this.factor=t.factor||2,this.jitter=t.jitter>0&&t.jitter<=1?t.jitter:0,this.attempts=0}_t.prototype.duration=function(){var t=this.ms*Math.pow(this.factor,this.attempts++);if(this.jitter){var n=Math.random(),i=Math.floor(n*this.jitter*t);t=1&Math.floor(10*n)?t+i:t-i}return 0|Math.min(t,this.max)},_t.prototype.reset=function(){this.attempts=0},_t.prototype.setMin=function(t){this.ms=t},_t.prototype.setMax=function(t){this.max=t},_t.prototype.setJitter=function(t){this.jitter=t};var Dt=function(t){function n(n,i){var r,e;(r=t.call(this)||this).nsps={},r.subs=[],n&&"object"===c(n)&&(i=n,n=void 0),(i=i||{}).path=i.path||"/socket.io",r.opts=i,$(r,i),r.reconnection(!1!==i.reconnection),r.reconnectionAttempts(i.reconnectionAttempts||1/0),r.reconnectionDelay(i.reconnectionDelay||1e3),r.reconnectionDelayMax(i.reconnectionDelayMax||5e3),r.randomizationFactor(null!==(e=i.randomizationFactor)&&void 0!==e?e:.5),r.backoff=new _t({min:r.reconnectionDelay(),max:r.reconnectionDelayMax(),jitter:r.randomizationFactor()}),r.timeout(null==i.timeout?2e4:i.timeout),r.st="closed",r.uri=n;var o=i.parser||xt;return r.encoder=new o.Encoder,r.decoder=new o.Decoder,r.et=!1!==i.autoConnect,r.et&&r.open(),r}s(n,t);var i=n.prototype;return i.reconnection=function(t){return arguments.length?(this.kt=!!t,t||(this.skipReconnect=!0),this):this.kt},i.reconnectionAttempts=function(t){return void 0===t?this.At:(this.At=t,this)},i.reconnectionDelay=function(t){var n;return void 0===t?this.jt:(this.jt=t,null===(n=this.backoff)||void 0===n||n.setMin(t),this)},i.randomizationFactor=function(t){var n;return void 0===t?this.Et:(this.Et=t,null===(n=this.backoff)||void 0===n||n.setJitter(t),this)},i.reconnectionDelayMax=function(t){var n;return void 0===t?this.Ot:(this.Ot=t,null===(n=this.backoff)||void 0===n||n.setMax(t),this)},i.timeout=function(t){return arguments.length?(this.Bt=t,this):this.Bt},i.maybeReconnectOnOpen=function(){!this.ot&&this.kt&&0===this.backoff.attempts&&this.reconnect()},i.open=function(t){var n=this;if(~this.st.indexOf("open"))return this;this.engine=new pt(this.uri,this.opts);var i=this.engine,r=this;this.st="opening",this.skipReconnect=!1;var e=It(i,"open",(function(){r.onopen(),t&&t()})),o=function(i){n.cleanup(),n.st="closed",n.emitReserved("error",i),t?t(i):n.maybeReconnectOnOpen()},s=It(i,"error",o);if(!1!==this.Bt){var u=this.Bt,h=this.setTimeoutFn((function(){e(),o(new Error("timeout")),i.close()}),u);this.opts.autoUnref&&h.unref(),this.subs.push((function(){n.clearTimeoutFn(h)}))}return this.subs.push(e),this.subs.push(s),this},i.connect=function(t){return this.open(t)},i.onopen=function(){this.cleanup(),this.st="open",this.emitReserved("open");var t=this.engine;this.subs.push(It(t,"ping",this.onping.bind(this)),It(t,"data",this.ondata.bind(this)),It(t,"error",this.onerror.bind(this)),It(t,"close",this.onclose.bind(this)),It(this.decoder,"decoded",this.ondecoded.bind(this)))},i.onping=function(){this.emitReserved("ping")},i.ondata=function(t){try{this.decoder.add(t)}catch(t){this.onclose("parse error",t)}},i.ondecoded=function(t){var n=this;R((function(){n.emitReserved("packet",t)}),this.setTimeoutFn)},i.onerror=function(t){this.emitReserved("error",t)},i.socket=function(t,n){var i=this.nsps[t];return i?this.et&&!i.active&&i.connect():(i=new Lt(this,t,n),this.nsps[t]=i),i},i.wt=function(t){for(var n=0,i=Object.keys(this.nsps);n<i.length;n++){var r=i[n];if(this.nsps[r].active)return}this.St()},i.ct=function(t){for(var n=this.encoder.encode(t),i=0;i<n.length;i++)this.engine.write(n[i],t.options)},i.cleanup=function(){this.subs.forEach((function(t){return t()})),this.subs.length=0,this.decoder.destroy()},i.St=function(){this.skipReconnect=!0,this.ot=!1,this.onclose("forced close")},i.disconnect=function(){return this.St()},i.onclose=function(t,n){var i;this.cleanup(),null===(i=this.engine)||void 0===i||i.close(),this.backoff.reset(),this.st="closed",this.emitReserved("close",t,n),this.kt&&!this.skipReconnect&&this.reconnect()},i.reconnect=function(){var t=this;if(this.ot||this.skipReconnect)return this;var n=this;if(this.backoff.attempts>=this.At)this.backoff.reset(),this.emitReserved("reconnect_failed"),this.ot=!1;else{var i=this.backoff.duration();this.ot=!0;var r=this.setTimeoutFn((function(){n.skipReconnect||(t.emitReserved("reconnect_attempt",n.backoff.attempts),n.skipReconnect||n.open((function(i){i?(n.ot=!1,n.reconnect(),t.emitReserved("reconnect_error",i)):n.onreconnect()})))}),i);this.opts.autoUnref&&r.unref(),this.subs.push((function(){t.clearTimeoutFn(r)}))}},i.onreconnect=function(){var t=this.backoff.attempts;this.ot=!1,this.backoff.reset(),this.emitReserved("reconnect",t)},n}(I),Pt={};function $t(t,n){"object"===c(t)&&(n=t,t=void 0);var i,r=function(t){var n=arguments.length>1&&void 0!==arguments[1]?arguments[1]:"",i=arguments.length>2?arguments[2]:void 0,r=t;i=i||"undefined"!=typeof location&&location,null==t&&(t=i.protocol+"//"+i.host),"string"==typeof t&&("/"===t.charAt(0)&&(t="/"===t.charAt(1)?i.protocol+t:i.host+t),/^(https?|wss?):\/\//.test(t)||(t=void 0!==i?i.protocol+"//"+t:"https://"+t),r=ft(t)),r.port||(/^(http|ws)$/.test(r.protocol)?r.port="80":/^(http|ws)s$/.test(r.protocol)&&(r.port="443")),r.path=r.path||"/";var e=-1!==r.host.indexOf(":")?"["+r.host+"]":r.host;return r.id=r.protocol+"://"+e+":"+r.port+n,r.href=r.protocol+"://"+e+(i&&i.port===r.port?"":":"+r.port),r}(t,(n=n||{}).path||"/socket.io"),e=r.source,o=r.id,s=r.path,u=Pt[o]&&s in Pt[o].nsps;return n.forceNew||n["force new connection"]||!1===n.multiplex||u?i=new Dt(e,n):(Pt[o]||(Pt[o]=new Dt(e,n)),i=Pt[o]),r.query&&!n.query&&(n.query=r.queryKey),i.socket(r.path,n)}return e($t,{Manager:Dt,Socket:Lt,io:$t,connect:$t}),$t}));
+//# sourceMappingURL=socket.io.min.js.map
diff --git a/Lab 6/order-up/server/templates/screen.html b/Lab 6/order-up/server/templates/screen.html
new file mode 100644
index 0000000..42aa7f7
--- /dev/null
+++ b/Lab 6/order-up/server/templates/screen.html	
@@ -0,0 +1,36 @@
+<!doctype html>
+<html lang="en">
+<head>
+  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
+  <title>Order Up! · Dinner rush</title>
+  <link rel="stylesheet" href="{{ url_for('static', filename='screen.css') }}">
+  <script defer src="{{ url_for('static', filename='socket.io.min.js') }}"></script>
+  <script defer src="{{ url_for('static', filename='screen.js') }}"></script>
+</head>
+<body data-simulator="{{ 'true' if simulator else 'false' }}">
+<main>
+  <header>
+    <div><p class="eyebrow">THREE COOKS. ONE KITCHEN.</p><h1>Order Up<span>!</span></h1></div>
+    <div class="scoreboard"><div><span class="eyebrow">SCORE</span><strong id="score">0</strong></div><div><span class="eyebrow">SERVICE LEFT</span><strong id="timer">3:00</strong></div></div>
+  </header>
+  <div class="service-bar"><span id="phase">KITCHEN CLOSED</span><span id="connection" role="status">Connecting…</span><button id="start" disabled>Start service</button></div>
+  <section aria-labelledby="orders-heading"><div class="section-title"><h2 id="orders-heading">On the rail</h2><span>Get it out while it’s hot.</span></div><div id="tickets" class="tickets"><p class="placeholder">Start service to receive your first order.</p></div></section>
+  <section aria-labelledby="counter-heading"><div class="section-title"><h2 id="counter-heading">The counter</h2><span id="capacity">0 / 6 spaces used</span></div><div id="counter" class="counter"></div></section>
+  <div class="stations"><section id="chop" class="station"></section><section id="cook" class="station"></section></div>
+  <p id="message" class="message" role="status" aria-live="polite">Getting the kitchen ready…</p>
+  {% if simulator %}
+  <section class="sim-panel" aria-labelledby="sim-heading">
+    <div class="section-title"><h2 id="sim-heading">Practice kitchen</h2><span>All three stations, right here.</span></div>
+    <fieldset id="controls" disabled><legend class="sr-only">Simulator controls</legend>
+    <div class="sim-grid"><div><h3>01 / Runner</h3><p>Get an ingredient. Select a counter slot, then send or trash it.</p>
+      <div class="buttons" id="get-buttons"><button data-get="lettuce">+ Lettuce</button><button data-get="tomato">+ Tomato</button><button data-get="patty">+ Patty</button><button data-get="bun">+ Bun</button></div>
+      <p id="selection">No counter slot selected</p><div class="buttons"><button data-send="chop">Send to Chop</button><button data-send="cook">Send to Cook</button><button id="trash">Trash</button></div>
+      <p>Select a ticket above to serve it. Missing ingredients stay on the counter.</p>
+    </div><div><h3>02 / Chopper</h3><p>Six chops finish an ingredient.</p><button id="do-chop">Chop <kbd>C</kbd></button></div>
+    <div><h3>03 / Cook</h3><p>Stir until done, then pull within 8 seconds.</p><div class="buttons"><button id="stir">Stir +3 <kbd>S</kbd></button><button id="pull">Pull <kbd>P</kbd></button></div></div></div>
+    </fieldset><p id="result" role="status" aria-live="polite">Start service to practice.</p>
+  </section>
+  {% endif %}
+  <footer><span id="online">Station connections pending</span><a href="{{ '/' if simulator else '/sim' }}">{{ 'Shared screen ↗' if simulator else 'Open practice kitchen ↗' }}</a></footer>
+</main>
+</body></html>
diff --git a/Lab 6/order-up/sim/network_check.py b/Lab 6/order-up/sim/network_check.py
new file mode 100644
index 0000000..4e3079c
--- /dev/null
+++ b/Lab 6/order-up/sim/network_check.py	
@@ -0,0 +1,63 @@
+"""Measure MQTT round-trip time to the running game server from each Pi."""
+import argparse
+import json
+from pathlib import Path
+import statistics
+import sys
+import threading
+import time
+import uuid
+sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
+from pi.common import make_client, connect, topic
+
+
+def main():
+    parser = argparse.ArgumentParser()
+    parser.add_argument("--count", type=int, default=10)
+    args = parser.parse_args()
+    if args.count <= 0:
+        parser.error("count must be positive")
+    client = make_client("ping")
+    subscribed, reply = threading.Event(), threading.Event()
+    expected = None
+    def on_connect(client, userdata, flags, reason, properties):
+        if not reason.is_failure:
+            client.subscribe(topic("pong"), qos=0)
+    def on_message(client, userdata, message):
+        try:
+            if json.loads(message.payload).get("id") == expected:
+                reply.set()
+        except (ValueError, AttributeError):
+            pass
+    client.on_connect = on_connect
+    client.on_subscribe = lambda *args: subscribed.set()
+    client.on_message = on_message
+    connect(client)
+    times = []
+    try:
+        if not subscribed.wait(10):
+            raise SystemExit("Broker connection timed out; check host, port and credentials")
+        for _ in range(args.count):
+            expected = uuid.uuid4().hex
+            reply.clear()
+            start = time.monotonic()
+            client.publish(topic("ping"), json.dumps({"id": expected}))
+            if reply.wait(3):
+                elapsed = (time.monotonic() - start) * 1000
+                times.append(elapsed)
+                print(f"{elapsed:.1f} ms")
+            else:
+                print("Timed out — is the server running with --mqtt and the same topic prefix?")
+            time.sleep(0.2)
+        print(f"Replies: {len(times)}/{args.count}")
+        if times:
+            print(f"Median {statistics.median(times):.1f} ms; max {max(times):.1f} ms")
+        if len(times) != args.count:
+            raise SystemExit(1)
+    finally:
+        client.disconnect()
+        client.loop_stop()
+
+
+if __name__ == "__main__":
+    main()
diff --git a/Lab 6/order-up/sim/sim_station.py b/Lab 6/order-up/sim/sim_station.py
new file mode 100644
index 0000000..0a2d368
--- /dev/null
+++ b/Lab 6/order-up/sim/sim_station.py	
@@ -0,0 +1,109 @@
+"""Keyboard stand-in. HTTP needs no broker; --mqtt exercises the Pi transport."""
+import argparse
+import json
+from pathlib import Path
+import shlex
+import sys
+import threading
+import time
+import urllib.error
+import urllib.request
+import uuid
+
+sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
+from pi.common import StationClient
+
+
+def command(role, words, state):
+    if not words:
+        return None
+    cmd = words[0].lower()
+    if role == "chop" and cmd == "chop":
+        return {"type": "chop"}
+    if role == "cook":
+        if cmd == "stir":
+            return {"type": "stir", "ticks": int(words[1]) if len(words) > 1 else 3}
+        if cmd == "pull":
+            return {"type": "pull"}
+    if role == "runner":
+        if cmd == "get" and len(words) == 2:
+            return {"action": "get", "item": words[1]}
+        if cmd in ("send", "trash") and len(words) == (3 if cmd == "send" else 2):
+            slot = int(words[1]) - 1
+            if not 0 <= slot < 6:
+                raise ValueError("Use slot numbers 1–6")
+            payload = {"action": cmd, "slot": slot, "version": state["counter_versions"][slot]}
+            if cmd == "send":
+                payload["to"] = words[2]
+            return payload
+        if cmd == "serve" and len(words) == 2:
+            return {"action": "serve", "ticket": int(words[1])}
+    raise ValueError("Unknown command; type help")
+
+
+def main():
+    parser = argparse.ArgumentParser(description=__doc__)
+    parser.add_argument("role", choices=("runner", "chop", "cook"))
+    parser.add_argument("--mqtt", action="store_true")
+    parser.add_argument("--url", default="http://127.0.0.1:5000")
+    args = parser.parse_args()
+    client = StationClient(args.role) if args.mqtt else None
+    stop = threading.Event()
+    worker = None
+
+    def http(path, data=None):
+        request = urllib.request.Request(args.url.rstrip("/") + path,
+                  data=json.dumps(data).encode() if data is not None else None,
+                  headers={"Content-Type": "application/json"})
+        with urllib.request.urlopen(request, timeout=5) as response:
+            return json.load(response)
+
+    if client:
+        client.start()
+        def service():
+            while not stop.wait(0.2):
+                client.service()
+        worker = threading.Thread(target=service, daemon=True)
+        worker.start()
+    help_text = "Commands: state, help, quit; HTTP only: start\nRunner: get tomato | send 1 chop | trash 2 | serve 1\nChop: chop\nCook: stir [ticks, default 3] | pull\nSlots are 1–6; ticket IDs are shown on the screen. MQTT results appear with state."
+    print(help_text)
+    try:
+        while True:
+            try:
+                words = shlex.split(input(f"{args.role}> "))
+                if not words:
+                    continue
+                if words[0] in ("quit", "exit"):
+                    break
+                if words[0] == "help":
+                    print(help_text)
+                    continue
+                if words[0] == "start":
+                    print("Start from the browser in MQTT mode" if client else http("/api/start", {}))
+                    continue
+                state = client.snapshot()[0] if client else http("/api/state")
+                if words[0] == "state":
+                    print(json.dumps(state, indent=2))
+                    if client:
+                        print("Last result:", client.snapshot()[1])
+                    continue
+                payload = command(args.role, words, state)
+                if client:
+                    print("Sent" if client.send(payload) else client.snapshot()[1])
+                else:
+                    payload.update(id=uuid.uuid4().hex, round_id=state.get("round_id"))
+                    print(http(f"/api/action/{args.role}", payload)["msg"])
+            except (ValueError, KeyError, urllib.error.URLError) as error:
+                print(error)
+    except (KeyboardInterrupt, EOFError):
+        pass
+    finally:
+        stop.set()
+        if worker:
+            worker.join(timeout=1)
+        if client:
+            client.close()
+
+
+if __name__ == "__main__":
+    main()
diff --git a/Lab 6/order-up/tests/mqtt_smoke.py b/Lab 6/order-up/tests/mqtt_smoke.py
new file mode 100644
index 0000000..ff17898
--- /dev/null
+++ b/Lab 6/order-up/tests/mqtt_smoke.py	
@@ -0,0 +1,92 @@
+"""Optional real-broker test: pip install amqtt; python tests/mqtt_smoke.py."""
+import asyncio
+import os
+from pathlib import Path
+import random
+import subprocess
+import sys
+import time
+import uuid
+sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
+from amqtt.broker import Broker
+from pi.common import StationClient
+from server.app import create_app
+from server.game import Game
+
+
+def wait_for(predicate, description, seconds=6):
+    deadline = time.monotonic() + seconds
+    while time.monotonic() < deadline:
+        if predicate():
+            return
+        time.sleep(0.03)
+    raise AssertionError(f"Timed out: {description}")
+
+
+def exercise():
+    app, socketio, runtime = create_app(Game(rng=random.Random(5)))
+    clients = {role: StationClient(role) for role in ("runner", "chop", "cook")}
+    try:
+        runtime.start(use_mqtt=True)
+        runtime.start_round()
+        for client in clients.values():
+            client.start()
+        wait_for(lambda: all(c.ready() for c in clients.values()), "all three clients ready")
+        wait_for(lambda: all(runtime.state()["online"].values()), "station presence")
+        runner, chop, cook = (clients[k] for k in ("runner", "chop", "cook"))
+        get = {"action":"get", "item":"tomato", "id":"duplicate-get"}
+        assert runner.send(get)
+        wait_for(lambda: not runner.pending, "get acknowledgement")
+        assert runner.send(get)
+        wait_for(lambda: not runner.pending, "duplicate acknowledgement")
+        assert runtime.state()["counter"].count("tomato") == 1
+        assert runner.send({"action":"send", "slot":0, "to":"chop"})
+        wait_for(lambda: chop.snapshot()[0]["chop"]["item"] == "tomato", "chop receives tomato")
+        for _ in range(6):
+            assert chop.send({"type":"chop"})
+        wait_for(lambda: "chopped_tomato" in runtime.state()["counter"], "six MQTT chops")
+        assert runner.send({"action":"send", "slot":0, "to":"cook"})
+        wait_for(lambda: cook.snapshot()[0]["cook"]["item"] == "chopped_tomato", "cook receives tomato")
+        assert cook.send({"type":"stir", "ticks":24})
+        wait_for(lambda: cook.snapshot()[0]["cook"]["status"] == "done", "stir finishes")
+        assert cook.send({"type":"pull", "id":"duplicate-pull"})
+        wait_for(lambda: not cook.pending, "pull acknowledgement")
+        assert cook.send({"type":"pull", "id":"duplicate-pull"})
+        wait_for(lambda: not cook.pending, "duplicate pull acknowledgement")
+        assert runtime.state()["counter"].count("soup") == 1
+        ticket = runtime.state()["tickets"][0]
+        assert ticket["recipe"] == "soup"
+        assert runner.send({"action":"serve", "ticket":ticket["id"]})
+        wait_for(lambda: runtime.state()["score"] >= 20, "served soup scores")
+        runner.close()
+        wait_for(lambda: not runtime.state()["online"]["runner"], "clean disconnect")
+        clients["runner"] = StationClient("runner")
+        clients["runner"].start()
+        wait_for(lambda: clients["runner"].ready(), "restarted Pi gets live state")
+        assert clients["runner"].snapshot()[0]["score"] == runtime.state()["score"]
+        subprocess.run([sys.executable, "sim/network_check.py", "--count", "3"], check=True)
+        runtime.close()
+        wait_for(lambda: not clients["runner"].ready(), "server disconnect pauses input")
+        assert not clients["runner"].send({"action":"get", "item":"bun"})
+        print("MQTT smoke passed: three roles, soup recipe, QoS deduplication, reconnect, presence, ping, server loss.")
+    finally:
+        for client in clients.values():
+            client.close()
+        runtime.close()
+
+
+async def main():
+    os.environ.update(MQTT_HOST="127.0.0.1", MQTT_PORT="18884", MQTT_TLS="0", ORDERUP_TOPIC="IDD/orderup-test-" + uuid.uuid4().hex)
+    os.environ.pop("MQTT_USERNAME", None)
+    os.environ.pop("MQTT_PASSWORD", None)
+    broker = Broker({"listeners":{"default":{"type":"tcp", "bind":"127.0.0.1:18884"}},
+                     "plugins":{"amqtt.plugins.authentication.AnonymousAuthPlugin":{"allow_anonymous":True}}})
+    await broker.start()
+    try:
+        await asyncio.to_thread(exercise)
+    finally:
+        await broker.shutdown()
+
+
+if __name__ == "__main__":
+    asyncio.run(main())
diff --git a/Lab 6/order-up/tests/test_app.py b/Lab 6/order-up/tests/test_app.py
new file mode 100644
index 0000000..6b3d3e1
--- /dev/null
+++ b/Lab 6/order-up/tests/test_app.py	
@@ -0,0 +1,72 @@
+import json
+from types import SimpleNamespace
+import unittest
+from unittest.mock import Mock
+from server.app import create_app
+from server.game import Game
+from pi.common import topic
+
+
+class AppTest(unittest.TestCase):
+    def setUp(self):
+        self.now = 0
+        self.app, self.socket, self.runtime = create_app(Game(clock=lambda: self.now))
+        self.http = self.app.test_client()
+
+    def test_pages_assets_and_initial_socket_state(self):
+        for path in ("/", "/sim", "/static/screen.js", "/static/screen.css", "/static/socket.io.min.js"):
+            with self.http.get(path) as response:
+                self.assertEqual(response.status_code, 200)
+        client = self.socket.test_client(self.app)
+        messages = client.get_received()
+        self.assertEqual(messages[0]["name"], "state")
+        self.assertEqual(messages[0]["args"][0]["phase"], "lobby")
+        client.disconnect()
+
+    def test_http_action_updates_socket_and_reconnect(self):
+        first = self.socket.test_client(self.app)
+        first.get_received()
+        self.assertTrue(self.http.post("/api/start", json={}).json["ok"])
+        data = {"action":"get", "item":"bun", "id":"x"}
+        self.assertTrue(self.http.post("/api/action/runner", json=data).json["ok"])
+        self.assertTrue(self.http.post("/api/action/runner", json=data).json["ok"])
+        self.runtime.publish_once()
+        state = first.get_received()[0]["args"][0]
+        self.assertEqual(state["counter"].count("bun"), 1)
+        second = self.socket.test_client(self.app)
+        self.assertEqual(second.get_received()[0]["args"][0]["counter"], state["counter"])
+        first.disconnect()
+        second.disconnect()
+
+    def test_malformed_http_and_oversized_body(self):
+        for value in (None, [], "string", 4):
+            self.assertFalse(self.http.post("/api/action/runner", json=value).json["ok"])
+        self.assertFalse(self.http.post("/api/action/invalid", json={}).json["ok"])
+        self.assertEqual(self.http.post("/api/action/runner", data='x' * 5000, content_type='application/json').status_code, 413)
+
+    def message(self, client, suffix, data, retained=False):
+        msg = SimpleNamespace(topic=topic(suffix), payload=json.dumps(data).encode(), retain=retained)
+        self.runtime.mqtt_message(client, None, msg)
+
+    def test_mqtt_routing_dedup_retained_and_malformed_messages(self):
+        self.runtime.start_round()
+        client = Mock()
+        data = {"action":"get", "item":"tomato", "id":"mqtt1"}
+        self.message(client, "runner/action", data, retained=True)
+        self.assertEqual(self.runtime.game.counter, [None]*6)
+        self.message(client, "runner/action", data)
+        self.message(client, "runner/action", data)
+        self.assertEqual(self.runtime.game.counter.count("tomato"), 1)
+        self.assertEqual(client.publish.call_count, 2)
+        self.assertEqual(client.publish.call_args.args[0], topic("runner/result"))
+        self.message(client, "runner/action", [])
+        self.runtime.mqtt_message(client, None, SimpleNamespace(topic=topic("chop/event"),payload=b'\xff',retain=False))
+        self.message(client, "ping", {"id":"probe"})
+        self.assertEqual(client.publish.call_args.args[0], topic("pong"))
+
+    def test_mqtt_presence_and_disconnect(self):
+        client = Mock()
+        self.runtime.mqtt_message(client, None, SimpleNamespace(topic=topic("chop/online"),payload=b'1',retain=True))
+        self.assertTrue(self.runtime.game.online["chop"])
+        self.runtime.mqtt_disconnect(client, None, None, None, None)
+        self.assertFalse(any(self.runtime.game.online.values()))
diff --git a/Lab 6/order-up/tests/test_controls.py b/Lab 6/order-up/tests/test_controls.py
new file mode 100644
index 0000000..4e88095
--- /dev/null
+++ b/Lab 6/order-up/tests/test_controls.py	
@@ -0,0 +1,77 @@
+import unittest
+from pi.controls import ChopDetector, FlickDetector, PressDetector, RunnerMenu
+from server.game import Game
+
+
+class ControlsTest(unittest.TestCase):
+    def test_chop_needs_release_and_cooldown(self):
+        d = ChopDetector()
+        self.assertFalse(d.sample((0, 0, 9.81), 0))
+        self.assertTrue(d.sample((0, 0, 30), 1))
+        self.assertFalse(d.sample((0, 0, 30), 2))
+        d.sample((0, 0, 9.81), 2.01)
+        self.assertTrue(d.sample((0, 0, 30), 2.02))
+        d.sample((0, 0, 9.81), 2.03)
+        self.assertFalse(d.sample((0, 0, 30), 2.04))
+
+    def test_gravity_rotation_does_not_chop(self):
+        d = ChopDetector()
+        for acceleration in ((9.81,0,0),(0,9.81,0),(0,0,-9.81)):
+            self.assertFalse(d.sample(acceleration, 1))
+
+    def test_flick_requires_center_and_handles_inversion(self):
+        d = FlickDetector()
+        self.assertEqual(d.sample(1000, 515), "up")
+        self.assertIsNone(d.sample(0, 515))
+        self.assertIsNone(d.sample(504, 515))
+        self.assertEqual(d.sample(504, 1000), "right")
+        self.assertEqual(FlickDetector(invert_up=True).sample(1000, 515), "down")
+
+    def test_press_is_debounced(self):
+        d = PressDetector()
+        self.assertTrue(d.sample(True, 0))
+        self.assertFalse(d.sample(True, 1))
+        d.sample(False, 1.01)
+        self.assertTrue(d.sample(True, 1.02))
+        d.sample(False, 1.03)
+        self.assertFalse(d.sample(True, 1.04))
+
+    def test_runner_get_and_back(self):
+        state = Game().snapshot()
+        state.update(phase="playing", round_id="test")
+        m = RunnerMenu()
+        self.assertIsNone(m.input("up", state))
+        m.input("down", state)
+        self.assertEqual(m.input("press", state), {"action":"get","item":"tomato","round_id":"test"})
+        m.input("right", state)
+        self.assertIn("Nothing available", m.lines())
+        m.input("left", state)
+        self.assertEqual(m.mode, "home")
+
+    def test_runner_send_latches_slot_version_and_back_is_unambiguous(self):
+        g = Game(clock=lambda: 0)
+        g.start()
+        g.handle("runner", {"action":"get", "item":"tomato", "id":"a"})
+        s = g.snapshot()
+        m = RunnerMenu()
+        m.input("right", s)
+        m.input("press", s)
+        self.assertEqual(m.mode, "station")
+        version = s["counter_versions"][0]
+        s["counter_versions"][0] += 1
+        p = m.input("left", s)
+        self.assertEqual(p["to"], "chop")
+        self.assertEqual(p["version"], version)
+        m.input("right", s)
+        m.input("press", s)
+        m.input("back", s)
+        self.assertEqual(m.mode, "home")
+
+    def test_runner_discards_selection_after_restart(self):
+        s = Game().snapshot()
+        s.update(phase="playing", round_id="first")
+        m = RunnerMenu()
+        m.input("up", s)
+        s["round_id"] = "second"
+        self.assertIsNone(m.input("press", s))
+        self.assertEqual(m.mode, "home")
diff --git a/Lab 6/order-up/tests/test_game.py b/Lab 6/order-up/tests/test_game.py
new file mode 100644
index 0000000..c2c478f
--- /dev/null
+++ b/Lab 6/order-up/tests/test_game.py	
@@ -0,0 +1,230 @@
+import itertools
+import random
+import unittest
+from server.game import Game, Rules, RECIPES
+
+
+class GameTest(unittest.TestCase):
+    def setUp(self):
+        self.now = 0
+        self.g = Game(clock=lambda: self.now, rng=random.Random(1))
+        self.ids = itertools.count()
+        self.g.start()
+
+    def action(self, action, **fields):
+        return self.g.handle("runner", {"action": action, "id": str(next(self.ids)), **fields})
+
+    def event(self, role, kind, **fields):
+        return self.g.handle(role, {"type": kind, "id": str(next(self.ids)), **fields})
+
+    def prepare(self, item, station):
+        self.assertTrue(self.action("get", item=item)["ok"])
+        index = self.g.counter.index(item)
+        self.assertTrue(self.action("send", slot=index, to=station)["ok"])
+        if station == "chop":
+            for _ in range(6):
+                self.assertTrue(self.event("chop", "chop")["ok"])
+        else:
+            self.assertTrue(self.event("cook", "stir", ticks=24)["ok"])
+            self.assertTrue(self.event("cook", "pull")["ok"])
+
+    def test_lobby_and_round_restart(self):
+        self.assertFalse(self.g.start()["ok"])
+        old = self.g.round_id
+        self.now = 180
+        self.g.tick()
+        self.assertEqual(self.g.phase, "over")
+        self.assertFalse(self.action("get", item="bun")["ok"])
+        self.assertTrue(self.g.start()["ok"])
+        self.assertNotEqual(self.g.round_id, old)
+        self.assertEqual(self.g.score, 0)
+
+    def test_all_recipes_can_be_prepared_and_served(self):
+        for recipe, definition in RECIPES.items():
+            with self.subTest(recipe=recipe):
+                self.setUp()
+                self.g.tickets[0]["recipe"] = recipe
+                if recipe == "salad":
+                    self.prepare("lettuce", "chop")
+                    self.prepare("tomato", "chop")
+                elif recipe == "burger":
+                    self.prepare("lettuce", "chop")
+                    self.prepare("patty", "cook")
+                    self.action("get", item="bun")
+                else:
+                    self.prepare("tomato", "chop")
+                    self.action("send", slot=0, to="cook")
+                    self.event("cook", "stir", ticks=24)
+                    self.event("cook", "pull")
+                self.assertTrue(self.action("serve", ticket=self.g.tickets[0]["id"])["ok"])
+                self.assertEqual(self.g.score, definition["points"] + 6)
+                self.assertEqual(self.g.counter, [None] * 6)
+
+    def test_missing_recipe_is_atomic(self):
+        self.g.tickets[0]["recipe"] = "burger"
+        self.action("get", item="bun")
+        before = self.g.snapshot()
+        result = self.action("serve", ticket=self.g.tickets[0]["id"])
+        self.assertFalse(result["ok"])
+        self.assertIn("cooked patty", result["msg"])
+        self.assertEqual(self.g.counter, before["counter"])
+        self.assertEqual(self.g.score, 0)
+        self.assertEqual(len(self.g.tickets), 1)
+
+    def test_invalid_prep_paths_ruin_food(self):
+        for station, items in (("chop", ["patty", "bun", "chopped_tomato"]),
+                               ("cook", ["lettuce", "tomato", "bun"])):
+            for item in items:
+                with self.subTest(station=station, item=item):
+                    self.setUp()
+                    if item == "chopped_tomato":
+                        self.prepare("tomato", "chop")
+                    else:
+                        self.action("get", item=item)
+                    self.action("send", slot=0, to=station)
+                    if station == "chop":
+                        for _ in range(6):
+                            self.event("chop", "chop")
+                    else:
+                        self.event("cook", "stir", ticks=24)
+                        self.event("cook", "pull")
+                    self.assertIn("ruined", self.g.counter)
+
+    def test_full_counter_and_busy_station(self):
+        for _ in range(6):
+            self.action("get", item="tomato")
+        self.assertFalse(self.action("get", item="bun")["ok"])
+        self.action("send", slot=0, to="chop")
+        before = list(self.g.counter)
+        self.assertFalse(self.action("send", slot=1, to="chop")["ok"])
+        self.assertEqual(self.g.counter, before)
+
+    def test_chop_waits_for_counter_then_drains(self):
+        self.action("get", item="lettuce")
+        self.action("send", slot=0, to="chop")
+        for _ in range(6):
+            self.action("get", item="bun")
+        for _ in range(6):
+            self.event("chop", "chop")
+        self.assertTrue(self.g.chop["waiting"])
+        self.assertFalse(self.event("chop", "chop")["ok"])
+        self.action("trash", slot=2)
+        self.assertEqual(self.g.counter[2], "chopped_lettuce")
+        self.assertIsNone(self.g.chop["item"])
+
+    def test_stir_stops_without_input_and_early_pull_rejected(self):
+        self.action("get", item="patty")
+        self.action("send", slot=0, to="cook")
+        self.event("cook", "stir", ticks=3)
+        self.now = 10
+        self.g.tick()
+        self.assertEqual(self.g.snapshot()["cook"]["progress"], 0.125)
+        self.assertFalse(self.event("cook", "pull")["ok"])
+
+    def test_burn_deadline_inclusive_and_burnt_recoverable(self):
+        self.action("get", item="patty")
+        self.action("send", slot=0, to="cook")
+        self.event("cook", "stir", ticks=24)
+        self.now = 8
+        self.assertTrue(self.event("cook", "pull")["ok"])
+        self.assertIn("burnt", self.g.counter)
+        self.assertTrue(self.action("trash", slot=0)["ok"])
+
+    def test_pulled_food_waits_safely_on_full_counter(self):
+        self.action("get", item="patty")
+        self.action("send", slot=0, to="cook")
+        for _ in range(6):
+            self.action("get", item="bun")
+        self.event("cook", "stir", ticks=24)
+        self.now = 7.99
+        self.event("cook", "pull")
+        self.now = 30
+        self.g.tick()
+        self.assertEqual(self.g.cook["item"], "cooked_patty")
+        self.assertTrue(self.g.cook["waiting"])
+        self.action("trash", slot=5)
+        self.assertEqual(self.g.counter[5], "cooked_patty")
+
+    def test_duplicate_runner_and_pull_ids_apply_once(self):
+        payload = {"action": "get", "item": "patty", "id": "unique"}
+        first = self.g.handle("runner", payload)
+        self.assertEqual(first, self.g.handle("runner", payload))
+        self.assertEqual(self.g.counter.count("patty"), 1)
+        self.action("send", slot=0, to="cook")
+        self.event("cook", "stir", ticks=24)
+        pull = {"type": "pull", "id": "unique"}
+        first = self.g.handle("cook", pull)
+        self.assertEqual(first, self.g.handle("cook", pull))
+        self.assertEqual(self.g.counter.count("cooked_patty"), 1)
+
+    def test_stale_slot_and_previous_round_rejected(self):
+        self.action("get", item="bun")
+        old_version = self.g.versions[0]
+        self.action("trash", slot=0)
+        self.action("get", item="bun")
+        self.assertFalse(self.action("trash", slot=0, version=old_version)["ok"])
+        old_round = self.g.round_id
+        self.now = 180
+        self.g.start()
+        self.assertFalse(self.action("get", item="bun", round_id=old_round)["ok"])
+
+    def test_expiry_precedes_serve_at_deadline(self):
+        ticket = self.g.tickets[0]["id"]
+        self.now = 60
+        self.assertFalse(self.action("serve", ticket=ticket)["ok"])
+        self.assertEqual(self.g.score, -10)
+        self.assertEqual(len(self.g.tickets), 3)
+
+    def test_delayed_tick_matches_continuous_ticks(self):
+        other = Game(clock=lambda: 0, rng=random.Random(1))
+        other.start()
+        for i in range(1, 181):
+            other.tick(i)
+        self.now = 1000
+        self.g.tick()
+        self.assertEqual(self.g.score, other.score)
+        self.assertEqual(self.g.tickets, other.tickets)
+        self.assertEqual(self.g.phase, "over")
+        score = self.g.score
+        self.now = 2000
+        self.g.tick()
+        self.assertEqual(self.g.score, score)
+
+    def test_end_of_round_freezes_ticket_timers(self):
+        self.now = 180
+        self.g.tick()
+        tickets = self.g.snapshot()["tickets"]
+        self.now = 1000
+        self.g.tick()
+        self.assertEqual(self.g.snapshot()["tickets"], tickets)
+
+    def test_ticket_cap(self):
+        game = Game(Rules(arrival_seconds=1), clock=lambda: 0)
+        game.start()
+        game.tick(20)
+        self.assertEqual(len(game.tickets), 4)
+
+    def test_malformed_payloads_do_not_mutate_items(self):
+        for payload in (None, [], "hi", {}, {"action": "get", "item": []},
+                        {"action": "trash", "slot": True}, {"action": "send", "slot": -1},
+                        {"action": "serve", "ticket": True}, {"action": []}):
+            if isinstance(payload, dict):
+                payload = {"id": str(next(self.ids)), **payload}
+            self.assertFalse(self.g.handle("runner", payload)["ok"])
+        self.assertEqual(self.g.counter, [None] * 6)
+        self.action("get", item="patty")
+        self.action("send", slot=0, to="cook")
+        for ticks in (True, 0, -1, 25, "3", 1.5, [], None):
+            self.assertFalse(self.event("cook", "stir", ticks=ticks)["ok"])
+        self.assertEqual(self.g.cook["ticks"], 0)
+
+    def test_invalid_rules(self):
+        for value in (0, -1, float('nan'), float('inf'), True):
+            with self.assertRaises(ValueError):
+                Rules(round_seconds=value)
+        with self.assertRaises(ValueError):
+            Rules(chops=1.5)
+
+
+if __name__ == "__main__":
+    unittest.main()
