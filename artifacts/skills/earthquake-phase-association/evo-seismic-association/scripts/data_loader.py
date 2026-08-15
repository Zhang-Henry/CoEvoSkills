"""Data loading utilities for seismic phase association."""
import obspy
import pandas as pd


def load_waveforms(mseed_path):
    """Load waveform data from MSEED file."""
    return obspy.read(mseed_path)


def load_stations(csv_path):
    """Load station data and extract unique station coordinates.
    
    Returns:
        dict: {"NET.STA": (lat, lon, elevation_m)} for each unique station
    """
    df = pd.read_csv(csv_path)
    station_info = df.groupby(['network', 'station']).first().reset_index()
    station_coords = {}
    for _, row in station_info.iterrows():
        key = f"{row['network']}.{row['station']}"
        station_coords[key] = (row['latitude'], row['longitude'], row['elevation_m'])
    return station_coords


def group_station_streams(stream, station_coords):
    """Group traces by station, selecting best available 3-component set.
    
    Preference order: HH > HN > EH channels.
    
    Args:
        stream: ObsPy Stream with all traces
        station_coords: dict of station coordinates
    
    Returns:
        dict: {"NET.STA": ObsPy Stream} with selected channels per station
    """
    station_streams = {}
    for key in station_coords:
        net, sta = key.split('.')
        sta_traces = stream.select(network=net, station=sta)
        
        for chan_prefix in ['HH', 'HN', 'EH']:
            e_traces = sta_traces.select(channel=f"{chan_prefix}E")
            n_traces = sta_traces.select(channel=f"{chan_prefix}N")
            z_traces = sta_traces.select(channel=f"{chan_prefix}Z")
            
            if len(z_traces) > 0:
                sub_st = obspy.Stream()
                if len(e_traces) > 0:
                    sub_st += e_traces[0]
                if len(n_traces) > 0:
                    sub_st += n_traces[0]
                sub_st += z_traces[0]
                station_streams[key] = sub_st
                break
    
    return station_streams
