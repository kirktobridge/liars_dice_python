# liars_dice_python
Python simulation of Liar's Dice (includes the 'Spot On' variation). One human player only.
The game is modeled using three classes:

# LiarsDiceGame
Manages players, runs rounds by signaling Players to roll dice and triggering their decision-making. Handles tasks like eliminating players, and arbitrating challenges and spot on calls.

# Player
Represents a player that can be placed in a LiarsDiceGame object's inventory. Maintains personal inventory of dice, makes play decisions (bid, challenge, call spot on).

# Main Class
Initializes a LiarsDiceGame object, collects setup inputs (number of players, name) from human and sets up game for 1 human player. Talks like a pirate.