# General Background: Trend Anomalies and Causal Analysis

Observational commerce data often combines transactions, customer attributes,
and time. Before modeling, identifiers and timestamps must be normalized,
duplicate records understood, missing values handled explicitly, and joins
checked for unintended row multiplication or loss.

## Counterfactual anomaly analysis

A time-series anomaly is a departure from a reasonable counterfactual: what the
series would likely have done without the event being studied. Forecasts should
be trained only on information available before the evaluation period. Trend,
seasonality, sparse categories, outliers, and calendar effects can all affect
the counterfactual.

An anomaly index may normalize the difference between actual and forecast
values, but its scale and transformation should be declared and applied
consistently. Diagnostics should examine residuals, calibration, category
coverage, and sensitivity to plausible model choices instead of relying only on
the most extreme ranks.

## Difference-in-differences

Difference-in-differences compares outcome changes over time between groups. A
causal interpretation depends on assumptions such as parallel trends, stable
group composition, absence of differential concurrent shocks, and an
appropriate observational unit. Repeated transactions from the same user are
not automatically independent observations; aggregation or clustered
uncertainty may be needed.

Demographic and survey features must be encoded consistently, with missingness,
reference categories, constant columns, and multicollinearity handled
deliberately. Intensive-margin and extensive-margin outcomes answer different
questions and should not be mixed without explanation.

## Reproducibility

Training windows, comparison periods, grouping rules, feature definitions,
model formulas, uncertainty estimates, and ranking policies should come from the
task instruction or be justified from the supplied data. They must not be
hard-coded from a previous dataset. Output validation should cover schema,
uniqueness, finite numeric values, row provenance, and consistency between
reported summaries and the underlying model results.
