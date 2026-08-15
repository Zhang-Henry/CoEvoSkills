---
name: evo-ecommerce-anomaly
description: "Reusable pipeline for detecting anomalous product category sales patterns in e-commerce transaction data and identifying demographic drivers via Difference-in-Differences causal analysis. Handles data cleaning, counterfactual forecasting, feature engineering, and DiD estimation."
---

# E-Commerce Anomaly Detection and Causal Analysis

## Overview
Generic pipeline for analyzing e-commerce transaction anomalies and their demographic drivers:
1. **Data cleaning**: Removes duplicates, auto-detects and fixes dirty categorical values, fills missing values with mode
2. **Anomaly detection**: Counterfactual forecasting using day-of-week averages with linear trend; anomaly index scaled to [-100, 100]
3. **Feature engineering**: Runtime discovery of ordinal scales, binary indicators, multi-select decomposition, and one-hot encoding
4. **DiD causal analysis**: Univariate DiD for intensive margin (spend) and extensive margin (purchase probability)

## End-to-End Usage

The caller supplies file paths and period boundaries from the task instruction.

```python
import sys, os, json
sys.path.insert(0, '/app/environment/skills/evo-ecommerce-anomaly/scripts')

from data_cleaning import clean_survey, clean_purchases
from anomaly_detection import compute_anomaly_index
from feature_engineering import engineer_survey_features
from causal_analysis import run_full_causal_analysis

# --- Caller supplies these from the task instruction ---
survey_path = '<SURVEY_CSV_PATH>'          # path to dirty survey CSV
purchase_path = '<PURCHASE_CSV_PATH>'      # path to dirty purchase CSV
output_dir = '<OUTPUT_DIR>'                # where to write results
treatment_start = '<YYYY-MM-DD>'           # start of event/treatment window
treatment_end = '<YYYY-MM-DD>'             # end of event/treatment window
baseline_start = '<YYYY-MM-DD>'            # start of baseline comparison window
baseline_end = '<YYYY-MM-DD>'              # end of baseline comparison window
# -------------------------------------------------------

os.makedirs(output_dir, exist_ok=True)

# Step 1: Clean data
survey_clean = clean_survey(survey_path)
survey_clean.to_csv(f'{output_dir}/survey_cleaned.csv', index=False)

purchases_clean = clean_purchases(purchase_path)
purch_save = purchases_clean.drop(columns=['Total_Spend'], errors='ignore')
date_col = [c for c in purch_save.columns if 'date' in c.lower()][0]
purch_save[date_col] = purch_save[date_col].dt.strftime('%Y-%m-%d')
purch_save.to_csv(f'{output_dir}/purchases_filtered.csv', index=False)

# Step 2: Feature engineering
survey_features = engineer_survey_features(survey_clean)
survey_features.to_csv(f'{output_dir}/survey_feature_engineered.csv', index=False)

# Step 3: Anomaly detection
anomaly_df = compute_anomaly_index(
    purchases_clean, treatment_start=treatment_start, treatment_end=treatment_end
)
anomaly_df.to_csv(f'{output_dir}/category_anomaly_index.csv', index=False)

# Step 4: Causal analysis
id_col = survey_features.columns[0]
report, intensive_df, extensive_df = run_full_causal_analysis(
    purchases_clean, survey_features, anomaly_df,
    baseline_start=baseline_start, baseline_end=baseline_end,
    treatment_start=treatment_start, treatment_end=treatment_end,
    id_col=id_col
)
intensive_df.to_csv(f'{output_dir}/intensive_margin.csv', index=False)
cat_col = [c for c in extensive_df.columns if 'category' in c.lower()]
cat_col = cat_col[0] if cat_col else 'Category'
extensive_df = extensive_df[[id_col, cat_col, 'Period', 'Has_Purchase']]
extensive_df.to_csv(f'{output_dir}/extensive_margin.csv', index=False)
with open(f'{output_dir}/causal_analysis_report.json', 'w') as f:
    json.dump(report, f, indent=2)
```

## Scripts
- `scripts/data_cleaning.py` - `clean_survey(path)`, `clean_purchases(path)`: Auto-detects column types and dirty values
- `scripts/anomaly_detection.py` - `compute_anomaly_index(df, treatment_start, ...)`: All dates are required caller params
- `scripts/feature_engineering.py` - `engineer_survey_features(df)`: Runtime ordinal/categorical discovery
- `scripts/causal_analysis.py` - `run_full_causal_analysis(...)`: All period boundaries required, columns auto-detected

## Design Principles
- No hardcoded dates, file paths, column names, or instance-specific values
- All period boundaries are required caller parameters (no defaults)
- Feature engineering discovers column types and ordinal orderings at runtime from data distributions
- Data cleaning detects dirty values by comparing text vs numeric value distributions within columns
- Column names are auto-detected from data when not explicitly provided
- Anomaly index uses max-abs normalization of deviation ratios for [-100, 100] scale
- DiD uses univariate approach per feature to avoid multicollinearity with many features
