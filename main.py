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
    for line0 in Constants.TITLE_CARD:
        print(Fore.GREEN + Style.BRIGHT + line0)
    print(Fore.CYAN + Style.BRIGHT +
          '<i> Arrrrrgh, matey! Let\'s play some Liar\'s Dice!')

    input_fails = 0
    while True:  # rules question loop
        try:
            rules = input(Fore.BLUE + Style.NORMAL +
                          '<?> Do ye know the rules of the game- or are ye a filthy landlubber? [Y/N]: ').upper()
            if rules == 'N' or rules == 'NO':
                print(Back.WHITE + Fore.WHITE +
                      '___________________________________________________________________________________________')
                for line1 in Constants.GAME_RULES:
                    print(line1)
                print(Back.WHITE + Fore.WHITE +
                      '___________________________________________________________________________________________')
            elif rules == 'Y' or rules == 'YES':
                print(Fore.BLUE + Style.NORMAL +
                      '<i> Alright then, matey, let\'s get to it.')
            else:
                raise Exception(Fore.RED + Style.DIM + "<?> What did ye say?")

        except Exception as e:
            print(e)
            time.sleep(Constants.PAUSE)
            continue
        break

    while True:  # number of players typerror loop
        try:
            num_players = int(
                input(Fore.BLUE + "<?> How many scallywags would ye like t' play with?: "))

            if isinstance(num_players, int) == True and num_players < 2:
                input_fails += 1
                raise AttributeError(
                    Fore.RED + Style.DIM + "<!> Are ye' daft? This isn't a game fer one.\n<!> How can ye bet against yerself?")

            elif isinstance(num_players, int) == True and num_players > Constants.MAX_PLAYERS:
                input_fails += 1
                raise AttributeError(
                    Fore.RED + Style.DIM + f"<!> I decline to acquiesce to yer request. (Means 'no'.)\n<i> T' limit th' computational workload, yer limited to takin' yer chances against a total o' {Constants.MAX_PLAYERS} scallywags.\n<i> Keep to th' code.")

        except ValueError as e:
            input_fails += 1
            print(Fore.RED + Style.DIM +
                  "<!> That won't do matey, ye've got to provide a number.")
            if input_fails > 2:
                print(Fore.YELLOW + Style.NORMAL +
                      "<i> The problem is not the problem. The problem is your attitude about the problem. Do you understand?")
            time.sleep(Constants.PAUSE)
            continue
        except AttributeError as e:
            print(e)
            if input_fails > 2:
                print(Fore.YELLOW + Style.NORMAL +
                      "<i> The problem is not the problem. The problem is your attitude about the problem. Do you understand?")
            time.sleep(Constants.PAUSE)
            continue
        break
    while True:  # num players restrictions loop
        try:
            if isinstance(num_players, int) == True and num_players < 2:
                input_fails += 1
                raise Exception(
                    Fore.RED + Style.DIM + "<!> Are ye' daft? This isn't a game fer one.\n<!> How can ye bet against yerself?")
            elif isinstance(num_players, int) == True and num_players > Constants.MAX_PLAYERS:
                input_fails += 1
                raise Exception(
                    Fore.RED + Style.DIM + f"<!> I decline to acquiesce to yer request. (Means 'no'.)\n<i> T' limit th' computational workload, yer limited to takin' yer chances against a total o' {Constants.MAX_PLAYERS} scallywags.\n<i> Keep to th' code.")

        except Exception as e:
            print(e)
            if input_fails > 2:
                print(Fore.YELLOW + Style.NORMAL +
                      "<\"> The problem is not the problem. The problem is your attitude about the problem. Do you understand?")
            time.sleep(Constants.PAUSE)
            continue

        print(Fore.CYAN +
              f'<i> {num_players} players selected. Initalizing...')
        break

    game = LiarsDiceGame(num_players)
    if Constants.DEBUG == True:
        spot = 'CPU'
    else:
        spot = 'HUMAN'
    game.add_player(
        Player(input(Fore.BLUE + "<?> What be yer name, matey? "), spot=spot))
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
