# Multilingual Video Dubbing Pipeline

This document covers the core engineering concepts behind building an automated multilingual video dubbing system: text-to-speech synthesis, audio-video alignment, broadcast loudness normalization, and professional audio format requirements.

## Text-to-Speech Synthesis for Dubbing

Modern neural TTS engines convert text into natural-sounding speech waveforms. In a dubbing context, the TTS system must produce speech in the **target language** that replaces the original spoken dialogue. Several considerations shape how the TTS stage interacts with the rest of the pipeline.

**Language-specific pipelines.** Different languages require different phonemizers, tokenizers, and sometimes entirely different TTS models. Japanese, for example, needs morphological analysis (tools like MeCab/fugashi with dictionaries such as UniDic) and kana-to-phoneme conversion before synthesis. Correctly configuring the language pipeline is essential for intelligible output, even when the text content is correct.

**Kokoro TTS.** Kokoro is an ONNX-based neural TTS engine that supports multiple languages through language-code-specific pipelines. Each language code (e.g., 'j' for Japanese, 'a' for American English) loads a distinct set of voice models and phonemizer rules. When initializing Kokoro, the language code parameter must match the target language. Kokoro produces raw waveform arrays at a native sample rate, which may differ from the final output requirements and must be resampled accordingly.

**Speech naturalness and MOS.** Mean Opinion Score (MOS) is the standard metric for evaluating perceived speech quality on a 1-to-5 scale. Automated MOS predictors like UTMOS (specifically the utmos22_strong variant from the SpeechMOS library) use neural networks trained on human judgments to estimate naturalness without requiring a listening panel. Scores above 3.5 are generally considered acceptable for broadcast-quality synthetic speech; scores below 3.0 indicate noticeable robotic or distorted artifacts. The UTMOS model expects a single-channel (mono) waveform tensor as input. If the synthesized audio is stereo or multi-channel, it must be reduced to mono before scoring.

## Temporal Alignment: Windows, Anchors, and Drift

The most technically demanding aspect of dubbing is placing the synthesized speech so that it aligns temporally with the original performance. This involves three distinct concepts.

**Speech windows.** Each subtitle segment defines a time window: a start time and an end time during which the original speaker is talking. The dubbed speech must be placed within this same window so that lip movements, scene cuts, and visual cues remain synchronized. The window is derived from the SRT subtitle file, which uses the format HH:MM:SS,mmm --> HH:MM:SS,mmm.

**Anchor alignment.** The start of the placed audio must match the start of the window with very high precision. In broadcast dubbing, even small offsets between where the audience expects speech to begin and where it actually begins are perceptible and distracting. Professional standards typically require sub-frame accuracy. The placed start time in the output report must correspond to the window start time from the subtitle timing.

**End drift and duration control.** Because different languages express the same idea with different numbers of syllables, the TTS output will almost never have exactly the same duration as the original speech window. Japanese text, for instance, often requires more syllables than English for the same semantic content, which can make the synthesized audio longer than the window. Conversely, some translations may be shorter. Three strategies exist for handling this mismatch:

- **Rate adjustment** (rate_adjust): Speed up or slow down the TTS audio so its duration matches the window. This is the most common approach because it preserves all speech content. However, extreme rate changes (beyond roughly 0.75x-1.5x) degrade naturalness and intelligibility.
- **Padding with silence** (pad_silence): If the TTS audio is shorter than the window, append silence to fill the remaining time. This avoids any rate distortion but may leave noticeable gaps.
- **Trimming** (trim): If the TTS audio is longer than the window, truncate it to fit. This risks cutting off the end of a sentence and should only be used when the overshoot is minimal.

The drift value in the output report captures how far the end of the placed audio deviates from the end of the window. Positive drift means the audio extends past the window; negative drift means it ends early. Keeping drift small is essential for maintaining the illusion of synchronized speech.

## Broadcast Loudness Standards: ITU-R BS.1770-4

Broadcast audio must conform to loudness standards to prevent jarring volume differences between programs, segments, or channels. The **ITU-R BS.1770-4** recommendation defines how loudness is measured and what target levels are acceptable.

**LUFS (Loudness Units relative to Full Scale).** LUFS is the measurement unit specified by ITU-R BS.1770. Unlike peak amplitude or RMS, LUFS applies frequency weighting (K-weighting) and temporal integration that models how humans perceive loudness. The measurement considers the entire program's audio, not just instantaneous peaks.

**The EBU R128 target.** The European Broadcasting Union's R128 recommendation, built on ITU-R BS.1770, specifies a target integrated loudness of **-23 LUFS** for broadcast content. This is the most widely adopted target globally for television, streaming, and podcast distribution. Content that is too loud (closer to 0 LUFS) sounds harsh and clips easily; content that is too quiet (below -30 LUFS) gets lost in background noise.

**Measuring LUFS with ffmpeg.** The ebur128 audio filter in ffmpeg implements the full ITU-R BS.1770-4 algorithm. When run with peak=true, it reports integrated loudness (I), loudness range (LRA), and true peak. The integrated loudness value (the line containing "I:" followed by a LUFS reading) is the primary metric for compliance. In a typical ffmpeg pipeline, the audio is sent through the ebur128 filter to a null output and the summary statistics are parsed from stderr.

**Loudness normalization techniques.** To bring audio to a target LUFS level, you can either:
1. Measure the current LUFS, compute the gain difference, and apply a linear gain adjustment.
2. Use ffmpeg's loudnorm filter, which performs two-pass loudness normalization (measure first, then adjust).

The key insight is that loudness normalization must be applied to the **final mixed audio** that will be embedded in the video, not just to the raw TTS output in isolation. If the TTS segment is normalized but then re-encoded or re-mixed during the video muxing step, the final loudness may shift.

## Professional Audio Format Requirements

Dubbed video intended for broadcast or professional distribution must adhere to specific audio encoding parameters.

**Sample rate: 48 kHz.** The professional video standard sample rate is 48,000 Hz (48 kHz), as opposed to the 44,100 Hz (44.1 kHz) common in music CDs. This is mandated by standards bodies for television and film. TTS engines may output at different native sample rates (e.g., 22,050 Hz or 24,000 Hz), so resampling to 48 kHz is almost always required. Resampling should use a high-quality algorithm to avoid aliasing artifacts.

**Channel layout: Mono.** For dubbed dialogue tracks, mono (single-channel) audio is standard. This ensures the speech is centered in the stereo or surround field and avoids phase issues. If the TTS engine produces stereo output, it must be downmixed to mono before embedding in the video.

**Container format and muxing.** The final deliverable is an MP4 container that combines the original video stream (untouched) with the new audio track. The muxing step must:
- Copy the video stream without re-encoding to preserve visual quality and avoid unnecessary computation.
- Encode the audio stream at the target sample rate and channel count.
- Ensure the audio track is properly aligned with the video timeline.

Re-encoding the video stream during muxing degrades quality and takes far longer than necessary. The audio stream, however, must be explicitly encoded (not copied) to apply the correct sample rate and channel configuration.

## The SRT Subtitle Format

SRT (SubRip Text) is the most common subtitle format. Each entry has a sequence number, a timecode range, and the text content:

Each entry consists of a sequence number (e.g., 1), a timecode line with start and end times separated by --> (e.g., 00:00:00,500 --> 00:00:02,100), and one or more lines of text content (e.g., "This is the first subtitle."). Entries are separated by blank lines.

**Parsing timecodes.** The timecode format is HH:MM:SS,mmm where mmm is milliseconds (note: comma separator, not period). Converting to seconds: hours * 3600 + minutes * 60 + seconds + milliseconds / 1000. Libraries like pysrt handle this parsing automatically and expose start/end times as objects with hours, minutes, seconds, and milliseconds attributes, or as ordinal values in milliseconds.

**Segments vs. subtitles.** In this dubbing context, there is a distinction between the segments file (which defines the time windows where speech must be placed) and the source/target text files (which contain the actual dialogue). Both use SRT format but serve different purposes. The segments file defines timing; the text files define content.

## Constructing the Dubbing Report

The dubbing report is a structured JSON document that serves as a manifest of the entire dubbing operation. It records both the global audio properties and per-segment details.

**Global fields** capture the overall configuration: source and target languages (as ISO 639-1 codes, e.g., "en", "ja", "fr"), the audio format (sample rate, channel count), video durations (original and new), and the measured loudness of the final output.

**Per-segment fields** record the alignment details for each speech segment: the original window timing, the actual placement timing, the source and target text, the TTS duration before any rate adjustment, the resulting drift, and which duration control strategy was applied. This level of detail enables quality auditing and debugging of alignment issues.

**Language codes.** The source_language and target_language fields must use standardized language codes. The target language code should be read directly from the provided input file rather than inferred or hard-coded, ensuring consistency between the report and the pipeline configuration.

## Important Technical Details

**Resampling is required before final muxing.** TTS engines rarely output at 48 kHz natively. If the raw TTS waveform is embedded without resampling, the audio will play at the wrong speed (if the player assumes 48 kHz) or the container metadata will report the wrong sample rate. The resampling step must occur before the audio is muxed into the final video container.

**Loudness measurement must be taken from the final video file's audio track.** The LUFS measurement must reflect the actual delivered audio, not intermediate TTS output. Re-encoding, resampling, and muxing can all shift the integrated loudness by a small but meaningful amount. If the TTS segment is normalized to exactly the target and then the muxing step applies any gain change, the final file will be non-compliant with the loudness standard.

**Drift is computed relative to the window boundaries.** Drift is the difference between where the speech actually ends and where the window says it should end. The standard calculation is placed_end minus window_end, where placed_end accounts for both the placement start offset and the actual audio duration. If the audio is placed starting at the window start, drift equals the difference between the placed audio end time and the window end time.

**The video stream should be copied without re-encoding during muxing.** Omitting the copy directive causes the video to be re-encoded with default settings, degrading quality and increasing processing time. The audio stream must be explicitly encoded (not copied) to apply the correct sample rate and channel configuration.

**Stereo TTS output must be explicitly converted to mono before encoding.** If the TTS produces stereo audio and it is declared as mono in the container, only one channel will play, or the audio will sound distorted. The conversion to mono (by averaging channels or selecting one) should happen as an explicit processing step rather than relying on the container to handle the mismatch.

**The reference translation should be used as the TTS input when available.** When a reference target-language script is provided, the TTS input should be derived from that reference rather than from an independent machine translation of the source text. The reference script is typically human-edited for naturalness, timing, and cultural adaptation. Using a different translation may produce speech with a very different duration, making alignment more difficult and potentially altering the intended meaning.
