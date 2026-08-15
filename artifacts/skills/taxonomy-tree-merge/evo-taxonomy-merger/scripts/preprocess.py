"""
Preprocessing module for taxonomy merging.
Handles: loading CSVs, removing prefix paths, text normalization, lemmatization.
"""
import pandas as pd
import re
import string
from nltk.stem import WordNetLemmatizer


def load_sources(data_dir):
    """Load all three source CSVs and tag with source name."""
    sources = {
        'amazon': f'{data_dir}/amazon_product_categories.csv',
        'facebook': f'{data_dir}/fb_product_categories.csv',
        'google': f'{data_dir}/google_shopping_product_categories.csv',
    }
    frames = []
    for src, path in sources.items():
        df = pd.read_csv(path)
        df = df[['category_path']].copy()
        # Strip quotes
        df['category_path'] = df['category_path'].str.strip().str.strip('"')
        df['source'] = src
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=['category_path'])
    combined = combined[combined['category_path'].str.strip() != ''].reset_index(drop=True)
    return combined


def remove_prefix_paths(df):
    """Remove prefix paths - keep only leaf paths per source.
    If 'A > B' and 'A > B > C' both exist for same source, remove 'A > B'.
    """
    result = []
    for src in df['source'].unique():
        src_df = df[df['source'] == src].copy()
        paths = set(src_df['category_path'].values)
        # A path is a prefix if any other path starts with it + ' > '
        leaf_paths = set()
        for p in paths:
            prefix = p + ' > '
            is_prefix = any(other.startswith(prefix) for other in paths if other != p)
            if not is_prefix:
                leaf_paths.add(p)
        result.append(src_df[src_df['category_path'].isin(leaf_paths)])
    return pd.concat(result, ignore_index=True)


def normalize_text(text):
    """Normalize a category name: lowercase, remove special chars, lemmatize."""
    if not isinstance(text, str):
        return ''
    # Lowercase
    text = text.lower().strip()
    # Replace & with 'and', / with space
    text = text.replace('&', ' and ').replace('/', ' ')
    # Remove apostrophes and possessives
    text = re.sub(r"'s\b", '', text)
    text = re.sub(r"'", '', text)
    # Remove parenthetical content
    text = re.sub(r'\([^)]*\)', '', text)
    # Replace hyphens with space
    text = text.replace('-', ' ')
    # Remove remaining punctuation except spaces
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


_lemmatizer = None
def get_lemmatizer():
    global _lemmatizer
    if _lemmatizer is None:
        _lemmatizer = WordNetLemmatizer()
    return _lemmatizer


def lemmatize_text(text):
    """Lemmatize each word in the text."""
    lem = get_lemmatizer()
    words = text.split()
    lemmatized = [lem.lemmatize(w) for w in words]
    return ' '.join(lemmatized)


def normalize_and_lemmatize(text):
    """Full normalization pipeline for a single text string."""
    return lemmatize_text(normalize_text(text))


def split_path_levels(path):
    """Split a category path into individual level names."""
    parts = [p.strip() for p in path.split(' > ')]
    return [p for p in parts if p]


def preprocess_dataframe(df):
    """Add normalized columns to the dataframe."""
    df = df.copy()
    # Split into levels
    levels = df['category_path'].apply(split_path_levels)
    df['depth'] = levels.apply(len)
    df['levels'] = levels
    # Normalized levels
    df['norm_levels'] = levels.apply(lambda ls: [normalize_and_lemmatize(l) for l in ls])
    # Full normalized path for embedding
    df['norm_path'] = df['norm_levels'].apply(lambda ls: ' > '.join(ls))
    return df
