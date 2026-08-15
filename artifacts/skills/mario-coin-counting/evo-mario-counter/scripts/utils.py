import cv2
import numpy as np
import subprocess
import os
import glob
import pandas as pd


def extract_keyframes(video_path, output_dir, prefix="keyframes"):
    """
    Extract codec keyframes (I-frames) from a video file.
    Returns list of output file paths in timeline order.
    """
    output_pattern = os.path.join(output_dir, f"{prefix}_%03d.png")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", "select=eq(pict_type\\,I)",
        "-vsync", "vfr",
        output_pattern
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg stderr: {result.stderr}")
    
    files = sorted(glob.glob(os.path.join(output_dir, f"{prefix}_*.png")))
    print(f"Extracted {len(files)} keyframes: {[os.path.basename(f) for f in files]}")
    return files


def convert_to_grayscale_inplace(image_path):
    """
    Convert an image file from RGB to grayscale and overwrite it.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cv2.imwrite(image_path, gray)
    return image_path


def nms_detections(detections, min_dist_x, min_dist_y):
    """
    Non-maximum suppression on detections.
    Each detection is a tuple where index 0=x, 1=y, 2=primary_score.
    Keeps highest-scoring detection when two are within min_dist.
    """
    if len(detections) == 0:
        return []
    
    detections = sorted(detections, key=lambda d: d[2], reverse=True)
    
    keep = []
    for det in detections:
        x, y = det[0], det[1]
        is_duplicate = False
        for kept in keep:
            kx, ky = kept[0], kept[1]
            if abs(x - kx) < min_dist_x and abs(y - ky) < min_dist_y:
                is_duplicate = True
                break
        if not is_duplicate:
            keep.append(det)
    
    return keep


def count_objects(frame_path, template_path, threshold, debug=False,
                  use_sqdiff_filter=False, sqdiff_threshold=0.15):
    """
    Count occurrences of a template in a frame using template matching.
    Uses TM_CCOEFF_NORMED with non-maximum suppression.
    
    Optionally also checks TM_SQDIFF_NORMED to filter out structurally
    similar but visually different objects (e.g., question blocks vs coins).
    
    Args:
        frame_path: path to grayscale frame image
        template_path: path to template image (will be read as grayscale)
        threshold: minimum CCOEFF_NORMED score
        debug: print debug info
        use_sqdiff_filter: also require low SQDIFF_NORMED score
        sqdiff_threshold: maximum SQDIFF_NORMED score (lower = better match)
    
    Returns:
        count of detected objects
    """
    frame = cv2.imread(frame_path, cv2.IMREAD_GRAYSCALE)
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    
    if frame is None:
        raise ValueError(f"Cannot read frame: {frame_path}")
    if template is None:
        raise ValueError(f"Cannot read template: {template_path}")
    
    th, tw = template.shape[:2]
    fh, fw = frame.shape[:2]
    
    if th > fh or tw > fw:
        return 0
    
    result_ccoeff = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    max_val = result_ccoeff.max()
    
    if max_val < threshold:
        if debug:
            print(f"    max_ccoeff={max_val:.3f} < threshold={threshold}, count=0")
        return 0
    
    # Also compute SQDIFF if needed
    result_sqdiff = None
    if use_sqdiff_filter:
        result_sqdiff = cv2.matchTemplate(frame, template, cv2.TM_SQDIFF_NORMED)
    
    locs = np.where(result_ccoeff >= threshold)
    if len(locs[0]) == 0:
        return 0
    
    # Collect all detections with both scores
    raw_dets = []
    for y, x in zip(locs[0], locs[1]):
        ccoeff = result_ccoeff[y, x]
        sqdiff = result_sqdiff[y, x] if result_sqdiff is not None else 0.0
        raw_dets.append((x, y, ccoeff, sqdiff))
    
    # NMS based on CCOEFF score
    kept = nms_detections(raw_dets, tw, th)
    
    # Apply SQDIFF filter if enabled
    if use_sqdiff_filter:
        filtered = [d for d in kept if d[3] <= sqdiff_threshold]
        if debug:
            for d in kept:
                status = "KEEP" if d[3] <= sqdiff_threshold else "REJECT"
                print(f"      ({d[0]},{d[1]}) ccoeff={d[2]:.3f} sqdiff={d[3]:.3f} -> {status}")
        kept = filtered
    
    if debug:
        print(f"    max_ccoeff={max_val:.3f}, threshold={threshold}, count={len(kept)}")
        if not use_sqdiff_filter:
            for d in kept:
                print(f"      ({d[0]},{d[1]}) ccoeff={d[2]:.3f}")
    
    return len(kept)


def run_full_pipeline(video_path, output_dir, template_paths, csv_output_path,
                      coin_threshold=0.75, enemy_threshold=0.80, turtle_threshold=0.85,
                      coin_sqdiff_threshold=0.15,
                      debug=False):
    """
    End-to-end pipeline:
    1. Extract keyframes from video
    2. Convert to grayscale in place
    3. Count objects using template matching
    4. Write CSV results
    
    Args:
        video_path: path to input video
        output_dir: directory for keyframe images
        template_paths: dict with keys 'coin', 'enemy', 'turtle' -> paths
        csv_output_path: output CSV path
        coin_threshold: CCOEFF threshold for coins
        enemy_threshold: CCOEFF threshold for enemies
        turtle_threshold: CCOEFF threshold for turtles
        coin_sqdiff_threshold: SQDIFF threshold for coins (filters question blocks)
        debug: print debug info
    
    Returns:
        pandas DataFrame with results
    """
    # Step 1: Extract keyframes
    print("Step 1: Extracting keyframes...")
    keyframe_files = extract_keyframes(video_path, output_dir)
    print(f"  Extracted {len(keyframe_files)} keyframes")
    
    # Step 2: Verify templates exist
    print("Step 2: Verifying templates...")
    for name, path in template_paths.items():
        if not os.path.exists(path):
            raise FileNotFoundError(f"Template not found: {path}")
        img = cv2.imread(path)
        print(f"  {name}: {path} shape={img.shape}")
    
    # Step 3: Convert keyframes to grayscale in place
    print("Step 3: Converting keyframes to grayscale...")
    for kf in keyframe_files:
        convert_to_grayscale_inplace(kf)
        print(f"  Converted: {os.path.basename(kf)}")
    
    # Steps 4-5: Count objects in each frame
    print("Steps 4-5: Counting objects...")
    
    results = []
    for kf in keyframe_files:
        frame_id = kf
        if debug:
            print(f"  {os.path.basename(kf)}:")
        
        # Coins: use combined CCOEFF + SQDIFF to filter question blocks
        coins = count_objects(kf, template_paths['coin'], coin_threshold,
                            debug=debug, use_sqdiff_filter=True,
                            sqdiff_threshold=coin_sqdiff_threshold)
        
        # Enemies: use CCOEFF only
        enemies = count_objects(kf, template_paths['enemy'], enemy_threshold,
                              debug=debug)
        
        # Turtles: use CCOEFF only with high threshold
        turtles = count_objects(kf, template_paths['turtle'], turtle_threshold,
                              debug=debug)
        
        results.append({
            'frame_id': frame_id,
            'coins': coins,
            'enemies': enemies,
            'turtles': turtles
        })
        print(f"  {os.path.basename(kf)}: coins={coins}, enemies={enemies}, turtles={turtles}")
    
    # Step 6: Write CSV
    print("Step 6: Writing CSV...")
    df = pd.DataFrame(results)
    df.to_csv(csv_output_path, index=False)
    print(f"  Written to: {csv_output_path}")
    
    return df


def validate_output(csv_path, output_dir, prefix="keyframes"):
    """
    Validate the output CSV and keyframe files.
    """
    issues = []
    
    if not os.path.exists(csv_path):
        issues.append(f"CSV file not found: {csv_path}")
        return issues
    
    df = pd.read_csv(csv_path)
    
    expected_cols = ['frame_id', 'coins', 'enemies', 'turtles']
    for col in expected_cols:
        if col not in df.columns:
            issues.append(f"Missing column: {col}")
    
    if issues:
        return issues
    
    # Check frame_id format
    for idx, row in df.iterrows():
        fid = row['frame_id']
        if not fid.startswith(f"{output_dir}/{prefix}_"):
            issues.append(f"Frame ID format issue: {fid}")
        if not os.path.exists(fid):
            issues.append(f"Frame file not found: {fid}")
        else:
            img = cv2.imread(fid, cv2.IMREAD_UNCHANGED)
            if img is not None and len(img.shape) == 3:
                issues.append(f"Frame not single-channel grayscale: {fid}")
    
    # Check counts are non-negative integers
    for col in ['coins', 'enemies', 'turtles']:
        if (df[col] < 0).any():
            issues.append(f"Negative values in {col}")
    
    # Check timeline order
    frame_nums = []
    for fid in df['frame_id']:
        try:
            num = int(os.path.basename(fid).split('_')[-1].replace('.png', ''))
            frame_nums.append(num)
        except:
            issues.append(f"Cannot parse frame number from: {fid}")
    
    if frame_nums and frame_nums != sorted(frame_nums):
        issues.append("Frames not in timeline order")
    
    if not issues:
        print("Validation PASSED")
    else:
        print(f"Validation FAILED: {issues}")
    
    return issues
