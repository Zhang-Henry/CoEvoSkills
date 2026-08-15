# Gravitational Wave Detection with Matched Filtering

This document provides background on gravitational wave physics, detector data conditioning, waveform template generation, and the matched filtering technique used to identify compact binary merger signals buried in noisy detector output.

## Gravitational Waves from Binary Mergers

Gravitational waves are ripples in spacetime produced by accelerating massive objects. The strongest sources detectable by ground-based interferometers such as LIGO and Virgo are compact binary coalescences -- systems of two compact objects (black holes or neutron stars) spiraling inward under gravitational radiation until they merge. The emitted waveform sweeps upward in both frequency and amplitude as the orbital separation shrinks, producing a characteristic "chirp" signal.

A binary black hole (BBH) merger passes through three phases:

1. **Inspiral**: The two objects orbit each other at gradually increasing frequency. The waveform is well described by post-Newtonian theory and depends primarily on the component masses m1 and m2. Lower total mass systems spend more cycles in the sensitive frequency band of the detector, while higher total mass systems merge at lower frequencies and have shorter in-band durations.

2. **Merger**: The objects plunge together. The waveform reaches its peak amplitude and frequency. Modeling this regime requires numerical relativity or calibrated phenomenological fits.

3. **Ringdown**: The merged remnant settles into a stable Kerr black hole, emitting damped oscillations at characteristic quasi-normal mode frequencies determined by the remnant's mass and spin.

The key physical parameters governing the waveform shape are the component masses m1 and m2. The **total mass** M = m1 + m2 sets the overall frequency scale of the signal -- higher total mass pushes the merger to lower frequencies. The **mass ratio** q = m2/m1 (with q <= 1) and the **chirp mass** Mc = (m1*m2)^(3/5) / (m1+m2)^(1/5) control the rate of frequency evolution during inspiral. For detection purposes, performing a grid search over m1 and m2 effectively explores the space of possible chirp masses and mass ratios.

## Waveform Approximants

Because the full two-body problem in general relativity has no closed-form solution, gravitational waveforms are computed using **approximant** models -- semi-analytical or numerical-relativity-calibrated prescriptions that produce a time-domain or frequency-domain waveform given input parameters (masses, spins, etc.). Different approximants make different physical assumptions and trade accuracy for computational speed.

Three commonly used families are:

- **SEOBNRv4_opt**: An optimized effective-one-body (EOB) model. EOB theory maps the two-body dynamics onto a single effective particle moving in a deformed Schwarzschild-like spacetime, then calibrates free parameters against numerical relativity simulations. SEOBNRv4_opt covers inspiral, merger, and ringdown (IMR) and is accurate across a wide range of mass ratios. It is a time-domain waveform generator.

- **IMRPhenomD**: A phenomenological frequency-domain model that stitches together analytical inspiral, intermediate, and ringdown-merger pieces, with coefficients fit to hybrid EOB/numerical-relativity waveforms. It is computationally efficient and covers the full IMR signal for aligned-spin binaries. When used in time-domain matched filtering, the waveform is typically generated in the frequency domain and then inverse-Fourier-transformed, or generated directly in the time domain via PyCBC's interface.

- **TaylorT4**: A post-Newtonian (PN) time-domain approximant that integrates the orbital equations of motion using a particular re-expansion scheme (Taylor T4). It is accurate during the inspiral phase but does not model merger or ringdown. For low-mass systems that spend many cycles in the inspiral band, TaylorT4 can still capture substantial SNR. For higher-mass systems whose signal power is concentrated in the merger, TaylorT4 will underperform IMR models.

Because these approximants model the signal with different levels of fidelity, the same underlying signal will generally produce different peak SNR values with each approximant. A full IMR model that accurately captures the merger and ringdown will typically recover more SNR from a BBH signal than an inspiral-only model, especially when the true signal's total mass places the merger frequency within the detector's sensitive band.

## Detector Data Conditioning

Raw interferometer output contains the gravitational wave strain signal h(t) superimposed on instrumental noise n(t), so the measured data is d(t) = h(t) + n(t). The noise is many orders of magnitude larger than any astrophysical signal, and it has a strongly colored power spectral density (PSD) -- the noise amplitude varies enormously across frequency. Before any analysis, the data must be conditioned.

### High-Pass Filtering

Ground-based detectors are dominated by seismic noise at low frequencies (below roughly 10--20 Hz). A high-pass filter removes this low-frequency contamination. The cutoff frequency should be chosen below the lowest frequency at which the detector has useful sensitivity (and below the low-frequency cutoff used in template generation) so that the astrophysical signal content is preserved. Typical choices are 15--20 Hz.

### Resampling (Downsampling)

Raw LIGO data is often recorded at 16384 Hz, but gravitational wave signals from stellar-mass BBH mergers have negligible power above a few kHz. Downsampling to a lower rate (e.g., 4096 Hz, giving a Nyquist frequency of 2048 Hz) reduces computational cost without losing signal content. The resampling must be performed after high-pass filtering to avoid aliasing low-frequency noise into the analysis band.

### Cropping Filter Transients

Both the high-pass filter and any subsequent spectral operations introduce transient artifacts at the edges of the data segment. These corrupted samples must be cropped away before analysis. A typical approach is to remove a few seconds from each end of the conditioned data segment.

### Power Spectral Density Estimation

The noise PSD S_n(f) characterizes the frequency-dependent noise power and is essential for optimal matched filtering. It is estimated from the data itself, typically using Welch's method -- dividing the data into overlapping segments, computing the periodogram of each, and averaging. The PSD segment length determines the frequency resolution (delta_f = 1/T_segment).

After estimation, the PSD must be **interpolated** to match the frequency resolution of the data (which depends on the total data segment duration), and **inverse spectrum truncation** is applied to prevent the whitening filter from having excessively long time-domain impulse responses. The truncation length is typically set to a few seconds' worth of samples, and a low-frequency cutoff matching the high-pass filter frequency is applied.

## Matched Filtering

Matched filtering is the optimal linear detection statistic for a known signal shape in stationary Gaussian noise. It works by cross-correlating the data with a bank of template waveforms, weighting by the inverse of the noise PSD to emphasize frequencies where the detector is most sensitive.

### Mathematical Foundation

Given detector data d(t) and a template waveform h(t), the matched filter output is:

z(t) = 4 * integral_0^infinity [ d~(f) * h~*(f) / S_n(f) ] * exp(2*pi*i*f*t) df

where d~(f) and h~(f) are the Fourier transforms of the data and template, h~*(f) is the complex conjugate, and S_n(f) is the one-sided noise PSD. The result z(t) is a complex time series. The **signal-to-noise ratio** (SNR) at each time sample is |z(t)| / sigma, where sigma is the template normalization factor. Taking the absolute value maximizes over the unknown phase of the signal.

In practice, the matched filter is computed efficiently using the Fast Fourier Transform (FFT). The matched filter returns a complex SNR time series; taking the absolute value of this time series yields the SNR maximized over signal phase at each time sample. The peak value across all time samples is the detection SNR for that template.

### Template Alignment

Waveform generators produce templates with the merger (peak amplitude) at time zero by convention. For matched filtering via circular convolution (FFT-based), the template must be cyclically shifted so that the merger time aligns with the start of the array. This is accomplished by applying a cyclic time shift equal to the waveform's start time. Additionally, the template must be zero-padded (resized) to match the length of the conditioned data segment before filtering.

### Cropping the SNR Time Series

The SNR time series is corrupted at its edges by two effects:

1. **PSD filter corruption**: The inverse-PSD weighting acts as a filter whose impulse response extends for a duration determined by the PSD segment length (typically 4 seconds on each end).
2. **Template filter corruption**: The template waveform itself acts as a filter, and its duration corrupts additional samples at the beginning of the SNR time series.

Both corrupted regions must be cropped before searching for the peak SNR. The beginning of the SNR time series should be cropped by the sum of both effects, while the end only needs cropping for the PSD filter effect.

## Grid Search Strategy

When the signal parameters are unknown, a grid search (template bank) over the parameter space is required. For a BBH search over component masses m1 and m2:

- The search grid is defined over integer solar mass values in a specified range for both m1 and m2.
- By convention, m1 >= m2 (the more massive component is labeled m1). This avoids testing redundant mass combinations, since a waveform with (m1=30, m2=20) is identical to one with (m1=20, m2=30). For masses ranging from some minimum to some maximum in integer steps, the number of unique combinations is the sum 1 + 2 + ... + (max - min + 1), which equals (max - min + 1)(max - min + 2)/2.
- The total mass for each combination is simply M = m1 + m2, constrained to lie between 2*min_mass and 2*max_mass.
- For each approximant, every mass combination is tested independently. The template producing the highest SNR identifies the best-fit parameters for that approximant.

The grid search is repeated for each waveform approximant. The best result per approximant is the mass combination yielding the highest peak SNR. Because different approximants model different physical effects, they will generally identify slightly different best-fit parameters and achieve different peak SNR values for the same underlying signal.

## The Low-Frequency Cutoff

A critical parameter in both waveform generation and matched filtering is the **low-frequency cutoff** f_low. This is the frequency below which:

- The waveform template is not generated (it starts at f_low and evolves upward).
- The matched filter integral excludes contributions (the integral effectively starts at f_low rather than zero).

The low-frequency cutoff should be chosen at or above the frequency where the detector's noise rises steeply (the "seismic wall"), typically 15--25 Hz. Setting f_low too high discards useful signal cycles and reduces SNR. Setting it too low includes frequency bins dominated by noise, which degrades the PSD estimate and can introduce numerical artifacts. The cutoff used for waveform generation and the cutoff used in the matched filter call should be consistent (commonly 20 Hz for both).

## Important Technical Details

### Data Conditioning Is a Required Prerequisite
Raw detector data has enormous low-frequency noise that completely dominates the matched filter output if not removed. All three conditioning steps -- high-pass filtering, resampling, and cropping filter transients -- must be applied in the correct order before PSD estimation. Each step addresses a distinct source of contamination, and omitting any one of them will produce meaningless SNR values.

### Template Preparation Requires Both Resizing and Cyclic Shifting
The template waveform must be resized to match the conditioned data length and cyclically shifted so the merger aligns with the start of the array. Omitting the resize causes a dimension mismatch in the frequency-domain multiplication. Omitting the cyclic shift misaligns the template relative to the data in the circular convolution, producing suppressed or incorrect SNR values.

### The Edges of the SNR Time Series Are Corrupted by Filter Transients
The matched filter output is corrupted at its boundaries by filter transients from both the PSD estimation and the template duration. The crop lengths must account for both the PSD segment duration and the template length. Searching for the peak SNR without first removing these corrupted regions will find spurious peaks at the boundaries rather than the true astrophysical signal.

### Waveforms Are Symmetric Under Exchange of m1 and m2
A system with (m1=25, m2=15) is physically identical to (m1=15, m2=25). The standard convention m1 >= m2 eliminates this redundancy and halves the number of templates in the grid search without any loss of coverage.

### The Detection SNR Is the Absolute Value of the Complex SNR Time Series
The matched filter returns a complex-valued SNR time series. The detection SNR is the modulus (absolute value) of this complex series, which maximizes over the unknown signal phase. Using only the real part, or the raw complex values, will underestimate the true SNR and can miss detections entirely.

### Frequency Parameters Must Be Consistent Across the Pipeline
The low-frequency cutoff used for waveform generation must be consistent with (or lower than) the cutoff used in the matched filter and the high-pass filter frequency. Mismatched cutoffs cause the template and data to cover different frequency ranges, reducing the overlap integral and suppressing the recovered SNR.
