from LiarsDiceGame import LiarsDiceGame
from Player import Player
import colorama
from colorama import Fore, Back, Style
import time
import Constants
import random
from collections import Counter


def pirate_renderer(event: dict) -> None:
    """Translates every LiarsDiceGame event into the original pirate-voice CLI output."""
    etype = event['type']
    if etype == 'round_started':
        print(Fore.WHITE + f'<!> Round {event["round_num"]} Begin')
        time.sleep(Constants.PAUSE)
    elif etype == 'dice_rolling':
        print(Fore.CYAN + '<i> Rolling Dice...')
        time.sleep(Constants.PAUSE)
    elif etype == 'dice_rolled':
        print(Fore.CYAN + '<i> Dice Rolled')
    elif etype == 'turn_started':
        round_msg = ''
        if Constants.DEBUG:
            round_msg = str(event['num_dice']) + 'dice '
        round_msg += f'<*> Round {event["round_num"]}: {event["player_name"]}\'s Turn'
        print(round_msg)
        time.sleep(Constants.PAUSE)
    elif etype == 'bid_made':
        print(Fore.WHITE + f'<!> {event["player_name"]} bids {event["count"]} {event["face"]}\'s.')
        time.sleep(Constants.PAUSE)
    elif etype == 'raise_made':
        print(Fore.WHITE + f'<!> {event["player_name"]} raises the bid to {event["count"]} {event["face"]}\'s.')
        time.sleep(Constants.PAUSE)
    elif etype == 'challenge_called':
        print(Fore.WHITE + f'<!> {event["challenger_name"]} has challenged the previous bid of {event["bid_count"]} {event["bid_face"]}s made by {event["bidder_name"]}!')
    elif etype == 'rolls_revealed':
        print(Fore.CYAN + '<i> Lifting cups:\n')
        for p_data in event['player_rolls']:
            output = Fore.CYAN + f'<i> {p_data["name"]}\'s rolls: '
            player_roll_freq = Counter(p_data['dice'])
            loop_cnt = 0
            num_dice = len(p_data['dice'])
            for d in sorted(player_roll_freq, key=player_roll_freq.get):
                output += str(player_roll_freq[d]) + ' ' + str(d)
                if player_roll_freq[d] > 1:
                    output += '\'s'
                loop_cnt += 1
                if loop_cnt == len(player_roll_freq):
                    output += '.'
                elif loop_cnt == num_dice - 1:
                    output += ', and '
                else:
                    output += ', '
            print(output)
    elif etype == 'challenge_resolved':
        if event['succeeded']:
            output = f'{event["challenger_name"]}\'s challenge succeeds- there are only {event["actual_count"]} {event["bid_face"]}\'s'
            if event['ones_count'] > 0 and event['bid_face'] != 1:
                output += f' and {event["ones_count"]} 1\'s!'
            else:
                output += '!'
            print(Fore.WHITE + output)
        else:
            output = f'{event["challenger_name"]}\'s challenge fails- there are actually {event["actual_count"]} {event["bid_face"]}\'s'
            if event['ones_count'] > 0:
                output += f' and {event["ones_count"]} 1\'s!'
            else:
                output += '!'
            print(Fore.WHITE + output)
        time.sleep(Constants.PAUSE)
    elif etype == 'spot_on_called':
        print(Fore.WHITE + f'<!> {event["caller_name"]} has called \'SPOT ON\' on the previous bid of {event["bid_count"]} {event["bid_face"]}s made by Player {event["bidder_name"]}!')
    elif etype == 'spot_on_resolved':
        if event['succeeded']:
            print(Fore.CYAN + '<!> SPOT ON! Everyone else loses a die!')
        else:
            if event['caller_spot'] == 'HUMAN':
                print(Fore.BLUE + '<!> Sorry, that bid wasn\'t spot on.\n<i> You will lose a die.')
            else:
                print(Fore.CYAN + f'<!> {event["caller_name"]} lost their spot on call!')
        time.sleep(Constants.PAUSE)
    elif etype == 'player_eliminated':
        if event['spot'] == 'HUMAN':
            print(Fore.BLUE + Style.BRIGHT + f'<X> {event["player_name"]}, you have been eliminated from the game!')
        else:
            print(Fore.WHITE + f'<X> {event["player_name"]} has been eliminated from the game!')
        time.sleep(Constants.PAUSE)
    elif etype == 'game_won':
        print(f'<!> There is only one player remaining. {event["winner_name"]} has won the game!')
        time.sleep(Constants.PAUSE)
    elif etype == 'round_summary':
        print(f'<!> There are {event["num_players"]} players and a total of {event["tot_num_dice"]} dice remaining.')
        time.sleep(Constants.PAUSE)
    elif etype == 'error':
        print(Fore.MAGENTA + Style.DIM + event['message'])
    elif etype == 'debug':
        print(Fore.MAGENTA + Style.DIM + f'<d> {event["msg"]}')


def main():
    '''Handles user inputs to set up a LiarsDiceGame object.
    Provides the rules of the game if reqeuested.
    Triggers game start and prints game log upon completion.'''
    colorama.init(autoreset=True)
    for line0 in Constants.TITLE_CARD:
        print(Fore.GREEN + Style.BRIGHT + line0)
    print(Fore.CYAN + Style.BRIGHT +
          '<i> Arrrrrgh, matey! Let\'s play some Liar\'s Dice!')
    print(Fore.CYAN + Style.BRIGHT +
          '<i> Tis good ye\'re here. Ye\'ll scare away the rats, ye slack-jawed, plagued cuttlefish!')

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
                raise Exception(Fore.RED + Style.DIM + '<?> What did ye say?')

        except Exception as e:
            print(e)
            time.sleep(Constants.PAUSE)
            continue
        break

    while True:  # number of players typerror loop
        try:
            num_players = int(
                input(Fore.BLUE + '<?> How many scallywags would ye like t\' play with?: '))
            if isinstance(num_players, int) == True:
                if num_players == 1:
                    input_fails += 1
                    raise AttributeError(
                        Fore.RED + Style.DIM + '<!> Are ye\' daft? This isn\'t a game fer one.\n<!> How can ye bet against yerself?')
                elif num_players == 0:
                    input_fails += 1
                    raise AttributeError(
                        Fore.RED + Style.DIM + '<!> Matey... yer\' not makin\' any sense.')
                elif num_players < 0:
                    raise AttributeError(
                        Fore.RED + Style.DIM + random.choice(Constants.INSULTS))
                elif num_players > Constants.MAX_PLAYERS:
                    input_fails += 1
                    raise AttributeError(
                        Fore.RED + Style.DIM + f'<!> I decline to acquiesce to yer request. (Means \'no\'.)\n<i> T\' limit th\' computational workload, yer\'limited to takin\' yer\' chances against a total o\' {Constants.MAX_PLAYERS} scallywags.\n<i> Keep to th\' code.')

        except ValueError as e:
            input_fails += 1
            print(Fore.RED + Style.DIM +
                  '<!> That won\'t do matey, ye\'ve got to provide a number.')
            if input_fails > 2:
                time.sleep(Constants.PAUSE)
                print(Fore.YELLOW + Style.NORMAL +
                      random.choice(Constants.INSULTS))
                # TODO randomize insults
            time.sleep(Constants.PAUSE)
            continue
        except AttributeError as e:
            print(e)
            if input_fails > 2:
                time.sleep(Constants.PAUSE)
                print(Fore.YELLOW + Style.NORMAL +
                      random.choice(Constants.INSULTS))
                # TODO randomize insults
            time.sleep(Constants.PAUSE)
            continue
        print(Fore.CYAN +
              f'<i> {num_players} players selected. Initalizing...')
        break

    game = LiarsDiceGame(num_players, on_event=pirate_renderer, log=True)
    player_names_upper = list(map(str.upper, Constants.PLAYER_NAMES))
    while True and not Constants.MULTIPLAYER_ON:
        try:
            player_name = input(Fore.BLUE + '<?> What be yer name, matey? ')
            if player_names_upper.count(str.upper(player_name)) > 0:
                input_fails += 1
                raise AttributeError(
                    Fore.RED + Style.DIM + '<!> Arrrgh! Identity theft be a serious crime! Shape up, or I\'ll have yer\' guts fer garters!')
            else:
                game.add_player(Player(player_name, spot='HUMAN'))
                break
        except Exception as e:
            print(e)
            if input_fails > 2:
                time.sleep(Constants.PAUSE)
                print(Fore.YELLOW + Style.NORMAL +
                      random.choice(Constants.INSULTS))
                # TODO randomize insults
            time.sleep(Constants.PAUSE)
            continue

    rand_int = -1
    rand_ints_used = [-1]
    for p in range(1, num_players):

        while rand_ints_used.count(rand_int) > 0:
            rand_int = random.randint(
                0, len(Constants.PLAYER_NAMES)-1)
        rand_ints_used.append(rand_int)
        game.add_player(Player(Constants.PLAYER_NAMES[rand_int]))

    run_game = True

    while run_game:
        run_game = game.process_round()

    print(Fore.BLUE + Style.BRIGHT +
          '<!> Thanks fer playing! Now gimme all yer\' coins or ye\'ll be swimmin\' with the fishes!')
    if Constants.DEBUG == True and game._log_path:
        print(Fore.MAGENTA + f'----- GAME LOG: {game._log_path} -----')
    game.close()


if __name__ == '__main__':
    main()
