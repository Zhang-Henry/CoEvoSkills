---
name: evo-diarization
description: "Speaker diarization and transcription pipeline for video files. Extracts audio, performs VAD with SpeechBrain, speaker embedding extraction with ECAPA-TDNN, data-driven clustering, and Whisper ASR. Produces RTTM, ASS subtitle, and JSON report files."
---

# Speaker Diarization Pipeline

This skill provides a complete speaker diarization and transcription pipeline.

## Components
- `scripts/audio_extract.py` - FFmpeg-based audio extraction (video -> 16kHz mono WAV)
- `scripts/diarize.py` - SpeechBrain VAD + ECAPA-TDNN embeddings + silhouette-driven clustering
- `scripts/transcribe.py` - Whisper-based per-segment transcription
- `scripts/output_gen.py` - RTTM, ASS subtitle, and JSON report generators
- `scripts/pipeline.py` - End-to-end orchestration with validation

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-diarization/scripts')
from pipeline import run_pipeline, validate_outputs

# All paths are caller-supplied arguments
run_pipeline(
    video_path='<path-to-input-video>',
    rttm_output='<path-to-output-rttm>',
    ass_output='<path-to-output-ass>',
    report_output='<path-to-output-json>'
)
validate_outputs(
    '<path-to-output-rttm>',
    '<path-to-output-ass>',
    '<path-to-output-json>'
)
```

## Pipeline Steps
1. Extract 16kHz mono WAV from video using ffmpeg
2. Run SpeechBrain VAD (vad-crdnn-libriparty) with model defaults to detect speech regions
3. Extract ECAPA-TDNN speaker embeddings per segment
4. Cluster embeddings using agglomerative clustering with cosine distance;
   threshold is auto-derived from the runtime embedding distribution via silhouette analysis
5. Auto-detect cached Whisper model and transcribe each segment
6. Generate RTTM, ASS subtitles (with SPEAKER_XX labels), and JSON report

## Key Design Decisions
- **No hardcoded thresholds**: VAD uses model defaults; clustering threshold is derived
  from runtime silhouette analysis over the observed embedding distances
- **Whisper model auto-detection**: Scans cache directory and selects the best available model
- **All paths are caller-supplied**: No artifact paths are embedded in the code
- **Consistent speaker labels**: RTTM uses spkXX, ASS uses SPEAKER_XX, both derived from
  the same clustering output
