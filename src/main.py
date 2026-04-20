from LiarsDiceGame import LiarsDiceGame
from Player import Player
from models import Action, Bid, InputRequest, InputResponse
import colorama
from colorama import Fore, Back, Style
import logging
import time
import sys
import constants as Constants
import presentation
import random
from collections import Counter

_fast = False

logger = logging.getLogger(__name__)


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(level=level, format='%(name)s [%(levelname)s] %(message)s', stream=sys.stderr)


def _pause(duration: float) -> None:
    if not _fast:
        time.sleep(duration)


def pirate_renderer(event: dict) -> None:
    """Translates every LiarsDiceGame event into the original pirate-voice CLI output."""
    etype = event['type']
    if etype == 'round_started':
        print(Fore.WHITE + f'<!> Round {event["round_num"]} Begin')
        _pause(presentation.PAUSE_MICRO)
    elif etype == 'dice_rolling':
        print(Fore.CYAN + '<i> Rolling Dice...')
        _pause(presentation.PAUSE_MICRO)
    elif etype == 'dice_rolled':
        print(Fore.CYAN + '<i> Dice Rolled')
    elif etype == 'turn_started':
        print(f'<*> Round {event["round_num"]}: {event["player_name"]}\'s Turn')
        _pause(presentation.PAUSE_MICRO)
    elif etype == 'bid_made':
        print(Fore.WHITE + f'<!> {event["player_name"]} bids {event["count"]} {event["face"]}\'s.')
        _pause(presentation.PAUSE_ROUTINE)
    elif etype == 'raise_made':
        print(Fore.WHITE + f'<!> {event["player_name"]} raises the bid to {event["count"]} {event["face"]}\'s.')
        _pause(presentation.PAUSE_ROUTINE)
    elif etype == 'challenge_called':
        print(Fore.WHITE + f'<!> {event["challenger_name"]} has challenged the previous bid of {event["bid_count"]} {event["bid_face"]}s made by {event["bidder_name"]}!')
        _pause(presentation.PAUSE_DRAMATIC)
    elif etype == 'human_turn_start':
        players = event['player_dice']
        current_player = event.get('current_player')
        name_w = max(len(p['name']) for p in players) + 2
        header = f"\n  {'Player':<{name_w}} Dice"
        print(Fore.CYAN + header)
        print(Fore.CYAN + '  ' + '-' * (name_w + 5))
        for p in players:
            marker = '* ' if p['name'] == current_player else '  '
            if p['name'] == current_player:
                print(Fore.YELLOW + Style.BRIGHT + marker + f"{p['name']:<{name_w}} {p['num_dice']}" + Style.RESET_ALL)
            else:
                print(Fore.CYAN + marker + f"{p['name']:<{name_w}} {p['num_dice']}")
        print()
    elif etype == 'rolls_revealed':
        print(Fore.CYAN + '<i> Lifting cups:\n')
        _pause(presentation.PAUSE_DRAMATIC)
        faces = [1, 2, 3, 4, 5, 6]
        col_w = 4
        bid_face = event.get('bid_face')
        highlight_faces = set()
        if bid_face is not None:
            highlight_faces.add(bid_face)
            if bid_face != 1:
                highlight_faces.add(1)
        name_w = max(len(p['name']) for p in event['player_rolls']) + 2
        header = f"{'Player':<{name_w}}"
        for f in faces:
            label = f"  {f}  "
            header += Fore.YELLOW + Style.BRIGHT + label + Fore.CYAN if f in highlight_faces else label
        divider = '-' * name_w + '+' + '+'.join('-' * col_w for _ in faces)
        print(Fore.CYAN + header)
        print(Fore.CYAN + divider)
        for p_data in event['player_rolls']:
            freq = Counter(p_data['dice'])
            row = Fore.CYAN + f"{p_data['name']:<{name_w}}"
            for f in faces:
                count = freq[f]
                cell = str(count) if count else ' '
                if f in highlight_faces and count:
                    row += Fore.YELLOW + Style.BRIGHT + f" {cell:^{col_w-1}} " + Fore.CYAN
                else:
                    row += f" {cell:^{col_w-1}} "
            print(row)
            _pause(presentation.PAUSE_MICRO)
        print()
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
        _pause(presentation.PAUSE_ROUTINE)
    elif etype == 'spot_on_called':
        print(Fore.WHITE + f'<!> {event["caller_name"]} has called \'SPOT ON\' on the previous bid of {event["bid_count"]} {event["bid_face"]}s made by Player {event["bidder_name"]}!')
        _pause(presentation.PAUSE_DRAMATIC)
    elif etype == 'spot_on_resolved':
        if event['succeeded']:
            losers = event.get('loser_names', [])
            loser_str = ', '.join(losers) if losers else 'Everyone else'
            print(Fore.CYAN + f'<!> SPOT ON! {loser_str} lose{"s" if len(losers) == 1 else ""} a die!')
        else:
            if event['caller_spot'] == 'HUMAN':
                print(Fore.BLUE + '<!> Sorry, that bid wasn\'t spot on.\n<i> You will lose a die.')
            else:
                print(Fore.CYAN + f'<!> {event["caller_name"]} lost their spot on call!')
        _pause(presentation.PAUSE_ROUTINE)
    elif etype == 'player_eliminated':
        if event['spot'] == 'HUMAN':
            print(Fore.BLUE + Style.BRIGHT + f'<X> {event["player_name"]}, you have been eliminated from the game! (Round {event["round_num"]})')
        else:
            print(Fore.WHITE + f'<X> {event["player_name"]} has been eliminated from the game! (Round {event["round_num"]})')
        _pause(presentation.PAUSE_DRAMATIC)
    elif etype == 'game_won':
        print(f'<!> There is only one player remaining. {event["winner_name"]} has won the game!')
        _pause(presentation.PAUSE_DRAMATIC)
    elif etype == 'round_summary':
        print(f'<!> There are {event["num_players"]} players and a total of {event["tot_num_dice"]} dice remaining.')
        _pause(presentation.PAUSE_ROUTINE)
    elif etype == 'error':
        print(Fore.MAGENTA + Style.DIM + event['message'])


def human_input_handler(request: InputRequest) -> InputResponse:
    """Handle all human player I/O. Returns {'action': Action, 'bid': Bid | None}."""
    dice = request['dice']
    tot_other_dice = request['tot_other_dice']
    sep = Fore.BLUE + ', '
    dice_str = sep.join(Fore.YELLOW + Style.BRIGHT + str(d) + Style.NORMAL for d in dice)
    print(Fore.BLUE + '<i> Your dice: [' + dice_str + Fore.BLUE + ']')

    if request['type'] == 'opening_bid':
        print(Fore.BLUE + '<i> You go first — make the opening bid.')
        bid_count = _prompt_bid_count(tot_other_dice + len(dice))
        bid_face = _prompt_bid_face()
        return {'action': Action.BID, 'bid': Bid(bid_count, bid_face)}

    prev_bid: Bid = request['prev_bid']
    prev_player: str = request['prev_player']
    print(Fore.BLUE + f'<i> {prev_player} bid {prev_bid.count} {prev_bid.face}\'s.')
    while True:
        try:
            choice = input(Fore.BLUE + f'<?> Your action — [{Fore.YELLOW + Style.BRIGHT}B{Fore.BLUE + Style.NORMAL}]id/Raise, [{Fore.YELLOW + Style.BRIGHT}C{Fore.BLUE + Style.NORMAL}]hallenge, [{Fore.YELLOW + Style.BRIGHT}S{Fore.BLUE + Style.NORMAL}]pot On: ').strip().upper()
            if choice not in ('B', 'BID', 'R', 'RAISE', 'C', 'CHALLENGE', 'S', 'SPOT'):
                raise ValueError('<!> Say B, C, or S, matey!')
            break
        except ValueError as e:
            print(Fore.RED + Style.DIM + str(e))

    if choice in ('B', 'BID', 'R', 'RAISE'):
        max_count = tot_other_dice + len(dice)
        while True:
            bid_count = _prompt_bid_count(max_count)
            bid_face = _prompt_bid_face()
            if bid_count < prev_bid.count or (bid_count == prev_bid.count and bid_face == prev_bid.face):
                print(Fore.RED + Style.DIM +
                      f'<!> Yarrr, that\'s not allowed, matey, yer bid must raise th\' count above {prev_bid.count}, or bid a diff\'rent face at count {prev_bid.count}.')
                continue
            break
        action = Action.RAISE if bid_count > prev_bid.count else Action.BID
        return {'action': action, 'bid': Bid(bid_count, bid_face)}
    elif choice in ('C', 'CHALLENGE'):
        return {'action': Action.CHALLENGE, 'bid': None}
    else:  # SPOT
        return {'action': Action.SPOT_ON, 'bid': None}


def _prompt_bid_count(max_count: int) -> int:
    while True:
        try:
            val = int(input(Fore.BLUE + '<?> Enter bid size: '))
            if val < 0:
                raise ValueError('<!> Ye\' cannot do that, matey.')
            if val > max_count:
                raise ValueError('<!> Are ye\' daft? Yer\' bettin\' more dice than are possible.')
            return val
        except ValueError as e:
            print(Fore.RED + Style.DIM + (str(e) if str(e).startswith('<!>') else '<!> Arrrgh, ye must provide an integer, matey!'))


def _prompt_bid_face() -> int:
    while True:
        try:
            val = int(input(Fore.BLUE + '<?> Enter face value (1–6): '))
            if val < 1 or val > 6:
                raise ValueError('<!> Ye\' cannot do that, matey.')
            return val
        except ValueError as e:
            print(Fore.RED + Style.DIM + (str(e) if str(e).startswith('<!>') else '<!> Arrrgh, ye must provide an integer, matey!'))


def main():
    '''Handles user inputs to set up a LiarsDiceGame object.
    Provides the rules of the game if reqeuested.
    Triggers game start and prints game log upon completion.'''
    global _fast
    _fast = '--fast' in sys.argv
    configure_logging(debug='--debug' in sys.argv)

    colorama.init(autoreset=True)
    for line0 in presentation.TITLE_CARD:
        print(Fore.GREEN + Style.BRIGHT + line0)
    print(Fore.CYAN + Style.BRIGHT +
          '<i> Arrrrrgh, matey! Let\'s play some Liar\'s Dice!')
    print(Fore.CYAN + Style.BRIGHT +
          '<i> Tis good ye\'re here. Ye\'ll scare away the rats, ye slack-jawed, plagued cuttlefish!')

    input_fails = 0
    while True:  # rules question loop
        rules = input(Fore.BLUE + Style.NORMAL +
                      '<?> Do ye know the rules of the game- or are ye a filthy landlubber? [Y/N]: ').upper()
        if rules in ('N', 'NO'):
            print(Back.WHITE + Fore.WHITE +
                  '___________________________________________________________________________________________')
            for line1 in presentation.GAME_RULES:
                print(line1)
            print(Back.WHITE + Fore.WHITE +
                  '___________________________________________________________________________________________')
        elif rules in ('Y', 'YES'):
            print(Fore.BLUE + Style.NORMAL +
                  '<i> Alright then, matey, let\'s get to it.')
        else:
            print(Fore.RED + Style.DIM + '<?> What did ye say?')
            _pause(presentation.PAUSE_ROUTINE)
            continue
        break

    while True:  # number of players loop
        try:
            num_players = int(
                input(Fore.BLUE + '<?> How many scallywags would ye like t\' play with?: '))
        except ValueError:
            input_fails += 1
            print(Fore.RED + Style.DIM +
                  '<!> That won\'t do matey, ye\'ve got to provide a number.')
            if input_fails > 2:
                _pause(presentation.PAUSE_ROUTINE)
                print(Fore.YELLOW + Style.NORMAL + random.choice(presentation.INSULTS))
            _pause(presentation.PAUSE_ROUTINE)
            continue
        if num_players == 1:
            input_fails += 1
            print(Fore.RED + Style.DIM +
                  '<!> Are ye\' daft? This isn\'t a game fer one.\n<!> How can ye bet against yerself?')
        elif num_players == 0:
            input_fails += 1
            print(Fore.RED + Style.DIM + '<!> Matey... yer\' not makin\' any sense.')
        elif num_players < 0:
            print(Fore.RED + Style.DIM + random.choice(presentation.INSULTS))
        elif num_players > Constants.MAX_PLAYERS:
            input_fails += 1
            print(Fore.RED + Style.DIM +
                  f'<!> I decline to acquiesce to yer request. (Means \'no\'.)\n<i> T\' limit th\' computational workload, yer\'limited to takin\' yer\' chances against a total o\' {Constants.MAX_PLAYERS} scallywags.\n<i> Keep to th\' code.')
        else:
            print(Fore.CYAN + f'<i> {num_players} players selected. Initalizing...')
            break
        if input_fails > 2:
            _pause(presentation.PAUSE_ROUTINE)
            print(Fore.YELLOW + Style.NORMAL + random.choice(presentation.INSULTS))
        _pause(presentation.PAUSE_ROUTINE)

    with LiarsDiceGame(num_players, on_event=pirate_renderer, log=True) as game:
        player_names_upper = list(map(str.upper, Constants.PLAYER_NAMES))
        while True:
            player_name = input(Fore.BLUE + '<?> What be yer name, matey? ')
            if player_names_upper.count(str.upper(player_name)) > 0:
                input_fails += 1
                print(Fore.RED + Style.DIM +
                      '<!> Arrrgh! Identity theft be a serious crime! Shape up, or I\'ll have yer\' guts fer garters!')
                if input_fails > 2:
                    _pause(presentation.PAUSE_ROUTINE)
                    print(Fore.YELLOW + Style.NORMAL + random.choice(presentation.INSULTS))
                _pause(presentation.PAUSE_ROUTINE)
                continue
            game.add_player(Player(player_name, spot='HUMAN', input_handler=human_input_handler))
            break

        sampled_indices = random.sample(range(len(Constants.PLAYER_NAMES)), num_players - 1)
        for idx in sampled_indices:
            game.add_player(Player(Constants.PLAYER_NAMES[idx]))

        run_game = True

        while run_game:
            run_game = game.process_round()

        print(Fore.BLUE + Style.BRIGHT +
              '<!> Thanks fer playing! Now gimme all yer\' coins or ye\'ll be swimmin\' with the fishes!')
        if game._log_path:
            print(Fore.CYAN + f'<i> Game log saved to: {game._log_path}')


if __name__ == '__main__':
    main()
