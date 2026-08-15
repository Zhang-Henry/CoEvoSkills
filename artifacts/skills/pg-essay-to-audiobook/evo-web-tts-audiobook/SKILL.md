---
name: evo-web-tts-audiobook
description: "Fetches web articles/essays, extracts main text content, converts to speech using edge-tts (local, no API key needed), and concatenates into a single MP3 audiobook. Use when you need to convert online text content to audio."
---

# Web Text to Audiobook Pipeline

This skill fetches web pages (e.g., Paul Graham essays), extracts the main text,
converts to speech using edge-tts (Microsoft Edge's free TTS service), and
concatenates chunks into a single MP3 audiobook using ffmpeg.

## Dependencies

- `edge-tts` (pip install)
- `requests` (pip install)
- `beautifulsoup4` (pip install)
- `pydub` (pip install, optional)
- `ffmpeg` (system)

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-web-tts-audiobook/scripts')
from utils import run_pipeline, validate_audio

essays = [
    {'url': 'http://paulgraham.com/ds.html', 'title': 'Do Things that Don\'t Scale'},
    {'url': 'http://paulgraham.com/foundermode.html', 'title': 'Founder Mode'},
]

output_path = '/root/audiobook.mp3'
run_pipeline(essays, output_path, voice='en-US-AriaNeural')

# Validate
duration = validate_audio(output_path, min_duration_seconds=60)
print(f"Validated: {duration:.0f}s")
```

## Key Functions

- `fetch_essay_text(url)` - Fetches and extracts text from a web page
- `clean_essay_text(raw_text, essay_title)` - Removes navigation chrome
- `chunk_text(text, max_chars=4000)` - Splits text at sentence boundaries
- `text_to_speech_chunks(chunks, output_dir, voice)` - Converts chunks to MP3 via edge-tts
- `concatenate_audio_files(file_list, output_path)` - Joins MP3s with ffmpeg
- `validate_audio(file_path, min_duration_seconds)` - Checks output duration
- `run_pipeline(essays, output_path, voice)` - End-to-end orchestration

## Notes

- edge-tts is free and requires no API key
- Text is chunked at ~4000 chars to stay within TTS limits
- ffmpeg concat demuxer is used for proper audio joining
- Validation checks file exists, is non-empty, and has nontrivial duration
