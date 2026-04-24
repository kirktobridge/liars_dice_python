## claude branch
Working on this game with Claude Code now. Forked from the main branch so I can keep the original for posterity.

# liars_dice_python
A Python-based Liar's Dice game engine with:

AI players using a Bayesian binomial probability model, personality traits (risk appetite, peer pressure), and opponent profiling
CLI game mode with pirate-themed flavor text
Tournament/simulation mode with multiprocessing and a Plotly analytics dashboard
Event-driven architecture — the game emits events; a renderer, stats collector, and logger subscribe independently

To change the Google Fonts URL (i.e. swap to entirely different fonts), edit web/static/fonts.css — one @import line.

To update Tailwind's font utility classes (e.g. font-display), edit web/static/tailwind-config.js.