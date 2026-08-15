"""Detect filler words and phrases from transcribed word list."""
import re

# Single-word fillers (case-insensitive matching)
SINGLE_FILLERS = {
    "um", "uh", "hum", "hmm", "mhm",
    "like",
    "yeah",
    "so",
    "basically",
    "well",
    "okay",
}

# Multi-word filler phrases (ordered by length descending for greedy matching)
MULTI_FILLERS = [
    ["you", "know"],
    ["i", "mean"],
    ["kind", "of"],
    ["i", "guess"],
]

def normalize_word(w):
    """Normalize a word for filler matching: lowercase, strip punctuation."""
    return re.sub(r'[^a-zA-Z]', '', w).lower()

def detect_fillers(words):
    """Detect filler words and phrases from word-level transcript.
    
    Args:
        words: List of dicts with 'word', 'start', 'end' keys
    
    Returns:
        List of dicts with 'word' (filler text), 'timestamp' (start time),
        'start', 'end' keys, sorted by timestamp
    """
    fillers = []
    used_indices = set()
    n = len(words)
    
    # First pass: detect multi-word phrases (greedy, longer first)
    for phrase_tokens in sorted(MULTI_FILLERS, key=len, reverse=True):
        phrase_len = len(phrase_tokens)
        for i in range(n - phrase_len + 1):
            if any(j in used_indices for j in range(i, i + phrase_len)):
                continue
            normalized = [normalize_word(words[j]["word"]) for j in range(i, i + phrase_len)]
            if normalized == phrase_tokens:
                filler_text = " ".join(phrase_tokens)
                fillers.append({
                    "word": filler_text,
                    "timestamp": round(words[i]["start"], 2),
                    "start": words[i]["start"],
                    "end": words[i + phrase_len - 1]["end"]
                })
                for j in range(i, i + phrase_len):
                    used_indices.add(j)
    
    # Second pass: detect single-word fillers
    for i in range(n):
        if i in used_indices:
            continue
        normalized = normalize_word(words[i]["word"])
        if normalized in SINGLE_FILLERS:
            fillers.append({
                "word": normalized,
                "timestamp": round(words[i]["start"], 2),
                "start": words[i]["start"],
                "end": words[i]["end"]
            })
            used_indices.add(i)
    
    # Sort by timestamp
    fillers.sort(key=lambda x: x["timestamp"])
    
    # Remove overlapping detections (keep earlier one)
    cleaned = []
    for f in fillers:
        if cleaned and f["start"] < cleaned[-1]["end"]:
            continue
        cleaned.append(f)
    
    return cleaned

def fillers_to_annotations(fillers):
    """Convert filler detections to the required annotation format.
    
    Returns:
        List of dicts with 'word' and 'timestamp' keys only
    """
    return [{"word": f["word"], "timestamp": f["timestamp"]} for f in fillers]
