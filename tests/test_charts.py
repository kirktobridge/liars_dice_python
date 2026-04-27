import sys
import os
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from charts import compute_tournament_stats
from stats_schema import RoundRow, rounds_to_df


def _make_dfs():
    """Minimal synthetic DataFrames for 2 players, 3 games."""
    players = ['Captain Jack Sparrow', 'Captain Hector Barbossa']
    safe0 = players[0].replace(' ', '_')
    safe1 = players[1].replace(' ', '_')

    df = pd.DataFrame({
        'seed': [1, 2, 3],
        'winner': [players[0], players[1], players[0]],
        'rounds': [5, 8, 6],
        'num_players': [2, 2, 2],
        f'p_{safe0}_risk': [40, 40, 40],
        f'p_{safe0}_peer': [50, 50, 50],
        f'p_{safe0}_att': [60, 60, 60],
        f'p_{safe1}_risk': [70, 70, 70],
        f'p_{safe1}_peer': [30, 30, 30],
        f'p_{safe1}_att': [20, 20, 20],
    })

    df_rounds = rounds_to_df([
        RoundRow(seed=0, round_num=1, total_dice_on_table=10, bid_count=1,
                 action_type='bid', bid_count_claimed=3, effective_actual_count=None,
                 challenge_succeeded=None, round_loser=None,
                 action_caller=players[0], bidder_num_dice=5),
        RoundRow(seed=0, round_num=2, total_dice_on_table=10, bid_count=2,
                 action_type='challenge', bid_count_claimed=3, effective_actual_count=2,
                 challenge_succeeded=True, round_loser=players[1],
                 action_caller=players[0], bidder_num_dice=5),
        RoundRow(seed=0, round_num=3, total_dice_on_table=8, bid_count=3,
                 action_type='challenge', bid_count_claimed=4, effective_actual_count=5,
                 challenge_succeeded=False, round_loser=players[1],
                 action_caller=players[1], bidder_num_dice=4),
        RoundRow(seed=0, round_num=4, total_dice_on_table=8, bid_count=4,
                 action_type='spot_on', bid_count_claimed=2, effective_actual_count=2,
                 challenge_succeeded=True, round_loser=None,
                 action_caller=players[0], bidder_num_dice=4),
        RoundRow(seed=0, round_num=5, total_dice_on_table=6, bid_count=1,
                 action_type='bid', bid_count_claimed=2, effective_actual_count=None,
                 challenge_succeeded=None, round_loser=None,
                 action_caller=players[1], bidder_num_dice=3),
        RoundRow(seed=0, round_num=6, total_dice_on_table=6, bid_count=2,
                 action_type='challenge', bid_count_claimed=5, effective_actual_count=4,
                 challenge_succeeded=True, round_loser=players[0],
                 action_caller=players[1], bidder_num_dice=3),
    ])

    df_eliminations = pd.DataFrame({
        'player_name': [players[1], players[0], players[0], players[1], players[1], players[0]],
        'finishing_position': [1, 2, 1, 2, 1, 2],
    })

    return df, df_rounds, df_eliminations


class TestComputeTournamentStats:
    def setup_method(self):
        df, df_rounds, df_eliminations = _make_dfs()
        self.stats = compute_tournament_stats(df, df_rounds, df_eliminations)

    def test_top_level_keys_present(self):
        required = {
            'n_games', 'num_players', 'sorted_players', 'mean_rounds',
            'avg_bids_per_round', 'fastest_seed', 'fastest_rounds',
            'longest_seed', 'longest_rounds',
            'win_counts', 'win_pct',
            'hist_labels', 'hist_counts', 'hist_median', 'hist_below_mean_pct',
            'chall_called', 'chall_won', 'chall_win_pct',
            'spot_attempts', 'spot_wins', 'spot_win_pct',
            'violin_data',
            'scatter_success_claimed', 'scatter_success_actual',
            'scatter_fail_claimed', 'scatter_fail_actual', 'scatter_max_val',
            'escalation_bid_count', 'escalation_avg_claimed',
            'heat_x', 'heat_y', 'heat_z', 'heat_n', 'heat_text',
            'bucket_labels', 'bucket_success', 'bucket_fail',
            'pos_players', 'pos_positions', 'pos_matrix',
            'profile_players', 'profile_wins', 'profile_win_pct',
            'profile_risk', 'profile_peer', 'profile_att',
        }
        assert required <= set(self.stats.keys())

    def test_metadata_values(self):
        s = self.stats
        assert s['n_games'] == 3
        assert s['num_players'] == 2
        assert len(s['sorted_players']) == 2
        assert s['mean_rounds'] == pytest.approx(19 / 3, rel=1e-3)

    def test_win_counts_parallel_to_sorted_players(self):
        s = self.stats
        assert len(s['win_counts']) == len(s['sorted_players'])
        assert len(s['win_pct']) == len(s['sorted_players'])
        # Jack wins 2, Barbossa wins 1 — Jack should be first
        assert s['sorted_players'][0] == 'Captain Jack Sparrow'
        assert s['win_counts'][0] == 2

    def test_chall_stats_parallel_to_sorted_players(self):
        s = self.stats
        n = len(s['sorted_players'])
        assert len(s['chall_called']) == n
        assert len(s['chall_won']) == n
        assert len(s['chall_win_pct']) == n

    def test_spot_stats_parallel_to_sorted_players(self):
        s = self.stats
        n = len(s['sorted_players'])
        assert len(s['spot_attempts']) == n
        assert len(s['spot_wins']) == n
        assert len(s['spot_win_pct']) == n

    def test_escalation_lists_same_length(self):
        s = self.stats
        assert len(s['escalation_bid_count']) == len(s['escalation_avg_claimed'])

    def test_bucket_lists_same_length(self):
        s = self.stats
        assert len(s['bucket_labels']) == len(s['bucket_success']) == len(s['bucket_fail'])
        assert len(s['bucket_labels']) > 0

    def test_heat_shape_consistent(self):
        s = self.stats
        ny = len(s['heat_y'])
        nx = len(s['heat_x'])
        assert len(s['heat_z']) == ny
        assert all(len(row) == nx for row in s['heat_z'])
        assert len(s['heat_n']) == ny
        assert len(s['heat_text']) == ny

    def test_pos_matrix_shape(self):
        s = self.stats
        assert len(s['pos_players']) == len(s['sorted_players'])
        assert s['pos_positions'] == [1, 2]
        assert len(s['pos_matrix']) == len(s['pos_players'])
        assert all(len(row) == 2 for row in s['pos_matrix'])

    def test_profile_lists_parallel(self):
        s = self.stats
        n = s['num_players']
        assert len(s['profile_players']) == n
        assert len(s['profile_wins']) == n
        assert len(s['profile_win_pct']) == n
        assert len(s['profile_risk']) == n
        assert len(s['profile_peer']) == n
        assert len(s['profile_att']) == n

    def test_no_plotly_objects(self):
        """All values must be plain Python types, not Plotly objects."""
        import json
        # heat_z may contain None which is valid JSON
        json.dumps(self.stats)

    def test_violin_data_keys_match_sorted_players(self):
        s = self.stats
        assert set(s['violin_data'].keys()) == set(s['sorted_players'])

    def test_fastest_longest_seeds(self):
        s = self.stats
        assert s['fastest_rounds'] == 5
        assert s['fastest_seed'] == 1
        assert s['longest_rounds'] == 8
        assert s['longest_seed'] == 2
