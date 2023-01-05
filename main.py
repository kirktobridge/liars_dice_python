from LiarsDiceGame import LiarsDiceGame
from Player import Player
import colorama
from colorama import Fore, Back, Style
import time
import Constants

# Liar's Dice

def main():
    colorama.init(autoreset=True)
    print(Fore.GREEN + Style.BRIGHT + "[LIAR'S DICE]")
    

    while True:
        try:
            num_players = int(input(Fore.BLUE + "<?> Please indicate the total number of players: "))
        except:
            print(Fore.RED + Style.DIM + "<!> Sorry, you must enter an integer.")
            time.sleep(Constants.PAUSE)
            continue

        try:
            if isinstance(num_players, int) == True and num_players < 2:
                raise Exception(Fore.RED + Style.DIM + "<!> Sorry, you must play against at least one opponent.")
        except Exception as e:
            print(e)    
            time.sleep(Constants.PAUSE)
        else:
            print(Fore.CYAN + f'<i> {num_players} players selected. Initalizing...')
            break

    game = LiarsDiceGame(num_players)
    game.add_player(Player(input(Fore.BLUE + "<?> What is your name? "), spot='HUMAN'))
    for p in range(1,num_players):
        game.add_player(Player(f'P{p+1}'))

    run_game = False

    while run_game:
        print(Fore.WHITE + f'<!> Round {game.round_num} begin!')
        run_game = game.process_round()

    print(Fore.MAGENTA + '----- GAME LOG -----')
    for entry in game.game_log:
        print(entry)

if __name__ == '__main__':
    main()
