"""Shared MQTT code for every Order Up! station (and the laptop simulator).

No hardware imports here, so the simulator and tests can use it on a laptop.

Broker settings come from environment variables so we can switch to our own
Mosquitto broker on demo day without editing code:

    ORDERUP_BROKER=192.168.1.20 python chop_station.py
or
    python chop_station.py --broker 192.168.1.20
"""

import argparse
import json
import os
import threading
import time
import uuid

import paho.mqtt.client as mqtt

BROKER = os.environ.get("ORDERUP_BROKER", "farlab.infosci.cornell.edu")
PORT = int(os.environ.get("ORDERUP_PORT", "1883"))
USERNAME = os.environ.get("ORDERUP_USER", "idd")
PASSWORD = os.environ.get("ORDERUP_PASS", "device@theFarm")
PREFIX = os.environ.get("ORDERUP_PREFIX", "IDD/orderup").rstrip("/")


def add_broker_args(parser):
    parser.add_argument("--broker", default=BROKER, help=f"MQTT broker (default {BROKER})")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--prefix", default=PREFIX, help=f"topic prefix (default {PREFIX})")
    return parser


def make_client(client_id):
    """paho-mqtt 1.x (what the lab pins) and 2.x take different arguments."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    except AttributeError:
        return mqtt.Client(client_id=client_id)


class StationLink:
    """One station's connection to the game.

    - Announces itself on <prefix>/<station>/online: "1" while connected, with a
      retained last-will "0" so the shared screen notices if the Pi drops off.
    - Keeps the latest game state from <prefix>/state (retained, so a Pi that
      restarts catches up right away).
    - Receives replies on <prefix>/<station>/result.
    - send() publishes events/actions, and new_id() makes ids the server uses to
      ignore duplicate deliveries.

    Callbacks run on paho's network thread, so keep them short and don't touch
    I2C from them.
    """

    def __init__(self, station, broker=BROKER, port=PORT, prefix=PREFIX,
                 on_state=None, on_result=None, log=print):
        self.station = station
        self.log = log          # the simulator swaps this out so prints don't mess up curses
        self.broker = broker
        self.port = port
        self.prefix = prefix.rstrip("/")
        self.on_state = on_state
        self.on_result = on_result

        self.state = None
        self.state_time = 0.0          # time.monotonic() when the state arrived
        self.connected = False
        self.server_online = False
        self._session = uuid.uuid4().hex[:4]   # keeps ids unique across restarts
        self._count = 0
        self._id_lock = threading.Lock()

        self.client = make_client(f"orderup-{station}-{self._session}")
        if USERNAME:
            self.client.username_pw_set(USERNAME, PASSWORD)
        self.client.will_set(self.topic(station, "online"), "0", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=5)

    def topic(self, *parts):
        return "/".join([self.prefix, *parts])

    def start(self):
        self.log(f"[{self.station}] connecting to {self.broker}:{self.port} ...")
        self.client.connect_async(self.broker, self.port, keepalive=15)
        self.client.loop_start()
        return self

    def close(self):
        try:
            self.client.publish(self.topic(self.station, "online"), "0", qos=1, retain=True)
            time.sleep(0.2)
        finally:
            self.client.loop_stop()
            self.client.disconnect()

    def new_id(self):
        with self._id_lock:
            self._count += 1
            return f"{self.station[0]}{self._session}-{self._count}"

    def send(self, subtopic, payload, qos=0):
        """Publish JSON to <prefix>/<subtopic>, e.g. send("chop/event", {...})."""
        return self.client.publish(self.topic(subtopic), json.dumps(payload), qos=qos)

    # --- paho callbacks ---

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            self.log(f"[{self.station}] broker refused connection (rc={rc})")
            return
        self.connected = True
        self.log(f"[{self.station}] connected")
        client.subscribe(self.topic("state"), qos=1)
        client.subscribe(self.topic("server", "online"), qos=1)
        client.subscribe(self.topic(self.station, "result"), qos=1)
        client.publish(self.topic(self.station, "online"), "1", qos=1, retain=True)

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            self.log(f"[{self.station}] lost connection, retrying...")

    def _on_message(self, client, userdata, msg):
        raw = msg.payload.decode("utf-8", errors="replace")
        if msg.topic == self.topic("server", "online"):
            self.server_online = raw.strip() == "1"
            return
        try:
            data = json.loads(raw)
        except ValueError:
            return
        if msg.topic == self.topic("state"):
            self.state = data
            self.state_time = time.monotonic()
            if self.on_state:
                self.on_state(data)
        elif msg.topic == self.topic(self.station, "result") and self.on_result:
            self.on_result(data)

    def status_text(self):
        """Short connection status for a station screen, or None if all good."""
        if not self.connected:
            return "No broker"
        if not self.server_online:
            return "No server"
        if self.state is None:
            return "Waiting..."
        return None


def nice(item):
    """'chopped_tomato' -> 'chopped tomato'."""
    return item.replace("_", " ") if item else ""


def parse_station_args(description):
    parser = argparse.ArgumentParser(description=description)
    add_broker_args(parser)
    return parser
