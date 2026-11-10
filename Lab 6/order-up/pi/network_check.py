"""Milestone 2: measure message round-trip times. Needs no sensors.

    python network_check.py chop          # run on each Pi with its station name
    python network_check.py laptop --count 50

It times two loops and prints min / median / max in milliseconds:
  1. broker only:   this device -> broker -> this device
  2. via server:    this device -> broker -> app.py -> broker -> this device
     (start the game server first, or this part times out)
"""

import argparse
import json
import statistics
import threading
import time
import uuid

from common import PASSWORD, USERNAME, add_broker_args, make_client


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("station", help="a name for this device, e.g. chop, cook, runner, laptop")
    parser.add_argument("--count", type=int, default=20)
    add_broker_args(parser)
    args = parser.parse_args()
    prefix = args.prefix.rstrip("/")

    echo_topic = f"{prefix}/netcheck/{args.station}-{uuid.uuid4().hex[:4]}"
    pong_topic = f"{prefix}/pong/{args.station}"
    arrived = {}
    got = threading.Event()

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload)
        except ValueError:
            return
        arrived[data.get("n")] = time.perf_counter()
        got.set()

    client = make_client(f"orderup-netcheck-{uuid.uuid4().hex[:6]}")
    if USERNAME:
        client.username_pw_set(USERNAME, PASSWORD)
    client.on_message = on_message
    client.connect(args.broker, args.port, keepalive=15)
    client.subscribe([(echo_topic, 0), (pong_topic, 0)])
    client.loop_start()
    time.sleep(0.5)

    for label, out_topic in (("broker only", echo_topic), ("via server", f"{prefix}/ping")):
        times = []
        for n in range(args.count):
            arrived.clear()
            got.clear()
            sent = time.perf_counter()
            client.publish(out_topic, json.dumps({"n": n, "station": args.station}))
            if got.wait(2.0) and n in arrived:
                times.append((arrived[n] - sent) * 1000)
            time.sleep(0.05)
        if times:
            print(f"{label:12s}: {len(times)}/{args.count} replies  min {min(times):6.1f} ms  "
                  f"median {statistics.median(times):6.1f} ms  max {max(times):6.1f} ms")
        else:
            print(f"{label:12s}: no replies" + ("  (is app.py running?)" if label == "via server" else ""))

    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
