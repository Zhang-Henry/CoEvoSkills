import pandas as pd
import numpy as np

def clean_survey(input_path):
    """Clean survey data: fix dirty values, handle nulls, remove duplicates.
    Discovers valid categorical values at runtime from data distributions.
    """
    df = pd.read_csv(input_path)
    
    # Remove duplicate respondent IDs (keep first)
    id_col = df.columns[0]  # First column is the respondent ID
    df = df.drop_duplicates(subset=id_col, keep='first')
    
    # Strip whitespace from string columns
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].str.strip()
    
    # Detect and fix columns with numeric outlier values mixed into categorical data
    # Strategy: for each categorical column, if a value looks purely numeric and
    # falls outside the expected range of ordinal categories, treat it as dirty
    for col in df.select_dtypes(include='object').columns:
        if col == id_col:
            continue
        vals = df[col].dropna().unique()
        # Check if column has a mix of text and pure numeric values
        text_vals = [v for v in vals if not str(v).replace('.','').replace('-','').isdigit()]
        numeric_vals = [v for v in vals if str(v).replace('.','').replace('-','').isdigit()]
        # If most values are text but some are numeric, the numeric ones are likely dirty
        if len(text_vals) > 0 and len(numeric_vals) > 0:
            numeric_as_int = []
            for v in numeric_vals:
                try:
                    numeric_as_int.append(int(float(v)))
                except:
                    pass
            # If numeric values are outside a small ordinal range (e.g., > 10),
            # they are likely erroneous entries
            if numeric_as_int and max(numeric_as_int) > 10:
                df.loc[df[col].isin([str(v) for v in numeric_vals]), col] = np.nan
    
    # Fill nulls with mode for each column
    for col in df.columns:
        if col == id_col:
            continue
        null_count = df[col].isnull().sum()
        if null_count > 0:
            mode_val = df[col].mode()
            if len(mode_val) > 0:
                df[col] = df[col].fillna(mode_val[0])
    
    return df


def clean_purchases(input_path):
    """Clean purchase data: parse dates, handle nulls, remove duplicates."""
    df = pd.read_csv(input_path, low_memory=False)
    
    # Remove exact duplicate rows
    df = df.drop_duplicates(keep='first')
    
    # Identify date column (first column or column containing 'date')
    date_col = [c for c in df.columns if 'date' in c.lower()]
    date_col = date_col[0] if date_col else df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df = df.dropna(subset=[date_col])
    
    # Identify category column
    cat_col = [c for c in df.columns if 'category' in c.lower()]
    if cat_col:
        df = df.dropna(subset=[cat_col[0]])
    
    # Strip whitespace from string columns
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].str.strip()
    
    # Identify quantity and price columns
    qty_col = [c for c in df.columns if 'quantity' in c.lower()]
    price_col = [c for c in df.columns if 'price' in c.lower()]
    
    if qty_col:
        df = df[df[qty_col[0]] >= 1]
    if price_col:
        df = df[df[price_col[0]] > 0]
    
    # Calculate total spend
    if qty_col and price_col:
        df['Total_Spend'] = df[price_col[0]] * df[qty_col[0]]
    
    return df
