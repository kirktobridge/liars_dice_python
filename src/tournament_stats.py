"""Pure aggregation of tournament DataFrames into JSON-safe dicts.

No Plotly dependency — safe to call from a web route. The returned dict
contains only Python-native types (int/float/str/list/dict/None), so it
can be passed straight to ``json.dumps`` without a ``default=`` shim.
"""
import math

import numpy as np
import pandas as pd
import constants as Constants

MAX_SCATTER = 4000


def _downsample_df(df_subset: pd.DataFrame, max_n: int) -> pd.DataFrame:
    if len(df_subset) <= max_n:
        return df_subset
    return df_subset.sample(n=max_n, random_state=42)


def compute_tournament_stats(
    df: pd.DataFrame,
    df_rounds: pd.DataFrame,
    df_eliminations: pd.DataFrame,
) -> dict:
    df = df.sort_values('seed').reset_index(drop=True)
    n_games = len(df)
    num_players_val = int(df['num_players'].iloc[0])

    # --- Win rate ---
    win_counts = df['winner'].value_counts()
    win_pct_series = (win_counts / n_games * 100).round(1)
    sorted_players = win_counts.index.tolist()

    # --- Game length ---
    mean_rounds = float(df['rounds'].mean())
    avg_bids_per_round = float(df_rounds['bid_count'].mean())
    fastest_row = df.loc[df['rounds'].idxmin()]
    longest_row = df.loc[df['rounds'].idxmax()]

    rounds_arr = df['rounds'].values
    r_min, r_max = int(rounds_arr.min()), int(rounds_arr.max())
    if r_min == r_max:
        hist_labels = [r_min]
        hist_counts = [len(rounds_arr)]
    else:
        bin_width = max(1, math.ceil((r_max - r_min) / 28))
        bins = range(r_min, r_max + bin_width + 1, bin_width)
        counts, edges = np.histogram(rounds_arr, bins=list(bins))
        hist_labels = [int(e) for e in edges[:-1]]
        hist_counts = [int(c) for c in counts.tolist()]
    hist_median = float(np.median(rounds_arr))
    hist_below_mean_pct = int((rounds_arr <= mean_rounds).mean() * 100)

    # --- Challenge stats ---
    chall = df_rounds[df_rounds['action_type'] == 'challenge']
    chall_called = chall.groupby('action_caller').size().rename('called')
    chall_won = chall[chall['challenge_succeeded']].groupby('action_caller').size().rename('won')
    chall_stats = pd.concat([chall_called, chall_won], axis=1).fillna(0).astype(int)
    chall_stats = chall_stats.reindex(sorted_players, fill_value=0)
    chall_stats['win_pct'] = (
        chall_stats['won'] / chall_stats['called'].replace(0, pd.NA) * 100
    ).fillna(0).round(1)

    # --- Spot-on stats ---
    spot = df_rounds[df_rounds['action_type'] == 'spot_on']
    spot_attempts = spot.groupby('action_caller').size().rename('attempts')
    spot_wins = spot[spot['challenge_succeeded']].groupby('action_caller').size().rename('wins')
    spot_stats = pd.concat([spot_attempts, spot_wins], axis=1).fillna(0).astype(int)
    spot_stats = spot_stats.reindex(sorted_players, fill_value=0)
    spot_stats['win_pct'] = (
        spot_stats['wins'] / spot_stats['attempts'].replace(0, pd.NA) * 100
    ).fillna(0).round(1)

    # --- Position finish percentages ---
    pos_counts = (df_eliminations
        .groupby(['player_name', 'finishing_position'])
        .size()
        .unstack(fill_value=0))
    pos_pct = (pos_counts.div(pos_counts.sum(axis=1), axis=0) * 100).round(1)
    pos_pct = pos_pct.reindex(sorted_players, fill_value=0.0)
    pos_pct = pos_pct.reindex(columns=range(1, num_players_val + 1), fill_value=0.0)

    # --- Escalation curve ---
    escalation = (df_rounds[df_rounds['action_type'].isin(['challenge', 'spot_on'])]
        .groupby('bid_count')['bid_count_claimed']
        .mean()
        .reset_index())

    # --- Bid-ratio / heatmap analysis ---
    chall_br = df_rounds[df_rounds['action_type'] == 'challenge'].copy()
    chall_br = chall_br.dropna(subset=['bidder_num_dice', 'bid_count_claimed', 'challenge_succeeded'])
    chall_br['bidder_num_dice'] = chall_br['bidder_num_dice'].astype(int)

    heat_agg = (chall_br.groupby(['bidder_num_dice', 'bid_count_claimed'])['challenge_succeeded']
                .agg(['mean', 'count']).reset_index())
    heat_pivot = heat_agg.pivot(index='bidder_num_dice', columns='bid_count_claimed', values='mean')
    heat_count = heat_agg.pivot(
        index='bidder_num_dice', columns='bid_count_claimed', values='count'
    ).fillna(0).astype(int)
    heat_text = heat_pivot.map(lambda v: f'{v:.0%}' if pd.notna(v) else '')

    ratio_bins = [0, 1, 2, 3, float('inf')]
    ratio_labels = ['≤1×', '1–2×', '2–3×', '>3×']
    chall_br['bid_ratio'] = chall_br['bid_count_claimed'] / chall_br['bidder_num_dice']
    chall_br['ratio_bucket'] = pd.cut(chall_br['bid_ratio'], bins=ratio_bins, labels=ratio_labels)
    bucket_stats = (chall_br.groupby('ratio_bucket', observed=True)['challenge_succeeded']
                    .agg(['mean', 'count']).reset_index())
    bucket_stats['fail_rate'] = 1 - bucket_stats['mean']

    # --- Violin data (dice count at challenge per player) ---
    violin_data: dict[str, list] = {}
    for player in sorted_players:
        y_vals = chall[chall['action_caller'] == player]['total_dice_on_table'].dropna()
        violin_data[player] = [float(v) for v in y_vals.tolist()]

    # --- Bid scatter data ---
    chall_sc = chall.dropna(subset=['bid_count_claimed', 'effective_actual_count'])
    sc_succ = chall_sc[chall_sc['challenge_succeeded']]
    sc_fail = chall_sc[chall_sc['challenge_succeeded'] == False]
    sc_succ_ds = _downsample_df(sc_succ, MAX_SCATTER)
    sc_fail_ds = _downsample_df(sc_fail, MAX_SCATTER)
    scatter_max_val = float(max(
        chall_sc['bid_count_claimed'].max() if len(chall_sc) else 1,
        chall_sc['effective_actual_count'].max() if len(chall_sc) else 1,
    ))

    # --- Player profiles ---
    _safe_to_name = {name.replace(' ', '_'): name for name in Constants.PLAYER_NAMES}
    all_players = [
        _safe_to_name[col[2:-5]]
        for col in df.columns
        if col.startswith('p_') and col.endswith('_risk') and col[2:-5] in _safe_to_name
    ]
    profile_wins: list[int] = []
    profile_win_pct: list[str] = []
    profile_risk: list[int] = []
    profile_peer: list[int] = []
    profile_att: list[int] = []
    profile_cun: list[int] = []
    for player in all_players:
        safe = player.replace(' ', '_')
        wins = int((df['winner'] == player).sum())
        profile_wins.append(wins)
        profile_win_pct.append(f"{wins / n_games * 100:.1f}%")
        profile_risk.append(int(df[f'p_{safe}_risk'].iloc[0]))
        profile_peer.append(int(df[f'p_{safe}_peer'].iloc[0]))
        profile_att.append(int(df[f'p_{safe}_att'].iloc[0]))
        profile_cun.append(int(df[f'p_{safe}_cun'].iloc[0]) if f'p_{safe}_cun' in df.columns else 50)

    return {
        # Metadata
        "n_games": int(n_games),
        "num_players": num_players_val,
        "sorted_players": sorted_players,
        "mean_rounds": mean_rounds,
        "avg_bids_per_round": avg_bids_per_round,
        "fastest_seed": int(fastest_row['seed']),
        "fastest_rounds": int(fastest_row['rounds']),
        "longest_seed": int(longest_row['seed']),
        "longest_rounds": int(longest_row['rounds']),
        # Win rate (parallel to sorted_players)
        "win_counts": [int(v) for v in win_counts.tolist()],
        "win_pct": [float(v) for v in win_pct_series[sorted_players].tolist()],
        # Game length histogram
        "hist_labels": hist_labels,
        "hist_counts": hist_counts,
        "hist_median": hist_median,
        "hist_below_mean_pct": hist_below_mean_pct,
        # Challenge stats (parallel to sorted_players)
        "chall_called": [int(v) for v in chall_stats['called'].tolist()],
        "chall_won": [int(v) for v in chall_stats['won'].tolist()],
        "chall_win_pct": [float(v) for v in chall_stats['win_pct'].tolist()],
        # Spot-on stats (parallel to sorted_players)
        "spot_attempts": [int(v) for v in spot_stats['attempts'].tolist()],
        "spot_wins": [int(v) for v in spot_stats['wins'].tolist()],
        "spot_win_pct": [float(v) for v in spot_stats['win_pct'].tolist()],
        # Violin data
        "violin_data": violin_data,
        # Bid scatter (pre-downsampled to ≤MAX_SCATTER points each)
        "scatter_success_claimed": [float(v) for v in sc_succ_ds['bid_count_claimed'].tolist()],
        "scatter_success_actual": [float(v) for v in sc_succ_ds['effective_actual_count'].tolist()],
        "scatter_fail_claimed": [float(v) for v in sc_fail_ds['bid_count_claimed'].tolist()],
        "scatter_fail_actual": [float(v) for v in sc_fail_ds['effective_actual_count'].tolist()],
        "scatter_max_val": scatter_max_val,
        # Escalation curve
        "escalation_bid_count": [int(v) for v in escalation['bid_count'].tolist()],
        "escalation_avg_claimed": [float(v) for v in escalation['bid_count_claimed'].tolist()],
        # Challenge heatmap
        "heat_x": [int(v) for v in heat_pivot.columns.tolist()],
        "heat_y": [int(v) for v in heat_pivot.index.tolist()],
        "heat_z": [[None if pd.isna(v) else float(v) for v in row]
                   for row in heat_pivot.values],
        "heat_n": [[int(v) for v in row]
                   for row in heat_count.reindex(
                       index=heat_pivot.index, columns=heat_pivot.columns
                   ).values.tolist()],
        "heat_text": [[str(v) for v in row] for row in heat_text.values.tolist()],
        # Bid ratio buckets
        "bucket_labels": bucket_stats['ratio_bucket'].astype(str).tolist(),
        "bucket_success": [float(v) for v in bucket_stats['mean'].tolist()],
        "bucket_fail": [float(v) for v in bucket_stats['fail_rate'].tolist()],
        # Position finish percentages
        "pos_players": sorted_players,
        "pos_positions": list(range(1, num_players_val + 1)),
        "pos_matrix": [[float(v) for v in row] for row in pos_pct.values.tolist()],
        # Player profiles
        "profile_players": all_players,
        "profile_wins": profile_wins,
        "profile_win_pct": profile_win_pct,
        "profile_risk": profile_risk,
        "profile_peer": profile_peer,
        "profile_att": profile_att,
        "profile_cun": profile_cun,
        "profile_win_pct_float": [round(w / n_games * 100, 1) for w in profile_wins],
    }
