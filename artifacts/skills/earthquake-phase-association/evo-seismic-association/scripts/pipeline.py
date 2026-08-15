"""End-to-end seismic phase association pipeline."""
import sys
import os
import warnings
warnings.filterwarnings('ignore')

# Ensure this scripts directory is on path
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from data_loader import load_waveforms, load_stations, group_station_streams
from picker import run_phasenet_picking
from associator import associate_picks


def run_pipeline(mseed_path, stations_csv_path, output_csv_path,
                 p_threshold=0.3, s_threshold=0.3,
                 vp=6.0, vs_ratio=1.75,
                 max_p_spread=10.0, min_stations=3,
                 assumed_depth_km=8.0, dedup_window=5.0,
                 model_name='instance'):
    """Run complete seismic phase association pipeline.
    
    Args:
        mseed_path: Path to MSEED waveform file
        stations_csv_path: Path to stations CSV
        output_csv_path: Path to write results CSV
        p_threshold: P-phase detection threshold
        s_threshold: S-phase detection threshold
        vp: P-wave velocity (km/s)
        vs_ratio: vp/vs ratio
        max_p_spread: Max P-pick time spread for grouping (seconds)
        min_stations: Minimum stations per event
        assumed_depth_km: Assumed source depth (km)
        dedup_window: Deduplication window (seconds)
        model_name: SeisBench pretrained model name
    
    Returns:
        pd.DataFrame of detected events
    """
    print("Step 1: Loading data...")
    stream = load_waveforms(mseed_path)
    station_coords = load_stations(stations_csv_path)
    station_streams = group_station_streams(stream, station_coords)
    print(f"  Loaded {len(stream)} traces from {len(station_streams)} stations")
    
    print("Step 2: Running PhaseNet picking...")
    picks_df = run_phasenet_picking(station_streams,
                                    p_threshold=p_threshold,
                                    s_threshold=s_threshold,
                                    model_name=model_name)
    n_p = len(picks_df[picks_df['phase'] == 'P']) if len(picks_df) > 0 else 0
    n_s = len(picks_df[picks_df['phase'] == 'S']) if len(picks_df) > 0 else 0
    print(f"  Total picks: {len(picks_df)} (P: {n_p}, S: {n_s})")
    
    print("Step 3: Associating picks into events...")
    events_df = associate_picks(picks_df, station_coords,
                                vp=vp, vs_ratio=vs_ratio,
                                max_p_spread=max_p_spread,
                                min_stations=min_stations,
                                assumed_depth_km=assumed_depth_km,
                                dedup_window=dedup_window)
    print(f"  Detected {len(events_df)} events")
    
    print(f"Step 4: Writing results to {output_csv_path}...")
    events_df.to_csv(output_csv_path, index=False)
    print("  Done.")
    
    return events_df


def validate_results(output_csv_path):
    """Validate the output CSV meets requirements.
    
    Checks:
    - File exists and is readable
    - Has 'time' column
    - Times are valid ISO format
    - At least some events detected
    """
    import pandas as pd
    from datetime import datetime
    
    df = pd.read_csv(output_csv_path)
    
    assert 'time' in df.columns, "Missing 'time' column"
    assert len(df) > 0, "No events detected"
    
    # Validate time format
    for t in df['time']:
        try:
            datetime.fromisoformat(t)
        except ValueError:
            raise AssertionError(f"Invalid ISO time format: {t}")
    
    # Check no timezone info
    for t in df['time']:
        assert '+' not in t and 'Z' not in t, f"Time should not have timezone: {t}"
    
    print(f"Validation passed: {len(df)} events with valid ISO timestamps")
    return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--mseed', required=True)
    parser.add_argument('--stations', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    
    run_pipeline(args.mseed, args.stations, args.output)
    validate_results(args.output)
