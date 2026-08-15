import bibtexparser
import requests
import json
import re
import time

def parse_bib_file(bib_path):
    """Parse a BibTeX file and return list of entries."""
    with open(bib_path, 'r') as f:
        bib_db = bibtexparser.load(f)
    return bib_db.entries

def clean_bibtex_title(title):
    """Remove BibTeX formatting from title (curly braces, LaTeX commands)."""
    title = title.replace('{', '').replace('}', '')
    title = re.sub(r'\\[a-zA-Z]+', '', title)
    title = ' '.join(title.split())
    return title.strip()

def check_doi_crossref(doi, timeout=15):
    """Check if a DOI resolves via CrossRef API. Returns (status_code, metadata_dict or None)."""
    if not doi:
        return None, None
    try:
        resp = requests.get(
            f'https://api.crossref.org/works/{doi}',
            timeout=timeout,
            headers={'User-Agent': 'CitationVerifier/1.0 (mailto:verify@example.com)'}
        )
        if resp.status_code == 200:
            data = resp.json()
            msg = data.get('message', {})
            return 200, {
                'title': msg.get('title', [''])[0],
                'DOI': msg.get('DOI', ''),
                'publisher': msg.get('publisher', ''),
            }
        return resp.status_code, None
    except Exception as e:
        return None, {'error': str(e)}

def check_doi_resolution(doi, timeout=15):
    """Check if a DOI resolves via doi.org (HTTP HEAD). Returns status code."""
    if not doi:
        return None
    try:
        resp = requests.head(f'https://doi.org/{doi}', timeout=timeout, allow_redirects=False)
        return resp.status_code
    except Exception:
        return None

def search_semantic_scholar(title, limit=3, timeout=15):
    """Search Semantic Scholar by title. Returns list of results or empty list."""
    url = 'https://api.semanticscholar.org/graph/v1/paper/search'
    params = {'query': title, 'limit': limit, 'fields': 'title,authors,year,venue,externalIds'}
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code == 200:
            return resp.json().get('data', [])
        return []
    except Exception:
        return []

def has_dblp_provenance(entry):
    """Check if entry has DBLP biburl/bibsource provenance."""
    biburl = entry.get('biburl', '')
    bibsource = entry.get('bibsource', '')
    return 'dblp' in biburl.lower() or 'dblp' in bibsource.lower()

def has_acl_anthology_url(entry):
    """Check if entry has ACL Anthology URL."""
    url = entry.get('url', '')
    return 'aclanthology.org' in url

def is_suspicious_doi_prefix(doi):
    """Check if DOI has a suspicious/placeholder registrant code."""
    if not doi:
        return False
    known_prefixes = [
        '10.1038', '10.1126', '10.1109', '10.18653', '10.1145',
        '10.1007', '10.1016', '10.1371', '10.1073', '10.1162',
        '10.1093', '10.1080', '10.1177', '10.1002', '10.1103',
        '10.1021', '10.1186', '10.1111', '10.1017', '10.3390',
        '10.48550', '10.1257', '10.1146', '10.1515',
    ]
    # Extract registrant code
    match = re.match(r'(10\.\d+)/', doi)
    if not match:
        return True  # malformed DOI
    prefix = match.group(1)
    # Check for obviously fake prefixes like 10.1234, 10.5678
    if prefix in ['10.1234', '10.5678', '10.0000', '10.9999']:
        return True
    return False

def analyze_entry_suspicion(entry):
    """Analyze a single BibTeX entry for signs of fabrication.
    Returns a dict with signals and overall suspicion score."""
    signals = {}
    score = 0
    
    doi = entry.get('doi', None)
    title = entry.get('title', '')
    
    # DBLP provenance = strong real signal
    if has_dblp_provenance(entry):
        signals['dblp_provenance'] = True
        score -= 5
    
    # ACL Anthology URL = strong real signal
    if has_acl_anthology_url(entry):
        signals['acl_anthology'] = True
        score -= 3
    
    # Suspicious DOI prefix
    if doi and is_suspicious_doi_prefix(doi):
        signals['suspicious_doi_prefix'] = True
        score += 3
    
    # No DOI for article/inproceedings (modern papers should have DOIs)
    entry_type = entry.get('ENTRYTYPE', '')
    year = int(entry.get('year', '0') or '0')
    if not doi and entry_type in ('article', 'inproceedings') and year >= 2015:
        signals['no_doi_modern'] = True
        score += 1
    
    # Generic title patterns
    clean_title = clean_bibtex_title(title)
    generic_patterns = [
        r'^(A |An )?Comprehensive (Review|Survey|Study)',
        r'^Advances in .+ for .+$',
        r'^(A |An )?(Review|Survey|Study) of .+$',
    ]
    for pat in generic_patterns:
        if re.search(pat, clean_title, re.IGNORECASE):
            signals['generic_title'] = True
            score += 1
            break
    
    return {'signals': signals, 'score': score}

def verify_citations(bib_path, output_path, delay=0.5):
    """Main entry point: parse BibTeX, verify all citations, write answer.json.
    
    Strategy:
    1. DOI-first triage via CrossRef API
    2. doi.org resolution for failed DOIs
    3. Check DBLP provenance and ACL Anthology URLs
    4. Analyze suspicion signals
    5. Try Semantic Scholar for borderline cases
    """
    entries = parse_bib_file(bib_path)
    results = []
    
    for entry in entries:
        eid = entry.get('ID', 'unknown')
        title = entry.get('title', '')
        doi = entry.get('doi', None)
        clean_title = clean_bibtex_title(title)
        
        info = {
            'id': eid,
            'title': clean_title,
            'doi': doi,
            'verified_real': False,
            'confirmed_fake': False,
        }
        
        # Check DBLP/ACL provenance first
        if has_dblp_provenance(entry) or has_acl_anthology_url(entry):
            info['verified_real'] = True
            info['reason'] = 'provenance'
            results.append(info)
            continue
        
        # DOI verification
        if doi:
            cr_status, cr_meta = check_doi_crossref(doi)
            time.sleep(delay)
            
            if cr_status == 200:
                info['verified_real'] = True
                info['reason'] = 'doi_crossref_ok'
            elif cr_status == 404:
                # Double check with doi.org
                doi_status = check_doi_resolution(doi)
                time.sleep(delay)
                if doi_status == 404:
                    info['confirmed_fake'] = True
                    info['reason'] = 'doi_not_found'
                elif doi_status and doi_status in (301, 302, 303):
                    info['verified_real'] = True
                    info['reason'] = 'doi_resolves'
                else:
                    info['confirmed_fake'] = True
                    info['reason'] = 'doi_crossref_404'
        
        # Analyze suspicion signals
        suspicion = analyze_entry_suspicion(entry)
        info['suspicion'] = suspicion
        
        # For entries without DOI and not yet verified
        if not info['verified_real'] and not info['confirmed_fake']:
            # Try Semantic Scholar
            s2_results = search_semantic_scholar(clean_title)
            time.sleep(2)  # respect rate limits
            
            if s2_results:
                # Check if any result closely matches
                for r in s2_results:
                    r_title = r.get('title', '').lower().strip()
                    if r_title == clean_title.lower().strip():
                        info['verified_real'] = True
                        info['reason'] = 'semantic_scholar_match'
                        break
            
            # If still unverified and high suspicion score
            if not info['verified_real'] and suspicion['score'] >= 1:
                # Check for venue/publisher inconsistencies
                info['confirmed_fake'] = True
                info['reason'] = 'multiple_red_flags'
        
        results.append(info)
    
    # Collect fake titles
    fake_titles = sorted([
        r['title'] for r in results if r['confirmed_fake']
    ])
    
    answer = {'fake_citations': fake_titles}
    
    with open(output_path, 'w') as f:
        json.dump(answer, f, indent=2)
    
    return answer, results

def validate_answer(output_path):
    """Validate the answer.json file."""
    with open(output_path, 'r') as f:
        answer = json.load(f)
    
    assert 'fake_citations' in answer, 'Missing fake_citations key'
    assert isinstance(answer['fake_citations'], list), 'fake_citations must be a list'
    
    # Check titles are clean (no BibTeX formatting)
    for title in answer['fake_citations']:
        assert '{' not in title, f'Title contains curly braces: {title}'
        assert '\\' not in title, f'Title contains backslash: {title}'
    
    # Check alphabetical sorting
    assert answer['fake_citations'] == sorted(answer['fake_citations']), 'Titles not sorted alphabetically'
    
    print(f"Validation passed. {len(answer['fake_citations'])} fake citations identified.")
    for t in answer['fake_citations']:
        print(f"  - {t}")
    
    return True
