---
name: evo-tess-transit
description: "Detect exoplanet transit periods from TESS space telescope lightcurves. Identifies and removes stellar variability, runs BLS transit search with harmonic filtering, refines with batman model fitting, and validates across multiple detrending configurations."
---

# TESS Transit Period Detection

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-tess-transit/scripts')
from utils import find_exoplanet_period, validate_output

period = find_exoplanet_period(
    input_path='/root/data/tess_lc.txt',
    output_path='/root/period.txt',
    round_digits=5
)
validate_output('/root/period.txt')
```

## Pipeline Steps

1. **Load & filter** — read 4-column file (time, flux, flag, error), keep flag==0
2. **Outlier removal** — symmetric sigma clipping (configurable bounds)
3. **Stellar rotation** — Lomb-Scargle finds dominant periodic variability
4. **Multi-window BLS** — detrending windows derived as fractions of the
   stellar period; BLS peaks at stellar harmonics are excluded
5. **Iterative transit-masked detrending** — mask transit phases, interpolate,
   re-smooth, repeat to avoid absorbing transits into the trend
6. **Batman model fit** — differential evolution + Nelder-Mead for precise
   period, Rp/Rs, a/Rs, inclination
7. **Robustness** — repeat batman fit across the detrending window grid;
   report median period
8. **Output** — write rounded period to file

## Function Reference

| Function | Purpose |
|---|---|
| `load_and_filter(path)` | Quality-filtered LC |
| `remove_outliers(t,f,e,...)` | Sigma clipping |
| `identify_stellar_rotation(t,f,e)` | LS dominant period |
| `median_detrend(t,f,e,window)` | Simple median filter |
| `detrend_with_transit_mask(t,f,e,P,t0,window,...)` | Iterative masked detrend |
| `bls_search(t,f,e,...)` | BLS periodogram |
| `refine_bls(t,f,e,p0,...)` | Fine-grid BLS |
| `top_bls_peaks(results,...)` | Ranked peak list |
| `is_harmonic(pa,pb,...)` | Harmonic check |
| `multi_window_bls(t,f,e,stellar_p,...)` | Multi-window search |
| `fit_batman(t,f,e,per0,t0,...)` | Transit model fit |
| `find_exoplanet_period(in,out,...)` | End-to-end entry point |
| `validate_output(path,...)` | Output format check |

All numeric thresholds are function parameters with physically motivated
defaults. No instance-specific constants are embedded.
