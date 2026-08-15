import cv2
import numpy as np

def sample_frames(video_path, target_fps=5):
    """Sample frames from video at target fps. Returns list of grayscale frames and color frames."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    
    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_interval = orig_fps / target_fps
    
    gray_frames = []
    color_frames = []
    frame_indices = []
    
    i = 0.0
    while int(round(i)) < total_frames:
        idx = int(round(i))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            break
        color_frames.append(frame)
        gray_frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        frame_indices.append(idx)
        i += sample_interval
    
    cap.release()
    
    h, w = gray_frames[0].shape[:2]
    return gray_frames, color_frames, frame_indices, (h, w)


def compute_optical_flow(gray1, gray2):
    """Compute dense optical flow using Farneback method."""
    flow = cv2.calcOpticalFlowFarneback(
        gray1, gray2, None,
        pyr_scale=0.5, levels=3, winsize=15,
        iterations=3, poly_n=5, poly_sigma=1.2,
        flags=0
    )
    return flow


def compute_backward_flow(gray1, gray2):
    """Compute backward optical flow (from gray2 to gray1)."""
    return compute_optical_flow(gray2, gray1)
