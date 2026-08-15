---
name: evo-invoice-fraud
description: "Invoice fraud detection skill: extracts invoices from PDF, matches against vendor master and PO register, flags fraud using priority-ordered checks. Auto-calibrates fuzzy threshold and filters non-standard PO entries."
---

# Invoice Fraud Detection Skill

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-invoice-fraud/scripts')
from utils import run_fraud_detection, validate_report

report = run_fraud_detection(
    pdf_path='/root/invoices.pdf',
    vendors_path='/root/vendors.xlsx',
    po_path='/root/purchase_orders.csv',
    output_path='/root/fraud_report.json'
)
validate_report('/root/fraud_report.json')
```

## Key Features
- **PO dominant-pattern filtering**: Detects dominant vendor ID pattern in POs and excludes non-conforming entries
- **All vendors included**: Vendor master is loaded without filtering
- **Auto-calibrated fuzzy threshold**: Derived from score distribution gap analysis
- **Priority-ordered fraud checks**: Unknown Vendor > IBAN Mismatch > Invalid PO > Amount Mismatch > Vendor Mismatch
