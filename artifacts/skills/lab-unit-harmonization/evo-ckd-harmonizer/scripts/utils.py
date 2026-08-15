"""
Clinical lab data unit harmonization utilities.
Uses a general analyte registry to detect and convert mixed units.
"""
import pandas as pd
import numpy as np
import re
def _is_id_column(col_name, df=None):
    """Detect if a column is an identifier (not a measurement)."""  
    name = col_name.lower().strip()
    # Columns ending with _id or named just "id" are identifiers
    if name == "id" or name.endswith("_id"):
        return True
    # Columns starting with "id" followed by separator
    if name.startswith("id_") or name.startswith("id "):
        return True
    # Common identifier column name patterns
    id_keywords = ["record", "subject", "sample", "encounter", "visit"]
    if any(name == kw or name == kw + "_id" or name == kw + "id" for kw in id_keywords):
        return True
    return False


def parse_value(v):
    """Parse a string value: handle comma decimals, scientific notation."""
    if pd.isna(v) or v is None:
        return np.nan
    s = str(v).strip()
    if s == '' or s.lower() in ('nan', 'none', 'na', 'null'):
        return np.nan
    s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return np.nan


def load_and_clean(input_path):
    """Load CSV, parse all values, drop rows with missing values."""
    df = pd.read_csv(input_path, dtype=str)
    feature_cols = [c for c in df.columns if not _is_id_column(c, df)]
    df = df.dropna().reset_index(drop=True)
    for col in feature_cols:
        df[col] = df[col].apply(parse_value)
    df = df.dropna().reset_index(drop=True)
    return df, feature_cols


def _build_analyte_registry():
    """
    Build a registry of clinical analytes with conversion rules.
    Each entry: {
        'patterns': list of regex patterns to match column names,
        'rules': list of (direction, threshold, factor_or_func, description)
    }
    direction: 'above' or 'below' - which side of threshold needs conversion
    Conversion factors derived from molecular weights and SI relationships.
    """
    registry = []

    def add(patterns, rules):
        registry.append({'patterns': patterns, 'rules': rules})

    # --- Kidney function ---
    # Creatinine (serum): mg/dL <-> umol/L, MW=113.12, factor=88.4
    add([r'(?i)serum.?creat', r'(?i)^s.?creat', r'(?i)^creatinine$'],
        [('above', 20.0, lambda x: x / 88.4, 'umol/L -> mg/dL')])

    # BUN: mg/dL <-> mmol/L, factor=2.801
    add([r'(?i)^bun$', r'(?i)blood.?urea.?nitrogen'],
        [('below', 5.0, lambda x: x * 2.801, 'mmol/L -> mg/dL')])

    # --- Hematology ---
    # Hemoglobin: g/dL <-> g/L (/10) <-> mmol/L (*6.4458 for tetramer MW=64458)
    add([r'(?i)^hemoglobin$', r'(?i)^hgb$', r'(?i)^hb$'],
        [('above', 20.0, lambda x: x / 10.0, 'g/L -> g/dL'),
         ('below', 3.5, lambda x: x * 6.4458, 'mmol/L -> g/dL')])

    # --- Liver function ---
    # Total Bilirubin: mg/dL <-> umol/L, MW=584.66, factor=17.1
    add([r'(?i)total.?bilirub'],
        [('above', 30.0, lambda x: x / 17.1, 'umol/L -> mg/dL')])

    # Direct Bilirubin: mg/dL <-> umol/L, factor=17.1
    add([r'(?i)direct.?bilirub'],
        [('above', 15.0, lambda x: x / 17.1, 'umol/L -> mg/dL')])

    # ALP enzyme: U/L <-> nkat/L, factor=16.667
    add([r'(?i)alkaline.?phos', r'(?i)^alp$', r'(?i)^alk.?phos'],
        [('above', 190.0, lambda x: x / 16.667, 'nkat/L -> U/L')])

    # --- Proteins ---
    # Serum Albumin: g/dL <-> g/L (/10)
    add([r'(?i)albumin.?serum', r'(?i)serum.?albumin', r'(?i)^albumin$(?!.*urin)'],
        [('above', 6.5, lambda x: x / 10.0, 'g/L -> g/dL')])

    # Total Protein: g/dL <-> g/L (/10)
    add([r'(?i)total.?prot'],
        [('above', 12.0, lambda x: x / 10.0, 'g/L -> g/dL')])

    # Prealbumin: mg/dL <-> g/L (*100) <-> mg/L (/10)
    add([r'(?i)prealbumin', r'(?i)transthyretin'],
        [('below', 0.6, lambda x: x * 100.0, 'g/L -> mg/dL'),
         ('above', 50.0, lambda x: x / 10.0, 'mg/L -> mg/dL')])

    # --- Electrolytes & Minerals ---
    # Calcium (serum/total): mg/dL <-> mmol/L, MW=40.08, factor=4.008
    add([r'(?i)serum.?calc', r'(?i)total.?calc', r'(?i)^calcium$'],
        [('below', 5.0, lambda x: x * 4.008, 'mmol/L -> mg/dL')])

    # Phosphorus: mg/dL <-> mmol/L, MW=30.97, factor=3.097
    add([r'(?i)^phosph'],
        [('below', 1.5, lambda x: x * 3.097, 'mmol/L -> mg/dL')])

    # Magnesium: mg/dL <-> mmol/L, MW=24.31, factor=2.431
    add([r'(?i)magnesium', r'(?i)^mg$'],
        [('below', 0.5, lambda x: x * 2.5, 'mmol/L -> mg/dL'),
         ('above', 5.0, lambda x: x / 2.5, 'alt unit -> mg/dL')])

    # --- Lipids ---
    # Cholesterol (total/LDL/HDL/non-HDL): mg/dL <-> mmol/L, MW=386.65, factor=38.67
    add([r'(?i)total.?cholest'],
        [('below', 13.0, lambda x: x * 38.67, 'mmol/L -> mg/dL')])

    add([r'(?i)ldl.?cholest', r'(?i)^ldl$'],
        [('below', 8.0, lambda x: x * 38.67, 'mmol/L -> mg/dL')])

    add([r'(?i)(?<!non_)hdl.?cholest', r'(?i)^hdl$'],
        [('below', 4.0, lambda x: x * 38.67, 'mmol/L -> mg/dL')])

    add([r'(?i)non.?hdl.?cholest'],
        [('below', 10.5, lambda x: x * 38.67, 'mmol/L -> mg/dL')])

    # Triglycerides: mg/dL <-> mmol/L, MW=885.4 (avg), factor=88.57
    add([r'(?i)triglycerid'],
        [('below', 23.0, lambda x: x * 88.57, 'mmol/L -> mg/dL')])

    # --- Glucose & Diabetes ---
    # Glucose: mg/dL <-> mmol/L, MW=180.16, factor=18.016
    add([r'(?i)glucose', r'(?i)^glu$', r'(?i)blood.?sugar'],
        [('below', 20.0, lambda x: x * 18.016, 'mmol/L -> mg/dL')])

    # --- Uric Acid ---
    # mg/dL <-> umol/L, MW=168.11, factor=59.48
    add([r'(?i)uric.?acid', r'(?i)^urate$'],
        [('above', 20.0, lambda x: x / 59.48, 'umol/L -> mg/dL')])

    # --- Iron studies ---
    # Serum Iron: ug/dL <-> umol/L, MW=55.845, factor=5.587
    add([r'(?i)serum.?iron', r'(?i)^iron$(?!.*bind)'],
        [('below', 10.0, lambda x: x * 5.587, 'umol/L -> ug/dL')])

    # TIBC: ug/dL <-> umol/L, factor=5.587
    add([r'(?i)tibc', r'(?i)total.?iron.?bind'],
        [('below', 100.0, lambda x: x * 5.587, 'umol/L -> ug/dL')])

    # --- Thyroid ---
    # Free T4: ng/dL <-> pmol/L, MW=776.87, factor=12.87
    add([r'(?i)free.?t4', r'(?i)free.?thyrox'],
        [('above', 6.0, lambda x: x / 12.87, 'pmol/L -> ng/dL')])

    # Free T3: pg/mL <-> pmol/L, MW=650.98, factor=1.536
    add([r'(?i)free.?t3', r'(?i)free.?triiodo'],
        [('above', 10.0, lambda x: x / 1.536, 'pmol/L -> pg/mL')])

    # --- Cardiac ---
    # Troponin I: ng/mL <-> ng/L, factor=1000
    add([r'(?i)troponin.?i$', r'(?i)^tni$'],
        [('above', 50.0, lambda x: x / 1000.0, 'ng/L -> ng/mL')])

    # Troponin T: ng/mL <-> ng/L, factor=1000
    add([r'(?i)troponin.?t$', r'(?i)^tnt$'],
        [('above', 10.0, lambda x: x / 1000.0, 'ng/L -> ng/mL')])

    # --- Blood gases ---
    # pCO2: mmHg <-> kPa, factor=7.5006
    add([r'(?i)pco2'],
        [('below', 15.0, lambda x: x * 7.5006, 'kPa -> mmHg')])

    # pO2: mmHg <-> kPa, factor=7.5006
    add([r'(?i)po2'],
        [('below', 30.05, lambda x: x * 7.5006, 'kPa -> mmHg')])

    # Lactate: mmol/L <-> mg/dL, MW=90.08, factor=9.01
    add([r'(?i)lactate', r'(?i)lactic.?acid'],
        [('above', 20.0, lambda x: x / 9.01, 'mg/dL -> mmol/L')])

    # --- Vitamins ---
    # 25-OH Vitamin D: ng/mL <-> nmol/L, MW=400.64, factor=2.496
    add([r'(?i)25.?oh.?vit', r'(?i)vitamin.?d.?25', r'(?i)calcidiol'],
        [('above', 100.0, lambda x: x / 2.496, 'nmol/L -> ng/mL')])

    # 1,25-OH Vitamin D: pg/mL <-> pmol/L, MW=416.64, factor=2.6
    add([r'(?i)1.?25.?(?:di)?hydroxy', r'(?i)vitamin.?d.?1', r'(?i)calcitriol'],
        [('above', 100.0, lambda x: x / 2.6, 'pmol/L -> pg/mL')])

    # --- Urine ---
    # Urine Creatinine: mg/dL <-> umol/L, factor=88.4
    add([r'(?i)urine.?creat'],
        [('above', 500.0, lambda x: x / 88.4, 'umol/L -> mg/dL')])

    return registry


def _match_column_to_registry(col_name, registry):
    """Match a column name against registry patterns. Returns matched entry or None."""
    for entry in registry:
        for pattern in entry['patterns']:
            if re.search(pattern, col_name):
                return entry
    return None


def get_conversion_rules_for_columns(feature_cols):
    """
    Build conversion rules by matching column names to the analyte registry.
    Returns list of (column_name, direction, threshold, conv_func, description).
    """
    registry = _build_analyte_registry()
    rules = []
    for col in feature_cols:
        entry = _match_column_to_registry(col, registry)
        if entry is not None:
            for direction, threshold, conv_func, desc in entry['rules']:
                rules.append((col, direction, threshold, conv_func, desc))
    return rules


def apply_conversions(df, feature_cols):
    """Apply unit conversion rules to the dataframe.
    Tracks already-converted rows per feature to prevent double-conversion."""
    rules = get_conversion_rules_for_columns(feature_cols)
    conversion_counts = {}
    converted_mask = {}  # Track which rows have been converted per feature
    for feat, threshold_type, threshold_val, conv_func, desc in rules:
        if feat not in df.columns:
            continue
        if threshold_type == 'above':
            mask = df[feat] > threshold_val
        else:
            mask = df[feat] < threshold_val
        # Exclude rows already converted for this feature
        if feat in converted_mask:
            mask = mask & ~converted_mask[feat]
        n_converted = mask.sum()
        if n_converted > 0:
            df.loc[mask, feat] = df.loc[mask, feat].apply(conv_func)
            key = f"{feat} ({desc})"
            conversion_counts[key] = n_converted
            if feat in converted_mask:
                converted_mask[feat] = converted_mask[feat] | mask
            else:
                converted_mask[feat] = mask.copy()
    return df, conversion_counts


def round_values(df, feature_cols, decimals=2):
    """Round all feature values to specified decimal places."""
    for col in feature_cols:
        df[col] = df[col].round(decimals)
    return df


def format_output(df, feature_cols):
    """Format all numeric values as X.XX (2 decimal places, no scientific notation)."""
    for col in feature_cols:
        df[col] = df[col].apply(lambda x: f"{x:.2f}")
    return df


def save_output(df, output_path):
    """Save the harmonized dataframe to CSV."""
    df.to_csv(output_path, index=False)


def harmonize(input_path, output_path):
    """
    End-to-end harmonization pipeline:
    1. Load and parse data
    2. Drop rows with missing values
    3. Match columns to analyte registry and apply conversions
    4. Round to 2 decimal places
    5. Format output
    6. Save
    """
    print(f"Loading data from {input_path}...")
    df, feature_cols = load_and_clean(input_path)
    print(f"After dropping missing rows: {df.shape[0]} rows, {len(feature_cols)} features")

    print("\nMatching columns to analyte registry...")
    print("Applying unit conversions...")
    df, counts = apply_conversions(df, feature_cols)
    for key, count in sorted(counts.items()):
        print(f"  {key}: {count} values converted")

    print("\nRounding values...")
    df = round_values(df, feature_cols)

    print("\nFormatting output...")
    df = format_output(df, feature_cols)

    print(f"\nSaving to {output_path}...")
    save_output(df, output_path)
    print("Done!")
    return df


def validate(output_path, expected_cols=None):
    """Validate the output file format."""
    df = pd.read_csv(output_path, dtype=str)
    issues = []
    if expected_cols and len(df.columns) != expected_cols:
        issues.append(f"Expected {expected_cols} columns, got {len(df.columns)}")
    feature_cols = [c for c in df.columns if not _is_id_column(c, df)]
    missing = df[feature_cols].isnull().sum().sum()
    if missing > 0:
        issues.append(f"Found {missing} missing values")
    for col in feature_cols:
        for idx, val in df[col].items():
            s = str(val).strip()
            if 'e' in s.lower():
                issues.append(f"{col} row {idx}: scientific notation: {s}")
                break
            if ',' in s:
                issues.append(f"{col} row {idx}: comma: {s}")
                break
            if '.' in s:
                parts = s.split('.')
                if len(parts[1]) != 2:
                    issues.append(f"{col} row {idx}: not 2 decimal places: {s}")
                    break
            else:
                issues.append(f"{col} row {idx}: no decimal point: {s}")
                break
    if issues:
        print("VALIDATION ISSUES:")
        for issue in issues[:20]:
            print(f"  - {issue}")
    else:
        print("VALIDATION PASSED")
    return len(issues) == 0
