# Safe Handling of Heterogeneous Documents

This note contains general file-processing knowledge. It does not classify a
current document or provide current filenames, labels, identifiers, folder
counts, document contents, or a file-to-folder mapping.

## Reading different formats

Different document formats require suitable readers. Text-based PDFs,
word-processing files, presentations, and scanned pages may expose their text
through different parsers; scanned material may require optical character
recognition. If an extraction attempt is empty or malformed, check another
representation before treating the file as unreadable.

## Preserving a collection

Maintain an inventory of supported source files while processing them. Preserve
the original filename and bytes unless conversion or renaming is requested,
and keep temporary extraction artifacts outside the destination collection.
After processing, compare source and destination inventories to detect omitted,
duplicated, renamed, or leftover source files.

The document itself remains the source of any semantic conclusion. This note
does not prescribe a classification rule, keyword list, category definition, or
decision for a particular collection.
