# PowerPoint Editing Foundations

A `.pptx` file is an Office Open XML package whose slides, layouts, masters,
themes, media, relationships, and document properties are stored as connected
parts. Changes to one part can affect how other parts are interpreted.

Slide content is represented through shapes, transforms, text bodies,
paragraphs, and text runs. Position and size use document units rather than
screen pixels. Visible text appearance can be inherited from themes, masters,
layouts, paragraph styles, and run properties, so stored values and rendered
appearance are not always identical.

Text identification and visual layout are separate concerns. A text fragment's
role depends on the surrounding slide content, while fit and placement depend on
the actual slide geometry and typography. These properties should be inferred
from the supplied presentation rather than from fixed slide numbers, object
identifiers, coordinates, or content strings.
