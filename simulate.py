import random
import pandas as pd
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


if __name__ == '__main__':
    df = run_tournament(1000, num_players=4)
    print(df['winner'].value_counts())
    print(f"Avg rounds: {df['rounds'].mean():.1f}")
