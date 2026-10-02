# QPBT-comparator

A thin wrapper for the quantum Pauli basis test formalization in
[Dengnifer/MIPStarRE-QPBT](https://github.com/Dengnifer/MIPStarRE-QPBT).
The immutable substantive revision is recorded in `lakefile.toml`,
`lake-manifest.json`, and `formalization.yaml`.

## Mathematical claims

All strategies in these statements are finite-dimensional tensor-product
strategies with a pure unit state. The field and its self-dual normal basis
are chosen once for each admissible field size. The parameter structures in
`Challenge.lean` state the positive-integer and divisibility conditions.
The four declarations are in the namespace `MIPStarRE.QPBT.Palomar`:

- `exists_spcc_value_one`: for every admissible Pauli-test parameter tuple,
  there is a symmetric, projective, consistent strategy whose measurements
  commute on supported question pairs and whose winning probability is one.
- `exists_ld_soundness`: universal constants `a ≥ 1` and `0 < b ≤ 1` work
  for every admissible low-degree parameter tuple and every projective
  strategy winning with probability at least `1 − ε`, for `ε > 0`.
  Alice and Bob have polynomial-valued measurements satisfying the three
  point/polynomial and polynomial/polynomial consistency estimates, each
  bounded by `a (dmk)^a (ε^b + q^(-b) + 2^(-bmd))`.
- `pauli_soundness`: universal constants `a ≥ 1` and `0 < b < 1` work for
  every admissible tuple, `ε ≥ 0`, and strategy winning with probability at
  least `1 − ε`. Local isometries extract the prescribed maximally entangled
  qudits and an auxiliary state. The state norm error and each player's
  squared Pauli-operator error sum are separately bounded by
  `a (md)^a (ε^b + q^(-b) + 2^(-bmd))`.
- `pauli_soundness_qubit`: the same conclusion in the qubit coordinates of
  the fixed self-dual basis, with the same error form and quantifier order.

These are the statements labelled `lem:pauli-completeness`,
`lem:ld-soundness`, `thm:pauli`, and `cor:pauli-binary` in
[MIP*=RE](https://arxiv.org/abs/2001.04383). The library proves exact
correspondences between its original statements and these compact versions.
The inherited zero-direction convention and alternative low-degree proof
route are documented in the substantive repository's paper-gap notes.
This wrapper does not claim a formalization of the whole MIP*=RE theorem.

## Independent statement and proof

`Challenge.lean` is one Mathlib-only module, with 989 physical lines and
51,979 bytes. It contains the full verifier, parameter and strategy definitions,
fixed-field contract, and error quantities. Its SHA-256 is
`acb66991fbdbc80a9c5d0a7e522f572ba604e6c88b2907f9c43a477438ebe6f8`.
It exceeds Palomar's preferred review size but meets its hard limits.

The only deliberate holes are the four theorem proofs and the value of
`MIPStarRE.QPBT.fixedFieldModel`. That definition's full type is compared;
its library implementation constructs the field and basis and is audited
transitively. It is not an extra assumption in the Solution.
`Solution.lean` imports the three proved compact-result modules.

`comparator.json` permits only `propext`, `Quot.sound`, and `Classical.choice`.
The GitHub Actions workflow calls the official Palomar full verification
workflow at `65f0154ed776cd26c224254aa57b379137f28b0d`, using the hosted
`palomar-standard-v1` profile, Comparator, NanoDa, and con-ron. A successful
run is evidence for its exact commit only; it is not registry acceptance.

## Provenance and local checks

Ruixuan Deng is the responsible owner. The development is AI-generated;
no human mathematical or code review beyond the owner's decisions is claimed.
Agent review and operator self-assessment are distinct from human approval.
See `formalization.yaml` for the source, credit, and automation disclosures.

The local checker validates the metadata schema, source sizes and headers,
immutable pins, and the supplied official report. Artifact authenticity must
also be checked against the matching GitHub Actions run.

```sh
python3 -m unittest discover -s tools/palomar/tests -v
python3 tools/palomar/check.py report \
  --substantive-repo /path/to/MIPStarRE-QPBT \
  --official-report /path/to/official-report.json \
  --output /path/to/final-mechanical.json
```

Final evidence and the exact submission SHA are recorded in the substantive
repository's `docs/palomar-submission.md`. The final report is stored there so
recording it does not change the wrapper commit it verifies. No submission has
been made.
