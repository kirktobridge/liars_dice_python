# liars_dice_python
Python simulation of Liar's Dice (includes the 'Spot On' variation). One human player only.
The game is modeled using three classes:

# Player
Maintains personal inventory of dice, makes play decisions (bid, challenge, call).

# LiarsDiceGame
Maintains players, runs rounds by signaling Players to roll dice and triggering their decision-making.

# Main Class
Initializes a LiarsDiceGame object, collects setup inputs (number of players, name) and sets up game for 1 human player.