"""Fix theme flicker by adding blocking inline script to layout.tsx."""
import re

def fix_theme_flicker(layout_path: str) -> None:
    """Add a blocking inline script to read theme from localStorage before first paint.
    
    Inserts a <script> tag in <head> (or before <body> content) that reads
    localStorage theme and sets data-theme on <html> before React hydration.
    """
    with open(layout_path, 'r') as f:
        content = f.read()
    
    # Check if already has a theme script
    if 'dangerouslySetInnerHTML' in content and 'localStorage' in content:
        print("Theme flicker fix already applied.")
        return
    
    # The blocking script that runs before first paint
    theme_script = '''\n        <script\n          dangerouslySetInnerHTML={{\n            __html: `\n              (function() {\n                try {\n                  var theme = localStorage.getItem('theme');\n                  if (theme === 'dark' || theme === 'light') {\n                    document.documentElement.setAttribute('data-theme', theme);\n                  }\n                } catch(e) {}\n              })();\n            `,\n          }}\n        />'''
    
    # Insert the script inside <head> tag, or add <head> with the script
    if '<head>' in content:
        content = content.replace('<head>', '<head>' + theme_script)
    elif '<html' in content:
        # Add head section with the script between <html> and <body>
        content = content.replace(
            '<body>',
            '<head>' + theme_script + '\n        </head>\n        <body>'
        )
    else:
        print("WARNING: Could not find insertion point for theme script")
        return
    
    with open(layout_path, 'w') as f:
        f.write(content)
    print("Theme flicker fix applied.")


def fix_theme_provider_init(provider_path: str) -> None:
    """Fix ThemeProvider to initialize theme from localStorage/DOM synchronously.
    
    Replaces the useState('light') + useEffect pattern with a function initializer
    that reads from localStorage/DOM attribute set by the blocking script.
    """
    with open(provider_path, 'r') as f:
        content = f.read()
    
    # Check if already fixed
    if 'getInitialTheme' in content:
        print("ThemeProvider init already fixed.")
        return
    
    # Add the getInitialTheme function and update useState
    init_fn = '''\nfunction getInitialTheme(): Theme {\n  if (typeof window !== 'undefined') {\n    const saved = localStorage.getItem('theme') as Theme;\n    if (saved === 'dark' || saved === 'light') return saved;\n    const docTheme = document.documentElement.getAttribute('data-theme') as Theme;\n    if (docTheme === 'dark' || docTheme === 'light') return docTheme;\n  }\n  return 'light';\n}\n'''
    
    # Insert before ThemeProvider function
    content = content.replace(
        'export function ThemeProvider',
        init_fn + '\nexport function ThemeProvider'
    )
    
    # Replace useState('light') with useState(getInitialTheme)
    content = content.replace(
        "useState<Theme>('light')",
        'useState<Theme>(getInitialTheme)'
    )
    
    # Remove the useEffect that reads localStorage (no longer needed)
    import re
    content = re.sub(
        r"\s*useEffect\(\(\) => \{\s*const savedTheme = localStorage\.getItem\('theme'\) as Theme;\s*if \(savedTheme\) \{\s*setTheme\(savedTheme\);\s*\}\s*\}, \[\]\);\s*",
        '\n\n  ',
        content
    )
    
    with open(provider_path, 'w') as f:
        f.write(content)
    print("ThemeProvider init fix applied.")
