MAX_NUM_DICE = 6
MAX_PLAYERS = 8
MAX_ROUNDS = 100
MINIMUM_BID = 2
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
MIN_SPOT_ON_RISK = 0.6
RISK_APPETITE_DISTRIBUTION = list(range(1, 101))
MAX_RISK_SCORE = max(RISK_APPETITE_DISTRIBUTION)
PEER_PRESSURE_DISTRIBUTION = list(range(1, 101))
MAX_PEER_PRESSURE_SCORE = max(PEER_PRESSURE_DISTRIBUTION)
ATTENTIVENESS_DISTRIBUTION = list(range(1, 101))
MAX_ATTENTIVENESS_SCORE = max(ATTENTIVENESS_DISTRIBUTION)
POSITIONAL_CUNNING_DISTRIBUTION: list[int] = list(range(1, 101))
MAX_POSITIONAL_CUNNING_SCORE: int = max(POSITIONAL_CUNNING_DISTRIBUTION)
LOWEST_THRESHOLD = 'LOWER THAN DAVY JONES\' LOCKER'
SELF_RISK_THRESHOLDS = ['LOW', 'MED', 'HIGH']
PLAYER_NAMES = [
    # Core Crew / Main Characters
    'Captain Jack Sparrow',
    'Captain Hector Barbossa',
    'First Mate Joshamee Gibbs',
    'Pirate King Elizabeth Swann',
    'Will Turner',
    'Jack the Monkey',

    # Villains & Antagonists
    'Captain Davy Jones',
    'Captain Blackbeard',
    'Calypso',
    'Lord Cutler Beckett',
    'Davy Jones\' Kraken',

    # Flying Dutchman Crew
    'Bootstrap Bill Turner',
    'Maccus',
    'Hadras',
    'Koleniko',

    'Pintel',
    'Ragetti',
    'Cotton',
    'Cotton\'s Parrot',
    'Marty',
    'Leech',

    # Pirate Lords (Brethren Court)
    'Sao Feng',
    'Ammand the Corsair',
    'Mistress Ching',
    'Eduardo Villanueva',
    'Capitaine Chevalle',
    'Gentleman Jocard',

    # Supporting / Royal Navy
    'Commodore James Norrington',
    'Governor Weatherby Swann',
    'Captain Salazar',
    'Henry Turner',
    'Carina Smyth',

    # On Stranger Tides
    'Angelica',
    'Philip Swift',
    'Syrena',
    'Scrum',
]
