MAX_NUM_DICE = 5
MAX_PLAYERS = 3
MAX_ROUNDS = 3
ACTIONS = ['ELIM', 'BID', 'RAISE', 'CHLG', 'SPOT']
PROB_THRESHOLDS = {
    'LOW': 0.25,
    'MED': 0.5,
    'HIGH': 0.75,
    'VERY HIGH': 0.95,
    'CERTAIN': 1.0
}
SELF_RISK_THRESHOLDS = ['LOW', 'MED', 'HIGH']
PAUSE = 0.5
PlayerNames = []
DEBUG = True


# but must limit bid's count to max number of dice available
# if (prev_bid_cnt + 1) <= (tot_other_dice + self.num_dice):
