# Safe OOXML template filling

A Word document is a ZIP package of related XML parts.  Visible text may be
split across multiple runs even when a placeholder appears contiguous to a
reader, so replacement logic must reason about logical text spans while
preserving the surrounding run and paragraph structure.

Template content may occur outside the main document body, including headers,
footers, tables, text boxes, and other related parts.  Conditional blocks
should be evaluated as structured regions: retain or remove their contents as
directed, and always remove control markers from the final document.

After substitution, reopen the package, parse all modified XML, confirm that
no unresolved placeholder or conditional marker remains, and verify that the
document still opens normally.  Preserve styles, relationships, and unrelated
content rather than rebuilding the file from scratch.

