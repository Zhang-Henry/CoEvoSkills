# D3.js Force-Directed Layouts and Interactive Data Visualization

This document covers the domain knowledge needed to build interactive, multi-view web visualizations using D3.js v6: force simulations for bubble charts, data-driven DOM manipulation, categorical color encoding, number formatting for financial data, tooltip interaction patterns, and coordinated view linking between charts and tables.

## D3.js v6 Force Simulation Fundamentals

D3's force simulation computes node positions by iterating a physics-based model. Each "tick" of the simulation applies forces to nodes and updates their x and y coordinates. The simulation starts with high energy (alpha) and gradually cools until it reaches a resting state.

### Core Forces

A simulation is composed by chaining individual force functions:

| Force | Purpose | Key Parameter |
|---|---|---|
| Center force | Pulls the whole system toward a center point | Center coordinates |
| Collision force | Prevents node overlap by pushing apart nodes whose radii would intersect | Radius accessor function |
| Many-body force | Applies attraction (positive strength) or repulsion (negative strength) among all nodes | Strength value |
| Positional X force | Pulls nodes toward a target x-coordinate | Strength value per node |
| Positional Y force | Pulls nodes toward a target y-coordinate | Strength value per node |
| Link force | Connects pairs of nodes with spring-like constraints | Distance and strength |

### Building a Clustered Bubble Chart

To group bubbles by a categorical attribute (e.g., sector), use positional forces with per-category target positions:

1. **Assign cluster centers.** Create a mapping from each category to an (x, y) coordinate. For example, if there are five categories, distribute their target positions across the chart width. A simple approach is to use an ordinal scale that maps category names to evenly spaced x-positions, with a shared y-center.

2. **Apply positional forces.** Configure the x and y positional forces so that each node is pulled toward its category's center. The target accessor returns the cluster center coordinates for each node based on its category. The strength of these forces controls how tightly clusters form. Too weak and clusters overlap; too strong and the simulation becomes rigid and may not spread nodes out enough to avoid overlap.

3. **Prevent overlap with collision detection.** Pass a radius accessor that returns each node's bubble radius plus a small padding value. This is the force that guarantees bubbles do not sit on top of one another. The radius accessor must match the actual rendered circle radius, or collisions will be incorrectly computed.

4. **Keep clusters centered.** Use a centering force or adjust cluster target coordinates to keep the overall layout centered within the SVG viewport. Without centering, the node group can drift to one edge, especially if cluster sizes are unbalanced.

### Simulation Timing and Rendering

- The simulation runs asynchronously. Attach a tick event handler that updates the position attributes of each circle element on every tick.
- The simulation's alpha decays from its initial energy toward a configurable minimum. It typically settles after a finite cooling period for modest layouts. Restarting the simulation re-energizes it after data changes.
- For initial rendering, it is common to let the simulation run for a short period before the layout becomes visually stable. Some implementations "pre-tick" the simulation by calling tick in a loop before rendering, which avoids the initial animation but gives an immediate stable layout.

### Technical Considerations for Force Simulations

- **Collision radius must match rendered radius**: Bubbles will overlap visually even though positions seem correct if the collision radius does not match the rendered radius. The collision force radius accessor and the rendered circle radius should use the same calculation.
- **Simulation restart is required after data changes**: Modifying node data after the simulation has cooled will not move nodes unless the simulation is restarted with renewed energy. This is the standard approach for responding to data updates in force layouts.
- **Initial node positions affect convergence speed**: If all nodes start at the same position, they may take a long time to separate. D3 initializes positions with a small random jitter by default, but for clustered layouts, initializing nodes near their cluster center speeds convergence considerably.
- **Cluster center spacing must accommodate cluster footprints**: If category target positions are tightly spaced relative to the bubble radii, clusters will merge visually. The target positions need enough separation to accommodate the largest cluster's footprint.
- **Center force and positional forces serve different roles**: The center force adjusts the center of mass of all nodes but does not pull individual nodes toward specific positions. It is distinct from positional x/y forces, which provide per-category clustering by pulling each node toward its category's target coordinates.

## Sizing Bubbles by Quantitative Data

When encoding a numeric value (such as market capitalization) as bubble area, the mapping must go through a **square-root scale**. Human perception of circle size correlates with area, not radius. If you map a value directly to radius, differences are visually exaggerated.

### The Correct Scale

A square-root scale is used with a domain of [minValue, maxValue] and a range of [minRadius, maxRadius]. The square-root transform ensures that the *area* of the resulting circle is proportional to the input value.

### Handling Missing or Non-Applicable Data

Not all entities in a dataset will have the same fields populated. For example, Exchange-Traded Funds (ETFs) typically lack a market capitalization figure because they are funds tracking an index, not individual companies with equity valuations. When a numeric sizing field is absent:

- Assign a **uniform default radius** to all such entries so they are visually distinct from data-driven bubbles but do not distort the layout.
- Do not use zero radius (the bubble would be invisible) or a calculated value from missing data (which would produce NaN and break the simulation).
- The uniform sizing signals to the viewer that these entities belong to a different category where the sizing metric does not apply.

## Categorical Color Encoding and Legends

### Assigning Colors to Categories

D3 provides built-in ordinal color scales that map distinct categorical values to perceptually distinct colors. The typical pattern is to create an ordinal scale with a domain set to the list of category names (e.g., "Energy", "Financial", etc.) and a range of a standard categorical color palette.

Each category should map to exactly one color, and that mapping must be consistent between the bubble chart and the legend.

### Building a Legend

A legend translates the color encoding back into category labels. The recommended approach is to build the legend as **HTML elements** (e.g., a `<div>` with class "legend" or id "legend") rather than SVG group elements. HTML legends are more accessible, easier to style with CSS, and compatible with standard DOM text extraction methods. Each legend entry can be a `<div>` or `<span>` containing a small colored swatch (a `<span>` with a CSS background-color) and a text label.

If an SVG-based legend is used instead, be aware that SVG elements are not standard HTML elements — DOM methods like `innerText` will not work on SVG nodes, which can break automated testing and accessibility tools.

Steps:

1. Create an HTML container element (e.g., `<div class="legend">` or `<div id="legend">`) placed near the chart.
2. For each category, append a child element containing a colored swatch and a text label.
3. Position legend entries vertically or horizontally with consistent spacing.

The legend must include **every** category present in the data, not just the most common ones. Omitting a category means the viewer cannot decode some bubbles' colors.

### Labeling Bubbles with Text

Placing text labels (e.g., ticker symbols) inside bubbles requires:

- Appending text elements at the same position as each circle.
- Setting text-anchor to middle and dominant-baseline to central (or an equivalent vertical offset) to center the text within the circle.
- Using a font size that fits within the circle radius. For very small bubbles, labels may need to be abbreviated or hidden.
- Updating text positions on each simulation tick alongside the circle positions, since the force simulation moves nodes continuously.

### Pointer Events When Labels Overlay Marks

An SVG text label drawn on top of a circle can become the browser's pointer-event target. If interaction handlers are attached only to the circle, moving the pointer over the visible label may therefore fail to trigger the circle's hover behavior even though the user is visually inside the bubble. Two standard designs avoid this dead zone:

- Treat the label as decorative and set `pointer-events: none` on it, allowing pointer events to reach the circle underneath.
- Wrap the circle and its label in the same SVG group and attach the interaction handlers to that group, so either child participates in one interaction target.

Choose one event-ownership design consistently for hover, click, keyboard focus, and highlighting. If the label itself must remain interactive, use the group approach or forward its events to the same shared handler rather than maintaining separate selection logic.

## Formatting Large Numbers for Human Readability

Large raw values are difficult to scan. Financial displays commonly use
suffixes based on powers of ten:

| Suffix | Meaning | Example |
|---|---|---|
| K | Thousands (10^3) | 45.5K |
| M | Millions (10^6) | 320M |
| B | Billions (10^9) | 58.3B |
| T | Trillions (10^12) | 2.75T |

### Formatting Logic

The general algorithm for human-readable number formatting:

1. Determine the magnitude of the number by comparing against threshold boundaries (trillions, billions, millions, thousands).
2. Divide by the appropriate power of ten.
3. Round to a reasonable number of decimal places (typically one or two).
4. Append the suffix letter.

For an unrelated synthetic example, `2,750,000,000,000 / 10^12 = 2.75`, so it
may be displayed as `2.75T`.

D3 provides number formatting utilities, but the SI-suffix version uses standard SI prefixes (G for giga, T for tera) which may not match financial conventions (B for billions). Custom formatting logic or post-processing is often needed for financial displays.

### Handling Absent Values

When a numeric field is missing (e.g., ETFs without market capitalization), display a placeholder such as "-" or "N/A" rather than showing "undefined", "NaN", or an empty cell.

## Tooltip Interaction Patterns

Tooltips display contextual information when the user hovers over a visual element. The standard implementation in D3 visualizations:

### Structure

1. Create a single div element (the tooltip container) appended to the page body, initially hidden via CSS (opacity 0 or visibility hidden).
2. On mouseover / mouseenter of a visual element, populate the tooltip with the element's data and make it visible.
3. On mousemove, reposition the tooltip to follow the cursor.
4. On mouseout / mouseleave, hide the tooltip.

### Visibility Control

A common CSS pattern uses an opacity transition with a class toggle:

The tooltip class sets opacity to 0, a transition on opacity, and pointer-events to none. The tooltip visible state sets opacity to 1.

Adding/removing the visible class controls display. The pointer-events: none rule prevents the tooltip div from interfering with mouse events on the underlying chart elements.

### Conditional Tooltip Display

Some data categories should not display tooltips because they lack the relevant fields. For instance, if a tooltip is designed to show company name, sector, and market cap, entities that lack these fields (such as ETFs) should suppress the tooltip entirely. This requires a conditional check in the mouseover handler:

In the mouseover handler, check whether the datum has the relevant data fields. If not, return immediately without showing the tooltip.

Simply showing a tooltip with empty or "N/A" fields for every data point is a poor user experience. The decision to show or hide should be driven by whether the entity has meaningful data for the tooltip's content.

### Content Composition

A tooltip typically displays multiple fields from the data record. For a stock entity, relevant fields might include:

- **Ticker symbol** -- the short identifier
- **Full company name** -- the human-readable name
- **Sector** -- the categorical classification

Format the tooltip content as HTML within the tooltip div, using line breaks or structured layout for clarity.

## Coordinated Multi-View Interaction (Linking)

When a visualization includes multiple views of the same data (e.g., a chart and a table), interactions in one view should propagate to the other. This is called "brushing and linking" or "coordinated views."

### Click-to-Highlight Pattern

The most common coordination pattern:

1. **Bubble click handler**: When the user clicks a bubble, identify the corresponding data record (e.g., by ticker symbol). Apply a visual highlight to the clicked bubble (stroke change, opacity change, size pulse). Find the matching row in the table and apply a highlight class (e.g., selected or highlighted with a distinct background color).

2. **Table row click handler**: When the user clicks a table row, identify the corresponding data record. Apply a highlight to the matching bubble in the chart. Scroll the table to ensure the highlighted row is visible if needed.

3. **Selection state management**: Maintain a single "selected" state variable. Each click updates this state, removes highlights from the previously selected element, and applies highlights to the newly selected element in both views.

### CSS Highlight Classes

Define a CSS class for the highlighted state:

The selected row CSS rule sets a visually distinct background color (such as a light highlight color) to indicate the highlighted row.

Toggle this class in JavaScript. The highlight must be detectable either through the class name or through a computed background-color change.

### Table Layout Considerations

When placing a chart and a table side by side:

- Use CSS flexbox or CSS grid on the container to arrange elements horizontally.
- Both elements should share approximately the same vertical starting position. A large vertical offset between the chart and the table signals a stacked (vertical) layout rather than a side-by-side (horizontal) one.
- The table should be scrollable if it contains many rows, using overflow-y auto with a fixed height, so it does not push the page layout beyond the viewport.

## Working with CSV Data in D3

D3 provides CSV loading and parsing functionality. Key considerations:

### Parsing and Type Coercion

CSV loading returns all values as strings by default. Numeric fields must be explicitly converted:

After loading the CSV, iterate through each row and explicitly convert numeric fields from strings to numbers. Before conversion, check whether the field is truthy (non-empty); if it is empty or missing, assign null rather than converting, since applying numeric conversion to an empty string yields 0 rather than a null value.

Failing to convert strings to numbers causes scale computations and comparisons to produce incorrect results. An empty string converted to a number yields 0, not null, so checking for empty/missing values before conversion is essential.

### Data with Embedded Special Characters

CSV fields containing commas, newlines, or quotation marks are enclosed in double quotes per the CSV specification. Standard CSV parsers handle this correctly, but custom parsing (e.g., splitting on commas manually) will break on fields with embedded commas. The longBusinessSummary field in a stock description dataset is a typical example -- it often contains commas, line breaks, and special characters within a quoted field.

### Serving Files Locally

When loading CSV files in a browser, same-origin policy is enforced. Loading from a file:// URL will fail with a CORS error. The standard workaround is to serve the files through a local HTTP server. This is also the pattern used in automated testing with headless browsers.

## Single-Page Web Application Structure

A self-contained D3 visualization is typically organized as:

| File | Role |
|---|---|
| index.html | Entry point; loads CSS and JS; contains DOM containers for chart and table |
| css/style.css | Layout rules (flexbox/grid for side-by-side arrangement), tooltip styling, table formatting, highlight classes |
| js/d3.v6.min.js | D3 library (loaded first, before visualization code) |
| js/visualization.js | All visualization logic: data loading, scale setup, force simulation, DOM rendering, event handlers |
| data/ | Source data files (CSV, JSON) copied from the input dataset |

### Offline / Self-Contained Operation

For portability, the D3 library file should be included locally rather than loaded from a CDN. This ensures the visualization works without internet access. The library file should be placed in the js/ directory and referenced via a relative script tag.

## What Does NOT Work

Several approaches commonly attempted in D3 visualizations lead to incorrect or broken results:

- **Mapping values directly to radius instead of area**: Creates a misleading chart where large values appear disproportionately larger than they are. Square-root scaling is the standard for bubble sizing to ensure area-proportional encoding.
- **Using positional forces without collision detection**: Nodes cluster at their target positions but overlap heavily, making individual bubbles indistinguishable.
- **Using only collision detection without positional forces**: Nodes spread out uniformly with no categorical grouping. The chart becomes a random scatter of circles.
- **Setting tooltip display to none/block without transition**: The tooltip appears and disappears abruptly. More critically, some visibility-detection approaches (e.g., checking for a visible class) will not work if the implementation uses display toggling instead.
- **Placing text elements inside circle elements in SVG**: SVG does not support nested content inside circle elements. Text labels must be sibling elements positioned at the same coordinates, or both the circle and text must be wrapped in a group element.
- **Updating only circle positions on simulation tick without updating text**: If only circles are updated in the tick handler but text labels are not, labels will remain at their initial positions while bubbles move.
- **Loading the D3 library from a CDN in an offline environment**: The script tag will fail silently, and all D3 API calls will throw errors indicating the library is not defined.
- **Not copying source data to the output directory**: If the visualization references data files via relative paths, those files must exist in the served directory structure. A missing data file causes a silent load failure and an empty visualization.
- **Building the table with string concatenation of HTML**: This approach is fragile and does not integrate with D3's data-join pattern. Using D3's data binding and join pattern for table construction is more robust and maintainable.
