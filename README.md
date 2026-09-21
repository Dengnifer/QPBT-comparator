# QPBT-comparator

Comparator challenge for the Lean 4 formalization of the **quantum Pauli basis test** —
the Pauli basis test section of the MIP\* = RE development — carried out in
[Dengnifer/MIPStarRE-A](https://github.com/Dengnifer/MIPStarRE-A).

The theorems verified here are

- `MIPStarRE.QPBT.pauli_soundness` (blueprint `thm:pauli`), and
- `MIPStarRE.QPBT.pauli_soundness_qubit` (blueprint `cor:pauli-binary`),

checked in a single comparator run.

## What the check establishes

The [comparator](https://github.com/leanprover/comparator) exports both environments with
`lean4export` and compares them declaration by declaration. A green run says three things
at once:

1. every declaration in the *statement closure* of the two theorems is identical in
   `Challenge.lean` — which imports Mathlib and nothing else — and in the library;
2. the library proves those statements, under the same fully qualified names;
3. the proofs use no axioms beyond `propext`, `Quot.sound` and `Classical.choice`, and
   replay through the Lean kernel and through the independent `nanoda` kernel.

So the entire human audit surface is `Challenge.lean`. A reader who agrees that it states
the intended theorems does not have to read the library, the solution, or this README.

## Layout

| File | What it is |
|---|---|
| `Challenge.lean` | Imports **only Mathlib**, re-declares verbatim and in dependency order every declaration in the statement closure of the two theorems, then states the theorems with `sorry`. Generated, not hand-edited; every declaration carries a `-- source:` provenance comment pointing into the library, where the docstrings cite the paper passages being encoded. |
| `Solution.lean` | Imports the library, pinned by commit in `lakefile.toml`. No bridging lemmas: the library proves the same statements under the same names, so importing it is the whole solution. |
| `QPBTComparator.lean` | Package root, imports `Solution`; it exists so external checkers can be pointed at one module. |
| `comparator.json` | The comparator configuration: both theorem names, and `propext`, `Quot.sound`, `Classical.choice` as the only permitted axioms. |
| `verify.sh` | Runs the official comparator with the real landrun sandbox and the nanoda external kernel. `--fake-landrun` drops the sandbox for hosts without Landlock. |
| `lakefile.toml`, `lake-manifest.json`, `lean-toolchain` | The build. Mathlib and every other dependency are pinned to exactly the revisions the library itself is pinned to, so the two environments cannot drift apart through a dependency. |
| `.github/workflows/comparator.yml` | The authoritative run: real sandbox, external kernel, `lean4checker` re-check, on every push and pull request and once a week. |

## Running the check

Linux with Landlock (kernel ≥ 5.13), plus Go, Rust, `jq` and `elan`:

```sh
./verify.sh
```

`verify.sh` fetches and builds the comparator, `landrun` and `nanoda` at pinned revisions
on first use, then runs the comparison. Expect a long first run: it builds the library.

On macOS, or on any host without Landlock, Go or a recent Rust:

```sh
./verify.sh --fake-landrun
```

This is a **functional check only**. It substitutes comparator's own development stub for
the sandbox — the stub prints `WARNING: THIS IS NOT REAL LANDRUN!` and runs the command
unsandboxed — and turns `enable_nanoda` off. The export comparison and the axiom whitelist
are unchanged, so on a trusted checkout the logical content of a passing run is the same;
what is dropped is the guarantee that a hostile `Solution.lean` cannot tamper with the
run. Treat the workflow in `.github/workflows/` as the authoritative result.

## Which library commit is pinned

`lakefile.toml` and `lake-manifest.json` pin `MIPStarRE` to one full commit hash, and the
CI refuses anything else. **The pin currently points at a commit on the development branch
`issue-645-qpbt-comparator-20260919` (pull request 661), not at `main`.** It will move to
the merged `main` commit once that pull request lands; the pin and `Challenge.lean` always
move together, because the challenge is generated from the library at that exact commit.

## Regenerating after a library change

`Challenge.lean` is generated. After any change to a declaration in the statement closure:

1. in the library repository, run
   `python3 scripts/comparator/check_challenge_drift.py --root . --challenge qpbt --update`;
2. copy `scripts/comparator/expected/ChallengeQPBT.lean.expected` here as `Challenge.lean`;
3. bump `rev` in `lakefile.toml` and the `MIPStarRE` entry of `lake-manifest.json` to the
   library commit it was generated from.

The library's own CI fails if the checked-in expected copy drifts from what the tooling
produces. The regeneration tooling and the trust model live in the library repository, in
`scripts/comparator/` and `docs/comparator.md`.

Note that a declaration in the closure must be reproducible *by name*. A `local instance`
or an instance argument that is a proof gets an auto-generated name derived from whichever
declaration happens to need it first, and that ordering is not the same in the library and
in a Mathlib-only file; when the comparator reports `Const does not match`, this is the
usual cause, and the fix is to give the declaration an explicit name in the library.

## Status

The check does not pass yet. The current state, and the outstanding library-side fix, are
tracked in the library repository under issue 645.

---

The design follows the challenge repository of the companion low individual degree test
formalization, [LionSR/LDT-comparator](https://github.com/LionSR/LDT-comparator), and the
Lean reference manual's *Validating Proofs* chapter.


## Why the challenge is more than one file

`Challenge.lean` imports one Mathlib-only module per MIPStarRE module that
contributes to the statement closure, under `Challenge/<library path>.lean`,
and states the target theorems with `sorry`.  Each part imports Mathlib plus
the mirrors of the library modules its source module imports; nothing here ever
imports the library.

The partition is not cosmetic.  Lean caches an abstracted nested proof and a
`match` auxiliary *per module*, keyed by the statement, and names it after
whichever declaration of that module first needed it; instance synthesis inside
a module only sees what that module's imports declare; and comparator compares
the full `ConstantInfo` of every closure constant, values and proofs included.
A single-file challenge cannot reproduce an auxiliary name whenever the library
needs the same fact in two modules, and it lets every instance reach every
declaration.  Mirroring the library's module partition and import graph
reproduces both by construction: with it, comparator accepts; without it, it
reported 26 mismatching closure constants on exactly this library commit.

The files are generated from the library by
`scripts/comparator/check_challenge_drift.py --challenge qpbt --update` in the
MIPStarRE-A repository, which also guards them against drift in that
repository's CI.  The whole set is the human audit surface.
