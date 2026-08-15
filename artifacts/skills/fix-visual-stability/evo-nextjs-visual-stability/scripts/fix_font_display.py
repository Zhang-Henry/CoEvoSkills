"""Fix FOIT by adding font-display: swap to @font-face rules."""
import re

def fix_font_display(css_path: str) -> None:
    """Add font-display: swap to all @font-face rules that lack it."""
    with open(css_path, 'r') as f:
        content = f.read()
    
    # Find @font-face blocks and add font-display: swap if missing
    def add_font_display(match):
        block = match.group(0)
        if 'font-display' in block:
            return block  # Already has it
        # Insert font-display: swap before the closing brace
        return block.rstrip('}').rstrip() + '\n  font-display: swap;\n}'
    
    content = re.sub(r'@font-face\s*\{[^}]*\}', add_font_display, content)
    
    with open(css_path, 'w') as f:
        f.write(content)
    print("Font display fix applied.")
