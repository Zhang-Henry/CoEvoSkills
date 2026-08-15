# Molecular Similarity Foundations

Molecular similarity compares representations of chemical structure rather than
chemical names themselves. Names can be ambiguous or synonymous, while a
structure representation describes atoms, bonds, charge, and potentially
stereochemistry.

Molecular fingerprints encode selected structural features. Different
fingerprint families and settings emphasize different aspects of a molecule, so
a similarity value is meaningful only when the same representation policy is
used for every molecule being compared.

Tanimoto similarity is commonly applied to molecular fingerprints and is
bounded between zero and one. It is a representation-dependent structural
similarity measure, not a universal statement about chemical function, safety,
or biological activity.

Public chemistry databases and cheminformatics libraries can supply structure
records and standard representations. Their records have provenance and may
contain aliases, unresolved names, or multiple chemically distinct forms; those
possibilities should be treated as data-quality concerns rather than resolved by
a fixed name-to-structure table.
