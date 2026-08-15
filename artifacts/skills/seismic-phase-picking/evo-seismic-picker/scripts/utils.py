import numpy as np
import os
import pandas as pd

def load_trace(filepath):
    d = np.load(filepath, allow_pickle=True)
    result = {
        'data': d['data'],
        'dt': float(d['dt']),
        'channels': str(d['channels']),
    }
    for key in ['unit', 'start_time', 'network', 'station', 'location_code',
                'event_time', 'distance_km', 'event_depth_km', 'snr']:
        if key in d:
            val = d[key]
            if isinstance(val, np.ndarray) and val.ndim == 0:
                val = val.item()
            result[key] = val
    return result

def parse_channels(channel_str):
    return [c.strip() for c in channel_str.split(',')]

def get_component_map(channels):
    ch_list = parse_channels(channels)
    comp_map = {}
    for i, ch in enumerate(ch_list):
        orient = ch[2].upper() if len(ch) >= 3 else ch[-1].upper()
        if orient in ('Z', '3'): comp_map['Z'] = i
        elif orient in ('N', '1'): comp_map['N'] = i
        elif orient in ('E', '2'): comp_map['E'] = i
    return comp_map

def prepare_zne_normalized(data, channels):
    """Reorder data to ZNE, handle single-channel by replication, and normalize."""
    ch_list = parse_channels(channels)
    comp_map = get_component_map(channels)
    n_samples = data.shape[0]
    n_cols = data.shape[1]
    active_cols = [i for i in range(n_cols) if np.any(data[:, i] != 0)]
    zne = np.zeros((n_samples, 3), dtype=np.float64)
    if len(ch_list) == 1 or len(active_cols) <= 1:
        if active_cols:
            active_data = data[:, active_cols[0]].astype(np.float64)
        else:
            active_data = data[:, 0].astype(np.float64)
        for i in range(3):
            zne[:, i] = active_data
    else:
        for out_idx, comp in enumerate(['Z', 'N', 'E']):
            col = comp_map.get(comp)
            if col is not None and col < n_cols:
                zne[:, out_idx] = data[:, col].astype(np.float64)
    max_abs = np.max(np.abs(zne))
    if max_abs > 0:
        zne = zne / max_abs
    return zne

def make_obspy_stream(zne_data, dt, start_time_str):
    """Convert ZNE numpy array to ObsPy Stream."""
    import obspy
    from obspy import UTCDateTime
    st = obspy.Stream()
    for i, comp in enumerate(['Z', 'N', 'E']):
        tr = obspy.Trace(data=zne_data[:, i].copy())
        tr.stats.sampling_rate = 1.0 / dt
        try:
            tr.stats.starttime = UTCDateTime(start_time_str)
        except:
            tr.stats.starttime = UTCDateTime(0)
        tr.stats.channel = f'HH{comp}'
        tr.stats.station = 'STA'
        tr.stats.network = 'XX'
        st.append(tr)
    return st

def metadata_based_pick(trace_info, vp, vs_ratio):
    """Compute expected P and S arrival indices from metadata.
    vp: P-wave velocity in km/s (caller-supplied)
    vs_ratio: Vp/Vs ratio (caller-supplied)
    """
    from obspy import UTCDateTime
    vs = vp / vs_ratio
    dt = trace_info['dt']
    try:
        origin_t = UTCDateTime(str(trace_info['event_time']))
        start_t = UTCDateTime(str(trace_info['start_time']))
    except:
        return None, None
    origin_offset = float(origin_t - start_t)
    dist = float(trace_info.get('distance_km', 0))
    depth = float(trace_info.get('event_depth_km', 0))
    if dist <= 0:
        return None, None
    hypo_dist = np.sqrt(dist**2 + depth**2)
    p_travel = hypo_dist / vp
    s_travel = hypo_dist / vs
    p_idx = int(round((origin_offset + p_travel) / dt))
    s_idx = int(round((origin_offset + s_travel) / dt))
    return p_idx, s_idx

def pick_with_phasenet(stream, model, dt, start_time_str, p_threshold, s_threshold):
    """Run PhaseNet classify and return list of (phase, pick_idx, prob) tuples.
    p_threshold, s_threshold: caller-supplied probability thresholds.
    """
    from obspy import UTCDateTime
    try:
        start_t = UTCDateTime(start_time_str)
    except:
        start_t = UTCDateTime(0)
    picks_result = []
    try:
        classified = model.classify(stream, P_threshold=p_threshold, S_threshold=s_threshold)
        for pick in classified.picks:
            pick_idx = int(round(float(pick.peak_time - start_t) / dt))
            if 0 <= pick_idx < int(round(stream[0].stats.npts)):
                picks_result.append((pick.phase, pick_idx, pick.peak_value))
    except Exception as e:
        print(f"  PhaseNet classify error: {e}")
    return picks_result

def select_best_picks(picks):
    """Select best P and S picks from candidates.
    For each phase, keep highest probability pick.
    S must come after P (physical constraint)."""
    p_picks = [(idx, prob) for phase, idx, prob in picks if phase == 'P']
    s_picks = [(idx, prob) for phase, idx, prob in picks if phase == 'S']
    result = []
    best_p = None
    if p_picks:
        p_picks.sort(key=lambda x: x[1], reverse=True)
        best_p = p_picks[0]
        result.append(('P', best_p[0]))
    if s_picks:
        s_picks.sort(key=lambda x: x[1], reverse=True)
        for s_idx, s_prob in s_picks:
            if best_p is None or s_idx > best_p[0]:
                result.append(('S', s_idx))
                break
    return result

def calibrate_thresholds(data_dir, model, sample_size=10):
    """Derive suitable P and S thresholds from a sample of traces.
    Runs PhaseNet at a very low threshold, then picks a threshold
    that retains picks with probability above the median of the
    top-1 picks per trace.
    Returns (p_threshold, s_threshold).
    """
    from obspy import UTCDateTime
    files = sorted([f for f in os.listdir(data_dir) if f.endswith('.npz')])
    # Sample evenly across dataset
    step = max(1, len(files) // sample_size)
    sample_files = files[::step][:sample_size]
    
    p_probs = []
    s_probs = []
    
    for fname in sample_files:
        filepath = os.path.join(data_dir, fname)
        trace = load_trace(filepath)
        zne = prepare_zne_normalized(trace['data'], trace['channels'])
        start_time = str(trace.get('start_time', '1970-01-01T00:00:00'))
        stream = make_obspy_stream(zne, trace['dt'], start_time)
        # Use very low threshold to see all candidates
        raw = pick_with_phasenet(stream, model, trace['dt'], start_time,
                                 p_threshold=0.01, s_threshold=0.01)
        p_max = max([prob for ph, idx, prob in raw if ph == 'P'], default=0)
        s_max = max([prob for ph, idx, prob in raw if ph == 'S'], default=0)
        if p_max > 0:
            p_probs.append(p_max)
        if s_max > 0:
            s_probs.append(s_max)
    
    # Set threshold at fraction of median peak probability
    # This adapts to the actual confidence distribution in the data
    if p_probs:
        p_thresh = max(0.05, np.median(p_probs) * 0.3)
    else:
        p_thresh = 0.1
    if s_probs:
        s_thresh = max(0.05, np.median(s_probs) * 0.3)
    else:
        s_thresh = 0.1
    
    return float(p_thresh), float(s_thresh)

def process_all_files(data_dir, output_csv, p_threshold=None, s_threshold=None,
                      vp=6.0, vs_ratio=1.73):
    """Process all trace files using PhaseNet with metadata fallback.
    
    Args:
        data_dir: directory containing .npz trace files
        output_csv: path to write results CSV
        p_threshold: P-wave probability threshold (if None, calibrated from data)
        s_threshold: S-wave probability threshold (if None, calibrated from data)
        vp: P-wave velocity in km/s for metadata fallback
        vs_ratio: Vp/Vs ratio for metadata fallback
    """
    import seisbench.models as sbm
    print("Loading PhaseNet model...")
    model = sbm.PhaseNet.from_pretrained('original')
    model.eval()
    print("Model loaded.")
    
    # Calibrate thresholds from data if not supplied
    if p_threshold is None or s_threshold is None:
        print("Calibrating thresholds from data sample...")
        cal_p, cal_s = calibrate_thresholds(data_dir, model)
        if p_threshold is None:
            p_threshold = cal_p
        if s_threshold is None:
            s_threshold = cal_s
        print(f"  Calibrated thresholds: P={p_threshold:.3f}, S={s_threshold:.3f}")
    
    files = sorted([f for f in os.listdir(data_dir) if f.endswith('.npz')])
    n_samples_per_trace = None
    all_picks = []
    phasenet_count = 0
    metadata_count = 0
    for i, fname in enumerate(files):
        filepath = os.path.join(data_dir, fname)
        trace = load_trace(filepath)
        if n_samples_per_trace is None:
            n_samples_per_trace = trace['data'].shape[0]
        zne = prepare_zne_normalized(trace['data'], trace['channels'])
        start_time = str(trace.get('start_time', '1970-01-01T00:00:00'))
        stream = make_obspy_stream(zne, trace['dt'], start_time)
        raw_picks = pick_with_phasenet(
            stream, model, trace['dt'], start_time,
            p_threshold=p_threshold, s_threshold=s_threshold
        )
        best_picks = select_best_picks(raw_picks)
        has_p = any(p == 'P' for p, _ in best_picks)
        has_s = any(p == 'S' for p, _ in best_picks)
        if has_p and has_s:
            phasenet_count += 1
        else:
            meta_p, meta_s = metadata_based_pick(trace, vp=vp, vs_ratio=vs_ratio)
            if not has_p and meta_p is not None and 0 <= meta_p < n_samples_per_trace:
                best_picks.append(('P', meta_p))
            if not has_s and meta_s is not None and 0 <= meta_s < n_samples_per_trace:
                best_picks.append(('S', meta_s))
            if meta_p is not None or meta_s is not None:
                metadata_count += 1
        for phase, idx in best_picks:
            all_picks.append({
                'file_name': fname,
                'phase': phase,
                'pick_idx': int(idx)
            })
        if (i + 1) % 20 == 0:
            print(f"  Processed {i+1}/{len(files)} files")
    df = pd.DataFrame(all_picks, columns=['file_name', 'phase', 'pick_idx'])
    df.to_csv(output_csv, index=False)
    print(f"\nDone! Wrote {len(df)} picks to {output_csv}")
    print(f"  P picks: {len(df[df['phase']=='P'])}")
    print(f"  S picks: {len(df[df['phase']=='S'])}")
    print(f"  PhaseNet: {phasenet_count}, Metadata fallback: {metadata_count}")
    print(f"  Files with picks: {df['file_name'].nunique()}/{len(files)}")
    return df
