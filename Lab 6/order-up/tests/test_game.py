"""Rules tests. Run from Lab 6/order-up with:  python -m pytest tests"""

import json
import random

import pytest

from game import Game, Settings


def make_game(**overrides):
    """A game with no randomness: tickets every 20 s exactly, always 'burger'
    unless a test sets the recipe by hand."""
    settings = Settings(ticket_jitter=0, **overrides)
    game = Game(settings, rng=random.Random(1))
    game.start(now=0)
    return game


def runner(game, now=0, **payload):
    return game.handle_runner(payload, now)


def fill_counter(game, items):
    for i, item in enumerate(items):
        game.counter[i] = item


def chop_all(game, now=0):
    for _ in range(game.s.chops_needed):
        game.handle_chop({"type": "chop"}, now)


def stir(game, ticks, now=0):
    game.handle_cook({"type": "stir", "ticks": ticks}, now)


# --- Round lifecycle -----------------------------------------------------------

def test_start_round_spawns_first_ticket():
    game = make_game()
    state = game.state()
    assert state["phase"] == "playing"
    assert state["time_left"] == 180
    assert len(state["tickets"]) == 1
    assert state["counter"] == [None] * 6


def test_lobby_rejects_actions_until_start():
    game = Game(Settings())
    result = game.handle_runner({"action": "get", "item": "bun", "id": "a"}, 0)
    assert not result["ok"]
    result = game.handle_runner({"action": "start", "id": "b"}, 0)
    assert result["ok"]
    assert game.phase == "playing"


def test_round_ends_after_three_minutes_and_can_restart():
    game = make_game()
    game.tick(179.5)
    assert game.phase == "playing"
    game.tick(180)
    assert game.phase == "over"
    assert game.state()["tickets"] == []
    assert not runner(game, 181, action="get", item="bun", id="x")["ok"]
    assert runner(game, 182, action="start", id="y")["ok"]
    assert game.phase == "playing"
    assert game.score == 0


# --- Counter ---------------------------------------------------------------------

def test_get_fills_first_empty_slot():
    game = make_game()
    game.counter[0] = "bun"
    result = runner(game, action="get", item="tomato", id="r1")
    assert result == {"ok": True, "msg": "Got tomato", "id": "r1"}
    assert game.counter[:2] == ["bun", "tomato"]


def test_full_counter_blocks_get():
    game = make_game()
    fill_counter(game, ["bun"] * 6)
    result = runner(game, action="get", item="tomato", id="r1")
    assert not result["ok"]
    assert "full" in result["msg"].lower()


def test_unknown_pantry_item_rejected():
    game = make_game()
    assert not runner(game, action="get", item="caviar", id="r1")["ok"]


def test_trash_removes_item():
    game = make_game()
    game.counter[2] = "burnt"
    assert runner(game, action="trash", slot=2, id="r1")["ok"]
    assert game.counter[2] is None
    assert not runner(game, action="trash", slot=2, id="r2")["ok"]


def test_bad_slots_do_not_crash():
    game = make_game()
    for slot in (None, "2", -1, 6, 2.5, True):
        assert not runner(game, action="trash", slot=slot, id=f"bad{slot}")["ok"]


def test_counter_changed_guard():
    game = make_game()
    game.counter[0] = "bun"
    result = runner(game, action="trash", slot=0, item="tomato", id="r1")
    assert not result["ok"]
    assert game.counter[0] == "bun"


# --- Chop station ------------------------------------------------------------------

def test_chopping_lettuce_returns_it_to_counter():
    game = make_game()
    game.counter[3] = "lettuce"
    assert runner(game, action="send", slot=3, to="chop", id="r1")["ok"]
    assert game.counter[3] is None
    for i in range(5):
        game.handle_chop({"type": "chop"}, 1)
    assert game.state()["chop"]["progress"] == 5
    game.handle_chop({"type": "chop"}, 1)
    assert game.counter[0] == "chopped_lettuce"
    assert game.state()["chop"]["item"] is None


def test_chops_with_empty_station_are_ignored():
    game = make_game()
    chop_all(game)
    assert game.state()["chop"]["progress"] == 0


def test_wrong_item_at_chop_is_ruined():
    game = make_game()
    game.counter[0] = "bun"
    runner(game, action="send", slot=0, to="chop", id="r1")
    chop_all(game)
    assert game.counter[0] == "ruined"


def test_busy_station_rejects_send():
    game = make_game()
    fill_counter(game, ["lettuce", "tomato"])
    assert runner(game, action="send", slot=0, to="chop", id="r1")["ok"]
    result = runner(game, action="send", slot=1, to="chop", id="r2")
    assert not result["ok"]
    assert "busy" in result["msg"]
    assert game.counter[1] == "tomato"


def test_cannot_send_burnt_or_ruined():
    game = make_game()
    fill_counter(game, ["burnt", "ruined"])
    assert not runner(game, action="send", slot=0, to="cook", id="r1")["ok"]
    assert not runner(game, action="send", slot=1, to="chop", id="r2")["ok"]


def test_finished_chop_waits_for_a_free_slot():
    game = make_game()
    game.counter[0] = "tomato"
    runner(game, action="send", slot=0, to="chop", id="r1")
    fill_counter(game, ["bun"] * 6)
    chop_all(game)
    chop = game.state()["chop"]
    assert chop["waiting"] and chop["result"] == "chopped_tomato"
    runner(game, action="trash", slot=4, id="r2")
    assert game.counter[4] == "chopped_tomato"
    assert game.state()["chop"]["item"] is None


# --- Cook station ------------------------------------------------------------------

def send_patty_to_cook(game):
    game.counter[0] = "patty"
    assert runner(game, action="send", slot=0, to="cook", id="send-patty")["ok"]


def test_stirring_cooks_and_progress_stops_without_stirring():
    game = make_game()
    send_patty_to_cook(game)
    stir(game, 15, now=1)
    assert game.state()["cook"]["progress"] == 0.5
    game.tick(30)
    assert game.state()["cook"]["progress"] == 0.5
    assert game.state()["cook"]["status"] == "cooking"


def test_many_small_stirs_finish_cooking():
    # 6 x 5 ticks: float fractions would add up to 0.999... and never finish
    game = make_game()
    send_patty_to_cook(game)
    for _ in range(6):
        stir(game, 5)
    assert game.state()["cook"]["status"] == "done"


def test_pull_before_done_is_rejected():
    game = make_game()
    send_patty_to_cook(game)
    result = game.handle_cook({"type": "pull", "id": "k1"}, 1)
    assert not result["ok"]


def test_done_then_pull_gives_cooked_patty():
    game = make_game()
    send_patty_to_cook(game)
    stir(game, 30, now=1)
    cook = game.state()["cook"]
    assert cook["status"] == "done"
    assert cook["burn_in"] == 8
    result = game.handle_cook({"type": "pull", "id": "k1"}, 5)
    assert result["ok"]
    assert game.counter[0] == "cooked_patty"
    assert game.state()["cook"]["status"] == "empty"


def test_food_burns_after_eight_seconds():
    game = make_game()
    send_patty_to_cook(game)
    stir(game, 30, now=1)
    game.tick(8.9)
    assert game.state()["cook"]["burn_in"] == 1
    game.tick(9)
    cook = game.state()["cook"]
    assert cook["status"] == "burning"
    assert game.handle_cook({"type": "pull", "id": "k1"}, 10)["ok"]
    assert game.counter[0] == "burnt"


def test_pull_with_full_counter_waits_and_keeps_burning():
    game = make_game()
    send_patty_to_cook(game)
    stir(game, 30, now=1)
    fill_counter(game, ["bun"] * 6)
    assert not game.handle_cook({"type": "pull", "id": "k1"}, 2)["ok"]
    game.tick(20)
    assert game.state()["cook"]["status"] == "burning"


def test_silly_stir_messages_are_ignored_or_capped():
    game = make_game()
    send_patty_to_cook(game)
    stir(game, "lots")
    stir(game, None)
    assert game.state()["cook"]["progress"] == 0
    stir(game, -10)  # either direction counts
    assert game.state()["cook"]["progress"] == pytest.approx(10 / 30, abs=0.01)


# --- Orders and scoring ------------------------------------------------------------

def test_serve_reports_what_is_missing_and_removes_nothing():
    game = make_game()
    game.tickets[0]["recipe"] = "burger"
    fill_counter(game, ["bun", "chopped_lettuce"])
    result = runner(game, action="serve", ticket=game.tickets[0]["id"], id="r1")
    assert result["msg"] == "Missing cooked patty"
    assert game.counter[:2] == ["bun", "chopped_lettuce"]
    assert game.score == 0


def test_serve_scores_points_plus_tip_and_uses_items():
    game = make_game()
    game.tickets[0]["recipe"] = "burger"
    fill_counter(game, ["bun", "tomato", "cooked_patty", "chopped_lettuce"])
    ticket_id = game.tickets[0]["id"]
    assert game.state()["tickets"][0]["ready"]
    result = runner(game, now=30, action="serve", ticket=ticket_id, id="r1")
    assert result["ok"]
    # 20 points + half the max tip of 10 (served with 30 of 60 seconds left)
    assert game.score == 25
    assert game.counter == [None, "tomato", None, None, None, None]
    assert ticket_id not in [t["id"] for t in game.tickets]


def test_full_soup_path():
    game = make_game()
    game.tickets[0]["recipe"] = "soup"
    runner(game, action="get", item="tomato", id="r1")
    runner(game, action="send", slot=0, to="chop", id="r2")
    chop_all(game)
    assert game.counter[0] == "chopped_tomato"
    runner(game, action="send", slot=0, to="cook", id="r3", item="chopped_tomato")
    stir(game, 30)
    game.handle_cook({"type": "pull", "id": "k1"}, 1)
    assert game.counter[0] == "soup"
    assert runner(game, now=2, action="serve", ticket=1, id="r4")["ok"]
    assert game.stats["served"] == 1


def test_expired_ticket_costs_points():
    game = make_game(ticket_interval=1000)
    game.tick(59)
    assert len(game.tickets) == 1
    game.tick(60)
    assert game.tickets == []
    assert game.score == -10
    assert not runner(game, now=61, action="serve", ticket=1, id="r1")["ok"]


def test_ticket_cadence_and_cap():
    game = make_game(ticket_seconds=1000)
    for now in (20, 40, 60, 80, 100):
        game.tick(now)
    assert len(game.tickets) == 4
    assert [t["id"] for t in game.tickets] == [1, 2, 3, 4]


# --- Network robustness ---------------------------------------------------------------

def test_duplicate_message_ids_apply_once():
    game = make_game()
    first = runner(game, action="get", item="bun", id="dup")
    second = runner(game, action="get", item="bun", id="dup")
    assert first == second
    assert game.counter.count("bun") == 1

    send_patty_to_cook(game)
    stir(game, 30)
    game.counter[2:] = ["bun"] * 4
    # counter has room for exactly one pull; a repeated pull must not double up
    game.counter[5] = None
    assert game.handle_cook({"type": "pull", "id": "k9"}, 1)["ok"]
    assert game.handle_cook({"type": "pull", "id": "k9"}, 1)["ok"]
    assert game.counter.count("cooked_patty") == 1


def test_garbage_payloads_do_not_crash():
    game = make_game()
    assert not game.handle_runner(None, 0)["ok"]
    assert not game.handle_runner({"action": "dance", "id": "z"}, 0)["ok"]
    assert game.handle_chop("chop", 0) is None
    assert game.handle_cook(["stir"], 0) is None


def test_state_is_json():
    game = make_game()
    send_patty_to_cook(game)
    stir(game, 30)
    json.dumps(game.state())


def test_events_are_drained():
    game = make_game()
    kinds = [e["type"] for e in game.drain_events()]
    assert "round_start" in kinds and "new_ticket" in kinds
    assert game.drain_events() == []
