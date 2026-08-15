"""Validator for defect normalization output.
No instance-specific content - validates against schema and codebook.
"""
import json
import pandas as pd
import os


def validate_output(output_path, data_dir):
    """Validate normalization output against requirements."""
    errors, warnings = [], []
    
    with open(output_path) as f:
        data = json.load(f)
    
    if 'records' not in data:
        errors.append("Missing 'records' key")
        return errors, warnings, {}
    
    records = data['records']
    
    # Load codebooks for code validation
    valid_codes, valid_labels = {}, {}
    for fname in os.listdir(data_dir):
        if fname.startswith('codebook_') and fname.endswith('.csv'):
            df = pd.read_csv(os.path.join(data_dir, fname))
            for _, row in df.iterrows():
                pid = row['product_id']
                if pid not in valid_codes:
                    valid_codes[pid] = set()
                    valid_labels[pid] = {}
                valid_codes[pid].add(row['code'])
                valid_labels[pid][row['code']] = row['standard_label']
    
    # Load logs for span validation
    logs_df = pd.read_csv(os.path.join(data_dir, 'test_center_logs.csv'))
    log_texts = dict(zip(logs_df['record_id'].astype(str), logs_df['raw_reason_text'].astype(str)))
    
    if len(records) != len(logs_df):
        errors.append(f"Expected {len(logs_df)} records, got {len(records)}")
    
    seen_seg_ids = set()
    for r in records:
        rid = str(r.get('record_id', ''))
        pid = r.get('product_id', '')
        
        for field in ['record_id', 'product_id', 'station', 'engineer_id', 'raw_reason_text']:
            if field not in r:
                errors.append(f"{rid}: missing '{field}'")
        
        if 'normalized' not in r or not r['normalized']:
            errors.append(f"{rid}: missing/empty 'normalized'")
            continue
        
        for si, seg in enumerate(r['normalized']):
            seg_id = seg.get('segment_id', '')
            expected = f"{rid}-S{si+1}"
            if seg_id != expected:
                errors.append(f"{rid}: segment_id '{seg_id}' should be '{expected}'")
            if seg_id in seen_seg_ids:
                errors.append(f"Duplicate segment_id: {seg_id}")
            seen_seg_ids.add(seg_id)
            
            span = seg.get('span_text', '')
            if not span:
                errors.append(f"{seg_id}: empty span_text")
            elif rid in log_texts and span not in log_texts[rid]:
                errors.append(f"{seg_id}: span_text not verbatim")
            
            code = seg.get('pred_code', '')
            label = seg.get('pred_label', '')
            if code == 'UNKNOWN':
                if label != '':
                    warnings.append(f"{seg_id}: UNKNOWN should have empty pred_label")
            elif code and pid in valid_codes:
                if code not in valid_codes[pid]:
                    errors.append(f"{seg_id}: code '{code}' not in {pid} codebook")
                elif code in valid_labels.get(pid, {}) and label != valid_labels[pid][code]:
                    errors.append(f"{seg_id}: label mismatch for {code}")
            
            conf = seg.get('confidence')
            if conf is None:
                errors.append(f"{seg_id}: missing confidence")
            elif not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
                errors.append(f"{seg_id}: confidence {conf} invalid")
            
            if not seg.get('rationale', ''):
                errors.append(f"{seg_id}: empty rationale")
    
    total = sum(len(r['normalized']) for r in records)
    unk = sum(1 for r in records for s in r['normalized'] if s['pred_code'] == 'UNKNOWN')
    confs = [s['confidence'] for r in records for s in r['normalized'] if s.get('confidence') is not None]
    nu = [c for r in records for s in r['normalized'] if s['pred_code'] != 'UNKNOWN' for c in [s.get('confidence', 0)]]
    uc = [c for r in records for s in r['normalized'] if s['pred_code'] == 'UNKNOWN' for c in [s.get('confidence', 0)]]
    
    if nu and uc and sum(uc)/len(uc) >= sum(nu)/len(nu):
        errors.append("Unknown confidence mean should be less than non-unknown")
    
    stats = dict(
        total_records=len(records), total_segments=total,
        unknown_count=unk, unknown_pct=round(100*unk/total, 1) if total else 0,
        conf_mean=round(sum(confs)/len(confs), 4) if confs else 0,
        conf_unique=len(set(round(c, 4) for c in confs)),
        errors=len(errors), warnings=len(warnings))
    
    return errors, warnings, stats


if __name__ == '__main__':
    import sys
    op = sys.argv[1] if len(sys.argv) > 1 else '/app/output/solution.json'
    dd = sys.argv[2] if len(sys.argv) > 2 else '/app/data'
    errors, warnings, stats = validate_output(op, dd)
    print(f"Stats: {stats}")
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors[:20]: print(f"  {e}")
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings[:10]: print(f"  {w}")
    if not errors: print("\nVALIDATION PASSED")
