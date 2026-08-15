"""Utility functions for Wyckoff position analysis of CIF files."""

import warnings
from fractions import Fraction
from typing import Any


def float_to_frac_str(val: float, max_denom: int = 12) -> str:
    """Convert a float to a rational string with denominator <= max_denom.
    
    Args:
        val: The floating point value to convert
        max_denom: Maximum denominator for the fraction
    
    Returns:
        String representation like '0', '1/2', '3/8', etc.
    """
    f = Fraction(val).limit_denominator(max_denom)
    if f.denominator == 1:
        return str(f.numerator)
    else:
        return f"{f.numerator}/{f.denominator}"


def coords_to_frac_strs(coords, max_denom: int = 12) -> list:
    """Convert a list/array of float coordinates to fraction strings.
    
    Args:
        coords: Array-like of 3 fractional coordinates
        max_denom: Maximum denominator for fractions
    
    Returns:
        List of 3 fraction strings
    """
    return [float_to_frac_str(c, max_denom) for c in coords]


def analyze_wyckoff_position_multiplicities_and_coordinates(
    filepath: str,
) -> dict[str, dict] | dict[str, Any]:
    """Analyze Wyckoff position multiplicities and calculate approximate
    coordinates for the first atom of each Wyckoff position.
    
    Uses pymatgen to parse the CIF file and spglib (via pymatgen's
    SpacegroupAnalyzer) to determine Wyckoff positions.
    
    Args:
        filepath: Path to a CIF file
    
    Returns:
        Dictionary with:
            - wyckoff_multiplicity_dict: {letter: count} for each Wyckoff letter
            - wyckoff_coordinates_dict: {letter: [x, y, z]} fraction strings
              for the first atom of each Wyckoff position
    """
    warnings.filterwarnings('ignore')
    
    import pymatgen.core as pmg
    from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
    
    # Parse the CIF file
    struct = pmg.Structure.from_file(filepath)
    
    # Get symmetry analysis
    sga = SpacegroupAnalyzer(struct)
    sym_dataset = sga.get_symmetry_dataset()
    wyckoff_letters = sym_dataset.wyckoffs
    
    # Group by Wyckoff letter:
    # - Sum multiplicities (count of atoms with that letter)
    # - Keep the first atom's original coordinates as representative
    wyckoff_mult = {}
    wyckoff_coords = {}
    
    for i, letter in enumerate(wyckoff_letters):
        if letter not in wyckoff_mult:
            wyckoff_mult[letter] = 0
            # Use original structure coordinates for the first atom
            coords = struct[i].frac_coords
            wyckoff_coords[letter] = coords_to_frac_strs(coords)
        wyckoff_mult[letter] += 1
    
    return {
        "wyckoff_multiplicity_dict": wyckoff_mult,
        "wyckoff_coordinates_dict": wyckoff_coords,
    }


def validate_result(result: dict, filepath: str) -> bool:
    """Validate a Wyckoff analysis result.
    
    Checks:
    - Required keys exist
    - All Wyckoff letters have both multiplicity and coordinates
    - Coordinates are lists of 3 fraction strings
    - Total atom count matches the structure
    
    Args:
        result: Output from analyze_wyckoff_position_multiplicities_and_coordinates
        filepath: Path to the original CIF file for cross-checking
    
    Returns:
        True if valid
    """
    warnings.filterwarnings('ignore')
    import pymatgen.core as pmg
    
    assert "wyckoff_multiplicity_dict" in result, "Missing wyckoff_multiplicity_dict"
    assert "wyckoff_coordinates_dict" in result, "Missing wyckoff_coordinates_dict"
    
    mult = result["wyckoff_multiplicity_dict"]
    coords = result["wyckoff_coordinates_dict"]
    
    # Same keys in both dicts
    assert set(mult.keys()) == set(coords.keys()), \
        f"Key mismatch: {set(mult.keys())} vs {set(coords.keys())}"
    
    # Check total matches structure
    struct = pmg.Structure.from_file(filepath)
    total = sum(mult.values())
    assert total == len(struct), \
        f"Total multiplicity {total} != structure sites {len(struct)}"
    
    # Check coordinate format
    for letter, coord_list in coords.items():
        assert len(coord_list) == 3, f"Wyckoff '{letter}' has {len(coord_list)} coords, expected 3"
        for c in coord_list:
            assert isinstance(c, str), f"Coordinate {c} is not a string"
            # Verify it's a valid fraction
            f = Fraction(c)
            assert f.denominator <= 12, f"Denominator {f.denominator} > 12 for {c}"
    
    print(f"Validation passed for {filepath}")
    return True
