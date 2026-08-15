# General Background: Locating Disfluencies in Video

Finding hesitation and discourse markers in a video combines automatic speech
recognition (ASR), linguistic classification, timestamp alignment, and media
editing.  These stages should remain separate: a recognized word is evidence,
not yet a decision that the word functions as a filler in context.

## Recognition and timing

ASR systems often expose segment timestamps, while editing individual words
requires word-level timing.  Word boundaries are estimates because speech is
continuous and adjacent sounds overlap.  Low-volume hesitations may also be
omitted or normalized by a recognizer more often than ordinary content words.
Model choice, decoding settings, audio quality, and language all affect this
behavior.

For CPU-bound processing, benchmark the recognition backend and model on a
short representative excerpt before transcribing the full recording.  Prefer a
CPU-appropriate or quantized implementation when available, cache completed
transcripts, and avoid rerunning full inference merely to change downstream
classification or editing logic.  Chunking can bound memory and retry cost, but
word times must be translated back to the source timeline consistently.

Keep the recognizer's original token, start time, and end time together.  If a
system produces only coarse segments, assigning the same segment start to every
word does not create genuine word alignment.  A second alignment method or a
recognizer that supports word timing is usually needed.

## Classifying disfluencies

Some hesitation sounds are primarily non-lexical, but many discourse markers
are also ordinary content words.  Classification can therefore use neighboring
words, pauses, repetition, syntax, and prosody in addition to a vocabulary.
Normalization of case and attached punctuation helps lexical matching without
altering the stored raw transcript.

Multi-word expressions need phrase-level matching over adjacent tokens.  Their
time interval normally spans from the first token's start to the last token's
end.  Detectors should avoid emitting both an expression and overlapping
partial detections unless the output contract calls for both.  Sorting by time
and using an explicit overlap policy makes results deterministic.

## Producing media clips

Media containers use presentation timestamps and encoded frames rather than
independent clips for each spoken word.  Stream-copy cuts commonly begin at a
nearby keyframe, so short, precise excerpts may require decoding and
re-encoding.  Clip bounds should be clamped to the source duration, kept in
chronological order, and handled consistently when intervals overlap.

After concatenation, decode the result and check that it contains the expected
audio/video streams, has finite nonnegative duration, and corresponds to the
reported intervals.  Intermediate transcripts and interval decisions are
useful for diagnosing whether an error came from recognition, classification,
alignment, or editing.  Do not invent detections when the audio evidence is
uncertain.
