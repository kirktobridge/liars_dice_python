LLM_MODEL = "gemma4:e4b"
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
MAX_RISK_SCORE = 100
MAX_ATTENTIVENESS_SCORE = 100
MAX_BLUFF_SCORE = 100
TRAIT_JITTER = 8

# Archetype-based personality sampling. Generic — assigned randomly per game,
# independent of pirate name. Same character can play differently across games.
ARCHETYPES: list[dict] = [
    {'label': 'Salty Veteran',       'risk': 30, 'att': 80, 'bluff': 10, 'weight': 3},
    {'label': 'Reckless Buccaneer',  'risk': 80, 'att': 30, 'bluff': 60, 'weight': 2},
    {'label': 'Crafty Captain',      'risk': 50, 'att': 90, 'bluff': 35, 'weight': 2},
    {'label': 'Stoic Quartermaster', 'risk': 15, 'att': 70, 'bluff':  5, 'weight': 2},
    {'label': 'Wild Card',           'risk': 70, 'att': 50, 'bluff': 80, 'weight': 1},
]
ARCHETYPE_LABELS: list[str] = [a['label'] for a in ARCHETYPES]
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
