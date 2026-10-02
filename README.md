# QPBT-comparator

Thin comparator wrapper for the Lean 4 formalization of the quantum Pauli
basis test in the canonical substantive repository
[Dengnifer/MIPStarRE-QPBT](https://github.com/Dengnifer/MIPStarRE-QPBT).

The comparator registers these four compact headline declarations, in order:

- `MIPStarRE.QPBT.Palomar.exists_spcc_value_one`;
- `MIPStarRE.QPBT.Palomar.exists_ld_soundness`;
- `MIPStarRE.QPBT.Palomar.pauli_soundness`; and
- `MIPStarRE.QPBT.Palomar.pauli_soundness_qubit`.

It also registers the definition frontier
`MIPStarRE.QPBT.fixedFieldModel` and permits only `propext`, `Quot.sound`, and
`Classical.choice`.

## What The Check Establishes

The official comparator exports the Challenge and Solution environments and
compares the registered declaration closures. A successful full run would
establish equality of the four theorem statements and the selector type, then
check the solution values transitively against the permitted axioms and the
configured independent kernels. This source-only draft has not completed that
run.

## Layout

`Challenge.lean` is the complete independent statement surface: one
Mathlib-only module, 992 physical lines and 52,483 UTF-8 bytes. Its audited
SHA-256 is
`4600b1c3e2409edf2a68df53a2055516c99646e42750f966cf02e60437700de3`.
The only intended holes are the fixed-field selector value and the four
registered theorem bodies.

`Solution.lean` is a thin module importing exactly
`MIPStarRE.QPBT.Palomar.PauliCompleteness`,
`MIPStarRE.QPBT.Palomar.LowDegreeSoundness`, and
`MIPStarRE.QPBT.Palomar.PauliSoundness`. `QPBTComparator.lean` only re-exports
that solution module. No generated helper Lean files remain in this wrapper.

## Official Caller

`.github/workflows/comparator.yml` is the pinned native caller for
`PalomarRegistry/PalomarSubmission` revision
`65f0154ed776cd26c224254aa57b379137f28b0d`. It requests full mode with the
hosted `palomar-standard-v1` execution profile and binds both the reusable
workflow and pipeline revision to that commit. There is no local substitute
verifier; the authenticated workflow artifact is required for final evidence.

## Preparation Checks

The non-executing checker validates the metadata schema, repository layout,
module headers, size limits, immutable pins, Challenge import spelling, and the
shape of a supplied official report:

```sh
python3 -m unittest discover -s tools/palomar/tests -v
python3 tools/palomar/check.py report \
  --substantive-repo /path/to/MIPStarRE-QPBT \
  --output reports/palomar-mechanical.json
```

The report is intentionally red or unknown where runtime evidence is absent.
Static checks do not prove statement equality, proof completion, axiom closure,
resolved transitive import origins, or registry acceptance.

## Pending Integration

The Lake files still carry the historical MIPStarRE-A pin
`ecb97d1f66eec1e6fad964f144f78b91ce1fab36` and Lean/Mathlib v4.32.0. That
revision does not contain the compact solution modules, and v4.32.0 is below
the v4.35.0-rc2 minimum recorded by the pinned policy. The regenerated report
also measures that historical substantive tree at 1,809,506,272 bytes, above
the 500 MiB cap, and records its source-module requirements as failing. The
dependency URL, final main-reachable library revision, final supported-version
manifest, completed module migration, native comparator run, authenticated
runtime artifact, and independent exact-head review all remain pending. They
must move together; this draft is not ready for submission.
