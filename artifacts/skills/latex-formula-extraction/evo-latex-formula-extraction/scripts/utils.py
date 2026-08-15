"""
Utility functions for extracting, cleaning, and fixing LaTeX display-mode formulas from PDFs.
"""
import re
import os
import subprocess
import json


def extract_formulas_with_marker(pdf_path, output_dir):
    """
    Use marker-pdf to convert a PDF to markdown, then extract display-mode formulas.
    Returns a list of raw formula strings (between $$ delimiters).
    """
    # Run marker_single
    cmd = f"marker_single '{pdf_path}' --output_dir '{output_dir}'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    
    # Find the markdown file
    md_files = []
    for root, dirs, files in os.walk(output_dir):
        for f in files:
            if f.endswith('.md'):
                md_files.append(os.path.join(root, f))
    
    if not md_files:
        raise FileNotFoundError(f"No markdown files found in {output_dir}")
    
    with open(md_files[0], 'r') as f:
        content = f.read()
    
    # Extract formulas between $$ delimiters
    # Handle both single-line and multi-line $$...$$ blocks
    formulas = re.findall(r'\$\$\s*\n?(.*?)\n?\s*\$\$', content, re.DOTALL)
    
    return [f.strip() for f in formulas if f.strip()]


def extract_formulas_with_texify(pdf_path, equation_bboxes=None):
    """
    Use texify on cropped equation regions from PDF pages.
    equation_bboxes: list of (page_idx, (x1, y1, x2, y2)) tuples
    Returns list of raw formula strings.
    """
    import pypdfium2 as pdfium
    from PIL import Image
    from texify.inference import batch_inference
    from texify.model.model import load_model
    from texify.model.processor import load_processor
    
    model = load_model()
    processor = load_processor()
    
    pdf = pdfium.PdfDocument(pdf_path)
    
    crops = []
    for page_idx, bbox in equation_bboxes:
        page = pdf[page_idx]
        bitmap = page.render(scale=3)
        img = bitmap.to_pil()
        
        x1, y1, x2, y2 = bbox
        pad = 20
        crop = img.crop((max(0, x1-pad), max(0, y1-pad), 
                         min(img.width, x2+pad), min(img.height, y2+pad)))
        crops.append(crop)
    
    results = batch_inference(crops, model, processor)
    
    # Extract formula content from $$ delimiters
    formulas = []
    for r in results:
        # Remove $$ delimiters if present
        text = r.strip()
        if text.startswith('$$') and text.endswith('$$'):
            text = text[2:-2].strip()
        formulas.append(text)
    
    return formulas


def detect_equation_bboxes(pdf_path, scale=3):
    """
    Use surya layout detection to find equation bounding boxes in PDF pages.
    Returns list of (page_idx, (x1, y1, x2, y2)) tuples.
    """
    import pypdfium2 as pdfium
    from PIL import Image
    from surya.layout import LayoutPredictor
    
    layout_predictor = LayoutPredictor()
    pdf = pdfium.PdfDocument(pdf_path)
    
    bboxes = []
    for page_idx in range(len(pdf)):
        page = pdf[page_idx]
        bitmap = page.render(scale=scale)
        img = bitmap.to_pil()
        
        result = layout_predictor([img])
        for pred in result:
            for bbox in pred.bboxes:
                if bbox.label.lower() == 'equation':
                    poly = bbox.polygon
                    x1 = min(p[0] for p in poly)
                    y1 = min(p[1] for p in poly)
                    x2 = max(p[0] for p in poly)
                    y2 = max(p[1] for p in poly)
                    bboxes.append((page_idx, (x1, y1, x2, y2)))
    
    return bboxes


def clean_formula(formula):
    """
    Clean a raw extracted formula:
    - Remove tag commands
    - Remove trailing equation numbers
    - Remove trailing commas and periods
    - Normalize whitespace
    """
    f = formula.strip()
    
    # Remove \tag{...}
    f = re.sub(r'\\tag\{[^}]*\}', '', f)
    
    # Remove trailing equation numbers: \quad (1), \qquad(2), (1), etc.
    # Pattern: optional \quad/\qquad + space + (number) at end
    f = re.sub(r'[,\s]*\\q?quad\s*\(?\d+[\w.]*\)?\s*$', '', f)
    f = re.sub(r'[,\s]*\\qquad\s*\(?\d+[\w.]*\)?\s*$', '', f)
    # Also handle bare (number) at end after whitespace
    f = re.sub(r'\s*\\q{1,2}uad\s*\(\d+\)\s*$', '', f)
    f = re.sub(r'\s+\(\d+\)\s*$', '', f)
    
    # Remove trailing commas, periods
    f = f.rstrip(' ,.')
    
    # Normalize whitespace
    f = re.sub(r'\s+', ' ', f).strip()
    
    return f


def validate_brackets(formula):
    """
    Validate bracket matching in a LaTeX formula.
    Checks left/right pairs and basic bracket matching.
    Returns list of issues found: [(position, description), ...]
    """
    issues = []
    
    # Find all \left and \right delimiters
    left_pattern = r'\\left\s*([\(\[\{\|]|\\\{|\\\||\\langle|\.)'  
    right_pattern = r'\\right\s*([\)\]\}\|]|\\\}|\\\||\\rangle|\.)'  
    
    # More comprehensive: find \left followed by delimiter
    left_delims = list(re.finditer(
        r'\\left\s*(\(|\[|\\\{|\||\\\||\\langle|\.)', formula))
    right_delims = list(re.finditer(
        r'\\right\s*(\)|\]|\\\}|\||\\\||\\rangle|\.)', formula))
    
    # Map delimiter types for matching
    def get_delim_type(match, side):
        delim = match.group(1).strip()
        if delim == '(' or delim == ')':
            return 'paren'
        elif delim == '[' or delim == ']':
            return 'bracket'
        elif delim == '\\{' or delim == '\\}':
            return 'brace'
        elif delim == '\\langle' or delim == '\\rangle':
            return 'angle'
        elif delim == '|':
            return 'abs'
        elif delim == '\\|':
            return 'norm'
        elif delim == '.':
            return 'invisible'
        return 'unknown'
    
    # Use stack-based matching
    all_delims = []
    for m in left_delims:
        all_delims.append(('left', m.start(), get_delim_type(m, 'left'), m.group(1)))
    for m in right_delims:
        all_delims.append(('right', m.start(), get_delim_type(m, 'right'), m.group(1)))
    
    all_delims.sort(key=lambda x: x[1])
    
    stack = []
    for side, pos, dtype, raw in all_delims:
        if side == 'left':
            stack.append((pos, dtype, raw))
        elif side == 'right':
            if not stack:
                issues.append((pos, f'Unmatched \\right{raw} at position {pos}'))
            else:
                left_pos, left_type, left_raw = stack.pop()
                if left_type != 'invisible' and dtype != 'invisible' and left_type != dtype:
                    issues.append((left_pos, 
                        f'Mismatched delimiters: \\left{left_raw} at {left_pos} '
                        f'paired with \\right{raw} at {pos}'))
    
    for pos, dtype, raw in stack:
        issues.append((pos, f'Unmatched \\left{raw} at position {pos}'))
    
    return issues


def fix_bracket_mismatches(formula):
    """
    Fix bracket mismatches in a LaTeX formula.
    Returns (fixed_formula, was_changed).
    """
    issues = validate_brackets(formula)
    if not issues:
        return formula, False
    
    # Find all \left/\right pairs and check for mismatches
    left_pattern = r'\\left\s*(\(|\[|\\\{|\||\\\||\\langle|\.)'
    right_pattern = r'\\right\s*(\)|\]|\\\}|\||\\\||\\rangle|\.)'
    
    left_delims = list(re.finditer(left_pattern, formula))
    right_delims = list(re.finditer(right_pattern, formula))
    
    all_delims = []
    for m in left_delims:
        all_delims.append(('left', m.start(), m.end(), m.group(1), m))
    for m in right_delims:
        all_delims.append(('right', m.start(), m.end(), m.group(1), m))
    all_delims.sort(key=lambda x: x[1])
    
    def delim_type(raw):
        if raw in ('(', ')'): return 'paren'
        if raw in ('[', ']'): return 'bracket'
        if raw in ('\\{', '\\}'): return 'brace'
        if raw in ('\\langle', '\\rangle'): return 'angle'
        if raw == '|': return 'abs'
        if raw == '\\|': return 'norm'
        if raw == '.': return 'invisible'
        return 'unknown'
    
    # Match pairs using stack
    stack = []
    pairs = []  # (left_entry, right_entry)
    for entry in all_delims:
        side = entry[0]
        if side == 'left':
            stack.append(entry)
        else:
            if stack:
                left_entry = stack.pop()
                pairs.append((left_entry, entry))
    
    # Find mismatched pairs and fix them
    # Process replacements in reverse order to preserve positions
    replacements = []  # (start, end, new_text)
    
    for left_entry, right_entry in pairs:
        l_type = delim_type(left_entry[3])
        r_type = delim_type(right_entry[3])
        
        if l_type != r_type and l_type != 'invisible' and r_type != 'invisible':
            # Mismatch found - determine which side to fix
            # Heuristic: look at surrounding context
            # For now, change the right delimiter to match the left
            # unless the right delimiter type is more common in the formula
            
            # Count occurrences of each type in the formula
            l_count = len(re.findall(re.escape(left_entry[3]), formula))
            r_count = len(re.findall(re.escape(right_entry[3]), formula))
            
            # Map from type to left/right delimiters
            type_to_left = {'paren': '(', 'bracket': '[', 'brace': '\\{', 
                           'angle': '\\langle', 'abs': '|', 'norm': '\\|'}
            type_to_right = {'paren': ')', 'bracket': ']', 'brace': '\\}',
                            'angle': '\\rangle', 'abs': '|', 'norm': '\\|'}
            
            # Default: change right to match left's type
            # But if right's type appears more in the formula, change left instead
            new_right = '\\right' + type_to_right.get(l_type, right_entry[3])
            replacements.append((right_entry[1], right_entry[2], new_right))
    
    if not replacements:
        return formula, False
    
    # Apply replacements in reverse order
    replacements.sort(key=lambda x: x[0], reverse=True)
    fixed = formula
    for start, end, new_text in replacements:
        fixed = fixed[:start] + new_text + fixed[end:]
    
    return fixed, True


def check_misspelled_commands(formula):
    """
    Check for common misspelled LaTeX commands.
    Returns list of (position, wrong_cmd, suggested_fix).
    """
    common_commands = {
        'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta',
        'iota', 'kappa', 'lambda', 'mu', 'nu', 'xi', 'pi', 'rho', 'sigma',
        'tau', 'upsilon', 'phi', 'chi', 'psi', 'omega',
        'Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta', 'Theta',
        'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi', 'Pi', 'Rho', 'Sigma',
        'Tau', 'Upsilon', 'Phi', 'Chi', 'Psi', 'Omega',
        'sin', 'cos', 'tan', 'log', 'ln', 'exp', 'lim', 'sup', 'inf',
        'sum', 'prod', 'int', 'oint', 'frac', 'sqrt', 'text', 'mathrm',
        'operatorname', 'left', 'right', 'hbar', 'ell', 'partial',
        'nabla', 'infty', 'cdot', 'times', 'otimes', 'oplus',
        'langle', 'rangle', 'dagger', 'ddagger',
        'substack', 'stackrel', 'overline', 'underline',
    }
    
    issues = []
    # Find all backslash commands
    for m in re.finditer(r'\\([a-zA-Z]+)', formula):
        cmd = m.group(1)
        if cmd not in common_commands:
            # Check if it's a close misspelling of a known command
            from difflib import get_close_matches
            matches = get_close_matches(cmd, common_commands, n=1, cutoff=0.7)
            if matches:
                issues.append((m.start(), cmd, matches[0]))
    
    return issues


def deduplicate_formulas(formulas):
    """
    Remove duplicate formulas while preserving order.
    """
    seen = set()
    result = []
    for f in formulas:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


def write_output(original_formulas, fixed_formulas, output_path):
    """
    Write formulas to output file in the required format.
    original_formulas: list of cleaned original formula strings
    fixed_formulas: list of fixed formula strings (corrections only)
    """
    with open(output_path, 'w') as f:
        for formula in original_formulas:
            f.write(f'$${formula}$$\n')
        if fixed_formulas:
            f.write('\n')
            for formula in fixed_formulas:
                f.write(f'$${formula}$$\n')


def run_extraction_pipeline(pdf_path, output_path, marker_output_dir='/tmp/marker_output'):
    """
    End-to-end pipeline: extract, clean, validate, fix, and write formulas.
    """
    # Step 1: Extract formulas using marker-pdf
    print("Step 1: Extracting formulas with marker-pdf...")
    raw_formulas = extract_formulas_with_marker(pdf_path, marker_output_dir)
    print(f"  Found {len(raw_formulas)} raw formulas")
    
    # Step 2: Also detect equation bboxes and extract with texify for cross-reference
    print("Step 2: Detecting equation bounding boxes...")
    try:
        bboxes = detect_equation_bboxes(pdf_path)
        print(f"  Found {len(bboxes)} equation regions")
        
        if bboxes:
            print("Step 2b: Extracting with texify for cross-reference...")
            texify_formulas = extract_formulas_with_texify(pdf_path, bboxes)
            for i, tf in enumerate(texify_formulas):
                print(f"  Texify eq {i+1}: {tf[:80]}...")
    except Exception as e:
        print(f"  Texify extraction failed: {e}")
        texify_formulas = []
    
    # Step 3: Clean formulas
    print("Step 3: Cleaning formulas...")
    cleaned = [clean_formula(f) for f in raw_formulas]
    for i, (raw, clean) in enumerate(zip(raw_formulas, cleaned)):
        print(f"  Formula {i+1}: {clean[:80]}...")
    
    # Step 4: Deduplicate
    cleaned = deduplicate_formulas(cleaned)
    
    # Step 5: Validate and fix
    print("Step 4: Validating and fixing...")
    fixed_formulas = []
    for i, formula in enumerate(cleaned):
        # Check brackets
        bracket_issues = validate_brackets(formula)
        if bracket_issues:
            print(f"  Formula {i+1} has bracket issues: {bracket_issues}")
            fixed, was_changed = fix_bracket_mismatches(formula)
            if was_changed:
                print(f"  Fixed: {fixed[:80]}...")
                fixed_formulas.append(fixed)
        
        # Check misspelled commands
        spell_issues = check_misspelled_commands(formula)
        if spell_issues:
            print(f"  Formula {i+1} has spelling issues: {spell_issues}")
            fixed_f = formula
            for pos, wrong, correct in sorted(spell_issues, key=lambda x: x[0], reverse=True):
                fixed_f = fixed_f[:pos] + '\\' + correct + fixed_f[pos+len(wrong)+1:]
            if fixed_f != formula and fixed_f not in fixed_formulas:
                fixed_formulas.append(fixed_f)
    
    # Step 6: Write output
    print(f"Step 5: Writing {len(cleaned)} original + {len(fixed_formulas)} fixed formulas...")
    write_output(cleaned, fixed_formulas, output_path)
    print(f"Output written to {output_path}")
    
    return cleaned, fixed_formulas


def validate_output(output_path):
    """
    Validate the output file format and content.
    """
    if not os.path.exists(output_path):
        raise FileNotFoundError(f"Output file not found: {output_path}")
    
    with open(output_path, 'r') as f:
        content = f.read()
    
    lines = [l for l in content.strip().split('\n') if l.strip()]
    
    issues = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith('$$') or not line.endswith('$$'):
            issues.append(f"Line {i+1} not wrapped in $$: {line[:50]}")
        
        # Check for remaining tags
        formula = line[2:-2] if line.startswith('$$') and line.endswith('$$') else line
        if re.search(r'\\tag\{', formula):
            issues.append(f"Line {i+1} still has \\tag command")
        if re.search(r'\\q{1,2}uad\s*\(\d+\)', formula):
            issues.append(f"Line {i+1} still has equation number")
        if formula.endswith(',') or formula.endswith('.'):
            issues.append(f"Line {i+1} ends with punctuation")
    
    if issues:
        print("Validation issues:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    
    print(f"Validation passed: {len(lines)} formulas")
    return True

