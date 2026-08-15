import cv2
import numpy as np


def decompose_homography_proper(H, h, w):
    """Decompose homography using cv2.decomposeHomographyMat.
    Returns (roll_deg, pitch_deg, yaw_deg, translation) for the most plausible solution."""
    H_norm = H / (H[2, 2] + 1e-10)
    fx = w
    fy = w
    K = np.array([[fx, 0, w/2.0], [0, fy, h/2.0], [0, 0, 1]], dtype=np.float64)
    try:
        n_solutions, rotations, translations, normals = cv2.decomposeHomographyMat(H_norm, K)
    except:
        return None
    best = None
    best_score = float('inf')
    for j in range(n_solutions):
        R = rotations[j]
        t = translations[j].flatten()
        sy = np.sqrt(R[0,0]**2 + R[1,0]**2)
        roll = np.degrees(np.arctan2(R[2,1], R[2,2]))
        pitch = np.degrees(np.arctan2(-R[2,0], sy))
        yaw = np.degrees(np.arctan2(R[1,0], R[0,0]))
        score = abs(roll) + abs(pitch) + abs(yaw)
        if score < best_score:
            best_score = score
            best = (roll, pitch, yaw, t)
    return best


def extract_motion_params(H, h, w):
    """Extract scale_ratio, dx, dy, roll_angle from homography."""
    if H is None:
        return None
    cx, cy = w / 2.0, h / 2.0
    test_pts = np.array([
        [w * 0.25, h * 0.25], [w * 0.75, h * 0.25],
        [w * 0.25, h * 0.75], [w * 0.75, h * 0.75]
    ], dtype=np.float32)
    ones = np.ones((4, 1), dtype=np.float32)
    pts_h = np.hstack([test_pts, ones])
    transformed = (H @ pts_h.T).T
    transformed_xy = transformed[:, :2] / (transformed[:, 2:3] + 1e-10)
    dist_before = np.sqrt((test_pts[:, 0] - cx)**2 + (test_pts[:, 1] - cy)**2)
    dist_after = np.sqrt((transformed_xy[:, 0] - cx)**2 + (transformed_xy[:, 1] - cy)**2)
    scale_ratio = np.median(dist_after / (dist_before + 1e-10))

    center = np.array([[cx, cy, 1.0]], dtype=np.float64)
    ct = (H @ center.T).T
    ct_xy = ct[0, :2] / (ct[0, 2] + 1e-10)
    dx = ct_xy[0] - cx
    dy = ct_xy[1] - cy

    roll_angle = 0.0
    decomp = decompose_homography_proper(H, h, w)
    if decomp is not None:
        roll_angle = decomp[0]
    else:
        H_norm = H / (H[2, 2] + 1e-10)
        roll_angle = np.degrees(np.arctan2(H_norm[1, 0] - H_norm[0, 1],
                                            H_norm[0, 0] + H_norm[1, 1]))
    return {'scale_ratio': scale_ratio, 'dx': dx, 'dy': dy, 'roll_angle': roll_angle}


def _estimate_axis_threshold(values):
    """Estimate a per-axis classification threshold purely from the data.

    Uses sign consistency to decide whether the axis carries real directed
    motion or is dominated by estimation noise.

    - sign_frac = fraction of values sharing the majority sign
    - When sign_frac -> 1.0 (consistent direction), the motion is real:
      threshold is the midpoint between zero and the minimum observed
      |value|, so every frame is classified.
    - When sign_frac -> 0.5 (random sign), the values are noise:
      threshold is placed above the maximum observed |value| plus the
      interquartile spread, so nothing is classified.
    - Intermediate sign_frac: linearly interpolate between the two.
    """
    arr = np.array(values, dtype=np.float64)
    n = len(arr)
    if n < 2:
        # Single observation: threshold at the midpoint between 0 and |value|
        return abs(arr[0]) / 2.0 if n == 1 else 0.0

    abs_arr = np.abs(arr)
    min_abs = float(np.min(abs_arr))
    max_abs = float(np.max(abs_arr))
    q25 = float(np.percentile(abs_arr, 25))
    q75 = float(np.percentile(abs_arr, 75))
    iqr = q75 - q25

    # Sign consistency
    n_pos = int(np.sum(arr > 0))
    n_neg = int(np.sum(arr < 0))
    n_nonzero = n_pos + n_neg
    if n_nonzero == 0:
        return 0.0
    sign_frac = max(n_pos, n_neg) / n_nonzero

    # Weight: 0 at sign_frac=0.5 (noise), 1 at sign_frac=1.0 (signal)
    w = (sign_frac - 0.5) * 2.0
    w = float(np.clip(w, 0.0, 1.0))

    # Signal case: midpoint between zero and the weakest observed magnitude
    signal_thresh = min_abs / 2.0

    # Noise case: above the strongest observation plus the data spread (IQR)
    noise_thresh = max_abs + max(iqr, max_abs / n)

    thresh = w * signal_thresh + (1.0 - w) * noise_thresh
    return thresh


def estimate_noise_thresholds(all_params):
    """Estimate motion thresholds from the distribution of motion parameters.

    For each axis, uses sign consistency and data spread to derive whether
    observed values represent consistent real motion or estimation noise.
    When only one observation is available, thresholds are derived from
    that single observation's magnitude.
    """
    valid = [p for p in all_params if p is not None]
    if not valid:
        # No valid observations: return zero thresholds (everything is Stay)
        return {'scale_thresh': float('inf'), 'pan_thresh': float('inf'),
                'tilt_thresh': float('inf'), 'roll_thresh': float('inf')}

    scale_devs = [p['scale_ratio'] - 1.0 for p in valid]
    dxs = [p['dx'] for p in valid]
    dys = [p['dy'] for p in valid]
    rolls = [p['roll_angle'] for p in valid]

    return {
        'scale_thresh': _estimate_axis_threshold(scale_devs),
        'pan_thresh': _estimate_axis_threshold(dxs),
        'tilt_thresh': _estimate_axis_threshold(dys),
        'roll_thresh': _estimate_axis_threshold(rolls)
    }


def classify_motion(params, thresholds):
    """Classify camera motion given extracted parameters and derived thresholds."""
    if params is None:
        return ["Stay"]
    labels = []
    sr = params['scale_ratio']
    dx = params['dx']
    dy = params['dy']
    roll = params['roll_angle']
    st = thresholds['scale_thresh']
    pt = thresholds['pan_thresh']
    tt = thresholds['tilt_thresh']
    rt = thresholds['roll_thresh']

    if sr > 1.0 + st:
        labels.append("Dolly In")
    elif sr < 1.0 - st:
        labels.append("Dolly Out")

    if abs(dx) > pt:
        labels.append("Pan Left" if dx > 0 else "Pan Right")

    if abs(dy) > tt:
        labels.append("Tilt Up" if dy > 0 else "Tilt Down")

    if abs(roll) > rt:
        labels.append("Roll Left" if roll > 0 else "Roll Right")

    if not labels:
        labels.append("Stay")
    return labels


def classify_motion_from_flow(flow, h, w):
    """Fallback: classify motion from median optical flow when homography fails.
    Threshold is derived from the flow magnitude itself."""
    median_flow = np.median(flow.reshape(-1, 2), axis=0)
    dx, dy = float(median_flow[0]), float(median_flow[1])
    flow_mag = np.sqrt(dx**2 + dy**2)
    # Use the smaller component as noise floor for the larger
    min_comp = min(abs(dx), abs(dy))
    max_comp = max(abs(dx), abs(dy))
    # Threshold: midpoint between the two components
    # If both are similar, both are real; if one is much smaller, it's noise
    thresh = (min_comp + max_comp) / 4.0 if max_comp > 0 else 0.0
    labels = []
    if abs(dx) > thresh and abs(dx) > 0:
        labels.append("Pan Right" if dx < 0 else "Pan Left")
    if abs(dy) > thresh and abs(dy) > 0:
        labels.append("Tilt Down" if dy < 0 else "Tilt Up")
    if not labels:
        labels.append("Stay")
    return labels


def smooth_labels(all_labels, window=3):
    """Apply temporal smoothing to motion labels using majority voting."""
    n = len(all_labels)
    if n <= 2:
        return all_labels
    half = window // 2
    smoothed = []
    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        label_counts = {}
        for j in range(start, end):
            key = tuple(sorted(all_labels[j]))
            label_counts[key] = label_counts.get(key, 0) + 1
        best = max(label_counts, key=label_counts.get)
        smoothed.append(list(best))
    return smoothed


def merge_intervals(all_labels):
    """Merge consecutive frames with identical labels into intervals."""
    if not all_labels:
        return {}
    intervals = {}
    current_labels = all_labels[0]
    start_idx = 0
    for i in range(1, len(all_labels)):
        if sorted(all_labels[i]) != sorted(current_labels):
            key = f"{start_idx}->{i}"
            intervals[key] = current_labels
            current_labels = all_labels[i]
            start_idx = i
    key = f"{start_idx}->{len(all_labels)}"
    intervals[key] = current_labels
    return intervals
