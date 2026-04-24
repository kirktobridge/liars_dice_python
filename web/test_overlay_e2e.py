"""
Playwright E2E tests for the cups-lifted overlay pause/unpause flow.

Tests:
  Unit (mock injection) — verify overlay DOM content without a real game.
  Integration (live server) — start a real 2-player game, wait for a challenge,
    confirm overlay pauses execution, dismiss it, and verify the game resumes.
"""
import re
import time
import pytest
from playwright.sync_api import sync_playwright, Page, expect

BASE_URL = "http://localhost:8765"

# ── mock payloads ─────────────────────────────────────────────────────────────

MOCK_ROLLS_REVEALED = {
    "event": {
        "type": "rolls_revealed",
        "bid_face": 3,
        "bid_count": 2,
        "bidder_name": "Alice",
        "player_rolls": [
            {"name": "Alice", "dice": [3, 1, 5]},
            {"name": "Bob",   "dice": [3, 2]},
        ],
    },
    "snapshot": None,
}

MOCK_CHALLENGE_RESOLVED_WIN = {
    "event": {
        "type": "challenge_resolved",
        "succeeded": True,
        "challenger_name": "Bob",
        "bidder_name": "Alice",
        "bid_count": 2,
        "bid_face": 3,
        "actual_count": 2,
        "ones_count": 1,
        "loser_name": "Alice",
    },
    "snapshot": None,
}

MOCK_CHALLENGE_RESOLVED_FAIL = {
    "event": {
        "type": "challenge_resolved",
        "succeeded": False,
        "challenger_name": "Bob",
        "bidder_name": "Alice",
        "bid_count": 2,
        "bid_face": 3,
        "actual_count": 1,
        "ones_count": 0,
        "loser_name": "Bob",
    },
    "snapshot": None,
}


def inject_setup(page: Page):
    """Show game view and install a patched ws that records sends."""
    page.evaluate("""() => {
        document.getElementById('game-view').style.display = 'flex';
        document.getElementById('lobby-view').style.display = 'none';
    }""")


# ── unit tests (mock injection) ───────────────────────────────────────────────

def test_overlay_shows_bid(page: Page):
    page.goto(BASE_URL)
    inject_setup(page)

    page.evaluate("(msg) => handleMessage(msg)", MOCK_ROLLS_REVEALED)

    overlay = page.locator("#rolls-reveal-overlay")
    expect(overlay).to_be_visible()
    expect(overlay).to_contain_text("CUPS LIFTED")
    expect(overlay).to_contain_text("bid by:")
    expect(overlay).to_contain_text("Alice")


def test_overlay_shows_correct_call_outcome(page: Page):
    page.goto(BASE_URL)
    inject_setup(page)

    page.evaluate("(msg) => handleMessage(msg)", MOCK_ROLLS_REVEALED)
    page.evaluate("(msg) => handleMessage(msg)", MOCK_CHALLENGE_RESOLVED_WIN)

    overlay = page.locator("#rolls-reveal-overlay")
    expect(overlay).to_contain_text("ACTUAL:")
    expect(overlay).to_contain_text("+ 1 ×")          # ones shown
    expect(overlay).to_contain_text("= 3")             # 2 bid-face + 1 one = 3
    expect(overlay).to_contain_text("CORRECT CALL")
    expect(overlay.get_by_text("Lower Cups")).to_be_visible()


def test_overlay_shows_failure_outcome(page: Page):
    page.goto(BASE_URL)
    inject_setup(page)

    page.evaluate("(msg) => handleMessage(msg)", MOCK_ROLLS_REVEALED)
    page.evaluate("(msg) => handleMessage(msg)", MOCK_CHALLENGE_RESOLVED_FAIL)

    overlay = page.locator("#rolls-reveal-overlay")
    expect(overlay).to_contain_text("FAILURE")
    expect(overlay).not_to_contain_text("CORRECT CALL")


def test_ones_not_shown_when_bid_face_is_one(page: Page):
    page.goto(BASE_URL)
    inject_setup(page)

    reveal = {**MOCK_ROLLS_REVEALED,
              "event": {**MOCK_ROLLS_REVEALED["event"], "bid_face": 1}}
    resolved = {**MOCK_CHALLENGE_RESOLVED_WIN,
                "event": {**MOCK_CHALLENGE_RESOLVED_WIN["event"],
                          "bid_face": 1, "ones_count": 2}}
    page.evaluate("(msg) => handleMessage(msg)", reveal)
    page.evaluate("(msg) => handleMessage(msg)", resolved)

    overlay = page.locator("#rolls-reveal-overlay")
    # "+ 2 ×" must NOT appear when face is 1 (ones are the bid, not wilds)
    expect(overlay).not_to_contain_text("+ 2 ×")


def test_close_button_hides_overlay(page: Page):
    page.goto(BASE_URL)
    inject_setup(page)

    page.evaluate("(msg) => handleMessage(msg)", MOCK_ROLLS_REVEALED)
    page.evaluate("(msg) => handleMessage(msg)", MOCK_CHALLENGE_RESOLVED_WIN)

    overlay = page.locator("#rolls-reveal-overlay")
    expect(overlay).to_be_visible()

    page.get_by_text("Lower Cups").click()

    expect(overlay).not_to_be_visible()


def test_overlay_auto_dismiss_when_human_eliminated(page: Page):
    page.goto(BASE_URL)
    inject_setup(page)

    # Simulate human already eliminated so the flag is set
    page.evaluate("() => { humanEliminated = true; }")

    page.evaluate("(msg) => handleMessage(msg)", MOCK_ROLLS_REVEALED)
    page.evaluate("(msg) => handleMessage(msg)", MOCK_CHALLENGE_RESOLVED_WIN)

    overlay = page.locator("#rolls-reveal-overlay")
    expect(overlay).to_be_visible()
    # No "Lower Cups" button — auto-dismiss path
    expect(overlay).not_to_contain_text("Lower Cups")
    # Overlay auto-closes within 6 seconds (5 s timer + headroom)
    expect(overlay).not_to_be_visible(timeout=6_000)


# ── integration test (live server + real WebSocket) ───────────────────────────

def test_live_game_resumes_after_overlay_dismissed(page: Page):
    """
    Full round-trip test:
      1. Start a real 2-player game.
      2. Play rounds until a challenge/spot-on produces the overlay.
      3. Verify the game is paused (no new feed entries arrive on their own).
      4. Click 'Lower Cups'.
      5. Verify the game resumes (new feed entries appear within 10 s).
    """
    # Capture WebSocket sent frames so we can verify the ack is dispatched.
    sent_ws_frames: list[str] = []

    def on_ws(ws):
        # frame is a str (the raw payload) in playwright sync API
        ws.on("framesent", lambda frame: sent_ws_frames.append(
            frame if isinstance(frame, str) else getattr(frame, "payload", str(frame))
        ))

    page.on("websocket", on_ws)

    page.goto(BASE_URL)

    # Start a 2-player game (1 opponent = least variance, fastest challenges)
    page.fill("#player-name", "Tester")
    page.evaluate("""() => {
        const sel = document.getElementById('num-players');
        // populate if empty, then set to 2 total players
        if (!sel.options.length) {
            const opt = document.createElement('option');
            opt.value = '2'; opt.text = '1 opponent';
            sel.appendChild(opt);
        }
        sel.value = '2';
    }""")
    page.click("#start-btn")
    page.wait_for_selector("#game-view", state="visible", timeout=5_000)

    overlay  = page.locator("#rolls-reveal-overlay")
    feed_el  = page.locator("#event-feed")

    def feed_text():
        try:
            return feed_el.inner_text(timeout=500)
        except Exception:
            return ""

    # Play the game: on each human turn challenge if possible, else confirm bid.
    # Challenging every time provokes the cups-lifted overlay quickly.
    deadline = time.time() + 90
    overlay_appeared = False

    while time.time() < deadline:
        # ── overlay visible? handle it before touching game controls ──────────
        if overlay.is_visible():
            close_btn = overlay.get_by_text("Lower Cups")
            try:
                close_btn.wait_for(state="visible", timeout=5_000)
            except Exception:
                time.sleep(0.2)
                continue

            text_before = feed_text()

            # Pause must be real: wait 1 s, confirm feed hasn't changed
            time.sleep(1.0)
            assert feed_text() == text_before, \
                "Feed changed while overlay was up — game was NOT paused"

            close_btn.click()
            overlay_appeared = True

            expect(overlay).not_to_be_visible()

            # Ack must have been sent over the real WebSocket
            page.wait_for_timeout(300)
            ack_sent = any('"rolls_revealed_ack"' in f for f in sent_ws_frames)
            assert ack_sent, \
                f"rolls_revealed_ack not found in WS frames: {sent_ws_frames[-5:]}"

            # Game must produce new feed content within 10 s (proves server resumed)
            page.wait_for_function(
                "(before) => document.getElementById('event-feed')"
                ".innerText.trim() !== before.trim()",
                arg=text_before,
                timeout=10_000,
            )
            break

        # ── service human turn — only when overlay is NOT visible ─────────────
        try:
            challenge_btn = page.locator("#btn-challenge")
            if challenge_btn.is_enabled():
                challenge_btn.click()
                time.sleep(0.15)
                continue
        except Exception:
            pass

        try:
            confirm_btn = page.locator("#btn-confirm-bid")
            if confirm_btn.is_enabled():
                confirm_btn.click()
                time.sleep(0.15)
                continue
        except Exception:
            pass

        time.sleep(0.25)

    assert overlay_appeared, "Cups-lifted overlay never appeared within 90 s"
    ws_closed = page.evaluate("() => typeof ws === 'undefined' || !ws || ws.readyState === 3")
    assert not ws_closed, "WebSocket closed after overlay dismissed — game did not resume"
