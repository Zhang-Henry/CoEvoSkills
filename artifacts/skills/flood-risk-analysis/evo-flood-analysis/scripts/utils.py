import pandas as pd
import requests
import io
import os


def read_station_ids(filepath):
    """Read USGS station IDs from a text file, one per line.
    Returns list of string station IDs with leading zeros preserved."""
    station_ids = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line and line.isdigit():
                station_ids.append(line)
    return station_ids


def fetch_nws_flood_stages():
    """Download NWS all gauges report and return dict mapping usgs_id -> flood_stage (float).
    Only includes stations with valid numeric flood stage values."""
    url = "https://water.noaa.gov/resources/downloads/reports/nwps_all_gauges_report.csv"
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), dtype=str)
    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]
    
    # Use exact column names
    usgs_col = 'usgs id'
    flood_col = 'flood stage'
    
    if usgs_col not in df.columns or flood_col not in df.columns:
        raise ValueError(f"Could not find required columns. Available: {list(df.columns)}")
    
    result = {}
    for _, row in df.iterrows():
        usgs_id = str(row[usgs_col]).strip()
        flood_stage_str = str(row[flood_col]).strip()
        try:
            flood_stage = float(flood_stage_str)
            # -9999 is a sentinel for missing data
            if pd.notna(flood_stage) and flood_stage > -9000:
                result[usgs_id] = flood_stage
        except (ValueError, TypeError):
            continue
    return result


def fetch_gage_height_data(station_id, start_date, end_date):
    """Fetch instantaneous gage height data from USGS NWIS for a station.
    Returns DataFrame with datetime index and gage height values.
    Uses parameter code 00065 (gage height)."""
    from dataretrieval import nwis
    
    try:
        df, metadata = nwis.get_iv(
            sites=station_id,
            parameterCd='00065',
            start=start_date,
            end=end_date
        )
    except Exception as e:
        print(f"  Warning: Could not retrieve data for station {station_id}: {e}")
        return None
    
    if df is None or df.empty:
        return None
    
    # Find gage height column (contains 00065, not ending in _cd)
    gage_cols = [c for c in df.columns if '00065' in str(c) and not str(c).endswith('_cd')]
    if not gage_cols:
        return None
    
    # Use the first matching column
    gage_col = gage_cols[0]
    series = pd.to_numeric(df[gage_col], errors='coerce')
    result = pd.DataFrame({'gage_height': series})
    result.index = df.index
    return result


def compute_daily_max(gage_df):
    """Resample gage height data to daily frequency using maximum value.
    Returns Series with date index and daily max gage height."""
    if gage_df is None or gage_df.empty:
        return None
    daily_max = gage_df['gage_height'].resample('D').max()
    daily_max = daily_max.dropna()
    return daily_max


def count_flood_days(daily_max_series, flood_stage):
    """Count number of days where daily max gage height >= flood stage.
    Returns integer count."""
    if daily_max_series is None or daily_max_series.empty:
        return 0
    flood_days = (daily_max_series >= flood_stage).sum()
    return int(flood_days)


def run_flood_analysis(stations_file, output_file, start_date='2025-04-01', end_date='2025-04-07'):
    """End-to-end flood analysis pipeline.
    
    Args:
        stations_file: Path to text file with USGS station IDs
        output_file: Path to output CSV file
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
    
    Returns:
        DataFrame with results
    """
    # Step 1: Read station IDs
    print("Reading station IDs...")
    station_ids = read_station_ids(stations_file)
    print(f"  Found {len(station_ids)} stations")
    
    # Step 2: Fetch NWS flood stages
    print("Fetching NWS flood stage thresholds...")
    flood_stages = fetch_nws_flood_stages()
    print(f"  Found {len(flood_stages)} stations with flood stages in NWS report")
    
    # Step 3: Match stations
    matched = {sid: flood_stages[sid] for sid in station_ids if sid in flood_stages}
    print(f"  Matched {len(matched)} stations with flood stage thresholds")
    
    # Step 4: For each matched station, fetch data and count flood days
    results = []
    for sid, threshold in matched.items():
        print(f"  Processing station {sid} (flood stage: {threshold} ft)...")
        gage_df = fetch_gage_height_data(sid, start_date, end_date)
        daily_max = compute_daily_max(gage_df)
        flood_count = count_flood_days(daily_max, threshold)
        if flood_count > 0:
            results.append({'station_id': sid, 'flood_days': flood_count})
            print(f"    -> {flood_count} flood days")
        else:
            print(f"    -> No flooding")
    
    # Step 5: Create output DataFrame, sort by flood_days descending
    result_df = pd.DataFrame(results, columns=['station_id', 'flood_days'])
    result_df = result_df.sort_values('flood_days', ascending=False).reset_index(drop=True)
    
    # Step 6: Write output
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    result_df.to_csv(output_file, index=False)
    print(f"\nResults written to {output_file}")
    print(f"  {len(result_df)} stations with flooding")
    
    return result_df


def validate_output(output_file):
    """Validate the output CSV file meets requirements."""
    df = pd.read_csv(output_file, dtype={'station_id': str})
    
    assert 'station_id' in df.columns, "Missing 'station_id' column"
    assert 'flood_days' in df.columns, "Missing 'flood_days' column"
    assert len(df) > 0, "No stations in output"
    assert (df['flood_days'] > 0).all(), "All stations must have at least 1 flood day"
    assert df['flood_days'].dtype in ['int64', 'int32', 'float64'], "flood_days should be numeric"
    
    # Check station IDs are strings (preserved leading zeros)
    for sid in df['station_id']:
        assert isinstance(sid, str), f"Station ID {sid} is not a string"
    
    print(f"Validation passed: {len(df)} stations with flooding")
    return True
