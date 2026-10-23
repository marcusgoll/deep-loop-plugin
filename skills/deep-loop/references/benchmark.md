# Phase 7 recorded fixture comparison

Use `scripts/benchmark.py INPUT.json OUTPUT.json` to compare already recorded `baseline` and `candidate` fixture sets through the Phase 6 evaluator. Both sets must have exactly the same scenario IDs and required-check sets for each ID; ordering is immaterial. Missing/failed evidence remains visible as not_proven evaluation outcomes rather than being discarded. Pass-rate delta is arithmetic over the supplied records.

This is not an empirical benchmark or evidence that one skill/model is better. It authenticates no artifact, executes no scenario, blinds no judge and measures no runtime/cost/intervention/detection rate. For behavioral claims, retain the existing identical-task/no-guidance control and independent blinded-review procedure with actual execution evidence. Scenario/check labels alone do not prove the tasks, inputs or proof semantics were identical.

The CLI validates before exclusively creating a new output. Existing/concurrent paths are preserved; interrupted writes remain incomplete evidence. Exit 0 means a valid comparison report was saved, including not_proven cases; exit 2 rejects mismatched/bad input or output/I/O failure. This cannot satisfy acceptance, native-goal completion or SHIP gates.

Run `py -3 -B scripts/test_benchmark.py`; the existing package suite includes it.
