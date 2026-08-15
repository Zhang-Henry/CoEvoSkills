"""
Lake warming trend analysis and driver attribution utilities.

Trend: Mann-Kendall test for p-value, year-based Sen's slope (Theil-Sen)
  for rate of change in proper time units.
Attribution: Per-category R-squared from linear regression,
  normalized to sum to 100%.

All variable-to-category mappings are derived at runtime from column names.
"""
import pandas as pd
import numpy as np
from scipy import stats
import os
import warnings
warnings.filterwarnings('ignore')


def discover_csvs(data_dir):
    return sorted(
        os.path.join(data_dir, f)
        for f in os.listdir(data_dir)
        if f.lower().endswith('.csv')
    )


def load_and_merge(data_dir, target_file_keyword='temperature', join_key='Year'):
    csvs = discover_csvs(data_dir)
    if not csvs:
        raise FileNotFoundError(f"No CSV files found in {data_dir}")
    dfs = {}
    target_col = None
    for path in csvs:
        df = pd.read_csv(path)
        fname = os.path.basename(path).lower()
        dfs[fname] = df
        if target_file_keyword.lower() in fname:
            non_key = [c for c in df.columns if c != join_key]
            if non_key:
                target_col = non_key[0]
    merged = None
    for fname, df in dfs.items():
        if merged is None:
            merged = df
        else:
            merged = merged.merge(df, on=join_key, how='inner')
    if target_col is None:
        raise ValueError("Could not identify target temperature column")
    return merged, target_col


def compute_trend(df, time_col, target_col):
    """Mann-Kendall test for significance + year-based Sen's slope.
    Uses scipy theilslopes for proper time-unit slope and
    pymannkendall for the non-parametric p-value.
    Returns dict with 'slope' (units: target/time) and 'p-value'.
    """
    import pymannkendall as mk
    df_sorted = df.sort_values(time_col)
    x = df_sorted[time_col].values.astype(float)
    y = df_sorted[target_col].values.astype(float)
    # Year-based Sen's slope
    theil = stats.theilslopes(y, x)
    # MK p-value
    mk_result = mk.original_test(y)
    return {'slope': theil.slope, 'p-value': mk_result.p}


_CATEGORY_KEYWORDS = {
    'Heat':  ['airtemp', 'shortwave', 'longwave', 'radiation', 'solar',
              'sensible', 'latent', 'heatflux', 'thermal'],
    'Flow':  ['precip', 'rain', 'inflow', 'outflow', 'discharge',
              'streamflow', 'runoff', 'hydro'],
    'Wind':  ['wind', 'gust'],
    'Human': ['developed', 'agriculture', 'urban', 'impervious',
              'landcover', 'landuse', 'cropland', 'built'],
}


def classify_column(col_name, category_keywords=None):
    if category_keywords is None:
        category_keywords = _CATEGORY_KEYWORDS
    lower = col_name.lower().replace('_', '').replace(' ', '')
    for cat, keywords in category_keywords.items():
        for kw in keywords:
            if kw in lower:
                return cat
    return None


def build_category_map(predictor_cols, category_keywords=None):
    mapping = {}
    for col in predictor_cols:
        cat = classify_column(col, category_keywords)
        if cat is not None:
            mapping[col] = cat
    return mapping


def compute_attribution(df, target_col, time_col, category_keywords=None):
    """Compute relative importance using per-category R-squared from
    linear regression, normalized to sum to 100%.
    Returns (dominant_category, contribution_pct, details_dict).
    """
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score

    all_cols = [c for c in df.columns if c not in (target_col, time_col)]
    cat_map = build_category_map(all_cols, category_keywords)

    categories = {}
    for col, cat in cat_map.items():
        categories.setdefault(cat, []).append(col)

    if not categories:
        raise ValueError("No predictor columns could be classified.")

    y = df[target_col].values.astype(float)

    cat_r2 = {}
    for cat, cols in categories.items():
        X = df[cols].values.astype(float)
        model = LinearRegression()
        model.fit(X, y)
        r2 = r2_score(y, model.predict(X))
        cat_r2[cat] = max(r2, 0.0)

    total_r2 = sum(cat_r2.values())
    if total_r2 == 0:
        total_r2 = 1.0

    cat_importance = {cat: r2 / total_r2 * 100.0 for cat, r2 in cat_r2.items()}
    dominant = max(cat_importance, key=cat_importance.get)
    return dominant, cat_importance[dominant], cat_importance


def write_trend_csv(trend_dict, output_path):
    pd.DataFrame([trend_dict]).to_csv(output_path, index=False)
    return output_path


def write_dominant_csv(category, contribution, output_path):
    pd.DataFrame({'variable': [category], 'contribution': [contribution]}).to_csv(
        output_path, index=False
    )
    return output_path


def run_end_to_end(data_dir, output_dir,
                   target_file_keyword='temperature',
                   join_key='Year',
                   category_keywords=None):
    os.makedirs(output_dir, exist_ok=True)
    df, target_col = load_and_merge(data_dir, target_file_keyword, join_key)
    trend = compute_trend(df, join_key, target_col)
    trend_path = write_trend_csv(trend, os.path.join(output_dir, 'trend_result.csv'))
    dominant, contribution, details = compute_attribution(
        df, target_col, join_key, category_keywords
    )
    factor_path = write_dominant_csv(dominant, contribution,
                                     os.path.join(output_dir, 'dominant_factor.csv'))
    return {
        'trend': trend,
        'dominant_category': dominant,
        'contribution': contribution,
        'category_details': details,
        'trend_path': trend_path,
        'factor_path': factor_path,
    }


def validate_outputs(output_dir):
    trend_path = os.path.join(output_dir, 'trend_result.csv')
    factor_path = os.path.join(output_dir, 'dominant_factor.csv')
    assert os.path.exists(trend_path)
    dt = pd.read_csv(trend_path)
    assert 'slope' in dt.columns
    assert 'p-value' in dt.columns
    assert len(dt) == 1
    assert np.isfinite(dt['slope'].iloc[0])
    assert 0 <= dt['p-value'].iloc[0] <= 1
    assert os.path.exists(factor_path)
    dff = pd.read_csv(factor_path)
    assert 'variable' in dff.columns
    assert 'contribution' in dff.columns
    assert len(dff) == 1
    assert np.isfinite(dff['contribution'].iloc[0])
    assert dff['contribution'].iloc[0] > 0
    return True
