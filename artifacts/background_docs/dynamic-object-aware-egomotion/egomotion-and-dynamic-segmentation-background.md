# Egomotion Estimation and Dynamic Object Segmentation from Video

This document provides background on camera motion (egomotion) classification and dynamic object detection from monocular video, covering the optical flow and geometric reasoning foundations needed to solve both problems jointly.

## Video Sampling and Frame Representation

When processing video for motion analysis, continuous footage is typically downsampled to a target frame rate (e.g., 6 fps) to reduce computational cost while retaining enough temporal resolution for reliable motion estimation. The sampling procedure reads the original video, computes a frame interval from the ratio of original fps to target fps, and extracts every Nth frame. Frames are converted to grayscale for optical flow and feature matching, since color information is unnecessary for motion geometry.

The number of sampled frames determines the temporal granularity of all downstream outputs. Motion labels and dynamic masks are produced per consecutive pair of sampled frames, meaning N sampled frames yield N-1 pairwise analyses (with the last frame typically duplicating the previous result to maintain a one-to-one frame-to-output correspondence).

## Optical Flow: Measuring Pixel-Level Motion

Optical flow computes a 2D displacement vector (dx, dy) for every pixel between two consecutive frames, capturing apparent motion in the image plane. Dense optical flow methods such as Farneback produce a flow field of the same spatial dimensions as the input frame, with two channels representing horizontal and vertical displacement.

Key properties of optical flow relevant to this domain:

- **Camera motion produces global flow patterns.** When only the camera moves (no independently moving objects), every pixel's displacement is determined by the camera's 3D motion and scene geometry. For example, a pure rightward pan shifts all pixels leftward; a dolly-in produces a radial expansion pattern emanating from the focus of expansion.
- **Dynamic objects produce local flow anomalies.** Independently moving objects have displacements that deviate from the global camera-induced pattern. The magnitude and direction of this deviation depend on both the object's own motion and the camera motion.
- **Flow estimation is noisy.** Textureless regions, occlusion boundaries, and motion blur all degrade flow accuracy. Robust downstream processing must account for this.

Farneback optical flow uses polynomial expansion to approximate local neighborhoods, operating at multiple pyramid levels to handle large displacements. Typical parameters include a pyramid scale of 0.5, 3 pyramid levels, a window size of 15 pixels, and 3 iterations per level.

## Geometric Camera Models: Homography and Affine Transforms

For scenes where the camera rotates or the scene is approximately planar, the relationship between two views can be modeled by a **homography** -- a 3x3 projective transformation matrix H that maps pixel coordinates from one frame to the next:

The homography H is a 3x3 matrix with elements `h11` through `h33`. It maps a pixel at coordinates (`x`, `y`) to a new location (`x'`, `y'`) by multiplying the column vector [x, y, 1] by H and dividing through by the resulting third component (projective division): the transformed point is (X'/W', Y'/W') where [X', Y', W'] = H * [x, y, 1].

where s is a scale factor from the projective division (x' = X'/W', y' = Y'/W').

### Estimating the Homography with RANSAC

The standard pipeline for robust homography estimation:

1. **Detect keypoints** in both frames using a feature detector (ORB, SIFT, etc.). Choose a feature budget based on image resolution, texture, and runtime constraints.
2. **Match keypoints** across frames using descriptor distance (e.g., brute-force matching with Hamming distance for binary descriptors like ORB).
3. **Estimate H with RANSAC** to reject outlier matches. RANSAC iteratively samples minimal subsets of 4 point correspondences, fits a homography, and counts inliers within a reprojection threshold. Points on independently moving objects appear as outliers.

A homography requires at least four non-degenerate correspondences, but robust estimation usually needs more. Judge sufficiency from inlier geometry, residuals, and spatial coverage rather than a fixed match count supplied here.

### Why the Homography Matters for Both Tasks

The homography serves as the bridge between the two subtasks:

- **For egomotion**: Decomposing H reveals camera translation (pan, tilt, dolly) and rotation (roll). The matrix encodes scale changes (dolly), translations (pan/tilt), and rotational components.
- **For dynamic masks**: By computing the "expected" flow field from H (the flow that every pixel would exhibit if the scene were static and only the camera moved), the residual between actual optical flow and expected flow isolates independently moving objects.

## Egomotion Classification from Homography Decomposition

Camera motion types map to specific geometric signatures in the homography:

| Motion Type | Geometric Signature |
|---|---|
| **Stay** | Near-identity transform: negligible translation and scale change |
| **Dolly In** | Scale factor > 1.0 (image magnification, radial expansion) |
| **Dolly Out** | Scale factor < 1.0 (image shrinkage, radial contraction) |
| **Pan Left** | Positive horizontal translation of image center (scene shifts right) |
| **Pan Right** | Negative horizontal translation of image center (scene shifts left) |
| **Tilt Up** | Positive vertical translation of image center (scene shifts down) |
| **Tilt Down** | Negative vertical translation of image center (scene shifts up) |
| **Roll Left / Roll Right** | Rotational component around the optical axis |

### Scale Change Analysis

To detect dolly motion, measure how the homography changes distances from the image center. Transform a set of test points (e.g., the four quadrant centers) through H, and compare their distances from the image center before and after transformation. A ratio greater than 1 indicates zoom-in / dolly-in; less than 1 indicates zoom-out / dolly-out. The magnitude of scale change must exceed a noise floor to be classified as intentional motion rather than estimation jitter.

### Translation Analysis

Pan and tilt are detected by transforming the image center through H and measuring the displacement:
- The horizontal component (dx) indicates pan: positive dx means the image content shifted right (pan left), negative dx means pan right.
- The vertical component (dy) indicates tilt: positive dy means content shifted down (tilt up), negative dy means tilt down.

Note the **sign inversion**: camera motion in one direction causes apparent scene motion in the opposite direction. Pan right moves the camera rightward, causing image content to shift leftward (negative dx in image coordinates).

Translation must exceed a motion threshold to register, and vertical motion (tilt) typically requires a higher threshold than horizontal motion (pan) because vertical camera motion is less common and vertical flow noise from parallax is more prevalent.

### Stay and Roll Decisions

Use a near-identity test for Stay and a rotation estimate for Roll. Calibrate both against measurement noise and the actual video; do not assume an undisclosed class distribution or suppress a class because it is often rare in other datasets.

### Compound Motion

A single frame transition can exhibit multiple simultaneous motion types -- for example, "Dolly In" combined with "Pan Right." The classifier should check each motion axis independently and return all applicable labels. Only when no motion axis exceeds its threshold should the frame be labeled "Stay."

### Temporal Smoothing of Labels

Raw per-frame labels can be noisy because optical flow and homography estimation fluctuate. Temporal voting or state filtering can stabilize predictions, but window size and retention rules should be chosen from frame rate, motion duration, and validation rather than fixed here.

### Merging Consecutive Frames into Intervals

After smoothing, consecutive frames with identical label sets are merged into intervals. The output format uses `"start->end"` keys where `start` is the index of the first frame in the interval and `end` is the index of the first frame of the next interval (exclusive). This run-length encoding compactly represents the temporal structure of camera motion.

## Dynamic Object Segmentation

Dynamic objects are those that move independently of the camera (vehicles, pedestrians, animals). Detecting them requires separating their motion from camera-induced motion.

### Flow Residual Method

The core approach:

1. **Compute expected flow from the homography.** For every pixel (x, y), apply H to get the destination (x', y'). The expected flow is (x'-x, y'-y). This represents the motion every pixel would exhibit if the scene were static.
2. **Compute the residual.** Subtract expected flow from actual optical flow. Pixels on static scene elements will have near-zero residuals; pixels on independently moving objects will have large residuals.
3. **Threshold the residual magnitude.** Pixels exceeding a deviation threshold are classified as dynamic.

When no homography is available (insufficient feature matches), a fallback uses the **median flow** as the global motion estimate. The median is robust to outliers (dynamic objects typically occupy a minority of pixels), so the residual from median flow still isolates moving objects, though less accurately than the homography-based method.

### Residuals are object seeds, not complete object masks

A large motion residual often appears only on textured parts, boundaries, or
unoccluded portions of an independently moving object.  Thresholding the
residual therefore produces sparse evidence rather than a complete object
silhouette.  Treat high-confidence residual components as seeds and expand them
to object-consistent regions using image edges, color or appearance
segmentation, region growing, or instance proposals.  Reject an expansion when
its interior motion is inconsistent with the seed, but do not require every
pixel in a rigid object to have a strong optical-flow residual.

This distinction is important for recall: aggressive component-size filters
and erosion can remove genuine but weakly textured objects, while raw dilation
can spread edge artifacts across the background.  Prefer object-aware filling,
then validate the completed region against motion on both sides of the frame
pair.

### Parallax, occlusion, and bidirectional evidence

A single homography explains a planar scene or rotation-dominated view, not a
general three-dimensional scene with strong depth variation.  Residuals caused
by parallax can be mistaken for dynamic objects.  Diagnose this by examining
whether residual direction varies smoothly with image position or depth and by
checking the spatial coverage of global-model inliers.  When needed, use a
more suitable background model such as an affine mesh, epipolar geometry, or
multiple locally coherent motion models.

Forward/backward flow consistency is useful for separating reliable motion
from occlusions and flow failures.  Combine evidence across adjacent pairs so
that the first and last sampled frames receive support from their available
neighbor rather than defaulting to empty masks.  Propagate object regions, not
just residual pixels, and revalidate their appearance after every warp.

### Spatial Weighting and Edge Handling

Not all image regions contribute equally to reliable dynamic object detection:

- **Image edges** can suffer from flow artifacts (boundary effects, vignetting, lens distortion). If an edge margin is used, scale it to resolution and validate that it does not hide real objects.
- **Lower image regions** in some camera setups contain a ground plane with strong parallax. Spatial weighting may help, but it should be inferred from scene geometry rather than applying a fixed height cutoff.
- **Far-left / far-right regions** may also exhibit stronger parallax flow for non-planar scenes.

A spatial weight map multiplied with the deviation magnitude adjusts sensitivity across the frame before thresholding.

### Morphological Cleanup

Raw thresholded masks are noisy -- they contain isolated pixels and holes. Standard morphological operations clean them:

- **Opening** (erosion then dilation) removes small isolated noise pixels.
- **Closing** (dilation then erosion) fills small holes within detected objects.
- **Connected component analysis** with area filtering removes small blobs below a minimum size threshold (typically a fraction of total image area) while retaining genuine object detections.

Choose morphological kernel dimensions relative to image resolution and the smallest object that must be preserved.

### Temporal Consistency and Tracking

Frame-by-frame mask detection produces flickering results because optical flow estimates vary between frames. A temporal tracker improves consistency:

1. **Warp the previous mask** using the current optical flow field. This projects where the previous frame's dynamic regions should appear in the current frame, accounting for both camera and object motion.
2. **Fuse current detection with warped previous mask.** Weight current and propagated evidence according to flow confidence and desired responsiveness.
3. **Maintain a confidence map** that accumulates evidence of dynamic regions over time. If decay is used, relate it to frame rate and expected object persistence.
4. **Apply a fusion threshold** to produce the final binary mask from the fused confidence values.

This temporal propagation dramatically reduces mask flicker (the fraction of pixels that change classification between consecutive frames) while maintaining responsiveness to genuinely appearing or disappearing dynamic objects.

Be precise about the direction of the warp.  A forward optical-flow vector
usually maps a source pixel to its destination in the next frame.  Image
resampling APIs commonly use the inverse convention: for each destination
pixel they request the coordinate to sample in the source image.  Passing a
forward map directly to such an inverse-mapping API can move evidence in the
wrong direction even though shapes and types remain valid.  Either estimate a
backward flow, construct an inverse sampling map, or use a forward-warp method
with explicit collision and hole handling.  A synthetic translation of a
single blob is a useful implementation check because the expected direction is
unambiguous.

## Compressed Sparse Row (CSR) Format for Mask Storage

Binary masks are spatially sparse (dynamic objects occupy a small fraction of the frame), making dense storage wasteful. The CSR format stores only the locations of True (dynamic) pixels:

| Component | Content |
|---|---|
| `shape` | Global mask dimensions [H, W], shared across all frames |
| `f_{i}_data` | Array of True values (length = number of dynamic pixels in frame i) |
| `f_{i}_indices` | Column indices of dynamic pixels (which columns are True in each row) |
| `f_{i}_indptr` | Row pointer array (length H+1): `indptr[r]` to `indptr[r+1]` gives the range in `indices` for row `r` |

To reconstruct a dense mask from CSR, iterate over each row `r` from 0 to H-1. For each row, extract the column indices by slicing the `indices` array from position `indptr[r]` to position `indptr[r+1]`. Set `mask[r, cols]` to True for all those column indices. Rows with no dynamic pixels will have `indptr[r]` equal to `indptr[r+1]`, producing an empty slice.

When saving masks to CSR, iterate over the dense mask, collect (row, col) pairs where the mask is True, build the indices array from the column values, and compute indptr as the cumulative count of True pixels per row.

## Quality Diagnostics

Motion classification can be diagnosed with per-class precision and recall, while masks can be inspected with overlap, boundary, and temporal-consistency measures. Use the metrics and aggregation rules explicitly stated by the task or evaluator. Do not assume a class distribution, percentile, averaging convention, or hidden scoring weight from this background.

Without access to reference masks, inspect complementary diagnostics: predicted
area over time, fraction of residual seeds retained after cleanup, region
interior support, boundary alignment with image edges, forward/backward
consistency, and track continuity.  A mask that contains only thin edges or a
small textured patch of a visibly coherent moving object is under-segmented
even when its residual pixels are precise.

## Key Distinctions in Practice

- **Sign convention for pan and tilt.** Camera panning right causes scene content to move left in the image. The camera's motion direction and the image displacement direction are opposite: a rightward pan produces leftward image displacement. This sign inversion applies symmetrically to tilt as well.
- **Homography-based vs. raw flow analysis for egomotion.** Raw optical flow magnitude conflates camera motion with independent object motion and cannot reliably distinguish the two. The homography (or an equivalent robust global motion model) isolates camera-induced motion from object-induced motion, making it the appropriate basis for camera motion classification.
- **Graceful degradation when feature matching fails.** In textureless scenes or under heavy motion blur, feature matching may yield insufficient correspondences for homography estimation. Robust systems incorporate a fallback to median-flow-based estimation, which provides a reasonable global motion approximation even without explicit geometric modeling.
- **Adaptive vs. fixed thresholding for flow residuals.** The appropriate deviation threshold for classifying dynamic pixels depends on the noise level of the current frame pair. An adaptive threshold (e.g., based on the standard deviation of residuals) accommodates varying scene complexity more effectively than a single fixed value.
- **Morphological post-processing as a standard step.** Raw thresholded binary masks contain substantial noise in the form of isolated pixels and internal holes. Standard practice includes morphological opening, closing, and connected-component area filtering, which substantially improves IoU by cleaning the mask while preserving the underlying motion analysis.
- **Temporal smoothing for both tasks.** Both motion labels and dynamic masks benefit from temporal propagation across consecutive frames. Single-frame analysis produces flickery results, and temporal consistency is both a standard quality metric and a practical requirement for downstream applications.
- **CSR encoding conventions.** In the Compressed Sparse Row format for binary masks, the indptr array has length H+1 (one more than the number of rows), and column indices are sorted within each row. Correct construction of indptr as a cumulative count of True pixels per row ensures that the mask reconstructs accurately at the correct spatial positions.
- **Radial vs. translational flow patterns.** Dolly (zoom) motion produces radial flow patterns emanating from or converging to the focus of expansion, which are geometrically distinct from the uniform displacement fields produced by pure translational camera motion (pan/tilt). A global motion model must account for both pattern types to correctly classify the motion and compute accurate residuals for mask detection.
- **Frame count and output correspondence.** N sampled frames produce N-1 adjacent pairs. Follow the task's declared convention for assigning pairwise estimates to frame-indexed outputs, and document how either endpoint is handled rather than assuming a hidden duplication rule.
- **Motion classification threshold sensitivity.** Translation, scale, and rotation thresholds depend on resolution, frame rate, calibration, estimator noise, and the evaluation objective. Estimate a noise floor from the data or use legitimate validation. Do not tune toward an assumed majority class, fixed pixel displacement, fixed angle, or hidden metric weighting.
