# New-skill migration history

PR #2 merged the legacy-to-Codex migration at commit 30c2a4be2302c0ed483af88362dd6ed9445d47f0. All 53 tracked legacy files remain byte-for-byte under legacy/claude-code, with Git history and licenses retained.

This update replaces the v0.5.6 package with the independently reviewed v0.5.9 snapshot: 44 files copied without packaging adjustments. release-manifest.json binds the exact reviewed source and public copy. The current update does not modify the legacy archive.

The local Mac installation was separately promoted to v0.5.9 and hash-verified. Other hosts, release tags, deployments and unattended pilot enrollment are outside this public package update.

## v0.6.1 synchronization

This update replaces the v0.5.9 snapshot with the current 83-file installed skill. The release manifest records both installed-source and repository hashes. Thirty text files use LF instead of installed CRLF; no other packaging changes apply.

The controller runtime was extracted into its own local app before this synchronization. Deep Loop remains the skill that can use that app. The legacy archive, licenses and history remain unchanged. This update does not publish the controller app, enroll workers, merge the PR, create a release or activate services.
