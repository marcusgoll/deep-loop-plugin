# Phase 6 recorded fixture evaluation

Use `scripts/evaluate.py INPUT.json OUTPUT.json` to summarize already recorded deterministic fixture results. This is an optional report tool, separate from existing `verify_skill.py` model trials, blinded comparisons and closure gates. It neither executes fixtures nor reads artifacts.

Input has a nonempty `scenarios` list. Each scenario has a unique nonblank `id`, nonempty unique string `required_checks`, and an `evidence` object keyed by check ID. A recorded passing check has exactly boolean `passed: true` and a 64-character lowercase hexadecimal `artifact_sha256` string. Missing evidence is `incomplete`; failed/malformed evidence is `failed`. A detected failure takes precedence over missing entries, while both lists remain visible. Every required check in every scenario must pass for `overall: passed`.

The output shape is [evaluation.schema.json](../schemas/evaluation.schema.json). Pass count/rate summarize the supplied records only. A plausible digest need not correspond to a file, and a passed flag authenticates no execution. Inspect artifacts and actual results through existing proof requirements before relying on this report. Do not label these counts model reliability, security assurance, live delivery or causal improvement.

The CLI validates before exclusively creating a new report, preserving preexisting/concurrent output. Exit 0 reports all scenarios passed, exit 1 reports `not_proven`, and exit 2 rejects input/output/I/O. A `not_proven` report retains all failing/missing cases; do not waive them by citing a partial pass rate. Preserve interrupted output and diagnose before selecting a new output path.

For a comparative model/skill experiment, use the existing controlled trial and blind-review procedure with identical cases, no-guidance control, attributable revisions and raw failure evidence. This summarizer collects no detection rate, intervention count, runtime cost or model identity; retain those only when actually measured by the existing harness. Schemas document output shape, not full JSON Schema validation by the CLI.

Run `py -3 -B scripts/test_evaluation.py`; the existing package suite includes these tests. No model-behavior comparison is performed by installation.
