---
name: evo-dubbing
description: "Multilingual video dubbing pipeline: TTS synthesis with Kokoro, temporal alignment to SRT windows, ITU-R BS.1770-4 loudness normalization, and video muxing. Use when tasked with dubbing a video from one language to another."
---

# Multilingual Dubbing Skill

This skill provides a complete pipeline for dubbing video from one language to
another using neural TTS, with broadcast-standard audio output.

## Capabilities

- Parse SRT subtitle files for timing windows and dialogue text
- Synthesize speech using Kokoro TTS with language-appropriate voices
- Two-step duration matching: Kokoro speed parameter + rate adjustment
- Normalize audio to ITU-R BS.1770-4 target (-23 LUFS per EBU R128)
- Mux dubbed audio into video container (configurable sample rate, mono)
- Generate structured JSON report with per-segment alignment metrics
- Validate output quality with UTMOS scoring

## Quick Start

The caller must supply paths to the input files and output directory.
All paths are runtime arguments with no defaults.

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-dubbing/scripts')
from pipeline import run_dubbing_pipeline
from validator import validate_dubbing_output

# Discover input paths from the task environment at runtime.
# These are illustrative variable names - adapt to actual task layout.
video_path = '<path-to-input-video>'         # e.g. /root/input.mp4
segments_srt = '<path-to-segments-srt>'       # defines speech time windows
source_text_srt = '<path-to-source-text-srt>' # original language dialogue
target_text_srt = '<path-to-target-text-srt>' # reference translation
target_lang_file = '<path-to-target-lang>'    # file containing ISO 639-1 code
out_dir = '<output-directory>'                # e.g. /outputs

# Run the full pipeline
report = run_dubbing_pipeline(
    video_path=video_path,
    segments_srt_path=segments_srt,
    source_text_srt_path=source_text_srt,
    target_text_srt_path=target_text_srt,
    target_language_path=target_lang_file,
    output_dir=out_dir,
    target_sr=48000,       # broadcast standard
    target_channels=1,     # mono
    target_lufs=-23.0      # EBU R128
)

# Validate all outputs
passed, issues = validate_dubbing_output(out_dir)
if passed:
    print("All validations passed!")
else:
    for issue in issues:
        print(f"ISSUE: {issue}")
```

## Pipeline Steps

1. **Parse inputs** - Read SRT files for timing windows, source text, and
   target text. Read target language code from file. Detect source language
   from text content.

2. **Configure TTS** - Map the target language ISO code to Kokoro's internal
   language code and select an appropriate voice.

3. **Synthesize & align** - For each segment:
   a. Synthesize at default speed to measure natural duration
   b. Compute optimal Kokoro speed parameter to approximate window duration
   c. Re-synthesize at optimal speed if significantly different
   d. Choose duration strategy (rate_adjust / pad_silence / trim)
   e. Apply rate adjustment to exactly match window duration
   f. Resample to target sample rate

4. **Normalize loudness** - Apply ITU-R BS.1770-4 loudness normalization
   to each segment, targeting -23 LUFS. Iteratively correct if needed.

5. **Quality check** - Score with UTMOS (target > 3.5 for broadcast quality).

6. **Assemble & mux** - Place all segments into a full-length audio track,
   mux into the video container (copy video stream, encode audio as AAC).

7. **Final verification** - Measure LUFS of the final video's audio track
   and re-normalize if needed.

8. **Report** - Generate JSON report with global and per-segment metrics.

## Key Technical Insights

### LUFS Measurement Parsing
The ffmpeg ebur128 filter outputs per-frame `I:` values that converge over
time, followed by a summary block. Always use the **last** `I: ... LUFS`
match from stderr, which is the integrated loudness summary.

### Two-Step Duration Matching
Rather than applying extreme rate adjustment post-synthesis, first adjust
Kokoro's `speed` parameter (clamped to 0.7-1.5 for quality) to get the
raw TTS duration close to the target, then apply fine rate adjustment
via resampling for the remaining difference.

### Kokoro TTS Configuration
- Native sample rate: 24000 Hz (must resample for broadcast)
- Language codes: single letter ('j'=Japanese, 'a'=English, 'z'=Chinese, etc.)
- Voice naming: `{lang}{gender}_{name}` (e.g., jf_alpha = Japanese female)
- Speed parameter: higher values = faster speech

## Scripts Reference

### scripts/utils.py
Small, independently testable utility functions:
- `parse_srt_file(path)` - Parse any SRT file into segment dicts
- `read_target_language(path)` - Read language code from file
- `detect_source_language(text)` - Heuristic language detection from text
- `get_kokoro_lang_code(lang)` - ISO 639-1 to Kokoro code mapping
- `get_kokoro_default_voice(lang)` - Default voice selection per language
- `discover_available_voices(repo_id, lang_prefix)` - Query available voices
- `synthesize_tts(text, lang_code, voice, speed)` - Generate TTS audio
- `resample_audio(audio, orig_sr, target_sr)` - Sample rate conversion
- `rate_adjust_audio(audio, sr, target_duration)` - Duration adjustment
- `ensure_mono(audio)` - Channel conversion
- `measure_lufs_from_file(path)` - LUFS measurement via ffmpeg
- `normalize_to_lufs(audio, sr, target_lufs)` - Loudness normalization
- `save_wav(audio, sr, path)` - WAV file output
- `get_video_duration(path)` - Duration query via ffprobe
- `create_full_audio_track(segments, duration, sr)` - Assemble audio track
- `mux_audio_video(video, audio, output, sr)` - Video muxing via ffmpeg
- `compute_utmos_score(audio, sr)` - Quality scoring
- `generate_report(...)` - JSON report generation
- `choose_duration_strategy(tts_dur, window_dur)` - Strategy selection
- `compute_optimal_tts_speed(raw_dur, window_dur)` - Speed optimization

### scripts/pipeline.py
End-to-end entry point: `run_dubbing_pipeline(...)` orchestrates all steps.
All paths are explicit parameters.

### scripts/validator.py
Validation: `validate_dubbing_output(output_dir, ...)` checks all outputs
against configurable tolerances.

## Requirements
- kokoro (TTS engine with ONNX backend)
- pysrt (SRT parsing)
- scipy (resampling)
- soundfile (WAV I/O)
- numpy, torch, torchaudio
- ffmpeg (system binary for audio measurement and video muxing)
