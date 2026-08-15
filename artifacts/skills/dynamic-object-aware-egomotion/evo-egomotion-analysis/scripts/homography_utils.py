import cv2
import numpy as np

def estimate_homography(gray1, gray2, max_features=2000, ransac_thresh=3.0):
    """Estimate homography between two frames using ORB features + RANSAC.
    Returns (H, inlier_mask, kp1_pts, kp2_pts) or (None, None, None, None) if insufficient matches."""
    orb = cv2.ORB_create(nfeatures=max_features)
    kp1, des1 = orb.detectAndCompute(gray1, None)
    kp2, des2 = orb.detectAndCompute(gray2, None)
    
    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        return None, None, None, None
    
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    
    if len(matches) < 4:
        return None, None, None, None
    
    # Sort by distance
    matches = sorted(matches, key=lambda m: m.distance)
    
    pts1 = np.float32([kp1[m.queryIdx].pt for m in matches])
    pts2 = np.float32([kp2[m.trainIdx].pt for m in matches])
    
    H, mask = cv2.findHomography(pts1, pts2, cv2.RANSAC, ransac_thresh)
    
    if H is None:
        return None, None, pts1, pts2
    
    return H, mask, pts1, pts2


def compute_expected_flow_from_homography(H, h, w):
    """Compute the expected flow field from homography H for an image of size (h, w).
    Returns flow array of shape (h, w, 2)."""
    # Create grid of pixel coordinates
    y_coords, x_coords = np.mgrid[0:h, 0:w].astype(np.float32)
    
    # Apply homography to all pixels
    ones = np.ones_like(x_coords)
    coords = np.stack([x_coords, y_coords, ones], axis=-1)  # (h, w, 3)
    coords_flat = coords.reshape(-1, 3).T  # (3, h*w)
    
    transformed = H @ coords_flat  # (3, h*w)
    transformed = transformed / (transformed[2:3, :] + 1e-10)  # projective division
    
    new_x = transformed[0].reshape(h, w)
    new_y = transformed[1].reshape(h, w)
    
    expected_flow = np.stack([new_x - x_coords, new_y - y_coords], axis=-1)
    return expected_flow.astype(np.float32)
