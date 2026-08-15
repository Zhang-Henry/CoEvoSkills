"""Fix layout shifts from async content that returns null while loading."""
import re

def fix_banner_placeholder(banner_path: str, testid: str, classes: str) -> None:
    """Replace 'return null' loading state with a placeholder div that reserves space.
    
    The placeholder has the same dimensions as the final banner.
    """
    with open(banner_path, 'r') as f:
        content = f.read()
    
    # Replace the 'if (!promo/text) return null' with a placeholder
    # Find the pattern: if (!variable) return null;
    null_pattern = r"if \(!\w+\) return null;"
    
    match = re.search(null_pattern, content)
    if not match:
        print(f"No null return pattern found in {banner_path}")
        return
    
    # Extract the variable name from the condition
    var_match = re.search(r"if \(!(\w+)\)", match.group(0))
    var_name = var_match.group(1)
    
    # Create placeholder that reserves the same space
    placeholder = f"""if (!{var_name}) return (
    <div
      data-testid="{testid}"
      className="{classes}"
      style={{{{ visibility: 'hidden' }}}}
    />
  );"""
    
    content = content[:match.start()] + placeholder + content[match.end():]
    
    with open(banner_path, 'w') as f:
        f.write(content)
    print(f"Banner placeholder fix applied to {banner_path}")


def fix_sidepane_placeholder(sidepane_path: str) -> None:
    """Replace null return in SidePane with a placeholder that reserves the sidebar width."""
    with open(sidepane_path, 'r') as f:
        content = f.read()
    
    null_pattern = r"if \(!data\) return null;"
    match = re.search(null_pattern, content)
    if not match:
        print("No null return pattern found in SidePane")
        return
    
    placeholder = """if (!data) return (
    <aside
      data-testid="side-pane"
      className="w-[220px] shrink-0 bg-[var(--card-bg)] p-5 border-r"
      style={{ borderColor: 'var(--border-color)' }}
    />
  );"""
    
    content = content[:match.start()] + placeholder + content[match.end():]
    
    with open(sidepane_path, 'w') as f:
        f.write(content)
    print("SidePane placeholder fix applied.")


def fix_resultsbar_placeholder(resultsbar_path: str) -> None:
    """Replace null return in ResultsBar with a placeholder."""
    with open(resultsbar_path, 'r') as f:
        content = f.read()
    
    # ResultsBar has: if (!visible || totalProducts === 0) return null;
    null_pattern = r"if \(!visible.*?\) return null;"
    match = re.search(null_pattern, content)
    if not match:
        print("No null return pattern found in ResultsBar")
        return
    
    placeholder = """if (!visible || totalProducts === 0) return (
    <div
      data-testid="results-bar"
      className="flex justify-between items-center bg-[var(--card-bg)] py-4 px-5 mb-5 rounded-lg text-sm"
      style={{ visibility: 'hidden' }}
    >
      &nbsp;
    </div>
  );"""
    
    content = content[:match.start()] + placeholder + content[match.end():]
    
    with open(resultsbar_path, 'w') as f:
        f.write(content)
    print("ResultsBar placeholder fix applied.")
