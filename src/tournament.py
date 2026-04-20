import logging
import os
import random
import sys

logging.getLogger('liars_dice').addHandler(logging.NullHandler())
logger = logging.getLogger(__name__)
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm
import pandas as pd
from LiarsDiceGame import LiarsDiceGame
from Player import Player
from stats_collector import GameStatsCollector
import constants as Constants

# Personality snapshot type: name -> (risk_appetite, peer_pressure_score, attentiveness_score)
_Personalities = dict[str, tuple[int, int, int]]


def _build_result(
    seed: int,
    num_players: int,
    names: list[str],
    players: dict[str, Player],
    winner_name: str,
    game: LiarsDiceGame,
    collector: GameStatsCollector,
) -> dict:
    winner = players[winner_name]
    player_data = {}
    for name in names:
        p = players[name]
        safe = name.replace(' ', '_')
        player_data[f'p_{safe}_risk'] = p.risk_appetite
        player_data[f'p_{safe}_peer'] = p.peer_pressure_score
        player_data[f'p_{safe}_att'] = p.attentiveness_score
    return {
        'seed': seed,
        'winner': winner_name,
        'rounds': game.round_num,
        'num_players': num_players,
        'winner_risk_appetite': winner.risk_appetite,
        'winner_peer_pressure': winner.peer_pressure_score,
        'winner_attentiveness': winner.attentiveness_score,
        **player_data,
        '_round_rows': collector.round_rows,
        '_elim_rows': collector.elimination_rows,
    }


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
    return _build_result(seed, num_players, names, players, winner_name, game, collector)


def _run_game_worker(args: tuple[int, int, _Personalities]) -> dict:
    """Top-level worker for ProcessPoolExecutor (must be picklable)."""
    seed, num_players, personalities = args
    try:
        return _run_game_worker_inner(seed, num_players, personalities)
    except Exception:
        logger.warning('Worker failed for seed=%d, num_players=%d', seed, num_players, exc_info=True)
        raise


def _run_game_worker_inner(seed: int, num_players: int, personalities: _Personalities) -> dict:
    game_rng = random.Random(seed)
    dummy_rng = random.Random()  # throwaway — only used to satisfy Player.__init__
    names = Constants.PLAYER_NAMES[:num_players]
    players = {}
    for name in names:
        p = Player(name, rng=dummy_rng)
        p.risk_appetite, p.peer_pressure_score, p.attentiveness_score = personalities[name]
        p._rng = game_rng  # bind game RNG so dice rolls are deterministic per seed
        players[name] = p
    collector = GameStatsCollector(seed, num_players)
    with LiarsDiceGame(num_players, rng=game_rng, on_event=collector.on_event) as game:
        for name in names:
            game.add_player(players[name])
        while game.process_round():
            pass
        winner_name = game.players[0].name
    return _build_result(seed, num_players, names, players, winner_name, game, collector)


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
            name: (persistent_players[name].risk_appetite, persistent_players[name].peer_pressure_score, persistent_players[name].attentiveness_score)
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


if __name__ == '__main__':
    import argparse
    from charts import show_tournament_stats

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
    show_tournament_stats(df, df_rounds, df_eliminations)
