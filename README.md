# QPBT-comparator

Comparator challenge for the Lean 4 formalization of the quantum Pauli basis
test in [Dengnifer/MIPStarRE-A](https://github.com/Dengnifer/MIPStarRE-A).

The single comparator run checks these four registered headline declarations:

- `MIPStarRE.QPBT.exists_spcc_value_one`;
- `MIPStarRE.QPBT.exists_ld_soundness`;
- `MIPStarRE.QPBT.pauli_soundness`; and
- `MIPStarRE.QPBT.pauli_soundness_qubit`.

## What The Check Establishes

The official [Lean comparator](https://github.com/leanprover/comparator)
exports the challenge and solution environments and compares the complete
statement closure declaration by declaration. A successful run establishes
that the library proves exactly the four challenge statements, that every
constant in their statement closures agrees, and that the proofs use no axioms
beyond `propext`, `Quot.sound`, and `Classical.choice`. The workflow also
replays the environment through Lean's kernel, `lean4checker`, and the
independent nanoda kernel.

## Layout

`Challenge.lean` imports 30 generated modules below `Challenge/`, one for each
contributing library module. Those 31 files import only Mathlib and other
generated challenge modules. Mirroring the library module partition is
necessary because compiler-generated auxiliary names and instance visibility
are module-sensitive.

`Solution.lean` imports the four library theorem modules. `comparator.json`
names the four targets and the three permitted axioms. `lakefile.toml` and
`lake-manifest.json` pin the exact library revision used to generate the
challenge.

## Verification

On Linux with Landlock, Go, a current Rust toolchain, `jq`, and `elan`, run:

```sh
./verify.sh
```

This invokes the unchanged official comparator with real landrun and nanoda.
For diagnostics only, `./verify.sh --fake-landrun` substitutes the comparator's
development sandbox and disables nanoda; that mode is not official acceptance.

The authoritative GitHub workflow checks the Mathlib-only import boundary,
the full revision pin, Lean compilation and kernel replay, then runs the real
landrun/nanoda comparison.

## Source Pin

This candidate pins MIPStarRE-A commit
`8bd40f9f77d27815f65d85e81a6570146657173a`, the exact PR 663 head from which
the checked-in 31-file challenge was generated. Until that source commit is
service-merged into `main`, results on this branch are preliminary evidence;
the final artifact must be regenerated or repinned to the actual merged-main
commit and verified again.

## Regeneration

From the pinned MIPStarRE-A checkout, run:

```sh
python3 scripts/comparator/check_challenge_drift.py \
  --root . --challenge qpbt --update
```

Then replace this repository's `Challenge.lean` and `Challenge/` with the
contents of `scripts/comparator/expected/qpbt/`, and update the MIPStarRE
revision in both Lake files in the same commit.
