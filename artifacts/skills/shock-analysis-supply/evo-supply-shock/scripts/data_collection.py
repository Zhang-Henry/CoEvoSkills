"""Data collection functions for supply-side shock analysis."""
import subprocess
import json
import csv
import io
import os

def collect_pwt_data():
    """Download and extract PWT data for Georgia (rnna - capital stock at constant national prices).
    Returns dict {year: rnna_value} in millions of national currency."""
    # Download PWT 10.01 Stata file
    pwt_path = '/root/pwt_data.dta'
    if not os.path.exists(pwt_path):
        url = 'https://dataverse.nl/api/access/datafile/354098'
        subprocess.run(['curl', '-s', '-L', '-o', pwt_path, url], timeout=60)
    
    import pandas as pd
    df = pd.read_stata(pwt_path)
    geo = df[df['countrycode'] == 'GEO']
    
    result = {}
    for _, row in geo.iterrows():
        year = int(row['year'])
        if not pd.isna(row['rnna']):
            result[year] = float(row['rnna'])
    return result


def collect_weo_data():
    """Collect IMF WEO data for Georgia.
    Returns (gdp_levels, growth_rates) where:
    - gdp_levels: dict {year: real_gdp_billions_lari} for 2000-2027
    - growth_rates: dict {year: percent_change} for 2000-2027
    """
    # Get growth rates from IMF DataMapper API
    url = 'https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/GEO'
    result = subprocess.run(['curl', '-s', '-L', '--max-time', '30', url],
                          capture_output=True, text=True, timeout=35)
    data = json.loads(result.stdout)
    growth_rates = {}
    if 'values' in data and 'NGDP_RPCH' in data['values']:
        geo_data = data['values']['NGDP_RPCH'].get('GEO', {})
        for yr_str, val in geo_data.items():
            growth_rates[int(yr_str)] = float(val)
    
    # Get GDP levels from World Bank API (constant LCU)
    url_wb = 'https://api.worldbank.org/v2/country/GEO/indicator/NY.GDP.MKTP.KN?date=2000:2023&format=json&per_page=50'
    result_wb = subprocess.run(['curl', '-s', '-L', '--max-time', '20', url_wb],
                             capture_output=True, text=True, timeout=25)
    wb_data = json.loads(result_wb.stdout)
    
    gdp_levels = {}  # in billions of Lari
    if isinstance(wb_data, list) and len(wb_data) > 1:
        for entry in wb_data[1]:
            year = int(entry['date'])
            val = entry['value']
            if val is not None:
                gdp_levels[year] = float(val) / 1e9  # Convert to billions
    
    # Extend GDP levels using growth rates for 2024-2027
    last_wb_year = max(gdp_levels.keys())
    for y in range(last_wb_year + 1, 2028):
        if y in growth_rates:
            gdp_levels[y] = gdp_levels[y-1] * (1 + growth_rates[y] / 100)
    
    return gdp_levels, growth_rates


def collect_ecb_cfc_data():
    """Collect ECB Consumption of Fixed Capital data for Georgia.
    Returns dict {year: cfc_value} in units of national currency (Lari)."""
    url = 'https://data-api.ecb.europa.eu/service/data/IDCM/A.N.GE.W2.S1.S1.D.P51C.N1G._T._Z.XDC.V.N?format=csvdata'
    result = subprocess.run(['curl', '-s', '-L', '--max-time', '20', url],
                          capture_output=True, text=True, timeout=25)
    
    cfc_data = {}
    reader = csv.DictReader(io.StringIO(result.stdout))
    for row in reader:
        year = int(row['TIME_PERIOD'])
        value = float(row['OBS_VALUE'])
        cfc_data[year] = value
    
    return cfc_data
