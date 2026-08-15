import pandas as pd
from rapidfuzz import fuzz, process

def load_coverpage(quarter_dir):
    """Load COVERPAGE.tsv from a quarter directory."""
    return pd.read_csv(f"{quarter_dir}/COVERPAGE.tsv", sep='\t', dtype=str)

def load_infotable(quarter_dir):
    """Load INFOTABLE.tsv from a quarter directory."""
    return pd.read_csv(f"{quarter_dir}/INFOTABLE.tsv", sep='\t', 
                       dtype={'ACCESSION_NUMBER': str, 'CUSIP': str, 'NAMEOFISSUER': str,
                              'TITLEOFCLASS': str, 'PUTCALL': str, 'SSHPRNAMTTYPE': str,
                              'INVESTMENTDISCRETION': str, 'OTHERMANAGER': str},
                       low_memory=False)

def fuzzy_search_coverpage(coverpage_df, search_term, top_n=5):
    """
    Fuzzy search COVERPAGE FILINGMANAGER_NAME for a search term.
    Returns list of (name, accession_number, score) tuples sorted by score desc.
    """
    names = coverpage_df['FILINGMANAGER_NAME'].dropna().unique().tolist()
    # Normalize for matching
    results = process.extract(
        search_term.lower(), 
        [n.lower() for n in names], 
        scorer=fuzz.token_sort_ratio,
        limit=top_n
    )
    # Map back to original names
    name_lower_to_orig = {}
    for n in names:
        nl = n.lower()
        if nl not in name_lower_to_orig:
            name_lower_to_orig[nl] = n
    
    output = []
    for matched_lower, score, idx in results:
        orig_name = name_lower_to_orig.get(matched_lower, matched_lower)
        # Get accession number for this name
        acc = coverpage_df[coverpage_df['FILINGMANAGER_NAME'].str.lower() == matched_lower]['ACCESSION_NUMBER'].iloc[0]
        output.append((orig_name, acc, score))
    return output

def get_accession_number(coverpage_df, search_term, infotable_df=None):
    """
    Find the best matching fund manager and return (name, accession_number).
    Uses fuzzy matching on FILINGMANAGER_NAME.
    
    When multiple filings exist for the same manager name (e.g., main portfolio
    vs subsidiary filing), selects the filing with the most holdings by 
    cross-referencing INFOTABLE row counts. This ensures we get the main 
    portfolio, not a subsidiary with only a few holdings.
    
    Args:
        coverpage_df: COVERPAGE DataFrame
        search_term: Fund manager name to search for
        infotable_df: Optional INFOTABLE DataFrame for disambiguating multiple filings
    """
    results = fuzzy_search_coverpage(coverpage_df, search_term, top_n=1)
    if not results:
        return None, None
    
    best_name = results[0][0]
    best_name_lower = best_name.lower()
    
    # Get ALL accession numbers for this manager name
    matching_rows = coverpage_df[coverpage_df['FILINGMANAGER_NAME'].str.lower() == best_name_lower]
    accession_numbers = matching_rows['ACCESSION_NUMBER'].unique().tolist()
    
    if len(accession_numbers) == 1:
        return best_name, accession_numbers[0]
    
    # Multiple filings exist - pick the one with the most holdings
    if infotable_df is not None:
        best_acc = None
        best_count = -1
        for acc in accession_numbers:
            count = len(infotable_df[infotable_df['ACCESSION_NUMBER'] == acc])
            if count > best_count:
                best_count = count
                best_acc = acc
        print(f"  Multiple filings found for '{best_name}': {len(accession_numbers)} filings")
        for acc in accession_numbers:
            count = len(infotable_df[infotable_df['ACCESSION_NUMBER'] == acc])
            marker = ' <-- SELECTED' if acc == best_acc else ''
            print(f"    {acc}: {count} holdings{marker}")
        return best_name, best_acc
    else:
        # Without infotable, return the first one (fallback)
        print(f"  WARNING: Multiple filings for '{best_name}', returning first. Pass infotable_df for better selection.")
        return best_name, accession_numbers[0]

def get_fund_aum(infotable_df, accession_number):
    """
    Calculate total AUM for a fund by summing VALUE column.
    VALUE is in dollars for filings from 2023 onward.
    """
    holdings = infotable_df[infotable_df['ACCESSION_NUMBER'] == accession_number].copy()
    holdings['VALUE'] = pd.to_numeric(holdings['VALUE'], errors='coerce')
    return holdings['VALUE'].sum()

def get_holdings(infotable_df, accession_number):
    """
    Get all holdings for a given accession number.
    Returns DataFrame with numeric VALUE and SSHPRNAMT columns.
    """
    holdings = infotable_df[infotable_df['ACCESSION_NUMBER'] == accession_number].copy()
    holdings['VALUE'] = pd.to_numeric(holdings['VALUE'], errors='coerce')
    holdings['SSHPRNAMT'] = pd.to_numeric(holdings['SSHPRNAMT'], errors='coerce')
    return holdings

def count_stocks(infotable_df, accession_number):
    """
    Count the number of distinct stock positions held.
    Uses unique CUSIPs from the holdings for the given accession number.
    """
    holdings = get_holdings(infotable_df, accession_number)
    return holdings['CUSIP'].nunique()

def compare_holdings_across_quarters(infotable_q2, infotable_q3, acc_q2, acc_q3):
    """
    Compare holdings between Q2 and Q3 for a fund.
    Aggregates by CUSIP before comparison (handles multiple rows per CUSIP).
    Uses outer join to capture new positions and exits.
    Returns DataFrame with CUSIP, VALUE_Q2, VALUE_Q3, VALUE_CHANGE
    sorted by VALUE_CHANGE descending.
    """
    h_q2 = get_holdings(infotable_q2, acc_q2)
    h_q3 = get_holdings(infotable_q3, acc_q3)
    
    # Aggregate by CUSIP (sum VALUE)
    agg_q2 = h_q2.groupby('CUSIP').agg({'VALUE': 'sum', 'NAMEOFISSUER': 'first'}).reset_index()
    agg_q2.columns = ['CUSIP', 'VALUE_Q2', 'NAMEOFISSUER_Q2']
    
    agg_q3 = h_q3.groupby('CUSIP').agg({'VALUE': 'sum', 'NAMEOFISSUER': 'first'}).reset_index()
    agg_q3.columns = ['CUSIP', 'VALUE_Q3', 'NAMEOFISSUER_Q3']
    
    # Outer merge
    merged = pd.merge(agg_q2[['CUSIP', 'VALUE_Q2']], agg_q3[['CUSIP', 'VALUE_Q3', 'NAMEOFISSUER_Q3']], 
                      on='CUSIP', how='outer')
    merged['VALUE_Q2'] = merged['VALUE_Q2'].fillna(0)
    merged['VALUE_Q3'] = merged['VALUE_Q3'].fillna(0)
    merged['VALUE_CHANGE'] = merged['VALUE_Q3'] - merged['VALUE_Q2']
    merged['NAMEOFISSUER'] = merged.get('NAMEOFISSUER_Q3', '')
    
    return merged.sort_values('VALUE_CHANGE', ascending=False)

def find_cusip_by_issuer(infotable_df, issuer_name):
    """
    Search INFOTABLE for a security by issuer name (fuzzy).
    Returns list of (CUSIP, NAMEOFISSUER, count, score) tuples.
    """
    unique_issuers = infotable_df[['CUSIP', 'NAMEOFISSUER']].drop_duplicates()
    names = unique_issuers['NAMEOFISSUER'].dropna().unique().tolist()
    
    results = process.extract(
        issuer_name.lower(),
        [n.lower() for n in names],
        scorer=fuzz.token_sort_ratio,
        limit=10
    )
    
    name_lower_to_orig = {}
    for n in names:
        nl = n.lower()
        if nl not in name_lower_to_orig:
            name_lower_to_orig[nl] = n
    
    output = []
    for matched_lower, score, idx in results:
        orig_name = name_lower_to_orig.get(matched_lower, matched_lower)
        cusips = unique_issuers[unique_issuers['NAMEOFISSUER'].str.lower() == matched_lower]['CUSIP'].unique()
        for c in cusips:
            count = len(infotable_df[infotable_df['CUSIP'] == c])
            output.append((c, orig_name, count, score))
    return output

def top_holders_by_cusip(infotable_df, coverpage_df, cusip, top_n=10):
    """
    Find top fund managers holding a specific CUSIP, ranked by VALUE.
    Returns DataFrame with FILINGMANAGER_NAME and total VALUE.
    """
    holdings = infotable_df[infotable_df['CUSIP'] == cusip].copy()
    holdings['VALUE'] = pd.to_numeric(holdings['VALUE'], errors='coerce')
    
    # Aggregate by accession number
    agg = holdings.groupby('ACCESSION_NUMBER')['VALUE'].sum().reset_index()
    agg.columns = ['ACCESSION_NUMBER', 'TOTAL_VALUE']
    
    # Join with coverpage to get manager names
    merged = agg.merge(coverpage_df[['ACCESSION_NUMBER', 'FILINGMANAGER_NAME']], 
                       on='ACCESSION_NUMBER', how='left')
    
    return merged.sort_values('TOTAL_VALUE', ascending=False).head(top_n)


def run_13f_analysis(q2_dir, q3_dir, output_path):
    """
    End-to-end entry point for SEC 13F analysis.
    Answers 4 questions about hedge fund activities comparing Q2 and Q3.
    
    Args:
        q2_dir: Path to Q2 data directory containing COVERPAGE.tsv and INFOTABLE.tsv
        q3_dir: Path to Q3 data directory containing COVERPAGE.tsv and INFOTABLE.tsv
        output_path: Path to write answers.json
    
    Returns:
        dict with q1_answer, q2_answer, q3_answer, q4_answer
    """
    import json
    
    # Load Q3 data
    print("Loading Q3 COVERPAGE...")
    coverpage_q3 = load_coverpage(q3_dir)
    print(f"Q3 coverpage rows: {len(coverpage_q3)}")
    
    print("Loading Q3 INFOTABLE...")
    infotable_q3 = load_infotable(q3_dir)
    print(f"Q3 infotable rows: {len(infotable_q3)}")
    
    # Q1: AUM of Renaissance Technologies in Q3
    print("\n=== Q1: Renaissance Technologies AUM ===")
    ren_name, ren_acc = get_accession_number(coverpage_q3, 'renaissance technologies', infotable_q3)
    print(f"Found: {ren_name} | {ren_acc}")
    aum = get_fund_aum(infotable_q3, ren_acc)
    print(f"AUM: {aum}")
    
    # Q2: Number of stocks held by Renaissance
    print("\n=== Q2: Number of stocks held by Renaissance ===")
    num_stocks = count_stocks(infotable_q3, ren_acc)
    print(f"Unique CUSIPs: {num_stocks}")
    
    # Q3: Top 5 stocks with increased investment by Berkshire Hathaway
    print("\n=== Q3: Top 5 increased investments by Berkshire Hathaway ===")
    print("Loading Q2 data...")
    coverpage_q2 = load_coverpage(q2_dir)
    infotable_q2 = load_infotable(q2_dir)
    print(f"Q2 coverpage rows: {len(coverpage_q2)}, infotable rows: {len(infotable_q2)}")
    
    bh_name_q2, bh_acc_q2 = get_accession_number(coverpage_q2, 'berkshire hathaway', infotable_q2)
    print(f"Q2 Berkshire: {bh_name_q2} | {bh_acc_q2}")
    
    bh_name_q3, bh_acc_q3 = get_accession_number(coverpage_q3, 'berkshire hathaway', infotable_q3)
    print(f"Q3 Berkshire: {bh_name_q3} | {bh_acc_q3}")
    
    changes = compare_holdings_across_quarters(infotable_q2, infotable_q3, bh_acc_q2, bh_acc_q3)
    top5 = changes.head(5)
    print("Top 5 increased investments:")
    print(top5[['CUSIP', 'VALUE_Q2', 'VALUE_Q3', 'VALUE_CHANGE']].to_string())
    q3_answer = top5['CUSIP'].tolist()
    
    # Q4: Top 3 fund managers holding Palantir by share value in Q3
    print("\n=== Q4: Top 3 Palantir holders ===")
    palantir_results = find_cusip_by_issuer(infotable_q3, 'Palantir')
    if palantir_results:
        palantir_cusip = palantir_results[0][0]
        print(f"Palantir CUSIP: {palantir_cusip}")
        top_holders = top_holders_by_cusip(infotable_q3, coverpage_q3, palantir_cusip, top_n=3)
        print(top_holders[['FILINGMANAGER_NAME', 'TOTAL_VALUE']].to_string())
        q4_answer = top_holders['FILINGMANAGER_NAME'].tolist()
    else:
        q4_answer = []
        print("WARNING: Palantir not found")
    
    answers = {
        "q1_answer": int(aum),
        "q2_answer": int(num_stocks),
        "q3_answer": q3_answer,
        "q4_answer": q4_answer
    }
    
    with open(output_path, 'w') as f:
        json.dump(answers, f, indent=2)
    print(f"\nAnswers written to {output_path}")
    print(json.dumps(answers, indent=2))
    
    return answers


def validate_answers(output_path):
    """
    Validate the answers.json file for structural correctness.
    
    Args:
        output_path: Path to answers.json
    
    Returns:
        True if valid, raises AssertionError otherwise
    """
    import json
    
    with open(output_path, 'r') as f:
        answers = json.load(f)
    
    # Check all keys present
    required_keys = ['q1_answer', 'q2_answer', 'q3_answer', 'q4_answer']
    for key in required_keys:
        assert key in answers, f"Missing key: {key}"
    
    # Q1: AUM should be a positive number
    assert isinstance(answers['q1_answer'], (int, float)), "q1_answer must be a number"
    assert answers['q1_answer'] > 0, "q1_answer (AUM) must be positive"
    assert answers['q1_answer'] > 1e9, "q1_answer (AUM) seems too small for Renaissance Technologies"
    
    # Q2: Stock count should be a positive integer
    assert isinstance(answers['q2_answer'], int), "q2_answer must be an integer"
    assert answers['q2_answer'] > 0, "q2_answer (stock count) must be positive"
    
    # Q3: Should be a list of 5 CUSIPs
    assert isinstance(answers['q3_answer'], list), "q3_answer must be a list"
    assert len(answers['q3_answer']) == 5, f"q3_answer must have 5 CUSIPs, got {len(answers['q3_answer'])}"
    for cusip in answers['q3_answer']:
        assert isinstance(cusip, str), f"Each CUSIP must be a string, got {type(cusip)}"
        assert len(cusip) == 9, f"CUSIP must be 9 characters, got '{cusip}' ({len(cusip)} chars)"
    
    # Q4: Should be a list of 3 fund manager names
    assert isinstance(answers['q4_answer'], list), "q4_answer must be a list"
    assert len(answers['q4_answer']) == 3, f"q4_answer must have 3 names, got {len(answers['q4_answer'])}"
    for name in answers['q4_answer']:
        assert isinstance(name, str), f"Each fund manager name must be a string"
        assert len(name) > 0, "Fund manager name cannot be empty"
    
    print("All validations passed!")
    return True
