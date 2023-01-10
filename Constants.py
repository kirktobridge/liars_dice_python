import colorama
from colorama import Fore, Back, Style
MAX_NUM_DICE = 5
MAX_PLAYERS = 3
MAX_ROUNDS = 2
ACTIONS = ['ELIM', 'BID', 'RAISE', 'CHLG', 'SPOT', 'BLANK']
PROB_THRESHOLDS = {
    'LOW': 0.25,
    'MED': 0.5,
    'HIGH': 0.75,
    'VERY HIGH': 0.95,
    'CERTAIN': 1.0
}

SELF_RISK_THRESHOLDS = ['LOW', 'MED', 'HIGH']
PAUSE = 0.5
PLAYER_NAMES = ['Jack Sparrow', 'Hector Barbossa', 'Joshamee Gibbs',
                'Elizabeth Swann', 'Will Turner', 'Jack the Monkey', 'Davy Jones', 'Blackbeard', 'Calypso']
GAME_RULES = [Fore.BLUE + Style.BRIGHT + 'HERE BE THE RULES:\n']
TITLE_CARD = [
    " _       _________ _______  _______  _  _______    ______  _________ _______  _______ ",
    "( \      \__   __/(  ___  )(  ____ )( )(  ____ \  (  __  \ \__   __/(  ____ \(  ____ \\",
    "| (         ) (   | (   ) || (    )||/ | (    \/  | (  \  )   ) (   | (    \/| (    \/",
    "| |         | |   | (___) || (____)|   | (_____   | |   ) |   | |   | |      | (__    ",
    "| |         | |   |  ___  ||     __)   (_____  )  | |   | |   | |   | |      |  __)   ",
    "| |         | |   | (   ) || (\ (            ) |  | |   ) |   | |   | |      | (      ",
    "| (____/\___) (___| )   ( || ) \ \__   /\____) |  | (__/  )___) (___| (____/\| (____/\\",
    "(_______/\_______/|/     \||/   \__/   \_______)  (______/ \_______/(_______/(_______/",
    "BY @KIRKTOBRIDGE - GITHUB.COM/KIRKTOBRIDGE"]


DEBUG = True


# but must limit bid's count to max number of dice available
# if (prev_bid_cnt + 1) <= (tot_other_dice + self.num_dice):
