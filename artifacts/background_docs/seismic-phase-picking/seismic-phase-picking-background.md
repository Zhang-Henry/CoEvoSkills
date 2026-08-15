# Seismic Phase Picking: Domain Background

This document provides background on seismic wave propagation, phase arrival identification, waveform data conventions, and the evaluation methodology used in seismological phase picking.

## Seismic Wave Propagation and Phase Types

When an earthquake occurs, energy radiates outward from the hypocenter in the form of seismic waves. Two body-wave phases are of primary interest for earthquake location and characterization:

**P-waves (Primary waves)** are compressional (longitudinal) waves that travel through solid and liquid media by alternately compressing and dilating the material in the direction of propagation. They are the fastest seismic waves and therefore arrive first at a recording station. P-waves typically produce a sharp onset on the vertical (Z) component of a seismogram, though they appear on all three components depending on the angle of incidence.

**S-waves (Secondary waves)** are shear (transverse) waves that travel only through solid media by displacing material perpendicular to the direction of propagation. S-waves travel at roughly 55-70% of the P-wave velocity in crustal rock (a common approximation is Vs approximately equals Vp / 1.73, following a Poisson ratio of about 0.25). Because of this lower velocity, S-waves always arrive after the P-wave. S-wave energy is typically strongest on the horizontal components (E/N or 1/2), though it appears on all components.

The **S-P time difference** (the time interval between the S-wave and P-wave arrivals) is directly proportional to the source-station distance. For shallow crustal earthquakes, a rough rule of thumb is that each second of S-P time corresponds to approximately 8 km of distance. Short S-P times (a few tenths of a second) indicate very nearby events, while S-P times of many seconds indicate distant sources. This relationship means that the position of the S-wave pick relative to the P-wave pick is physically constrained: the S pick must always occur after the P pick, and the separation encodes distance information.

## Waveform Data: Three-Component Seismograms

Modern seismic stations record ground motion as three-component (3-C) time series capturing motion along three orthogonal axes. The standard orientation is:

- **Z (vertical)**: sensitive to up-down motion
- **N (north-south)** and **E (east-west)**: the two horizontal components

Some stations use numbered orientations (1, 2, 3) instead of geographic directions when sensors are not precisely aligned to cardinal directions. For phase picking purposes, the distinction between geographic and numbered orientations does not affect the fundamental signal characteristics.

### SEED Channel Naming Convention

Seismic data follows the SEED (Standard for the Exchange of Earthquake Data) naming convention, where each channel code is a three-character string:

- **First character (band code)**: indicates the sampling rate and response band
  - `H` = high broadband (80-250 sps, typically 100 sps)
  - `B` = broadband (10-80 sps, typically 40 sps)
  - `S` = short period (10-80 sps)
  - `E` = extremely short period (80-250 sps, typically 100 sps)
  - `D` = diagnostic/special (>= 250 sps or variable)

- **Second character (instrument code)**: indicates sensor type
  - `H` = high-gain seismometer (velocity sensor)
  - `N` = accelerometer (strong motion)
  - `L` = low-gain seismometer
  - `P` = geophone (short period)

- **Third character (orientation code)**: indicates the axis
  - `Z`, `N`, `E` for vertical, north, east
  - `1`, `2`, `3` for non-standard orientations

Understanding the instrument code matters because **accelerometer (N) channels record acceleration while seismometer (H, L, P) channels record velocity**. Deep learning models trained on velocity waveforms may behave differently when presented with acceleration data, and vice versa. Additionally, different band codes imply different frequency content and noise characteristics, which can affect picking accuracy.

### Data Format and Sampling

Waveform data in this domain is stored as NumPy `.npz` archives. Each file contains the waveform array along with metadata. The waveform data array has shape `(num_samples, num_channels)` -- for example, 12000 samples across 3 channels represents 120 seconds of recording at 100 Hz. The sampling interval `dt` (in seconds) defines the time resolution; its reciprocal gives the sampling rate in Hz.

Not all traces have three channels. Some stations record only a single vertical component or two horizontal components. When fewer than three channels are available, the data array still has a fixed number of columns, but only the columns corresponding to available channels carry meaningful signal.

Converting between time and sample index is straightforward: `index = time_offset / dt`, where `time_offset` is measured from the start of the trace. This relationship is critical for evaluating pick accuracy, as tolerances defined in seconds must be converted to sample indices using the trace's specific sampling rate.

## Phase Picking Methods

### Why Method Choice Matters

Classical energy-ratio pickers and learned models have different assumptions, dependencies, and failure modes. S-wave onsets can be hard for amplitude-only methods because they occur after P-wave energy has raised the background. Learned models may distinguish richer waveform patterns but require compatible weights, preprocessing, and runtime support. Choose from the methods actually available and validate the choice without relying on score ranges or a benchmark-specific cutoff supplied by background text.

### Classical Methods (STA/LTA)

The traditional approach to automatic phase picking uses the **STA/LTA (Short-Term Average / Long-Term Average)** ratio. This method computes the ratio of the average amplitude in a short window (capturing transient signals) to the average amplitude in a longer window (capturing background noise). When a seismic phase arrives, the short-term energy rises sharply relative to the long-term background, producing a spike in the STA/LTA ratio. A trigger is declared when this ratio exceeds a configurable threshold.

STA/LTA operates independently on each channel and requires tuning of the short window, long window, and trigger threshold. Relate window lengths to sampling rate and expected event duration, and relate the trigger to the observed noise distribution.

STA/LTA works well for impulsive P-wave arrivals with high signal-to-noise ratio (SNR) but struggles with:
- Emergent (gradual) P-wave onsets
- S-wave picking, because the S-wave arrives within the P-wave coda (the STA already contains elevated energy from the P-wave)
- Low-SNR environments where background noise obscures the onset

STA/LTA can serve as a baseline or as a practical picker when learned dependencies are unavailable. Its suitability must be assessed on the actual data.

### Deep Learning Methods

Modern seismic phase picking has been transformed by deep learning models that learn to identify phase arrivals from waveform patterns. These models consistently outperform classical methods by a wide margin, especially for S-waves. The most widely used models include:

**PhaseNet** is a U-Net style architecture that takes three-component waveforms as input and outputs probability time series for three classes: P-wave, S-wave, and noise. Peaks in the P and S probability traces correspond to predicted arrivals. PhaseNet operates on fixed-length windows and naturally handles both P and S phases simultaneously.

**EQTransformer** uses a transformer-based architecture with attention mechanisms, producing similar probability outputs for P, S, and detection. It tends to be more robust for distant events and complex waveforms.

**GPD (Generalized Phase Detection)** is a convolutional classifier that was among the earlier deep learning approaches. It classifies individual windows as containing P, S, or noise.

All of these models are available through the **SeisBench** library, which provides a unified interface for loading pretrained models and running inference on ObsPy Stream objects. SeisBench handles the windowing, normalization, and output parsing internally.

SeisBench, ObsPy, and their dependencies are distributed as Python packages, but availability, network access, model caches, and compute support vary by environment. Inspect the environment first. A classical picker, a cached pretrained model, or a custom probability-trace workflow may each be appropriate depending on what is actually available and on validation results.

### SeisBench Workflow

SeisBench models expose two inference interfaces: `annotate` and `classify`. Understanding the distinction is critical for correct usage.

**`annotate(stream)`** returns continuous probability time series (as ObsPy Streams) with one trace per class (P, S, noise). These probability curves require peak detection, thresholding, and careful time-to-index alignment to produce discrete picks. Inspect the returned trace metadata because windowing and stitching conventions can vary by model.

**`classify(stream)`** is a higher-level interface that can perform annotation, peak detection, and pick extraction internally, returning discrete Pick objects with times and probabilities. Its defaults are convenient, while `annotate` permits dataset-specific post-processing. Neither interface is universally preferable: confirm metadata alignment and compare candidates on evidence available within the task.

The typical workflow involves:

1. **Data loading**: Convert raw waveform data into a representation accepted by the chosen picker. Preserve each trace's channel ordering, sampling interval, start-time metadata, and file identity so that predicted times can be mapped back without offsets.

2. **Model loading**: Inspect the installed or cached candidates and their expected input conventions. Choose weights only after checking compatibility and, where possible, controlled validation rather than assuming that a named checkpoint is best.

3. **Inference**: Run either a discrete-pick interface or probability annotation. Inspect the actual return type and metadata of the installed model version rather than relying on one fixed API shape.

4. **Index conversion**: Map a predicted timestamp back through the trace-specific start time and sampling interval, or map a probability-trace sample through that trace's own metadata. Define rounding and boundary behavior explicitly. Add filters or preprocessing only when their effect is justified by the data or validation.

### Handling Incomplete Channel Data

Deep learning models for seismic phase picking are typically trained on three-component data. When a trace has fewer than three channels, the model may still produce output, but the missing channel information can degrade accuracy. Common strategies for handling incomplete data include:

- Filling missing channels with zeros
- Duplicating the available channel(s) to fill the expected input shape
- Relying on the model's internal robustness to partial input

The choice of strategy can affect pick quality, particularly for S-waves, which rely more heavily on horizontal component information.

## Evaluation: Precision, Recall, and F1 Score

Phase picking performance is evaluated by comparing predicted arrival times to human-analyst ground truth labels. The evaluation uses a **tolerance-based matching** criterion: a predicted pick is considered correct (a True Positive) if it falls within a specified time tolerance of the ground truth arrival.

Matching tolerance is an evaluation-policy choice and depends on the data and task specification. Convert any stated time tolerance to samples separately for each trace's sampling rate; do not infer an undisclosed evaluator threshold from this background.

The three core metrics are:

- **Precision** = TP / (TP + FP): the fraction of predicted picks that are correct. Low precision indicates many false picks.
- **Recall** = TP / (TP + FN): the fraction of ground truth arrivals that were successfully detected. Low recall indicates many missed arrivals.
- **F1 score** = 2 * Precision * Recall / (Precision + Recall): the harmonic mean balancing precision and recall.

In this evaluation framework:
- **TP (True Positive)**: a predicted pick that is within tolerance of a ground truth arrival
- **FP (False Positive)**: a predicted pick that does not match any ground truth arrival (outside tolerance)
- **FN (False Negative)**: a ground truth arrival for which no predicted pick falls within tolerance

P-wave and S-wave metrics are computed separately because the two phases present different challenges. P-waves generally have sharper onsets and are easier to pick accurately, while S-waves arrive within the P-wave coda and have more gradual onsets, making them inherently harder to identify precisely.

### Multiple Picks Per Trace

The evaluation allows for multiple P or S picks per trace. When multiple picks are submitted for a given phase in a single trace, each pick is independently checked against the ground truth. Correct picks count as true positives, and incorrect picks count as false positives. However, each ground truth arrival can only be "satisfied" once for recall purposes -- submitting many picks for the same file can inflate false positives (hurting precision) without improving recall beyond the first correct pick.

This means there is a tradeoff: being liberal with picks (using low probability thresholds) can improve recall but may harm precision. Conversely, using high probability thresholds may miss legitimate arrivals. The optimal strategy maximizes the F1 score, which rewards balancing both objectives.

## Practical Considerations

**The relationship between time and sample index depends on trace-specific metadata.** For an absolute predicted time, subtract the corresponding trace start time and divide by its sampling interval, then apply a documented rounding convention. For an annotated probability trace, use that output trace's start time and sampling interval. Validate alignment with metadata rather than assuming every file shares one time base.

**S-waves often arrive during the P-wave coda, which can make them difficult for simple energy-ratio methods.** Learned models and classical detectors have different failure modes; compare them using available evidence instead of assuming a method from a hidden score target.

**Not all traces contain three channels of meaningful data, even when the data array has three columns.** Some stations record only one or two components, and the remaining columns may contain zeros or uninformative values. The channels metadata indicates which columns carry real data. Feeding zero-padded or meaningless channels to a model trained on three-component data can degrade pick reliability, particularly for S-waves that depend on horizontal component information.

**Seismometer channels and accelerometer channels record different physical quantities.** Seismometer channels (instrument code H, L, P) record ground velocity, while accelerometer channels (instrument code N) record ground acceleration. The waveform amplitudes, frequency content, and phase onset characteristics differ between these instrument types. Models pretrained on one type may produce degraded results on the other, and datasets that mix instrument types may require preprocessing (such as integrating acceleration to velocity) or verification that the chosen model is robust across instrument types.

**Phase picking output must conform to the exact column names and value formats expected by the evaluation pipeline.** The standard output format uses specific column names (file_name, phase, pick_idx) with integer-valued sample indices and uppercase phase labels (P, S). Deviations such as floating-point indices, lowercase labels, missing file extensions, or extra columns can cause parsing failures independent of the actual pick quality.

**Pick confidence affects the precision-recall balance.** Stricter acceptance can reduce false positives while missing weak arrivals; looser acceptance does the reverse. Select thresholds from explicit requirements or legitimate validation evidence, not from an undisclosed benchmark target.

**Raw waveform amplitudes can span many orders of magnitude** depending on instrument gain, event magnitude, and source-station distance. Inspect finite values, scale, variance, and the chosen model's documented normalization. A numerically neutral rescaling may help avoid underflow, while filtering, clipping, detrending, or custom normalization can also alter a model's expected input. Treat each preprocessing step as a hypothesis to validate rather than a prescribed solution.

**Keep the pipeline auditable.** Record channel construction, metadata mapping, preprocessing, model or detector choice, thresholding, and index conversion. Test alignment and output formatting separately so that a plausible detector is not undermined by a bookkeeping error.
