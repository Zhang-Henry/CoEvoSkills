---
name: evo-gw-detection
description: "Gravitational wave detection using matched filtering with PyCBC. Loads .gwf data, conditions it, performs grid search over mass parameters for multiple approximants, and reports peak SNR per approximant."
---

# Gravitational Wave Detection Skill

## Overview
Detects gravitational wave signals from binary black hole mergers using matched filtering.
Performs a grid search over component masses for multiple waveform approximants.

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-gw-detection/scripts')
from utils import run_full_detection, validate_results

# Run the full detection pipeline
df = run_full_detection(
    data_path='/root/data/PyCBC_T2_2.gwf',
    channel='H1:TEST-STRAIN',
    output_csv='/root/detection_results.csv',
    approximants=['SEOBNRv4_opt', 'IMRPhenomD', 'TaylorT4'],
    mass_min=10,
    mass_max=40,
    highpass_freq=15.0,
    resample_rate=4096,
    f_low=20.0,
    psd_seg_len=4
)

# Validate
validate_results('/root/detection_results.csv')
```

## Pipeline Steps

1. **Load data**: `load_gwf_data(filepath, channel)` - reads .gwf frame file
2. **Condition data**: `condition_data(strain, highpass_freq, resample_rate)` - high-pass filter, resample, crop transients
3. **Estimate PSD**: `estimate_psd(conditioned_data, seg_len, low_freq_cutoff)` - Welch method with interpolation and inverse spectrum truncation
4. **Grid search**: `grid_search_approximant(data, psd, approximant, mass_min, mass_max, ...)` - searches m1>=m2 combinations
5. **Matched filtering**: `compute_snr(data, template, psd, f_low, psd_seg_len)` - returns peak SNR after cropping corrupted edges
6. **Write results**: CSV with approximant, snr, total_mass columns

## Functions

- `load_gwf_data(filepath, channel)` - Load .gwf data
- `condition_data(strain, highpass_freq, resample_rate)` - Data conditioning
- `estimate_psd(conditioned_data, seg_len, low_freq_cutoff)` - PSD estimation
- `generate_template(mass1, mass2, approximant, sample_rate, f_low)` - Waveform generation
- `compute_snr(conditioned_data, template, psd, f_low, psd_seg_len)` - Matched filtering
- `grid_search_approximant(data, psd, approximant, mass_min, mass_max, ...)` - Grid search
- `run_full_detection(data_path, channel, output_csv, ...)` - End-to-end pipeline
- `validate_results(csv_path)` - Validate output CSV
