"""Order Up! game server (runs on the laptop).

    MQTT (Pis) --> game.py (rules) --> MQTT retained state + Socket.IO (screen)

Run:
    cd "Lab 6/order-up/server"
    python app.py                       # class broker
    python app.py --broker localhost    # your own Mosquitto (demo-day backup)

Then open http://localhost:5050 on the laptop (or the laptop's IP from
another computer) for the shared screen.
"""

import argparse
import json
import os
import socket
import threading
import time
import uuid

import paho.mqtt.client as mqtt
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

from game import STATIONS, Game, Settings

# --- Settings (env vars or command-line flags override these) ------------------

BROKER = os.environ.get("ORDERUP_BROKER", "farlab.infosci.cornell.edu")
PORT = int(os.environ.get("ORDERUP_PORT", "1883"))
USERNAME = os.environ.get("ORDERUP_USER", "idd")
PASSWORD = os.environ.get("ORDERUP_PASS", "device@theFarm")
PREFIX = os.environ.get("ORDERUP_PREFIX", "IDD/orderup").rstrip("/")
WEB_PORT = int(os.environ.get("ORDERUP_WEB_PORT", "5050"))

TICK_SECONDS = 0.1       # how often timers advance
MIN_PUBLISH_GAP = 0.2    # state goes out at most 5 times a second

# --- App objects ---------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = "order-up"
# Threading mode on purpose (see GAME_PLAN.md): no eventlet monkey-patching.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

game = Game(Settings())
game_lock = threading.Lock()       # game.py is not thread-safe; MQTT and the loop share it
publish_lock = threading.Lock()
mqtt_client = None
topics = {}
_last_state_json = None
_last_publish_time = 0.0


def make_topics(prefix):
    return {
        "chop_event": f"{prefix}/chop/event",
        "cook_event": f"{prefix}/cook/event",
        "runner_action": f"{prefix}/runner/action",
        "online": f"{prefix}/+/online",
        "state": f"{prefix}/state",
        "result": f"{prefix}/{{station}}/result",
        "server_online": f"{prefix}/server/online",
        "ping": f"{prefix}/ping",
        "pong": f"{prefix}/pong/{{station}}",
    }


def now():
    return time.monotonic()


# --- Publishing ------------------------------------------------------------------

def push_state(force=False):
    """Send the state to MQTT and the browser if it changed, at most 5x/second.
    If we're inside the gap, the game loop picks it up on its next tick."""
    global _last_state_json, _last_publish_time
    # Hold publish_lock throughout so two threads can't send states out of order.
    with publish_lock:
        with game_lock:
            state = game.state()
            events = game.drain_events()
        if events:
            socketio.emit("events", events)

        state_json = json.dumps(state, sort_keys=True, separators=(",", ":"))
        if state_json == _last_state_json and not force:
            return
        if not force and now() - _last_publish_time < MIN_PUBLISH_GAP:
            return
        _last_state_json = state_json
        _last_publish_time = now()
        if mqtt_client is not None:
            mqtt_client.publish(topics["state"], state_json, qos=1, retain=True)
        socketio.emit("state", state)


def game_loop():
    while True:
        with game_lock:
            game.tick(now())
        push_state()
        socketio.sleep(TICK_SECONDS)


# --- MQTT --------------------------------------------------------------------------

def make_mqtt_client(client_id):
    """Works with paho-mqtt 1.x (what the lab pins) and 2.x."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    except AttributeError:
        return mqtt.Client(client_id=client_id)


def on_connect(client, userdata, flags, rc):
    if rc != 0:
        print(f"[MQTT] connection refused (rc={rc}). Check the broker, user and password.")
        return
    print(f"[MQTT] connected to {BROKER}:{PORT}")
    for key in ("chop_event", "cook_event", "runner_action", "online", "ping"):
        client.subscribe(topics[key], qos=1)
    client.publish(topics["server_online"], "1", qos=1, retain=True)
    push_state(force=True)


def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"[MQTT] lost connection (rc={rc}); paho will keep retrying")


def on_message(client, userdata, msg):
    topic = msg.topic
    raw = msg.payload.decode("utf-8", errors="replace").strip()

    if topic.endswith("/online"):
        station = topic[len(PREFIX) + 1:].split("/")[0]
        if station in STATIONS:
            online = raw == "1"
            with game_lock:
                game.set_online(station, online)
            print(f"[{station}] {'online' if online else 'OFFLINE'}")
            push_state()
        return

    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        print(f"[MQTT] ignoring non-JSON on {topic}: {raw[:80]}")
        return

    if topic == topics["ping"]:
        # Network check: echo straight back so a Pi can time the round trip.
        station = payload.get("station", "unknown") if isinstance(payload, dict) else "unknown"
        client.publish(topics["pong"].format(station=station), raw, qos=0)
        return

    result = None
    station = None
    with game_lock:
        t = now()
        if topic == topics["runner_action"]:
            station = "runner"
            result = game.handle_runner(payload, t)
        elif topic == topics["chop_event"]:
            game.handle_chop(payload, t)
        elif topic == topics["cook_event"]:
            station = "cook"
            result = game.handle_cook(payload, t)

    if result is not None:
        mark = "ok " if result["ok"] else "NO "
        print(f"[{station}] {mark} {json.dumps(payload)} -> {result['msg']}")
        client.publish(topics["result"].format(station=station), json.dumps(result), qos=1)
    push_state()


def start_mqtt():
    global mqtt_client
    client = make_mqtt_client(f"orderup-server-{uuid.uuid4().hex[:6]}")
    if USERNAME:
        client.username_pw_set(USERNAME, PASSWORD)
    client.will_set(topics["server_online"], "0", qos=1, retain=True)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=5)
    client.connect_async(BROKER, PORT, keepalive=15)
    client.loop_start()
    mqtt_client = client


# --- Web -------------------------------------------------------------------------------

@app.route("/")
def screen():
    return render_template("screen.html")


@socketio.on("connect")
def on_browser_connect():
    with game_lock:
        state = game.state()
    emit("state", state)  # just to the browser that connected


@socketio.on("start")
def on_browser_start():
    """Space bar on the shared screen starts a round (handy for testing)."""
    with game_lock:
        game.start(now())
    push_state(force=True)


@socketio.on("lobby")
def on_browser_lobby():
    """Escape on the shared screen goes back to the lobby."""
    with game_lock:
        game.reset()
    push_state(force=True)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "localhost"


def main():
    global BROKER, PORT, PREFIX, WEB_PORT, topics
    parser = argparse.ArgumentParser(description="Order Up! game server")
    parser.add_argument("--broker", default=BROKER)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--prefix", default=PREFIX)
    parser.add_argument("--web-port", type=int, default=WEB_PORT)
    args = parser.parse_args()
    BROKER, PORT, PREFIX, WEB_PORT = args.broker, args.port, args.prefix.rstrip("/"), args.web_port
    topics = make_topics(PREFIX)

    # Check the web port BEFORE connecting to MQTT. Otherwise a failed start can
    # leave a retained "server online" behind, and the Pis think a server is running.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(("0.0.0.0", WEB_PORT))
    except OSError:
        print(f"Port {WEB_PORT} is already in use. Is another copy of the server still running?")
        print(f"Stop it, or start this one with:  python server/app.py --web-port {WEB_PORT + 1}")
        return
    finally:
        probe.close()

    print("=" * 60)
    print("  Order Up! game server")
    print(f"  Broker:        {BROKER}:{PORT}   topics under {PREFIX}/")
    print(f"  Shared screen: http://localhost:{WEB_PORT}  or  http://{lan_ip()}:{WEB_PORT}")
    print("  Space on the screen starts a round, Esc returns to the lobby.")
    print("=" * 60)

    start_mqtt()
    socketio.start_background_task(game_loop)
    try:
        socketio.run(app, host="0.0.0.0", port=WEB_PORT, debug=False,
                     allow_unsafe_werkzeug=True)
    finally:
        if mqtt_client is not None:
            mqtt_client.publish(topics["server_online"], "0", qos=1, retain=True)
            time.sleep(0.2)
            mqtt_client.loop_stop()
            mqtt_client.disconnect()


if __name__ == "__main__":
    main()
