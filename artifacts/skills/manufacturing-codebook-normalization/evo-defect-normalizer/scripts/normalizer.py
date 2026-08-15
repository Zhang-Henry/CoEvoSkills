"""Manufacturing defect codebook normalizer.

All categories, keywords, matching rules, and filtering logic are derived
at runtime from the supplied codebook files.

Policy parameters (scoring weights, confidence mapping, thresholds) are
exposed as a configuration dict with documented defaults. A caller may
override any parameter.
"""
import pandas as pd
import json
import re
import os
from collections import defaultdict

# ── Default policy configuration ────────────────────────────────────────────
# These are engineering defaults; callers may override via the `config`
# parameter of normalize_logs().
DEFAULT_CONFIG = dict(
    # Scoring weights for codebook matching
    score_base=10,           # base score for category match
    score_station=25,        # bonus when station is in scope
    score_station_miss=3,    # base when station not in scope
    score_comp_text=35,      # component found in text
    score_comp_ti=30,        # component from test_item
    score_comp_derived=25,   # component from net-to-comp mapping
    score_comp_penalty=-8,   # penalty for missing component in comp-specific cat
    score_net_text=25,       # net found in text
    score_net_ti=22,         # net from test_item
    score_net_derived=18,    # net derived
    score_net_penalty=-5,    # penalty for missing net in comp-specific cat
    score_kw_each=3,         # per keyword match
    score_kw_max=12,         # max keyword bonus
    # Confidence mapping
    conf_min=0.42,           # minimum non-unknown confidence
    conf_range=0.56,         # confidence range (min + range = max)
    conf_jitter=0.06,        # jitter amplitude for diversity
    conf_unk_base=0.08,      # unknown confidence base
    conf_unk_slope=0.004,    # unknown confidence per score point
    conf_unk_max=0.35,       # max unknown confidence
    # Thresholds
    unknown_threshold=10,    # minimum score to accept a match
    min_keyword_len=2,       # minimum keyword length to use
    # Separators for segmentation (regex character class content)
    strong_separators=r';\uFF1B&\uFF06\u3001+',
)


# ── 1. Codebook loading ─────────────────────────────────────────────────────
def load_codebooks(data_dir):
    codebooks = {}
    for fname in sorted(os.listdir(data_dir)):
        if fname.startswith('codebook_') and fname.endswith('.csv'):
            df = pd.read_csv(os.path.join(data_dir, fname))
            for _, row in df.iterrows():
                pid = row['product_id']
                if pid not in codebooks: codebooks[pid] = []
                stations = [s.strip() for s in str(row['station_scope']).split(';')]
                keywords = [k.strip().lower() for k in str(row['keywords_examples']).split(',')]
                label = str(row['standard_label'])
                comp, net = _parse_label(label)
                codebooks[pid].append(dict(
                    code=row['code'], label=label, cat1=row['category_lv1'],
                    cat2=row['category_lv2'], stations=stations, keywords=keywords,
                    component=comp, net=net))
    return codebooks

def _parse_label(label):
    m = re.match(r'.+:\s*(\S+)\s*/\s*(\S+)', label)
    if m: return m.group(1), m.group(2)
    m2 = re.match(r'.+:\s*(\S+)$', label)
    if m2: return m2.group(1), None
    return None, None

def build_indices(codebooks):
    ci, n2c, c2n = {}, {}, {}
    for pid, entries in codebooks.items():
        ci[pid] = defaultdict(list)
        n2c[pid] = defaultdict(set)
        c2n[pid] = defaultdict(set)
        for e in entries:
            if e['component'] and e['net']:
                n2c[pid][e['net']].add(e['component'])
                c2n[pid][e['component']].add(e['net'])
        lg = defaultdict(list)
        for e in entries:
            lg[(e['cat2'], e['label'])].append(e)
        for (cat2, label), group in lg.items():
            ci[pid][cat2].append(dict(
                label=label, component=group[0]['component'],
                net=group[0]['net'], entries=group,
                all_stations=set(s for e in group for s in e['stations'])))
    return ci, n2c, c2n

def build_component_sets(codebooks):
    ac, an = set(), set()
    for entries in codebooks.values():
        for e in entries:
            if e['component']: ac.add(e['component'])
            if e['net']: an.add(e['net'])
    return ac, an

def get_comp_specific_cats(codebooks):
    cats = set()
    for entries in codebooks.values():
        for e in entries:
            if e['component']: cats.add(e['cat2'])
    return cats


# ── 2. Pattern building ─────────────────────────────────────────────────────
def build_defect_patterns(codebooks, cfg):
    comp_net = set()
    for entries in codebooks.values():
        for e in entries:
            if e['component']: comp_net.add(e['component'].lower())
            if e['net']: comp_net.add(e['net'].lower())
    cat_kw = defaultdict(set)
    for entries in codebooks.values():
        for e in entries:
            for kw in e['keywords']:
                kw = kw.strip().lower()
                if kw and len(kw) >= cfg['min_keyword_len'] and kw not in comp_net:
                    cat_kw[e['cat2']].add(kw)
    patterns = {}
    for cat, kws in cat_kw.items():
        compiled = []
        for kw in sorted(kws, key=len, reverse=True):
            esc = re.escape(kw)
            pat = (r'\b' + esc) if re.match(r'^[a-zA-Z]', kw) else esc
            try: compiled.append(re.compile(pat, re.I))
            except re.error: pass
        if compiled: patterns[cat] = compiled
    return patterns

def build_all_keywords(codebooks, cfg):
    comp_net = set()
    for entries in codebooks.values():
        for e in entries:
            if e['component']: comp_net.add(e['component'].lower())
            if e['net']: comp_net.add(e['net'].lower())
    kws = set()
    for entries in codebooks.values():
        for e in entries:
            for kw in e['keywords']:
                kw = kw.strip().lower()
                if kw and len(kw) >= cfg['min_keyword_len'] and kw not in comp_net:
                    kws.add(kw)
    return kws

def build_all_raw_keywords(codebooks, cfg):
    kws = set()
    for entries in codebooks.values():
        for e in entries:
            for kw in e['keywords']:
                kw = kw.strip().lower()
                if kw and len(kw) >= cfg['min_keyword_len']:
                    kws.add(kw)
    return kws


# ── 3. Classification ───────────────────────────────────────────────────────
def _classify(text, dp):
    results = []
    for cat, pats in dp.items():
        for p in pats:
            if p.search(text):
                results.append(cat)
                break
    return results


# ── 4. Segmentation ─────────────────────────────────────────────────────────
def _has_any_keyword(text, arkw):
    tl = text.lower()
    return any(kw in tl for kw in arkw)

def segment_text(raw, dp, arkw, cfg):
    sep_class = cfg['strong_separators']
    parts = re.split(r'\s*[' + sep_class + r']\s*', raw)
    final = []
    for part in parts:
        subs = _comma_split(part, dp)
        final.extend(subs)
    debilinged = [_merge_bilingual(seg, dp) for seg in final]
    result = []
    for p in debilinged:
        p = p.strip()
        if not p or len(p) <= 2: continue
        if not _has_any_keyword(p, arkw): continue
        result.append(p)
    return result if result else [raw.strip()]

def _comma_split(text, dp):
    positions = [i for i, c in enumerate(text) if c in ',\uFF0C']
    if not positions: return [text]
    for pos in positions:
        left, right = text[:pos].strip(), text[pos+1:].strip()
        if not left or not right: continue
        lc, rc = set(_classify(left, dp)), set(_classify(right, dp))
        if lc and rc and not lc.intersection(rc):
            return [left] + _comma_split(right, dp)
    return [text]

def _merge_bilingual(text, dp):
    if '/' not in text: return text
    all_cats = set(_classify(text, dp))
    if len(all_cats) <= 1: return text
    for i, c in enumerate(text):
        if c != '/': continue
        left, right = text[:i].strip(), text[i+1:].strip()
        if not left or not right: continue
        lc, rc = set(_classify(left, dp)), set(_classify(right, dp))
        if lc and rc and lc == rc:
            left_cjk = bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', left))
            right_cjk = bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', right))
            if left_cjk != right_cjk:
                return left if len(left) >= len(right) else right
    return text


# ── 5. Signal extraction ────────────────────────────────────────────────────
def extract_signals(text, ac, an):
    tu = text.upper()
    comps = [c for c in ac if re.search(r'\b' + re.escape(c) + r'\b', tu)]
    nets = [n for n in an if re.search(r'\b' + re.escape(n) + r'\b', tu)]
    # Detect suffixed references: if text has XXXX_YYY where XXXX is a known
    # component, extract it (handles common naming conventions)
    for c in ac:
        pat = re.compile(r'\b' + re.escape(c) + r'_\w+\b')
        if pat.search(tu) and c not in comps:
            comps.append(c)
    return list(set(comps)), list(set(nets))

def get_ti_signals(ti, ac, an):
    if not ti or str(ti) == 'nan': return [], []
    t = str(ti).strip().upper()
    # Try the full test_item as a component or net
    comps, nets = [], []
    if t in ac: comps.append(t)
    if t in an: nets.append(t)
    # Try stripping common suffixes to find base component
    base = re.sub(r'_[A-Z]+$', '', t)
    if base != t:
        if base in ac and base not in comps: comps.append(base)
        if base in an and base not in nets: nets.append(base)
    return comps, nets


# ── 6. Matching ─────────────────────────────────────────────────────────────
def match_segment(cat, pid, sta, ti, tc, tn, text, ci, n2c, ac, an, csc, cfg):
    if pid not in ci: return None, 0, ""
    groups = ci[pid].get(cat, [])
    if not groups: return None, 0, ""
    tic, tin = get_ti_signals(ti, ac, an)
    dc = set(tc + tic)
    for n in tn + tin:
        if pid in n2c and n in n2c[pid]: dc.update(n2c[pid][n])
    an_set = set(tn + tin)
    isc = cat in csc
    best, bs, br = None, -1, ""
    for g in groups:
        gc, gn = g['component'], g['net']
        for entry in g['entries']:
            sc = cfg['score_base']
            parts = [f"cat={cat}"]
            if sta in entry['stations']:
                sc += cfg['score_station']; parts.append(f"station {sta} in scope")
            else:
                sc += cfg['score_station_miss']
            if gc:
                if gc in tc: sc += cfg['score_comp_text']; parts.append(f"component {gc} in text")
                elif gc in tic: sc += cfg['score_comp_ti']; parts.append(f"component {gc} from test_item")
                elif gc in dc: sc += cfg['score_comp_derived']; parts.append(f"component {gc} derived")
                elif isc: sc += cfg['score_comp_penalty']
            if gn:
                if gn in tn: sc += cfg['score_net_text']; parts.append(f"signal {gn} in text")
                elif gn in tin: sc += cfg['score_net_ti']; parts.append(f"signal {gn} from test_item")
                elif gn in an_set: sc += cfg['score_net_derived']; parts.append(f"signal {gn} derived")
                elif isc: sc += cfg['score_net_penalty']
            tl = text.lower()
            kw = sum(1 for k in entry['keywords'] if k and k in tl)
            if kw > 0:
                sc += min(kw * cfg['score_kw_each'], cfg['score_kw_max'])
                parts.append(f"{kw} keywords")
            if sc > bs: bs = sc; best = entry; br = "; ".join(parts)
    return best, bs, br


# ── 7. Confidence ───────────────────────────────────────────────────────────
def compute_conf(score, rid, seg, cfg, is_unk=False):
    h = abs(hash(rid + seg)) % 10000
    jitter = (h / 10000.0 - 0.5) * cfg['conf_jitter']
    if is_unk:
        base = max(0.05, min(cfg['conf_unk_max'],
                             cfg['conf_unk_base'] + score * cfg['conf_unk_slope']))
        return round(max(0.02, min(cfg['conf_unk_max'] + 0.03, base + jitter * 0.5)), 4)
    norm = max(0, min(1, (score - 5) / 100.0))
    base = cfg['conf_min'] + norm * cfg['conf_range']
    return round(max(cfg['conf_min'] - 0.02, min(0.99, base + jitter)), 4)


# ── 8. Span finding ─────────────────────────────────────────────────────────
def find_span(seg, raw):
    s = seg.strip()
    if s in raw: return s
    for e in range(len(s), 2, -1):
        t = s[:e].strip()
        if t and t in raw: return t
    bl, bs2 = 0, raw.strip()[:50]
    for i in range(len(s)):
        for j in range(len(s), i+2, -1):
            t = s[i:j].strip()
            if t and t in raw and len(t) > bl: bl, bs2 = len(t), t; break
    return bs2


# ── 9. Column discovery ────────────────────────────────────────────────────
def _find_col(cols, cands):
    for c in cands:
        if c in cols: return c
    return None


# ── 10. End-to-end pipeline ─────────────────────────────────────────────────
def normalize_logs(data_dir, output_path, config=None):
    """End-to-end normalization pipeline.
    
    Parameters
    ----------
    data_dir : str
        Directory containing test_center_logs.csv and codebook_*.csv files.
    output_path : str
        Path to write the output JSON.
    config : dict, optional
        Override default policy parameters. See DEFAULT_CONFIG.
    """
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    
    cbs = load_codebooks(data_dir)
    ac, an = build_component_sets(cbs)
    ci, n2c, c2n = build_indices(cbs)
    csc = get_comp_specific_cats(cbs)
    dp = build_defect_patterns(cbs, cfg)
    akw = build_all_keywords(cbs, cfg)
    arkw = build_all_raw_keywords(cbs, cfg)
    
    df = pd.read_csv(os.path.join(data_dir, 'test_center_logs.csv'))
    cols = set(df.columns)
    rc = _find_col(cols, ['record_id','id'])
    pc = _find_col(cols, ['product_id','product'])
    sc = _find_col(cols, ['station','test_station'])
    ec = _find_col(cols, ['engineer_id','engineer'])
    tc = _find_col(cols, ['raw_reason_text','reason_text','defect_text'])
    tic = _find_col(cols, ['test_item','test_signal'])
    
    records = []
    for _, row in df.iterrows():
        rid = str(row[rc]); pid = str(row[pc]); sta = str(row[sc])
        raw = str(row[tc]); ti = str(row[tic]) if tic else ''
        so = _process(rid, pid, sta, ti, raw, cbs, ci, n2c, ac, an, dp, akw, arkw, csc, cfg)
        records.append(dict(
            record_id=row[rc], product_id=row[pc], station=row[sc],
            engineer_id=row[ec] if ec else '', raw_reason_text=row[tc],
            normalized=so))
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'records': records}, f, ensure_ascii=False, indent=2)
    return records


def _process(rid, pid, sta, ti, raw, cbs, ci, n2c, ac, an, dp, akw, arkw, csc, cfg):
    if pid not in cbs:
        return [dict(segment_id=f"{rid}-S1", span_text=raw[:80],
                     pred_code='UNKNOWN', pred_label='', confidence=0.10,
                     rationale=f'Product {pid} not in codebooks')]
    
    segs = segment_text(raw, dp, arkw, cfg)
    classified = []
    for st in segs:
        st = st.strip()
        if not st or len(st) <= 2: continue
        cats = _classify(st, dp)
        comps, nets = extract_signals(st, ac, an)
        classified.append((st, cats[0] if cats else 'UNKNOWN', comps, nets))
    
    deduped = []
    seen = set()
    for st, cat, comps, nets in classified:
        key = (cat, tuple(sorted(comps)), tuple(sorted(nets)))
        if key not in seen: seen.add(key); deduped.append((st, cat, comps, nets))
    
    results = []
    si = 1
    for st, cat, comps, nets in deduped:
        if cat == 'UNKNOWN':
            span = find_span(st, raw)
            conf = compute_conf(0, rid, st, cfg, is_unk=True)
            results.append(dict(segment_id=f"{rid}-S{si}", span_text=span,
                               pred_code='UNKNOWN', pred_label='', confidence=conf,
                               rationale='No codebook category matched'))
            si += 1; continue
        
        bm, bs, br = match_segment(cat, pid, sta, ti, comps, nets, st, ci, n2c, ac, an, csc, cfg)
        for alt in _classify(st, dp):
            if alt == cat: continue
            am, asc, ar = match_segment(alt, pid, sta, ti, comps, nets, st, ci, n2c, ac, an, csc, cfg)
            if am and asc > bs: bm, bs, br = am, asc, ar
        
        if bm is None or bs < cfg['unknown_threshold']:
            span = find_span(st, raw)
            conf = compute_conf(bs or 0, rid, st, cfg, is_unk=True)
            results.append(dict(segment_id=f"{rid}-S{si}", span_text=span,
                               pred_code='UNKNOWN', pred_label='', confidence=conf,
                               rationale=f'Low match: {br}'))
            si += 1; continue
        
        conf = compute_conf(bs, rid, st, cfg)
        span = find_span(st, raw)
        results.append(dict(segment_id=f"{rid}-S{si}", span_text=span,
                           pred_code=bm['code'], pred_label=bm['label'],
                           confidence=conf, rationale=br))
        si += 1
    
    if not results:
        results.append(dict(segment_id=f"{rid}-S1", span_text=raw.strip()[:80],
                           pred_code='UNKNOWN', pred_label='', confidence=0.10,
                           rationale='No defect pattern identified'))
    return results
