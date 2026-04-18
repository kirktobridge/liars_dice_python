import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm
import pandas as pd
from LiarsDiceGame import LiarsDiceGame
from Player import Player
from stats_collector import GameStatsCollector
import Constants

# Personality snapshot type: name -> (risk_appetite, peer_pressure_score)
_Personalities = dict[str, tuple[int, int]]


def run_game(seed: int, num_players: int, players: dict[str, Player] | None = None) -> dict:
    rng = random.Random(seed)
    names = Constants.PLAYER_NAMES[:num_players]
    if players is None:
        players = {name: Player(name, rng=rng) for name in names}
    else:
        for p in players.values():
            p.reset()
            p._rng = rng  # rebind so dice rolls use this game's RNG
    collector = GameStatsCollector(seed, num_players)
    with LiarsDiceGame(num_players, rng=rng, on_event=collector.on_event) as game:
        for name in names:
            game.add_player(players[name])
        while game.process_round():
            pass
        winner_name = game.players[0].name
    winner = players[winner_name]
    player_data = {}
    for name in names:
        p = players[name]
        safe = name.replace(' ', '_')
        player_data[f'p_{safe}_risk'] = p.risk_appetite
        player_data[f'p_{safe}_peer'] = p.peer_pressure_score
    return {
        'seed': seed,
        'winner': winner_name,
        'rounds': game.round_num,
        'num_players': num_players,
        'winner_risk_appetite': winner.risk_appetite,
        'winner_peer_pressure': winner.peer_pressure_score,
        **player_data,
        '_round_rows': collector.round_rows,
        '_elim_rows': collector.elimination_rows,
    }


def _run_game_worker(args: tuple[int, int, _Personalities]) -> dict:
    """Top-level worker for ProcessPoolExecutor (must be picklable)."""
    seed, num_players, personalities = args
    game_rng = random.Random(seed)
    dummy_rng = random.Random()  # throwaway — only used to satisfy Player.__init__
    names = Constants.PLAYER_NAMES[:num_players]
    players = {}
    for name in names:
        p = Player(name, rng=dummy_rng)
        p.risk_appetite, p.peer_pressure_score = personalities[name]
        p._rng = game_rng  # bind game RNG so dice rolls are deterministic per seed
        players[name] = p
    collector = GameStatsCollector(seed, num_players)
    with LiarsDiceGame(num_players, rng=game_rng, on_event=collector.on_event) as game:
        for name in names:
            game.add_player(players[name])
        while game.process_round():
            pass
        winner_name = game.players[0].name
    winner = players[winner_name]
    player_data = {}
    for name in names:
        p = players[name]
        safe = name.replace(' ', '_')
        player_data[f'p_{safe}_risk'] = p.risk_appetite
        player_data[f'p_{safe}_peer'] = p.peer_pressure_score
    return {
        'seed': seed,
        'winner': winner_name,
        'rounds': game.round_num,
        'num_players': num_players,
        'winner_risk_appetite': winner.risk_appetite,
        'winner_peer_pressure': winner.peer_pressure_score,
        **player_data,
        '_round_rows': collector.round_rows,
        '_elim_rows': collector.elimination_rows,
    }


def run_tournament(
    n: int, num_players: int = 4, workers: int | None = None
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run n games and return (df_games, df_rounds, df_eliminations)."""
    if not (2 <= num_players <= Constants.MAX_PLAYERS):
        raise ValueError(f"num_players must be between 2 and {Constants.MAX_PLAYERS}, got {num_players}")
    # Create players once so personalities are consistent across all games
    personality_rng = random.Random(0)
    names = Constants.PLAYER_NAMES[:num_players]
    persistent_players = {name: Player(name, rng=personality_rng) for name in names}

    num_workers = workers if workers is not None else os.cpu_count() or 1
    # Throttle tqdm updates for large simulations to avoid render overhead
    update_interval = max(1, n // 1000)  # ~1000 updates regardless of n

    if num_workers == 1:
        # Serial path — reuses player objects (original behaviour)
        results = []
        with tqdm(
            range(n),
            desc="Simulating games",
            unit="game",
            miniters=update_interval,
            dynamic_ncols=True,
            colour="green",
        ) as pbar:
            for i in pbar:
                result = run_game(seed=i, num_players=num_players, players=persistent_players)
                results.append(result)
                pbar.set_postfix(last_winner=result['winner'], rounds=result['rounds'])
    else:
        # Parallel path — snapshot personalities so workers can reconstruct players safely
        personalities: _Personalities = {
            name: (persistent_players[name].risk_appetite, persistent_players[name].peer_pressure_score)
            for name in names
        }
        chunk = max(1, n // (num_workers * 4))
        args_iter = ((i, num_players, personalities) for i in range(n))

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            results = list(tqdm(
                executor.map(_run_game_worker, args_iter, chunksize=chunk),
                total=n,
                desc=f"Simulating games ({num_workers} workers)",
                unit="game",
                miniters=update_interval,
                dynamic_ncols=True,
                colour="green",
            ))

    round_rows = [row for r in results for row in r.pop('_round_rows', [])]
    elim_rows  = [row for r in results for row in r.pop('_elim_rows', [])]
    return pd.DataFrame(results), pd.DataFrame(round_rows), pd.DataFrame(elim_rows)

def show_tournament_stats(
    df: pd.DataFrame,
    df_rounds: pd.DataFrame,
    df_eliminations: pd.DataFrame,
    derived_stats=None,
) -> None:
    """Render a end stats dashboard and save html + png."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    df = df.sort_values('seed').reset_index(drop=True)
    n_games = len(df)
    medal_colors = {0: '#FFD700', 1: '#C0C0C0', 2: '#CD7F32'}

    # --- 1. Win Rate Bar Chart ---
    win_counts = df['winner'].value_counts()
    win_pct = (win_counts / n_games * 100).round(1)
    sorted_players = win_counts.index.tolist()
    bar_colors = [medal_colors.get(i, '#5B8DB8') for i in range(len(sorted_players))]

    bar_chart = go.Bar(
        x=win_counts.values,
        y=sorted_players,
        orientation='h',
        marker_color=bar_colors,
        text=[f'{c} wins ({p}%)' for c, p in zip(win_counts.values, win_pct[sorted_players])],
        textposition='auto',
        name='Wins',
    )

    # --- 2. Game Length Histogram ---
    mean_rounds = df['rounds'].mean()
    fastest_row = df.loc[df['rounds'].idxmin()]
    longest_row = df.loc[df['rounds'].idxmax()]

    hist = go.Histogram(
        x=df['rounds'],
        nbinsx=30,
        marker_color='#5B8DB8',
        name='Game Length',
        showlegend=False,
    )

    # --- 3. Cumulative Win Rate Over Time ---
    cum_lines = []
    for player in sorted_players:
        wins_series = (df['winner'] == player).astype(int)
        cum_pct = (wins_series.expanding().mean() * 100).round(2)
        cum_lines.append(go.Scatter(
            x=list(range(n_games)),
            y=cum_pct,
            mode='lines',
            name=player,
            line=dict(width=2),
            showlegend=True,
        ))

    # --- Derived stats (used by panels 4, 5, 6, 8) ---
    chall = df_rounds[df_rounds['action_type'] == 'challenge']
    chall_called = chall.groupby('action_caller').size().rename('called')
    chall_won = chall[chall['challenge_succeeded']].groupby('action_caller').size().rename('won')
    chall_stats = pd.concat([chall_called, chall_won], axis=1).fillna(0).astype(int)
    chall_stats = chall_stats.reindex(sorted_players, fill_value=0)
    chall_stats['win_pct'] = (chall_stats['won'] / chall_stats['called'].replace(0, pd.NA) * 100).fillna(0).round(1)

    spot = df_rounds[df_rounds['action_type'] == 'spot_on']
    spot_attempts = spot.groupby('action_caller').size().rename('attempts')
    spot_wins = spot[spot['challenge_succeeded']].groupby('action_caller').size().rename('wins')
    spot_stats = pd.concat([spot_attempts, spot_wins], axis=1).fillna(0).astype(int)
    spot_stats = spot_stats.reindex(sorted_players, fill_value=0)

    num_players_val = int(df['num_players'].iloc[0])
    pos_counts = (df_eliminations
        .groupby(['player_name', 'finishing_position'])
        .size()
        .unstack(fill_value=0))
    pos_pct = (pos_counts.div(pos_counts.sum(axis=1), axis=0) * 100).round(1)
    pos_pct = pos_pct.reindex(sorted_players, fill_value=0.0)
    pos_pct = pos_pct.reindex(columns=range(1, num_players_val + 1), fill_value=0.0)

    escalation = (df_rounds[df_rounds['action_type'].isin(['challenge', 'spot_on'])]
        .groupby('bid_count')['bid_count_claimed']
        .mean()
        .reset_index())

    # --- Bid-ratio analysis (panels 9 & 10) ---
    chall_br = df_rounds[df_rounds['action_type'] == 'challenge'].copy()
    chall_br = chall_br.dropna(subset=['bidder_num_dice', 'bid_count_claimed', 'challenge_succeeded'])
    chall_br['bidder_num_dice'] = chall_br['bidder_num_dice'].astype(int)

    heat_agg = (chall_br.groupby(['bidder_num_dice', 'bid_count_claimed'])['challenge_succeeded']
                .agg(['mean', 'count']).reset_index())
    heat_pivot = heat_agg.pivot(index='bidder_num_dice', columns='bid_count_claimed', values='mean')
    heat_text = heat_pivot.map(lambda v: f'{v:.0%}' if pd.notna(v) else '')

    ratio_bins   = [0, 1, 2, 3, float('inf')]
    ratio_labels = ['≤1×', '1–2×', '2–3×', '>3×']
    chall_br['bid_ratio'] = chall_br['bid_count_claimed'] / chall_br['bidder_num_dice']
    chall_br['ratio_bucket'] = pd.cut(chall_br['bid_ratio'], bins=ratio_bins, labels=ratio_labels)
    bucket_stats = (chall_br.groupby('ratio_bucket', observed=True)['challenge_succeeded']
                    .agg(['mean', 'count']).reset_index())
    bucket_stats['fail_rate'] = 1 - bucket_stats['mean']

    # --- 4. Dice Count at Challenge (Violin) ---
    violin_traces = []
    for player in sorted_players:
        y_vals = chall[chall['action_caller'] == player]['total_dice_on_table'].dropna()
        violin_traces.append(go.Violin(
            y=y_vals,
            name=player,
            box_visible=True,
            meanline_visible=True,
            showlegend=False,
        ))

    # --- 5. Challenge Accuracy by Player (horizontal bar) ---
    chall_acc_bar = go.Bar(
        x=[float(chall_stats.loc[p, 'win_pct']) if p in chall_stats.index else 0.0
           for p in sorted_players],
        y=sorted_players,
        orientation='h',
        marker_color=[medal_colors.get(i, '#5B8DB8') for i in range(len(sorted_players))],
        text=[
            f"{int(chall_stats.loc[p, 'won'])}/{int(chall_stats.loc[p, 'called'])} challenges"
            if p in chall_stats.index else '0/0 challenges'
            for p in sorted_players
        ],
        textposition='auto',
        showlegend=False,
    )

    # --- 6. Bid vs. Actual Count at Challenge (scatter) ---
    chall_sc = chall.dropna(subset=['bid_count_claimed', 'effective_actual_count'])
    max_val = max(
        chall_sc['bid_count_claimed'].max() if len(chall_sc) else 1,
        chall_sc['effective_actual_count'].max() if len(chall_sc) else 1,
    )
    sc_succ = chall_sc[chall_sc['challenge_succeeded'] == True]
    sc_fail = chall_sc[chall_sc['challenge_succeeded'] != True]
    bid_scatter = [
        go.Scatter(
            x=sc_succ['bid_count_claimed'],
            y=sc_succ['effective_actual_count'],
            mode='markers',
            marker=dict(color='#00CC00', opacity=0.4, size=5),
            name='Correct call',
            showlegend=True,
        ),
        go.Scatter(
            x=sc_fail['bid_count_claimed'],
            y=sc_fail['effective_actual_count'],
            mode='markers',
            marker=dict(color='#FF4444', opacity=0.4, size=5),
            name='Failed call',
            showlegend=True,
        ),
        go.Scatter(
            x=[0, max_val],
            y=[0, max_val],
            mode='lines',
            line=dict(color='white', dash='dash', width=1),
            showlegend=False,
        ),
    ]

    # --- 7. Player Profiles Table ---
    risk_labels = {0: 'Conservative', 1: 'Moderate', 2: 'Aggressive'}
    peer_labels = {0: 'Independent', 1: 'Follows Crowd'}
    all_players = Constants.PLAYER_NAMES[:df['num_players'].iloc[0]]
    profile_header = ['Player', 'Wins', 'Win %', 'Risk Appetite', 'Peer Pressure']
    profile_cols = {col: [] for col in profile_header}
    for player in all_players:
        safe = player.replace(' ', '_')
        risk_col = f'p_{safe}_risk'
        peer_col = f'p_{safe}_peer'
        wins = int((df['winner'] == player).sum())
        risk_val = int(df[risk_col].iloc[0])
        peer_val = int(df[peer_col].iloc[0])
        profile_cols['Player'].append(player)
        profile_cols['Wins'].append(str(wins))
        profile_cols['Win %'].append(f"{wins / n_games * 100:.1f}%")
        profile_cols['Risk Appetite'].append(risk_labels[risk_val])
        profile_cols['Peer Pressure'].append(peer_labels[peer_val])

    row_colors = ['#1e1e24' if i % 2 == 0 else '#26262e' for i in range(len(all_players))]
    profile_table = go.Table(
        header=dict(
            values=profile_header,
            fill_color='#2a2a2e',
            font=dict(color='#FFD700', size=13),
            align='center',
            line_color='#444',
            height=32,
        ),
        cells=dict(
            values=[profile_cols[col] for col in profile_header],
            fill_color=[row_colors] * len(profile_header),
            font=dict(color='#e8e8e8', size=12),
            align=['left'] + ['center'] * (len(profile_header) - 1),
            line_color='#444',
            height=28,
        ),
    )

    # --- 9. Challenge Success Heatmap (bidder dice × bid amount) ---
    heatmap_trace = go.Heatmap(
        x=heat_pivot.columns.tolist(),
        y=heat_pivot.index.tolist(),
        z=heat_pivot.values,
        text=heat_text.values,
        texttemplate='%{text}',
        colorscale='RdYlGn',
        zmin=0, zmax=1,
        colorbar=dict(title='Challenge<br>Success<br>Rate', len=0.2, y=0.08),
        showscale=True,
    )

    # --- 10. Challenge Accuracy by Bid Ratio (manually stacked bars) ---
    ratio_x = bucket_stats['ratio_bucket'].astype(str).tolist()
    ratio_success = bucket_stats['mean'].tolist()
    ratio_fail = bucket_stats['fail_rate'].tolist()
    ratio_bar_correct = go.Bar(
        x=ratio_x, y=ratio_success,
        base=0,
        name='Correct call',
        marker_color='#00CC00',
        showlegend=False,
        text=[f'{v:.0%}' for v in ratio_success],
        textposition='inside',
    )
    ratio_bar_wrong = go.Bar(
        x=ratio_x, y=ratio_fail,
        base=ratio_success,
        name='Wrong call',
        marker_color='#FF4444',
        showlegend=False,
        text=[f'{v:.0%}' for v in ratio_fail],
        textposition='inside',
    )

    # --- 8. Bid Escalation Curve ---
    avg_bids_per_round = df_rounds['bid_count'].mean()
    escalation_line = go.Scatter(
        x=escalation['bid_count'],
        y=escalation['bid_count_claimed'],
        mode='lines+markers',
        line=dict(color='#FFD700', width=2),
        marker=dict(size=6),
        showlegend=False,
    )

    # --- Assemble subplots ---
    fig = make_subplots(
        rows=5, cols=3,
        subplot_titles=(
            'Win Rate',
            'Game Length Distribution',
            'Cumulative Win Rate Over Time',
            'Dice Count at Challenge',
            'Challenge Accuracy by Player',
            'Bid vs. Actual Count at Challenge',
            'Player Profiles',
            '', '',
            'Bid Escalation Curve',
            '', '',
            'Challenge Success Rate: Bidder Dice × Bid Amount',
            '',
            'Challenge Accuracy by Bid Ratio',
        ),
        specs=[
            [{'type': 'bar'},    {'type': 'histogram'}, {'type': 'scatter'}],
            [{'type': 'violin'}, {'type': 'bar'},        {'type': 'scatter'}],
            [{'type': 'table', 'colspan': 3}, None, None],
            [{'type': 'scatter', 'colspan': 3}, None, None],
            [{'type': 'heatmap', 'colspan': 2}, None, {'type': 'bar'}],
        ],
        column_widths=[0.28, 0.36, 0.36],
        row_heights=[0.27, 0.27, 0.22, 0.24, 0.30],
        vertical_spacing=0.08,
        horizontal_spacing=0.08,
    )

    # Row 1
    fig.add_trace(bar_chart, row=1, col=1)
    fig.add_trace(hist, row=1, col=2)
    for line in cum_lines:
        fig.add_trace(line, row=1, col=3)

    # Row 2
    for vt in violin_traces:
        fig.add_trace(vt, row=2, col=1)
    fig.add_trace(chall_acc_bar, row=2, col=2)
    for st in bid_scatter:
        fig.add_trace(st, row=2, col=3)

    # Row 3
    fig.add_trace(profile_table, row=3, col=1)

    # Row 4
    fig.add_trace(escalation_line, row=4, col=1)

    # Row 5
    fig.add_trace(heatmap_trace, row=5, col=1)
    fig.add_trace(ratio_bar_correct, row=5, col=3)
    fig.add_trace(ratio_bar_wrong, row=5, col=3)

    # Mean line annotation on histogram
    # (add_vline can't be used here because go.Table in row 3 has no xaxis)
    hist_xref = 'x2'
    fig.add_shape(
        type='line',
        x0=mean_rounds, x1=mean_rounds,
        y0=0, y1=1,
        xref=hist_xref,
        yref='y2 domain',
        line=dict(color='#FFD700', width=2, dash='dash'),
    )
    fig.add_annotation(
        x=mean_rounds, y=1,
        xref=hist_xref, yref='y2 domain',
        text=f'mean {mean_rounds:.1f}',
        showarrow=False,
        font=dict(color='#FFD700', size=10),
        xanchor='left', yanchor='top',
    )

    # Annotate fastest / longest game
    hist_yref = 'y2'
    fig.add_annotation(
        x=fastest_row['rounds'], y=0,
        text=f"Fastest<br>seed {fastest_row['seed']}",
        showarrow=True, arrowhead=2,
        arrowcolor='#90EE90', font=dict(color='#90EE90', size=10),
        xref=hist_xref, yref=hist_yref,
        ax=0, ay=-40,
    )
    fig.add_annotation(
        x=longest_row['rounds'], y=0,
        text=f"Longest<br>seed {longest_row['seed']}",
        showarrow=True, arrowhead=2,
        arrowcolor='#FF7F7F', font=dict(color='#FF7F7F', size=10),
        xref=hist_xref, yref=hist_yref,
        ax=0, ay=-40,
    )

    fig.update_layout(
        template='plotly_dark',
        title=dict(
            text='🎲 LIAR\'S DICE — TOURNAMENT RESULTS',
            font=dict(size=26, color='#FFD700'),
            x=0.5,
            xanchor='center',
        ),
        height=2100,
        width=1600,
        legend=dict(
            title='Player',
            x=1.01, y=0.85,
            bgcolor='rgba(0,0,0,0.4)',
            bordercolor='#444',
            borderwidth=1,
        ),
        margin=dict(l=60, r=160, t=100, b=60),
    )

    # Axis labels — Row 1
    fig.update_xaxes(title_text='Wins', row=1, col=1)
    fig.update_xaxes(title_text='Rounds', row=1, col=2)
    fig.update_xaxes(title_text='Game #', row=1, col=3)
    fig.update_yaxes(title_text='Win %', row=1, col=3)
    # Row 2
    fig.update_yaxes(title_text='Total Dice on Table', row=2, col=1)
    fig.update_xaxes(title_text='Challenge Win %', row=2, col=2)
    fig.update_xaxes(title_text='Bid Count Claimed', row=2, col=3)
    fig.update_yaxes(title_text='Actual Count', row=2, col=3)
    # Row 4
    fig.update_xaxes(title_text='Bids in Round', row=4, col=1)
    fig.update_yaxes(title_text='Avg Claimed Count', row=4, col=1)
    # Row 5
    fig.update_xaxes(title_text='Bid Count Claimed', row=5, col=1)
    fig.update_yaxes(title_text='Bidder Dice Count', row=5, col=1)
    fig.update_xaxes(title_text='Bid / Bidder Dice', row=5, col=3)
    fig.update_yaxes(title_text='Rate', row=5, col=3, tickformat='.0%')

    fig.add_annotation(
        x=0.5, y=1.04,
        xref='x7 domain', yref='y7 domain',
        text=f'avg {avg_bids_per_round:.1f} bids/round',
        showarrow=False,
        font=dict(color='#aaaaaa', size=11),
        xanchor='center',
    )

    fig.write_html('tournament_stats.html')
    print('Saved tournament_stats.html')
    try:
        fig.write_image('tournament_stats.png', scale=2)
        print('Saved tournament_stats.png')
    except Exception:
        print('Skipped tournament_stats.png (Chrome not found — run `plotly_get_chrome` to enable)')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run a Liar\'s Dice tournament simulation.')
    parser.add_argument(
        '-n', '--num-games',
        type=int,
        default=1000,
        help='Number of games to simulate (default: 1000)'
    )
    parser.add_argument(
        '-p', '--num-players',
        type=int,
        default=4,
        help=f'Number of players per game, 2–{Constants.MAX_PLAYERS} (default: 4)'
    )
    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=None,
        help='Parallel worker processes (default: cpu_count; use 1 for serial)'
    )
    args = parser.parse_args()

    try:
        df, df_rounds, df_eliminations = run_tournament(args.num_games, num_players=args.num_players, workers=args.workers)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(df['winner'].value_counts())
    print(f"Avg rounds: {df['rounds'].mean():.1f}")
    print("\nWinner risk appetite distribution (0=conservative, 1=moderate, 2=aggressive):")
    print(df['winner_risk_appetite'].value_counts().sort_index())
    print("\nWinner peer pressure distribution (0=independent, 1=follows crowd):")
    print(df['winner_peer_pressure'].value_counts().sort_index())
    show_tournament_stats(df, df_rounds, df_eliminations)
