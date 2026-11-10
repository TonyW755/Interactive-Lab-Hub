"""Order Up! game rules.

This file holds every rule of the game and nothing else: no MQTT, no Flask, no
real clock. app.py feeds it actions and the current time, then publishes
whatever state() returns. Keeping it pure means tests/test_game.py can play a
whole round in milliseconds.

Every method that depends on time takes `now` (seconds, from any monotonic
clock). The game never calls time.time() itself.
"""

import math
import random
from collections import OrderedDict
from dataclasses import dataclass

# --- Recipes and ingredients --------------------------------------------------

RECIPES = {
    "salad": {"needs": ["chopped_lettuce", "chopped_tomato"], "points": 10},
    "burger": {"needs": ["bun", "cooked_patty", "chopped_lettuce"], "points": 20},
    "soup": {"needs": ["soup"], "points": 20},
}

# What the Runner can get from the pantry.
PANTRY = ["lettuce", "tomato", "patty", "bun"]

# What each station turns an item into. Anything not listed becomes "ruined".
CHOP_RESULTS = {"lettuce": "chopped_lettuce", "tomato": "chopped_tomato"}
COOK_RESULTS = {"chopped_tomato": "soup", "patty": "cooked_patty"}

# Items that can't go back to a station (they can only be trashed).
UNSENDABLE = {"ruined", "burnt"}

STATIONS = ("chop", "cook", "runner")


def nice(item):
    """'cooked_patty' -> 'cooked patty', 'burnt' -> 'burnt food' for messages."""
    if not item:
        return "nothing"
    return f"{item} food" if item in UNSENDABLE else item.replace("_", " ")


@dataclass
class Settings:
    """Every number we expect to tune in playtesting lives here."""

    round_seconds: float = 180
    counter_slots: int = 6
    max_tickets: int = 4
    ticket_interval: float = 20      # average gap between new tickets
    ticket_jitter: float = 4         # +/- random spread on that gap
    ticket_seconds: float = 60       # how long a ticket lasts
    expire_penalty: int = 10
    max_tip: int = 10                # tip for serving with the full time left
    chops_needed: int = 6
    cook_ticks_needed: int = 30      # encoder ticks of stirring to finish an item
    max_ticks_per_message: int = 40  # ignore absurd stir messages
    burn_seconds: float = 8          # window to pull a done item before it burns


class Game:
    def __init__(self, settings=None, rng=None):
        self.s = settings or Settings()
        self.rng = rng or random.Random()
        self.online = {name: False for name in STATIONS}
        self._message_seq = 0
        self._results = OrderedDict()  # (station, id) -> result, for de-duplication
        self.reset()

    # --- Round lifecycle ------------------------------------------------------

    def reset(self):
        """Back to the lobby with an empty kitchen."""
        self.phase = "lobby"
        self.score = 0
        self.round_ends = None
        self.tickets = []
        self.next_ticket_id = 1
        self.next_ticket_at = None
        self.counter = [None] * self.s.counter_slots
        self._clear_chop()
        self._clear_cook()
        self.message = None
        self.stats = {"served": 0, "expired": 0, "trashed": 0, "burnt": 0, "ruined": 0}
        self.events = []
        self._now = 0.0

    def start(self, now):
        """Start a new round. Works from the lobby or the game-over screen."""
        if self.phase == "playing":
            return False
        events_before = self.events
        self.reset()
        self.events = events_before
        self.phase = "playing"
        self._now = now
        self.round_ends = now + self.s.round_seconds
        self._spawn_ticket(now)
        self.next_ticket_at = now + self._next_gap()
        self._event("round_start")
        self._say("Round started! Good luck, chefs.", ok=True, station="server")
        return True

    def tick(self, now):
        """Advance timers. Call this often (app.py does it 10 times a second)."""
        self._now = now
        if self.phase != "playing":
            return
        if now >= self.round_ends:
            self._end_round()
            return

        # Tickets expire...
        for ticket in list(self.tickets):
            if now >= ticket["expires_at"]:
                self.tickets.remove(ticket)
                self.score -= self.s.expire_penalty
                self.stats["expired"] += 1
                self._event("expired", recipe=ticket["recipe"], penalty=self.s.expire_penalty)
                self._say(f"{nice(ticket['recipe']).title()} order expired! -{self.s.expire_penalty}",
                          ok=False, station="server")

        # ...and new ones arrive.
        if now >= self.next_ticket_at:
            if len(self.tickets) < self.s.max_tickets:
                self._spawn_ticket(now)
            self.next_ticket_at = now + self._next_gap()

        # Food left on the heat burns.
        if self.cook["status"] == "done" and now >= self.cook["burn_at"]:
            self.cook["status"] = "burning"
            self.cook["result"] = "burnt"
            self.stats["burnt"] += 1
            self._event("burnt", item=self.cook["item"])
            self._say(f"The {nice(self.cook['item'])} burnt! Pull it off.", ok=False, station="cook")

        self._flush_chop()

    def _end_round(self):
        self.phase = "over"
        self.tickets = []
        self._event("round_over", score=self.score)
        self._say(f"Time! Final score {self.score}", ok=True, station="server")

    # --- Inputs from the stations --------------------------------------------

    def handle_runner(self, payload, now):
        """Runner Pi actions: get, send, trash, serve, and start."""
        self.tick(now)
        return self._with_dedupe("runner", payload, lambda: self._runner(payload))

    def handle_chop(self, payload, now):
        """Chop Pi events. Returns None: chops get no reply."""
        self.tick(now)
        if not isinstance(payload, dict) or payload.get("type") != "chop":
            return None
        if self.phase != "playing":
            return None
        chop = self.chop
        if chop["item"] is None or chop["result"] is not None:
            return None  # nothing to chop, or already finished
        chop["progress"] += 1
        self._event("chop", progress=chop["progress"])
        if chop["progress"] >= self.s.chops_needed:
            chop["result"] = CHOP_RESULTS.get(chop["item"], "ruined")
            if chop["result"] == "ruined":
                self.stats["ruined"] += 1
            self._event("chop_done", item=chop["item"], result=chop["result"])
            self._flush_chop()
        return None

    def handle_cook(self, payload, now):
        """Cook Pi events: stir (no reply) and pull (reply with a result)."""
        self.tick(now)
        if not isinstance(payload, dict):
            return None
        kind = payload.get("type")
        if kind == "stir":
            self._stir(payload.get("ticks", 1))
            return None
        if kind == "pull":
            return self._with_dedupe("cook", payload, self._pull)
        return None

    def set_online(self, station, online):
        if station in self.online:
            self.online[station] = bool(online)

    # --- Runner actions -------------------------------------------------------

    def _runner(self, payload):
        action = payload.get("action")
        if action == "start":
            if self.start(self._now):
                return self._ok("Round started!")
            return self._fail("Already playing")
        if self.phase != "playing":
            return self._fail("No round running. Press to start!")
        if action == "get":
            return self._get(payload.get("item"))
        if action == "send":
            return self._send(payload.get("slot"), payload.get("to"), payload.get("item"))
        if action == "trash":
            return self._trash(payload.get("slot"), payload.get("item"))
        if action == "serve":
            return self._serve(payload.get("ticket"))
        return self._fail(f"Unknown action: {action}")

    def _get(self, item):
        if item not in PANTRY:
            return self._fail(f"No {nice(item)} in the pantry")
        slot = self._free_slot()
        if slot is None:
            return self._fail("Counter full! Trash something")
        self.counter[slot] = item
        return self._ok(f"Got {nice(item)}")

    def _send(self, slot, to, expected):
        item, error = self._counter_item(slot, expected)
        if error:
            return error
        if item in UNSENDABLE:
            return self._fail(f"Can't send {nice(item)}. Trash it")
        if to not in ("chop", "cook"):
            return self._fail("Send it to chop or cook")
        station = self.chop if to == "chop" else self.cook
        if station["item"] is not None:
            return self._fail(f"{to.title()} station is busy")
        self.counter[slot] = None
        if to == "chop":
            self._clear_chop()
            self.chop["item"] = item
        else:
            self._clear_cook()
            self.cook["item"] = item
            self.cook["status"] = "cooking"
        self._event("sent", item=item, to=to)
        self._flush_chop()
        return self._ok(f"Sent {nice(item)} to {to}")

    def _trash(self, slot, expected):
        item, error = self._counter_item(slot, expected)
        if error:
            return error
        self.counter[slot] = None
        self.stats["trashed"] += 1
        self._event("trashed", item=item)
        self._flush_chop()
        return self._ok(f"Trashed {nice(item)}")

    def _serve(self, ticket_id):
        ticket = next((t for t in self.tickets if t["id"] == ticket_id), None)
        if ticket is None:
            return self._fail("That order is gone")
        needs = RECIPES[ticket["recipe"]]["needs"]
        missing = self._missing(needs)
        if missing:
            return self._fail("Missing " + " + ".join(nice(m) for m in missing))
        for item in needs:
            self.counter[self.counter.index(item)] = None
        time_left = max(0.0, ticket["expires_at"] - self._now)
        tip = round(self.s.max_tip * time_left / self.s.ticket_seconds)
        points = RECIPES[ticket["recipe"]]["points"]
        self.score += points + tip
        self.tickets.remove(ticket)
        self.stats["served"] += 1
        self._event("served", recipe=ticket["recipe"], points=points, tip=tip)
        self._flush_chop()
        return self._ok(f"Served {nice(ticket['recipe'])}! +{points + tip}")

    # --- Cook -------------------------------------------------------------

    def _stir(self, ticks):
        if self.phase != "playing" or self.cook["status"] != "cooking":
            return
        try:
            ticks = abs(int(ticks))
        except (TypeError, ValueError):
            return
        ticks = min(ticks, self.s.max_ticks_per_message)
        if ticks == 0:
            return
        cook = self.cook
        # Count whole ticks: adding fractions (5/30 six times) never quite reaches 1.0.
        cook["ticks"] = min(self.s.cook_ticks_needed, cook["ticks"] + ticks)
        cook["progress"] = cook["ticks"] / self.s.cook_ticks_needed
        if cook["ticks"] >= self.s.cook_ticks_needed:
            cook["status"] = "done"
            cook["result"] = COOK_RESULTS.get(cook["item"], "ruined")
            if cook["result"] == "ruined":
                self.stats["ruined"] += 1
            cook["burn_at"] = self._now + self.s.burn_seconds
            self._event("cook_done", item=cook["item"], result=cook["result"])
            self._say(f"{nice(cook['result']).capitalize()} is ready! Pull it off the heat",
                      ok=True, station="cook")

    def _pull(self):
        if self.phase != "playing":
            return self._fail("No round running")
        cook = self.cook
        if cook["item"] is None:
            return self._fail("The pan is empty")
        if cook["status"] == "cooking":
            return self._fail("Not done yet. Keep stirring!")
        slot = self._free_slot()
        if slot is None:
            return self._fail("Counter full! Runner, clear a slot")
        result = cook["result"]
        self.counter[slot] = result
        self._clear_cook()
        self._event("pulled", result=result)
        return self._ok(f"Pulled {nice(result)}")

    # --- Helpers --------------------------------------------------------------

    def _flush_chop(self):
        """A finished chop item moves to the counter as soon as a slot is free."""
        chop = self.chop
        if chop["result"] is None:
            return
        slot = self._free_slot()
        if slot is None:
            chop["waiting"] = True
            return
        self.counter[slot] = chop["result"]
        self._clear_chop()

    def _clear_chop(self):
        self.chop = {"item": None, "progress": 0, "result": None, "waiting": False}

    def _clear_cook(self):
        self.cook = {"item": None, "ticks": 0, "progress": 0.0, "status": "empty",
                     "result": None, "burn_at": None}

    def _free_slot(self):
        try:
            return self.counter.index(None)
        except ValueError:
            return None

    def _counter_item(self, slot, expected):
        """Validate a counter slot from the network. Returns (item, error_result)."""
        if not isinstance(slot, int) or isinstance(slot, bool) or not 0 <= slot < len(self.counter):
            return None, self._fail("Pick a counter slot")
        item = self.counter[slot]
        if item is None:
            return None, self._fail("That slot is empty")
        if expected is not None and expected != item:
            return None, self._fail("Counter changed. Try again")
        return item, None

    def _missing(self, needs):
        available = [i for i in self.counter if i is not None]
        missing = []
        for item in needs:
            if item in available:
                available.remove(item)
            else:
                missing.append(item)
        return missing

    def _spawn_ticket(self, now):
        recipe = self.rng.choice(list(RECIPES))
        ticket = {"id": self.next_ticket_id, "recipe": recipe,
                  "expires_at": now + self.s.ticket_seconds}
        self.next_ticket_id += 1
        self.tickets.append(ticket)
        self._event("new_ticket", id=ticket["id"], recipe=recipe)

    def _next_gap(self):
        return self.s.ticket_interval + self.rng.uniform(-self.s.ticket_jitter, self.s.ticket_jitter)

    def _with_dedupe(self, station, payload, handler):
        """QoS 1 can deliver a message twice. Replay the first answer instead of
        applying the action again."""
        if not isinstance(payload, dict):
            return {"id": None, "ok": False, "msg": "Bad message"}
        msg_id = payload.get("id")
        key = (station, msg_id)
        if msg_id is not None and key in self._results:
            return self._results[key]
        result = handler()
        result["id"] = msg_id
        if msg_id is not None:
            self._results[key] = result
            while len(self._results) > 200:
                self._results.popitem(last=False)
        self._say(result["msg"], ok=result["ok"], station=station)
        return result

    def _ok(self, msg):
        return {"ok": True, "msg": msg}

    def _fail(self, msg):
        return {"ok": False, "msg": msg}

    def _say(self, text, ok, station):
        self._message_seq += 1
        self.message = {"text": text, "ok": ok, "station": station, "seq": self._message_seq}

    def _event(self, kind, **data):
        self.events.append({"type": kind, **data})

    def drain_events(self):
        """Events since the last call, for screen animations (served, expired...)."""
        events, self.events = self.events, []
        return events

    # --- Output ---------------------------------------------------------------

    def state(self):
        """Full game state as plain JSON-able data. This is what gets published
        retained on IDD/orderup/state, and what the shared screen draws."""
        now = self._now
        if self.phase == "playing":
            time_left = max(0, math.ceil(self.round_ends - now))
        elif self.phase == "lobby":
            time_left = int(self.s.round_seconds)
        else:
            time_left = 0

        tickets = []
        for t in self.tickets:
            recipe = RECIPES[t["recipe"]]
            tickets.append({
                "id": t["id"],
                "recipe": t["recipe"],
                "time_left": max(0, math.ceil(t["expires_at"] - now)),
                "duration": int(self.s.ticket_seconds),
                "needs": list(recipe["needs"]),
                "points": recipe["points"],
                "ready": not self._missing(recipe["needs"]),
            })

        cook = self.cook
        burn_in = None
        if cook["status"] == "done":
            burn_in = max(0, math.ceil(cook["burn_at"] - now))

        return {
            "phase": self.phase,
            "time_left": time_left,
            "round_seconds": int(self.s.round_seconds),
            "score": self.score,
            "tickets": tickets,
            "counter": list(self.counter),
            "chop": {
                "item": self.chop["item"],
                "progress": self.chop["progress"],
                "needed": self.s.chops_needed,
                "result": self.chop["result"],
                "waiting": self.chop["waiting"],
            },
            "cook": {
                "item": cook["item"],
                "progress": round(cook["progress"], 2),
                "status": cook["status"],
                "burn_in": burn_in,
                "burn_seconds": int(self.s.burn_seconds),
                "result": cook["result"],
            },
            "pantry": list(PANTRY),
            "online": dict(self.online),
            "message": self.message,
            "stats": dict(self.stats),
        }
