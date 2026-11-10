"""Tests for the hardware-free parts of the Pi stations."""

from chop_station import ChopDetector
from cook_station import NEEDLE_BURNT, NEEDLE_COLD, NEEDLE_DONE, StirCounter, needle_angle
from runner_menu import BACK, DOWN, HOME, LEFT, PRESS, RIGHT, UP, RunnerMenu
from runner_station import FlickDetector


# --- Chop detection -------------------------------------------------------------------

def feed(detector, magnitudes, start=0.0, dt=0.004):
    """Feed |a| values (straight down the z axis) and count chops."""
    chops = 0
    for i, m in enumerate(magnitudes):
        if detector.update(0.0, 0.0, m, start + i * dt):
            chops += 1
    return chops


def test_resting_knife_never_chops():
    assert feed(ChopDetector(), [9.81] * 500) == 0


def test_one_spike_is_one_chop():
    signal = [9.8] * 20 + [4, 25, 32, 28, 18] + [9.8] * 60
    assert feed(ChopDetector(), signal) == 1


def test_ringing_after_impact_does_not_double_count():
    # the blade bounces: motion stays high, never settles below the re-arm level
    signal = [9.8] * 10 + [30, 2, 28, 3, 26, 4, 24] + [9.8] * 60
    assert feed(ChopDetector(), signal) == 1


def test_six_separate_chops():
    one = [9.8] * 30 + [30] + [9.8] * 40     # ~0.28 s per chop at 250 Hz
    assert feed(ChopDetector(), one * 6) == 6


def test_gentle_waving_is_ignored():
    signal = [9.8 + (3 if i % 20 < 10 else -3) for i in range(400)]
    assert feed(ChopDetector(), signal) == 0


# --- Cook ---------------------------------------------------------------------------

def test_stir_counter_adds_both_directions_and_throttles():
    stir = StirCounter(gap=0.2)
    assert stir.update(0, 0.0) == 0          # first reading just sets the baseline
    assert stir.update(3, 0.05) == 3         # first movement goes out right away
    assert stir.update(1, 0.10) == 0         # 2 more ticks, but too soon to send
    assert stir.update(4, 0.15) == 0         # 3 more
    assert stir.update(4, 0.26) == 5         # sent together after the gap
    assert stir.stirring(0.3) and not stir.stirring(1.0)


def test_needle_zones():
    assert needle_angle(None) == NEEDLE_COLD
    assert needle_angle({"status": "empty"}) == NEEDLE_COLD
    assert needle_angle({"status": "cooking", "progress": 0.5}) == (NEEDLE_COLD + NEEDLE_DONE) / 2
    done = {"status": "done", "burn_in": 8, "burn_seconds": 8}
    assert needle_angle(done) == NEEDLE_DONE
    assert NEEDLE_DONE < needle_angle(done, seconds_since_state=4) < NEEDLE_BURNT
    assert needle_angle(done, seconds_since_state=20) == NEEDLE_BURNT
    assert needle_angle({"status": "burning"}) == NEEDLE_BURNT


# --- Joystick flicks ----------------------------------------------------------------------

def test_flick_fires_once_until_released():
    flicks = FlickDetector(center=(512, 512))
    # with the default mapping, a high "horizontal" reading means up
    assert flicks.update(1000, 512, 0.0) == UP
    assert flicks.update(1010, 512, 0.05) is None
    assert flicks.update(520, 512, 0.10) is None      # back to center
    assert flicks.update(512, 1000, 0.15) == RIGHT
    assert flicks.update(512, 512, 0.20) is None
    assert flicks.update(512, 20, 0.25) == LEFT


def test_holding_up_or_down_repeats():
    flicks = FlickDetector(center=(512, 512))
    assert flicks.update(20, 512, 0.0) == DOWN
    assert flicks.update(20, 512, 0.3) is None
    assert flicks.update(20, 512, 0.5) == DOWN
    assert flicks.update(20, 512, 0.6) is None
    assert flicks.update(20, 512, 0.7) == DOWN


# --- Runner menu -------------------------------------------------------------------------

def playing_state(**overrides):
    state = {
        "phase": "playing", "score": 0, "time_left": 150,
        "counter": ["tomato", None, "burnt", "bun", None, None],
        "tickets": [{"id": 4, "recipe": "salad", "time_left": 30, "ready": False},
                    {"id": 5, "recipe": "soup", "time_left": 8, "ready": True}],
        "chop": {"item": None}, "cook": {"item": "patty"},
        "pantry": ["lettuce", "tomato", "patty", "bun"],
    }
    state.update(overrides)
    return state


def menu_with(state=None):
    menu = RunnerMenu()
    menu.set_state(state or playing_state())
    return menu


def test_press_in_lobby_starts_round():
    menu = menu_with({"phase": "lobby", "counter": [None] * 6, "tickets": []})
    assert menu.handle(UP, 0) is None
    assert menu.handle(PRESS, 0) == {"action": "start"}


def test_get_stays_in_list_for_more():
    menu = menu_with()
    menu.handle(UP, 0)
    menu.handle(DOWN, 0)                       # lettuce -> tomato
    assert menu.handle(PRESS, 0) == {"action": "get", "item": "tomato"}
    assert menu.screen == "get"
    menu.handle(UP, 0)
    menu.handle(UP, 0)                         # wraps to bun
    assert menu.handle(PRESS, 0)["item"] == "bun"
    menu.handle(LEFT, 0)
    assert menu.screen == "home"


def test_send_picks_slot_then_station():
    menu = menu_with()
    menu.handle(RIGHT, 0)                      # SEND
    assert menu.slot == 0
    menu.handle(DOWN, 0)                       # skips the empty slot 1
    assert menu.slot == 2
    menu.handle(UP, 0)
    assert menu.handle(PRESS, 0) is None       # now choose a station
    assert menu.screen == "station"
    assert menu.handle(UP, 0) is None
    action = menu.handle(LEFT, 0)
    assert action == {"action": "send", "slot": 0, "to": "chop", "item": "tomato"}
    assert menu.screen == "home"


def test_back_button_from_station_choice():
    menu = menu_with()
    menu.handle(RIGHT, 0)
    menu.handle(PRESS, 0)
    menu.handle(BACK, 0)
    assert menu.screen == "slots"


def test_trash():
    menu = menu_with()
    menu.handle(LEFT, 0)                       # TRASH
    menu.handle(DOWN, 0)
    assert menu.handle(PRESS, 0) == {"action": "trash", "slot": 2, "item": "burnt"}
    assert menu.screen == "slots"


def test_serve_picks_ticket():
    menu = menu_with()
    menu.handle(DOWN, 0)                       # SERVE
    menu.handle(DOWN, 0)
    assert menu.handle(PRESS, 0) == {"action": "serve", "ticket": 5}
    assert menu.screen == "home"


def test_selection_follows_counter_changes():
    menu = menu_with()
    menu.handle(RIGHT, 0)
    menu.handle(DOWN, 0)                       # slot 2 (burnt)
    menu.handle(PRESS, 0)                      # station choice
    menu.set_state(playing_state(counter=["tomato", None, None, "bun", None, None]))
    assert menu.screen == "slots"              # the item vanished; back to the list
    assert menu.slot == 3


def test_ticket_selection_survives_expiry():
    menu = menu_with()
    menu.handle(DOWN, 0)
    menu.handle(DOWN, 0)                       # ticket 5
    menu.set_state(playing_state(tickets=[{"id": 4, "recipe": "salad", "time_left": 20, "ready": False}]))
    assert menu.ticket == 4


def test_round_end_returns_home_and_views_render():
    menu = menu_with()
    menu.handle(UP, 0)
    for screen_events in ([], [UP], [RIGHT], [RIGHT, PRESS], [LEFT], [DOWN]):
        menu.handle(HOME, 0)
        for e in screen_events:
            menu.handle(e, 0)
        view = menu.view(0)
        assert view["title"]
    menu.set_state(playing_state(phase="over", score=55))
    assert menu.screen == "home"
    assert menu.view(0)["kind"] == "idle"
    assert "55" in " ".join(menu.view(0)["lines"])
