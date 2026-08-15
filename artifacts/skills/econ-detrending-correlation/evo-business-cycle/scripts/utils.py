import numpy as np
import pandas as pd
import xlrd
from scipy.signal import filtfilt


def extract_erp_annual_data(filepath, data_start_row, col_index=1):
    """Extract annual data from an ERP .xls table.
    
    Reads rows starting at data_start_row, extracting year from column 0
    and value from col_index. Stops when a non-annual row is encountered.
    
    Returns a dict {year: value}.
    """
    wb = xlrd.open_workbook(filepath)
    sh = wb.sheet_by_index(0)
    data = {}
    for i in range(data_start_row, sh.nrows):
        label = str(sh.cell_value(i, 0)).strip()
        # Annual rows look like '1973.' or '1992. '
        if label and label.replace('.', '').replace(' ', '').isdigit() and len(label.replace('.', '').replace(' ', '')) == 4:
            year = int(label.replace('.', '').replace(' ', ''))
            val = sh.cell_value(i, col_index)
            if isinstance(val, (int, float)) and val != '':
                data[year] = float(val)
    return data


def extract_erp_quarterly_for_year(filepath, target_year, data_start_row, col_index=1):
    """Extract quarterly data for a specific year from an ERP table.
    
    Looks for rows like '2024: I.' and subsequent '    II.' etc.
    Returns list of quarterly values found.
    """
    wb = xlrd.open_workbook(filepath)
    sh = wb.sheet_by_index(0)
    quarters = []
    in_target_year = False
    
    for i in range(data_start_row, sh.nrows):
        label = str(sh.cell_value(i, 0)).strip()
        val = sh.cell_value(i, col_index)
        
        # Check if this is the start of the target year's quarters
        if f"{target_year}:" in label:
            in_target_year = True
            if isinstance(val, (int, float)) and val != '':
                quarters.append(float(val))
            continue
        
        # If we're in the target year, check for continuation quarters
        if in_target_year:
            # Continuation quarters start with spaces and Roman numerals
            stripped = label.strip()
            if stripped and (stripped.startswith('I') or stripped.startswith('V')):
                if isinstance(val, (int, float)) and val != '':
                    quarters.append(float(val))
            else:
                # Check if it's another year's quarters
                if ':' in label and f"{target_year}" not in label:
                    break
                elif not stripped.startswith('I') and not stripped.startswith('V') and stripped:
                    break
    
    return quarters


def load_cpi(filepath):
    """Load CPI data from xlsx file. Returns dict {year: cpi_value}."""
    df = pd.read_excel(filepath)
    return dict(zip(df['Year'].astype(int), df['CPI_2024'].astype(float)))


def deflate_series(nominal_dict, cpi_dict):
    """Deflate nominal values using CPI. Returns dict {year: real_value}.
    
    real = nominal / cpi
    """
    real = {}
    for year, nom in nominal_dict.items():
        if year in cpi_dict:
            real[year] = nom / cpi_dict[year]
    return real


def hp_filter(series_values, lamb=100):
    """Apply Hodrick-Prescott filter.
    
    Args:
        series_values: numpy array of values (typically log of real series)
        lamb: smoothing parameter (100 for annual data)
    
    Returns:
        (cycle, trend) tuple of numpy arrays
    """
    from statsmodels.tsa.filters.hp_filter import hpfilter
    cycle, trend = hpfilter(series_values, lamb=lamb)
    return cycle, trend


def compute_correlation(series1, series2):
    """Compute Pearson correlation between two arrays."""
    return np.corrcoef(series1, series2)[0, 1]


def run_business_cycle_correlation(
    pce_filepath,
    pfi_filepath,
    cpi_filepath,
    output_filepath,
    start_year=1973,
    end_year=2024,
    hp_lambda=100,
    decimals=5
):
    """End-to-end entry point: extract, deflate, filter, correlate, write result.
    
    Args:
        pce_filepath: path to ERP table with PCE data
        pfi_filepath: path to ERP table with PFI data  
        cpi_filepath: path to CPI xlsx file
        output_filepath: path to write the correlation result
        start_year: first year of sample (inclusive)
        end_year: last year of sample (inclusive)
        hp_lambda: HP filter smoothing parameter
        decimals: number of decimal places for rounding
    """
    # 1. Extract annual data
    # Detect data start rows by scanning for first year
    pce_annual = extract_erp_annual_data(pce_filepath, data_start_row=0, col_index=1)
    pfi_annual = extract_erp_annual_data(pfi_filepath, data_start_row=0, col_index=1)
    
    print(f"PCE annual years: {sorted(pce_annual.keys())}")
    print(f"PFI annual years: {sorted(pfi_annual.keys())}")
    
    # 2. Handle the last year if it's not in annual data (use quarterly average)
    if end_year not in pce_annual:
        pce_quarters = extract_erp_quarterly_for_year(pce_filepath, end_year, data_start_row=0, col_index=1)
        if pce_quarters:
            pce_annual[end_year] = np.mean(pce_quarters)
            print(f"PCE {end_year}: averaged {len(pce_quarters)} quarters = {pce_annual[end_year]:.1f}")
    
    if end_year not in pfi_annual:
        pfi_quarters = extract_erp_quarterly_for_year(pfi_filepath, end_year, data_start_row=0, col_index=1)
        if pfi_quarters:
            pfi_annual[end_year] = np.mean(pfi_quarters)
            print(f"PFI {end_year}: averaged {len(pfi_quarters)} quarters = {pfi_annual[end_year]:.1f}")
    
    # 3. Load CPI and deflate
    cpi = load_cpi(cpi_filepath)
    
    pce_real = deflate_series(pce_annual, cpi)
    pfi_real = deflate_series(pfi_annual, cpi)
    
    # 4. Build aligned series for the requested year range
    years = list(range(start_year, end_year + 1))
    
    # Verify all years present
    missing_pce = [y for y in years if y not in pce_real]
    missing_pfi = [y for y in years if y not in pfi_real]
    if missing_pce:
        raise ValueError(f"Missing PCE data for years: {missing_pce}")
    if missing_pfi:
        raise ValueError(f"Missing PFI data for years: {missing_pfi}")
    
    pce_values = np.array([pce_real[y] for y in years])
    pfi_values = np.array([pfi_real[y] for y in years])
    
    print(f"\nSample: {years[0]}-{years[-1]}, {len(years)} observations")
    print(f"PCE real range: {pce_values[0]:.1f} to {pce_values[-1]:.1f}")
    print(f"PFI real range: {pfi_values[0]:.1f} to {pfi_values[-1]:.1f}")
    
    # 5. Take natural log
    log_pce = np.log(pce_values)
    log_pfi = np.log(pfi_values)
    
    # 6. Apply HP filter
    pce_cycle, pce_trend = hp_filter(log_pce, lamb=hp_lambda)
    pfi_cycle, pfi_trend = hp_filter(log_pfi, lamb=hp_lambda)
    
    print(f"\nPCE cycle std: {np.std(pce_cycle):.6f}")
    print(f"PFI cycle std: {np.std(pfi_cycle):.6f}")
    
    # 7. Compute correlation
    corr = compute_correlation(pce_cycle, pfi_cycle)
    corr_rounded = round(corr, decimals)
    
    print(f"\nCorrelation: {corr}")
    print(f"Rounded to {decimals} places: {corr_rounded}")
    
    # 8. Write result
    with open(output_filepath, 'w') as f:
        f.write(f"{corr_rounded}\n")
    
    print(f"Result written to {output_filepath}")
    return corr_rounded


def validate_result(output_filepath):
    """Validate the output file exists and contains a valid correlation coefficient."""
    with open(output_filepath, 'r') as f:
        content = f.read().strip()
    
    val = float(content)
    assert -1.0 <= val <= 1.0, f"Correlation {val} out of range [-1, 1]"
    
    # Check decimal places
    if '.' in content:
        decimal_part = content.split('.')[1]
        assert len(decimal_part) == 5, f"Expected 5 decimal places, got {len(decimal_part)}"
    
    print(f"Validation passed: {val}")
    return val
