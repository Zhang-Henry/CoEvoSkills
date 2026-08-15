"""Fix ProductList to use skeleton loaders instead of text loading indicator."""
import re

def fix_product_list_skeleton(product_list_path: str, skeleton_count: int = 15) -> None:
    """Replace text loading indicator with skeleton components.
    
    The ProductSkeleton component already exists but isn't being used.
    Replace the 'Loading products...' text with an array of ProductSkeleton components.
    """
    with open(product_list_path, 'r') as f:
        content = f.read()
    
    # Find and replace the loading text with skeletons
    loading_pattern = r'<div data-testid="loading-text"[^>]*>[^<]*</div>'
    
    skeleton_jsx = f"""<>\n            {{Array.from({{ length: {skeleton_count} }}).map((_, i) => (\n              <ProductSkeleton key={{i}} />\n            ))}}\n          </>"""
    
    content = re.sub(loading_pattern, skeleton_jsx, content)
    
    with open(product_list_path, 'w') as f:
        f.write(content)
    print("ProductList skeleton fix applied.")
