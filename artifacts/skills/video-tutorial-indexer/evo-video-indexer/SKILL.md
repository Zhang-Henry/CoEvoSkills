---
name: evo-video-indexer
description: "Indexes tutorial videos by extracting audio, transcribing with Whisper, and aligning chapter titles to timestamps. Use for any task requiring video chapter timestamp extraction."
---

# Video Tutorial Indexer

Extracts chapter timestamps from tutorial videos using speech-to-text transcription and semantic alignment.

## Workflow

1. Extract audio from video with ffmpeg (16kHz mono WAV)
2. Transcribe with Whisper (base model for speed/accuracy balance)
3. Align chapter titles to transcript segments using keyword matching
4. Validate structural constraints (monotonicity, range, count)
5. Generate JSON output

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-video-indexer/scripts')
from transcribe import extract_audio, transcribe_audio, save_transcript
from align_chapters import align_chapters_to_transcript, validate_chapters, generate_index

# Step 1: Extract audio
audio_path = extract_audio('/root/tutorial_video.mp4', '/tmp/audio.wav')

# Step 2: Transcribe
segments = transcribe_audio(audio_path, model_name='base')
save_transcript(segments, '/root/transcript_segments.json')

# Step 3: Define chapter titles (from task)
chapter_titles = [
    "What we'll do",
    "How we'll get there",
    # ... all chapter titles ...
]

# Step 4: Align chapters to transcript
chapters = align_chapters_to_transcript(chapter_titles, segments, first_time=0)

# Step 5: Validate
errors = validate_chapters(chapters, duration=1382, expected_count=29)
if errors:
    print("Validation errors:", errors)

# Step 6: Generate output
generate_index(chapters, title='In-Depth Floor Plan Tutorial Part 1',
               duration=1382, output_path='/root/tutorial_index.json')
```

## Key Insights

- Whisper base model is sufficient for clear single-speaker English tutorials
- Chapter alignment requires semantic matching, not just keyword search
- The speaker rarely says exact chapter titles verbatim
- Enforce monotonicity globally across all chapters
- Very short chapters (Save, Break) may occupy only a few seconds
- "Break" and "Continue" pattern: break interrupts a topic, continuation resumes it
- Manual review of transcript is often needed for accurate alignment
- Timestamps should be integers (seconds) for clean output
