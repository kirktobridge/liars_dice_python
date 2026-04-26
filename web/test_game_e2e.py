"""
E2E tests covering lobby, bidding, game-over overlay, and tournament flows.

Unit tests (mock injection) — no live server required.
Integration tests (live server) — require server at http://localhost:8765.
"""
import re
import time
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8765"

# ── shared mock data ──────────────────────────────────────────────────────────

_SNAP = {
    "round_num": 1,
    "prev_bid": None,
    "prev_bidder": None,
    "current_player": "Bot",
    "game_over": False,
    "winner": None,
    "active_players": [
        {"name": "Tester", "player_type": "HUMAN", "num_dice": 5, "is_eliminated": False},
        {"name": "Bot",    "player_type": "CPU",   "num_dice": 5, "is_eliminated": False},
    ],
}

_SNAP_WITH_BID = {**_SNAP, "prev_bid": {"count": 2, "face": 3}, "prev_bidder": "Bot"}


def _inject_game_view(page: Page):
    """Switch to game view.

    ws is declared with `let` at module scope in game.js so it is NOT on
    window — setting window.ws has no effect on the real variable.  Instead
    we patch window.sendAction (top-level function declarations ARE writable
    window properties) so click handlers reach disableActions() without
    needing a real WebSocket connection.
    """
    page.evaluate("""() => {
        document.getElementById('game-view').style.display = 'flex';
        document.getElementById('lobby-view').style.display = 'none';
        window.sendAction = function(action, bid) { disableActions(); };
    }""")


def _send(page: Page, event_type, extra_fields=None, snapshot=None):
    """Convenience wrapper for handleMessage calls."""
    evt = {"type": event_type, **(extra_fields or {})}
    page.evaluate("(msg) => handleMessage(msg)", {
        "event": evt,
        "snapshot": snapshot or _SNAP,
    })


# ── LOBBY ─────────────────────────────────────────────────────────────────────

def test_lobby_empty_name_shows_error(page: Page):
    page.goto(BASE_URL)
    page.click("#start-btn")
    expect(page.locator("#lobby-error")).to_be_visible()
    expect(page.locator("#player-name")).to_have_class(re.compile(r"input-error"))


def test_lobby_error_clears_on_typing(page: Page):
    page.goto(BASE_URL)
    page.click("#start-btn")
    expect(page.locator("#lobby-error")).to_be_visible()
    page.locator("#player-name").press_sequentially("C")
    expect(page.locator("#lobby-error")).to_be_hidden()


def test_coin_dial_increments(page: Page):
    page.goto(BASE_URL)
    expect(page.locator("#coin-number")).to_have_text("2")  # default: 3 total, 2 opponents
    page.click("#coin-next")
    expect(page.locator("#coin-number")).to_have_text("3")


def test_coin_dial_decrements(page: Page):
    page.goto(BASE_URL)
    page.click("#coin-next")
    page.click("#coin-prev")
    expect(page.locator("#coin-number")).to_have_text("2")


def test_coin_dial_prev_disabled_at_minimum(page: Page):
    page.goto(BASE_URL)
    page.click("#coin-prev")  # 3 total → 2 total (1 opponent) = minimum
    expect(page.locator("#coin-prev")).to_be_disabled()
    expect(page.locator("#coin-label")).to_have_text("OPPONENT")


def test_set_sail_transitions_to_game_view(page: Page):
    """Clicking SET SAIL with a valid name shows game view. Requires live server."""
    page.goto(BASE_URL)
    page.fill("#player-name", "Tester")
    page.click("#start-btn")
    expect(page.locator("#game-view")).to_be_visible(timeout=5_000)
    expect(page.locator("#lobby-view")).to_be_hidden()


# ── BIDDING ACTION PANEL ──────────────────────────────────────────────────────

def test_challenge_and_spot_on_disabled_on_opening_bid(page: Page):
    page.goto(BASE_URL)
    _inject_game_view(page)
    page.evaluate("(msg) => handleMessage(msg)", {
        "event": {
            "type": "input_request",
            "request": {"type": "opening_bid", "dice": [3, 4, 5, 6, 1]},
            "advisor": None,
        },
        "snapshot": _SNAP,
    })
    expect(page.locator("#btn-challenge")).to_be_disabled()
    expect(page.locator("#btn-spot-on")).to_be_disabled()
    expect(page.locator("#btn-confirm-bid")).to_be_enabled()


def test_challenge_and_spot_on_enabled_on_decision(page: Page):
    page.goto(BASE_URL)
    _inject_game_view(page)
    page.evaluate("(msg) => handleMessage(msg)", {
        "event": {
            "type": "input_request",
            "request": {
                "type": "decision",
                "dice": [3, 4, 5],
                "prev_bid": {"count": 2, "face": 3},
            },
            "advisor": None,
        },
        "snapshot": _SNAP_WITH_BID,
    })
    expect(page.locator("#btn-challenge")).to_be_enabled()
    expect(page.locator("#btn-spot-on")).to_be_enabled()


def test_bid_count_slider_updates_display(page: Page):
    page.goto(BASE_URL)
    _inject_game_view(page)
    page.evaluate("(msg) => handleMessage(msg)", {
        "event": {
            "type": "input_request",
            "request": {"type": "opening_bid", "dice": [2, 2, 4, 5, 6]},
            "advisor": None,
        },
        "snapshot": _SNAP,
    })
    page.locator("#bid-count").evaluate(
        "el => { el.value = 7; el.dispatchEvent(new Event('input')); }"
    )
    expect(page.locator("#bid-count-display")).to_have_text("7")


def test_face_selector_highlights_selected(page: Page):
    page.goto(BASE_URL)
    _inject_game_view(page)
    page.evaluate("(msg) => handleMessage(msg)", {
        "event": {
            "type": "input_request",
            "request": {"type": "opening_bid", "dice": [1, 2, 3, 4, 5]},
            "advisor": None,
        },
        "snapshot": _SNAP,
    })
    page.locator(".face-btn[data-face='5']").click()
    expect(page.locator(".face-btn[data-face='5']")).to_have_class(re.compile(r"face-btn-selected"))
    expect(page.locator(".face-btn[data-face='1']")).not_to_have_class(re.compile(r"face-btn-selected"))


def test_confirm_bid_disables_panel(page: Page):
    """After submitting a bid, sendAction calls disableActions — panel becomes disabled."""
    page.goto(BASE_URL)
    _inject_game_view(page)
    page.evaluate("(msg) => handleMessage(msg)", {
        "event": {
            "type": "input_request",
            "request": {"type": "opening_bid", "dice": [3, 3, 3, 4, 5]},
            "advisor": None,
        },
        "snapshot": _SNAP,
    })
    page.click("#btn-confirm-bid")
    expect(page.locator("#btn-confirm-bid")).to_be_disabled()
    expect(page.locator("#waiting-indicator")).to_be_visible()


# ── GAME OVER OVERLAY ─────────────────────────────────────────────────────────

def test_game_over_overlay_shows_winner(page: Page):
    page.goto(BASE_URL)
    _inject_game_view(page)
    page.evaluate("(msg) => handleMessage(msg)", {
        "event": {"type": "game_won", "winner_name": "Bluebeard"},
        "snapshot": {**_SNAP, "game_over": True, "winner": "Bluebeard"},
    })
    expect(page.locator("#gameover-overlay")).to_be_visible()
    expect(page.locator("#gameover-overlay")).to_contain_text("VICTORY")
    expect(page.locator("#winner-name")).to_have_text("Bluebeard")


def test_weigh_anchor_returns_to_lobby(page: Page):
    page.goto(BASE_URL)
    _inject_game_view(page)
    page.evaluate("(msg) => handleMessage(msg)", {
        "event": {"type": "game_won", "winner_name": "Redcoat"},
        "snapshot": {**_SNAP, "game_over": True, "winner": "Redcoat"},
    })
    expect(page.locator("#gameover-overlay")).to_be_visible()
    page.click("#play-again-btn")
    expect(page.locator("#lobby-view")).to_be_visible()
    expect(page.locator("#game-view")).to_be_hidden()
    expect(page.locator("#gameover-overlay")).to_be_hidden()


# ── RAISE ACTION ─────────────────────────────────────────────────────────────

def test_raise_adds_feed_entry(page: Page):
    """raise_made event is handled and adds a feed entry (raise_made was an untested event type)."""
    page.goto(BASE_URL)
    _inject_game_view(page)
    # First enable decision mode (RAISE is valid after an existing bid)
    page.evaluate("(msg) => handleMessage(msg)", {
        "event": {
            "type": "input_request",
            "request": {
                "type": "decision",
                "dice": [3, 4, 5],
                "prev_bid": {"count": 2, "face": 3},
            },
            "advisor": None,
        },
        "snapshot": _SNAP_WITH_BID,
    })
    # Inject a raise_made event (simulates server confirming the raise)
    _send(page, "raise_made", {"player_name": "Bot", "count": 3, "face": 4})
    feed = page.locator("#event-feed")
    expect(feed).to_contain_text("raises to")


# ── TOURNAMENT API (live server) ──────────────────────────────────────────────

def test_tournament_player_names_returns_list():
    import requests
    r = requests.get(f"{BASE_URL}/tournament/player-names", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "names" in data
    assert isinstance(data["names"], list)
    assert len(data["names"]) > 0


def test_tournament_status_returns_state():
    import requests
    r = requests.post(
        f"{BASE_URL}/tournament/run",
        json={"n": 3, "num_players": 2},
        timeout=5,
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    r2 = requests.get(f"{BASE_URL}/tournament/status/{job_id}", timeout=5)
    assert r2.status_code == 200
    data = r2.json()
    assert "status" in data
    assert data["status"] in ("running", "complete")
    assert "progress" in data


def test_tournament_results_returns_data():
    import requests
    import time
    r = requests.post(
        f"{BASE_URL}/tournament/run",
        json={"n": 3, "num_players": 2},
        timeout=5,
    )
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    deadline = time.time() + 30
    while time.time() < deadline:
        r2 = requests.get(f"{BASE_URL}/tournament/status/{job_id}", timeout=5)
        if r2.json()["status"] == "complete":
            break
        time.sleep(0.5)
    r3 = requests.get(f"{BASE_URL}/tournament/results/{job_id}", timeout=5)
    assert r3.status_code == 200
    assert isinstance(r3.json(), dict)


# ── WEBSOCKET BAD HANDSHAKE (live server) ─────────────────────────────────────

def test_websocket_bad_handshake_closes():
    """Server closes with code 1008 when the first message is not a join."""
    from websockets.sync.client import connect
    import websockets.exceptions

    with connect("ws://localhost:8765/ws/test-bad-handshake-session") as ws:
        ws.send('{"type": "not_join"}')
        try:
            ws.recv(timeout=5.0)
        except websockets.exceptions.ConnectionClosed as exc:
            code = exc.rcvd.code if exc.rcvd is not None else None
            assert code == 1008, f"Expected close code 1008, got {code}"
        else:
            pytest.fail("Expected WebSocket connection to be closed with code 1008")


# ── FULL WEBSOCKET TURN CYCLE (live server) ───────────────────────────────────

def test_opening_bid_submitted_advances_game(page: Page):
    """
    Start a real 2-player game over WebSocket, wait for first human turn,
    submit the opening bid, and verify the action panel is disabled afterwards.
    """
    page.goto(BASE_URL)
    page.fill("#player-name", "Tester")
    page.click("#start-btn")
    expect(page.locator("#game-view")).to_be_visible(timeout=5_000)

    # Wait until the action panel is enabled (human turn arrived)
    page.wait_for_function(
        "() => !document.getElementById('action-panel').classList.contains('disabled')",
        timeout=30_000,
    )

    page.click("#btn-confirm-bid")

    # disableActions() is synchronous — panel re-disables immediately
    expect(page.locator("#btn-confirm-bid")).to_be_disabled(timeout=3_000)
    expect(page.locator("#waiting-indicator")).to_be_visible()


# ── TOURNAMENT STANDARD FLOW (live server) ────────────────────────────────────

def test_tournament_standard_run_shows_results(page: Page):
    """
    Submit a small standard tournament (5 games, 2 players),
    wait for the results dashboard to appear, and verify a chart is rendered.
    """
    page.goto(f"{BASE_URL}/tournament")

    page.fill("#n-games", "5")
    page.select_option("#num-players", "2")
    page.locator("#run-form button[type='submit']").click()

    expect(page.locator("#progress-section")).to_be_visible(timeout=5_000)
    expect(page.locator("#results-section")).to_be_visible(timeout=30_000)
    expect(page.locator("#chart-win-rate")).to_be_visible()
    # Summary chips should be populated
    expect(page.locator("#summary-stats")).to_contain_text("Games Simulated")
