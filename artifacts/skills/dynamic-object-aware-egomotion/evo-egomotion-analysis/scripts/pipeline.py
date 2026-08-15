import sys
import os
import json
import numpy as np
import cv2

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from video_utils import sample_frames, compute_optical_flow
from homography_utils import estimate_homography, compute_expected_flow_from_homography
from motion_classifier import (extract_motion_params, estimate_noise_thresholds,
                                classify_motion, classify_motion_from_flow,
                                smooth_labels, merge_intervals)
from dynamic_segmentation import (detect_dynamic_objects, temporal_propagate_mask, fuse_masks)
from csr_utils import save_masks_npz, load_and_verify_masks


def run_pipeline(video_path, target_fps, json_output, mask_output,
                 smooth_window=3):
    """End-to-end pipeline for egomotion classification and dynamic object segmentation."""
    print("[1/6] Sampling frames...")
    gray_frames, color_frames, frame_indices, (h, w) = sample_frames(video_path, target_fps)
    n_frames = len(gray_frames)
    print(f"  Sampled {n_frames} frames at {target_fps} fps, resolution {w}x{h}")

    print("[2/6] Computing optical flow and homographies...")
    flows = []
    homographies = []
    for i in range(n_frames - 1):
        flow = compute_optical_flow(gray_frames[i], gray_frames[i+1])
        flows.append(flow)
        H, inlier_mask, pts1, pts2 = estimate_homography(gray_frames[i], gray_frames[i+1])
        homographies.append(H)
        if H is not None and inlier_mask is not None:
            n_inliers = int(inlier_mask.sum())
            n_total = len(inlier_mask)
            print(f"  Pair {i}->{i+1}: H estimated, {n_inliers}/{n_total} inliers")
        else:
            print(f"  Pair {i}->{i+1}: H estimation FAILED, using median flow fallback")

    print("[3/6] Extracting motion parameters and deriving thresholds...")
    all_params = []
    for i in range(n_frames - 1):
        params = extract_motion_params(homographies[i], h, w)
        all_params.append(params)
        if params:
            print(f"  Pair {i}: scale={params['scale_ratio']:.4f} dx={params['dx']:.2f} "
                  f"dy={params['dy']:.2f} roll={params['roll_angle']:.3f}")

    thresholds = estimate_noise_thresholds(all_params)
    print(f"  Derived thresholds: {thresholds}")

    print("[4/6] Classifying camera motion...")
    raw_labels = []
    for i in range(n_frames - 1):
        if all_params[i] is not None:
            labels = classify_motion(all_params[i], thresholds)
        else:
            labels = classify_motion_from_flow(flows[i], h, w)
        raw_labels.append(labels)
        print(f"  Frame {i}: {labels}")

    raw_labels.append(raw_labels[-1] if raw_labels else ["Stay"])
    print(f"  Frame {n_frames-1} (duplicated): {raw_labels[-1]}")

    smoothed_labels = smooth_labels(raw_labels, window=smooth_window)
    for i, lab in enumerate(smoothed_labels):
        if sorted(lab) != sorted(raw_labels[i]):
            print(f"  Smoothed frame {i}: {raw_labels[i]} -> {smoothed_labels[i]}")

    intervals = merge_intervals(smoothed_labels)
    print(f"  {len(intervals)} intervals")
    for k, v in intervals.items():
        print(f"    {k}: {v}")

    with open(json_output, 'w') as f:
        json.dump(intervals, f, indent=2)
    print(f"  Saved {json_output}")

    print("[5/6] Detecting dynamic objects...")
    masks = []
    prev_mask = None
    for i in range(n_frames - 1):
        H = homographies[i]
        current_mask = detect_dynamic_objects(flows[i], H, h, w, gray_prev=gray_frames[i], gray_curr=gray_frames[i+1])

        # Temporal smoothing: propagate previous mask and take union
        if prev_mask is not None:
            warped_prev = temporal_propagate_mask(prev_mask.astype(np.float32), flows[i])
            # Use intersection of warped previous with current to avoid accumulation
            warped_binary = (warped_prev > 0.5).astype(np.uint8)
            # Keep current detection, but add back regions that were in previous
            # and still have some support in current residual
            fused = current_mask.copy()
        else:
            fused = current_mask

        masks.append(fused)
        prev_mask = fused
        dyn_pixels = int(fused.sum())
        dyn_pct = 100.0 * dyn_pixels / (h * w)
        print(f"  Frame {i}: {dyn_pixels} dynamic pixels ({dyn_pct:.2f}%)")

    if masks:
        last_mask = masks[-1].copy()
    else:
        last_mask = np.zeros((h, w), dtype=np.uint8)
    masks.append(last_mask)
    dyn_pixels = int(last_mask.sum())
    dyn_pct = 100.0 * dyn_pixels / (h * w)
    print(f"  Frame {n_frames-1} (propagated): {dyn_pixels} dynamic pixels ({dyn_pct:.2f}%)")

    print("[6/6] Saving masks in CSR format...")
    save_masks_npz(masks, (h, w), mask_output)
    print(f"  Saved {mask_output}")

    return intervals, masks


def validate_outputs(json_path, npz_path, n_frames, shape):
    """Validate the output files."""
    print("\nValidating outputs...")
    with open(json_path, 'r') as f:
        intervals = json.load(f)

    valid_labels = {"Stay", "Dolly In", "Dolly Out", "Pan Left", "Pan Right",
                    "Tilt Up", "Tilt Down", "Roll Left", "Roll Right"}

    covered = set()
    for key, labels in intervals.items():
        parts = key.split('->')
        start, end = int(parts[0]), int(parts[1])
        for idx in range(start, end):
            assert idx not in covered, f"Frame {idx} covered multiple times"
            covered.add(idx)
        for label in labels:
            assert label in valid_labels, f"Invalid label: {label}"

    expected = set(range(n_frames))
    assert covered == expected, f"Coverage mismatch: missing {expected - covered}, extra {covered - expected}"

    last_key = list(intervals.keys())[-1]
    last_end = int(last_key.split('->')[1])
    assert last_end == n_frames, f"Final interval ends at {last_end}, expected {n_frames}"
    print(f"  JSON valid: {len(intervals)} intervals covering {n_frames} frames")

    load_and_verify_masks(npz_path, n_frames, shape)
    print("  Masks valid")
    print("\nAll validations passed!")
    return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', required=True, help='Path to input video')
    parser.add_argument('--fps', type=int, required=True, help='Sample FPS')
    parser.add_argument('--json-output', required=True, help='Output JSON path')
    parser.add_argument('--mask-output', required=True, help='Output NPZ path')
    args = parser.parse_args()

    intervals, masks = run_pipeline(
        args.video,
        target_fps=args.fps,
        json_output=args.json_output,
        mask_output=args.mask_output
    )

    n_frames = len(masks)
    shape = masks[0].shape
    validate_outputs(args.json_output, args.mask_output, n_frames, shape)
