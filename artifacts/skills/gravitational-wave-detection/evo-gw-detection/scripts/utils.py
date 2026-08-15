import numpy as np
import pandas as pd
from pycbc.frame import read_frame
from pycbc.filter import matched_filter, highpass
from pycbc.waveform import get_td_waveform
from pycbc.psd import interpolate, inverse_spectrum_truncation
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def load_gwf_data(filepath, channel):
    """Load gravitational wave data from a .gwf file."""
    logger.info(f"Loading data from {filepath}, channel={channel}")
    strain = read_frame(filepath, channel)
    logger.info(f"Loaded {len(strain)} samples at {strain.sample_rate} Hz, duration={strain.duration}s")
    return strain


def condition_data(strain, highpass_freq=15.0, resample_rate=4096):
    """Condition raw detector data: high-pass filter, resample, crop transients."""
    logger.info(f"Conditioning: highpass={highpass_freq}Hz, resample={resample_rate}Hz")
    # High-pass filter
    strained = highpass(strain, highpass_freq)
    # Resample only if needed
    current_rate = int(strained.sample_rate)
    if current_rate != resample_rate:
        logger.info(f"Resampling from {current_rate} to {resample_rate} Hz")
        new_delta_t = 1.0 / resample_rate
        from pycbc.filter import resample_to_delta_t
        strained = resample_to_delta_t(strained, new_delta_t)
    else:
        logger.info(f"Data already at {resample_rate} Hz, skipping resample")
    # Crop 2 seconds from each end to remove filter transients
    crop_seconds = 2
    strained = strained.crop(crop_seconds, crop_seconds)
    logger.info(f"After conditioning: {len(strained)} samples, duration={strained.duration}s")
    return strained


def estimate_psd(conditioned_data, seg_len=4, low_freq_cutoff=20.0):
    """Estimate PSD using Welch's method."""
    seg_samples = int(seg_len * conditioned_data.sample_rate)
    logger.info(f"Estimating PSD with segment length={seg_len}s ({seg_samples} samples)")
    from pycbc.psd import welch
    psd = welch(conditioned_data, seg_len=seg_samples, seg_stride=seg_samples // 2)
    # Interpolate to match data frequency resolution
    delta_f = 1.0 / conditioned_data.duration
    psd = interpolate(psd, delta_f)
    # Inverse spectrum truncation
    trunc_samples = int(seg_len * conditioned_data.sample_rate)
    psd = inverse_spectrum_truncation(psd, trunc_samples, low_frequency_cutoff=low_freq_cutoff)
    logger.info(f"PSD estimated: {len(psd)} frequency bins, delta_f={psd.delta_f}")
    return psd


def generate_template(mass1, mass2, approximant, sample_rate=4096, f_low=20.0):
    """Generate a waveform template for given masses and approximant."""
    hp, hc = get_td_waveform(
        approximant=approximant,
        mass1=mass1,
        mass2=mass2,
        delta_t=1.0 / sample_rate,
        f_lower=f_low
    )
    return hp


def compute_snr(conditioned_data, template, psd, f_low=20.0, psd_seg_len=4):
    """Perform matched filtering and return peak SNR."""
    # Prepare template: resize to data length
    template.resize(len(conditioned_data))
    
    # Perform matched filtering
    snr_series = matched_filter(template, conditioned_data, psd=psd, low_frequency_cutoff=f_low)
    
    # Take absolute value (maximize over phase)
    snr_abs = abs(snr_series)
    
    # Crop corrupted edges
    # Beginning: PSD corruption + template duration
    template_duration = abs(float(template.start_time))  # template starts at negative time
    psd_crop = psd_seg_len  # seconds
    begin_crop = psd_crop + template_duration
    end_crop = psd_crop
    
    snr_cropped = snr_abs.crop(begin_crop, end_crop)
    
    peak_snr = float(snr_cropped.max())
    return peak_snr


def grid_search_approximant(conditioned_data, psd, approximant, mass_min=10, mass_max=40,
                             sample_rate=4096, f_low=20.0, psd_seg_len=4):
    """Grid search over m1, m2 for a single approximant. Returns best (snr, m1, m2, total_mass)."""
    best_snr = 0.0
    best_m1 = 0
    best_m2 = 0
    
    total_combos = (mass_max - mass_min + 1) * (mass_max - mass_min + 2) // 2
    logger.info(f"Grid search for {approximant}: {total_combos} combinations")
    
    count = 0
    for m1 in range(mass_min, mass_max + 1):
        for m2 in range(mass_min, m1 + 1):  # m1 >= m2
            count += 1
            if count % 50 == 0:
                logger.info(f"  {approximant}: {count}/{total_combos} (best SNR so far: {best_snr:.2f})")
            
            try:
                template = generate_template(m1, m2, approximant, sample_rate, f_low)
                snr = compute_snr(conditioned_data, template, psd, f_low, psd_seg_len)
                
                if snr > best_snr:
                    best_snr = snr
                    best_m1 = m1
                    best_m2 = m2
                    logger.info(f"  New best for {approximant}: m1={m1}, m2={m2}, SNR={snr:.2f}")
            except Exception as e:
                logger.warning(f"  Failed for {approximant} m1={m1} m2={m2}: {e}")
                continue
    
    total_mass = best_m1 + best_m2
    logger.info(f"Best for {approximant}: m1={best_m1}, m2={best_m2}, total_mass={total_mass}, SNR={best_snr:.2f}")
    return best_snr, best_m1, best_m2, total_mass


def run_full_detection(data_path, channel, output_csv,
                       approximants=None, mass_min=10, mass_max=40,
                       highpass_freq=15.0, resample_rate=4096,
                       f_low=20.0, psd_seg_len=4):
    """End-to-end detection pipeline."""
    if approximants is None:
        approximants = ["SEOBNRv4_opt", "IMRPhenomD", "TaylorT4"]
    
    # Load data
    strain = load_gwf_data(data_path, channel)
    
    # Condition data
    conditioned = condition_data(strain, highpass_freq, resample_rate)
    
    # Estimate PSD
    psd = estimate_psd(conditioned, seg_len=psd_seg_len, low_freq_cutoff=f_low)
    
    # Grid search for each approximant
    results = []
    for approx in approximants:
        snr, m1, m2, total_mass = grid_search_approximant(
            conditioned, psd, approx, mass_min, mass_max,
            resample_rate, f_low, psd_seg_len
        )
        results.append({
            'approximant': approx,
            'snr': round(snr, 2),
            'total_mass': total_mass
        })
    
    # Write results
    df = pd.DataFrame(results)
    df.to_csv(output_csv, index=False)
    logger.info(f"Results written to {output_csv}")
    logger.info(f"\n{df.to_string()}")
    return df


def validate_results(csv_path):
    """Validate the detection results CSV."""
    df = pd.read_csv(csv_path)
    
    # Check columns
    required_cols = ['approximant', 'snr', 'total_mass']
    for col in required_cols:
        assert col in df.columns, f"Missing column: {col}"
    
    # Check we have 3 rows
    assert len(df) == 3, f"Expected 3 rows, got {len(df)}"
    
    # Check approximants
    expected_approx = {"SEOBNRv4_opt", "IMRPhenomD", "TaylorT4"}
    actual_approx = set(df['approximant'].values)
    assert actual_approx == expected_approx, f"Expected approximants {expected_approx}, got {actual_approx}"
    
    # Check SNR values are positive and reasonable
    for _, row in df.iterrows():
        assert row['snr'] > 0, f"SNR must be positive for {row['approximant']}"
        assert 20 <= row['total_mass'] <= 80, f"Total mass {row['total_mass']} out of expected range"
    
    logger.info("Validation passed!")
    return True
