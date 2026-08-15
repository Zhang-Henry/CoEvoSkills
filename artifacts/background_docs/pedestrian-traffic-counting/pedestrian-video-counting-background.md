# Pedestrian Counting in Surveillance Video

This document provides background on the computer vision and video analysis concepts underlying pedestrian counting from fixed-position surveillance cameras. It covers the key challenges of counting unique individuals across video frames, distinguishing pedestrian activity from other road users, and the practical approaches available when working programmatically with video data.

## The Unique Counting Problem

Counting pedestrians in video is fundamentally different from counting objects in a single image. A surveillance camera recording at typical frame rates (24-30 fps) produces hundreds or thousands of frames per minute. A single pedestrian walking through the camera's field of view will appear in many consecutive frames. The central challenge is **deduplication**: determining that the person visible in frame 50 is the same individual visible in frame 75, and counting them exactly once.

Naive approaches that count detections per frame and sum them will massively overcount. If a pedestrian is visible for 3 seconds at 30 fps, a per-frame count would register 90 detections for a single person. The correct count is 1.

There are two broad families of solutions to this problem:

**Tracking-based approaches** use multi-object tracking (MOT) algorithms to maintain identity across frames. An object detector (such as YOLO, Faster R-CNN, or SSD) finds bounding boxes for people in each frame, and a tracker (such as SORT, DeepSORT, or ByteTrack) associates detections across frames using motion prediction and appearance features. Each tracked identity is counted once. This is the classical computer vision pipeline.

**Holistic video understanding** uses models that process the video as a whole (or in large temporal chunks) and reason about the scene semantically. Multimodal large language models (LLMs) with video input capabilities fall into this category. These models can be prompted to watch the entire video and report the number of unique pedestrians, effectively performing the deduplication internally through their temporal understanding.

Both approaches must handle occlusion (a person temporarily hidden behind an obstacle), re-entry (a person leaving and re-entering the frame), and crowded scenes where individuals overlap visually.

## Distinguishing Pedestrians from Other Road Users

Surveillance cameras positioned at public streets capture not only pedestrians but also cyclists, motorcyclists, drivers, and passengers in vehicles. The task of pedestrian counting requires classifying each individual by their mode of transport and excluding non-pedestrians.

**Pedestrians** are people who are traveling on foot -- walking, jogging, running, or standing. A person pushing a stroller or walking a dog is still a pedestrian.

**Cyclists** are people who are riding bicycles. Even though they are human figures and may be detected by person detectors, they should not be counted as pedestrians. A person who is walking alongside a bicycle (not riding it) would count as a pedestrian, but someone actively pedaling or coasting on a bicycle would not.

**Vehicle occupants** -- drivers and passengers inside cars, buses, trucks, or motorcycles -- should also be excluded. In typical surveillance footage these individuals are often partially occluded by the vehicle body, which makes detection less likely, but they can sometimes be visible through windshields.

The classification boundary can be ambiguous. A person dismounting a bicycle and then walking is a pedestrian from the moment they start walking. A person who stands up from a bench and walks across the scene should be counted. The key criterion is the mode of locomotion during the observed activity: on foot means pedestrian; on a vehicle means not.

## Video Processing Approaches

### Frame Sampling and Detection Pipelines

The classical approach processes video frame by frame (or at a sampled interval) through an object detection model. Widely used architectures include:

- **YOLO family** (YOLOv5, YOLOv8, YOLOv9, etc.): Single-stage detectors optimized for speed, commonly used in real-time surveillance. They output bounding boxes with class labels (person, bicycle, car, etc.).
- **Faster R-CNN / Mask R-CNN**: Two-stage detectors that are generally more accurate but slower. Mask R-CNN additionally provides instance segmentation masks.
- **SSD (Single Shot Detector)**: Another single-stage architecture, faster than R-CNN variants but often less accurate on small objects.

After detection, a tracking algorithm associates detections across frames. The tracker assigns a unique ID to each individual and maintains it as the person moves through successive frames. The total count of unique IDs is the pedestrian count.

Key parameters that affect accuracy:
- **Sampling rate**: Processing every frame is expensive. Sampling every Nth frame reduces cost but risks missing pedestrians who appear only briefly. The sampling interval must be short enough that a person is visible in at least one sampled frame.
- **Detection confidence threshold**: Setting it too high misses partially occluded or distant pedestrians; too low produces false positives from background objects.
- **Tracker association threshold**: Controls how aggressively the tracker links detections across frames. Loose thresholds risk merging two different people; tight thresholds risk fragmenting one person into multiple IDs.

### Multimodal LLM Video Analysis

An alternative approach leverages multimodal LLMs (such as Gemini, GPT-4V, or Claude with vision) that accept video as input. The video is uploaded to the model, and a carefully crafted prompt asks the model to count unique pedestrians.

Advantages of this approach:
- No need to implement detection + tracking pipelines from scratch
- The model can reason about scene context (e.g., understanding that a figure on a bicycle is not a pedestrian)
- Handles deduplication implicitly through temporal reasoning

Considerations:
- **API file upload**: Video files must be uploaded through the model's file API. Large videos may need to be processed in chunks or downsampled.
- **Processing state**: Video uploads may require a processing/transcoding step before the model can analyze them. The upload API typically returns a state indicator (e.g., PROCESSING, ACTIVE, FAILED) that must be polled until processing completes.
- **Prompt engineering**: The quality of the count depends heavily on the prompt. Clear instructions about what constitutes a pedestrian (walking on foot, excluding cyclists, excluding vehicle occupants) significantly improve accuracy.
- **Response parsing**: The model returns natural language text. The count must be extracted programmatically, often by asking the model to format its answer in a structured way (e.g., within specific tags or as a bare integer).

### Using ffmpeg and moviepy for Video Manipulation

The container environment includes `ffmpeg` (system package) and `moviepy` (Python library) for video manipulation tasks such as:

- Extracting individual frames as images
- Getting video metadata (duration, resolution, frame rate, codec)
- Splitting long videos into shorter clips
- Downsampling frame rate or resolution to reduce file size before upload

These tools are useful preprocessing steps regardless of whether the downstream analysis uses a classical CV pipeline or a multimodal LLM.

## Output Formatting: Excel with openpyxl

The results must be written to an Excel workbook (`.xlsx` format) using a library such as `openpyxl`. Key structural requirements for programmatic Excel generation:

- **Workbook and sheet management**: A new workbook created with openpyxl has one default sheet. The sheet should be renamed appropriately rather than leaving the default name. No additional sheets should be created.
- **Header row**: The first row should contain column names as plain strings. These column names serve as the schema of the output and must match the expected format exactly (case-sensitive).
- **Data types**: Numeric values (counts) should be written as integers, not as strings. Storing a count as a number ensures the cell is typed correctly, while storing it as text changes the cell type. When downstream consumers read cells and convert them to strings, both produce the same string representation, but it is good practice to store counts as their native type.
- **Row ordering**: Results should be written in a consistent, deterministic order (typically sorted alphabetically by filename) to ensure reproducibility.
- **No extraneous content**: Empty rows, extra columns, summary statistics rows, or metadata cells outside the expected schema will cause strict row-by-row comparison tests to fail.

## Technical Considerations

**Temporal deduplication is fundamental to accurate counting.** The core principle of video-based pedestrian counting is that each physical person must be counted exactly once regardless of how many frames they appear in. A person visible for 100 frames is 1 pedestrian, not 100. Any methodology that does not explicitly deduplicate across the temporal dimension will produce wildly inflated counts.

**Person detection models detect all humans regardless of activity.** Object detectors trained on datasets like COCO have a "person" class that includes all humans -- pedestrians, cyclists, vehicle occupants alike. A person riding a bicycle will be detected as "person." Accurate pedestrian counting therefore requires additional logic to determine whether a detected person is also associated with a vehicle or bicycle (via bounding box overlap or semantic reasoning), so that non-pedestrians can be excluded.

**Tracking identity fragmentation affects count accuracy.** When using multi-object tracking, temporary occlusions or detector failures can cause the tracker to lose an identity and assign a new ID when the person reappears. This leads to one physical person being counted as two or more unique individuals. The tracker's maximum age parameter (how many frames an identity persists without a detection match) and appearance re-identification features are the primary tools for reducing fragmentation.

**Track IDs are intermediate hypotheses, not final identities.** A robust counting pipeline should preserve a tracklet ledger and perform a second association pass across broken tracklets. Candidate joins can use elapsed time, motion extrapolation toward an entry or exit region, spatial compatibility, appearance embeddings, and consistent evidence about whether the subject is walking or riding. Tracklets should not be joined on appearance alone when two similar-looking people coexist, and a subject crossing an entry/exit line should not be counted again merely because the online tracker assigned a new ID after a short gap.

**Association parameters should scale with observable video geometry and time.** Pixel-distance gates should be normalized by frame diagonal, a robust bounding-box scale, or both; persistence and gap windows should be expressed as elapsed time and converted with the measured frame rate. Motion gates can be derived from recent track velocity, box scale, and prediction uncertainty. These data-derived quantities transfer across resolution and frame-rate changes better than fixed pixel or frame constants. Validate the policy through perturbation stability rather than tuning it to a known count.

**Counts should be stable under reasonable perturbations.** Run the pipeline over more than one defensible sampling interval and nearby detector/association settings. Large changes in unique-ID count usually indicate missed brief appearances, identity fragmentation, or over-aggressive merging rather than genuine uncertainty in the scene. Reconcile the tracklet ledger and inspect the unstable identities before accepting a count. This stability check determines whether a method is reliable; it does not prescribe a target count or a particular threshold.

**Cloud-based video models require processing time after upload.** When using cloud-based multimodal models for video analysis, the video file undergoes server-side processing after upload. The model cannot analyze the video until processing completes, so a polling mechanism that checks the processing state and waits for an active status is an essential part of the workflow.

**Precise prompting is essential for consistent counts.** Vague prompts like "how many people are in the video" can cause the model to count bystanders, vehicle occupants, or even reflections. Precise prompts that define the counting criteria (walking on foot, unique individuals, excluding specific categories) produce more reliable results.

**Scene boundary judgment involves inherent ambiguity.** When a pedestrian is only partially visible (entering or leaving the frame), it is ambiguous whether to count them. Similarly, people visible only in the far background at very low resolution may or may not be detectable. Consistent criteria for what constitutes "in the scene" help, but some degree of judgment-dependent variance is inherent in this task.
