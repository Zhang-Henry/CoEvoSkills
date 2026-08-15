---
name: evo-sc100-filler
description: "Fill California SC-100 Small Claims Court PDF forms using pymupdf. Use when you need to fill interactive PDF court forms with case data."
---

# SC-100 Small Claims Court Form Filler

This skill fills California SC-100 (Plaintiff's Claim and ORDER to Go to Small Claims Court) PDF forms.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-sc100-filler/scripts')
from fill_sc100 import fill_sc100, validate_sc100

case_data = {
    'plaintiff_name': 'Jane Doe',
    'plaintiff_phone': '5551234567',
    'plaintiff_street': '123 Main St',
    'plaintiff_city': 'San Jose',
    'plaintiff_state': 'CA',
    'plaintiff_zip': '95112',
    'plaintiff_email': 'jane@example.com',
    'defendant_name': 'John Smith',
    'defendant_phone': '5559876543',
    'defendant_street': '456 Oak Ave',
    'defendant_city': 'San Jose',
    'defendant_state': 'CA',
    'defendant_zip': '95112',
    'claim_amount': '2000',
    'claim_reason': 'Failed to return security deposit',
    'has_specific_date': False,
    'claim_date_started': '2025-01-01',
    'claim_date_through': '2025-06-01',
    'claim_calculation': 'Amount on lease agreement',
    'asked_defendant': True,
    'filing_reason': 'a',  # a-e corresponding to section 5 options
    'filing_zip': '95112',
    'attorney_dispute': False,
    'suing_public_entity': False,
    'filed_12_claims': False,
    'claim_over_2500': False,
    'filing_date': '2025-06-01',
}

fill_sc100('/root/sc100-blank.pdf', '/root/sc100-filled.pdf', case_data)
validate_sc100('/root/sc100-filled.pdf')
```

## Form Field Mapping

The SC-100 form uses XFA-style hierarchical field names. Key sections:
- Page 2, Section 1: Plaintiff info (name, phone, address, email)
- Page 2, Section 2: Defendant info (name, phone, address)
- Page 2, Section 3: Claim amount and reason
- Page 3, Section 3b: Dates (specific or range)
- Page 3, Section 3c: Calculation explanation
- Page 3, Section 4: Asked defendant (Yes/No)
- Page 3, Section 5: Filing reason (a-e checkboxes)
- Page 3, Section 6: Zip code of filing location
- Page 3, Section 7: Attorney-client dispute (Yes/No)
- Page 3, Section 8: Suing public entity (Yes/No)
- Page 4, Section 9: Filed 12+ claims (Yes/No)
- Page 4, Section 10: Claim over $2500 (Yes/No)
- Page 4, Section 11: Signature date and name
- Page headers: Plaintiff name on pages 2-4

## Checkbox States
- Yes/No pairs use on_states '1' for first option, '2' for second
- Section 5 uses on_states '1'-'5' for options a-e
- 'Off' or empty string means unchecked
