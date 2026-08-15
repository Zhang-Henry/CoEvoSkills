"""Seismic phase association utilities."""
import numpy as np
import pandas as pd
from math import radians, cos, sin, sqrt, atan2


def haversine_km(lat1, lon1, lat2, lon2):
    """Compute great-circle distance between two points in km."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c


def associate_picks(picks_df, station_coords, vp=6.0, vs_ratio=1.75,
                    max_p_spread=10.0, min_stations=3, assumed_depth_km=8.0,
                    dedup_window=5.0):
    """Associate phase picks into earthquake events.
    
    Algorithm:
    1. Sort P picks by time
    2. Greedy grouping: consecutive P picks within max_p_spread seconds
    3. For each group with >= min_stations, estimate origin time
    4. Deduplicate events within dedup_window seconds
    
    Args:
        picks_df: DataFrame with columns [station, phase, time, prob]
        station_coords: dict {"NET.STA": (lat, lon, elev_m)}
        vp: P-wave velocity in km/s
        vs_ratio: vp/vs ratio
        max_p_spread: Max time spread (seconds) for grouping P picks
        min_stations: Minimum stations required for valid event
        assumed_depth_km: Assumed source depth in km
        dedup_window: Window (seconds) for deduplicating events
    
    Returns:
        pd.DataFrame with columns [time, n_stations, n_picks, mean_prob]
    """
    from obspy import UTCDateTime
    
    vs = vp / vs_ratio
    
    # Get P picks sorted by time
    p_picks = picks_df[picks_df['phase'] == 'P'].copy()
    if len(p_picks) == 0:
        return pd.DataFrame(columns=['time', 'n_stations', 'n_picks', 'mean_prob'])
    
    # Determine reference time from earliest pick
    all_times = picks_df['time'].tolist()
    ref_time = min(all_times)
    
    p_picks['time_float'] = p_picks['time'].apply(lambda t: float(t - ref_time))
    p_picks = p_picks.sort_values('time_float').reset_index(drop=True)
    
    # Greedy grouping of P picks
    groups = []
    current_group = [0]
    for i in range(1, len(p_picks)):
        if p_picks.iloc[i]['time_float'] - p_picks.iloc[current_group[0]]['time_float'] <= max_p_spread:
            current_group.append(i)
        else:
            groups.append(current_group)
            current_group = [i]
    if current_group:
        groups.append(current_group)
    
    # Estimate origin time for each group
    events = []
    for group_indices in groups:
        group_picks = p_picks.iloc[group_indices]
        stations_in_group = group_picks['station'].unique()
        n_stations = len(stations_in_group)
        
        if n_stations < min_stations:
            continue
        
        # Compute center of stations in this group
        center_lat = np.mean([station_coords[s][0] for s in stations_in_group])
        center_lon = np.mean([station_coords[s][1] for s in stations_in_group])
        
        # Estimate origin time for each pick
        origin_times = []
        for _, pick in group_picks.iterrows():
            lat, lon, elev = station_coords[pick['station']]
            dist_km = haversine_km(lat, lon, center_lat, center_lon)
            dist_3d = sqrt(dist_km**2 + assumed_depth_km**2)
            travel_time = dist_3d / vp
            ot = pick['time_float'] - travel_time
            origin_times.append(ot)
        
        median_ot = np.median(origin_times)
        event_time = ref_time + median_ot
        mean_prob = group_picks['prob'].mean()
        
        events.append({
            'time': event_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
            'n_stations': n_stations,
            'n_picks': len(group_picks),
            'mean_prob': round(float(mean_prob), 4),
            'origin_time_float': median_ot,
        })
    
    if not events:
        return pd.DataFrame(columns=['time', 'n_stations', 'n_picks', 'mean_prob'])
    
    # Deduplicate events within dedup_window
    events_df = pd.DataFrame(events)
    events_df = events_df.sort_values('origin_time_float').reset_index(drop=True)
    
    final_events = []
    used = set()
    for i in range(len(events_df)):
        if i in used:
            continue
        cluster = [i]
        for j in range(i+1, len(events_df)):
            if j in used:
                continue
            if abs(events_df.iloc[j]['origin_time_float'] - events_df.iloc[i]['origin_time_float']) <= dedup_window:
                cluster.append(j)
                used.add(j)
        used.add(i)
        best = max(cluster, key=lambda idx: events_df.iloc[idx]['n_stations'])
        final_events.append(events_df.iloc[best])
    
    final_df = pd.DataFrame(final_events)[['time', 'n_stations', 'n_picks', 'mean_prob']]
    return final_df.sort_values('time').reset_index(drop=True)
