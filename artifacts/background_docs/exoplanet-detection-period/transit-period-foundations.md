# Transit-Period Detection Foundations

Transit photometry searches for repeated, short-lived decreases in stellar
brightness. Space-based light curves also contain flagged cadences, gaps,
outliers, instrumental trends, heteroscedastic uncertainties, and stellar
variability on overlapping time scales.

Quality flags define which observations are trusted. Robust preprocessing
should preserve timestamps and uncertainties, avoid allowing transit-like
negative excursions to define the outlier model, and document how gaps and
non-finite values are handled. Detrending aims to remove variability longer
than a transit while retaining transit depth and duration; excessive smoothing
can erase the signal or create periodic artifacts.

Sinusoidal periodograms are useful for smooth variability, whereas box-shaped
search statistics are better matched to transits. Candidate peaks may occur at
the true period, harmonics, subharmonics, or sampling aliases. Folding the data
at a candidate period and checking whether multiple events align is therefore
as important as the raw peak height.

A credible period estimate is stable to reasonable preprocessing choices,
supported by more than one event, and accompanied by checks of phase coverage,
event duration, depth, odd/even consistency, and nearby aliases. Numerical
refinement and final rounding should be separated so presentation precision
does not constrain the search.
