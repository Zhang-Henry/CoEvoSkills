import re
from collections import Counter
from nltk.stem import WordNetLemmatizer

STOPWORDS = {'and', 'or', 'the', 'a', 'an', 'of', 'for', 'in', 'on', 'to', 'with',
             'by', 'at', 'from', 'is', 'it', 'its', 'that', 'this', 'other', 'all',
             'not', 'no', 'but', 'so', 'if', 'as', 'be', 'do', 'has', 'have', 'had',
             'was', 'were', 'are', 'been', 'being', 'will', 'would', 'could', 'should',
             'may', 'might', 'can', 'shall', 'product', 'item', 'type', 'category',
             'general', 'specific', 'various', 'assorted', 'miscellaneous', 'unspecified'}

def extract_representative_words(norm_levels_list, parent_words=None, max_words=5, min_coverage=0.05):
    if parent_words is None: parent_words = set()
    word_counts = Counter()
    word_doc_freq = Counter()
    n_items = len(norm_levels_list)
    for norm_levels in norm_levels_list:
        item_words = set()
        for level_idx, level_text in enumerate(norm_levels):
            words = level_text.split()
            weight = max(1, 4 - level_idx)
            for w in words:
                if w not in STOPWORDS and len(w) > 1 and w not in parent_words:
                    word_counts[w] += weight
                    item_words.add(w)
        for w in item_words:
            word_doc_freq[w] += 1
    if not word_counts:
        for norm_levels in norm_levels_list:
            for level_text in norm_levels:
                for w in level_text.split():
                    if len(w) > 1:
                        word_counts[w] += 1
                        word_doc_freq[w] += 1
    if not word_counts: return 'miscellaneous'
    min_count = max(1, int(n_items * min_coverage))
    candidates = [(w, c) for w, c in word_counts.most_common(50)
                  if word_doc_freq[w] >= min_count]
    if not candidates: candidates = word_counts.most_common(max_words)
    selected = []
    for w, c in candidates:
        if len(selected) >= max_words: break
        if not any(w in s or s in w for s in selected):
            selected.append(w)
    if not selected: selected = [candidates[0][0]] if candidates else ['general']
    return ' | '.join(w.title() for w in selected)

def compute_coverage(name, norm_levels_list):
    name_tokens = set()
    lem = WordNetLemmatizer()
    for part in name.lower().replace(' | ', ' ').split():
        name_tokens.add(lem.lemmatize(part.lower()))
    if not name_tokens: return 0.0
    covered = 0
    for norm_levels in norm_levels_list:
        all_words = set()
        for lvl in norm_levels: all_words.update(lvl.split())
        if name_tokens & all_words: covered += 1
    return covered / max(1, len(norm_levels_list))

def ensure_coverage(name, norm_levels_list, parent_words, target_coverage=0.7, max_words=5):
    coverage = compute_coverage(name, norm_levels_list)
    if coverage >= target_coverage: return name, coverage
    name_tokens = set(name.lower().replace(' | ', ' ').split())
    word_doc_freq = Counter()
    for norm_levels in norm_levels_list:
        item_words = set()
        for lvl in norm_levels: item_words.update(lvl.split())
        for w in item_words:
            if w not in STOPWORDS and len(w) > 1 and w not in parent_words and w not in name_tokens:
                word_doc_freq[w] += 1
    current_words = name.split(' | ')
    for w, freq in word_doc_freq.most_common(20):
        if len(current_words) >= max_words: break
        current_words.append(w.title())
        new_name = ' | '.join(current_words)
        new_cov = compute_coverage(new_name, norm_levels_list)
        if new_cov >= target_coverage: return new_name, new_cov
    return ' | '.join(current_words[:max_words]), compute_coverage(' | '.join(current_words[:max_words]), norm_levels_list)

def check_sibling_overlap(names):
    issues = []
    for i in range(len(names)):
        words_i = set(names[i].lower().replace(' | ', ' ').split())
        for j in range(i+1, len(names)):
            words_j = set(names[j].lower().replace(' | ', ' ').split())
            if not words_i or not words_j: continue
            overlap = len(words_i & words_j) / min(len(words_i), len(words_j))
            if overlap > 0.3: issues.append((names[i], names[j], overlap))
    return issues
