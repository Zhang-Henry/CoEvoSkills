"""Detect opening and pause segments to remove from a teaching video.

All decision thresholds are derived from the input data at runtime.
Tunable parameters are exposed as function arguments with defaults
justified by signal-processing conventions (not tuned to any single recording).
"""
import numpy as np
from scipy.ndimage import median_filter


def _block_frame_diffs(frame_diffs, frames_fps, block_sec):
    """Average frame diffs into time blocks."""
    block_size = max(1, int(block_sec * frames_fps))
    n = len(frame_diffs) // block_size
    return np.array([
        np.mean(frame_diffs[i * block_size:(i + 1) * block_size])
        for i in range(n)
    ])


def _find_static_threshold(block_means):
    """Derive a threshold separating truly-static blocks from active ones.

    Scans sorted block-mean values for the largest multiplicative gap
    in the lower half of the distribution.  A gap >= 1.5x indicates a
    natural separation between near-zero-motion blocks and blocks with
    real visual activity.  If no clear gap exists, falls back to the
    lower-quartile boundary.

    Returns the threshold value.
    """
    sorted_bm = np.sort(block_means)
    lower = sorted_bm[:len(sorted_bm) // 2 + 1]
    if len(lower) < 2:
        return float(np.median(block_means))

    best_ratio, best_val = 1.0, None
    for i in range(1, len(lower)):
        prev = lower[i - 1]
        if prev > 0.01:
            r = lower[i] / prev
        else:
            r = lower[i] + 1.0
        if r > best_ratio:
            best_ratio, best_val = r, lower[i]

    if best_val is not None and best_ratio > 1.5:
        return float(best_val)
    return float(np.percentile(block_means, 25))


def _find_energy_drop(energies, window_sec, start_idx, end_idx,
                      context_sec=5.0, min_drop_ratio=0.6):
    """Find the largest relative energy drop in a search region.

    Slides a window and compares the median energy before vs after each
    candidate split point.  Returns (index, ratio) of the best drop,
    or (None, 1.0) if none exceeds *min_drop_ratio*.

    Parameters
    ----------
    context_sec : float
        How many seconds of context to use on each side of the split.
    min_drop_ratio : float
        Maximum after/before ratio to accept as a real transition.
    """
    if start_idx >= end_idx:
        return None, 1.0
    seg = energies[start_idx:end_idx]
    ctx = max(4, int(context_sec / window_sec))
    best_idx, best_ratio = None, 1.0
    floor = np.percentile(seg, 10)
    for i in range(ctx, len(seg) - ctx):
        before = np.median(seg[max(0, i - 2 * ctx):i])
        after = np.median(seg[i:i + 2 * ctx])
        if before > floor:
            r = after / before
            if r < best_ratio:
                best_ratio, best_idx = r, i
    if best_idx is not None and best_ratio < min_drop_ratio:
        return start_idx + best_idx, best_ratio
    return None, 1.0


def detect_opening(audio, sr, frames, frames_fps, window_sec=0.25,
                   block_sec=5.0, context_sec=5.0, min_drop_ratio=0.6,
                   refine_sec=3.0):
    """Detect the opening (non-teaching content) at the video start.

    Combines visual static-frame analysis with audio energy transition.

    Parameters
    ----------
    window_sec : float
        RMS energy window length.
    block_sec : float
        Frame-diff averaging block length.
    context_sec : float
        Context window for energy-drop detection.
    min_drop_ratio : float
        Maximum after/before energy ratio to accept as a transition.
    refine_sec : float
        Radius around the candidate boundary to search for a local
        energy minimum.

    Returns
    -------
    float  –  opening end time in seconds, or 0.0 if none detected.
    """
    from utils import compute_rms_energy, compute_frame_diffs

    energies = compute_rms_energy(audio, sr, window_sec)
    total_dur = len(audio) / sr
    frame_diffs = compute_frame_diffs(frames)
    block_means = _block_frame_diffs(frame_diffs, frames_fps, block_sec)
    if len(block_means) < 3:
        return 0.0

    # --- visual: contiguous truly-static prefix ---
    threshold = _find_static_threshold(block_means)
    static_end_block = 0
    for i in range(len(block_means)):
        if block_means[i] < threshold:
            static_end_block = i + 1
        else:
            break
    static_end_t = static_end_block * block_sec

    # --- audio: energy transition ---
    search_start = max(0, int((static_end_t - 2 * block_sec) / window_sec))
    search_end = min(len(energies),
                     int(min(total_dur * 0.5,
                             static_end_t + total_dur * 0.25) / window_sec))

    drop_idx, drop_ratio = _find_energy_drop(
        energies, window_sec, search_start, search_end,
        context_sec, min_drop_ratio)

    if drop_idx is not None:
        opening_end = drop_idx * window_sec
    elif static_end_t >= block_sec:
        opening_end = static_end_t
    else:
        # No visual static prefix and no audio drop → try audio-only
        drop_idx2, _ = _find_energy_drop(
            energies, window_sec, 0,
            min(len(energies), int(total_dur * 0.5 / window_sec)),
            context_sec, min_drop_ratio)
        if drop_idx2 is not None:
            opening_end = drop_idx2 * window_sec
            if opening_end < block_sec:
                return 0.0
        else:
            return 0.0

    # refine to local energy minimum
    r = int(refine_sec / window_sec)
    lo = max(0, int(opening_end / window_sec) - r)
    hi = min(len(energies), int(opening_end / window_sec) + r)
    if hi > lo:
        opening_end = (lo + int(np.argmin(energies[lo:hi]))) * window_sec

    return round(opening_end, 2) if opening_end >= block_sec else 0.0


def detect_pauses(audio, sr, content_start, window_sec=0.25,
                  min_pause_sec=2.0, local_window_sec=30.0):
    """Detect pause segments in the teaching portion of the audio.

    Three complementary, data-driven strategies whose thresholds are
    derived from the energy distribution of the teaching content:

    1. Adaptive local windows – threshold is the higher of a local
       estimate and a global floor so that pauses in quiet regions
       are not missed.
    2. Global percentile threshold – midpoint of the 10th and 25th
       percentiles of teaching energy.
    3. Running-median ratio – flags windows whose energy is a small
       fraction of the local smoothed baseline.

    Parameters
    ----------
    content_start : float
        Time (seconds) where teaching content begins.
    min_pause_sec : float
        Minimum pause duration to report.
    local_window_sec : float
        Context length for local adaptive thresholding.
    """
    from utils import compute_rms_energy

    energies = compute_rms_energy(audio, sr, window_sec)
    total_dur = len(audio) / sr
    si = int(content_start / window_sec)
    teach = energies[si:]
    if len(teach) == 0:
        return []

    g_med = np.median(teach)
    g_p10 = np.percentile(teach, 10)
    g_p25 = np.percentile(teach, 25)
    pause_thresh = (g_p10 + g_p25) / 2.0
    lw = max(4, int(min(local_window_sec, (total_dur - content_start) / 4) / window_sec))

    pauses = []

    def _scan(arr, thresh, offset):
        """Scan an energy array for contiguous sub-threshold runs."""
        segs = []
        in_p, ps = False, 0
        for i in range(len(arr)):
            if arr[i] < thresh and not in_p:
                ps, in_p = i, True
            elif (arr[i] >= thresh or i == len(arr) - 1) and in_p:
                d = (i - ps) * window_sec
                if d >= min_pause_sec:
                    segs.append(((offset + ps) * window_sec,
                                 (offset + i) * window_sec, d))
                in_p = False
        return segs

    # Strategy 1 – adaptive local
    for ws in range(si, len(energies), lw):
        we = min(ws + lw, len(energies))
        le = energies[ws:we]
        if len(le) < 4:
            continue
        lm = np.median(le)
        eff = max(pause_thresh,
                  lm * (g_p10 / g_med) if g_med > 0 else 0)
        pauses.extend(_scan(le, eff, ws))

    # Strategy 2 – global
    pauses.extend(_scan(teach, pause_thresh, si))

    # Strategy 3 – running-median ratio
    if len(energies) > lw:
        sm = median_filter(energies, size=lw)
        ratio = energies / (sm + 1e-10)
        dr = max(0.1, min(0.5, g_p10 / g_med)) if g_med > 0 else 0.3
        in_d, ds = False, 0
        for i in range(si, len(ratio)):
            if ratio[i] < dr and not in_d:
                ds, in_d = i, True
            elif (ratio[i] >= dr or i == len(ratio) - 1) and in_d:
                d = (i - ds) * window_sec
                if d >= min_pause_sec:
                    pauses.append((ds * window_sec, i * window_sec, d))
                in_d = False

    pauses = merge_segments(pauses)
    return [(s, e, d) for s, e, d in pauses if s >= content_start + 0.5]


def merge_segments(segments, gap=0.5):
    """Merge overlapping or nearly-adjacent segments.

    Parameters
    ----------
    gap : float
        Maximum gap (seconds) between segments to merge.
    """
    if not segments:
        return []
    segments = sorted(segments, key=lambda x: x[0])
    merged = [segments[0]]
    for s, e, d in segments[1:]:
        ps, pe, _ = merged[-1]
        if s <= pe + gap:
            ne = max(pe, e)
            merged[-1] = (ps, ne, ne - ps)
        else:
            merged.append((s, e, d))
    return merged


def get_segments_to_remove(audio, sr, frames, frames_fps,
                           window_sec=0.25, min_pause_sec=2.0,
                           local_window_sec=30.0,
                           block_sec=5.0, context_sec=5.0,
                           min_drop_ratio=0.6, refine_sec=3.0):
    """Detect all segments to remove (opening + pauses).

    All parameters are forwarded to the underlying detectors.

    Returns
    -------
    (segments, opening_end)
        segments : list of (start, end, duration)
        opening_end : float
    """
    opening_end = detect_opening(
        audio, sr, frames, frames_fps, window_sec,
        block_sec, context_sec, min_drop_ratio, refine_sec)

    segs = []
    if opening_end > 0:
        segs.append((0.0, opening_end, opening_end))

    segs.extend(detect_pauses(
        audio, sr, opening_end, window_sec,
        min_pause_sec, local_window_sec))

    return merge_segments(segs), opening_end
