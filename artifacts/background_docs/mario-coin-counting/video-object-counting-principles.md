# Video object counting with templates

Codec key frames are self-contained frames selected by the video's encoding
structure. When extracting a subset, preserve presentation order and avoid
frame-rate conversion that duplicates or drops selected frames. Confirm the
result from the media metadata and the files that were actually written.

Template matching compares a reference patch with every compatible location in
a scene. Convert the scene and template through the same image pipeline before
comparison. A score map contains clusters of nearby responses around one
object, so count local peaks or apply non-maximum suppression rather than
counting every above-threshold pixel.

No correlation threshold or suppression distance is universal. Estimate them
from the current template and frames, compare positive peaks with background
responses, and check that small parameter changes do not cause unstable counts.
For visually repetitive backgrounds, confirm candidates with independent
evidence such as color, silhouette, or edge agreement.

Keep frame identity and timeline order attached to every count. Before
delivery, reopen the written images and tabular output to confirm colorspace,
ordering, column types, and one record per selected frame.
