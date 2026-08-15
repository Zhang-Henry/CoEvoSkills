import cv2
import numpy as np


def compute_flow_residual(actual_flow, expected_flow):
    """Compute residual between actual and expected flow."""
    residual = actual_flow - expected_flow
    magnitude = np.sqrt(residual[:, :, 0]**2 + residual[:, :, 1]**2)
    return magnitude, residual


def compute_median_flow_residual(actual_flow):
    """Compute residual from median flow (fallback when no homography)."""
    median_flow = np.median(actual_flow.reshape(-1, 2), axis=0)
    expected = np.zeros_like(actual_flow)
    expected[:, :, 0] = median_flow[0]
    expected[:, :, 1] = median_flow[1]
    return compute_flow_residual(actual_flow, expected)


def derive_dynamic_threshold(magnitude):
    """Derive adaptive threshold from residual magnitude distribution.
    Uses median + k * std where k is derived from the distribution shape."""
    med = float(np.median(magnitude))
    std = float(np.std(magnitude))
    mean = float(np.mean(magnitude))

    if med < 1e-6:
        return std

    skew_ratio = mean / med
    # Map skew to k: more skewed -> lower k
    # For a Gaussian, mean/median ~ 1.25, so base = 2*1.25 = 2.5
    # gives k ~ 2.0 for Gaussian
    k = (2 * 1.25) / max(skew_ratio, 0.5)
    k = np.clip(k, 1.5, 3.0)

    thresh = med + k * std
    return thresh


def create_spatial_weight_map(h, w, edge_margin_frac=0.02):
    """Create spatial weight map that downweights image edges."""
    weight = np.ones((h, w), dtype=np.float32)
    margin_x = max(int(w * edge_margin_frac), 2)
    margin_y = max(int(h * edge_margin_frac), 2)
    for i in range(margin_x):
        f = i / margin_x
        weight[:, i] *= f
        weight[:, w - 1 - i] *= f
    for i in range(margin_y):
        f = i / margin_y
        weight[i, :] *= f
        weight[h - 1 - i, :] *= f
    return weight


def _derive_morph_kernel_size(h, w, purpose='open'):
    """Derive morphological kernel size from image resolution."""
    dim = min(h, w)
    if purpose == 'open':
        k = max(3, dim // 150)
    else:
        k = max(5, dim // 70)
    if k % 2 == 0:
        k += 1
    return k


def _derive_min_component_area(h, w):
    """Derive minimum connected component area from image dimensions."""
    dim = min(h, w)
    side = max(dim // 100, 3)
    return side * side


def detect_dynamic_objects(actual_flow, H, h, w,
                           gray_prev=None, gray_curr=None,
                           use_spatial_weight=True):
    """Detect dynamic objects using both flow residuals and aligned frame difference.
    
    Combines two signals:
    1. Flow residual from homography (or median flow)
    2. Aligned frame difference (warp prev frame with H, diff with current)
    
    The intersection of both signals gives more reliable dynamic detection.
    """
    # Signal 1: Flow residual
    if H is not None:
        from homography_utils import compute_expected_flow_from_homography
        expected_flow = compute_expected_flow_from_homography(H, h, w)
        magnitude, _ = compute_flow_residual(actual_flow, expected_flow)
    else:
        magnitude, _ = compute_median_flow_residual(actual_flow)

    if use_spatial_weight:
        weight_map = create_spatial_weight_map(h, w)
        magnitude = magnitude * weight_map

    flow_thresh = derive_dynamic_threshold(magnitude)
    flow_mask = (magnitude > flow_thresh).astype(np.uint8)

    # Signal 2: Aligned frame difference (if grayscale frames provided)
    if gray_prev is not None and gray_curr is not None and H is not None:
        warped = cv2.warpPerspective(gray_prev, H, (w, h))
        aligned_diff = cv2.absdiff(warped, gray_curr).astype(np.float32)
        
        if use_spatial_weight:
            aligned_diff = aligned_diff * weight_map
        
        # Adaptive threshold for aligned difference
        diff_thresh = derive_dynamic_threshold(aligned_diff)
        diff_mask = (aligned_diff > diff_thresh).astype(np.uint8)
        
        # Combine: union of both signals for better recall
        # Both signals detect different aspects of dynamic objects
        combined_mask = np.maximum(flow_mask, diff_mask)
    else:
        combined_mask = flow_mask

    # Morphological cleanup
    open_k = _derive_morph_kernel_size(h, w, 'open')
    close_k = _derive_morph_kernel_size(h, w, 'close')
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (open_k, open_k))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
    combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel_open)
    combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel_close)

    # Connected component filtering
    min_area = _derive_min_component_area(h, w)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(combined_mask, connectivity=8)
    clean_mask = np.zeros_like(combined_mask)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            clean_mask[labels == i] = 1

    return clean_mask


def temporal_propagate_mask(prev_mask, flow, decay=0.6):
    """Propagate previous mask using optical flow for temporal consistency."""
    h, w = prev_mask.shape[:2]
    y_coords, x_coords = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = x_coords - flow[:, :, 0]
    map_y = y_coords - flow[:, :, 1]
    warped = cv2.remap(prev_mask.astype(np.float32), map_x, map_y,
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    warped = (warped * decay).clip(0, 1)
    return warped


def fuse_masks(current_detection, warped_prev):
    """Fuse current detection with temporally propagated mask using Otsu."""
    n_current = int(current_detection.sum())
    n_warped = int((warped_prev > 0).sum())
    total_evidence = n_current + n_warped
    if total_evidence == 0:
        return current_detection.copy()

    cw = max(n_current / (total_evidence + 1), 0.5)
    fused_raw = cw * current_detection.astype(np.float32) + (1.0 - cw) * warped_prev

    fused_scaled = (fused_raw * 255).clip(0, 255).astype(np.uint8)
    if fused_scaled.max() == 0:
        return np.zeros_like(current_detection)
    _, binary = cv2.threshold(fused_scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return (binary > 0).astype(np.uint8)
