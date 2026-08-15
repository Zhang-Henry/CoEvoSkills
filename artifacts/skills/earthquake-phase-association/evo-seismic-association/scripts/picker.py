"""Phase picking utilities using SeisBench deep learning models."""
import pandas as pd


def run_phasenet_picking(station_streams, p_threshold=0.3, s_threshold=0.3, model_name='instance'):
    """Run PhaseNet phase picking on all station streams.
    
    Args:
        station_streams: dict {"NET.STA": ObsPy Stream}
        p_threshold: Detection threshold for P phases
        s_threshold: Detection threshold for S phases
        model_name: Pretrained model name (e.g., 'instance', 'original')
    
    Returns:
        pd.DataFrame with columns: station, phase, time (UTCDateTime), prob
    """
    import seisbench.models as sbm
    
    model = sbm.PhaseNet.from_pretrained(model_name)
    model.eval()
    
    all_picks = []
    for sta_key, sta_stream in station_streams.items():
        try:
            annotations = model.annotate(sta_stream)
            picks_result = model.classify_aggregate(annotations, {
                'P_threshold': p_threshold,
                'S_threshold': s_threshold
            })
            
            for pick in picks_result.picks:
                all_picks.append({
                    'station': sta_key,
                    'phase': pick.phase,
                    'time': pick.peak_time,
                    'prob': pick.peak_value,
                })
        except Exception as e:
            print(f"  Warning: Error processing {sta_key}: {e}")
    
    return pd.DataFrame(all_picks)
