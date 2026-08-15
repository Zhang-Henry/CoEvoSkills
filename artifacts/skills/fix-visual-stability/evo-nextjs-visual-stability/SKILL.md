---
name: evo-nextjs-visual-stability
description: "Fix visual stability issues (CLS, FOUC, FOIT) in Next.js e-commerce apps. Addresses theme flicker, font loading, image dimensions, and async content placeholders."
---

# Next.js Visual Stability Fixer

This skill fixes common visual instability issues in Next.js apps:

1. **Theme flicker (FOUC)**: Adds blocking inline script to set theme before first paint
2. **Font FOIT**: Adds `font-display: swap` to `@font-face` rules
3. **Image CLS**: Adds width/height to images missing dimensions
4. **Async content CLS**: Replaces `return null` loading states with space-reserving placeholders
5. **Skeleton loaders**: Uses skeleton components instead of text loading indicators

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-nextjs-visual-stability/scripts')
from run_all_fixes import run_all_fixes, validate_fixes

# Apply all fixes
results = run_all_fixes('/app')
print(results)

# Validate
validation = validate_fixes('/app')
assert validation['valid'], f"Validation failed: {validation['issues']}"
```

## Individual Fix Functions

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-nextjs-visual-stability/scripts')

from fix_theme_flicker import fix_theme_flicker
from fix_font_display import fix_font_display
from fix_image_dimensions import fix_image_dimensions
from fix_async_placeholders import fix_banner_placeholder, fix_sidepane_placeholder, fix_resultsbar_placeholder
from fix_product_skeleton import fix_product_list_skeleton
```

## Key Principles

- Never change existing class names, ids, or data-testid attributes
- Placeholders must use the same classes and testid as the final content
- Theme script must execute before first paint (in `<head>` or early `<body>`)
- `font-display: swap` prevents FOIT
- Images need both width and height for browser to reserve space
