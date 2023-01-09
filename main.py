from LiarsDiceGame import LiarsDiceGame
from Player import Player
import colorama
from colorama import Fore, Back, Style
import time
import Constants
import random

# Liar's Dice


def main():
    colorama.init(autoreset=True)
    for line in Constants.TITLE_CARD:
        print(Fore.GREEN + Style.BRIGHT + line)
    print(Fore.CYAN + Style.BRIGHT +
          '<i> Arrrrrgh, matey! Let\'s play some Liar\'s Dice!')
    rules = input(Fore.BLUE + Style.NORMAL +
                  '<?> Do ye know the rules of the game- or are ye a filthy landlubber? [Y/N]: ')
    if rules == True:
        for
    while True:
        try:
            num_players = int(
                input(Fore.BLUE + "<?> How many scallywags would ye like t' play with?: "))
        except:
            print(Fore.RED + Style.DIM +
                  "<!> That won't do matey, ye've got to provide a number.")
            time.sleep(Constants.PAUSE)
            continue

        try:
            if isinstance(num_players, int) == True and num_players < 2:
                raise Exception(
                    Fore.RED + Style.DIM + "<!> Sorry, you must play against at least one opponent.")
            elif isinstance(num_players, int) == True and num_players > Constants.MAX_PLAYERS:
                raise Exception(
                    Fore.RED + Style.DIM + f"<!> Sorry, to limit computational workload, you are limited to {Constants.MAX_PLAYERS} players.")

        except Exception as e:
            print(e)
            time.sleep(Constants.PAUSE)
            continue

        print(Fore.CYAN +
              f'<i> {num_players} players selected. Initalizing...')
        break

    game = LiarsDiceGame(num_players)
    game.add_player(
        Player(input(Fore.BLUE + "<?> What is your name? "), spot='CPU'))
    rand_int = -1
    rand_ints_used = [-1]
    for p in range(1, num_players):

        while rand_ints_used.count(rand_int) > 0:
            rand_int = random.randint(
                0, len(Constants.PLAYER_NAMES)-1)
        rand_ints_used.append(rand_int)
        game.add_player(Player(Constants.PLAYER_NAMES[rand_int]))

    game.report_rolls()

    run_game = True

    while run_game:
        run_game = game.process_round()

    print(Fore.MAGENTA + '----- GAME LOG -----')
    for entry in game.game_log:
        print(entry)


if __name__ == '__main__':
    main()
