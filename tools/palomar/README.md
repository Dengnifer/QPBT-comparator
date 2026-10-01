# Palomar preparation checker

This directory contains a non-executing preparation check for the Palomar
submission snapshot. It does not replace Palomar's official preparation and
verification workflows.

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
when a static requirement fails; `unknown` authoritative checks do not hide a
static failure. The report hashes every wrapper input except its own output and
binds the separately pinned Lean sources by Git tree and aggregate content
hashes. It deliberately contains no wrapper commit SHA, so committing a
regenerated report is not self-referential.

Evidence classes are explicit:

- `schema` validates `formalization.yaml` with the vendored official v0.4
  schema snapshot.
- `static` checks repository bytes, source text, Lake metadata, imports, and
  comparator configuration. Static checks cannot certify a proof or an axiom
  closure.
- `authoritative` remains `unknown` until an official Palomar/comparator report
  for the final integrated source snapshot is supplied and reviewed. A source
  scan is never promoted to proof evidence.

For an exact-head gate, pass the downloaded official report with
`--official-report`. It is accepted only when it reports a completed pass for
the current Git head, the configured wrapper repository, the four expected
declarations, the standard axiom set, and protected `nanoda` and `con-ron`
kernels.

## Pending final integration

- Replace the old split Challenge and old library pin, then regenerate this
  report against the final substantive revision.
- Confirm the final toolchain against Palomar's then-current minimum and update
  the vendored policy snapshots if upstream changed.
- Keep `review.status: unchecked` until a real human review is recorded.
- The owner must confirm final credit and submission authorization in the
  submission note/form. This draft records Ruixuan Deng as responsible owner,
  records the source authors as not contacted, and makes no authority or
  endorsement claim.

The upstream snapshots are byte-pinned in `palomar-check.json`. The module
header and physical-line rules track PalomarSubmission revision
`65f0154ed776cd26c224254aa57b379137f28b0d`.
