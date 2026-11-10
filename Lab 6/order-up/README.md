# Order Up! (code)

The code for the co-op kitchen game described in our [game plan](https://github.com/mc3223/Peppers-Ghost/blob/Fall2026/Lab%206/GAME_PLAN.md). The laptop runs the game, and each Pi senses its player and shows what the server tells it.

```text
order-up/
├── server/                    # laptop
│   ├── game.py                # every rule; no network code
│   ├── app.py                 # MQTT <-> game.py <-> Socket.IO glue, publishes state
│   ├── templates/screen.html  # the shared screen
│   ├── static/socket.io.min.js  # bundled so the screen works without internet
│   └── mosquitto-local.conf   # backup broker for demo day
├── pi/
│   ├── common.py              # broker settings, StationLink (MQTT + online/last-will)
│   ├── display.py             # Mini PiTFT drawing + buttons
│   ├── chop_station.py        # IMU knife -> chops
│   ├── cook_station.py        # encoder pan -> stir/pull, servo heat needle, encoder LED
│   ├── runner_station.py      # joystick -> menus
│   ├── runner_menu.py         # the Runner's menus (shared with the simulator)
│   └── network_check.py       # milestone 2: round-trip times
├── sim/sim_station.py         # keyboard stand-in for any or all Pis
├── tests/                     # pytest: rules + the Pis' hardware-free logic
├── .vscode/                   # Run and Debug entries + test settings for VS Code
├── requirements-server.txt
└── requirements-pi.txt
```

## Play a round on one laptop (no Pis)

```bash
cd "Lab 6/order-up"
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-server.txt
python -m pytest tests                 # 49 tests, well under a second

python server/app.py                   # terminal 1: the game server
python sim/sim_station.py all          # terminal 2 (same folder, venv active): all three stations
```

Then open http://localhost:5050 for the shared screen. Space starts a round, Esc returns to the lobby and M mutes. (The port is 5050, not the lab's usual 5000, because macOS AirPlay often holds 5000. Change it with `--web-port`.)

In VS Code, `.vscode/launch.json` has Run and Debug entries for all of this: **Server + simulator** starts both with F5. See the VS Code setup guide for the full walkthrough.

Simulator keys: arrows, Enter and Backspace act as the Runner's joystick, press and back button. `c` chops, `s` stirs (hold it down), `p` pulls. `python sim_station.py runner` (or `chop`, `cook`) stands in for just one missing Pi.

Everything uses the class broker by default. Add `--broker localhost` to every command if you're running Mosquitto yourself.

## Run it on the Pis

On each Pi, the first time:

```bash
cd "Lab 6/order-up"
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-pi.txt
sudo systemctl stop piscreen.service   # frees the Mini PiTFT
i2cdetect -y 1                         # check the parts are there (below)
```

| Station | I2C parts | Check the hardware | Play |
|---|---|---|---|
| Chop | LSM6DS3 (`0x6a` or `0x6b`) | `python pi/chop_station.py --calibrate` | `python pi/chop_station.py` |
| Cook | Encoder (`0x36`), Servo pHAT (`0x40`) | `python pi/cook_station.py --test-needle` | `python pi/cook_station.py` |
| Runner | Joystick (`0x20`) | `python pi/runner_station.py --test` | `python pi/runner_station.py` |

- **Chop:** `--calibrate` prints the biggest jolt every half second. Chop for real, then wave and tilt the knife, and set `CHOP_THRESHOLD` (top of `chop_station.py`) between the two.
- **Cook:** the Servo pHAT needs its own USB-C power. If the needle runs backwards on your dial, set `SERVO_REVERSED = True`. Needle angles: 0° is cold, 60° is done, and 120° is burnt.
- **Runner:** if `--test` shows a flick coming out the wrong way, flip the sign in `UP_AXIS` or `RIGHT_AXIS` at the top of `runner_station.py`. The defaults match the Lab 4 `dessert_box.py` notes. The joystick press confirms, the PiTFT's top button goes back, and the bottom button goes home.
- **Network check (milestone 2):** with the server running, run `python pi/network_check.py chop` (or `cook` or `runner`) on each Pi. It prints round-trip times through the broker alone and through the server.

Each Pi shows a red **No broker** or **No server** tag on its screen when something's missing, and the shared screen marks a dropped Pi as offline (via the MQTT last-will).

## Demo-day backup broker

If campus Wi-Fi or the class broker is down, put everything on one hotspot and run Mosquitto on the laptop:

```bash
mosquitto -c server/mosquitto-local.conf
python server/app.py --broker localhost
python pi/chop_station.py --broker <laptop IP>      # same for the other Pis
```

The server prints the laptop's IP when it starts. `ORDERUP_BROKER=<ip>` also works instead of `--broker`.

## Protocol

The topics and payloads follow the game plan, under `IDD/orderup/`. The code adds a few things the plan didn't cover:

| Addition | Why |
|---|---|
| `runner/action` with `{"action": "start"}` | The Runner starts a round from the lobby or game-over screen by pressing the joystick |
| `item` field on `send` and `trash` (`{"action":"send","slot":2,"to":"chop","item":"tomato"}`) | The server rejects the action if the slot changed since the Runner picked it |
| `cook/result` | Replies to `pull`, the same way `runner/result` replies to Runner actions (for example, "Counter full! Runner, clear a slot") |
| `server/online` (retained, with a last-will message) | Lets a Pi tell "server down" apart from "broker down" |
| `ping` → `pong/<station>` | Lets `network_check.py` time the round trip |
| Extra state fields | `round_seconds`, ticket `duration`/`needs`/`points`/`ready`, `chop.result`/`waiting`, `cook.burn_seconds`/`result`, `pantry`, `online`, `message`, `stats` |

Ids are `<station letter><session>-<n>` (for example `r71fd-3`), so a Pi that restarts never reuses an id the server has already seen.

## Rules decisions we made while coding (change them if you disagree)

- A wrong item still gets processed and comes out **ruined** (for example, chopping a bun six times). Ruined and burnt food can't be sent to a station, only trashed.
- The Cook can't pull food before it's done. Burnt food has to be pulled (it goes to the counter as `burnt`) and then trashed.
- Stirring in either direction counts. Progress only moves while stirring, and 30 encoder ticks cook an item (`cook_ticks_needed`).
- Tip = 10 × (time left ÷ 60), rounded. The score can go below zero.
- The Runner's Get and Trash lists stay open after an action so you can grab or clear several things in a row. Send and Serve go back home. Every list opens at the top.

All the numbers are in `Settings` at the top of `server/game.py`.
