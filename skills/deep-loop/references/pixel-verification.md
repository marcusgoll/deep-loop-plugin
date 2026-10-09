# Pixel verification

Use when selected-reference fidelity or screenshot regression is required. Prefer existing project screenshot assertions; otherwise use the [local comparator](../scripts/pixel_diff.py) from this skill. Requires Python and Pillow; reuse the installed dependency runtime rather than installing another framework. If either is unavailable, report BLOCKED.

Resolve an approved reference and acceptance thresholds before comparing. An image/mockup is a fidelity target; an approved app screenshot is a regression baseline. Capture the actual implementation through the selected browser at matching viewport, crop, interaction state, theme, content, fonts, pixel density, and environment. Record those conditions and the source/build revision in `design-qa.md`. This script compares saved pixels only; it cannot establish capture provenance or approval.

```powershell
py -3 '<installed deep-loop skill>/scripts/pixel_diff.py' --expected '<approved.png>' --actual '<capture.png>' --output '<new evidence directory>' --tolerance 0 --max-diff-ratio 0
```

Zero tolerance and zero differing-pixel ratio request exact equality; they are not universal mockup acceptance thresholds. Use the acceptance contract's declared values. `--tolerance` is the allowed absolute difference per RGBA channel (0–255); a pixel differs when any channel exceeds it. `--max-diff-ratio` is the allowed fraction of differing pixels (0–1). There is no antialiasing exemption or automatic alignment, scaling, cropping, or masking. RGBA values are compared, including alpha. Any agreed density/crop normalization happens separately, with original captures and its provenance retained.

For critical regions, repeat `--region X,Y,WIDTH,HEIGHT` and explicitly set `--region-max-diff-ratio` (0–1). All regions and the full image must pass; an average cannot hide a critical-region failure. Regions must fit inside the matched images. Different dimensions, invalid inputs, or missing captures are BLOCKED, not a visual defect verdict.

The output directory must not already exist. The comparator leaves input files untouched and saves normalized lossless `expected.png`, `actual.png`, a magenta changed-pixel `diff.png`, and `result.json`. The result includes thresholds, dimensions, per-region/global measurements, source-image and verifier hashes, runtime versions, and status. Native exits: 0 = PASS, 1 = FAIL, 2 = BLOCKED. A blocked run retains available evidence and does not invent a diff.

Run `py -3 '<installed deep-loop skill>/scripts/test_pixel_diff.py'` before first reliance on this verifier. It exercises known-good and known-bad fixtures, thresholds, alpha, critical regions, blocked dimensions/inputs, and output preservation. Keep pixel results in `design-qa.md` alongside human comparison and exercised interactions/accessibility. Required FAIL/BLOCKED prevents handoff. Do not relax thresholds or update the reference merely to pass. New captures need new evidence directories.

Deep Loop owns this verifier outside the plugin cache. The installed Product Design integration is a local customization that updates may replace; Deep Loop can still call its durable verifier directly. This does not modify upstream Product Design or provide a screenshot capture engine, scheduler, or complete shared gate reader.
