"""
Utility functions for filling California SC-100 Small Claims Court form.
Uses pymupdf to set form field values in the PDF.
"""
import pymupdf


def set_text_field(doc, field_name, value):
    """Set a text field value across all pages."""
    for page in doc:
        for widget in page.widgets():
            if widget.field_name == field_name:
                widget.field_value = str(value)
                widget.update()
                return True
    return False


def set_checkbox(doc, field_name, on_state_value):
    """Set a checkbox to its 'on' state. on_state_value is the state string like '1', '2', etc."""
    for page in doc:
        for widget in page.widgets():
            if widget.field_name == field_name:
                widget.field_value = on_state_value
                widget.update()
                return True
    return False


def fill_sc100(input_pdf, output_pdf, case_data):
    """
    Fill SC-100 form with case data.
    
    case_data is a dict with keys:
      plaintiff_name, plaintiff_phone, plaintiff_street, plaintiff_city,
      plaintiff_state, plaintiff_zip, plaintiff_email,
      defendant_name, defendant_phone, defendant_street, defendant_city,
      defendant_state, defendant_zip,
      claim_amount, claim_reason, claim_date_started, claim_date_through,
      claim_calculation,
      asked_defendant (bool), asked_defendant_explanation (str or None),
      filing_reason (str - 'a','b','c','d','e'),
      filing_zip,
      attorney_dispute (bool),
      suing_public_entity (bool), public_entity_claim_date (str or None),
      filed_12_claims (bool),
      claim_over_2500 (bool),
      filing_date,
      has_specific_date (bool), specific_date (str or None),
    """
    doc = pymupdf.open(input_pdf)
    
    prefix2 = 'SC-100[0].Page2[0]'
    prefix3 = 'SC-100[0].Page3[0]'
    prefix4 = 'SC-100[0].Page4[0]'
    
    # === PAGE 2: Section 1 - Plaintiff ===
    p1 = f'{prefix2}.List1[0].Item1[0]'
    set_text_field(doc, f'{p1}.PlaintiffName1[0]', case_data['plaintiff_name'])
    set_text_field(doc, f'{p1}.PlaintiffPhone1[0]', case_data['plaintiff_phone'])
    set_text_field(doc, f'{p1}.PlaintiffAddress1[0]', case_data['plaintiff_street'])
    set_text_field(doc, f'{p1}.PlaintiffCity1[0]', case_data['plaintiff_city'])
    set_text_field(doc, f'{p1}.PlaintiffState1[0]', case_data['plaintiff_state'])
    set_text_field(doc, f'{p1}.PlaintiffZip1[0]', case_data['plaintiff_zip'])
    set_text_field(doc, f'{p1}.EmailAdd1[0]', case_data['plaintiff_email'])
    
    # === PAGE 2: Section 2 - Defendant ===
    d1 = f'{prefix2}.List2[0].item2[0]'
    set_text_field(doc, f'{d1}.DefendantName1[0]', case_data['defendant_name'])
    set_text_field(doc, f'{d1}.DefendantPhone1[0]', case_data['defendant_phone'])
    set_text_field(doc, f'{d1}.DefendantAddress1[0]', case_data['defendant_street'])
    set_text_field(doc, f'{d1}.DefendantCity1[0]', case_data['defendant_city'])
    set_text_field(doc, f'{d1}.DefendantState1[0]', case_data['defendant_state'])
    set_text_field(doc, f'{d1}.DefendantZip1[0]', case_data['defendant_zip'])
    
    # === PAGE 2: Section 3 - Claim ===
    set_text_field(doc, f'{prefix2}.List3[0].PlaintiffClaimAmount1[0]', case_data['claim_amount'])
    set_text_field(doc, f'{prefix2}.List3[0].Lia[0].FillField2[0]', case_data['claim_reason'])
    
    # === PAGE 3: Section 3b - Dates ===
    if case_data.get('has_specific_date'):
        set_text_field(doc, f'{prefix3}.List3[0].Lib[0].Date1[0]', case_data['specific_date'])
    else:
        # Check the "If no specific date" checkbox
        set_checkbox(doc, f'{prefix3}.List3[0].Checkbox1[0]', '1')
        set_text_field(doc, f'{prefix3}.List3[0].Lib[0].Date2[0]', case_data['claim_date_started'])
        set_text_field(doc, f'{prefix3}.List3[0].Lib[0].Date3[0]', case_data['claim_date_through'])
    
    # === PAGE 3: Section 3c - Calculation ===
    set_text_field(doc, f'{prefix3}.List3[0].Lic[0].FillField1[0]', case_data['claim_calculation'])
    
    # === PAGE 3: Section 4 - Asked defendant ===
    if case_data['asked_defendant']:
        set_checkbox(doc, f'{prefix3}.List4[0].Item4[0].Checkbox50[0]', '1')  # Yes
    else:
        set_checkbox(doc, f'{prefix3}.List4[0].Item4[0].Checkbox50[1]', '2')  # No
        if case_data.get('asked_defendant_explanation'):
            set_text_field(doc, f'{prefix3}.List4[0].Item4[0].FillField2[0]', case_data['asked_defendant_explanation'])
    
    # === PAGE 3: Section 5 - Filing reason ===
    reason = case_data['filing_reason']
    reason_map = {
        'a': (f'{prefix3}.List5[0].Lia[0].Checkbox5cb[0]', '1'),
        'b': (f'{prefix3}.List5[0].Lib[0].Checkbox5cb[0]', '2'),
        'c': (f'{prefix3}.List5[0].Lic[0].Checkbox5cb[0]', '3'),
        'd': (f'{prefix3}.List5[0].Lid[0].Checkbox5cb[0]', '4'),
        'e': (f'{prefix3}.List5[0].Lie[0].Checkbox5cb[0]', '5'),
    }
    if reason in reason_map:
        fname, state = reason_map[reason]
        set_checkbox(doc, fname, state)
    
    # === PAGE 3: Section 6 - Zip code ===
    set_text_field(doc, f'{prefix3}.List6[0].item6[0].ZipCode1[0]', case_data['filing_zip'])
    
    # === PAGE 3: Section 7 - Attorney-client fee dispute ===
    if case_data.get('attorney_dispute'):
        set_checkbox(doc, f'{prefix3}.List7[0].item7[0].Checkbox60[0]', '1')  # Yes
    else:
        set_checkbox(doc, f'{prefix3}.List7[0].item7[0].Checkbox60[1]', '2')  # No
    
    # === PAGE 3: Section 8 - Suing public entity ===
    if case_data.get('suing_public_entity'):
        set_checkbox(doc, f'{prefix3}.List8[0].item8[0].Checkbox61[0]', '1')  # Yes
        if case_data.get('public_entity_claim_date'):
            set_text_field(doc, f'{prefix3}.List8[0].item8[0].Date4[0]', case_data['public_entity_claim_date'])
    else:
        set_checkbox(doc, f'{prefix3}.List8[0].item8[0].Checkbox61[1]', '2')  # No
    
    # === PAGE 4: Section 9 - Filed 12+ claims ===
    if case_data.get('filed_12_claims'):
        set_checkbox(doc, f'{prefix4}.List9[0].Item9[0].Checkbox62[0]', '1')  # Yes
    else:
        set_checkbox(doc, f'{prefix4}.List9[0].Item9[0].Checkbox62[1]', '2')  # No
    
    # === PAGE 4: Section 10 - Claim over $2500 ===
    if case_data.get('claim_over_2500'):
        set_checkbox(doc, f'{prefix4}.List10[0].li10[0].Checkbox63[0]', '1')  # Yes
    else:
        set_checkbox(doc, f'{prefix4}.List10[0].li10[0].Checkbox63[1]', '2')  # No
    
    # === PAGE 4: Section 11 - Signature ===
    set_text_field(doc, f'{prefix4}.Sign[0].Date1[0]', case_data['filing_date'])
    set_text_field(doc, f'{prefix4}.Sign[0].PlaintiffName1[0]', case_data['plaintiff_name'])
    
    # === Page headers (Plaintiff name on pages 2, 3, 4) ===
    set_text_field(doc, f'{prefix2}.PxCaption[0].Plaintiff[0]', case_data['plaintiff_name'])
    set_text_field(doc, f'{prefix3}.PxCaption[0].Plaintiff[0]', case_data['plaintiff_name'])
    set_text_field(doc, f'{prefix4}.PxCaption[0].Plaintiff[0]', case_data['plaintiff_name'])
    
    doc.save(output_pdf)
    doc.close()
    return output_pdf


def validate_sc100(pdf_path):
    """Validate that the filled SC-100 form has expected fields set."""
    doc = pymupdf.open(pdf_path)
    errors = []
    
    filled_fields = {}
    checked_boxes = {}
    
    for page in doc:
        for widget in page.widgets():
            if widget.field_type == 7:  # text
                if widget.field_value and widget.field_value.strip():
                    filled_fields[widget.field_name] = widget.field_value
            elif widget.field_type == 2:  # checkbox
                if widget.field_value and widget.field_value != 'Off' and widget.field_value != '':
                    checked_boxes[widget.field_name] = widget.field_value
    
    doc.close()
    
    # Check required fields are filled
    required_text_fields = [
        'PlaintiffName1[0]',
        'PlaintiffPhone1[0]',
        'PlaintiffAddress1[0]',
        'DefendantName1[0]',
        'PlaintiffClaimAmount1[0]',
    ]
    
    for req in required_text_fields:
        found = any(req in k for k in filled_fields.keys())
        if not found:
            errors.append(f"Missing required field containing: {req}")
    
    if errors:
        print(f"Validation FAILED with {len(errors)} errors:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("Validation PASSED")
    
    print(f"\nFilled text fields ({len(filled_fields)}):")
    for k, v in sorted(filled_fields.items()):
        print(f"  {k} = {v!r}")
    
    print(f"\nChecked boxes ({len(checked_boxes)}):")
    for k, v in sorted(checked_boxes.items()):
        print(f"  {k} = {v!r}")
    
    return len(errors) == 0

