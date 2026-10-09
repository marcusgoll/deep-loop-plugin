# New-skill migration readiness

This preview preserves every tracked file from the legacy commit, byte for byte, under legacy/claude-code. Root license and Git attribute/ignore files also remain available. No legacy hooks or plugin manifest remain at the root runtime entrypoints.

Capture verified all 43 v0.5.6 source files against the passing independent review manifest, rechecked source hashes before/after, and verified every copied file. The public package then normalizes four trailing blank-line sequences. Both the reviewed baseline digest and those exact before/after adjustments are recorded in release-manifest.json. Local current-package checks pass against the adjusted package. This draft migration is published; final migration review, merge and release approval remain pending. The scoped review does not establish completion of the broader optimization. The known installed 0.5.0 baseline and historical 0.5.2 candidate are not selected release sources.

No runtime install, promotion, legacy tag creation, GitHub workflow dispatch, repository rename, merge, or deployment has occurred.
