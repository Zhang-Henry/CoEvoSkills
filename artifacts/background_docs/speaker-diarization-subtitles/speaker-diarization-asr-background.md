# Speaker Diarization and Automatic Speech Recognition for Subtitle Generation

This document covers the domain knowledge required to build a speaker diarization and transcription pipeline: extracting audio from video, segmenting speech by speaker, transcribing spoken content, and producing correctly formatted output files.

## The Speaker Diarization Problem

Speaker diarization answers the question "who spoke when?" Given an audio stream, the goal is to partition it into temporal segments and assign each segment a speaker label. This is distinct from speech recognition (which produces text) and voice activity detection (which only determines whether speech is present, not who is speaking).

A complete diarization system typically operates in stages:

1. **Voice Activity Detection (VAD)**: Identify regions of the audio that contain speech, discarding silence, music, and environmental noise. VAD is the foundation layer -- errors here propagate through the entire pipeline. A missed speech region means a speaker turn is lost entirely; a false positive means non-speech is forwarded for clustering.

2. **Speaker Embedding Extraction**: For each detected speech segment, compute a fixed-dimensional vector (embedding) that captures the vocal characteristics of the speaker. Common architectures include x-vectors, ECAPA-TDNN, and d-vectors. These embeddings should be invariant to what is said and sensitive only to who is saying it.

3. **Clustering**: Group embeddings by speaker identity. Since speaker labels are not known in advance, this is an unsupervised problem. Agglomerative hierarchical clustering and spectral clustering are common approaches. The number of speakers may or may not be known a priori -- when it is unknown, the clustering algorithm must also estimate it, which is a significant source of error.

4. **Resegmentation (optional)**: Refine segment boundaries after initial clustering. Viterbi-based resegmentation or iterative re-alignment can correct boundary drift and reduce short erroneous segments.

### Why Speaker Count Matters

Overestimating the number of speakers causes a single person's speech to be split across multiple labels (fragmentation). Underestimating causes distinct speakers to share a label (merger). Both errors inflate diarization error rates. Models like SpeechBrain's ECAPA-TDNN perform speaker verification (same/different decisions on pairs of embeddings), and the clustering threshold determines how aggressively segments are merged. Tuning this threshold is one of the most impactful decisions in the pipeline.

## RTTM File Format

The Rich Transcription Time Marked (RTTM) format is the standard interchange format for diarization output, defined by NIST for the Rich Transcription evaluations. Each line describes one speaker turn:

Each line follows a fixed ten-field format: the literal word `SPEAKER`, followed by a file identifier, a channel number, a start time in seconds, a duration in seconds, two placeholder fields marked `NA`, a speaker identifier, and two more placeholder fields marked `NA`. All fields are separated by whitespace.

Field definitions:
- **Type**: Always `SPEAKER` for diarization entries
- **file-id**: An identifier for the source recording (e.g., `input`)
- **channel**: Audio channel number (typically `1` for mono)
- **start-time**: Onset of the speaker turn in seconds from the beginning of the recording (floating point)
- **duration**: Length of the speaker turn in seconds (must be strictly positive)
- **speaker-id**: A label identifying the speaker (e.g., `spk00`, `spk01`)
- Fields marked `<NA>` are placeholders defined by the format specification

Key constraints: start times must be non-negative, durations must be strictly positive, and the end time of a turn is computed as `start-time + duration`. Speaker labels are arbitrary strings but must be internally consistent -- the same label must always refer to the same speaker within a file.

### Speaker Label Normalization

Different diarization tools produce speaker labels in various formats. Labels
within one output must be internally consistent and must follow any format
required by the task. When two annotations are compared, speaker identities are
generally permutation-invariant, so a declared identity-mapping method is safer
than assuming that matching digits or surface strings denote the same person.

## Diarization Evaluation Metrics

### Diarization Error Rate (DER)

DER is the primary metric for evaluating diarization quality, standardized by NIST. It decomposes into three additive error components:

**DER = (Missed Speech + False Alarm + Speaker Confusion) / Total Reference Speech Duration**

- **Missed Speech (Miss)**: Reference speech that the hypothesis fails to detect. This happens when the system's VAD misses speech regions or when segment boundaries are too tight.
- **False Alarm**: Hypothesis speech in regions where the reference has no speech. Caused by VAD false positives -- the system marks non-speech as speech.
- **Speaker Confusion**: Both reference and hypothesis agree that speech is present, but they disagree on the speaker identity. This is the clustering error component.

DER is expressed as a proportion of total reference speech time. It can exceed 1.0 (100%) when false alarms are large, though in practice values above 1.0 indicate a severely broken system.

### Forgiveness Collar

NIST evaluations use a **collar** -- a tolerance window around each reference segment boundary (both onset and offset). Within the collar, errors are not counted. This compensates for the inherent imprecision of human annotation at segment boundaries: different annotators will mark the start and end of a speaker turn at slightly different points, so penalizing the system for boundary variations within the collar would be unfair.

The collar is applied symmetrically. Larger collars produce lower DER scores for
the same output, and the collar affects only boundary regions. Use a collar only
when it is declared by the task or by the evaluation protocol being followed;
this background supplies no task-specific value.

### Jaccard Error Rate (JER)

JER provides a **per-speaker balanced** evaluation. While DER weights errors proportionally to their duration (so a speaker who talks for 90% of the recording dominates the score), JER computes an error rate for each speaker individually and then averages across speakers. This ensures that short-speaking participants are not ignored.

JER is particularly important in recordings with unbalanced speaker participation. A system that perfectly diarizes a dominant speaker but completely misses a brief interjection would have a low DER (small miss relative to total speech) but a high JER (the missed speaker contributes 100% error to their individual score).

### Per-Speaker Analysis

Decomposing DER by individual speaker reveals which speakers the system handles well and which it struggles with. Common patterns:

- **Brief speakers** are harder to cluster because there are fewer embedding samples, leading to higher per-speaker DER
- **Speakers with similar vocal characteristics** (e.g., same gender, similar age) cause more confusion errors
- **Overlapping speech** (two speakers talking simultaneously) is challenging for most diarization systems and inflates both miss and confusion

## Automatic Speech Recognition (ASR)

ASR converts spoken audio into text. Modern ASR systems (e.g., Whisper) use encoder-decoder transformer architectures trained on large multilingual datasets. Key considerations for a diarization-plus-transcription pipeline:

### Integrating ASR with Diarization

There are two common architectures:

1. **Transcribe-then-diarize**: Run ASR on the full audio to get a complete transcript with word-level timestamps, then use diarization results to assign speaker labels to each word or segment. This approach preserves ASR context (the model sees the full conversation) but requires accurate timestamp alignment between the ASR output and diarization segments.

2. **Diarize-then-transcribe**: First perform diarization to segment the audio by speaker, then transcribe each segment independently. This naturally produces speaker-labeled transcripts but may hurt ASR quality because the model loses conversational context at segment boundaries.

Both approaches require careful alignment of timestamps. Off-by-one errors, rounding differences, or inconsistent time bases between the diarization and ASR outputs cause speaker labels to be assigned to the wrong text.

ASR segmentation and speech/speaker segmentation are not interchangeable. Decoder segments are chosen to produce coherent text and may extend across silence, merge multiple turns, or include low-confidence text where a VAD would reject the interval. They are useful containers for transcript context, but they are not sufficient evidence for RTTM speech boundaries or speaker turns. In a transcribe-then-diarize design, keep independently derived speech and speaker regions as the temporal authority, then assign ASR words or text spans to those regions by overlap. Do not construct RTTM turns merely by copying ASR segment start and end times.

### Word Error Rate (WER)

WER measures transcription accuracy at the word level:

**WER = (Substitutions + Insertions + Deletions) / Number of Reference Words**

The error count is computed via the Levenshtein (edit) distance between the reference and hypothesis word sequences. Before comparison, both sequences are typically normalized: converted to lowercase, punctuation removed, and whitespace collapsed. WER can exceed 1.0 if there are more insertion errors than reference words.

### Character Error Rate (CER)

CER is the character-level analog of WER. It is more forgiving of minor spelling differences and morphological variations. CER normalization typically removes all whitespace and punctuation before computing edit distance. CER is especially useful for languages without clear word boundaries or when partial word recognition is valuable.

### Text Normalization for Error Rate Computation

Consistent normalization is essential for meaningful WER/CER scores. Both reference and hypothesis text must undergo identical preprocessing:

- Case folding (convert to lowercase)
- Punctuation removal (or standardization)
- Whitespace normalization
- For CER: removal of all non-alphanumeric characters

Failing to normalize identically will inflate error rates with spurious mismatches. For example, if the reference contains "Mr." and the hypothesis produces "Mister", normalization should handle this consistently, or the discrepancy will count as an error.

## Subtitle File Formats

### ASS (Advanced SubStation Alpha)

ASS is a rich subtitle format supporting styled text, positioning, and effects. It consists of three main sections:

1. **[Script Info]**: Metadata including title, script type version (`v4.00+`), resolution, and rendering options.

2. **[V4+ Styles]**: Style definitions controlling font, color, size, and positioning. Each style is a comma-separated field list following a `Format:` header.

3. **[Events]**: The actual subtitle entries. Each `Dialogue:` line follows the format declared in the `Format:` header, containing comma-separated fields: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, and Text.

ASS timestamps use the format `H:MM:SS.cc` (hours, minutes, seconds, centiseconds -- two decimal places, not three). This is a common source of bugs: SRT uses milliseconds (`HH:MM:SS,mmm`), so converting between formats requires adjusting decimal precision.

For diarized subtitles, the Text field can include a speaker label prefix (for
example, `SPEAKER_00: Hello there.`). Styling override tags in curly braces are
formatting metadata rather than spoken transcript text.

### SRT (SubRip Text)

SRT is a simpler format consisting of numbered blocks:

Each entry consists of a sequence number (e.g., `1`), a timestamp line with start and end times separated by `-->` (e.g., `00:00:06,510 --> 00:00:07,440`), and one or more lines of text (e.g., `SPEAKER_00: Excuse me.`).

Each block has a sequence number, a timestamp line with `-->` separator, and one or more text lines. Blocks are separated by blank lines. SRT timestamps use comma as the decimal separator (not a period), though many parsers accept both.

### Speaker Label Requirements in Subtitles

When subtitles are generated from diarized audio, each subtitle entry must include a speaker label prefix so that readers can distinguish who is speaking. The expected format is `SPEAKER_XX:` followed by the transcribed text. Common patterns include `SPEAKER_00`, `SPEAKER_01`, `SPK_00`, etc. The key requirement is consistency: the same speaker must always receive the same label throughout the file.

A well-formed diarized subtitle entry maps each diarization segment to a subtitle cue, using the speaker label from the RTTM and the transcribed text from ASR. The temporal boundaries of the subtitle should align with the diarization segment boundaries, not the ASR word boundaries, since the subtitle is a visual representation of "who said what when."

## Audio Extraction from Video

Before any speech processing can begin, audio must be extracted from the video container. FFmpeg is the standard tool for this operation. Key considerations:

- **Sample rate**: Most speech processing models expect 16kHz mono audio. Whisper specifically operates at 16kHz. Extracting at a different sample rate and then resampling can introduce artifacts.
- **Channel count**: Diarization and ASR models typically expect mono (single-channel) audio. Multi-channel audio should be downmixed.
- **Format**: WAV (uncompressed PCM) is the safest intermediate format -- it avoids codec-related artifacts and is universally supported by audio processing libraries.
- **Codec considerations**: Lossy compression (MP3, AAC) can degrade speech quality, particularly for quiet speakers or noisy segments. Extracting to lossless WAV preserves maximum information for downstream processing.

## Pipeline Integration and Output Consistency

A complete pipeline must ensure consistency across its three output artifacts:

1. **RTTM file**: Contains the temporal speaker segments (who spoke when)
2. **Subtitle file**: Contains the same temporal segments with transcribed text and speaker labels
3. **Report JSON**: Contains summary statistics derived from the RTTM

These outputs should be mutually consistent. The number of speakers reported in the JSON should match the number of unique speaker labels in the RTTM. The total speech time should equal the sum of all segment durations in the RTTM. The subtitle timestamps should correspond to the RTTM segment boundaries.

Inconsistencies between outputs typically indicate that the pipeline stages were run independently without proper data flow -- for example, running ASR and diarization separately and then attempting to merge results after the fact, without aligning their timestamp spaces.

## Practical Considerations

**Audio extraction should target the expected sample rate directly.** Whisper and most VAD/embedding models expect 16kHz mono WAV. Extracting at 44.1kHz or 48kHz and then feeding it directly to a model that internally resamples can work but adds unnecessary computation. Some audio processing libraries may silently truncate or misinterpret audio at unexpected sample rates, producing degraded embeddings and poor diarization quality. Extracting at the target sample rate from the start avoids these issues.

**Speaker label formats vary across tools and must be reconciled.** A
well-integrated pipeline keeps a single explicit mapping so that RTTM turns,
subtitle cues, and the report refer to each speaker consistently.

**Short speech segments require careful handling.** Brief utterances (under one second) are common in conversational speech -- acknowledgments, interjections, back-channel feedback. These are difficult for both VAD and clustering. The approach to minimum-duration filtering involves a tradeoff: aggressive filtering discards real speech turns and increases missed speech, while no filtering at all can produce many noise-triggered micro-segments that inflate false alarm rates. The threshold should be tuned to the characteristics of the recording.

**ASR and diarization timestamps must be aligned.** When transcription and diarization are performed independently, their timestamp spaces may not align perfectly. A word-level ASR timestamp that falls in a diarization gap (between two speaker turns) produces an unlabeled word. Rounding to different precisions (centiseconds vs. milliseconds) can shift a boundary enough to change which speaker label is assigned to a word. Using a consistent time base across all pipeline stages prevents these misalignment issues.

**Subtitle speaker attribution must follow the requested format.** When the task
requires a label prefix, include the mapped speaker identifier and separator in
each cue rather than writing transcript text alone.

**ASS and SRT use different timestamp precisions.** ASS uses centisecond precision (`H:MM:SS.cc` -- two decimal places) while SRT uses millisecond precision (`HH:MM:SS,mmm` -- three decimal places with a comma separator). Generating subtitle files with the wrong precision for the format produces malformed files that parsers may reject or misinterpret.

**Summary statistics must be derived from actual pipeline outputs.** The reported number of predicted speakers, total speech time, and audio duration must be computed from the actual RTTM and audio data, not estimated or hardcoded. If speaker clusters become empty after resegmentation, the effective speaker count may differ from the initial clustering result, and the report must reflect the final state.

**Choose acoustic settings by evidence from the recording, not by one score in
one run.** Compare plausible VAD, context-window, embedding, and clustering
configurations using speech coverage, segment-length distributions, cluster
occupancy, and stability under small perturbations. A configuration that only
maximizes a single internal clustering score can still fragment one voice or
merge distinct voices. Very short speech regions provide unreliable standalone
speaker embeddings; retain their VAD timing while assigning identity from a
context window or accumulated neighboring evidence. Keep VAD as the authority
for whether an interval contains speech, and reject ASR text that is repeated,
unsupported by a speech interval, or carried across silence. When more than one
installed ASR model is feasible, compare them with a recording-derived
consistency check rather than assuming the first available model is adequate.

## Implementation from the Actual Environment

Inspect installed executables, importable Python packages, model caches, audio metadata, and network restrictions before selecting components. Common building blocks include an audio decoder, a VAD, a speaker-embedding or diarization model, a clustering method, and an ASR model, but their exact versions, cache paths, and availability are environmental facts to discover—not background knowledge to copy.

A defensible pipeline generally extracts audio in the format expected by the selected models, detects speech, obtains speaker evidence, clusters or decodes speakers, transcribes speech, aligns timestamps, and writes internally consistent RTTM, subtitle, and summary artifacts. The ordering and interfaces depend on the installed tools. Choose minimum-duration filters, embedding model, clustering method, distance threshold, and ASR strategy from model documentation and legitimate observations rather than fixed benchmark hints.

For clustering, ensure the distance metric is compatible with the linkage method. Determine speaker count or stopping thresholds from the recording and any explicit task constraints. Record the selected components and parameters so the result is reproducible.

### Common Pitfalls

- **An all-duration fallback is not evidence.** Do not replace failed
  diarization with one segment covering the entire recording.  A one-speaker
  result can be valid when supported by the audio, while multiple-speaker audio
  requires distinct, evidence-based turns.
- **Audio format consistency is critical.** All pipeline stages must use the same audio source at the same sample rate. Re-encoding or re-sampling between stages introduces subtle timing misalignments that accumulate across segment boundaries.
- **Unit consistency across stages.** VAD outputs timestamps in seconds. Embedding extraction requires sample indices (seconds × sample_rate). Clustering operates on embedding vectors. RTTM requires seconds with floating-point precision. Verify that unit conversions are correct at every stage boundary.
- **Clustering threshold tuning.** If the output fragments one speaker, a more permissive merge policy may help; if it merges distinct speakers, a stricter one may help. Select values from the actual embedding distribution or legitimate validation, with no hidden range supplied here.
- **ASR timestamps are not VAD labels.** A fluent transcript segment can include leading or trailing non-speech and can span speaker changes. Diagnose speech coverage with acoustic evidence, and use ASR timestamps only for text alignment unless the selected model explicitly provides validated speech or speaker boundaries.
