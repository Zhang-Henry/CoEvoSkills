import pandas as pd
import numpy as np
import statsmodels.api as sm
import warnings
warnings.filterwarnings('ignore')

def prepare_intensive_margin_data(purchases_df, survey_features_df, top_categories,
                                   baseline_start, baseline_end,
                                   treatment_start, treatment_end,
                                   date_col, cat_col, id_col, spend_col):
    """Prepare data for intensive margin DiD analysis."""
    df = purchases_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    baseline_mask = (df[date_col] >= baseline_start) & (df[date_col] <= baseline_end)
    treatment_mask = (df[date_col] >= treatment_start) & (df[date_col] <= treatment_end)
    df_period = df[baseline_mask | treatment_mask].copy()
    df_period['Period'] = np.where(
        (df_period[date_col] >= treatment_start) & (df_period[date_col] <= treatment_end),
        'treatment', 'baseline'
    )
    df_period = df_period[df_period[cat_col].isin(top_categories)]
    agg = df_period.groupby([id_col, cat_col, 'Period']).agg(
        Total_Spend=(spend_col, 'sum')
    ).reset_index()
    return agg

def prepare_extensive_margin_data(purchases_df, survey_features_df, top_categories,
                                   baseline_start, baseline_end,
                                   treatment_start, treatment_end,
                                   date_col, cat_col, id_col):
    """Prepare data for extensive margin DiD analysis."""
    df = purchases_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    baseline_mask = (df[date_col] >= baseline_start) & (df[date_col] <= baseline_end)
    treatment_mask = (df[date_col] >= treatment_start) & (df[date_col] <= treatment_end)
    df_period = df[baseline_mask | treatment_mask].copy()
    df_period['Period'] = np.where(
        (df_period[date_col] >= treatment_start) & (df_period[date_col] <= treatment_end),
        'treatment', 'baseline'
    )
    df_period = df_period[df_period[cat_col].isin(top_categories)]
    purchasers = df_period.groupby([id_col, cat_col, 'Period']).size().reset_index(name='count')
    purchasers['Has_Purchase'] = 1
    all_users = survey_features_df[id_col].unique()
    periods = ['baseline', 'treatment']
    user_period = pd.DataFrame({
        id_col: np.repeat(all_users, len(periods)),
        'Period': np.tile(periods, len(all_users))
    })
    result_frames = []
    for cat in top_categories:
        cat_frame = user_period.copy()
        cat_frame[cat_col] = cat
        result_frames.append(cat_frame)
    grid = pd.concat(result_frames, ignore_index=True)
    result = grid.merge(
        purchasers[[id_col, cat_col, 'Period', 'Has_Purchase']],
        on=[id_col, cat_col, 'Period'], how='left'
    )
    result['Has_Purchase'] = result['Has_Purchase'].fillna(0).astype(int)
    return result

def run_univariate_did(data_df, features_df, category, feature, outcome_col,
                       id_col, cat_col):
    """Run univariate DiD for a single feature on a given outcome."""
    cat_data = data_df[data_df[cat_col] == category].copy()
    merged = cat_data.merge(features_df, on=id_col, how='inner')
    if len(merged) < 10:
        return None
    merged['Post'] = (merged['Period'] == 'treatment').astype(int)
    if feature not in merged.columns:
        return None
    merged[feature] = pd.to_numeric(merged[feature], errors='coerce')
    valid = merged[[outcome_col, 'Post', feature]].dropna()
    if len(valid) < 10 or valid[feature].nunique() < 2:
        return None
    y = valid[outcome_col].astype(float)
    X = valid[['Post', feature]].astype(float).copy()
    X['Post_x_Feature'] = X['Post'] * X[feature]
    X = sm.add_constant(X)
    try:
        model = sm.OLS(y, X).fit()
        coef = model.params.get('Post_x_Feature', np.nan)
        pval = model.pvalues.get('Post_x_Feature', np.nan)
        if np.isfinite(coef) and np.isfinite(pval):
            return {'feature': feature, 'did_estimate': round(float(coef), 4),
                    'p_value': round(float(pval), 4)}
    except:
        pass
    return None

def run_full_causal_analysis(purchases_df, survey_features_df, anomaly_df,
                              baseline_start, baseline_end,
                              treatment_start, treatment_end,
                              n_top=10, n_drivers=3,
                              date_col=None, cat_col=None,
                              id_col=None, spend_col='Total_Spend'):
    """Run full causal analysis for top surge and slump categories.
    
    All period boundaries are required caller parameters.
    Column names are auto-detected if not specified.
    """
    # Auto-detect columns
    if date_col is None:
        date_cols = [c for c in purchases_df.columns if 'date' in c.lower()]
        date_col = date_cols[0] if date_cols else purchases_df.columns[0]
    if cat_col is None:
        cat_cols = [c for c in purchases_df.columns if 'category' in c.lower()]
        cat_col = cat_cols[0] if cat_cols else 'Category'
    if id_col is None:
        id_col = survey_features_df.columns[0]
    
    sorted_anom = anomaly_df.sort_values('Anomaly_Index', ascending=False)
    surge_cats = sorted_anom.head(n_top)[cat_col].tolist()
    slump_cats = sorted_anom.tail(n_top)[cat_col].tolist()
    all_cats = surge_cats + slump_cats
    feature_cols = [c for c in survey_features_df.columns if c != id_col]
    
    print("Preparing intensive margin data...")
    intensive_df = prepare_intensive_margin_data(
        purchases_df, survey_features_df, all_cats,
        baseline_start, baseline_end, treatment_start, treatment_end,
        date_col, cat_col, id_col, spend_col
    )
    print("Preparing extensive margin data...")
    extensive_df = prepare_extensive_margin_data(
        purchases_df, survey_features_df, all_cats,
        baseline_start, baseline_end, treatment_start, treatment_end,
        date_col, cat_col, id_col
    )
    
    def analyze_category_group(categories, is_surge=True):
        results = []
        for cat in categories:
            print(f"  Analyzing category: {cat}")
            cat_anom = anomaly_df[anomaly_df[cat_col] == cat]
            anom_idx = float(cat_anom['Anomaly_Index'].values[0]) if len(cat_anom) > 0 else 0.0
            purch = purchases_df.copy()
            purch[date_col] = pd.to_datetime(purch[date_col])
            cat_purch = purch[purch[cat_col] == cat]
            baseline_purch = cat_purch[(cat_purch[date_col] >= baseline_start) & (cat_purch[date_col] <= baseline_end)]
            treatment_purch = cat_purch[(cat_purch[date_col] >= treatment_start) & (cat_purch[date_col] <= treatment_end)]
            baseline_users = baseline_purch[id_col].unique()
            treatment_users = treatment_purch[id_col].unique()
            baseline_avg = baseline_purch.groupby(id_col)[spend_col].sum().mean() if len(baseline_users) > 0 else 0
            treatment_avg = treatment_purch.groupby(id_col)[spend_col].sum().mean() if len(treatment_users) > 0 else 0
            n_at_risk = len(survey_features_df)
            baseline_rate = len(baseline_users) / n_at_risk if n_at_risk > 0 else 0
            treatment_rate = len(treatment_users) / n_at_risk if n_at_risk > 0 else 0
            
            intensive_results = []
            for feat in feature_cols:
                r = run_univariate_did(intensive_df, survey_features_df, cat, feat, 'Total_Spend', id_col, cat_col)
                if r is not None:
                    r['method'] = 'Univariate DiD'
                    intensive_results.append(r)
            if is_surge:
                intensive_results.sort(key=lambda x: x['did_estimate'], reverse=True)
            else:
                intensive_results.sort(key=lambda x: x['did_estimate'], reverse=False)
            top_intensive = intensive_results[:n_drivers]
            
            extensive_results = []
            for feat in feature_cols:
                r = run_univariate_did(extensive_df, survey_features_df, cat, feat, 'Has_Purchase', id_col, cat_col)
                if r is not None:
                    r['method'] = 'Multivariate Heterogeneous DiD'
                    extensive_results.append(r)
            if is_surge:
                extensive_results.sort(key=lambda x: x['did_estimate'], reverse=True)
            else:
                extensive_results.sort(key=lambda x: x['did_estimate'], reverse=False)
            top_extensive = extensive_results[:n_drivers]
            
            cat_result = {
                'category': cat,
                'anomaly_index': round(anom_idx, 2),
                'baseline_avg_spend': round(float(baseline_avg), 2),
                'treatment_avg_spend': round(float(treatment_avg), 2),
                'n_purchasers_baseline': int(len(baseline_users)),
                'n_purchasers_treatment': int(len(treatment_users)),
                'baseline_purchase_rate': round(float(baseline_rate), 4),
                'treatment_purchase_rate': round(float(treatment_rate), 4),
                'n_at_risk': int(n_at_risk),
                'intensive_margin': top_intensive,
                'extensive_margin': top_extensive
            }
            results.append(cat_result)
        return results
    
    print("\nAnalyzing surge categories...")
    surge_results = analyze_category_group(surge_cats, is_surge=True)
    print("\nAnalyzing slump categories...")
    slump_results = analyze_category_group(slump_cats, is_surge=False)
    
    report = {
        'metadata': {
            'baseline_start': pd.Timestamp(baseline_start).strftime('%m-%d-%Y'),
            'baseline_end': pd.Timestamp(baseline_end).strftime('%m-%d-%Y'),
            'treatment_start': pd.Timestamp(treatment_start).strftime('%m-%d-%Y'),
            'treatment_end': pd.Timestamp(treatment_end).strftime('%m-%d-%Y'),
            'total_features_analyzed': len(feature_cols)
        },
        'surge_categories': surge_results,
        'slump_categories': slump_results,
        'summary': {
            'surge': {
                'total_categories': len(surge_results),
                'total_intensive_drivers': sum(len(r['intensive_margin']) for r in surge_results),
                'total_extensive_drivers': sum(len(r['extensive_margin']) for r in surge_results)
            },
            'slump': {
                'total_categories': len(slump_results),
                'total_intensive_drivers': sum(len(r['intensive_margin']) for r in slump_results),
                'total_extensive_drivers': sum(len(r['extensive_margin']) for r in slump_results)
            }
        }
    }
    return report, intensive_df, extensive_df
