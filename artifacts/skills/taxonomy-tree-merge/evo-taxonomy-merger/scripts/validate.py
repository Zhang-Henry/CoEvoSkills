"""
Validation module - check all taxonomy constraints.
"""
import pandas as pd
import os
from collections import Counter, defaultdict


def validate_full_output(full_path, hier_path):
    """Validate both output files against all constraints.
    Returns (passed, issues_list).
    """
    issues = []
    
    if not os.path.exists(full_path):
        return False, [f"Missing file: {full_path}"]
    if not os.path.exists(hier_path):
        return False, [f"Missing file: {hier_path}"]
    
    full_df = pd.read_csv(full_path)
    hier_df = pd.read_csv(hier_path)
    
    # Check required columns
    full_required = ['source', 'category_path', 'depth', 
                     'unified_level_1', 'unified_level_2', 'unified_level_3',
                     'unified_level_4', 'unified_level_5']
    for col in full_required:
        if col not in full_df.columns:
            issues.append(f"Missing column in full CSV: {col}")
    
    hier_required = ['unified_level_1', 'unified_level_2', 'unified_level_3',
                     'unified_level_4', 'unified_level_5']
    for col in hier_required:
        if col not in hier_df.columns:
            issues.append(f"Missing column in hierarchy CSV: {col}")
    
    if issues:
        return False, issues
    
    # Check sources
    valid_sources = {'amazon', 'facebook', 'google'}
    actual_sources = set(full_df['source'].unique())
    if not actual_sources.issubset(valid_sources):
        issues.append(f"Invalid sources: {actual_sources - valid_sources}")
    if len(actual_sources) < 3:
        issues.append(f"Missing sources: {valid_sources - actual_sources}")
    
    # Check depth values
    if full_df['depth'].min() < 1 or full_df['depth'].max() > 5:
        issues.append(f"Depth out of range: min={full_df['depth'].min()}, max={full_df['depth'].max()}")
    
    # Rule 1: Top level should have 10-20 broad categories
    top_cats = full_df['unified_level_1'].dropna().unique()
    n_top = len(top_cats)
    if n_top < 10 or n_top > 20:
        issues.append(f"Rule 1: Top level has {n_top} categories (need 10-20)")
    
    # Check children per parent at each level (3-20)
    for level in range(2, 6):
        parent_col = f'unified_level_{level-1}'
        child_col = f'unified_level_{level}'
        # Group by parent path
        parent_cols = [f'unified_level_{i}' for i in range(1, level)]
        subset = full_df.dropna(subset=[child_col])
        if len(subset) == 0:
            continue
        groups = subset.groupby(parent_cols)[child_col].nunique()
        for parent, n_children in groups.items():
            if n_children < 3:
                issues.append(f"Rule 1: Level {level} parent '{parent}' has only {n_children} children (need 3+)")
            if n_children > 20:
                issues.append(f"Rule 1: Level {level} parent '{parent}' has {n_children} children (need <=20)")
    
    # Rule 2: Category names use ' | ' separator, max 5 words
    for level in range(1, 6):
        col = f'unified_level_{level}'
        for name in full_df[col].dropna().unique():
            words = name.split(' | ')
            if len(words) > 5:
                issues.append(f"Rule 2: '{name}' has more than 5 words")
    
    # Rule 3: No special characters that shouldn't be there
    # Names should be clean
    import re
    for level in range(1, 6):
        col = f'unified_level_{level}'
        for name in full_df[col].dropna().unique():
            if not name or name.strip() == '':
                issues.append(f"Rule 3: Empty name at level {level}")
            # Check for non-descriptive names
            if name.lower() in ('none', 'null', 'nan', 'cluster', 'empty', 'n/a'):
                issues.append(f"Rule 3: Non-descriptive name '{name}' at level {level}")
    
    # Rule 4: No name overlap between child and parent
    for level in range(2, 6):
        parent_col = f'unified_level_{level-1}'
        child_col = f'unified_level_{level}'
        subset = full_df.dropna(subset=[parent_col, child_col])
        for _, row in subset.drop_duplicates(subset=[parent_col, child_col]).iterrows():
            parent_name = str(row[parent_col]).lower()
            child_name = str(row[child_col]).lower()
            if parent_name == child_name:
                issues.append(f"Rule 4: Identical parent-child: '{parent_name}' at levels {level-1}/{level}")
    
    # Rule 5: Sibling overlap < 30%
    for level in range(1, 6):
        if level == 1:
            names = list(full_df[f'unified_level_{level}'].dropna().unique())
            overlap_issues = check_word_overlap(names, 0.3)
            for issue in overlap_issues:
                issues.append(f"Rule 5 (level {level}): {issue}")
        else:
            parent_cols = [f'unified_level_{i}' for i in range(1, level)]
            child_col = f'unified_level_{level}'
            subset = full_df.dropna(subset=[child_col])
            if len(subset) == 0:
                continue
            for parent_key, group in subset.groupby(parent_cols):
                siblings = list(group[child_col].unique())
                overlap_issues = check_word_overlap(siblings, 0.3)
                for issue in overlap_issues:
                    issues.append(f"Rule 5 (level {level}, parent {parent_key}): {issue}")
    
    # Rule 7: Even distribution across sources
    source_dist = full_df.groupby('unified_level_1')['source'].value_counts().unstack(fill_value=0)
    # Check that no top category is dominated by a single source
    if len(source_dist.columns) >= 3:
        for cat in source_dist.index:
            total = source_dist.loc[cat].sum()
            if total > 10:  # Only check for substantial categories
                max_frac = source_dist.loc[cat].max() / total
                if max_frac > 0.95:
                    issues.append(f"Rule 7: Category '{cat}' is {max_frac:.0%} from one source")
    
    # Structural integrity: if level N is non-null, levels 1..N-1 must be non-null
    for i in range(len(full_df)):
        last_non_null = 0
        for level in range(1, 6):
            val = full_df.iloc[i][f'unified_level_{level}']
            if pd.notna(val) and str(val).strip():
                if level > last_non_null + 1:
                    issues.append(f"Structural: Row {i} has gap - level {level} set but level {last_non_null+1} missing")
                    break
                last_non_null = level
    
    passed = len(issues) == 0
    return passed, issues


def check_word_overlap(names, threshold=0.3):
    """Check word overlap between sibling names."""
    issues = []
    for i in range(len(names)):
        words_i = set(str(names[i]).lower().replace(' | ', ' ').split())
        for j in range(i+1, len(names)):
            words_j = set(str(names[j]).lower().replace(' | ', ' ').split())
            if not words_i or not words_j:
                continue
            overlap = len(words_i & words_j) / min(len(words_i), len(words_j))
            if overlap > threshold:
                issues.append(f"'{names[i]}' vs '{names[j]}' overlap={overlap:.0%}")
    return issues


def print_validation_report(full_path, hier_path):
    """Print a validation report."""
    passed, issues = validate_full_output(full_path, hier_path)
    print(f"\nValidation {'PASSED' if passed else 'FAILED'}")
    if issues:
        print(f"Issues ({len(issues)}):")
        # Group and limit output
        shown = 0
        for issue in issues[:50]:
            print(f"  - {issue}")
            shown += 1
        if len(issues) > 50:
            print(f"  ... and {len(issues) - 50} more issues")
    else:
        print("All checks passed!")
    return passed


if __name__ == '__main__':
    print_validation_report('/root/output/unified_taxonomy_full.csv',
                           '/root/output/unified_taxonomy_hierarchy.csv')
