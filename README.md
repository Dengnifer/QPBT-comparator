# QPBT-comparator

Comparator challenge for the Lean 4 formalization of the **quantum Pauli basis test**
(the Pauli basis test section of the MIP\* = RE paper), developed in
[Dengnifer/MIPStarRE-A](https://github.com/Dengnifer/MIPStarRE-A).

**Status: under construction.** This repository will hold

- `Challenge.lean` — imports only Mathlib and re-declares, verbatim and in dependency order, every
  declaration in the statement closure of the headline theorems (`MIPStarRE.QPBT.pauli_soundness`
  and its qubit form), then states the theorems with `sorry`. It is the entire human audit surface.
- `Solution.lean` — imports the MIPStarRE-A library, pinned by commit, which proves the same
  statements under the same fully qualified names.
- `comparator.json`, `verify.sh` and CI that run the official
  [leanprover/comparator](https://github.com/leanprover/comparator) with only the three standard
  axioms permitted (`propext`, `Classical.choice`, `Quot.sound`).

The design follows the challenge repository of the companion low individual degree test
formalization, [LionSR/LDT-comparator](https://github.com/LionSR/LDT-comparator), and the Lean
reference manual's *Validating Proofs* chapter. The regeneration tooling and the drift check live
in the library repository (`scripts/comparator/`, `docs/comparator.md`).
