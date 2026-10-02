# Palomar preparation checker

This directory contains a non-executing preparation and report-content checker
for the Palomar submission snapshot. It does not replace Palomar's workflows or
the existing companion-review lane that authenticates their artifacts.

Run the focused fixtures:

```sh
python3 -m unittest discover -s tools/palomar/tests -v
```

Generate the deterministic report against the substantive repository's pinned
revision (the path is read-only and is not written into the report):

```sh
python3 tools/palomar/check.py report \
  --substantive-repo /path/to/MIPStarRE-QPBT \
  --output reports/palomar-mechanical.json
```

`check` prints the same report without writing it. Both commands exit nonzero
when a static requirement fails; `unknown` report-evidence checks do not hide a
static failure. The report hashes every wrapper input except its own output and
binds the separately pinned Lean sources by Git tree and aggregate content
hashes. It deliberately contains no wrapper commit SHA, so committing a
regenerated report is not self-referential.

Evidence classes are explicit:

- `schema` validates `formalization.yaml` with the vendored official v0.4
  schema snapshot.
- `static` checks repository bytes, source text, Lake metadata, imports, and
  comparator configuration. Static checks cannot certify a proof or an axiom
  closure. In particular, the Challenge import check proves only that direct
  import spellings use approved prefixes and do not name local files. For a
  separately pinned substantive repository, the checker measures every regular
  tracked blob at the declared revision with Git object-size metadata, enforces
  the official 500 MiB cap, and checks that revision for submodules and cached
  `filter=lfs` attributes. Dirty files, untracked files, `.lake`, and symlink
  blob contents do not affect that immutable-tree measurement; `.lean`
  symlinks remain a source-requirements failure.
- `report-content` parses a supplied full-run JSON report in the producer's
  real shape. It checks the exact source commit and selected paths, declaration
  and axiom lists, the top-level `kernels` records, and the byte-digested JSON
  string in `protected_config`. It also checks the report's resolved Challenge
  origins. The official report records omitted optional path inputs as empty
  strings, so an empty metadata request is accepted only when the selected
  report record is the default project `formalization.yaml` with the local
  file's digest. This class does not authenticate where the JSON came from.

Pass a runtime report with `--official-report` only after the companion-review
lane has bound its artifact to the pinned workflow revision and exact
run/attempt/job. The local checker deliberately has no API client or signature
mechanism. Its synthetic unit reports test content validation only; they do not
establish that a kernel or workflow ran.

Missing runtime evidence leaves public-source and resolved transitive-import
checks `unknown`. A matching report-content check is not registry acceptance.

## Final exact-head sequence

1. Finalize every wrapper input, generate the deterministic report without
   `--official-report`, and commit the wrapper as fixed commit `H`. The tracked
   report is a pre-verification report and must retain every real failure or
   unknown.
2. Push `H` and run the immutable reusable full Palomar workflow in this
   repository. Do not amend `H` with the resulting report.
3. Let the existing companion-review lane authenticate the runtime artifact,
   workflow revision, source commit, run, attempt, and job.
4. In a clean checkout of exactly `H`, keep the authenticated artifact outside
   the checkout and run:

   ```sh
   mkdir -p /path/to/MIPStarRE-QPBT/results/palomar
   python3 tools/palomar/check.py check \
     --substantive-repo /path/to/MIPStarRE-QPBT \
     --official-report /path/to/authenticated/mechanical-report.json \
     > /path/to/MIPStarRE-QPBT/results/palomar/qpbt-comparator-H.json
   ```

   The checker still requires source commit `H` and a clean worktree. Redirecting
   stdout to the primary library repository avoids a report-commit cycle.
5. MAIN commits that final local output with the owner submission note in the
   primary repository. The wrapper remains at `H`.

## Pending final integration

- Replace the historical dependency URL, revision, Lean toolchain, and manifest
  together with one main-reachable MIPStarRE-QPBT revision that contains the
  three compact solution modules and the completed all-source module migration.
- Pin a substantive revision below Palomar's 500 MiB source cap. Until then the
  preparation report must remain red and record the measured committed-tree
  byte count.
- Replay the exact single-file Challenge and three-module Solution on the
  supported toolchain, then run the pinned reusable full workflow and
  authenticate its artifact through the companion-review lane.
- Keep `review.status: unchecked` until a real human review is recorded.
- The owner must confirm final credit and submission authorization in the
  submission note/form. This draft records Ruixuan Deng as responsible owner,
  records the source authors as not contacted, and makes no authority or
  endorsement claim.

The upstream snapshots are byte-pinned in `palomar-check.json`. The module
header, physical-line, configuration-byte, and cached Git-attribute rules track
PalomarSubmission revision `65f0154ed776cd26c224254aa57b379137f28b0d`.
