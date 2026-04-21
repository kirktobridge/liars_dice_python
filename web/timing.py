# Seconds to pause before forwarding each event type to the browser.
# Zero means "send immediately". Tune these to shape the pacing and suspense.
#
# Events NOT listed here default to 0.0.
# human_turn_start / input_request intentionally omitted (0 delay — don't keep the human waiting).
EVENT_DELAYS: dict[str, float] = {
    'round_started':      1.2,   # brief breath between rounds
    'dice_rolling':       0.5,
    'dice_rolled':        1.0,   # let the roll land before anything happens
    'turn_started':       0.8,   # opponent "thinking" pause
    'bid_made':           1.6,   # time to read and feel the bid
    'raise_made':         1.6,
    'challenge_called':   1.8,   # tension before the reveal
    'rolls_revealed':     1.2,
    'challenge_resolved': 2.2,   # outcome lands slowly
    'spot_on_called':     1.8,
    'spot_on_resolved':   2.2,
    'player_eliminated':  2.0,
    'round_summary':      0.8,
    'game_won':           0.5,
}
