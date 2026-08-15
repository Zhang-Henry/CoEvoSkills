"""End-to-end entry point: apply all visual stability fixes to a Next.js app."""
import os
import sys

def run_all_fixes(app_root: str) -> dict:
    """Apply all visual stability fixes to the Next.js app at app_root.
    
    Returns a dict of fix names to success status.
    """
    results = {}
    
    # Import fix modules
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    
    from fix_theme_flicker import fix_theme_flicker
    from fix_font_display import fix_font_display
    from fix_image_dimensions import fix_image_dimensions
    from fix_async_placeholders import fix_banner_placeholder, fix_sidepane_placeholder, fix_resultsbar_placeholder
    from fix_product_skeleton import fix_product_list_skeleton
    
    src = os.path.join(app_root, 'src')
    components = os.path.join(src, 'components')
    app_dir = os.path.join(src, 'app')
    
    # 1. Fix theme flicker
    try:
        fix_theme_flicker(os.path.join(app_dir, 'layout.tsx'))
        results['theme_flicker'] = True
    except Exception as e:
        print(f"Error fixing theme flicker: {e}")
        results['theme_flicker'] = False
    
    # 2. Fix font-display
    try:
        fix_font_display(os.path.join(app_dir, 'globals.css'))
        results['font_display'] = True
    except Exception as e:
        print(f"Error fixing font display: {e}")
        results['font_display'] = False
    
    # 3. Fix image dimensions
    try:
        fix_image_dimensions(os.path.join(components, 'ProductCard.tsx'))
        results['image_dimensions'] = True
    except Exception as e:
        print(f"Error fixing image dimensions: {e}")
        results['image_dimensions'] = False
    
    # 4. Fix Banner placeholder
    try:
        fix_banner_placeholder(
            os.path.join(components, 'Banner.tsx'),
            'promo-banner',
            'bg-[#0070f3] text-white py-24 px-4 text-center font-bold text-2xl'
        )
        results['banner_placeholder'] = True
    except Exception as e:
        print(f"Error fixing banner: {e}")
        results['banner_placeholder'] = False
    
    # 5. Fix LateBanner placeholder
    try:
        fix_banner_placeholder(
            os.path.join(components, 'LateBanner.tsx'),
            'late-banner',
            'bg-[#ff6b35] text-white py-32 px-4 text-center font-bold text-[28px]'
        )
        results['late_banner_placeholder'] = True
    except Exception as e:
        print(f"Error fixing late banner: {e}")
        results['late_banner_placeholder'] = False
    
    # 6. Fix SidePane placeholder
    try:
        fix_sidepane_placeholder(os.path.join(components, 'SidePane.tsx'))
        results['sidepane_placeholder'] = True
    except Exception as e:
        print(f"Error fixing sidepane: {e}")
        results['sidepane_placeholder'] = False
    
    # 7. Fix ResultsBar placeholder
    try:
        fix_resultsbar_placeholder(os.path.join(components, 'ResultsBar.tsx'))
        results['resultsbar_placeholder'] = True
    except Exception as e:
        print(f"Error fixing resultsbar: {e}")
        results['resultsbar_placeholder'] = False
    
    # 8. Fix ProductList skeleton
    try:
        fix_product_list_skeleton(os.path.join(components, 'ProductList.tsx'))
        results['product_skeleton'] = True
    except Exception as e:
        print(f"Error fixing product skeleton: {e}")
        results['product_skeleton'] = False
    
    return results


def validate_fixes(app_root: str) -> dict:
    """Validate that all fixes were applied correctly."""
    issues = []
    src = os.path.join(app_root, 'src')
    components = os.path.join(src, 'components')
    app_dir = os.path.join(src, 'app')
    
    # Check layout.tsx has blocking theme script
    with open(os.path.join(app_dir, 'layout.tsx'), 'r') as f:
        layout = f.read()
    if 'dangerouslySetInnerHTML' not in layout or 'localStorage' not in layout:
        issues.append('layout.tsx missing blocking theme script')
    
    # Check globals.css has font-display: swap
    with open(os.path.join(app_dir, 'globals.css'), 'r') as f:
        css = f.read()
    if 'font-display' not in css:
        issues.append('globals.css missing font-display: swap')
    
    # Check ProductCard has image dimensions
    with open(os.path.join(components, 'ProductCard.tsx'), 'r') as f:
        pc = f.read()
    if 'width=' not in pc and 'width={' not in pc:
        issues.append('ProductCard.tsx missing image width')
    if 'height=' not in pc and 'height={' not in pc:
        issues.append('ProductCard.tsx missing image height')
    
    # Check banners don't return null
    for fname in ['Banner.tsx', 'LateBanner.tsx', 'SidePane.tsx']:
        with open(os.path.join(components, fname), 'r') as f:
            comp = f.read()
        if 'return null' in comp:
            issues.append(f'{fname} still returns null (no placeholder)')
    
    # Check ResultsBar doesn't return null
    with open(os.path.join(components, 'ResultsBar.tsx'), 'r') as f:
        rb = f.read()
    if 'return null' in rb:
        issues.append('ResultsBar.tsx still returns null')
    
    # Check ProductList uses skeletons
    with open(os.path.join(components, 'ProductList.tsx'), 'r') as f:
        pl = f.read()
    if 'Loading products' in pl:
        issues.append('ProductList.tsx still uses text loading indicator')
    if 'ProductSkeleton' not in pl:
        issues.append('ProductList.tsx not using ProductSkeleton component')
    
    if issues:
        print("Validation FAILED:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("All fixes validated successfully!")
    
    return {'valid': len(issues) == 0, 'issues': issues}


if __name__ == '__main__':
    app_root = sys.argv[1] if len(sys.argv) > 1 else '/app'
    results = run_all_fixes(app_root)
    print("\nFix results:", results)
    print()
    validation = validate_fixes(app_root)
