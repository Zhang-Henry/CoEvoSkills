import pdfplumber
import pubchempy as pcp
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from rdkit import RDLogger
import warnings
import time
import json
import os
import tempfile
import hashlib

warnings.filterwarnings("ignore")
RDLogger.logger().setLevel(RDLogger.ERROR)


def _get_cache_path(pdf_path: str) -> str:
    abs_path = os.path.abspath(pdf_path)
    path_hash = hashlib.md5(abs_path.encode()).hexdigest()[:12]
    cache_dir = os.path.join(tempfile.gettempdir(), 'mol_similarity_cache')
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f'smiles_{path_hash}.json')


def _load_cache(cache_path: str) -> dict:
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}


def _save_cache(cache: dict, cache_path: str):
    with open(cache_path, 'w') as f:
        json.dump(cache, f, indent=2)


def _extract_molecule_names_from_pdf(pdf_path: str) -> list:
    names = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                for line in text.strip().split('\n'):
                    line = line.strip()
                    if line:
                        names.append(line)
    return names


def _resolve_name_to_smiles(chemical_name: str, max_retries: int = 5) -> str:
    """Resolve chemical name to isomeric SMILES via PubChemPy."""
    for attempt in range(max_retries):
        try:
            compounds = pcp.get_compounds(chemical_name, 'name')
            if compounds:
                smiles = compounds[0].isomeric_smiles
                if smiles:
                    return smiles
            return None
        except Exception as e:
            err_str = str(e)
            if '503' in err_str or '502' in err_str or 'ServerBusy' in err_str or 'Too many' in err_str or 'Bad Gateway' in err_str:
                time.sleep((2 ** attempt) * 1.5)
                continue
            else:
                return None
    return None


def _build_smiles_lookup(molecule_names: list, cache_path: str,
                         request_delay: float = 0.6) -> dict:
    cache = _load_cache(cache_path)
    new_lookups = 0

    for name in molecule_names:
        if name not in cache:
            cache[name] = _resolve_name_to_smiles(name)
            new_lookups += 1
            if new_lookups % 3 == 0:
                time.sleep(request_delay)
                _save_cache(cache, cache_path)

    if new_lookups > 0:
        _save_cache(cache, cache_path)

    for retry_delay in [1.5, 2.0, 3.0]:
        failed = [n for n in molecule_names if cache.get(n) is None]
        if not failed:
            break
        time.sleep(2.0)
        for name in failed:
            time.sleep(retry_delay)
            smiles = _resolve_name_to_smiles(name)
            if smiles:
                cache[name] = smiles
        _save_cache(cache, cache_path)

    return cache


def _compute_morgan_fingerprint(smiles: str, radius: int = 2,
                                 use_chirality: bool = True):
    """Compute Morgan fingerprint (count-based) from SMILES."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return AllChem.GetMorganFingerprint(mol, radius=radius, useChirality=use_chirality)


def _compute_tanimoto(fp1, fp2) -> float:
    if fp1 is None or fp2 is None:
        return 0.0
    return DataStructs.TanimotoSimilarity(fp1, fp2)


def topk_tanimoto_similarity_molecules(
    target_molecule_name: str,
    molecule_pool_filepath: str,
    top_k: int
) -> list:
    """Find the top-k most similar molecules from a PDF pool to a target.

    Uses PubChemPy for name-to-SMILES, Morgan fingerprints (radius=2,
    useChirality=True), and Tanimoto similarity.
    Results sorted descending by similarity, alphabetical for ties.
    """
    pool_names = _extract_molecule_names_from_pdf(molecule_pool_filepath)

    all_names = list(set(pool_names + [target_molecule_name]))
    cache_path = _get_cache_path(molecule_pool_filepath)
    smiles_lookup = _build_smiles_lookup(all_names, cache_path)

    target_smiles = smiles_lookup.get(target_molecule_name)
    if target_smiles is None:
        time.sleep(2.0)
        target_smiles = _resolve_name_to_smiles(target_molecule_name)
    if target_smiles is None:
        raise ValueError(f"Could not resolve target molecule: {target_molecule_name}")

    target_fp = _compute_morgan_fingerprint(target_smiles)
    if target_fp is None:
        raise ValueError(f"Invalid SMILES for target: {target_molecule_name}")

    results = []
    for name in pool_names:
        pool_smiles = smiles_lookup.get(name)
        if pool_smiles is None:
            continue
        pool_fp = _compute_morgan_fingerprint(pool_smiles)
        if pool_fp is None:
            continue
        sim = _compute_tanimoto(target_fp, pool_fp)
        results.append((name, sim))

    results.sort(key=lambda x: (-x[1], x[0]))
    return [name for name, _sim in results[:top_k]]


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "Benzene"
    pdf = sys.argv[2] if len(sys.argv) > 2 else "pool.pdf"
    k = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    result = topk_tanimoto_similarity_molecules(target, pdf, k)
    print(result)
