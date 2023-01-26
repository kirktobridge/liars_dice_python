import colorama
from colorama import Fore, Style
MAX_NUM_DICE = 6
MAX_PLAYERS = 8
MAX_ROUNDS = 100
MINIMUM_BID = 2
MULTIPLAYER_ON = False
ACTIONS = ['START', 'BID', 'RAISE', 'CHLG', 'SPOT', 'BLANK']
PROB_THRESHOLDS = {
    'HELL FREEZES OVER': 0.05,
    'EXTREMELY LOW': 0.10,
    'VERY LOW': 0.15,
    'LOW': 0.25,
    'MED': 0.5,
    'HIGH': 0.75,
    'VERY HIGH': 0.95,
    'CERTAIN': 1.0
}
MIN_SPOT_ON_RISK = 0.1
RISK_APPETITE_DISTRIBUTION = [0] * 5 + [1] * 3 + [2] * 2
MAX_RISK_SCORE = max(RISK_APPETITE_DISTRIBUTION)
PEER_PRESSURE_DISTRIBUTION = [0] * 2 + [1]
MAX_PEER_PRESSURE_SCORE = max(PEER_PRESSURE_DISTRIBUTION)
LOWEST_THRESHOLD = 'LOWER THAN DAVY JONES\' LOCKER'
DEBUG = True  # used to activate behaviors for the developer
SELF_RISK_THRESHOLDS = ['LOW', 'MED', 'HIGH']
PAUSE = 0 if DEBUG else 1
PLAYER_NAMES = ['Captain Jack Sparrow', 'Captain Hector Barbossa', 'First Mate Joshamee Gibbs',
                'Pirate King Elizabeth Swann', 'Will Turner', 'Jack the Monkey', 'Captain Davy Jones', 'Captain Blackbeard', 'Calypso']
GAME_RULES = [Fore.YELLOW +
              '<i> DO UNDERSTAND, MATEY, THERE BE MANY VARIATIONS O\' THIS GAME. THIS BE MINE.', Fore.BLUE + Style.BRIGHT +
              '<i> HERE BE THE RULES. THEY BE IN THE QUEEN\'S ENGLISH, NOT PIRATE.', Fore.WHITE + Style.NORMAL +
              f'<i> At the start of the game, each player will be given {MAX_NUM_DICE} dice.', Fore.BLUE + Style.NORMAL +
              '<i> For every round:', Fore.MAGENTA +
              '<i> Players will roll their dice simultaneously and keep the results to themselves.', Fore.MAGENTA +
              '<i> Players will then begin taking turns in a clockwise order. On your turn,', Fore.BLUE + Style.BRIGHT +
              '<i> You will have THREE options:', Fore.GREEN + Style.BRIGHT +
              '<i> 1) BID - DECLARE A FACE VALUE AND THE MINIMUM NUMBER OF DICE UNDER CUPS', Fore.GREEN + Style.BRIGHT +
              '           THAT YOU BELIEVE ARE SHOWING THAT VALUE, E.G. \'THREE SIXES.\'', Fore.WHITE +
              '           If someone has bid before you:', Fore.YELLOW +
              '           <*> You may only raise the amount of the previous bid', Fore.YELLOW +
              '           <*> or you may change the face value you are bidding on.', Fore.GREEN + Style.BRIGHT +
              '<i> 2) CHALLENGE - DECLARE THAT THE LAST BID DECLARED IS FALSE. ALL PLAYERS', Fore.GREEN +
              '           WILL THEN REVEAL THEIR DICE AND A COUNT WILL BE TAKEN.', Fore.YELLOW +
              '           <*> If the challenged bid is false, the challenge is a success:', Fore.RED +
              '               CHALLENGED PLAYER LOSES A DIE', Fore.YELLOW +
              '           <*> If the challenged bid is correct, the challenge fails:', Fore.RED +
              '               YOU LOSE A DIE', Fore.WHITE +
              '           <*> e.g. If the previous bid was for \'THREE SIXES\', and we find,', Fore.WHITE +
              '               after challenging, that there are four sixes, the challenge will fail,', Fore.WHITE +
              '               as there are AT LEAST THREE SIXES. If there are TWO OR FEWER SIXES', Fore.WHITE +
              '               your challenge succeeds.',  Fore.GREEN +
              '           AFTER THE CHALLENGE IS COMPLETE, A NEW ROUND BEGINS (ALL PLAYERS RE-ROLL).', Fore.GREEN + Style.BRIGHT +
              '<i> 3) CALL \'SPOT ON\' - DECLARE THAT THE PREVIOUS BID IS EXACTLY CORRECT: NO MORE, NO LESS.', Fore.GREEN +
              '       ALL PLAYERS WILL THEN REVEAL THEIR DICE AND A COUNT WILL BE TAKEN.', Fore.YELLOW +
              '           <*> If the previous bid is exactly correct, your call succeeds:', Fore.RED +
              '               ALL OTHER PLAYERS LOSE A DIE', Fore.YELLOW +
              '           <*> If the previous bid is not exactly correct, your call fails:', Fore.RED +
              '               YOU LOSE A DIE', Fore.WHITE +
              '           <*> e.g. If the previous bid was for \'THREE SIXES,\', and there are actually', Fore.WHITE +
              '               FOUR SIXES or TWO SIXES, your \'SPOT ON\' call will fail.', Fore.GREEN +
              '           AFTER THE CALL IS RESOLVED, A NEW ROUND BEGINS- ALL PLAYERS RE-ROLL.', Fore.MAGENTA +
              '\n<i> Aces Wild: A roll of ONE is considered a wild card. E.g., a roll of TWO SIXES and TWO ONES', Fore.MAGENTA +
              '    can be used as a roll of FOUR SIXES.']
TITLE_CARD = [
    " _       _________ _______  _______  _  _______    ______  _________ _______  _______ ",
    "( \      \__   __/(  ___  )(  ____ )( )(  ____ \  (  __  \ \__   __/(  ____ \(  ____ \\",
    "| (         ) (   | (   ) || (    )||/ | (    \/  | (  \  )   ) (   | (    \/| (    \/",
    "| |         | |   | (___) || (____)|   | (_____   | |   ) |   | |   | |      | (__    ",
    "| |         | |   |  ___  ||     __)   (_____  )  | |   | |   | |   | |      |  __)   ",
    "| |         | |   | (   ) || (\ (            ) |  | |   ) |   | |   | |      | (      ",
    "| (____/\___) (___| )   ( || ) \ \__   /\____) |  | (__/  )___) (___| (____/\| (____/\\",
    "(_______/\_______/|/     \||/   \__/   \_______)  (______/ \_______/(_______/(_______/",
    "singleplayer edition\nBY @KIRKTOBRIDGE - GITHUB.COM/KIRKTOBRIDGE"]
