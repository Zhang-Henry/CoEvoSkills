import fitz
import re
import subprocess
import os

def extract_text(pdf_path):
    """Extract full text from PDF, page by page."""
    doc = fitz.open(pdf_path)
    pages = []
    for i in range(doc.page_count):
        pages.append(doc[i].get_text())
    doc.close()
    return pages

def find_references_start_page(pages):
    """Find the page index where the References section starts."""
    for i, text in enumerate(pages):
        lines = text.split('\n')
        for line in lines:
            stripped = line.strip()
            # Common reference section headers
            if stripped.lower() in ['references', 'bibliography']:
                return i
            if re.match(r'^\d+\.?\s+references$', stripped.lower()):
                return i
            if re.match(r'^references$', stripped.lower()):
                return i
    return len(pages)  # If not found, treat all pages as before references

def redact_strings_from_pdf(input_path, output_path, redaction_list, refs_start_page=None):
    """
    Redact specific strings from a PDF using PyMuPDF's search_for + redact workflow.
    
    Args:
        input_path: Path to input PDF
        output_path: Path to save redacted PDF
        redaction_list: List of dicts with keys:
            - 'text': string to redact
            - 'pages': 'all', 'before_refs', or list of page indices (0-based)
        refs_start_page: Page index where references start (0-based)
    """
    doc = fitz.open(input_path)
    total_pages = doc.page_count
    
    if refs_start_page is None:
        pages_text = [doc[i].get_text() for i in range(total_pages)]
        refs_start_page = find_references_start_page(pages_text)
    
    for item in redaction_list:
        text = item['text']
        page_scope = item.get('pages', 'all')
        
        if page_scope == 'all':
            page_indices = range(total_pages)
        elif page_scope == 'before_refs':
            page_indices = range(min(refs_start_page, total_pages))
        elif isinstance(page_scope, list):
            page_indices = page_scope
        else:
            page_indices = range(total_pages)
        
        for pi in page_indices:
            if pi >= total_pages:
                continue
            page = doc[pi]
            # Search for the text
            rects = page.search_for(text)
            for rect in rects:
                page.add_redact_annot(rect, fill=(1, 1, 1))  # white fill
    
    # Apply all redactions
    for pi in range(total_pages):
        page = doc[pi]
        page.apply_redactions()
    
    # Clean metadata
    doc.set_metadata({
        'author': '',
        'title': doc.metadata.get('title', ''),
        'subject': '',
        'keywords': '',
        'creator': '',
        'producer': '',
    })
    
    doc.save(output_path)
    doc.close()

def verify_redaction(original_path, redacted_path, redaction_list):
    """Verify that redacted strings are no longer present in the output PDF."""
    doc = fitz.open(redacted_path)
    issues = []
    
    for item in redaction_list:
        text = item['text']
        for i in range(doc.page_count):
            page_text = doc[i].get_text()
            if text in page_text:
                issues.append(f"STILL PRESENT on page {i+1}: '{text}'")
    
    # Check page count preserved
    orig_doc = fitz.open(original_path)
    if orig_doc.page_count != doc.page_count:
        issues.append(f"Page count changed: {orig_doc.page_count} -> {doc.page_count}")
    orig_doc.close()
    
    # Check metadata cleaned
    meta = doc.metadata
    if meta.get('author', ''):
        issues.append(f"Author metadata not cleaned: {meta['author']}")
    
    doc.close()
    return issues

def run_anonymization(input_path, output_path, redaction_list, refs_start_page=None):
    """End-to-end anonymization: redact and verify."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    redact_strings_from_pdf(input_path, output_path, redaction_list, refs_start_page)
    issues = verify_redaction(input_path, output_path, redaction_list)
    return issues
