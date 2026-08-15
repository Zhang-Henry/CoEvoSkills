import json

def format_time_ass(seconds):
    """Format seconds to ASS timestamp format H:MM:SS.cc (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int(round((s - int(s)) * 100))
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"

def normalize_speaker_label(spk_id):
    """Convert spkXX to SPEAKER_XX format."""
    if spk_id.startswith('spk'):
        num = spk_id[3:]
        return f"SPEAKER_{num}"
    return spk_id

def write_rttm(diarization_segments, output_path, file_id='input'):
    """Write RTTM file from diarization segments."""
    with open(output_path, 'w') as f:
        for start, end, spk_id in diarization_segments:
            duration = end - start
            if duration <= 0:
                continue
            f.write(f"SPEAKER {file_id} 1 {start:.6f} {duration:.6f} <NA> <NA> {spk_id} <NA> <NA>\n")
    print(f"RTTM written to {output_path}")

def write_ass(transcription_results, output_path):
    """Write ASS subtitle file from transcription results."""
    header = """[Script Info]
Title: Diarization Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 640
PlayResY: 480

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(output_path, 'w') as f:
        f.write(header)
        for item in transcription_results:
            start_str = format_time_ass(item['start'])
            end_str = format_time_ass(item['end'])
            speaker_label = normalize_speaker_label(item['speaker'])
            text = item['text'].replace('\n', ' ')
            f.write(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{speaker_label}: {text}\n")
    print(f"ASS subtitles written to {output_path}")

def write_report(diarization_segments, audio_duration, output_path,
                 libraries_used=None, tools_used=None):
    """Write JSON report."""
    if not diarization_segments:
        num_speakers = 0
        total_speech = 0.0
    else:
        speakers = set(d[2] for d in diarization_segments)
        num_speakers = len(speakers)
        total_speech = sum(d[1] - d[0] for d in diarization_segments)
    
    report = {
        "num_speakers_pred": num_speakers,
        "total_speech_time_sec": round(total_speech, 1),
        "audio_duration_sec": round(audio_duration, 1),
        "steps_completed": [
            "audio_extraction",
            "voice_activity_detection",
            "speaker_embedding_extraction",
            "speaker_clustering",
            "transcription",
            "diarization",
            "subtitle_generation"
        ],
        "commands_used": ["python3", "ffmpeg"],
        "libraries_used": libraries_used or [
            "speechbrain",
            "whisper",
            "torch",
            "numpy",
            "scipy",
            "soundfile"
        ],
        "tools_used": tools_used or {
            "audio_extraction": "ffmpeg",
            "voice_activity_detection": "speechbrain/vad-crdnn-libriparty",
            "speaker_embedding": "speechbrain/spkrec-ecapa-voxceleb",
            "clustering": "scipy.cluster.hierarchy (agglomerative, cosine)",
            "diarization": "speechbrain + scipy clustering",
            "transcription": "openai-whisper (small)",
            "subtitle_generation": "custom python"
        },
        "notes": "Pipeline: ffmpeg audio extraction -> SpeechBrain VAD -> ECAPA-TDNN embeddings -> agglomerative clustering -> Whisper transcription -> RTTM/ASS/JSON output"
    }
    
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"Report written to {output_path}")
    return report
