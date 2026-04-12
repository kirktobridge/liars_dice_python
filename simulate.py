import random
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from LiarsDiceGame import LiarsDiceGame
from Player import Player
import Constants


def run_game(seed: int, num_players: int, bot_configs: list[dict] | None = None) -> dict:
    rng = random.Random(seed)
    game = LiarsDiceGame(num_players, rng=rng)  # no on_event renderer = silent
    names = Constants.PLAYER_NAMES[:num_players]
    for name in names:
        game.add_player(Player(name, rng=rng))
    while game.process_round():
        pass
    return {
        'seed': seed,
        'winner': game.players[0].name,
        'rounds': game.round_num,
        'num_players': num_players,
    }


def run_tournament(n: int, num_players: int = 4) -> pd.DataFrame:
    results = [run_game(seed=i, num_players=num_players) for i in range(n)]
    return pd.DataFrame(results)


def show_tournament_stats(df: pd.DataFrame) -> None:
    """Render a Civ 5 end-screen style stats dashboard and save html + png."""
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

    # --- Assemble subplots ---
    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=(
            'Win Rate',
            'Game Length Distribution',
            'Cumulative Win Rate Over Time',
            'Rounds per Winner',
            'Longest Win Streak',
            '',
        ),
        specs=[
            [{'type': 'bar'},      {'type': 'histogram'}, {'type': 'scatter'}],
            [{'type': 'box'},      {'type': 'bar'},        {'type': 'scatter'}],
        ],
        column_widths=[0.28, 0.36, 0.36],
        row_heights=[0.5, 0.5],
        vertical_spacing=0.18,
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

    # Mean line annotation on histogram (using paper coords for y)
    fig.add_vline(
        x=mean_rounds,
        line=dict(color='#FFD700', width=2, dash='dash'),
        annotation_text=f'mean {mean_rounds:.1f}',
        annotation_position='top right',
        annotation_font_color='#FFD700',
        row=1, col=2,
    )

    # Annotate fastest / longest game
    hist_xref = 'x2'
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
        height=900,
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

    fig.write_html('tournament_stats.html')
    fig.write_image('tournament_stats.png', scale=2)
    print('Saved tournament_stats.html and tournament_stats.png')


if __name__ == '__main__':
    df = run_tournament(1000, num_players=4)
    print(df['winner'].value_counts())
    print(f"Avg rounds: {df['rounds'].mean():.1f}")
    show_tournament_stats(df)
