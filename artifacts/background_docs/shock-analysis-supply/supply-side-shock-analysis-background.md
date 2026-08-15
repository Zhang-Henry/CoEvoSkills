# Supply-Side Shock Analysis Using Potential GDP Estimation

This document provides background on the macroeconomic theory and computational methods used to estimate the impact of an investment spending shock on a small open economy through a supply-side production function approach.

## The Cobb-Douglas Production Function

The Cobb-Douglas production function is the workhorse model of growth accounting. It describes the relationship between total output (GDP) and the inputs used to produce it. In its standard form, output equals total factor productivity multiplied by capital raised to the power alpha and labor raised to the power one minus alpha: Y = A * K^alpha * L^(1 - alpha), where:

- **Y** is real GDP (output)
- **K** is the physical capital stock
- **L** is the labor input (total employment or hours worked)
- **A** is total factor productivity (TFP), representing the efficiency with which capital and labor are combined
- **alpha** is capital's share of income (typically between 0.3 and 0.4 for most economies)

A critical property of the Cobb-Douglas function is **constant returns to scale**: doubling both K and L doubles Y. The parameter alpha governs how output responds to changes in each factor independently. A higher alpha means the economy is more capital-intensive, so investment shocks have a proportionally larger effect on potential output.

### Estimating TFP (the Solow Residual)

TFP is not directly observable. It is calculated as a residual after accounting for the contributions of capital and labor. Taking natural logarithms of both sides of the production function gives a linear relationship: ln(Y) = ln(A) + alpha * ln(K) + (1 - alpha) * ln(L). Rearranging to solve for the log of TFP yields ln(A) = ln(Y) - alpha * ln(K) - (1 - alpha) * ln(L).

In practice, since labor data may not always be available at the needed frequency or reliability, a simplified two-factor version is often used where the residual captures both TFP and labor contributions. In a spreadsheet context, this residual is often labeled **LnZ** and computed as LnZ = ln(Y) - alpha * ln(K).

This residual bundles true TFP with the labor contribution. When the goal is to estimate potential GDP (Y*) rather than to decompose growth sources precisely, this simplification is acceptable as long as the trend component is extracted consistently.

## The Hodrick-Prescott (HP) Filter

Raw economic time series contain both a long-run trend and short-run cyclical fluctuations. The HP filter is a standard method in macroeconomics for decomposing a time series into these two components.

### Mathematical Formulation

Given a time series {y_t} for t = 1, ..., T, the HP filter finds the trend component {tau_t} that minimizes the sum of two penalties. The first penalty is the sum of squared differences between the data and the trend across all time periods. The second penalty, weighted by the parameter lambda, is the sum of squared second-order differences of the trend (that is, the squared change-in-changes of the trend at each interior point). In notation, the objective is sum(y_t - tau_t)^2 + lambda * sum[(tau_{t+1} - tau_t) - (tau_t - tau_{t-1})]^2.

The first term penalizes deviation from the data (goodness of fit). The second term penalizes changes in the trend's growth rate (smoothness). The parameter **lambda** controls the trade-off:

- A larger lambda produces a smoother trend (approaching a linear trend as lambda approaches infinity)
- A smaller lambda allows the trend to track the data more closely
- For annual data, the standard convention is **lambda = 100** (also known as the Ravn-Uhlig recommendation for annual frequency)

### Implementation via Solver in Excel

In a spreadsheet, the HP filter is implemented as an optimization problem. The steps are:

1. **Initialize the trend decision series** by copying the raw series as starting values.
2. **Compute the second-order differences**: for each interior point t, calculate (tau_{t+1} - tau_t) - (tau_t - tau_{t-1}). This is the discrete second derivative of the trend.
3. **Compute the objective function**: the sum of squared deviations from data plus lambda times the sum of squared second-order differences. This single cell (the objective) is what the Solver minimizes.
4. **Sanity check**: before running Solver, the initialized trend equals the raw series, so a raw-minus-trend check should be zero. This confirms correct formula linkage.
5. **Run Solver**: discover the workbook's objective and decision-variable ranges from its visible labels and formulas, minimize the objective, and preserve the template's layout. Do not assume a fixed sheet, cell, or column name from a worked instance.

The output is a smoothed version of the TFP residual that represents the economy's trend productivity path, stripped of business cycle noise.

### Extending the Trend Beyond the Data

Historical data for LnZ typically ends at the last year for which both capital stock and GDP data are available. To project the trend forward, linear extrapolation of the HP-filtered LnZ series is used. This assumes that the underlying productivity trend continues at its recent historical pace. The extrapolation fits a least-squares line to the known values and returns predicted values for future time points.

## Capital Stock Dynamics and Depreciation

### The Perpetual Inventory Method

Capital stock evolves according to the accumulation equation: next period's capital equals the undepreciated portion of current capital plus new investment, or K_{t+1} = (1 - delta) * K_t + I_t, where:

- **K_t** is the capital stock at time t
- **delta** is the annual depreciation rate
- **I_t** is gross fixed capital formation (investment) at time t

This means next period's capital equals the undepreciated portion of current capital plus new investment. The depreciation rate delta represents the fraction of the capital stock that wears out, becomes obsolete, or is retired each year.

### Computing the Depreciation Rate

The depreciation rate is derived from the ratio of **consumption of fixed capital** (CFC) to the **capital stock**: delta_t = CFC_t / K_t.

CFC measures the value of capital that is used up during the production process in a given year. Dividing by the total capital stock gives the depreciation rate. Since this ratio fluctuates year to year due to compositional changes in the capital stock (e.g., shifts between long-lived structures and short-lived equipment), an analyst may use a documented, data-supported summary over a defensible historical window. The window and statistic must be derived from the supplied policy or runtime data rather than copied from a worked instance.

### Data Sources for Capital Stock and CFC

- **Penn World Table (PWT)**: Provides internationally comparable capital stock data. The variable `rnna` represents the capital stock at constant national prices. PWT data are available from 1950 (for some countries) through the most recent release year.
- **ECB Statistical Data Warehouse**: Provides consumption of fixed capital
  (CFC) for many economies. Select the series by inspecting its geography,
  frequency, sector, transaction, valuation, unit, and currency metadata; do not
  copy a fixed series identifier from a worked instance.

The depreciation rate is dimensionless only after its numerator and denominator
have been placed on compatible currency, scale, valuation, and price bases. A
current-price CFC series cannot be divided directly by a constant-price capital
series merely because the result is called a ratio. Read the visible source
metadata and make any required conversion once, explicitly, before forming the
ratio.

## Potential GDP (Y*) Estimation

### Baseline Potential GDP

Potential GDP (Y*) represents the level of output the economy can sustain without generating inflationary or deflationary pressure. It is the output level consistent with trend productivity and the current capital stock. Using the production function, baseline potential GDP is computed as Y*_base = exp(LnZ_trend) * K^alpha, where LnZ_trend is the HP-filtered (and possibly extended) productivity residual, and K is the actual or projected capital stock.

### Extending Capital Stock Beyond Observed Data

When capital stock data ends before the projection horizon, the capital-to-output ratio (K/Y) can provide a bridge. The procedure is:

1. **Compute K/Y** for all years where both K and Y are available.
2. **Anchor the ratio** using a documented statistic over a runtime-selected stable historical window. This captures structural capital intensity without assuming a fixed number of years.
3. **Extend K** by multiplying the anchored K/Y ratio by projected GDP: K_projected = (K/Y)_anchor * Y_projected.

GDP projections themselves come from the IMF World Economic Outlook (WEO), which provides forecasts through a near-term horizon. Beyond the WEO forecast period, the convention is to hold the growth rate constant at its last projected value.

## Modeling an Investment Spending Shock

### The Counterfactual Framework

A supply-side shock analysis compares two scenarios:

- **Baseline**: the economy evolves along its projected path with no additional investment
- **With-shock**: additional investment augments the capital stock, which raises potential GDP

The difference between Y*_with and Y*_base is the **uplift** attributable to the investment shock. This uplift can be expressed in absolute terms (additional GDP in national currency) or as a percentage of baseline GDP.

### Capital Accumulation with Additional Investment

Under the shock scenario, capital evolves as K_with_{t+1} = (1 - delta) * K_with_t + I_additional_t, where I_additional represents the exogenous investment (the shock), deflated to constant prices. The starting K_with equals the baseline K at the onset of the shock. As the shock phases in, K_with diverges increasingly from the baseline K.

Once K_with is computed, the with-shock potential GDP is Y*_with = exp(LnZ_trend) * K_with^alpha.

The uplift is then Y*_with - Y*_base. Note that because of the Cobb-Douglas functional form with alpha < 1, the relationship between additional capital and additional output exhibits **diminishing returns** -- each additional unit of capital contributes less to output than the previous one.

### Investment Deflation

Investment figures are typically stated in nominal (current-price) terms. To use them in a real (constant-price) production function, they must be deflated. Determine at runtime whether the supplied inputs are nominal, real, or already deflated by reading their visible labels, formulas, units, and source metadata; never assume a particular sheet contains precomputed values.

### Growth Rate Decomposition

Beyond the level effects, the model can compare growth rates for a reference scenario and a counterfactual scenario. Compute both from their corresponding level series. Their difference shows how an investment shock can temporarily change economic growth and how the effect attenuates as investment phases out and depreciation erodes additional capital.

## IMF World Economic Outlook (WEO) Data

The WEO database provides standardized macroeconomic data and forecasts for IMF member countries. Discover the applicable series from the current release's metadata rather than relying on a fixed variable code. For production-function work, distinguish a real output level in a documented national-currency scale from a real year-over-year growth rate, and verify units before combining either with other sources.

WEO data typically includes historical values and short-term projections (usually 2-5 years ahead). For long-range projections, the standard approach is to assume the growth rate in the final forecast year persists indefinitely. This steady-state growth assumption is a simplification but is standard practice for medium-term macroeconomic scenario analysis.

When extending GDP projections using a constant growth rate, each subsequent year's GDP is computed as the prior year's GDP multiplied by one plus the growth rate expressed as a decimal: GDP_{t+1} = GDP_t * (1 + g/100), where g is the growth rate in percentage terms from the last WEO forecast year.

## Data Source and Workbook Verification

Acquire data using the sources and method required by the task instruction. Before writing values, inspect each returned dataset and the supplied workbook to verify:

- the country or economy identifier,
- variable definitions and units,
- year coverage and whether values are historical or projected,
- the workbook's actual labels, formulas, and destination ranges.

Do not assume undocumented local mirrors, fixed source filenames, preset row numbers, or a particular overlap window. Align series by explicit year keys and record any unit conversions in workbook formulas or clearly labeled inputs. Preserve the template's intended formula flow and use the spreadsheet-based optimization method required by the instruction.

## Important Technical Details

**The production function operates entirely in real (constant-price) terms.** All monetary values in the model — GDP, capital stock, and investment — must be expressed in the same base-year prices. Mixing nominal GDP with real capital stock, or using nominal investment without deflation, produces meaningless results because price-level changes would be conflated with real quantity changes.

**The HP filter smoothing parameter differs by data frequency.** The standard conventions are lambda = 1600 for quarterly data and lambda = 100 for annual data (with lambda = 6.25 used in some annual calibrations). The choice of lambda is frequency-dependent because the ratio of cyclical to trend variation changes with the observation interval. Using the wrong lambda produces either an over-smoothed trend that misses structural shifts or an under-smoothed trend that tracks cyclical noise.

**The HP filter objective includes both fit and smoothness penalties simultaneously.** The optimization minimizes a single objective function that combines the sum of squared deviations from the data with lambda times the sum of squared second-order differences. Both terms must be included in the objective — the fit penalty alone would reproduce the raw data, while the smoothness penalty alone would produce a straight line. The Solver varies the entire trend column jointly to find the optimal balance.

**Unit consistency between data sources requires verification.** Source releases may report capital stock, GDP, and CFC in units, thousands, millions, or billions of national currency. Read the metadata for the downloaded series and convert all production-function inputs to a common scale before combining them. For the dimensionless depreciation ratio, numerator and denominator must use the same scale. Validate scale through explicit unit labels and identities rather than an expected answer range.

For a two-factor residual, a useful rowwise unit-ledger check is to reconstruct
output from the same inputs used to calculate it:
`EXP(LnY - alpha*LnK) * K^alpha` should reproduce `Y` apart from normal
floating-point precision. This identity does not supply a target output; it
detects inconsistent scale conversions in any dataset.

**The K/Y extension method assumes structural stability in capital intensity.** Extending the capital stock using an anchored K/Y ratio implicitly assumes the economy's capital intensity remains near its recent average. For economies undergoing rapid structural transformation, this assumption may not hold precisely. Using a multi-year average (rather than a single year) as the anchor mitigates short-term fluctuations but does not eliminate the underlying stationarity assumption.

**Use the spreadsheet optimization method required by the task.** Configure the workbook's objective and decision-variable cells and use the permitted Excel Solver workflow. Do not replace a required spreadsheet Solver result with an external optimizer unless the instruction explicitly allows that substitution.

**Recalculate and inspect the finished workbook.** Libraries that write formula strings do not necessarily evaluate them. Save the workbook, recalculate it with an available spreadsheet engine, reopen it in cached-value mode, and reject the artifact if required formula values remain missing or stale. Then verify key accounting identities. This is a workbook-integrity check, not a reason to replace formulas with hardcoded outputs.

**Formula-driven models ensure reproducibility and auditability.** The model is designed to be fully formula-driven so that changing any input (e.g., the investment amount, the depreciation rate, or updated GDP data) automatically propagates through all calculations. Intermediate results that are manually entered rather than computed from formulas break this chain and make the model non-reproducible.

**The Solow residual in a two-factor model captures more than pure TFP.** When labor is omitted from the production function, the residual LnZ captures both TFP and labor's contribution to output. This is acceptable for estimating potential GDP trends (since labor trends are embedded in LnZ), but the residual should be interpreted as a composite of technological progress and labor dynamics rather than pure technological change.
