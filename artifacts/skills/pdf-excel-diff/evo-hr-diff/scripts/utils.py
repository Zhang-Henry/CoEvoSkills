import pdfplumber
import pandas as pd
import numpy as np
import json

def extract_pdf_table(pdf_path):
    """Extract all rows from a multi-page PDF table, handling repeated headers."""
    all_rows = []
    headers = None
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            table = page.extract_table()
            if table is None or len(table) == 0:
                continue
            
            if headers is None:
                headers = table[0]
                data_rows = table[1:]
            else:
                # Check if first row is repeated header
                if table[0] == headers:
                    data_rows = table[1:]
                else:
                    data_rows = table
            
            for row in data_rows:
                if row and len(row) == len(headers):
                    all_rows.append(row)
    
    df = pd.DataFrame(all_rows, columns=headers)
    return df


def clean_pdf_dataframe(df):
    """Clean PDF-extracted data: strip whitespace, convert numeric fields."""
    # Strip whitespace from all string columns
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    
    # Remove commas from numeric fields and convert
    numeric_int_fields = ['Salary', 'Years']
    for field in numeric_int_fields:
        if field in df.columns:
            df[field] = df[field].str.replace(',', '', regex=False).astype(int)
    
    numeric_float_fields = ['Score']
    for field in numeric_float_fields:
        if field in df.columns:
            df[field] = df[field].astype(float)
    
    return df


def load_excel_data(excel_path):
    """Load Excel file and ensure proper types."""
    df = pd.read_excel(excel_path)
    
    # Strip whitespace from string columns
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip()
    
    # Ensure integer types for known int fields
    for field in ['Salary', 'Years']:
        if field in df.columns:
            df[field] = df[field].astype(int)
    
    # Ensure float for Score
    if 'Score' in df.columns:
        df['Score'] = df['Score'].astype(float)
    
    return df


def to_native(val):
    """Convert numpy types to native Python types."""
    if isinstance(val, (np.integer,)):
        return int(val)
    elif isinstance(val, (np.floating,)):
        return float(val)
    elif isinstance(val, (np.bool_,)):
        return bool(val)
    elif isinstance(val, (np.str_,)):
        return str(val)
    return val


def is_numeric(val):
    """Check if a value is numeric (including numpy types)."""
    return isinstance(val, (int, float, np.integer, np.floating))


def compare_datasets(old_df, new_df, id_col='ID'):
    """Compare old and new datasets, returning deleted IDs and modifications."""
    old_ids = set(old_df[id_col])
    new_ids = set(new_df[id_col])
    
    # Deleted employees
    deleted_ids = sorted(old_ids - new_ids)
    
    # Modified employees
    common_ids = old_ids & new_ids
    
    old_indexed = old_df.set_index(id_col)
    new_indexed = new_df.set_index(id_col)
    
    modifications = []
    
    # Determine which columns are numeric vs text
    numeric_int_cols = {'Salary', 'Years'}
    numeric_float_cols = {'Score'}
    
    # Get non-ID columns to compare
    compare_cols = [c for c in old_df.columns if c != id_col]
    
    for emp_id in sorted(common_ids):
        old_row = old_indexed.loc[emp_id]
        new_row = new_indexed.loc[emp_id]
        
        for col in compare_cols:
            old_val = old_row[col]
            new_val = new_row[col]
            
            # Convert to native Python types
            old_native = to_native(old_val)
            new_native = to_native(new_val)
            
            if col in numeric_int_cols:
                old_native = int(old_native)
                new_native = int(new_native)
                if old_native != new_native:
                    modifications.append({
                        'id': emp_id,
                        'field': col,
                        'old_value': old_native,
                        'new_value': new_native
                    })
            elif col in numeric_float_cols:
                old_native = float(old_native)
                new_native = float(new_native)
                if old_native != new_native:
                    # Output as int if whole number
                    old_out = int(old_native) if old_native == int(old_native) else old_native
                    new_out = int(new_native) if new_native == int(new_native) else new_native
                    modifications.append({
                        'id': emp_id,
                        'field': col,
                        'old_value': old_out,
                        'new_value': new_out
                    })
            else:
                # Text comparison
                old_str = str(old_native).strip()
                new_str = str(new_native).strip()
                if old_str != new_str:
                    modifications.append({
                        'id': emp_id,
                        'field': col,
                        'old_value': old_str,
                        'new_value': new_str
                    })
    
    return deleted_ids, modifications


def generate_diff_report(pdf_path, excel_path, output_path):
    """End-to-end: extract PDF, load Excel, compare, write JSON report."""
    # Extract and clean PDF data
    pdf_df = extract_pdf_table(pdf_path)
    pdf_df = clean_pdf_dataframe(pdf_df)
    
    # Load Excel data
    excel_df = load_excel_data(excel_path)
    
    # Compare (PDF is old, Excel is new)
    deleted_ids, modifications = compare_datasets(pdf_df, excel_df)
    
    # Build report
    report = {
        'deleted_employees': deleted_ids,
        'modified_employees': modifications
    }
    
    # Write JSON
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report


def validate_report(output_path):
    """Validate the generated report."""
    with open(output_path, 'r') as f:
        report = json.load(f)
    
    assert 'deleted_employees' in report, 'Missing deleted_employees'
    assert 'modified_employees' in report, 'Missing modified_employees'
    
    # Check deleted_employees is sorted
    deleted = report['deleted_employees']
    assert deleted == sorted(deleted), 'deleted_employees not sorted'
    
    # Check all IDs have correct format
    for emp_id in deleted:
        assert emp_id.startswith('EMP') and len(emp_id) == 8, f'Invalid ID format: {emp_id}'
    
    # Check modified_employees
    mods = report['modified_employees']
    if mods:
        mod_ids = [m['id'] for m in mods]
        assert mod_ids == sorted(mod_ids), 'modified_employees not sorted by ID'
        
        for m in mods:
            assert 'id' in m and 'field' in m and 'old_value' in m and 'new_value' in m, \
                f'Missing fields in modification: {m}'
            assert m['id'].startswith('EMP') and len(m['id']) == 8, f'Invalid ID: {m["id"]}'
            
            # Check numeric fields are numbers
            if m['field'] in ['Salary', 'Years', 'Score']:
                assert isinstance(m['old_value'], (int, float)), \
                    f"old_value for {m['field']} should be numeric, got {type(m['old_value'])}: {m['old_value']}"
                assert isinstance(m['new_value'], (int, float)), \
                    f"new_value for {m['field']} should be numeric, got {type(m['new_value'])}: {m['new_value']}"
    
    print(f'Validation passed: {len(deleted)} deleted, {len(mods)} modified')
    return True
