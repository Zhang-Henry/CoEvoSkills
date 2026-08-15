---
name: evo-sec-13f-analysis
description: "Analyze SEC Form 13F filings from EDGAR bulk data: fuzzy search fund managers, calculate AUM, count stock positions, compare holdings across quarters, and find top holders of specific securities."
---

# SEC 13F Filings Analysis Skill

## Overview
Analyze SEC Form 13F filings from EDGAR bulk data. Supports fuzzy searching for fund managers, calculating AUM, counting stock positions, comparing holdings across quarters, and finding top holders of specific securities.

## Data Structure
- COVERPAGE.tsv: Filing-level index with FILINGMANAGER_NAME and ACCESSION_NUMBER
- INFOTABLE.tsv: Individual security holdings with CUSIP, VALUE (in dollars for 2023+), SSHPRNAMT
- Tables joined by ACCESSION_NUMBER

## Key Rules
- VALUE column is in dollars for filings from 2023 onward
- ACCESSION_NUMBER changes every quarter - must look up independently per quarter
- Fuzzy matching needed for FILINGMANAGER_NAME (case-insensitive)
- Aggregate by CUSIP before cross-quarter comparison
- Use outer join for complete position change analysis
- Count stocks by unique CUSIPs

## Quick Start — End-to-End Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-sec-13f-analysis/scripts')
from utils import run_13f_analysis, validate_answers

# Run the full analysis: discovers funds, computes AUM, compares quarters,
# finds top holders, and writes answers.json
answers = run_13f_analysis(
    q2_dir='/root/2025-q2',
    q3_dir='/root/2025-q3',
    output_path='/root/answers.json'
)

# Validate the output
validate_answers('/root/answers.json')
```

## Individual Utility Functions

For custom analysis, you can import individual functions:

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-sec-13f-analysis/scripts')
from utils import (
    load_coverpage, load_infotable, fuzzy_search_coverpage,
    get_accession_number, get_fund_aum, get_holdings, count_stocks,
    compare_holdings_across_quarters, find_cusip_by_issuer, top_holders_by_cusip
)

# Load data
coverpage = load_coverpage('/root/2025-q3')
infotable = load_infotable('/root/2025-q3')

# Find a fund manager (fuzzy match)
name, acc = get_accession_number(coverpage, 'renaissance technologies', infotable)

# Get AUM
aum = get_fund_aum(infotable, acc)

# Count stocks
num_stocks = count_stocks(infotable, acc)
```

## Function Reference

### Data Loading
- `load_coverpage(quarter_dir)` — Load COVERPAGE.tsv from a quarter directory
- `load_infotable(quarter_dir)` — Load INFOTABLE.tsv from a quarter directory

### Fund Search
- `fuzzy_search_coverpage(coverpage_df, search_term, top_n=5)` — Fuzzy search FILINGMANAGER_NAME, returns list of (name, accession_number, score)
- `get_accession_number(coverpage_df, search_term, infotable_df=None)` — Find best matching fund and return (name, accession_number). When multiple filings exist, uses infotable_df to pick the one with most holdings.

### Holdings Analysis
- `get_fund_aum(infotable_df, accession_number)` — Sum VALUE column for a fund's AUM
- `get_holdings(infotable_df, accession_number)` — Get all holdings with numeric columns
- `count_stocks(infotable_df, accession_number)` — Count unique CUSIPs held

### Cross-Quarter Comparison
- `compare_holdings_across_quarters(infotable_q2, infotable_q3, acc_q2, acc_q3)` — Compare holdings between quarters, returns DataFrame sorted by VALUE_CHANGE descending

### Security Search
- `find_cusip_by_issuer(infotable_df, issuer_name)` — Fuzzy search for a security by issuer name, returns list of (CUSIP, name, count, score)
- `top_holders_by_cusip(infotable_df, coverpage_df, cusip, top_n=10)` — Find top fund managers holding a CUSIP, ranked by VALUE

### Orchestration
- `run_13f_analysis(q2_dir, q3_dir, output_path)` — End-to-end entry point that answers all 4 questions and writes answers.json
- `validate_answers(output_path)` — Validate answers.json structure and sanity checks
