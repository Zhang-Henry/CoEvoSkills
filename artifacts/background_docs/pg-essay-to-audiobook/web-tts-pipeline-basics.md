# Web-text to audiobook pipelines

An audiobook pipeline separates source retrieval, main-content extraction,
text normalization, speech synthesis, and audio assembly.  Preserve paragraph
order and remove navigation, scripts, repeated headers, and unrelated page
chrome without rewriting the author's prose.

Long text should be divided at semantic boundaries within the selected TTS
engine's request limit.  Keep chunk order explicit, retry transient failures,
and provide a local speech-engine fallback when a remote service is unavailable.
Audio chunks should be decoded and concatenated with a media-aware tool rather
than joined as arbitrary bytes.

Before delivery, decode the final file, check that it has nontrivial duration,
confirm that every requested source contributed content in the correct order,
and retain enough provenance to distinguish retrieved prose from generated
audio metadata.

