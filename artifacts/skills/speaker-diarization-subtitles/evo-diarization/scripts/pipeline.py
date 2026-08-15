"""End-to-end diarization pipeline entry point."""
import sys
import os

def detect_whisper_model():
    """Detect which whisper model is available in the local cache."""
    import glob
    cache_dir = os.path.join(os.path.expanduser('~'), '.cache', 'whisper')
    if os.path.isdir(cache_dir):
        models = glob.glob(os.path.join(cache_dir, '*.pt'))
        if models:
            # Pick the largest cached model (best quality)
            best = max(models, key=os.path.getsize)
            name = os.path.splitext(os.path.basename(best))[0]
            print(f"Detected cached whisper model: {name}")
            return name
    return 'base'  # whisper's own documented default

def run_pipeline(video_path, rttm_output, ass_output, report_output,
                 wav_path=None, whisper_model=None, clustering_threshold=None):
    """Run the full diarization + transcription pipeline.
    
    All paths are caller-supplied. No hardcoded artifact paths.
    """
    import tempfile
    if wav_path is None:
        wav_path = os.path.join(tempfile.gettempdir(), 'audio_16k.wav')
    
    if whisper_model is None:
        whisper_model = detect_whisper_model()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    
    from audio_extract import extract_audio, get_audio_duration
    from diarize import run_diarization
    from transcribe import transcribe_segments
    from output_gen import write_rttm, write_ass, write_report
    
    # Step 1: Extract audio
    print("=" * 60)
    print("STEP 1: Extracting audio from video")
    print("=" * 60)
    extract_audio(video_path, wav_path, sample_rate=16000)
    audio_duration = get_audio_duration(wav_path)
    print(f"Audio duration: {audio_duration:.2f}s")
    
    # Step 2: Diarization (threshold derived from data if not supplied)
    print("\n" + "=" * 60)
    print("STEP 2: Running diarization (VAD + Embeddings + Clustering)")
    print("=" * 60)
    diarization_segments = run_diarization(wav_path, threshold=clustering_threshold)
    
    if not diarization_segments:
        print("WARNING: No speech segments found. Creating minimal output.")
        diarization_segments = [(0.0, audio_duration, 'spk00')]
    
    print(f"\nDiarization results: {len(diarization_segments)} segments")
    for s, e, spk in diarization_segments:
        print(f"  [{s:.2f} - {e:.2f}] {spk}")
    
    # Step 3: Transcription
    print("\n" + "=" * 60)
    print("STEP 3: Transcribing speech segments")
    print("=" * 60)
    transcription = transcribe_segments(wav_path, diarization_segments, model_name=whisper_model)
    
    if not transcription:
        print("WARNING: No transcription results. Using segments without text.")
        transcription = [{'start': s, 'end': e, 'speaker': spk, 'text': '...'}
                         for s, e, spk in diarization_segments]
    
    # Step 4: Write outputs
    print("\n" + "=" * 60)
    print("STEP 4: Writing output files")
    print("=" * 60)
    write_rttm(diarization_segments, rttm_output)
    write_ass(transcription, ass_output)
    write_report(diarization_segments, audio_duration, report_output)
    
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    return {
        'diarization': diarization_segments,
        'transcription': transcription,
        'audio_duration': audio_duration
    }

def validate_outputs(rttm_path, ass_path, report_path):
    """Validate that all output files exist and are well-formed."""
    import json
    errors = []
    
    if not os.path.exists(rttm_path):
        errors.append(f"RTTM file missing: {rttm_path}")
    else:
        with open(rttm_path) as f:
            lines = f.readlines()
        if not lines:
            errors.append("RTTM file is empty")
        for i, line in enumerate(lines):
            parts = line.strip().split()
            if len(parts) != 10:
                errors.append(f"RTTM line {i+1}: expected 10 fields, got {len(parts)}")
            elif parts[0] != 'SPEAKER':
                errors.append(f"RTTM line {i+1}: must start with SPEAKER")
    
    if not os.path.exists(ass_path):
        errors.append(f"ASS file missing: {ass_path}")
    else:
        with open(ass_path) as f:
            content = f.read()
        if '[Events]' not in content:
            errors.append("ASS file missing [Events] section")
        if 'Dialogue:' not in content:
            errors.append("ASS file missing Dialogue lines")
        if 'SPEAKER_' not in content:
            errors.append("ASS file missing SPEAKER_ labels")
    
    if not os.path.exists(report_path):
        errors.append(f"Report file missing: {report_path}")
    else:
        with open(report_path) as f:
            report = json.load(f)
        required_keys = ['num_speakers_pred', 'total_speech_time_sec', 'audio_duration_sec',
                        'steps_completed', 'commands_used', 'libraries_used', 'tools_used', 'notes']
        for key in required_keys:
            if key not in report:
                errors.append(f"Report missing key: {key}")
    
    if errors:
        print("VALIDATION ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("All outputs validated successfully!")
        return True
