# Flood Risk Analysis Using USGS and NWS Data

This document provides background on how hydrologists determine whether a river station is experiencing flood conditions, covering the data sources, measurement conventions, and analytical methods used in operational flood monitoring across the United States.

## Stream Gage Measurement and Gage Height

The United States Geological Survey (USGS) operates a nationwide network of stream gages that continuously measure water conditions at rivers, streams, and other bodies of water. Each station is identified by a unique numeric station ID (typically 8 digits, though some are longer).

The primary measurement relevant to flood detection is **gage height** (also called stage), recorded under USGS parameter code 00065. Gage height is the water surface elevation measured in feet above a local datum at the gage site. It is distinct from **discharge** (parameter code 00060), which measures the volume of water flow in cubic feet per second. While discharge is important for many hydrological analyses, flood determination is based on gage height because flood thresholds are defined in terms of water level, not flow volume.

USGS stations record **instantaneous values** (IV) at intervals of typically 15 minutes. This means a single day can have approximately 96 individual gage height readings. When assessing whether flooding occurred on a given day, the standard practice is to use the **daily maximum** gage height -- the highest instantaneous reading recorded during that calendar day. A day is considered a flood day if the daily maximum gage height meets or exceeds the flood threshold, regardless of how briefly the water level was elevated.

### Accessing USGS Data Programmatically

The USGS provides water data through the National Water Information System (NWIS). The Python library `dataretrieval` (specifically `dataretrieval.nwis`) offers programmatic access. The instantaneous value retrieval function returns data for specified sites, date ranges, and parameter codes. The returned DataFrame is indexed by datetime, with column names containing the parameter code (e.g., columns containing 00065 for gage height). Columns ending in `_cd` are qualifier codes and should be excluded when extracting numeric measurements.

Because instantaneous values are recorded at sub-daily intervals, the data must be **resampled to daily frequency** (using the maximum value for each calendar day) before comparing against flood thresholds. Comparing each 15-minute reading individually or using daily mean instead of daily max will produce incorrect flood day counts.

## NWS Flood Stage Thresholds

The National Weather Service (NWS), part of NOAA, defines flood thresholds for gaged locations across the country. These thresholds are published in the **NWS All Gauges Report**, a CSV file available at `https://water.noaa.gov/resources/downloads/reports/nwps_all_gauges_report.csv`.

This report contains metadata for thousands of stations including location names, coordinates, and critically, the **flood stage** -- the gage height (in feet) at which overflow of the natural banks of the stream begins to cause damage in the local area. The flood stage column is labeled `flood stage` in the CSV.

Each row in the NWS report includes a `usgs id` field that maps to the USGS station identifier. Not every USGS station has a corresponding NWS flood threshold. Only stations that appear in both the input station list and the NWS report (with a valid numeric flood stage value) should be analyzed. Stations without a defined flood stage threshold cannot be assessed for flooding and should be excluded from the analysis.

### Threshold Interpretation

A station experiences flooding on a given day when its **daily maximum gage height is greater than or equal to the flood stage**. This is a greater-than-or-equal comparison, not strictly greater-than. The distinction matters at boundary values: a daily max that exactly equals the flood stage counts as a flood day.

## Linking Data Sources: The Analysis Pipeline

Flood detection requires joining two independent data sources by station ID:

1. **NWS flood thresholds** -- provides the flood stage for each station
2. **USGS instantaneous gage height data** -- provides the actual water levels over time

The analysis proceeds as follows:

1. **Filter stations**: From the input list of USGS station IDs, identify which ones have a valid flood stage threshold in the NWS report. Only these stations can be evaluated.

2. **Retrieve gage height data**: For each station with a threshold, download instantaneous value data (parameter code 00065) from USGS NWIS for the specified date range.

3. **Compute daily maximums**: Resample the sub-daily instantaneous readings to daily frequency, taking the maximum value for each calendar day.

4. **Compare against thresholds**: For each day, check whether the daily maximum gage height meets or exceeds the flood stage. Count the number of such days per station.

5. **Filter results**: Only stations with at least one flood day should appear in the output.

The station ID serves as the join key between these datasets. Care must be taken to ensure consistent formatting -- USGS station IDs may have leading zeros (synthetic example: `00123456`) that must be preserved as strings, not parsed as integers (which would strip the leading zeros).

## Date Range and Temporal Boundaries

When querying USGS instantaneous data for a date range, the boundaries of the query determine which days are included. A query for April 1 through April 7 should cover all seven calendar days (April 1, 2, 3, 4, 5, 6, 7). The instantaneous data timestamps are in the station's local time zone. When resampling to daily frequency, the resampling aligns to calendar days based on the timestamp index. It is important that the query range captures full days -- if the end date is exclusive in the API being used, adjust accordingly so that all intended days are included.

## Output Format Conventions

Flood analysis results are typically reported as a table of station IDs paired with the count of flood days. Stations are generally sorted by flood severity (descending flood day count). Station IDs must remain as strings to preserve leading zeros. The flood day count is an integer.

## Domain-Specific Nuances

**Flood thresholds are defined in terms of gage height, not discharge.** NWS flood stages are specified in feet of gage height (USGS parameter code 00065), not in cubic feet per second of discharge (parameter code 00060). Retrieving discharge data instead of gage height produces values in incompatible units, making any threshold comparison meaningless.

**The daily maximum is the standard aggregation for flood assessment.** USGS instantaneous data has sub-daily resolution (typically 15-minute intervals). The daily maximum is used because flooding occurs when the peak water level reaches the threshold, even if it recedes later in the day. Other aggregation methods such as daily mean or individual reading comparison are not appropriate for this purpose.

**Station IDs must be treated as string identifiers throughout the pipeline.** An identifier such as the synthetic `00123456` has leading zeros. If parsed as an integer, those zeros are lost and the value will fail to match the NWS report's `usgs id` field or the input station list. String representation preserves the complete identifier.

**The flood stage comparison uses a greater-than-or-equal test.** The flood stage represents the threshold at which flooding begins. A gage height exactly equal to the flood stage is a flood condition. Using a strict greater-than comparison will undercount flood days for stations where the daily max exactly matches the threshold.

**The analysis must be scoped to stations with valid NWS thresholds.** Many USGS stations in the input list will not have a corresponding flood stage in the NWS report. These stations cannot be evaluated for flooding and must be excluded rather than analyzed with missing or default thresholds.

**Non-numeric flood stage values in the NWS report must be handled gracefully.** The NWS report may contain blank or non-numeric entries in the flood stage column. These entries should be treated as missing data and the corresponding stations excluded from analysis.
