"""Fix layout shift from images without dimensions."""
import re

def fix_image_dimensions(component_path: str) -> None:
    """Add width and height attributes to <img> tags that lack them.
    
    For product images, uses reasonable defaults and ensures aspect-ratio is maintained.
    """
    with open(component_path, 'r') as f:
        content = f.read()
    
    # Check if img already has width/height
    # Look for <img tags and add width/height if missing
    if re.search(r'<img[^>]*\bwidth[=]', content):
        print(f"Image dimensions already present in {component_path}")
        return
    
    # Add width and height to img tags - for product cards, use standard dimensions
    # We add width/height HTML attributes for the browser to compute aspect ratio
    content = re.sub(
        r'(<img\b)([^>]*?)(/?>)',
        lambda m: add_dimensions_to_img(m),
        content
    )
    
    with open(component_path, 'w') as f:
        f.write(content)
    print(f"Image dimensions fix applied to {component_path}")

def add_dimensions_to_img(match):
    """Add width and height to an img tag match."""
    tag_start = match.group(1)
    attrs = match.group(2)
    tag_end = match.group(3)
    
    # Skip if already has width/height
    if 'width=' in attrs or 'height=' in attrs:
        return match.group(0)
    
    # Add width and height attributes
    return f'{tag_start}{attrs}\n        width={{400}}\n        height={{300}}\n        style={{{{ aspectRatio: "4/3", objectFit: "cover" }}}}\n      {tag_end}'
