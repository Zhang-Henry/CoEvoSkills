"""End-to-end multilingual dubbing pipeline.

Fully parameterized - all paths and settings are passed as arguments.
No hardcoded paths or instance-specific values.
"""
import os
import sys
import warnings
warnings.filterwarnings('ignore')

import numpy as np

from utils import (
    parse_srt_file, read_target_language, detect_source_language,
    get_kokoro_lang_code, get_kokoro_default_voice, synthesize_tts,
    resample_audio, rate_adjust_audio, ensure_mono,
    normalize_to_lufs, save_wav, get_video_duration, create_full_audio_track,
    mux_audio_video, measure_lufs_from_file, generate_report,
    compute_utmos_score, choose_duration_strategy, compute_optimal_tts_speed
)


def run_dubbing_pipeline(
    video_path,
    segments_srt_path,
    source_text_srt_path,
    target_text_srt_path,
    target_language_path,
    output_dir,
    target_sr=48000,
    target_channels=1,
    target_lufs=-23.0
):
    """Run the complete multilingual dubbing pipeline.
    
    Args:
        video_path: Path to input video file
        segments_srt_path: Path to SRT file defining speech time windows
        source_text_srt_path: Path to SRT file with source language text
        target_text_srt_path: Path to SRT file with target language text
        target_language_path: Path to file containing target language ISO code
        output_dir: Directory for all outputs
        target_sr: Output sample rate in Hz (default 48000 per broadcast standard)
        target_channels: Output channel count (default 1 for mono)
        target_lufs: Target integrated loudness in LUFS (default -23.0 per EBU R128)
    
    Returns:
        dict: The generated report
    """
    # --- Phase 1: Parse all inputs ---
    print("[1/8] Parsing input files...")
    segments = parse_srt_file(segments_srt_path)
    source_texts = parse_srt_file(source_text_srt_path)
    target_texts = parse_srt_file(target_text_srt_path)
    target_lang = read_target_language(target_language_path)
    
    # Detect source language from the actual text content
    all_source_text = ' '.join([s['text'] for s in source_texts])
    source_lang = detect_source_language(all_source_text)
    
    print(f"  Source language: {source_lang}")
    print(f"  Target language: {target_lang}")
    print(f"  Number of segments: {len(segments)}")
    
    # Get video properties
    orig_duration = get_video_duration(video_path)
    print(f"  Video duration: {orig_duration:.3f}s")
    
    # --- Phase 2: Configure TTS ---
    kokoro_lang = get_kokoro_lang_code(target_lang)
    kokoro_voice = get_kokoro_default_voice(target_lang)
    print(f"  TTS config: lang_code={kokoro_lang}, voice={kokoro_voice}")
    
    # --- Phase 3: Process each segment ---
    tts_segments_dir = os.path.join(output_dir, 'tts_segments')
    os.makedirs(tts_segments_dir, exist_ok=True)
    
    segments_audio = []
    speech_segments_report = []
    
    for i, seg in enumerate(segments):
        print(f"\n[2/8] Processing segment {i}/{len(segments)-1}...")
        window_start = seg['start_sec']
        window_end = seg['end_sec']
        window_duration = window_end - window_start
        
        # Match segment to source/target text by index
        source_text = source_texts[i]['text'] if i < len(source_texts) else ''
        target_text = target_texts[i]['text'] if i < len(target_texts) else ''
        
        print(f"  Window: {window_start:.3f}s - {window_end:.3f}s ({window_duration:.3f}s)")
        
        # --- Synthesize at default speed to measure natural duration ---
        print(f"[3/8] Synthesizing TTS...")
        tts_audio_raw, tts_sr = synthesize_tts(target_text, kokoro_lang, kokoro_voice, speed=1.0)
        tts_audio_raw = ensure_mono(tts_audio_raw)
        raw_duration = len(tts_audio_raw) / tts_sr
        print(f"  Raw TTS duration: {raw_duration:.3f}s")
        
        # --- Compute optimal speed and re-synthesize if needed ---
        optimal_speed = compute_optimal_tts_speed(raw_duration, window_duration)
        
        if abs(optimal_speed - 1.0) > 0.05:
            print(f"  Re-synthesizing at speed {optimal_speed:.3f}...")
            tts_audio, tts_sr = synthesize_tts(target_text, kokoro_lang, kokoro_voice, speed=optimal_speed)
            tts_audio = ensure_mono(tts_audio)
        else:
            tts_audio = tts_audio_raw
        
        tts_duration = len(tts_audio) / tts_sr
        print(f"  TTS duration after speed adj: {tts_duration:.3f}s")
        
        # --- Choose and apply duration control strategy ---
        strategy = choose_duration_strategy(tts_duration, window_duration)
        print(f"  Duration strategy: {strategy}")
        
        if strategy == 'rate_adjust':
            adjusted_audio = rate_adjust_audio(tts_audio, tts_sr, window_duration)
        elif strategy == 'pad_silence':
            adjusted_audio = tts_audio  # Will be padded by placement in full track
        elif strategy == 'trim':
            target_samples = int(window_duration * tts_sr)
            adjusted_audio = tts_audio[:target_samples]
        else:
            adjusted_audio = tts_audio
        
        # --- Resample to target sample rate ---
        print(f"[4/8] Resampling to {target_sr}Hz...")
        resampled_audio = resample_audio(adjusted_audio, tts_sr, target_sr)
        resampled_audio = ensure_mono(resampled_audio)
        
        actual_duration = len(resampled_audio) / target_sr
        placed_start = window_start
        placed_end = placed_start + actual_duration
        drift = placed_end - window_end
        
        print(f"  Actual duration: {actual_duration:.3f}s")
        print(f"  Drift: {drift:.4f}s")
        
        # --- Normalize to target LUFS ---
        print(f"[5/8] Normalizing to {target_lufs} LUFS...")
        normalized_audio = normalize_to_lufs(resampled_audio, target_sr, target_lufs)
        
        # Save segment WAV
        seg_path = os.path.join(tts_segments_dir, f'seg_{i}.wav')
        save_wav(normalized_audio, target_sr, seg_path)
        
        # Verify and iteratively correct LUFS
        seg_lufs = measure_lufs_from_file(seg_path)
        print(f"  Segment LUFS: {seg_lufs}")
        
        if seg_lufs is not None and abs(seg_lufs - target_lufs) > 1.0:
            for attempt in range(3):
                gain_db = target_lufs - seg_lufs
                gain_linear = 10 ** (gain_db / 20.0)
                normalized_audio = normalized_audio * gain_linear
                peak = np.max(np.abs(normalized_audio))
                if peak > 0.99:
                    normalized_audio = normalized_audio * (0.99 / peak)
                save_wav(normalized_audio, target_sr, seg_path)
                seg_lufs = measure_lufs_from_file(seg_path)
                print(f"  Re-norm attempt {attempt+1}: LUFS = {seg_lufs}")
                if seg_lufs is not None and abs(seg_lufs - target_lufs) <= 1.0:
                    break
        
        # --- Quality check ---
        print(f"[6/8] Checking audio quality...")
        try:
            utmos_score = compute_utmos_score(normalized_audio, target_sr)
            print(f"  UTMOS score: {utmos_score:.2f}")
        except Exception as e:
            print(f"  UTMOS scoring unavailable: {e}")
        
        segments_audio.append({
            'start_sec': placed_start,
            'audio': normalized_audio
        })
        
        speech_segments_report.append({
            'window_start_sec': round(window_start, 3),
            'window_end_sec': round(window_end, 3),
            'placed_start_sec': round(placed_start, 3),
            'placed_end_sec': round(placed_end, 3),
            'source_text': source_text,
            'target_text': target_text,
            'window_duration_sec': round(window_duration, 3),
            'tts_duration_sec': round(raw_duration, 3),
            'drift_sec': round(drift, 3),
            'duration_control': strategy
        })
    
    # --- Phase 4: Create full audio track ---
    print(f"\n[7/8] Creating full audio track...")
    full_audio = create_full_audio_track(segments_audio, orig_duration, target_sr)
    
    # Save temporary full audio
    full_audio_path = os.path.join(output_dir, 'full_audio.wav')
    save_wav(full_audio, target_sr, full_audio_path)
    
    # --- Phase 5: Mux into video ---
    print(f"[8/8] Muxing audio into video...")
    dubbed_path = os.path.join(output_dir, 'dubbed.mp4')
    mux_audio_video(video_path, full_audio_path, dubbed_path, target_sr)
    
    # Measure and correct final LUFS
    final_lufs = measure_lufs_from_file(dubbed_path)
    print(f"  Final LUFS: {final_lufs}")
    
    if final_lufs is not None and abs(final_lufs - target_lufs) > 1.0:
        print(f"  Re-normalizing final audio...")
        gain_db = target_lufs - final_lufs
        gain_linear = 10 ** (gain_db / 20.0)
        full_audio = full_audio * gain_linear
        peak = np.max(np.abs(full_audio))
        if peak > 0.99:
            full_audio = full_audio * (0.99 / peak)
        save_wav(full_audio, target_sr, full_audio_path)
        mux_audio_video(video_path, full_audio_path, dubbed_path, target_sr)
        final_lufs = measure_lufs_from_file(dubbed_path)
        print(f"  Final LUFS after correction: {final_lufs}")
    
    new_duration = get_video_duration(dubbed_path)
    
    # --- Phase 6: Generate report ---
    report_path = os.path.join(output_dir, 'report.json')
    report = generate_report(
        source_lang=source_lang,
        target_lang=target_lang,
        sr=target_sr,
        channels=target_channels,
        orig_duration=orig_duration,
        new_duration=new_duration,
        measured_lufs=final_lufs,
        speech_segments=speech_segments_report,
        output_path=report_path
    )
    
    print(f"\nDubbing complete!")
    print(f"  Outputs in: {output_dir}")
    
    # Cleanup temporary file
    if os.path.exists(full_audio_path):
        os.unlink(full_audio_path)
    
    return report
