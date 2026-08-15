# Visual Stability in Web Applications

This document provides background on the browser rendering mechanics, performance metrics, and front-end patterns that govern visual stability in modern web applications, with a focus on React and Next.js environments.

## Core Web Vitals and Cumulative Layout Shift

Google's Core Web Vitals are a set of user-centric performance metrics that quantify real-world aspects of the user experience. The metric most directly concerned with visual stability is **Cumulative Layout Shift (CLS)**.

### What CLS Measures

CLS quantifies how much visible content moves around unexpectedly after the page has started rendering. Every time a visible element changes its position between two rendered frames without being triggered by user interaction, the browser records a **layout shift entry**. Each entry has a `value` representing the fraction of the viewport that was affected.

CLS is not simply the sum of all layout shift values. It uses a **session window** algorithm:

1. Layout shifts are grouped into **session windows**. A session window begins with the first layout shift and remains open as long as shifts continue to occur within 1 second of each other, up to a maximum window duration of 5 seconds.
2. If more than 1 second passes without a shift, or if the window exceeds 5 seconds, the current window closes and the next shift starts a new window.
3. The CLS score for the page is the **maximum session window score** -- the highest sum of shift values within any single session window.

This windowed approach means that a single burst of rapid shifts (such as several elements repositioning during initial load) is treated differently than shifts spread across the entire page lifecycle. A concentrated burst in one window may produce a lower CLS than the same total shift spread across multiple windows, because only the worst window counts.

### What Triggers Layout Shifts

A layout shift occurs when a rendered element changes its start position between frames. Common causes include:

- **Dynamically injected content**: Elements that appear in the DOM after surrounding content has already rendered push that content to new positions. Banners, notification bars, sidebars, and toolbars that load asynchronously are classic culprits.
- **Images and media without dimensions**: When an `<img>` tag lacks explicit `width` and `height` attributes (or equivalent CSS sizing), the browser initially lays out the element at zero size. Once the image loads, it expands to its natural dimensions, pushing surrounding content downward.
- **Late-loading web fonts**: When a custom font takes time to load and the browser behavior causes text to reflow once the font arrives, character widths change and layout shifts follow.
- **Client-side state changes that alter layout**: In single-page applications, state changes that conditionally render or remove elements (such as toggling a component from `null` to a visible element) cause the same kind of content displacement.

Crucially, layout shifts that follow a recent user input (a click, tap, or keypress within the preceding 500ms) are **excluded** from CLS. The metric only captures unexpected shifts.

### Rating Scale

Google classifies CLS scores into three bands: "good," "needs improvement," and "poor." A page that keeps its CLS in the "good" range delivers a visually stable experience where users are not distracted by content jumping around. Higher scores indicate progressively worse instability, which erodes user trust and can lead to mis-clicks when interactive elements shift under the cursor.

## The Hydration Gap and Theme Flicker

In server-rendered React frameworks like Next.js, the server sends pre-rendered HTML to the browser, and then the client-side JavaScript takes over in a process called **hydration**. During hydration, React attaches event handlers and reconciles the server-rendered DOM with the client-side component tree.

### Why Theme Flicker Happens

A common pattern in React applications is to store the user's preferred theme (light or dark) in localStorage and apply it on mount using a post-hydration effect hook. The problem is that such effect hooks run **after** hydration -- after the browser has already painted the initial frame. The sequence is:

1. Server renders HTML with a default theme (typically light).
2. Browser paints this default-themed page immediately.
3. React hydrates the component tree.
4. The effect hook fires, reads localStorage, and updates the theme.
5. Browser repaints with the correct theme.

Steps 2 through 5 produce a visible flash: the user sees the wrong theme for a fraction of a second before it snaps to the correct one. This is commonly called **FOUC (Flash of Unstyled Content)** in the theme context, or simply **theme flicker**.

### How to Prevent Theme Flicker

The solution is to apply the theme **before** React hydration, during the initial HTML parse. This is achieved by inserting a **blocking inline script** in the `<head>` (or very early in `<body>`) that:

1. Reads the saved theme from localStorage.
2. Applies it to the DOM immediately -- typically by setting a data attribute on the root HTML element, or by adding/modifying a CSS class, or by directly manipulating inline styles.

Because this script executes synchronously during HTML parsing (before the browser's first paint), the correct theme is in place from the very first frame the user sees. There is no flash.

In Next.js specifically, inline scripts in the document head can be injected using raw HTML insertion on a script tag within a custom document component or the root layout. The script must be inline (not an external file reference) so that it executes synchronously during parsing. Alternatives include Next.js's Script component with a "beforeInteractive" strategy, though the raw inline approach is the most reliable for critical-path theme application.

### Key Technical Constraints

The inline script must reference localStorage and must apply the theme to the DOM in a way that CSS can target. Common DOM manipulation patterns include:

- Adding or toggling a class on the document's root element
- Setting a data attribute (such as data-theme) on the root element
- Setting a style property directly on the root element or the body element
- Targeting an element by ID and modifying its class or style

Any of these patterns, combined with reading from localStorage, constitutes the flicker prevention technique.

## Font Loading Strategies and FOIT

When a web page uses custom fonts loaded via `@font-face`, the browser must decide what to display while the font file is being downloaded. There are two undesirable outcomes:

- **FOIT (Flash of Invisible Text)**: The browser hides text entirely until the custom font arrives. Users see a blank space where text should be, then it suddenly appears. This is the default behavior in many browsers.
- **FOUT (Flash of Unstyled Text)**: The browser shows text in a fallback system font, then swaps to the custom font once it loads. The text is always visible, but there is a brief visual reflow.

### The font-display Property

The CSS `font-display` descriptor controls which strategy the browser uses. It is declared inside an `@font-face` rule alongside the font-family, src, and other descriptors. For example, an `@font-face` rule would declare the font-family name, specify the src URL pointing to the font file, and include `font-display: swap` to control loading behavior.

The most relevant values are:

- **`auto`**: Browser-default behavior, which in practice is usually equivalent to `block` (FOIT).
- **`block`**: Text is invisible during a long block period (typically 3 seconds), then falls back. This causes FOIT.
- **`swap`**: Text is displayed immediately in the fallback font. When the custom font loads, it swaps in. This eliminates FOIT entirely -- text is always visible -- though it may cause a minor reflow.
- **`fallback`**: A very short block period (~100ms), then fallback. If the font does not load within a short swap period, the fallback is kept permanently.
- **`optional`**: The browser may choose not to use the custom font at all if it does not load quickly enough.

For most applications, `swap` is the recommended choice because it ensures text is always visible to the user. The brief reflow when the custom font arrives is a far better experience than invisible text. When `font-display` is omitted entirely, browsers typically default to the `auto`/`block` behavior, causing FOIT.

### How Browsers Expose font-display

At runtime, loaded fonts are accessible through the document's font API (the FontFaceSet interface). Each FontFace object exposes a display property reflecting the font-display value from the originating `@font-face` rule. This provides a programmatic way to verify that font-loading behavior is correctly configured.

## Images and Layout Reservation

Images are one of the most common sources of layout shift on the web. The issue arises from the mismatch between when the browser lays out the page and when it knows the image's dimensions.

### The Problem

When an `<img>` element has no explicit sizing information, the browser allocates zero space for it in the initial layout. Once the image file's headers arrive and the browser learns the intrinsic dimensions, it recalculates the layout, expanding the image to its natural size and pushing surrounding content downward. This is a layout shift.

### The Solution: Explicit Dimensions

Providing the browser with dimension information before the image loads allows it to reserve the correct amount of space from the start. There are several equivalent approaches:

- **HTML attributes**: `<img width="400" height="300">` tells the browser the intrinsic dimensions. Modern browsers use these to compute the aspect ratio and reserve space even before the image loads.
- **CSS `width` and `height`**: Explicitly setting both dimensions via inline styles or a stylesheet.
- **CSS `aspect-ratio`**: Setting `aspect-ratio: 4/3` (or the appropriate ratio) on the image element, in combination with one dimension, allows the browser to compute the other and reserve space.

The underlying principle is the same in all cases: the browser must know the aspect ratio and at least one dimension before the image data arrives so that it can reserve a correctly-sized box in the layout. Whether this comes from HTML attributes, CSS properties, or the `aspect-ratio` declaration is a matter of implementation preference.

In React and Next.js, the next/image component handles this automatically by requiring width and height props (or using the fill layout mode). When using raw `<img>` tags, the developer must provide these dimensions manually.

## Asynchronous Content Insertion and Layout Reservations

Single-page applications frequently load content asynchronously -- fetching data from APIs and rendering components only when the data arrives. When a component conditionally renders (returning nothing while loading and a visible element after data arrives), the act of inserting that element into the DOM displaces everything below it. Each such insertion is a layout shift.

### Placeholder Strategies

The general technique for preventing layout shifts from asynchronous content is **reserving space** before the content arrives. Several patterns accomplish this:

- **Skeleton screens**: Placeholder elements that match the dimensions of the eventual content. A skeleton for a product card grid, for example, renders the same number of card-shaped boxes with the same padding and margins as the real cards. When real data replaces the skeletons, no content moves because the space was already occupied.
- **Fixed-height containers**: Wrapping asynchronous content in a container with a predetermined minimum height. Even if the container is empty, it occupies the correct amount of vertical space.
- **CSS containment**: Using `contain: layout` or `contain: size` to tell the browser that an element's internal layout changes should not affect elements outside it.

The key insight is that any component that renders nothing during its loading state and then renders a block of content is guaranteed to cause a layout shift. The solution is to always render a placeholder that occupies the same space the final content will occupy.

### Banners, Toolbars, and Injected UI

A particularly impactful category of layout shift comes from full-width UI elements (promotional banners, cookie consent bars, notification strips) that insert themselves at the top of the page after surrounding content has already rendered. Because these elements sit above the main content, their insertion pushes **everything** on the page downward, producing large CLS values proportional to the viewport fraction displaced.

The mitigation is the same: reserve space for these elements from the first render. If a banner will eventually be 80px tall, the layout should include an 80px placeholder from the start, regardless of whether the banner data has arrived.

## Practical Considerations

**Critical visual state must be established before the first paint.** Any visual property that must be correct on the first frame (theme, locale-specific layout, user preferences) needs to be applied during the HTML parsing phase, before the browser's first paint. Post-hydration effect hooks in React run after the first paint, which means they are appropriate for non-visual side effects but not for properties that the user will see immediately upon page load. The standard approach is to use blocking inline scripts in the document head.

**Components should always render a space-occupying element, even while loading.** Components that render nothing while waiting for data and then render content always cause layout shifts. The standard pattern is to render a same-sized placeholder instead of nothing. This applies to every asynchronously-loaded section of the page, including side panels, toolbars, and banners.

**The font-display descriptor controls text visibility during font loading.** When custom fonts are declared via `@font-face`, the `font-display` descriptor determines whether the browser shows invisible text (FOIT) or fallback text (FOUT) while the font downloads. The `swap` value ensures text is always visible, which is the recommended behavior for most applications. When `font-display` is omitted, browsers default to the block behavior, which hides text during the download period.

**Both dimensions are needed for image space reservation.** Providing only one dimension (width without height, or vice versa) does not give the browser enough information to compute the aspect ratio. Both dimensions must be available -- through any combination of HTML attributes, CSS properties, or the aspect-ratio declaration -- for the browser to reserve the correct amount of space before the image data arrives.

**Skeleton loaders must match the final content dimensions.** Skeleton components only prevent layout shifts if they occupy exactly the same space as the real content they replace. A skeleton that is shorter or narrower than the final component will still cause a shift when the real content renders. The dimensions, margins, and padding must match precisely.

**Inline scripts must execute before the first paint to be effective.** An inline theme script placed at the end of the body (or loaded as an external module) will execute after the browser has already painted the initial frame, which means the theme correction arrives too late. For the script to prevent flicker, it must execute during the parsing of the head or very early in the body, before the first paint occurs.
