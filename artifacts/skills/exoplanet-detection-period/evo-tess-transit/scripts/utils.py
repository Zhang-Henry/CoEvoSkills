import numpy as np
from scipy.ndimage import median_filter
from scipy.interpolate import interp1d
from astropy.timeseries import BoxLeastSquares, LombScargle


def load_and_filter(filepath):
    """Load TESS lightcurve file, filter by quality flags and remove NaN/inf.
    Expects columns: time, flux, quality_flag, flux_error.
    """
    data = np.loadtxt(filepath, comments='#')
    time = data[:, 0]
    flux = data[:, 1]
    flag = data[:, 2].astype(int)
    flux_err = data[:, 3]
    good = (flag == 0) & np.isfinite(time) & np.isfinite(flux) & np.isfinite(flux_err)
    time, flux, flux_err = time[good], flux[good], flux_err[good]
    order = np.argsort(time)
    return time[order], flux[order], flux_err[order]


def remove_outliers(time, flux, flux_err, sigma_upper=5.0, sigma_lower=5.0):
    """Sigma-clip outliers. Both bounds default to 5-sigma.
    Caller may widen sigma_lower to preserve deep transits.
    """
    med = np.median(flux)
    std = np.std(flux)
    mask = (flux < med + sigma_upper * std) & (flux > med - sigma_lower * std)
    return time[mask], flux[mask], flux_err[mask]


def identify_stellar_rotation(time, flux, flux_err):
    """Use Lomb-Scargle to find the dominant periodic variability.
    Returns (period, power).
    """
    baseline = time[-1] - time[0]
    ls = LombScargle(time, flux, flux_err)
    frequency, power = ls.autopower(
        minimum_frequency=1.0 / baseline,
        maximum_frequency=1.0 / 0.1
    )
    best_idx = np.argmax(power)
    return 1.0 / frequency[best_idx], power[best_idx]


def median_detrend(time, flux, flux_err, window_days):
    """Simple median-filter detrending. Returns detrended flux, error, trend."""
    cadence = np.median(np.diff(time))
    wpts = max(int(window_days / cadence) | 1, 3)  # ensure odd and >= 3
    trend = median_filter(flux, size=wpts)
    return flux / trend, flux_err / trend, trend


def detrend_with_transit_mask(time, flux, flux_err, period, t0,
                              window_days, transit_phase_hw=0.02,
                              n_iter=3):
    """Iterative transit-masked median-filter detrending.

    Masks phases within *transit_phase_hw* of the expected mid-transit,
    interpolates over the gaps, then applies a median filter.
    """
    cadence = np.median(np.diff(time))
    wpts = max(int(window_days / cadence) | 1, 3)
    trend = median_filter(flux, size=wpts)

    for _ in range(n_iter):
        phase = ((time - t0) % period) / period
        phase[phase > 0.5] -= 1.0
        mask = np.abs(phase) < transit_phase_hw
        fm = flux.copy()
        fm[mask] = np.nan
        valid = ~np.isnan(fm)
        if valid.sum() < 10:
            break
        fm_filled = interp1d(time[valid], fm[valid], kind='linear',
                             fill_value='extrapolate')(time)
        trend = median_filter(fm_filled, size=wpts)

    return flux / trend, flux_err / trend, trend


def bls_search(time, flux, flux_err,
               min_period=0.5, max_period=None,
               min_dur_hr=0.5, max_dur_hr=8.0,
               n_dur=20, freq_factor=2.0):
    """BLS periodogram. Returns (period, duration, t0, results, bls)."""
    if max_period is None:
        max_period = (time[-1] - time[0]) / 2.0
    bls = BoxLeastSquares(time, flux, dy=flux_err)
    durs = np.linspace(min_dur_hr / 24, max_dur_hr / 24, n_dur)
    res = bls.autopower(durs, minimum_period=min_period,
                        maximum_period=max_period,
                        frequency_factor=freq_factor)
    i = np.argmax(res.power)
    return res.period[i], res.duration[i], res.transit_time[i], res, bls


def refine_bls(time, flux, flux_err, p0,
               rel_width=0.01, n_pts=200000,
               min_dur_hr=0.5, max_dur_hr=8.0, n_dur=20):
    """Fine-grid BLS around *p0*. Returns (period, duration, t0, results)."""
    bls = BoxLeastSquares(time, flux, dy=flux_err)
    durs = np.linspace(min_dur_hr / 24, max_dur_hr / 24, n_dur)
    periods = np.linspace(p0 * (1 - rel_width), p0 * (1 + rel_width), n_pts)
    res = bls.power(periods, durs)
    i = np.argmax(res.power)
    return res.period[i], res.duration[i], res.transit_time[i], res


def top_bls_peaks(results, order=20, n=10):
    """Return list of (period, power) for top BLS peaks."""
    from scipy.signal import argrelextrema
    idx = argrelextrema(results.power, np.greater, order=order)[0]
    if len(idx) == 0:
        i = np.argmax(results.power)
        return [(results.period[i], results.power[i])]
    s = idx[np.argsort(-results.power[idx])][:n]
    return [(results.period[j], results.power[j]) for j in s]


def is_harmonic(pa, pb, tol=0.03, max_n=6):
    """True if pa/pb is close to a small integer ratio n/1 for n in 1..max_n."""
    r = pa / pb
    for n in range(1, max_n + 1):
        if abs(r - n) < tol * n:
            return True
    for n in range(2, max_n + 1):
        if abs(r - 1.0 / n) < tol / n:
            return True
    return False


def _choose_detrend_windows(stellar_period, cadence, n_windows=5):
    """Pick a set of detrending windows shorter than the stellar period.

    Physical rationale: the window must be long enough to contain many
    cadences (for a smooth trend) but short enough to track variability
    faster than the stellar rotation. We use fractions of the stellar
    period from ~0.15 P_rot to ~0.5 P_rot.
    """
    lo = max(stellar_period * 0.15, cadence * 30)
    hi = stellar_period * 0.5
    if hi <= lo:
        hi = lo * 2
    return np.linspace(lo, hi, n_windows)


def multi_window_bls(time, flux, flux_err, stellar_period,
                     min_period=0.5, max_period=None,
                     min_dur_hr=0.5, max_dur_hr=8.0):
    """Run BLS across several detrending windows, skip stellar harmonics.

    Returns (consensus_period, list_of_periods).
    """
    import lightkurve as lk
    if max_period is None:
        max_period = (time[-1] - time[0]) / 2.0
    cadence = np.median(np.diff(time))
    windows = _choose_detrend_windows(stellar_period, cadence)
    lc = lk.LightCurve(time=time, flux=flux, flux_err=flux_err)
    periods = []
    for w in windows:
        wl = max(int(w / cadence) | 1, 5)
        flat = lc.flatten(window_length=wl)
        bp, _, _, _, _ = bls_search(
            flat.time.value, flat.flux.value, flat.flux_err.value,
            min_period=min_period, max_period=max_period,
            min_dur_hr=min_dur_hr, max_dur_hr=max_dur_hr
        )
        if not is_harmonic(bp, stellar_period):
            periods.append(bp)
    if not periods:
        # fallback: accept all
        for w in windows:
            wl = max(int(w / cadence) | 1, 5)
            flat = lc.flatten(window_length=wl)
            bp, _, _, _, _ = bls_search(
                flat.time.value, flat.flux.value, flat.flux_err.value,
                min_period=min_period, max_period=max_period,
                min_dur_hr=min_dur_hr, max_dur_hr=max_dur_hr
            )
            periods.append(bp)
    return float(np.median(periods)), periods


def fit_batman(time, flux, flux_err, per0, t0_0,
               rp0=0.05, a0=15.0, inc0=88.0,
               u=(0.3, 0.1), per_rel_bound=0.005):
    """Fit a batman transit model via DE + Nelder-Mead.

    Bounds on period are *per0 * (1 +/- per_rel_bound)*.
    Bounds on a/Rs span 3–100 (agnostic to system scale).
    Returns dict of best-fit parameters.
    """
    import batman
    from scipy.optimize import minimize, differential_evolution

    def chi2(x):
        per, t0, rp, a, inc, bl = x
        try:
            p = batman.TransitParams()
            p.t0, p.per, p.rp, p.a, p.inc = t0, per, rp, a, inc
            p.ecc, p.w = 0.0, 90.0
            p.u, p.limb_dark = list(u), 'quadratic'
            model = batman.TransitModel(p, time).light_curve(p)
            return float(np.sum(((flux - bl * model) / flux_err) ** 2))
        except Exception:
            return 1e15

    bounds = [
        (per0 * (1 - per_rel_bound), per0 * (1 + per_rel_bound)),
        (t0_0 - 0.15, t0_0 + 0.15),
        (0.005, 0.2),
        (3.0, 100.0),
        (75.0, 90.0),
        (0.995, 1.005),
    ]
    de = differential_evolution(chi2, bounds, seed=42,
                                maxiter=300, tol=1e-10, popsize=20)
    nm = minimize(chi2, de.x, method='Nelder-Mead',
                  options={'xatol': 1e-10, 'maxiter': 100000})
    per, t0, rp, a, inc, bl = nm.x
    return dict(period=per, t0=t0, rp_rs=rp, a_rs=a, inc=inc,
                baseline=bl, chi2=nm.fun,
                chi2_dof=nm.fun / max(len(time) - 6, 1))


def find_exoplanet_period(input_path, output_path, round_digits=5,
                          min_period=0.5, max_period=None,
                          sigma_upper=5.0, sigma_lower=5.0,
                          min_dur_hr=0.5, max_dur_hr=8.0):
    """End-to-end pipeline.

    1. Load & quality-filter
    2. Sigma-clip outliers
    3. Identify stellar rotation (Lomb-Scargle)
    4. Multi-window BLS (windows < stellar period), skip stellar harmonics
    5. Iterative transit-masked detrending + BLS refinement
    6. Batman model fit for precise period
    7. Robustness: repeat batman across detrending windows
    8. Write median period rounded to *round_digits*
    """
    print('Step 1: Load & filter')
    time, flux, ferr = load_and_filter(input_path)
    print(f'  {len(time)} pts, {time[-1]-time[0]:.2f} d baseline')

    print('Step 2: Outlier removal')
    time, flux, ferr = remove_outliers(time, flux, ferr,
                                       sigma_upper=sigma_upper,
                                       sigma_lower=sigma_lower)
    print(f'  {len(time)} pts remain')

    if max_period is None:
        max_period = (time[-1] - time[0]) / 2.0

    print('Step 3: Stellar rotation')
    sp, spow = identify_stellar_rotation(time, flux, ferr)
    print(f'  P_rot={sp:.4f} d  (LS power={spow:.4f})')

    print('Step 4: Multi-window BLS')
    cons_p, all_p = multi_window_bls(time, flux, ferr, sp,
                                      min_period=min_period,
                                      max_period=max_period,
                                      min_dur_hr=min_dur_hr,
                                      max_dur_hr=max_dur_hr)
    print(f'  consensus={cons_p:.6f}  all={[round(p,5) for p in all_p]}')

    cadence = np.median(np.diff(time))
    windows = _choose_detrend_windows(sp, cadence)
    mid_window = float(np.median(windows))

    print('Step 5: Iterative transit-masked BLS')
    # bootstrap t0
    d0, e0, _ = median_detrend(time, flux, ferr, mid_window)
    _, _, t0_init, _, _ = bls_search(time, d0, e0,
                                      min_period=cons_p*0.95,
                                      max_period=cons_p*1.05,
                                      min_dur_hr=min_dur_hr,
                                      max_dur_hr=max_dur_hr)
    p_it, t0_it = cons_p, t0_init
    for i in range(3):
        det, derr, _ = detrend_with_transit_mask(
            time, flux, ferr, p_it, t0_it, window_days=mid_window)
        p_it, _, t0_it, _ = refine_bls(time, det, derr, p_it,
                                         min_dur_hr=min_dur_hr,
                                         max_dur_hr=max_dur_hr)
        print(f'  iter {i+1}: P={p_it:.7f}')

    print('Step 6: Batman fit')
    n_exp = int((time[-1] - time[0]) / p_it) + 2
    near = np.zeros(len(time), dtype=bool)
    for n in range(-1, n_exp + 1):
        near |= np.abs(time - (t0_it + n * p_it)) < 0.2
    fr = fit_batman(time[near], det[near], derr[near], p_it, t0_it)
    print(f'  P={fr["period"]:.7f}  chi2/dof={fr["chi2_dof"]:.3f}')

    print('Step 7: Robustness')
    robust = []
    for w in windows:
        dr, er, _ = detrend_with_transit_mask(
            time, flux, ferr, fr['period'], fr['t0'], window_days=w)
        nr = np.zeros(len(time), dtype=bool)
        for n in range(-1, n_exp + 1):
            nr |= np.abs(time - (fr['t0'] + n * fr['period'])) < 0.2
        r = fit_batman(time[nr], dr[nr], er[nr], fr['period'], fr['t0'])
        robust.append(r['period'])
        print(f'  w={w:.3f}: P={r["period"]:.7f}  chi2/dof={r["chi2_dof"]:.4f}')

    final = float(np.median(robust))
    rounded = round(final, round_digits)
    print(f'Final: {final:.7f} -> {rounded}')
    with open(output_path, 'w') as f:
        f.write(f'{rounded}\n')
    return final


def validate_output(path, lo=0.1, hi=100.0):
    """Check output file: single number, within range, <= 5 decimals."""
    txt = open(path).read().strip()
    val = float(txt)
    assert lo < val < hi, f'{val} outside [{lo},{hi}]'
    parts = txt.split('.')
    if len(parts) == 2:
        assert len(parts[1]) <= 5, f'>{5} decimals'
    print(f'OK: {val} days')
    return val
