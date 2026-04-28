"""Plotly rendering of tournament stats. Pure aggregation lives in tournament_stats."""
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from tournament_stats import compute_tournament_stats


def show_tournament_stats(
    df: pd.DataFrame,
    df_rounds: pd.DataFrame,
    df_eliminations: pd.DataFrame,
    derived_stats=None,
) -> None:
    """Render an end-of-tournament stats dashboard and save html + png."""
    s = compute_tournament_stats(df, df_rounds, df_eliminations)

    sorted_players = s['sorted_players']
    medal_colors = {0: '#FFD700', 1: '#C0C0C0', 2: '#CD7F32'}

    # --- 1. Win Rate Bar Chart ---
    bar_colors = [medal_colors.get(i, '#5B8DB8') for i in range(len(sorted_players))]
    bar_chart = go.Bar(
        x=s['win_counts'],
        y=sorted_players,
        orientation='h',
        marker_color=bar_colors,
        text=[f'{c} wins ({p}%)' for c, p in zip(s['win_counts'], s['win_pct'])],
        textposition='auto',
        name='Wins',
    )

    # --- 2. Game Length Histogram ---
    hist = go.Bar(
        x=s['hist_labels'],
        y=s['hist_counts'],
        marker_color='#5B8DB8',
        name='Game Length',
        showlegend=False,
    )

    # --- 3. Spot On Accuracy by Player ---
    spot_acc_bar = go.Bar(
        x=s['spot_win_pct'],
        y=sorted_players,
        orientation='h',
        marker_color=[medal_colors.get(i, '#5B8DB8') for i in range(len(sorted_players))],
        text=[
            f"{s['spot_wins'][i]}/{s['spot_attempts'][i]} spot-ons"
            for i in range(len(sorted_players))
        ],
        textposition='auto',
        showlegend=False,
    )

    # --- 4. Dice Count at Challenge (Violin) ---
    violin_traces = [
        go.Violin(
            y=s['violin_data'][player],
            name=player,
            box_visible=True,
            meanline_visible=True,
            showlegend=False,
        )
        for player in sorted_players
    ]

    # --- 5. Challenge Accuracy by Player ---
    chall_acc_bar = go.Bar(
        x=s['chall_win_pct'],
        y=sorted_players,
        orientation='h',
        marker_color=[medal_colors.get(i, '#5B8DB8') for i in range(len(sorted_players))],
        text=[
            f"{s['chall_won'][i]}/{s['chall_called'][i]} challenges"
            for i in range(len(sorted_players))
        ],
        textposition='auto',
        showlegend=False,
    )

    # --- 6. Bid vs. Actual Count at Challenge (scatter) ---
    max_val = s['scatter_max_val']
    bid_scatter = [
        go.Scatter(
            x=s['scatter_success_claimed'],
            y=s['scatter_success_actual'],
            mode='markers',
            marker=dict(color='#00CC00', opacity=0.4, size=5),
            name='Correct call',
            showlegend=True,
        ),
        go.Scatter(
            x=s['scatter_fail_claimed'],
            y=s['scatter_fail_actual'],
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
    def _risk_label(v: int) -> str:
        if v <= 33:
            return f'{v} (Conservative)'
        elif v <= 66:
            return f'{v} (Moderate)'
        else:
            return f'{v} (Aggressive)'
    def _att_label(v: int) -> str:
        if v <= 33:
            return f'{v} (Oblivious)'
        elif v <= 66:
            return f'{v} (Observant)'
        else:
            return f'{v} (Eagle-eyed)'

    def _cun_label(v: int) -> str:
        if v <= 33:
            return f'{v} (Blinkered)'
        elif v <= 66:
            return f'{v} (Tactical)'
        else:
            return f'{v} (Masterful)'
    profile_header = ['Player', 'Wins', 'Win %', 'Risk Appetite', 'Peer Pressure', 'Attentiveness', 'Positional Cunning']
    profile_values = [
        s['profile_players'],
        [str(w) for w in s['profile_wins']],
        s['profile_win_pct'],
        [_risk_label(v) for v in s['profile_risk']],
        [str(v) for v in s['profile_peer']],
        [_att_label(v) for v in s['profile_att']],
        [_cun_label(v) for v in s['profile_cun']],
    ]
    row_colors = ['#1e1e24' if i % 2 == 0 else '#26262e' for i in range(s['num_players'])]
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
            values=profile_values,
            fill_color=[row_colors] * len(profile_header),
            font=dict(color='#e8e8e8', size=12),
            align=['left'] + ['center'] * (len(profile_header) - 1),
            line_color='#444',
            height=28,
        ),
    )

    # --- 8. Bid Escalation Curve ---
    escalation_line = go.Scatter(
        x=s['escalation_bid_count'],
        y=s['escalation_avg_claimed'],
        mode='lines+markers',
        line=dict(color='#FFD700', width=2),
        marker=dict(size=6),
        showlegend=False,
    )

    # --- 9. Challenge Success Heatmap ---
    heatmap_trace = go.Heatmap(
        x=s['heat_x'],
        y=s['heat_y'],
        z=s['heat_z'],
        text=s['heat_text'],
        texttemplate='%{text}',
        customdata=s['heat_n'],
        hovertemplate='Bid: %{x}<br>Bidder dice: %{y}<br>Success: %{text}<br>n=%{customdata}<extra></extra>',
        colorscale='RdYlGn',
        zmin=0, zmax=1,
        colorbar=dict(title='Challenge<br>Success<br>Rate', len=0.2, y=0.08),
        showscale=True,
    )

    # --- 10. Challenge Accuracy by Bid Ratio ---
    ratio_bar_correct = go.Bar(
        x=s['bucket_labels'], y=s['bucket_success'],
        base=0,
        name='Correct call',
        marker_color='#00CC00',
        showlegend=False,
        text=[f'{v:.0%}' for v in s['bucket_success']],
        textposition='inside',
    )
    ratio_bar_wrong = go.Bar(
        x=s['bucket_labels'], y=s['bucket_fail'],
        base=s['bucket_success'],
        name='Wrong call',
        marker_color='#FF4444',
        showlegend=False,
        text=[f'{v:.0%}' for v in s['bucket_fail']],
        textposition='inside',
    )

    # --- Assemble subplots ---
    fig = make_subplots(
        rows=5, cols=3,
        subplot_titles=(
            'Win Rate',
            'Game Length Distribution',
            'Spot On Accuracy by Player',
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
            [{'type': 'bar'},    {'type': 'bar'}, {'type': 'bar'}],
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
    fig.add_trace(spot_acc_bar, row=1, col=3)

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
    hist_xref = 'x2'
    fig.add_shape(
        type='line',
        x0=s['mean_rounds'], x1=s['mean_rounds'],
        y0=0, y1=1,
        xref=hist_xref,
        yref='y2 domain',
        line=dict(color='#FFD700', width=2, dash='dash'),
    )
    fig.add_annotation(
        x=s['mean_rounds'], y=1,
        xref=hist_xref, yref='y2 domain',
        text=f"mean {s['mean_rounds']:.1f}",
        showarrow=False,
        font=dict(color='#FFD700', size=10),
        xanchor='left', yanchor='top',
    )

    # Annotate fastest / longest game
    hist_yref = 'y2'
    fig.add_annotation(
        x=s['fastest_rounds'], y=0,
        text=f"Fastest<br>seed {s['fastest_seed']}",
        showarrow=True, arrowhead=2,
        arrowcolor='#90EE90', font=dict(color='#90EE90', size=10),
        xref=hist_xref, yref=hist_yref,
        ax=0, ay=-40,
    )
    fig.add_annotation(
        x=s['longest_rounds'], y=0,
        text=f"Longest<br>seed {s['longest_seed']}",
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
    fig.update_xaxes(title_text='Spot On Win %', row=1, col=3)
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
        text=f"avg {s['avg_bids_per_round']:.1f} bids/round",
        showarrow=False,
        font=dict(color='#aaaaaa', size=11),
        xanchor='center',
    )

    try:
        fig.write_html('tournament_stats.html')
        print('Saved tournament_stats.html')
    except Exception:
        print('Skipped tournament_stats.html (write failed)')
    try:
        fig.write_image('tournament_stats.png', scale=2)
        print('Saved tournament_stats.png')
    except Exception:
        print('Skipped tournament_stats.png (Chrome not found — run `plotly_get_chrome` to enable)')
