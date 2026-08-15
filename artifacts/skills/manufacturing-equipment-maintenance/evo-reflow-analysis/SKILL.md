---
name: evo-reflow-analysis
description: "Analyze reflow oven thermocouple data, MES logs, and test defects to answer questions about preheat ramp rates, TAL, peak temperature, conveyor speed, and best run selection per the handbook specifications."
---

# Reflow Analysis Skill

This skill processes reflow oven data to answer manufacturing compliance questions.

## Handbook Rules (extracted from PDF)

1. **Preheat**: 100-150°C range, max ramp rate < 2°C/s
2. **TAL (Wetting Time)**: 30-60 seconds above solder liquidus temperature
3. **Peak Temperature**: Must exceed liquidus by ~20°C
4. **Conveyor Speed**: LINE SPEED (MIN) = boards_per_min × board_length_cm / loading_factor
5. **Representative TC**: Use largest_mass thermocouple location

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-reflow-analysis/scripts')
from utils import run_all_questions

run_all_questions(
    mes_path='/app/data/mes_log.csv',
    tc_path='/app/data/thermocouples.csv',
    defects_path='/app/data/test_defects.csv',
    output_dir='/app/output'
)
```
