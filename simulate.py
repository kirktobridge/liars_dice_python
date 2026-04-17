import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm
import pandas as pd
from LiarsDiceGame import LiarsDiceGame
from Player import Player
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
    with LiarsDiceGame(num_players, rng=rng) as game:  # no on_event renderer = silent
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
    with LiarsDiceGame(num_players, rng=game_rng) as game:
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
    }


def run_tournament(n: int, num_players: int = 4, workers: int | None = None) -> pd.DataFrame:
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
        return pd.DataFrame(results)

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

    return pd.DataFrame(results)

def show_tournament_stats(df: pd.DataFrame) -> None:
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

    # --- 4. Rounds per Winner (Box) ---
    box_plots = []
    for player in sorted_players:
        player_rounds = df.loc[df['winner'] == player, 'rounds']
        box_plots.append(go.Box(
            y=player_rounds,
            name=player,
            boxmean=True,
            showlegend=False,
        ))

    # --- 5. Win Streaks ---
    def longest_streak(series: pd.Series) -> int:
        max_streak = current = 0
        for val in series:
            current = current + 1 if val else 0
            max_streak = max(max_streak, current)
        return max_streak

    streaks = {p: longest_streak(df['winner'] == p) for p in sorted_players}
    streak_colors = [medal_colors.get(i, '#5B8DB8') for i in range(len(sorted_players))]
    streak_bar = go.Bar(
        x=sorted_players,
        y=[streaks[p] for p in sorted_players],
        marker_color=streak_colors,
        text=[str(streaks[p]) for p in sorted_players],
        textposition='outside',
        name='Streak',
        showlegend=False,
    )

    # --- 6. Personality Profile (winner risk_appetite × peer_pressure) ---
    personality_bars = []
    pp_labels = {0: 'No Peer Pressure', 1: 'Peer Pressure'}
    pp_colors = {0: '#5B8DB8', 1: '#E07B54'}
    risk_labels = ['0 — Conservative', '1 — Moderate', '2 — Aggressive']
    for pp_val in [0, 1]:
        win_counts_pp = [
            len(df[(df['winner_risk_appetite'] == ra) & (df['winner_peer_pressure'] == pp_val)])
            for ra in [0, 1, 2]
        ]
        personality_bars.append(go.Bar(
            x=risk_labels,
            y=win_counts_pp,
            name=pp_labels[pp_val],
            marker_color=pp_colors[pp_val],
            text=[str(c) for c in win_counts_pp],
            textposition='auto',
            showlegend=True,
        ))

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

    # --- Assemble subplots ---
    fig = make_subplots(
        rows=3, cols=3,
        subplot_titles=(
            'Win Rate',
            'Game Length Distribution',
            'Cumulative Win Rate Over Time',
            'Rounds per Winner',
            'Longest Win Streak',
            'Win Rate by Personality Type',
            'Player Profiles',
            '',
            '',
        ),
        specs=[
            [{'type': 'bar'},      {'type': 'histogram'}, {'type': 'scatter'}],
            [{'type': 'box'},      {'type': 'bar'},        {'type': 'bar'}],
            [{'type': 'table', 'colspan': 3}, None, None],
        ],
        column_widths=[0.28, 0.36, 0.36],
        row_heights=[0.35, 0.35, 0.30],
        vertical_spacing=0.14,
        horizontal_spacing=0.08,
    )

    # Row 1
    fig.add_trace(bar_chart, row=1, col=1)
    fig.add_trace(hist, row=1, col=2)
    for line in cum_lines:
        fig.add_trace(line, row=1, col=3)

    # Row 2
    for bp in box_plots:
        fig.add_trace(bp, row=2, col=1)
    fig.add_trace(streak_bar, row=2, col=2)
    for pb in personality_bars:
        fig.add_trace(pb, row=2, col=3)

    # Row 3
    fig.add_trace(profile_table, row=3, col=1)

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
        height=1300,
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

    # Axis labels
    fig.update_xaxes(title_text='Wins', row=1, col=1)
    fig.update_xaxes(title_text='Rounds', row=1, col=2)
    fig.update_xaxes(title_text='Game #', row=1, col=3)
    fig.update_yaxes(title_text='Win %', row=1, col=3)
    fig.update_yaxes(title_text='Rounds', row=2, col=1)
    fig.update_yaxes(title_text='Streak Length', row=2, col=2)
    fig.update_xaxes(title_text='Risk Appetite', row=2, col=3)
    fig.update_yaxes(title_text='Wins', row=2, col=3)

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
        df = run_tournament(args.num_games, num_players=args.num_players, workers=args.workers)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(df['winner'].value_counts())
    print(f"Avg rounds: {df['rounds'].mean():.1f}")
    print("\nWinner risk appetite distribution (0=conservative, 1=moderate, 2=aggressive):")
    print(df['winner_risk_appetite'].value_counts().sort_index())
    print("\nWinner peer pressure distribution (0=independent, 1=follows crowd):")
    print(df['winner_peer_pressure'].value_counts().sort_index())
    show_tournament_stats(df)
