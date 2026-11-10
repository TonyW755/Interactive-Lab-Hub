"""Runner menus. No hardware here: runner_station.py feeds it joystick flicks,
and sim/sim_station.py feeds it arrow keys.

From the home screen each joystick direction picks an action:

             up: GET
    left: TRASH ─●─ SEND :right
           down: SERVE

Lists always open at the top. Inside a list, flick up/down to move, press
to confirm, flick left (or the Pi's top button) to go back. In Send's
station choice, left = Chop and right = Cook, so only the top button goes
back there.

Menu movement stays on the Pi so it feels instant; only confirmed actions are
returned from handle() to be sent over MQTT.
"""

DEFAULT_PANTRY = ["lettuce", "tomato", "patty", "bun"]
DISHES = {"salad": "Salad", "burger": "Burger", "soup": "Soup"}
BAD_ITEMS = {"burnt", "ruined"}
BANNER_SECONDS = 2.5

# Events the menu understands
UP, DOWN, LEFT, RIGHT, PRESS, BACK, HOME = "up", "down", "left", "right", "press", "back", "home"


def nice(item):
    return item.replace("_", " ") if item else ""


class RunnerMenu:
    def __init__(self):
        self.state = None
        self.screen = "home"     # home | get | slots | station | tickets
        self.action = None       # "send" or "trash" while on the slots screen
        self.get_cursor = 0
        self.slot = None         # chosen counter slot
        self.ticket = None       # chosen ticket id
        self.ticket_index = 0
        self.banner = None       # {"text", "ok", "until"}

    # --- Inputs ------------------------------------------------------------------

    def set_state(self, state):
        was_playing = self.playing
        self.state = state
        if not self.playing:
            self.screen = "home"
        elif not was_playing:
            self.screen = "home"   # fresh round: start from home
        self._fix_selection()

    def show_result(self, result, now):
        self.banner = {"text": result.get("msg", ""), "ok": bool(result.get("ok")),
                       "until": now + BANNER_SECONDS}

    def handle(self, event, now):
        """Apply one input. Returns an action dict to publish, or None."""
        if not self.playing:
            if event == PRESS:
                self._note("Starting...", True, now)
                return {"action": "start"}
            return None
        if event == HOME:
            self.screen = "home"
            return None
        handler = getattr(self, f"_on_{self.screen}")
        return handler(event, now)

    # --- Screens -------------------------------------------------------------------

    def _on_home(self, event, now):
        # Every list opens at the top, so players can act without looking.
        if event == UP:
            self.screen = "get"
            self.get_cursor = 0
        elif event in (RIGHT, LEFT):
            self.screen = "slots"
            self.action = "send" if event == RIGHT else "trash"
            self.slot = self._first_occupied()
        elif event == DOWN:
            self.screen = "tickets"
            self.ticket_index = 0
            self._fix_selection(force_index=True)
        return None

    def _on_get(self, event, now):
        pantry = self.pantry
        if event in (UP, DOWN):
            step = -1 if event == UP else 1
            self.get_cursor = (self.get_cursor + step) % len(pantry)
        elif event == PRESS:
            item = pantry[self.get_cursor]
            self._note(f"Getting {nice(item)}...", True, now)
            return {"action": "get", "item": item}   # stay here to grab more
        elif event in (LEFT, BACK):
            self.screen = "home"
        return None

    def _on_slots(self, event, now):
        occupied = self._occupied()
        if event in (UP, DOWN):
            self._move_slot(-1 if event == UP else 1)
        elif event == PRESS:
            if self.slot not in occupied:
                self._note("Counter is empty", False, now)
                return None
            if self.action == "send":
                self.screen = "station"
                return None
            item = self.counter[self.slot]
            self._note(f"Trashing {nice(item)}...", True, now)
            return {"action": "trash", "slot": self.slot, "item": item}   # stay to trash more
        elif event in (LEFT, BACK):
            self.screen = "home"
        return None

    def _on_station(self, event, now):
        if event in (LEFT, RIGHT):
            to = "chop" if event == LEFT else "cook"
            item = self.counter[self.slot]
            self._note(f"Sending {nice(item)} to {to}...", True, now)
            self.screen = "home"
            return {"action": "send", "slot": self.slot, "to": to, "item": item}
        if event == BACK:
            self.screen = "slots"
        return None

    def _on_tickets(self, event, now):
        tickets = self.tickets
        if event in (UP, DOWN) and tickets:
            self.ticket_index = (self.ticket_index + (-1 if event == UP else 1)) % len(tickets)
            self.ticket = tickets[self.ticket_index]["id"]
        elif event == PRESS:
            if self.ticket is None:
                self._note("No orders yet", False, now)
                return None
            self._note("Serving...", True, now)
            self.screen = "home"
            return {"action": "serve", "ticket": self.ticket}
        elif event in (LEFT, BACK):
            self.screen = "home"
        return None

    # --- What to draw -----------------------------------------------------------------

    def view(self, now):
        """A plain dict describing the screen. Both the PiTFT and the terminal
        simulator draw from this, and it compares with == so the display only
        redraws when something changed."""
        banner = None
        if self.banner and now < self.banner["until"]:
            banner = (self.banner["text"], self.banner["ok"])

        if self.state is None:
            return {"kind": "idle", "title": "RUNNER", "lines": ["Waiting for the", "game server..."],
                    "hint": "", "banner": banner}
        if not self.playing:
            if self.state.get("phase") == "over":
                lines = ["Round over!", f"Score {self.state.get('score', 0)}"]
                hint = "Press to play again"
            else:
                lines = ["ORDER UP!", "Ready, chefs?"]
                hint = "Press to start"
            return {"kind": "idle", "title": "RUNNER", "lines": lines, "hint": hint, "banner": banner}

        counter = self.counter
        used = sum(1 for c in counter if c)
        if self.screen == "home":
            return {"kind": "home", "title": "RUNNER",
                    "info": f"{used}/{len(counter)}", "orders": len(self.tickets),
                    "hint": "flick to choose", "banner": banner}

        if self.screen == "get":
            full = used >= len(counter)
            items = [(nice(p).capitalize(), "") for p in self.pantry]
            return {"kind": "list", "title": "GET", "items": items, "cursor": self.get_cursor,
                    "hint": "COUNTER FULL" if full else "press: get  <: back",
                    "banner": banner}

        if self.screen == "slots":
            occupied = self._occupied()
            items = [(f"{s + 1}. {nice(counter[s])}", "bad" if counter[s] in BAD_ITEMS else "")
                     for s in occupied]
            cursor = occupied.index(self.slot) if self.slot in occupied else None
            verb = "send" if self.action == "send" else "trash"
            return {"kind": "list", "title": self.action.upper(), "items": items or [("(counter empty)", "dim")],
                    "cursor": cursor, "hint": f"press: {verb}  <: back", "banner": banner}

        if self.screen == "station":
            chop_busy = bool((self.state.get("chop") or {}).get("item"))
            cook_busy = bool((self.state.get("cook") or {}).get("item"))
            item = nice(counter[self.slot]) if self.slot is not None else ""
            return {"kind": "station", "title": "SEND TO", "item": item,
                    "left": ("CHOP", chop_busy), "right": ("COOK", cook_busy),
                    "hint": "top button: back", "banner": banner}

        # tickets
        items = []
        for t in self.tickets:
            tag = "ready" if t.get("ready") else ("urgent" if t.get("time_left", 99) <= 10 else "")
            mark = " OK" if t.get("ready") else ""
            items.append((f"{DISHES.get(t['recipe'], t['recipe'])} {t.get('time_left', 0)}s{mark}", tag))
        cursor = self.ticket_index if self.tickets else None
        return {"kind": "list", "title": "SERVE", "items": items or [("(no orders)", "dim")],
                "cursor": cursor, "hint": "press: serve  <: back", "banner": banner}

    # --- Helpers -------------------------------------------------------------------------

    @property
    def playing(self):
        return bool(self.state) and self.state.get("phase") == "playing"

    @property
    def counter(self):
        return (self.state or {}).get("counter") or []

    @property
    def tickets(self):
        return (self.state or {}).get("tickets") or []

    @property
    def pantry(self):
        return (self.state or {}).get("pantry") or DEFAULT_PANTRY

    def _occupied(self):
        return [i for i, item in enumerate(self.counter) if item]

    def _first_occupied(self):
        occupied = self._occupied()
        return occupied[0] if occupied else None

    def _move_slot(self, step):
        occupied = self._occupied()
        if not occupied:
            self.slot = None
            return
        if self.slot not in occupied:
            self.slot = occupied[0]
            return
        index = (occupied.index(self.slot) + step) % len(occupied)
        self.slot = occupied[index]

    def _fix_selection(self, force_index=False):
        """Keep the cursor on something real after the state changes."""
        self.get_cursor %= max(1, len(self.pantry))

        occupied = self._occupied()
        if self.slot not in occupied:
            if self.screen == "station":
                self.screen = "slots"
            later = [s for s in occupied if self.slot is not None and s > self.slot]
            earlier = [s for s in occupied if self.slot is not None and s < self.slot]
            self.slot = later[0] if later else (earlier[-1] if earlier else self._first_occupied())

        tickets = self.tickets
        ids = [t["id"] for t in tickets]
        if not ids:
            self.ticket, self.ticket_index = None, 0
        elif force_index or self.ticket not in ids:
            self.ticket_index = min(self.ticket_index, len(ids) - 1)
            self.ticket = ids[self.ticket_index]
        else:
            self.ticket_index = ids.index(self.ticket)

    def _note(self, text, ok, now):
        self.banner = {"text": text, "ok": ok, "until": now + BANNER_SECONDS}
