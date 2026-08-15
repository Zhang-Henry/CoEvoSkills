import json
import re
import copy
import zipfile
import os
import shutil
from lxml import etree

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{' + W_NS + '}'


def load_employee_data(json_path):
    """Load employee data from JSON file."""
    with open(json_path, 'r') as f:
        return json.load(f)


def get_xml_parts_to_process(zip_path):
    """Return list of XML part names that may contain placeholders."""
    parts = []
    with zipfile.ZipFile(zip_path, 'r') as z:
        for name in z.namelist():
            if name.startswith('word/') and name.endswith('.xml'):
                # Include document.xml, headers, footers
                if any(k in name for k in ['document', 'header', 'footer']):
                    parts.append(name)
    return parts


def merge_split_placeholders(xml_content):
    """
    Merge adjacent <w:r> elements whose combined <w:t> text forms a placeholder.
    
    Placeholders like {{SOME_VAR}} may be split across multiple runs due to 
    Word's internal formatting. This function detects such splits and merges
    the text into the first run, removing subsequent partial runs.
    
    Strategy: Walk through all paragraphs and table cells. For each sequence
    of runs, check if concatenating their text would form complete placeholders.
    If a run contains '{{' but not the closing '}}', merge subsequent runs until
    we find the closing '}}'.
    """
    root = etree.fromstring(xml_content)
    
    # Find all elements that can contain runs (paragraphs)
    # We need to process <w:p> elements
    paragraphs = root.iter(W + 'p')
    
    for para in paragraphs:
        _merge_runs_in_parent(para)
    
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)


def _merge_runs_in_parent(parent):
    """
    Within a parent element (paragraph), find runs with split placeholders
    and merge them.
    """
    while True:
        runs = list(parent.findall(W + 'r'))
        if not runs:
            break
        
        merged_any = False
        i = 0
        while i < len(runs):
            run = runs[i]
            t_elem = run.find(W + 't')
            if t_elem is None or t_elem.text is None:
                i += 1
                continue
            
            text = t_elem.text
            
            # Check if this run has an unclosed {{ placeholder
            # Count opening {{ and closing }} to see if balanced
            open_count = text.count('{{')
            close_count = text.count('}}')
            
            if open_count > close_count:
                # We have unclosed placeholders - need to merge with subsequent runs
                combined_text = text
                runs_to_remove = []
                j = i + 1
                
                while j < len(runs):
                    next_run = runs[j]
                    next_t = next_run.find(W + 't')
                    if next_t is None or next_t.text is None:
                        j += 1
                        continue
                    
                    combined_text += next_t.text
                    runs_to_remove.append(next_run)
                    
                    # Check if now balanced
                    total_open = combined_text.count('{{')
                    total_close = combined_text.count('}}')
                    
                    if total_open <= total_close:
                        break
                    j += 1
                
                if runs_to_remove:
                    # Set the merged text on the first run
                    t_elem.text = combined_text
                    # Preserve space
                    t_elem.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                    
                    # Remove the merged runs from parent
                    for r in runs_to_remove:
                        parent.remove(r)
                    
                    merged_any = True
                    break  # Restart the loop since we modified the structure
            
            i += 1
        
        if not merged_any:
            break


def replace_placeholders(xml_bytes, data):
    """
    Replace {{PLACEHOLDER}} patterns in the XML with values from data dict.
    Works on the serialized XML bytes after merging.
    """
    xml_str = xml_bytes.decode('utf-8') if isinstance(xml_bytes, bytes) else xml_bytes
    
    for key, value in data.items():
        placeholder = '{{' + key + '}}'
        xml_str = xml_str.replace(placeholder, str(value))
    
    return xml_str.encode('utf-8') if isinstance(xml_bytes, bytes) else xml_str


def handle_conditional_sections(xml_bytes, data):
    """
    Handle {{IF_RELOCATION}}...{{END_IF_RELOCATION}} conditional blocks.
    
    If RELOCATION_PACKAGE is 'Yes', keep the content but remove the markers.
    If RELOCATION_PACKAGE is not 'Yes', remove the entire block including content.
    """
    xml_str = xml_bytes.decode('utf-8') if isinstance(xml_bytes, bytes) else xml_bytes
    
    relocation = data.get('RELOCATION_PACKAGE', 'No')
    
    if relocation.lower() == 'yes':
        # Keep content, just remove the markers
        xml_str = xml_str.replace('{{IF_RELOCATION}}', '')
        xml_str = xml_str.replace('{{END_IF_RELOCATION}}', '')
    else:
        # Remove everything between IF and END_IF markers, including the markers
        # This needs to handle the case where markers might be in different runs
        pattern = r'\{\{IF_RELOCATION\}\}.*?\{\{END_IF_RELOCATION\}\}'
        xml_str = re.sub(pattern, '', xml_str, flags=re.DOTALL)
    
    return xml_str.encode('utf-8') if isinstance(xml_bytes, bytes) else xml_str


def process_template(template_path, output_path, data):
    """
    End-to-end: process a DOCX template, fill placeholders, handle conditionals,
    and save the result.
    """
    # Copy template to output
    shutil.copy2(template_path, output_path)
    
    # Get parts to process
    parts = get_xml_parts_to_process(template_path)
    
    # Read all parts
    part_contents = {}
    with zipfile.ZipFile(template_path, 'r') as z:
        for part in parts:
            part_contents[part] = z.read(part)
    
    # Process each part
    processed = {}
    for part, content in part_contents.items():
        # Step 1: Merge split placeholders
        merged = merge_split_placeholders(content)
        
        # Step 2: Handle conditional sections (before placeholder replacement
        # so that placeholders inside conditionals get replaced too)
        merged = handle_conditional_sections(merged, data)
        
        # Step 3: Replace placeholders
        merged = replace_placeholders(merged, data)
        
        processed[part] = merged
    
    # Write back to the output docx
    # We need to update the zip file in place
    _update_zip_parts(output_path, processed)
    
    return output_path


def _update_zip_parts(zip_path, parts_dict):
    """
    Update specific parts in a ZIP (docx) file.
    """
    temp_path = zip_path + '.tmp'
    
    with zipfile.ZipFile(zip_path, 'r') as zin:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.namelist():
                if item in parts_dict:
                    data = parts_dict[item]
                    if isinstance(data, str):
                        data = data.encode('utf-8')
                    zout.writestr(item, data)
                else:
                    zout.writestr(item, zin.read(item))
    
    shutil.move(temp_path, zip_path)


def validate_output(output_path):
    """
    Validate the output docx:
    1. Check it's a valid ZIP
    2. Check no unresolved {{PLACEHOLDER}} patterns remain
    3. Check no {{IF_*}} or {{END_IF_*}} markers remain
    """
    errors = []
    
    # Check valid ZIP
    if not zipfile.is_zipfile(output_path):
        errors.append("Output is not a valid ZIP/DOCX file")
        return errors
    
    with zipfile.ZipFile(output_path, 'r') as z:
        for name in z.namelist():
            if name.startswith('word/') and name.endswith('.xml'):
                if any(k in name for k in ['document', 'header', 'footer']):
                    content = z.read(name).decode('utf-8')
                    
                    # Check for unresolved placeholders
                    unresolved = re.findall(r'\{\{[A-Z_]+\}\}', content)
                    if unresolved:
                        errors.append(f"{name}: Unresolved placeholders: {unresolved}")
                    
                    # Check for conditional markers
                    if_markers = re.findall(r'\{\{(?:IF_|END_IF_)[A-Z_]+\}\}', content)
                    if if_markers:
                        errors.append(f"{name}: Remaining conditional markers: {if_markers}")
                    
                    # Check XML is valid
                    try:
                        etree.fromstring(content.encode('utf-8'))
                    except etree.XMLSyntaxError as e:
                        errors.append(f"{name}: Invalid XML: {e}")
    
    return errors


def fill_template(template_path, json_path, output_path):
    """
    Main entry point: load data, process template, validate output.
    Returns list of validation errors (empty if success).
    """
    data = load_employee_data(json_path)
    process_template(template_path, output_path, data)
    errors = validate_output(output_path)
    return errors
