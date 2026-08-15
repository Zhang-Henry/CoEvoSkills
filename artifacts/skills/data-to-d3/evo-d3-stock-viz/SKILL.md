---
name: evo-d3-stock-viz
description: "Generate a D3.js v6 single-page web app with a force-simulation bubble chart and coordinated data table for stock market data. Use when the task requires visualizing stocks by sector with bubble sizing by market cap, sector-colored clustering, tooltips, and click-linked table."
---

# D3.js Stock Visualization Skill

Generates a complete single-page web app with:
- **Bubble chart**: Force-simulated, clustered by sector, sized by market cap (sqrt scale), colored by sector, with legends and ticker labels
- **Data table**: All stocks with Ticker, Name, Sector, Market Cap (human-readable format)
- **Coordination**: Click a bubble to highlight its table row and vice versa
- **Tooltips**: Hover shows ticker, name, sector (suppressed for ETFs)

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-d3-stock-viz/scripts')
from generate_app import generate_stock_viz_app, validate_app

# Generate the complete web app
generate_stock_viz_app(
    input_data_dir='/root/data',
    output_dir='/root/output'
)

# Validate all required files exist
assert validate_app('/root/output'), "Validation failed"
```

## Architecture

### Output Structure
```
output/
  index.html              # Entry point
  js/d3.v6.min.js         # D3 v6 library (local copy)
  js/visualization.js     # All viz logic
  css/style.css           # Layout, tooltip, table, highlight styles
  data/                   # Copied input data
    stock-descriptions.csv
    indiv-stock/*.csv
```

### Key Design Decisions

1. **Bubble sizing**: Uses `d3.scaleSqrt()` for area-proportional encoding. ETFs get uniform radius since they lack marketCap.
2. **Sector clustering**: Uses `forceX`/`forceY` with per-sector target positions arranged in a circle. `forceCollide` prevents overlap.
3. **Market cap formatting**: Custom function using T/B/M/K suffixes (e.g., "1.64T").
4. **ETF handling**: No tooltip shown on hover. Market cap displays as "N/A".
5. **Labels**: Ticker text inside each bubble, font-size scaled to bubble radius.
6. **Coordination**: Single `selectStock(ticker)` function toggles `.selected` on bubbles and `.highlighted` on table rows.
7. **Layout**: CSS flexbox for side-by-side arrangement. Table container has `overflow-y: auto` for scrolling.

### Scripts

- `scripts/generate_app.py` — Contains all generation functions:
  - `generate_stock_viz_app(input_data_dir, output_dir)` — End-to-end entry point
  - `validate_app(output_dir)` — Validates output structure
  - `ensure_d3_library(output_dir)` — Gets D3.js from npm if needed
  - `copy_data(input_data_dir, output_dir)` — Copies CSV data
  - `write_css(output_dir)` — Generates style.css
  - `write_visualization_js(output_dir)` — Generates visualization.js
  - `write_index_html(output_dir)` — Generates index.html
