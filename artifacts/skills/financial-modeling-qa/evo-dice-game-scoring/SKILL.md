---
name: evo-dice-game-scoring
description: "Dice game scoring optimization: parse Excel workbook with dice rolls, compute category scores per turn, optimize game scores across turns with no-repeat category constraint, and answer comparative questions about player matchups."
---

# Dice Game Scoring Optimization

This skill handles dice game analysis tasks where:
- A workbook contains dice roll data (6 rolls per turn, 2 turns per game)
- Turns must be scored using categories with specific rules
- Games are scored by optimally assigning different categories to each turn
- Questions involve comparing players across matched games

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-dice-game-scoring/scripts')
from dice_scoring import (
    parse_dice_data,
    compute_all_scores,
    best_game_score,
    compute_all_game_scores,
    match_players
)

# Parse data
turns, games = parse_dice_data('/root/data.xlsx')

# Compute all game scores
game_scores = compute_all_game_scores(games)

# Match players: odd games = P1, even games = P2
p1_wins, p2_wins, ties = match_players(game_scores)
result = p1_wins - p2_wins

with open('/root/answer.txt', 'w') as f:
    f.write(str(result))
```

## Key Design Decisions

- Missing turns are handled gracefully (1-turn games scored with best single category)
- The "Ordered subset of four" category checks consecutive positions in roll order
- Category assignment optimization uses brute-force over 6 categories (fast enough)
- PDF background must be read at runtime to extract exact scoring rules
