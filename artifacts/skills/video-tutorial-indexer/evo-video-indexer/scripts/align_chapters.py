import json
import re

def load_transcript(transcript_path):
    """Load transcript segments from JSON file."""
    with open(transcript_path) as f:
        return json.load(f)

def find_keyword_matches(segments, keywords):
    """Find segments that contain any of the given keywords (case-insensitive)."""
    matches = []
    for seg in segments:
        text_lower = seg["text"].lower()
        for kw in keywords:
            if kw.lower() in text_lower:
                matches.append(seg)
                break
    return matches

def align_chapters_to_transcript(chapter_titles, segments, first_time=0):
    """Align chapter titles to transcript segments using semantic matching.
    
    Returns list of {time, title} dicts with monotonically increasing timestamps.
    Uses keyword extraction from chapter titles and finds best matching segments.
    Enforces monotonicity constraint.
    """
    # Build keyword map for each chapter
    chapter_keywords = {}
    for i, title in enumerate(chapter_titles):
        words = re.findall(r'[a-zA-Z]+', title.lower())
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'to', 'in', 'of', 'it', 'we', 'do',
                       'if', 'you', 'how', 'll', 'get', 'all', 'with', 's', 'as', 'on',
                       'your', 'what', 'up', 'into', 're'}
        keywords = [w for w in words if w not in stop_words and len(w) > 1]
        chapter_keywords[i] = keywords
    
    # Score each segment for each chapter
    def score_segment(seg, keywords):
        text_lower = seg["text"].lower()
        score = 0
        for kw in keywords:
            if kw in text_lower:
                score += 1
        return score
    
    # Find best matching segment for each chapter, enforcing monotonicity
    results = []
    min_time = first_time
    
    for i, title in enumerate(chapter_titles):
        keywords = chapter_keywords[i]
        best_score = -1
        best_time = min_time
        
        # Determine max time (next chapter's approximate region)
        max_time = segments[-1]["end"] if i == len(chapter_titles) - 1 else None
        
        for seg in segments:
            if seg["start"] < min_time:
                continue
            if max_time and seg["start"] > max_time:
                break
            s = score_segment(seg, keywords)
            if s > best_score:
                best_score = s
                best_time = seg["start"]
        
        results.append({"time": int(best_time), "title": title})
        min_time = int(best_time) + 1
    
    # Ensure first chapter starts at 0
    if results:
        results[0]["time"] = first_time
    
    return results

def validate_chapters(chapters, duration, expected_count):
    """Validate chapter list meets all structural requirements."""
    errors = []
    if len(chapters) != expected_count:
        errors.append(f"Expected {expected_count} chapters, got {len(chapters)}")
    if chapters and chapters[0]["time"] != 0:
        errors.append(f"First chapter must start at 0, got {chapters[0]['time']}")
    for i in range(len(chapters) - 1):
        if chapters[i]["time"] >= chapters[i+1]["time"]:
            errors.append(f"Not monotonically increasing at {i}: {chapters[i]['time']} >= {chapters[i+1]['time']}")
    for c in chapters:
        if c["time"] < 0 or c["time"] > duration:
            errors.append(f"Timestamp {c['time']} out of range [0, {duration}]")
    return errors

def generate_index(chapters, title, duration, output_path):
    """Generate the final tutorial_index.json file."""
    output = {
        "video_info": {
            "title": title,
            "duration_seconds": duration
        },
        "chapters": chapters
    }
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    return output_path
