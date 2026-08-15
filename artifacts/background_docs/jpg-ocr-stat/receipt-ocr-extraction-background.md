# General Background: OCR on Noisy Receipts

Optical character recognition converts pixels into text; it does not by itself
determine what a recognized number means.  A receipt-processing system normally
separates recognition, field interpretation, normalization, and output
validation so that an error in one stage can be diagnosed without silently
changing the others.

## Recognition under variable image quality

Thermal paper, skew, uneven lighting, compression, small type, and decorative
layouts can all reduce OCR accuracy.  Grayscale conversion, contrast adjustment,
thresholding, rotation correction, and moderate upscaling are common image
preparations.  Their value depends on the image: an aggressive transform that
helps faded text can erase punctuation or thin characters elsewhere.

Tesseract and similar engines offer different layout-segmentation assumptions.
A page may behave like a single text block, a column, or sparse text.  Trying a
small number of plausible recognition settings and retaining their raw text is
often more robust than assuming one configuration is universally best.

Common confusions include `O`/`0`, `I`/`l`/`1`, decimal punctuation, inserted
spaces, and broken lines.  Corrections should be local to a field parser.  A
global character replacement can damage ordinary words that are later needed
for semantic classification.

## Interpreting fields

Receipts contain several dates and monetary values with different roles.  Field
selection should use nearby labels, layout, and consistency rather than simply
choosing the first or largest number.  In particular, a final payable amount is
semantically different from a subtotal, tax, discount, tendered cash, or change.
Labels and values may also be separated by OCR line breaks.

Date strings can use different component orders and two- or four-digit years.
Unambiguous value ranges and locale evidence can support an interpretation, but
ambiguous dates should not be resolved by a fixed country assumption that was
not established from the current input.

Number normalization likewise depends on whether punctuation is a decimal mark
or a grouping separator.  Preserve the original recognized token until the
surrounding currency and formatting evidence has been considered.

## Validation and uncertainty

Useful checks include confirming that every discovered input has exactly one
output record, output ordering is deterministic, normalized dates are valid,
and monetary formatting matches the requested interface.  Keep failures as
missing values when the evidence is insufficient instead of manufacturing a
plausible field.  Saving intermediate OCR text and candidate confidence makes
errors reproducible and helps target a second recognition pass only where it is
needed.
