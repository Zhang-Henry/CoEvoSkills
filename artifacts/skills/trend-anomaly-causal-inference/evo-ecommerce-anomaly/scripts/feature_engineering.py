import pandas as pd
import numpy as np
import re

def _infer_ordinal_order(values, col_name):
    """Infer ordinal ordering from categorical values at runtime.
    Handles age ranges, income ranges, education levels, frequency scales,
    and household/user count scales.
    Returns dict mapping value -> ordinal int, or None if not ordinal.
    """
    unique_vals = [v for v in values.dropna().unique() if isinstance(v, str)]
    if len(unique_vals) < 2:
        return None
    
    col_lower = col_name.lower()
    
    # Age ranges: extract lower bound number
    if 'age' in col_lower:
        def age_key(v):
            nums = re.findall(r'\d+', str(v))
            return int(nums[0]) if nums else 999
        sorted_vals = sorted(unique_vals, key=age_key)
        return {v: i+1 for i, v in enumerate(sorted_vals)}
    
    # Income ranges: extract dollar amounts
    if 'income' in col_lower:
        def income_key(v):
            v_str = str(v).replace(',', '')
            nums = re.findall(r'\d+', v_str)
            if 'less' in v_str.lower():
                return 0
            if 'more' in v_str.lower() or 'or more' in v_str.lower():
                return 999999
            if 'prefer' in v_str.lower():
                return -1  # will be mapped to NaN
            return int(nums[0]) if nums else 500000
        sorted_vals = sorted(unique_vals, key=income_key)
        result = {}
        rank = 1
        for v in sorted_vals:
            if 'prefer' in str(v).lower():
                result[v] = None  # NaN marker
            else:
                result[v] = rank
                rank += 1
        return result
    
    # Education: order by typical progression
    if 'education' in col_lower or 'edu' in col_lower:
        edu_keywords_order = [
            ('some high school', 'less than high'),
            ('high school', 'ged'),
            ('associate', 'some college'),
            ('bachelor',),
            ('graduate', 'professional', 'master', 'phd', 'doctor', 'mba'),
        ]
        def edu_key(v):
            v_lower = str(v).lower()
            if 'prefer' in v_lower:
                return -1
            for idx, keywords in enumerate(edu_keywords_order):
                if any(kw in v_lower for kw in keywords):
                    return idx
            return len(edu_keywords_order)
        sorted_vals = sorted(unique_vals, key=edu_key)
        result = {}
        rank = 1
        for v in sorted_vals:
            if 'prefer' in str(v).lower():
                result[v] = None
            else:
                result[v] = rank
                rank += 1
        return result
    
    # Frequency/count scales: extract numbers or keywords
    if any(kw in col_lower for kw in ['how', 'freq', 'oft', 'many', 'size']):
        def count_key(v):
            v_str = str(v)
            if 'just me' in v_str.lower() or v_str == '1':
                return 1
            if 'less' in v_str.lower():
                return 0
            if 'more' in v_str.lower():
                return 999
            nums = re.findall(r'\d+', v_str)
            if nums:
                return int(nums[0])
            return 500
        sorted_vals = sorted(unique_vals, key=count_key)
        return {v: i+1 for i, v in enumerate(sorted_vals)}
    
    return None


def engineer_survey_features(survey_clean_df):
    """Engineer features from cleaned survey data.
    Discovers column types and categories at runtime.
    All output columns are numeric (int/float) except the ID column.
    """
    df = survey_clean_df.copy()
    id_col = df.columns[0]  # First column is ID
    result = pd.DataFrame()
    result[id_col] = df[id_col]
    
    for col in df.columns:
        if col == id_col:
            continue
        
        unique_vals = df[col].dropna().unique()
        n_unique = len(unique_vals)
        col_lower = col.lower()
        
        # Skip if only one unique value
        if n_unique < 2:
            continue
        
        # Check for binary yes/no columns
        val_set_lower = set(str(v).lower().strip() for v in unique_vals)
        
        # Try ordinal encoding
        ordinal_map = _infer_ordinal_order(df[col], col)
        if ordinal_map is not None:
            clean_name = col.split('-')[-1] if '-' in col else col
            clean_name = clean_name.strip().replace(' ', '_').replace('-', '_')
            ord_col_name = f"{clean_name}_ordinal"
            mapped = df[col].map(ordinal_map).astype(float)
            mapped = mapped.fillna(mapped.median())
            result[ord_col_name] = mapped
        
        # Binary indicators for specific values
        if n_unique <= 10:
            # Check for yes/no type columns
            for val in unique_vals:
                val_str = str(val).strip()
                val_lower = val_str.lower()
                if val_lower == 'yes':
                    indicator_name = f"{col.split('Q-')[-1] if 'Q-' in col else col}"
                    indicator_name = 'uses_' + indicator_name.split('-')[-1] if 'substance' in col_lower else \
                                    'has_' + indicator_name.split('-')[-1] if 'personal' in col_lower else \
                                    'is_' + indicator_name.split('-')[-1]
                    indicator_name = indicator_name.replace(' ', '_').replace('-', '_')
                    result[indicator_name] = (df[col] == val).astype(int)
                elif 'stopped' in val_lower or 'recent past' in val_lower:
                    indicator_name = f"stopped_{col.split('-')[-1]}"
                    indicator_name = indicator_name.replace(' ', '_').replace('-', '_')
                    result[indicator_name] = (df[col] == val).astype(int)
        
        # Check for specific demographic indicators
        if 'hispanic' in col_lower:
            result['is_hispanic'] = (df[col] == 'Yes').astype(int)
        
        if 'gender' in col_lower:
            for val in unique_vals:
                if str(val).lower() == 'female':
                    result['is_female'] = (df[col] == val).astype(int)
                elif str(val).lower() == 'male':
                    result['is_male'] = (df[col] == val).astype(int)
        
        if 'orientation' in col_lower or 'sexual' in col_lower:
            for val in unique_vals:
                if 'lgbtq' in str(val).lower():
                    result['is_lgbtq'] = (df[col] == val).astype(int)
        
        # Multi-select race column: extract individual indicators
        if 'race' in col_lower:
            # Find all individual race values by splitting on commas
            all_races = set()
            for v in unique_vals:
                for race in str(v).split(','):
                    race = race.strip()
                    if race:
                        all_races.add(race)
            for race in sorted(all_races):
                race_col = 'race_' + race.lower().replace(' ', '_').replace('/', '_')[:30]
                result[race_col] = df[col].str.contains(race, na=False, regex=False).astype(int)
            result['race_multiracial'] = df[col].str.contains(',', na=False).astype(int)
            continue  # Skip dummies for race
        
        # One-hot encode categorical columns
        if n_unique <= 60 and df[col].dtype == 'object':
            prefix = col.split('Q-')[-1] if 'Q-' in col else col
            prefix = prefix.split('-')[-1] if '-' in prefix else prefix
            prefix = prefix.strip().replace(' ', '_')[:15]
            dummies = pd.get_dummies(df[col], prefix=prefix, dtype=int)
            # Clean dummy column names
            dummies.columns = [c.replace(' ', '_').replace(',', '').replace('(', '').replace(')', '').replace("'", '').replace('/', '_') for c in dummies.columns]
            result = pd.concat([result, dummies], axis=1)
    
    # Ensure no duplicate columns
    result = result.loc[:, ~result.columns.duplicated()]
    
    return result
