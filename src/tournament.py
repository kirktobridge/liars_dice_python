import logging
import os
import random
import sys
from collections.abc import Callable

logging.getLogger('liars_dice').addHandler(logging.NullHandler())
logger = logging.getLogger(__name__)
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm
import pandas as pd
from LiarsDiceGame import LiarsDiceGame
from Player import Player
from stats_collector import GameStatsCollector
from stats_schema import rounds_to_df, eliminations_to_df
from strategy import Personality
import constants as Constants

# name -> Personality (one per CPU player). LLM/HUMAN players are absent from this map.
_Personalities = dict[str, Personality]


def _trait_columns(name: str, personality: 'Personality | None') -> dict:
    safe = name.replace(' ', '_')
    if personality is None:
        return {f'p_{safe}_risk': 0, f'p_{safe}_att': 0, f'p_{safe}_bluff': 0,
                f'p_{safe}_archetype': None}
    return {
        f'p_{safe}_risk':      personality.risk_appetite,
        f'p_{safe}_att':       personality.attentiveness_score,
        f'p_{safe}_bluff':     personality.bluff_frequency,
        f'p_{safe}_archetype': personality.archetype_label,
    }


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
    winner_pers = winner.personality
    player_data: dict = {}
    for name in names:
        player_data.update(_trait_columns(name, players[name].personality))
    return {
        'seed': seed,
        'winner': winner_name,
        'rounds': game.round_num,
        'num_players': num_players,
        'winner_risk_appetite': winner_pers.risk_appetite if winner_pers else 0,
        'winner_attentiveness': winner_pers.attentiveness_score if winner_pers else 0,
        'winner_bluff_frequency': winner_pers.bluff_frequency if winner_pers else 0,
        'winner_archetype': winner_pers.archetype_label if winner_pers else None,
        **player_data,
        '_round_rows': collector.round_rows,
        '_elim_rows': collector.elimination_rows,
    }


def run_game(seed: int, num_players: int, players: dict[str, Player] | None = None) -> dict:
    rng = random.Random(seed)
    names = list(players.keys()) if players is not None else Constants.PLAYER_NAMES[:num_players]
    num_players = len(names)
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
    names = list(personalities.keys())
    players = {
        name: Player(name, rng=game_rng, personality=personalities[name])
        for name in names
    }
    collector = GameStatsCollector(seed, num_players)
    with LiarsDiceGame(num_players, rng=game_rng, on_event=collector.on_event) as game:
        for name in names:
            game.add_player(players[name])
        while game.process_round():
            pass
        winner_name = game.players[0].name
    return _build_result(seed, num_players, names, players, winner_name, game, collector)


def run_tournament(
    n: int,
    num_players: int = 4,
    workers: int | None = None,
    parallel: bool = False,
    on_progress: Callable[[float], None] | None = None,
    player_configs: list[dict] | None = None,
    show_progress: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run n games and return (df_games, df_rounds, df_eliminations).

    parallel=True uses ProcessPoolExecutor. Safe for web callers running inside
    daemon threads (e.g. threading.Thread), but not directly inside an async event loop.

    player_configs: optional list of dicts with keys name, risk_appetite,
        attentiveness_score, bluff_frequency, optional archetype. When provided,
        these players are used with fixed personalities instead of randomly
        assigning traits.
    """
    if player_configs is not None:
        names = [c['name'] for c in player_configs]
        num_players = len(names)
    else:
        names = Constants.PLAYER_NAMES[:num_players]
    if not (2 <= num_players <= Constants.MAX_PLAYERS):
        raise ValueError(f"num_players must be between 2 and {Constants.MAX_PLAYERS}, got {num_players}")
    if player_configs is not None:
        has_llm = any(c.get('player_type', 'CPU') == 'LLM' for c in player_configs)
        if parallel and has_llm:
            raise ValueError("LLM players are not supported with parallel=True")
        dummy_rng = random.Random()
        persistent_players = {}
        for c in player_configs:
            ptype = c.get('player_type', 'CPU')
            personality = None
            if ptype == 'CPU':
                personality = Personality.from_traits(
                    risk_appetite=c['risk_appetite'],
                    attentiveness_score=c['attentiveness_score'],
                    bluff_frequency=c['bluff_frequency'],
                    archetype_label=c.get('archetype'),
                )
            persistent_players[c['name']] = Player(
                c['name'],
                player_type=ptype,
                rng=dummy_rng,
                llm_model=c.get('llm_model'),
                personality=personality,
            )
    else:
        personality_rng = random.Random()
        persistent_players = {name: Player(name, rng=personality_rng) for name in names}

    num_workers = workers if workers is not None else os.cpu_count() or 1
    # Throttle tqdm updates for large simulations to avoid render overhead
    update_interval = max(1, n // 1000)  # ~1000 updates regardless of n

    if not parallel or num_workers == 1:
        # Serial path — reuses player objects (original behaviour)
        results = []
        with tqdm(
            range(n),
            desc="Simulating games",
            unit="game",
            miniters=update_interval,
            dynamic_ncols=True,
            colour="green",
            disable=not show_progress,
        ) as pbar:
            for i in pbar:
                result = run_game(seed=i, num_players=num_players, players=persistent_players)
                results.append(result)
                pbar.set_postfix(last_winner=result['winner'], rounds=result['rounds'])
                if on_progress and (i % update_interval == 0):
                    on_progress((i + 1) / n)
    else:
        # Parallel path — snapshot Personalities so workers can reconstruct players safely.
        # Guarded above: parallel implies all-CPU, so every player has a personality.
        personalities: _Personalities = {
            name: persistent_players[name].personality for name in names
        }
        chunk = max(1, n // (num_workers * 4))
        args_iter = ((i, num_players, personalities) for i in range(n))

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            results = []
            for i, result in enumerate(tqdm(
                executor.map(_run_game_worker, args_iter, chunksize=chunk),
                total=n,
                desc=f"Simulating games ({num_workers} workers)",
                unit="game",
                miniters=update_interval,
                dynamic_ncols=True,
                colour="green",
                disable=not show_progress,
            )):
                results.append(result)
                if on_progress and (i % update_interval == 0):
                    on_progress((i + 1) / n)

    round_rows = [row for r in results for row in r.pop('_round_rows', [])]
    elim_rows  = [row for r in results for row in r.pop('_elim_rows', [])]
    return pd.DataFrame(results), rounds_to_df(round_rows), eliminations_to_df(elim_rows)


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
        df, df_rounds, df_eliminations = run_tournament(args.num_games, num_players=args.num_players, workers=args.workers, parallel=True)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    show_tournament_stats(df, df_rounds, df_eliminations)
