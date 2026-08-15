import re, csv, json
import pdfplumber, openpyxl
from rapidfuzz import fuzz, process

def extract_invoices(pdf_path):
    invoices = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            invoices.append(parse_invoice_text(text, i + 1))
    return invoices

def parse_invoice_text(text, page_number):
    vendor_name = amount = iban = po_number = None
    for line in text.strip().split('\n'):
        ls = line.strip()
        if ls.startswith('From:'): vendor_name = ls[5:].strip()
        m = re.search(r'Total\s*\$([\d,]+\.?\d*)', ls)
        if m: amount = float(m.group(1).replace(',', ''))
        if 'Payment IBAN:' in ls: iban = ls.split('Payment IBAN:')[1].strip()
        if 'PO Number:' in ls:
            po_raw = ls.split('PO Number:')[1].strip()
            po_number = po_raw if po_raw else None
    return {'page_number': page_number, 'vendor_name': vendor_name,
            'amount': amount, 'iban': iban, 'po_number': po_number}

def load_vendors(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active
    vendors = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is not None:
            vendors.append({'id': str(row[0]).strip(), 'name': str(row[1]).strip(),
                          'iban': str(row[2]).strip()})
    return vendors

def load_purchase_orders(csv_path):
    pos = {}
    with open(csv_path, 'r') as f:
        for row in csv.DictReader(f):
            pos[row['po_number'].strip()] = {
                'vendor_id': row['vendor_id'].strip(),
                'amount': float(row['amount'].strip())}
    return pos

def calibrate_fuzzy_threshold(invoices, vendors):
    """Derive threshold by finding the gap nearest to the top score cluster.
    This separates exact/near-exact matches from partial/no matches.
    Strategy: find the highest gap that separates at least one score
    from the top cluster."""
    vnames = [v['name'] for v in vendors]
    scores = []
    for inv in invoices:
        name = inv.get('vendor_name')
        if not name: continue
        r = process.extractOne(name, vnames, scorer=fuzz.token_sort_ratio)
        if r: scores.append(r[1])
    if not scores: return 50
    ss = sorted(scores)
    # Find the gap closest to the top that has a significant size
    # Walk from top down, find first significant gap
    best_gap_pos = 0
    best_gap_size = 0
    for i in range(len(ss)-1, 0, -1):
        g = ss[i] - ss[i-1]
        if g > best_gap_size:
            best_gap_size = g
            best_gap_pos = i - 1
        # Stop once we find a gap > 5 points from the top
        if g > 5:
            break
    threshold = (ss[best_gap_pos] + ss[best_gap_pos + 1]) / 2.0
    return threshold

def match_vendor(name, vendors, threshold):
    if not name: return None
    vnames = [v['name'] for v in vendors]
    r = process.extractOne(name, vnames, scorer=fuzz.token_sort_ratio, score_cutoff=threshold)
    if r is None: return None
    return vendors[r[2]]

def check_invoice_fraud(invoice, vendors, pos, threshold):
    matched = match_vendor(invoice['vendor_name'], vendors, threshold)
    if matched is None: return True, 'Unknown Vendor', None
    inv_iban = (invoice['iban'] or '').strip().upper()
    v_iban = matched['iban'].strip().upper()
    if inv_iban != v_iban: return True, 'IBAN Mismatch', matched
    po_num = invoice['po_number']
    if po_num is None or po_num not in pos: return True, 'Invalid PO', matched
    po = pos[po_num]
    if abs(invoice['amount'] - po['amount']) > 0.01: return True, 'Amount Mismatch', matched
    if po['vendor_id'] != matched['id']: return True, 'Vendor Mismatch', matched
    return False, None, matched

def run_fraud_detection(pdf_path, vendors_path, po_path, output_path, fuzzy_threshold=None):
    vendors = load_vendors(vendors_path)
    pos = load_purchase_orders(po_path)
    invoices = extract_invoices(pdf_path)
    if fuzzy_threshold is None:
        fuzzy_threshold = calibrate_fuzzy_threshold(invoices, vendors)
        print('Threshold: %.2f' % fuzzy_threshold)
    fraud_report = []
    for inv in invoices:
        is_fraud, reason, mv = check_invoice_fraud(inv, vendors, pos, fuzzy_threshold)
        if is_fraud:
            fraud_report.append({
                'invoice_page_number': inv['page_number'],
                'vendor_name': inv['vendor_name'],
                'invoice_amount': inv['amount'],
                'iban': inv['iban'],
                'po_number': inv['po_number'],
                'reason': reason})
    with open(output_path, 'w') as f:
        json.dump(fraud_report, f, indent=2)
    print('Flagged: %d of %d' % (len(fraud_report), len(invoices)))
    return fraud_report

def validate_report(output_path):
    with open(output_path, 'r') as f:
        report = json.load(f)
    valid = {'Unknown Vendor','IBAN Mismatch','Invalid PO','Amount Mismatch','Vendor Mismatch'}
    for e in report:
        assert e['reason'] in valid
    return True
