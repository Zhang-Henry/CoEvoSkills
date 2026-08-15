import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

def compute_daily_category_sales(purchases_df, date_col, cat_col, spend_col):
    """Compute daily total sales per category."""
    df = purchases_df.copy()
    df['date'] = df[date_col].dt.date
    daily = df.groupby([cat_col, 'date']).agg(
        daily_sales=(spend_col, 'sum')
    ).reset_index()
    daily['date'] = pd.to_datetime(daily['date'])
    return daily

def compute_anomaly_index(purchases_df, treatment_start, treatment_end=None,
                          train_end=None, date_col=None, cat_col=None,
                          spend_col='Total_Spend'):
    """Compute anomaly index for all categories using counterfactual prediction.
    
    Parameters:
        purchases_df: DataFrame with purchase data including a date, category, and spend column
        treatment_start: Start of treatment/event period (required, str or Timestamp)
        treatment_end: End of treatment period. If None, end of treatment_start's month.
        train_end: End of training period. If None, day before treatment_start.
        date_col: Name of date column. If None, auto-detected.
        cat_col: Name of category column. If None, auto-detected.
        spend_col: Name of spend column.
    
    Returns DataFrame with cat_col and Anomaly_Index columns.
    Index ranges from -100 (extreme slump) to 100 (extreme surge).
    """
    # Auto-detect columns if not specified
    if date_col is None:
        date_cols = [c for c in purchases_df.columns if 'date' in c.lower()]
        date_col = date_cols[0] if date_cols else purchases_df.columns[0]
    if cat_col is None:
        cat_cols = [c for c in purchases_df.columns if 'category' in c.lower()]
        cat_col = cat_cols[0] if cat_cols else purchases_df.columns[1]
    
    # Derive treatment_end and train_end from treatment_start if not given
    ts = pd.Timestamp(treatment_start)
    if treatment_end is None:
        treatment_end = (ts + pd.offsets.MonthEnd(0)).strftime('%Y-%m-%d')
    if train_end is None:
        train_end = (ts - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    
    daily = compute_daily_category_sales(purchases_df, date_col, cat_col, spend_col)
    categories = daily[cat_col].unique()
    
    train_end_dt = pd.Timestamp(train_end)
    forecast_start_dt = pd.Timestamp(treatment_start)
    forecast_end_dt = pd.Timestamp(treatment_end)
    
    results = []
    for i, cat in enumerate(categories):
        if (i + 1) % 50 == 0:
            print(f"  Processing category {i+1}/{len(categories)}")
        
        cat_data = daily[daily[cat_col] == cat][['date', 'daily_sales']].copy()
        if len(cat_data) == 0:
            continue
        
        # Fill in zeros for missing dates
        min_date = cat_data['date'].min()
        max_date = max(cat_data['date'].max(), forecast_end_dt)
        full_range = pd.date_range(min_date, max_date, freq='D')
        cat_full = cat_data.set_index('date')['daily_sales'].reindex(full_range, fill_value=0).reset_index()
        cat_full.columns = ['date', 'daily_sales']
        
        train = cat_full[cat_full['date'] <= train_end_dt].copy()
        test = cat_full[(cat_full['date'] >= forecast_start_dt) & (cat_full['date'] <= forecast_end_dt)].copy()
        
        if len(train) < 30:
            continue
        
        # Counterfactual: day-of-week averages from recent period with trend adjustment
        train['dow'] = train['date'].dt.dayofweek
        recent_cutoff = train_end_dt - pd.Timedelta(days=90)
        recent_train = train[train['date'] >= recent_cutoff]
        if len(recent_train) < 14:
            recent_train = train
        
        dow_avg = recent_train.groupby('dow')['daily_sales'].mean()
        overall_avg = recent_train['daily_sales'].mean()
        
        # Simple linear trend on monthly averages
        train_copy = train.copy()
        train_copy['month_idx'] = train_copy['date'].dt.year * 12 + train_copy['date'].dt.month
        monthly = train_copy.groupby('month_idx')['daily_sales'].mean().reset_index()
        
        if len(monthly) >= 3:
            x = np.arange(len(monthly), dtype=float)
            y = monthly['daily_sales'].values.astype(float)
            slope, intercept = np.polyfit(x, y, 1)
            trend_factor = 1 + slope / (intercept + 1e-10) if abs(intercept) > 1e-10 else 1.0
            trend_factor = np.clip(trend_factor, 0.5, 2.0)
        else:
            trend_factor = 1.0
        
        test = test.copy()
        test['dow'] = test['date'].dt.dayofweek
        test['predicted'] = test['dow'].map(dow_avg).fillna(overall_avg) * trend_factor
        test['predicted'] = test['predicted'].clip(lower=0)
        
        actual_total = test['daily_sales'].sum()
        predicted_total = test['predicted'].sum()
        
        results.append({
            cat_col: cat,
            'actual_total': actual_total,
            'predicted_total': predicted_total,
            'residual': actual_total - predicted_total
        })
    
    results_df = pd.DataFrame(results)
    if len(results_df) == 0:
        return pd.DataFrame(columns=[cat_col, 'Anomaly_Index'])
    
    results_df['deviation_ratio'] = np.where(
        results_df['predicted_total'] > 0,
        (results_df['actual_total'] - results_df['predicted_total']) / results_df['predicted_total'],
        np.where(results_df['actual_total'] > 0, 1.0, 0.0)
    )
    
    max_abs = results_df['deviation_ratio'].abs().max()
    if max_abs > 0:
        results_df['Anomaly_Index'] = (results_df['deviation_ratio'] / max_abs * 100).clip(-100, 100)
    else:
        results_df['Anomaly_Index'] = 0.0
    results_df['Anomaly_Index'] = results_df['Anomaly_Index'].round(2)
    
    return results_df[[cat_col, 'Anomaly_Index']].sort_values('Anomaly_Index', ascending=False).reset_index(drop=True)
